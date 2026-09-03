"""Broadcast Readable v2 BR-15~BR-18 폐쇄 조건을 검증한다."""

import asyncio
import json
import os
from collections.abc import Mapping, Sequence
from copy import deepcopy
from pathlib import Path
from shutil import copytree, rmtree
from typing import cast

import pytest
from runtime.support import create_runtime_project, create_runtime_repository
from test_broadcast_readable_v2_runtime import project_task_outputs
from test_broadcast_readable_v2_source_fixtures import apply_feature_fixture
from test_broadcast_readable_v2_validation import (
    build_report,
    pilot_fixture,
    render_fixture,
)

from RUNTIME.contracts import load_artifact_contracts, load_task_catalog
from RUNTIME.engine import execute_run
from RUNTIME.errors import RuntimeExecutionError
from RUNTIME.event_store import utc_now
from RUNTIME.models import GenerationOptions, LLMMessage, LLMRequest, OutputContract
from RUNTIME.output_gateway import validate_artifact_content
from RUNTIME.planner import task_condition_matches
from RUNTIME.providers.fake import fake_screenplay_units
from RUNTIME.transactions import (
    acquire_project_lock,
    commit_gate_transaction,
    release_project_lock,
    write_artifact,
)
from VALIDATORS.broadcast_readable import production_readable_deliverable_issues
from VALIDATORS.broadcast_readable_v2 import consume_actual_block
from VALIDATORS.candidate_evaluation import document_sha256
from VALIDATORS.config_admission import (
    admit_broadcast_readable_config,
    broadcast_readable_config_admission_issues,
)
from VALIDATORS.dependency import (
    artifact_hash,
    artifact_required_for_project,
    invalidate_artifact_dependents,
)
from VALIDATORS.exceptions import ConfigurationError
from VALIDATORS.gate_transaction import (
    audit_project,
    task_inputs_support_validated_reuse,
    task_open,
    task_submit,
    trace_records,
)
from VALIDATORS.io import load_json_object, write_json_object
from VALIDATORS.library_store import sync_novelty_gate
from VALIDATORS.models import ProjectState
from VALIDATORS.output_profiles import broadcast_readable_activation_mode
from VALIDATORS.presentation_validation import validate_presentation_design
from VALIDATORS.production_cli import build_parser, run_cli
from VALIDATORS.requirements import production_manifest_required

ROOT = Path(__file__).resolve().parents[1]
PILOT_ROOT = ROOT / "PROJECTS/PRJ-006"
ADMITTED_AT = "2026-09-03T01:00:00Z"
READABLE_INVALIDATION = {
    "broadcast_readable_script",
    "broadcast_readable_report",
    "production_broadcast_readable_script",
    "production_manifest",
    "editorial_review",
}


def mapping_list(document: dict[str, object], field: str) -> list[dict[str, object]]:
    """필수 객체 배열을 구체적인 사전 목록으로 반환한다."""
    value = document[field]
    assert isinstance(value, list)
    assert all(isinstance(item, dict) for item in value)
    return [item for item in value if isinstance(item, dict)]


def unit_by_id(fixture: Mapping[str, object], unit_id: str) -> dict[str, object]:
    """Fixture에서 지정 Unit을 고유하게 찾는다."""
    screenplay_units = fixture["screenplay_units"]
    assert isinstance(screenplay_units, dict)
    matches = [
        unit
        for scene in mapping_list(screenplay_units, "scenes")
        for unit in mapping_list(scene, "units")
        if unit.get("unit_id") == unit_id
    ]
    assert len(matches) == 1
    return matches[0]


def issue_codes(issues: Sequence[Mapping[str, object]]) -> set[str]:
    """검증 Issue Code 집합을 반환한다."""
    return {
        str(issue["code"])
        for issue in issues
        if isinstance(issue.get("code"), str)
    }


def normalize_unadmitted_pilot(project_path: Path) -> None:
    """격리 복사본을 공식 Config Admission 이전 Revision 5 상태로 되돌린다."""
    state_path = project_path / "00_PROJECT/project_state.json"
    state = load_json_object(state_path)
    readiness = state["readiness"]
    artifacts = state["artifacts"]
    assert isinstance(readiness, dict)
    assert isinstance(artifacts, dict)
    readiness["process_revision"] = 5
    readiness["process_start_gate"] = "GATE-08"
    config_state = artifacts["broadcast_readable_config"]
    assert isinstance(config_state, dict)
    config_state.update(
        {
            "status": "MISSING",
            "content_hash": None,
            "invalidated_by": [],
        }
    )
    write_json_object(state_path, state)

    change_log_path = project_path / "00_PROJECT/change_log.jsonl"
    retained_change_log: list[str] = []
    for line in change_log_path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        record = json.loads(line)
        assert isinstance(record, dict)
        if record.get("event") == "BROADCAST_READABLE_CONFIG_ADMITTED":
            break
        retained_change_log.append(line)
    change_log_path.write_text(
        "\n".join(retained_change_log) + "\n",
        encoding="utf-8",
    )

    trace_path = project_path / "00_PROJECT/process_trace.jsonl"
    retained_traces = [
        line
        for line in trace_path.read_text(encoding="utf-8").splitlines()
        if line.strip() and json.loads(line).get("process_revision") != 6
    ]
    trace_path.write_text("\n".join(retained_traces) + "\n", encoding="utf-8")

    task_root = project_path / ".runtime/codex_tasks"
    if task_root.is_dir():
        for task_path in sorted(task_root.glob("*/task.json")):
            task = load_json_object(task_path)
            if task.get("process_revision") == 6:
                rmtree(task_path.parent)


def copied_pilot_repository(tmp_path: Path) -> tuple[Path, Path]:
    """Runtime 계약과 Canonical Pilot만 가진 격리 Repository를 만든다."""
    repository_root = tmp_path / "repository"
    for directory in (
        "AGENTS",
        "STANDARD",
        "CHANNELS",
        "RUNTIME",
        "STORY_LIBRARY",
        "VALIDATORS",
    ):
        copytree(ROOT / directory, repository_root / directory)
    project_path = repository_root / "PROJECTS/PRJ-006"
    copytree(
        PILOT_ROOT,
        project_path,
        ignore=lambda _directory, names: {".runtime"}.intersection(names),
    )
    normalize_unadmitted_pilot(project_path)
    return repository_root, project_path


def copied_pilot_repository_with_runtime(tmp_path: Path) -> tuple[Path, Path]:
    """과거 실행 근거까지 포함한 격리 Pilot Repository를 만든다."""
    repository_root = tmp_path / "repository"
    for directory in (
        "AGENTS",
        "STANDARD",
        "CHANNELS",
        "RUNTIME",
        "STORY_LIBRARY",
        "VALIDATORS",
    ):
        copytree(ROOT / directory, repository_root / directory)
    project_path = repository_root / "PROJECTS/PRJ-006"
    copytree(PILOT_ROOT, project_path)
    normalize_unadmitted_pilot(project_path)
    return repository_root, project_path


def admission_canonical_bytes(project_path: Path) -> dict[str, bytes]:
    """Admission Transaction의 세 Canonical Target Byte를 캡처한다."""
    return {
        relative_path: (project_path / relative_path).read_bytes()
        for relative_path in (
            "00_PROJECT/broadcast_readable_config.json",
            "00_PROJECT/project_state.json",
            "00_PROJECT/change_log.jsonl",
        )
    }


def project_canonical_bytes(project_path: Path) -> dict[str, bytes]:
    """Runtime 운영 경로를 제외한 Project 전체 Byte Snapshot을 반환한다."""
    return {
        path.relative_to(project_path).as_posix(): path.read_bytes()
        for path in sorted(project_path.rglob("*"))
        if path.is_file() and ".runtime" not in path.relative_to(project_path).parts
    }


def build_footprint_off_readable_chain(
    project_path: Path,
    project_constraints: dict[str, object],
) -> tuple[str, dict[str, object], str, dict[str, object]]:
    """Footprint 입력 없이 v2 Readable·Report·Copy·Manifest를 순차 생성한다."""
    fixture = pilot_fixture()
    overlay: dict[str, object] = {
        "broadcast_readable_config": fixture["config"],
        "project_constraints": project_constraints,
    }
    overlay.update(
        project_task_outputs(
            "script.render_broadcast_readable",
            project_path,
            overlay,
        )
    )
    overlay.update(
        project_task_outputs(
            "continuity.validate_broadcast_readable",
            project_path,
            overlay,
        )
    )
    overlay["validation_report"] = {"result": "PASS"}
    overlay.update(
        project_task_outputs(
            "production.package_broadcast_readable",
            project_path,
            overlay,
        )
    )
    outputs = project_task_outputs(
        "production.build_manifest",
        project_path,
        overlay,
    )
    readable = overlay["broadcast_readable_script"]
    report = overlay["broadcast_readable_report"]
    production_copy = overlay["production_broadcast_readable_script"]
    manifest = outputs["production_manifest"]
    assert isinstance(readable, str)
    assert isinstance(report, dict)
    assert isinstance(production_copy, str)
    assert isinstance(manifest, dict)
    return readable, report, production_copy, manifest


def fake_screenplay_candidate(project_path: Path, project_id: str) -> dict[str, object]:
    """Plumbing 검증용 FakeProvider Screenplay 후보를 명시 Context로 만든다."""
    graph = load_json_object(ROOT / "STANDARD/dependency_graph.json")
    definitions = graph["artifacts"]
    assert isinstance(definitions, dict)
    context_names = (
        "characters",
        "viewer_timeline",
        "clue_matrix",
        "crime_event_contract",
        "scene_cards",
    )
    context_items: list[dict[str, object]] = []
    for artifact_name in context_names:
        definition = definitions[artifact_name]
        assert isinstance(definition, dict)
        relative_path = definition["path"]
        assert isinstance(relative_path, str)
        context_items.append(
            {
                "artifact_name": artifact_name,
                "content": load_json_object(project_path / relative_path),
            }
        )
    message = LLMMessage(
        role="user",
        content=(
            '<CONTEXT_DATA instructional="false">\n'
            f"{json.dumps(context_items, ensure_ascii=False)}\n"
            "</CONTEXT_DATA>"
        ),
    )
    request = LLMRequest(
        request_id="REQ-FAKE-CLOSURE",
        idempotency_key="0" * 64,
        model_ref="fake",
        messages=(message,),
        output_contract=OutputContract(
            mode="JSON_OBJECT",
            name="SCREENPLAY_UNITS",
            json_schema=None,
        ),
        generation=GenerationOptions(
            max_output_tokens=4096,
            temperature=0.0,
            top_p=1.0,
            seed=None,
            stop=(),
        ),
        tools=(),
        deadline_ms=120000,
        metadata={"task_id": "script.compose_screenplay_units"},
        extensions={},
    )
    return fake_screenplay_units(request, project_id, "ORIGINAL_FICTION")


def install_source_style_fixture(
    repository_root: Path,
    project_path: Path,
    fixture_id: str,
) -> set[str]:
    """R1·R2 Source와 결정론적 GATE-08 파생 후보를 Canonical에 배치한다."""
    fixture = apply_feature_fixture(fixture_id)
    for document_name in (
        "config",
        "screenplay_units",
        "characters",
        "relationships",
        "panel_cast",
        "reaction_segments",
        "presentation_plan",
    ):
        fixture[document_name]["project_id"] = "PRJ-006"
    overlay: dict[str, object] = {
        "broadcast_readable_config": fixture["config"],
        "screenplay_units": fixture["screenplay_units"],
        "characters": fixture["characters"],
        "relationships": fixture["relationships"],
        "panel_cast": fixture["panel_cast"],
        "reaction_segments": fixture["reaction_segments"],
        "presentation_plan": fixture["presentation_plan"],
    }
    overlay.update(
        project_task_outputs(
            "script.render_screenplay_layers",
            project_path,
            overlay,
        )
    )
    overlay.update(
        project_task_outputs(
            "script.render_broadcast_master",
            project_path,
            overlay,
        )
    )
    overlay.update(
        project_task_outputs(
            "script.render_reenactment_export",
            project_path,
            overlay,
        )
    )
    overlay.update(
        project_task_outputs(
            "script.render_broadcast_readable",
            project_path,
            overlay,
        )
    )
    graph = load_json_object(repository_root / "STANDARD/dependency_graph.json")
    definitions = graph["artifacts"]
    assert isinstance(definitions, dict)
    installed = {
        "broadcast_readable_config",
        "characters",
        "relationships",
        "panel_cast",
        "reaction_segments",
        "presentation_plan",
        "screenplay_units",
        "drama_script",
        "narration_script",
        "panel_reaction_script",
        "draft_script",
        "final_script",
        "reenactment_character_script",
        "broadcast_readable_script",
    }
    for artifact_name in sorted(installed):
        definition = definitions[artifact_name]
        assert isinstance(definition, dict)
        relative_path = definition["path"]
        assert isinstance(relative_path, str)
        write_artifact(project_path / relative_path, overlay[artifact_name])
    return installed


def prepare_source_style_gate_project(
    tmp_path: Path,
    fixture_id: str,
    process_revision: int,
) -> tuple[Path, Path]:
    """R1·R2를 미검증 DIRTY Source로 둔 GATE-04 직전 Project를 만든다."""
    repository_root, project_path = copied_pilot_repository(tmp_path)
    installed = install_source_style_fixture(
        repository_root,
        project_path,
        fixture_id,
    )
    state_path = project_path / "00_PROJECT/project_state.json"
    state = cast(ProjectState, load_json_object(state_path))
    state["current_gate"] = "GATE-03"
    state["state"] = "CASE_DEFINED"
    state["readiness"] = {
        "artifact_status": "INCOMPLETE",
        "contract_status": "UNVALIDATED",
        "process_status": "NONCONFORMANT",
        "editorial_status": "NOT_REVIEWED",
        "process_start_gate": "GATE-04",
        "process_revision": process_revision,
    }
    graph = load_json_object(repository_root / "STANDARD/dependency_graph.json")
    for artifact_name in sorted(installed - {"broadcast_readable_config"}):
        definition = graph["artifacts"]
        assert isinstance(definition, dict)
        artifact_definition = definition[artifact_name]
        assert isinstance(artifact_definition, dict)
        relative_path = artifact_definition["path"]
        assert isinstance(relative_path, str)
        state = invalidate_artifact_dependents(
            graph,
            state,
            artifact_name,
            artifact_hash((project_path / relative_path).read_bytes()),
            "2026-09-03T03:00:00Z",
        )
    write_json_object(state_path, state)
    admit_broadcast_readable_config(
        project_path,
        project_path / "00_PROJECT/broadcast_readable_config.json",
        "fixture-builder",
        f"{fixture_id} Config 승인",
        "2026-09-03T03:01:00Z",
    )
    return repository_root, project_path


def submit_gate_until_committed(
    repository_root: Path,
    project_path: Path,
    gate_id: str,
    started_at: str,
    completed_at: str,
) -> dict[str, object]:
    """현재 Gate의 LLM 단계와 CORE 단계를 모두 진행해 Commit 결과를 반환한다."""
    result = task_open(
        repository_root,
        project_path,
        gate_id,
        started_at,
        None,
    )
    for _attempt in range(12):
        if result.get("status") == "COMMITTED":
            return result
        result = task_submit(
            repository_root,
            project_path,
            gate_id,
            completed_at,
            None,
        )
    raise AssertionError(f"Gate Transaction이 완료되지 않았습니다: gate_id={gate_id}")


def test_audit_rejects_existing_v2_config_with_missing_state_entry(
    tmp_path: Path,
) -> None:
    """실제 Config가 있는데 State가 MISSING이면 Audit가 완료를 거부한다."""
    project_path = tmp_path / "PRJ-006"
    copytree(PILOT_ROOT, project_path)
    state_path = project_path / "00_PROJECT/project_state.json"
    state = load_json_object(state_path)
    artifacts = state["artifacts"]
    assert isinstance(artifacts, dict)
    artifacts["broadcast_readable_config"] = {
        "status": "MISSING",
        "content_hash": None,
        "invalidated_by": [],
    }
    write_json_object(state_path, state)

    report = audit_project(
        ROOT,
        project_path,
        None,
        None,
        "2026-09-03T00:00:00Z",
    )

    assert report["result"] == "FAIL"
    raw_process_issues = report["process_issues"]
    assert isinstance(raw_process_issues, list)
    process_issues = [
        issue for issue in raw_process_issues if isinstance(issue, dict)
    ]
    assert "CANONICAL_ARTIFACT_DRIFT" in issue_codes(process_issues)


def test_config_admission_backfills_state_and_invalidates_exact_chain(
    tmp_path: Path,
) -> None:
    """기존 Config도 공식 Admission으로 CLEAN 등록하고 Readable 하위만 무효화한다."""
    repository_root, project_path = copied_pilot_repository(tmp_path)
    state_before = load_json_object(project_path / "00_PROJECT/project_state.json")
    artifacts_before = state_before["artifacts"]
    assert isinstance(artifacts_before, dict)

    result = admit_broadcast_readable_config(
        project_path,
        project_path / "00_PROJECT/broadcast_readable_config.json",
        "codex-app",
        "기존 v2 Config를 공식 경로로 등록",
        ADMITTED_AT,
    )

    assert result["result"] == "COMMITTED"
    assert set(result["invalidated_artifacts"]) == READABLE_INVALIDATION
    state_after = load_json_object(project_path / "00_PROJECT/project_state.json")
    artifacts_after = state_after["artifacts"]
    readiness = state_after["readiness"]
    assert isinstance(artifacts_after, dict)
    assert isinstance(readiness, dict)
    config_state = artifacts_after["broadcast_readable_config"]
    assert isinstance(config_state, dict)
    assert config_state == {
        "status": "CLEAN",
        "content_hash": result["config_file_sha256"],
        "invalidated_by": [],
    }
    assert state_after["current_gate"] == "GATE-07"
    assert state_after["state"] == "BLOCKED"
    assert readiness["process_start_gate"] == "GATE-08"
    assert readiness["process_revision"] == 6
    for artifact_name, artifact_state in artifacts_after.items():
        assert isinstance(artifact_state, dict)
        if artifact_name in READABLE_INVALIDATION:
            assert artifact_state["status"] == "DIRTY"
            assert artifact_state["invalidated_by"] == [
                "broadcast_readable_config"
            ]
        elif artifact_name != "broadcast_readable_config":
            assert artifact_state == artifacts_before[artifact_name]
    typed_state = cast(ProjectState, state_after)
    assert broadcast_readable_config_admission_issues(
        repository_root,
        project_path,
        typed_state,
    ) == []


def test_config_admission_cli_help_and_transaction(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """공식 CLI의 Help 계약과 실제 Admission Transaction을 검증한다."""
    parser = build_parser()
    with pytest.raises(SystemExit) as help_exit:
        parser.parse_args(["broadcast-readable-config-set", "--help"])
    assert help_exit.value.code == 0
    help_output = capsys.readouterr().out
    for option in ("project_path", "--input", "--actor", "--reason"):
        assert option in help_output

    _repository_root, project_path = copied_pilot_repository(tmp_path)
    config_path = project_path / "00_PROJECT/broadcast_readable_config.json"
    exit_code = run_cli(
        [
            "broadcast-readable-config-set",
            str(project_path),
            "--input",
            str(config_path),
            "--actor",
            "closure-test",
            "--reason",
            "Config Admission CLI 통합 검증",
        ]
    )
    result = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert result["result"] == "COMMITTED"
    state = load_json_object(project_path / "00_PROJECT/project_state.json")
    artifacts = state["artifacts"]
    assert isinstance(artifacts, dict)
    config_state = artifacts["broadcast_readable_config"]
    assert isinstance(config_state, dict)
    assert config_state["status"] == "CLEAN"
    assert config_state["content_hash"] == artifact_hash(config_path.read_bytes())


@pytest.mark.parametrize(
    "mutation",
    ["schema", "project", "profile"],
)
def test_config_admission_rejects_invalid_candidate_without_canonical_change(
    tmp_path: Path,
    mutation: str,
) -> None:
    """Schema·Project·Profile 오류는 Canonical 파일을 하나도 바꾸지 않는다."""
    _repository_root, project_path = copied_pilot_repository(tmp_path)
    candidate = load_json_object(
        project_path / "00_PROJECT/broadcast_readable_config.json"
    )
    if mutation == "schema":
        candidate["unregistered_field"] = True
    elif mutation == "project":
        candidate["project_id"] = "PRJ-999"
    elif mutation == "profile":
        candidate["profile_version"] = "9.9.9"
    else:
        raise AssertionError(f"알 수 없는 Mutation입니다: {mutation}")
    input_path = tmp_path / f"candidate-{mutation}.json"
    write_json_object(input_path, candidate)
    before = admission_canonical_bytes(project_path)

    with pytest.raises(ConfigurationError):
        admit_broadcast_readable_config(
            project_path,
            input_path,
            "codex-app",
            f"{mutation} 오류 검증",
            ADMITTED_AT,
        )

    assert admission_canonical_bytes(project_path) == before


@pytest.mark.parametrize("registry_mutation", ["hash", "path"])
def test_config_admission_rejects_invalid_profile_registry_binding(
    tmp_path: Path,
    registry_mutation: str,
) -> None:
    """Profile Hash와 Repository 경계 밖 경로 변조를 모두 거부한다."""
    repository_root, project_path = copied_pilot_repository(tmp_path)
    registry_path = repository_root / "CHANNELS/mystery_main/output_profiles/registry.json"
    registry = load_json_object(registry_path)
    profiles = registry["profiles"]
    assert isinstance(profiles, dict)
    profile = profiles["BROADCAST_READABLE_SCRIPT"]
    assert isinstance(profile, dict)
    versions = profile["versions"]
    assert isinstance(versions, dict)
    version = versions["2.0.0"]
    assert isinstance(version, dict)
    if registry_mutation == "hash":
        version["sha256"] = "0" * 64
    elif registry_mutation == "path":
        version["path"] = "../../outside.json"
    else:
        raise AssertionError(
            f"알 수 없는 Registry Mutation입니다: {registry_mutation}"
        )
    write_json_object(registry_path, registry)
    before = admission_canonical_bytes(project_path)

    with pytest.raises(ConfigurationError):
        admit_broadcast_readable_config(
            project_path,
            project_path / "00_PROJECT/broadcast_readable_config.json",
            "codex-app",
            "Profile 결속 검증",
            ADMITTED_AT,
        )

    assert admission_canonical_bytes(project_path) == before


def test_config_admission_rejects_open_gate_transaction(tmp_path: Path) -> None:
    """열린 Gate Transaction과 Config Admission의 동시 Writer를 차단한다."""
    _repository_root, project_path = copied_pilot_repository(tmp_path)
    write_json_object(
        project_path / ".runtime/codex_tasks/CODEX-TASK-OPEN/task.json",
        {
            "transaction_id": "CODEX-TASK-OPEN",
            "status": "OPEN",
        },
    )
    before = admission_canonical_bytes(project_path)

    with pytest.raises(ConfigurationError, match="CONFIG_ADMISSION_CONFLICT"):
        admit_broadcast_readable_config(
            project_path,
            project_path / "00_PROJECT/broadcast_readable_config.json",
            "codex-app",
            "Gate 충돌 검증",
            ADMITTED_AT,
        )

    assert admission_canonical_bytes(project_path) == before


def test_config_admission_rejects_lock_conflict(tmp_path: Path) -> None:
    """다른 Writer가 가진 Project Lock을 침범하지 않는다."""
    _repository_root, project_path = copied_pilot_repository(tmp_path)
    lock_path = acquire_project_lock(project_path, "OTHER-WRITER")
    before = admission_canonical_bytes(project_path)
    try:
        with pytest.raises(RuntimeExecutionError) as error_info:
            admit_broadcast_readable_config(
                project_path,
                project_path / "00_PROJECT/broadcast_readable_config.json",
                "codex-app",
                "Lock 충돌 검증",
                ADMITTED_AT,
            )
    finally:
        release_project_lock(lock_path, "OTHER-WRITER")

    assert error_info.value.code == "PROJECT_LOCKED"
    assert admission_canonical_bytes(project_path) == before


def test_config_admission_rejects_input_changed_after_snapshot(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Lock 획득 전후 외부 Candidate가 바뀌면 Stale 입력으로 거부한다."""
    _repository_root, project_path = copied_pilot_repository(tmp_path)
    input_path = tmp_path / "candidate.json"
    candidate = load_json_object(
        project_path / "00_PROJECT/broadcast_readable_config.json"
    )
    write_json_object(input_path, candidate)
    before = admission_canonical_bytes(project_path)

    def acquire_and_mutate(target_project: Path, run_id: str) -> Path:
        lock_path = acquire_project_lock(target_project, run_id)
        changed = deepcopy(candidate)
        changed["enabled"] = False
        changed.pop("profile_id")
        changed.pop("profile_version")
        write_json_object(input_path, changed)
        return lock_path

    monkeypatch.setattr(
        "VALIDATORS.config_admission.acquire_project_lock",
        acquire_and_mutate,
    )

    with pytest.raises(ConfigurationError, match="CONFIG_ADMISSION_STALE_INPUT"):
        admit_broadcast_readable_config(
            project_path,
            input_path,
            "codex-app",
            "Stale 입력 검증",
            ADMITTED_AT,
        )

    assert admission_canonical_bytes(project_path) == before


@pytest.mark.parametrize("failure_call", [1, 2, 3])
def test_config_admission_write_failure_restores_all_canonical_targets(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    failure_call: int,
) -> None:
    """Config·State·Log 어느 Replace가 실패해도 이전 Byte로 복구한다."""
    _repository_root, project_path = copied_pilot_repository(tmp_path)
    before = admission_canonical_bytes(project_path)
    original_replace = os.replace
    calls = 0

    def fail_selected_replace(source: Path, target: Path) -> None:
        nonlocal calls
        calls += 1
        if calls == failure_call:
            raise OSError(f"의도한 Admission Replace 실패: call={failure_call}")
        original_replace(source, target)

    monkeypatch.setattr("RUNTIME.transactions.os.replace", fail_selected_replace)

    with pytest.raises(RuntimeExecutionError) as error_info:
        admit_broadcast_readable_config(
            project_path,
            project_path / "00_PROJECT/broadcast_readable_config.json",
            "codex-app",
            "원자 복구 검증",
            ADMITTED_AT,
        )

    assert error_info.value.code == "TRANSACTION_ERROR"
    assert admission_canonical_bytes(project_path) == before
    records = list(
        (project_path / ".runtime/transactions").glob("*/transaction.json")
    )
    assert len(records) == 1
    assert load_json_object(records[0])["status"] == "ROLLED_BACK"


def test_config_admission_recovers_prepared_transaction_before_commit(
    tmp_path: Path,
) -> None:
    """중단된 PREPARED Transaction을 복구한 뒤 새 Admission을 Commit한다."""
    repository_root, project_path = copied_pilot_repository(tmp_path)
    dependency_graph = load_json_object(
        repository_root / "STANDARD/dependency_graph.json"
    )
    state_path = project_path / "00_PROJECT/project_state.json"
    original_state = cast(ProjectState, load_json_object(state_path))
    interrupted_state = deepcopy(original_state)
    interrupted_state["state"] = "BLOCKED"
    interrupted_state["updated_at"] = "2026-09-03T00:59:00Z"
    transaction_id = commit_gate_transaction(
        project_path,
        "INTERRUPTED-CONFIG-WRITER",
        "CONFIG-ADMISSION",
        project_path,
        {},
        dependency_graph,
        interrupted_state,
        {},
    )
    record_path = (
        project_path
        / ".runtime/transactions"
        / transaction_id
        / "transaction.json"
    )
    record = load_json_object(record_path)
    record["status"] = "PREPARED"
    record["committed_at"] = None
    write_json_object(record_path, record)

    result = admit_broadcast_readable_config(
        project_path,
        project_path / "00_PROJECT/broadcast_readable_config.json",
        "codex-app",
        "Crash Recovery 뒤 승인",
        ADMITTED_AT,
    )

    assert result["result"] == "COMMITTED"
    assert result["recovered_transaction_ids"] == [transaction_id]
    assert load_json_object(record_path)["status"] == "ROLLED_BACK"
    state = load_json_object(state_path)
    readiness = state["readiness"]
    assert isinstance(readiness, dict)
    assert readiness["process_revision"] == 6


@pytest.mark.parametrize(
    ("mutation", "expected_reason"),
    [
        ("clean_null", "CLEAN_HASH_MISSING"),
        ("hash_mismatch", "CONTENT_HASH_MISMATCH"),
        ("file_deleted", "CANONICAL_FILE_MISSING"),
        ("direct_edit", "CONTENT_HASH_MISMATCH"),
    ],
)
def test_config_state_drift_fails_read_only_audit(
    tmp_path: Path,
    mutation: str,
    expected_reason: str,
) -> None:
    """Config State·File Drift를 진단하되 Audit는 Canonical을 고치지 않는다."""
    repository_root, project_path = copied_pilot_repository(tmp_path)
    config_path = project_path / "00_PROJECT/broadcast_readable_config.json"
    admit_broadcast_readable_config(
        project_path,
        config_path,
        "codex-app",
        "Audit Drift 준비",
        ADMITTED_AT,
    )
    state_path = project_path / "00_PROJECT/project_state.json"
    state = load_json_object(state_path)
    artifacts = state["artifacts"]
    assert isinstance(artifacts, dict)
    config_state = artifacts["broadcast_readable_config"]
    assert isinstance(config_state, dict)
    if mutation == "clean_null":
        config_state["content_hash"] = None
        write_json_object(state_path, state)
    elif mutation == "hash_mismatch":
        config_state["content_hash"] = "0" * 64
        write_json_object(state_path, state)
    elif mutation == "file_deleted":
        config_path.unlink()
    elif mutation == "direct_edit":
        config = load_json_object(config_path)
        config["enabled"] = False
        config.pop("profile_id")
        config.pop("profile_version")
        write_json_object(config_path, config)
    else:
        raise AssertionError(f"알 수 없는 Drift Mutation입니다: {mutation}")
    before = project_canonical_bytes(project_path)

    report = audit_project(
        repository_root,
        project_path,
        None,
        None,
        "2026-09-03T01:10:00Z",
    )

    assert report["result"] == "FAIL"
    raw_issues = report["process_issues"]
    assert isinstance(raw_issues, list)
    drift = next(
        issue
        for issue in raw_issues
        if isinstance(issue, dict)
        and issue.get("code") == "CANONICAL_ARTIFACT_DRIFT"
    )
    details = drift["artifacts"]
    assert isinstance(details, list)
    assert expected_reason in {
        str(detail.get("reason"))
        for detail in details
        if isinstance(detail, dict)
    }
    assert project_canonical_bytes(project_path) == before


def test_disabled_config_overrides_v1_pins_and_reactivation_is_explicit(
    tmp_path: Path,
) -> None:
    """disabled 우선순위와 후속 명시적 v2 재활성화를 보존한다."""
    _repository_root, project_path = copied_pilot_repository(tmp_path)
    active_config = load_json_object(
        project_path / "00_PROJECT/broadcast_readable_config.json"
    )
    disabled_config = deepcopy(active_config)
    disabled_config["enabled"] = False
    disabled_config.pop("profile_id")
    disabled_config.pop("profile_version")
    disabled_path = tmp_path / "disabled.json"
    active_path = tmp_path / "active.json"
    write_json_object(disabled_path, disabled_config)
    write_json_object(active_path, active_config)

    disabled_result = admit_broadcast_readable_config(
        project_path,
        disabled_path,
        "codex-app",
        "Readable v2 비활성화",
        ADMITTED_AT,
    )
    production_config = load_json_object(
        project_path / "00_PROJECT/production_config.json"
    )
    assert disabled_result["result"] == "COMMITTED"
    assert broadcast_readable_activation_mode(
        production_config,
        {"broadcast_readable_config": disabled_config},
    ) == "DISABLED"

    active_result = admit_broadcast_readable_config(
        project_path,
        active_path,
        "codex-app",
        "Readable v2 재활성화",
        "2026-09-03T01:01:00Z",
    )
    canonical_config = load_json_object(
        project_path / "00_PROJECT/broadcast_readable_config.json"
    )
    assert active_result["result"] == "COMMITTED"
    assert broadcast_readable_activation_mode(
        production_config,
        {"broadcast_readable_config": canonical_config},
    ) == "V2_CONFIG"


def test_identical_config_admission_is_no_op(tmp_path: Path) -> None:
    """완전한 동일 Admission은 State·Revision·Change Log를 바꾸지 않는다."""
    _repository_root, project_path = copied_pilot_repository(tmp_path)
    config_path = project_path / "00_PROJECT/broadcast_readable_config.json"
    first = admit_broadcast_readable_config(
        project_path,
        config_path,
        "codex-app",
        "첫 승인",
        ADMITTED_AT,
    )
    state_path = project_path / "00_PROJECT/project_state.json"
    log_path = project_path / "00_PROJECT/change_log.jsonl"
    state_before = state_path.read_bytes()
    log_before = log_path.read_bytes()

    second = admit_broadcast_readable_config(
        project_path,
        config_path,
        "codex-app",
        "동일 승인 재실행",
        "2026-09-03T01:01:00Z",
    )

    assert first["result"] == "COMMITTED"
    assert second["result"] == "NO_OP"
    assert second["transaction_id"] is None
    assert second["admission_id"] == first["admission_id"]
    assert state_path.read_bytes() == state_before
    assert log_path.read_bytes() == log_before


def test_config_only_revision_does_not_change_novelty_index(tmp_path: Path) -> None:
    """Readable 전용 재검증은 공용 Story Novelty Index를 갱신하지 않는다."""
    repository_root, project_path = copied_pilot_repository(tmp_path)
    config_path = project_path / "00_PROJECT/broadcast_readable_config.json"
    admit_broadcast_readable_config(
        project_path,
        config_path,
        "codex-app",
        "Readable 전용 Revision",
        ADMITTED_AT,
    )
    index_path = repository_root / "STORY_LIBRARY/novelty_index.json"
    before = index_path.read_bytes()

    sync_novelty_gate(
        repository_root,
        project_path,
        "GATE-10",
        "2026-09-03T01:01:00Z",
    )
    sync_novelty_gate(
        repository_root,
        project_path,
        "GATE-13",
        "2026-09-03T01:02:00Z",
    )

    assert index_path.read_bytes() == before


def test_config_backfill_records_llm_outputs_as_validated_reuse(
    tmp_path: Path,
) -> None:
    """동일 입력·출력의 기존 LLM 결과를 새 실행으로 가장하지 않는다."""
    repository_root, project_path = copied_pilot_repository_with_runtime(tmp_path)
    config_path = project_path / "00_PROJECT/broadcast_readable_config.json"
    admit_broadcast_readable_config(
        project_path,
        config_path,
        "codex-app",
        "기존 v2 Config 공식 등록",
        ADMITTED_AT,
    )

    opened = task_open(
        repository_root,
        project_path,
        "GATE-08",
        "2026-09-03T01:01:00Z",
        None,
    )
    assert opened["gate_phase"] == "READY_TO_COMMIT"
    result = task_submit(
        repository_root,
        project_path,
        "GATE-08",
        "2026-09-03T01:02:00Z",
        None,
    )

    assert result["status"] == "COMMITTED"
    revision_traces = [
        trace
        for trace in trace_records(repository_root, project_path)
        if trace["process_revision"] == 6 and trace["gate_id"] == "GATE-08"
    ]
    reused = [
        trace
        for trace in revision_traces
        if trace.get("execution_mode") == "VALIDATED_REUSE"
    ]
    assert {trace["task_id"] for trace in reused} == {
        "script.compose_screenplay_units",
    }
    assert all(isinstance(trace.get("reused_trace_id"), str) for trace in reused)


def test_editorial_reuse_requires_self_bound_new_config_inputs(
    tmp_path: Path,
) -> None:
    """구 Editorial 결과는 신규 Config·Profile 입력을 자체 Hash로 결속해야 한다."""
    repository_root, project_path = copied_pilot_repository(tmp_path)
    graph = load_json_object(repository_root / "STANDARD/dependency_graph.json")
    prior_inputs = {"production_config": "same"}
    current_inputs = {
        "production_config": "same",
        "broadcast_readable_config": "config-file-hash",
        "broadcast_readable_output_profile": "profile-file-hash",
    }

    assert task_inputs_support_validated_reuse(
        "editorial.review",
        prior_inputs,
        current_inputs,
        project_path,
        graph,
    )

    review_path = project_path / "08_QA/editorial_review.json"
    review = load_json_object(review_path)
    artifact_hashes = review["artifact_hashes"]
    assert isinstance(artifact_hashes, dict)
    artifact_hashes["broadcast_readable_config"] = "0" * 64
    write_json_object(review_path, review)
    assert not task_inputs_support_validated_reuse(
        "editorial.review",
        prior_inputs,
        current_inputs,
        project_path,
        graph,
    )


def test_identical_blocks_follow_a_b_a_presentation_segments() -> None:
    """동일 Block 세 개도 Scene 순서가 아닌 A→B→A 표시 순서로 소비한다."""
    fixture = apply_feature_fixture("R1")
    presentation_plan = fixture["presentation_plan"]
    assert isinstance(presentation_plan, dict)
    segments = mapping_list(presentation_plan, "segments")
    narration_segment = next(
        segment for segment in segments if segment.get("segment_id") == "SEG-002"
    )
    narration_segment["segment_type"] = "DRAMA"
    narration_segment["source_artifact"] = "drama_script"
    narration_segment.pop("narrator_character_id", None)
    narration_segment.pop("narration_function", None)
    repeated_text = "같은 경고등이 두 줄로 깜박인다."
    for unit_id in ("UNIT-001", "UNIT-011", "UNIT-009", "UNIT-010"):
        unit = unit_by_id(fixture, unit_id)
        unit["type"] = "ACTION"
        if unit_id != "UNIT-010":
            unit["text"] = repeated_text
        unit.pop("speaker_id", None)
        unit.pop("delivery", None)

    rendered = render_fixture(fixture)
    report = build_report(fixture, rendered)

    assert report["result"] == "NEEDS_REVIEW"
    raw_mappings = report["unit_mappings"]
    assert isinstance(raw_mappings, list)
    mappings = {
        str(mapping["unit_id"]): mapping
        for mapping in raw_mappings
        if isinstance(mapping, dict)
        and mapping.get("unit_id") in {"UNIT-001", "UNIT-011", "UNIT-009"}
    }
    starts: list[int] = []
    for unit_id in ("UNIT-001", "UNIT-011", "UNIT-009"):
        byte_range = mappings[unit_id]["actual_byte_range"]
        assert isinstance(byte_range, dict)
        byte_start = byte_range["byte_start"]
        assert isinstance(byte_start, int)
        starts.append(byte_start)
    assert starts == sorted(starts)


def test_segment_cursor_has_direct_utf8_multiline_prefix_oracle() -> None:
    """A→B→A·Prefix 중첩·다중 행의 UTF-8 범위를 고정 정답으로 검증한다."""
    actual = "한글\n\n한글 확장\n둘째 줄\n\n한글\n"
    expected = [
        ("한글", {"byte_start": 0, "byte_end": 6}, 4),
        ("한글 확장\n둘째 줄", {"byte_start": 8, "byte_end": 32}, 16),
        ("한글", {"byte_start": 34, "byte_end": 40}, 19),
    ]
    cursor = 0
    for block, expected_range, expected_cursor in expected:
        byte_range, cursor, issues = consume_actual_block(
            actual,
            cursor,
            block,
            "ORACLE_ORDER_MISMATCH",
            {"block": block},
        )
        assert issues == []
        assert byte_range == expected_range
        assert cursor == expected_cursor
    assert cursor == len(actual)

    _byte_range, failed_cursor, issues = consume_actual_block(
        actual,
        0,
        "한글 확장",
        "ORACLE_ORDER_MISMATCH",
        {"block": "prefix-overlap"},
    )
    assert failed_cursor == 0
    assert {str(issue["code"]) for issue in issues} == {"ORACLE_ORDER_MISMATCH"}


def test_repeated_unit_turn_and_cross_layer_blocks_map_to_distinct_ranges() -> None:
    """동일 Unit·대사·Panel 발화도 Segment와 Layer별 실제 발생을 소비한다."""
    fixture = apply_feature_fixture("R1")
    action_text = "한글 *경고등*이 켜진다."
    for unit_id in ("UNIT-002", "UNIT-004", "UNIT-011"):
        unit = unit_by_id(fixture, unit_id)
        unit["type"] = "ACTION"
        unit["text"] = action_text
        unit.pop("speaker_id", None)
        unit.pop("delivery", None)

    source_dialogue = unit_by_id(fixture, "UNIT-003")
    repeated_dialogue = unit_by_id(fixture, "UNIT-013")
    for field in ("type", "text", "speaker_id", "delivery"):
        repeated_dialogue[field] = deepcopy(source_dialogue[field])

    reactions = mapping_list(fixture["reaction_segments"], "reaction_segments")
    turns = mapping_list(reactions[0], "turns")
    turns[1]["panelist_id"] = turns[0]["panelist_id"]
    turns[1]["spoken_line"] = turns[0]["spoken_line"]
    characters = mapping_list(fixture["characters"], "characters")
    panelists = mapping_list(fixture["panel_cast"], "panelists")
    dialogue_character = next(
        character
        for character in characters
        if character.get("character_id") == source_dialogue["speaker_id"]
    )
    matching_panelist = next(
        panelist
        for panelist in panelists
        if panelist.get("panelist_id") == turns[0]["panelist_id"]
    )
    matching_panelist["display_name"] = dialogue_character["name"]

    rendered = render_fixture(fixture)
    report = build_report(fixture, rendered)

    assert report["issues"] == []
    unit_mappings = report["unit_mappings"]
    panel_mappings = report["panel_turn_mappings"]
    assert isinstance(unit_mappings, list)
    assert isinstance(panel_mappings, list)
    repeated_action_mappings = [
        mapping
        for mapping in unit_mappings
        if isinstance(mapping, dict)
        and mapping.get("unit_id") in {"UNIT-002", "UNIT-004", "UNIT-011"}
    ]
    repeated_dialogue_mappings = [
        mapping
        for mapping in unit_mappings
        if isinstance(mapping, dict)
        and mapping.get("unit_id") in {"UNIT-003", "UNIT-013"}
    ]
    repeated_panel_mappings = [
        mapping
        for mapping in panel_mappings
        if isinstance(mapping, dict)
        and mapping.get("turn_id") in {"TURN-001-01", "TURN-001-02"}
    ]
    assert [
        mapping["exact_occurrence_index"]
        for mapping in repeated_action_mappings
    ] == [1, 2, 3]
    assert [
        mapping["exact_occurrence_index"]
        for mapping in repeated_dialogue_mappings
    ] == [1, 2]
    for mappings in (
        repeated_action_mappings,
        repeated_dialogue_mappings,
        repeated_panel_mappings,
    ):
        ranges = [json.dumps(mapping["actual_byte_range"], sort_keys=True) for mapping in mappings]
        assert len(ranges) == len(set(ranges))


@pytest.mark.parametrize("fixture_id", ["R1", "R2"])
def test_source_style_fixture_passes_production_presentation_semantics(
    fixture_id: str,
) -> None:
    """R1·R2가 Production과 같은 GATE-07 Presentation 의미 검증을 통과한다."""
    fixture = apply_feature_fixture(fixture_id)
    production_config = load_json_object(
        PILOT_ROOT / "00_PROJECT/production_config.json"
    )
    channel = load_json_object(
        ROOT / "CHANNELS/mystery_main/versions/2.1.0/channel_dna.json"
    )

    issues = validate_presentation_design(
        fixture["panel_cast"],
        fixture["reaction_segments"],
        fixture["presentation_plan"],
        load_json_object(PILOT_ROOT / "06_SCENE/scene_cards.json"),
        load_json_object(PILOT_ROOT / "03_TIMELINE/viewer_timeline.json"),
        load_json_object(PILOT_ROOT / "01_CASE/facts.json"),
        load_json_object(PILOT_ROOT / "04_MYSTERY/clue_matrix.json"),
        channel,
        production_config,
    )

    assert issues == []


@pytest.mark.parametrize(
    ("fixture_id", "process_revision"),
    [("R1", 91), ("R2", 92)],
)
def test_source_style_fixture_passes_real_gate_transactions(
    tmp_path: Path,
    fixture_id: str,
    process_revision: int,
) -> None:
    """R1·R2가 정상 GATE-04~09 Transaction과 의미 Validator를 통과한다."""
    repository_root, project_path = prepare_source_style_gate_project(
        tmp_path,
        fixture_id,
        process_revision,
    )
    for gate_number in range(4, 10):
        gate_id = f"GATE-{gate_number:02d}"
        result = submit_gate_until_committed(
            repository_root,
            project_path,
            gate_id,
            f"2026-09-03T03:{gate_number:02d}:00Z",
            f"2026-09-03T03:{gate_number:02d}:30Z",
        )
        assert result["status"] == "COMMITTED"

    state = load_json_object(project_path / "00_PROJECT/project_state.json")
    assert state["current_gate"] == "GATE-09"
    gate_traces = [
        trace
        for trace in trace_records(repository_root, project_path)
        if trace["process_revision"] == process_revision
    ]
    assert {trace["gate_id"] for trace in gate_traces} == {
        "GATE-04",
        "GATE-05",
        "GATE-06",
        "GATE-07",
        "GATE-08",
        "GATE-09",
    }
    assert any(
        trace["task_id"] == "script.render_broadcast_readable"
        for trace in gate_traces
    )
    assert any(
        trace["task_id"] == "continuity.validate_broadcast_readable"
        for trace in gate_traces
    )
    report = load_json_object(
        project_path / "08_QA/broadcast_readable_report.json"
    )
    assert report["issues"] == []


def test_v2_enabled_requires_manifest_when_footprint_is_disabled() -> None:
    """v2 활성 경로는 Footprint와 무관하게 GATE-13 Manifest를 요구한다."""
    fixture = apply_feature_fixture("R1")
    production_config = load_json_object(
        PILOT_ROOT / "00_PROJECT/production_config.json"
    )
    channel = load_json_object(
        ROOT / "CHANNELS/mystery_main/versions/2.1.0/channel_dna.json"
    )
    project_constraints = deepcopy(
        load_json_object(PILOT_ROOT / "00_PROJECT/project_constraints.json")
    )
    production_limits = project_constraints["production_limits"]
    assert isinstance(production_limits, dict)
    production_limits["enforce_final_footprint"] = False
    artifacts: dict[str, object] = {
        "broadcast_readable_config": fixture["config"],
        "project_constraints": project_constraints,
    }
    graph = load_json_object(ROOT / "STANDARD/dependency_graph.json")
    definitions = graph["artifacts"]
    assert isinstance(definitions, dict)
    manifest_definition = definitions["production_manifest"]
    assert isinstance(manifest_definition, dict)
    task = load_task_catalog(ROOT)["production.build_manifest"]

    assert task_condition_matches(
        task["condition"],
        production_config,
        channel,
        artifacts,
    )
    assert artifact_required_for_project(
        manifest_definition,
        channel,
        production_config,
        artifacts,
    )


@pytest.mark.parametrize(
    ("readable_mode", "footprint_enabled", "expected"),
    [
        ("v2", True, True),
        ("v2", False, True),
        ("disabled", True, True),
        ("disabled", False, False),
        ("v1", True, True),
        ("v1", False, False),
    ],
)
def test_manifest_requiredness_matrix_is_shared_by_task_and_artifact(
    readable_mode: str,
    footprint_enabled: bool,
    expected: bool,
) -> None:
    """Task Planner와 Artifact Requiredness가 같은 Manifest 선택자를 쓴다."""
    production_config = load_json_object(
        PILOT_ROOT / "00_PROJECT/production_config.json"
    )
    channel = load_json_object(
        ROOT / "CHANNELS/mystery_main/versions/2.1.0/channel_dna.json"
    )
    constraints = deepcopy(
        load_json_object(PILOT_ROOT / "00_PROJECT/project_constraints.json")
    )
    limits = constraints["production_limits"]
    assert isinstance(limits, dict)
    limits["enforce_final_footprint"] = footprint_enabled
    artifacts: dict[str, object] = {"project_constraints": constraints}
    if readable_mode == "v2":
        artifacts["broadcast_readable_config"] = pilot_fixture()["config"]
    elif readable_mode == "disabled":
        disabled = deepcopy(pilot_fixture()["config"])
        disabled["enabled"] = False
        disabled.pop("profile_id")
        disabled.pop("profile_version")
        artifacts["broadcast_readable_config"] = disabled
    elif readable_mode != "v1":
        raise AssertionError(f"알 수 없는 Readable Mode입니다: {readable_mode}")
    graph = load_json_object(ROOT / "STANDARD/dependency_graph.json")
    definitions = graph["artifacts"]
    assert isinstance(definitions, dict)
    manifest_definition = definitions["production_manifest"]
    assert isinstance(manifest_definition, dict)
    task = load_task_catalog(ROOT)["production.build_manifest"]

    assert production_manifest_required(artifacts) is expected
    assert task_condition_matches(
        task["condition"],
        production_config,
        channel,
        artifacts,
    ) is expected
    assert artifact_required_for_project(
        manifest_definition,
        channel,
        production_config,
        artifacts,
    ) is expected


def test_footprint_off_builds_deliverables_only_manifest(tmp_path: Path) -> None:
    """Footprint 파일 없이도 실제 v2 Copy 뒤 Deliverables-only Manifest를 만든다."""
    _repository_root, project_path = copied_pilot_repository(tmp_path)
    footprint_path = project_path / "06_SCENE/production_footprint.json"
    footprint_path.unlink()
    constraints_path = project_path / "00_PROJECT/project_constraints.json"
    project_constraints = load_json_object(constraints_path)
    production_limits = project_constraints["production_limits"]
    assert isinstance(production_limits, dict)
    production_limits["enforce_final_footprint"] = False
    write_json_object(constraints_path, project_constraints)
    _readable, _report, _production_copy, manifest = (
        build_footprint_off_readable_chain(project_path, project_constraints)
    )
    assert manifest["schema_version"] == "1.2.0"
    assert "source_footprint_sha256" not in manifest
    assert "scenes" not in manifest
    validate_artifact_content(
        ROOT,
        "production.build_manifest",
        "production_manifest",
        "application/json",
        manifest,
        load_artifact_contracts(ROOT)["production_manifest"],
    )


@pytest.mark.parametrize(
    ("mutation", "expected_code"),
    [
        ("missing_manifest", "PRODUCTION_READABLE_DELIVERABLE_MISSING"),
        ("missing_entry", "PRODUCTION_READABLE_DELIVERABLE_MISSING"),
        ("duplicate_entry", "PRODUCTION_READABLE_DELIVERABLE_MISSING"),
        ("path_escape", "PRODUCTION_READABLE_DELIVERABLE_STALE"),
        ("copy_changed", "PRODUCTION_READABLE_DELIVERABLE_STALE"),
        ("canonical_changed", "PRODUCTION_BROADCAST_READABLE_COPY_MISMATCH"),
        ("report_changed", "PRODUCTION_READABLE_DELIVERABLE_STALE"),
        ("profile_changed", "PRODUCTION_READABLE_DELIVERABLE_STALE"),
    ],
)
def test_footprint_off_manifest_mutations_are_rejected(
    tmp_path: Path,
    mutation: str,
    expected_code: str,
) -> None:
    """Footprint-off Manifest의 누락·중복·Path·Byte·Binding Drift를 거부한다."""
    _repository_root, project_path = copied_pilot_repository(tmp_path)
    footprint_path = project_path / "06_SCENE/production_footprint.json"
    footprint_path.unlink()
    constraints = load_json_object(
        project_path / "00_PROJECT/project_constraints.json"
    )
    limits = constraints["production_limits"]
    assert isinstance(limits, dict)
    limits["enforce_final_footprint"] = False
    readable, report, production_copy, manifest = build_footprint_off_readable_chain(
        project_path,
        constraints,
    )
    candidate_manifest: dict[str, object] | None = deepcopy(manifest)
    candidate_readable = readable
    candidate_copy = production_copy
    report_hash = document_sha256(report)
    profile_version = "2.0.0"
    deliverables = manifest["deliverables"]
    assert isinstance(deliverables, list)
    if mutation == "missing_manifest":
        candidate_manifest = None
    elif mutation == "missing_entry":
        assert candidate_manifest is not None
        candidate_manifest["deliverables"] = []
    elif mutation == "duplicate_entry":
        assert candidate_manifest is not None
        candidate_manifest["deliverables"] = [
            deepcopy(deliverables[0]),
            deepcopy(deliverables[0]),
        ]
    elif mutation == "path_escape":
        assert candidate_manifest is not None
        candidate_deliverables = candidate_manifest["deliverables"]
        assert isinstance(candidate_deliverables, list)
        candidate_entry = candidate_deliverables[0]
        assert isinstance(candidate_entry, dict)
        candidate_entry["path"] = "../../outside.md"
    elif mutation == "copy_changed":
        candidate_copy = f"{production_copy}변조"
    elif mutation == "canonical_changed":
        candidate_readable = f"{readable}변조"
    elif mutation == "report_changed":
        report_hash = "0" * 64
    elif mutation == "profile_changed":
        profile_version = "2.0.1"
    else:
        raise AssertionError(f"알 수 없는 Manifest Mutation입니다: {mutation}")

    issues = production_readable_deliverable_issues(
        candidate_manifest,
        candidate_readable,
        candidate_copy,
        report_hash,
        "BROADCAST_READABLE_SCRIPT",
        profile_version,
    )

    assert expected_code in issue_codes(issues)


def test_full_runtime_reaches_gate_13_without_footprint_file(tmp_path: Path) -> None:
    """v2+Footprint-off Project가 실제 GATE-00~13 Transaction을 완주한다."""
    repository_root = create_runtime_repository(tmp_path)
    project_path = create_runtime_project(repository_root, "PRJ-918")
    constraints_path = project_path / "00_PROJECT/project_constraints.json"
    constraints = load_json_object(constraints_path)
    limits = constraints["production_limits"]
    assert isinstance(limits, dict)
    limits["enforce_final_footprint"] = False
    write_json_object(constraints_path, constraints)
    footprint_path = project_path / "06_SCENE/production_footprint.json"
    footprint_path.unlink(missing_ok=True)
    first_result = asyncio.run(
        execute_run(
            repository_root,
            project_path,
            "GATE-00",
            "GATE-07",
            "default",
            None,
            None,
        )
    )
    assert first_result["status"] == "COMPLETED"
    config = deepcopy(pilot_fixture()["config"])
    config["project_id"] = "PRJ-918"
    input_path = tmp_path / "PRJ-918-readable-config.json"
    write_json_object(input_path, config)
    admit_broadcast_readable_config(
        project_path,
        input_path,
        "runtime-test",
        "Footprint-off 전체 경로 활성화",
        utc_now(),
    )
    opened = task_open(
        repository_root,
        project_path,
        "GATE-08",
        utc_now(),
        None,
    )
    assert opened["gate_phase"] == "AWAITING_LLM"
    workspace = Path(str(opened["workspace"]))
    screenplay_path = workspace / "07_SCRIPT/screenplay_units.json"
    write_json_object(
        screenplay_path,
        fake_screenplay_candidate(project_path, "PRJ-918"),
    )
    presentation = load_json_object(
        workspace / "06_SCENE/presentation_plan.json"
    )
    screenplay = load_json_object(screenplay_path)
    planned_by_scene: dict[str, list[str]] = {}
    for segment in mapping_list(presentation, "segments"):
        scene_id = segment["scene_id"]
        segment_id = segment["segment_id"]
        assert isinstance(scene_id, str)
        assert isinstance(segment_id, str)
        planned_by_scene.setdefault(scene_id, []).append(segment_id)
    for scene in mapping_list(screenplay, "scenes"):
        scene_id = scene["scene_id"]
        assert isinstance(scene_id, str)
        scene["segment_ids"] = planned_by_scene[scene_id]
    write_json_object(screenplay_path, screenplay)
    gate_eight = task_submit(
        repository_root,
        project_path,
        "GATE-08",
        utc_now(),
        None,
    )
    assert gate_eight["status"] == "COMMITTED"
    for gate_id in ("GATE-09", "GATE-10", "GATE-11", "GATE-12"):
        opened = task_open(
            repository_root,
            project_path,
            gate_id,
            utc_now(),
            None,
        )
        assert opened["gate_phase"] == "READY_TO_COMMIT"
        submitted = task_submit(
            repository_root,
            project_path,
            gate_id,
            utc_now(),
            None,
        )
        assert submitted["status"] == "COMMITTED"

    result = asyncio.run(
        execute_run(
            repository_root,
            project_path,
            "GATE-13",
            "GATE-13",
            "default",
            None,
            None,
        )
    )

    assert result["status"] == "COMPLETED"
    assert not footprint_path.exists()
    manifest = load_json_object(
        project_path / "09_PRODUCTION/production_manifest.json"
    )
    assert manifest["schema_version"] == "1.2.0"
    state = load_json_object(project_path / "00_PROJECT/project_state.json")
    assert state["current_gate"] == "GATE-13"
    assert state["state"] == "EDITORIAL_REVIEW_REQUIRED"
    audit = audit_project(
        repository_root,
        project_path,
        None,
        None,
        "2026-09-03T02:00:00Z",
    )
    assert audit["result"] == "PASS"
