"""Broadcast Readable v2 BR-15~BR-18 폐쇄 조건을 검증한다."""

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
from test_broadcast_readable_v2_source_fixtures import (
    SourceFixture,
    apply_feature_fixture,
    assert_panel_reveal_scope,
    fixture_metadata,
    render_fixture_machine_master,
)
from test_broadcast_readable_v2_validation import (
    PilotFixture,
    build_report,
    mapping_records,
    pilot_fixture,
    render_fixture,
)

import VALIDATORS.gate_transaction as gate_transaction_module
from RUNTIME.contracts import load_artifact_contracts, load_task_catalog
from RUNTIME.errors import RuntimeExecutionError
from RUNTIME.event_store import utc_now
from RUNTIME.models import GenerationOptions, LLMMessage, LLMRequest, OutputContract
from RUNTIME.output_gateway import validate_artifact_content
from RUNTIME.planner import task_condition_matches
from RUNTIME.providers.fake import (
    fake_edit_script_from_presentation_plan,
    fake_editorial_review,
    fake_screenplay_units,
)
from RUNTIME.transactions import (
    acquire_project_lock,
    commit_gate_transaction,
    release_project_lock,
    write_artifact,
)
from VALIDATORS.broadcast_readable import production_readable_deliverable_issues
from VALIDATORS.broadcast_readable_v2 import (
    block_occurrence_ranges,
    consume_actual_block,
    independent_conformance,
)
from VALIDATORS.candidate_evaluation import (
    candidate_evaluation_input_hashes,
    document_sha256,
)
from VALIDATORS.config_admission import (
    admit_broadcast_readable_config,
    broadcast_readable_config_admission_issues,
)
from VALIDATORS.dependency import (
    artifact_hash,
    artifact_required_for_project,
    invalidate_artifact_dependents,
)
from VALIDATORS.exceptions import ConfigurationError, GateTransactionError
from VALIDATORS.gate_transaction import (
    audit_project,
    return_task_to_owner,
    revision_trigger_allows_validated_reuse,
    task_inputs_support_validated_reuse,
    task_open,
    task_submit,
    trace_records,
)
from VALIDATORS.io import load_json_object, write_json_object
from VALIDATORS.library_store import sync_novelty_gate
from VALIDATORS.models import ProjectState
from VALIDATORS.output_profiles import broadcast_readable_activation_mode
from VALIDATORS.pipeline import load_existing_project_artifacts
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
    return {str(issue["code"]) for issue in issues if isinstance(issue.get("code"), str)}


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
    """과거 실행 근거를 명시적으로 구성한 격리 Pilot Repository를 만든다."""
    repository_root, project_path = copied_pilot_repository(tmp_path)
    prior_trace = next(
        trace
        for trace in trace_records(repository_root, project_path)
        if trace.get("process_revision") == 5
        and trace.get("gate_id") == "GATE-08"
        and trace.get("task_id") == "script.compose_screenplay_units"
    )
    task_id = "script.compose_screenplay_units"
    task = load_task_catalog(repository_root)[task_id]
    graph = load_json_object(repository_root / "STANDARD/dependency_graph.json")
    definitions = graph["artifacts"]
    assert isinstance(definitions, dict)
    prior_workspace = (
        project_path / ".runtime/reuse_fixture/gates/GATE-08/semantic-attempt-001/staged_project"
    )
    for artifact_name in task["writes"]:
        definition = definitions[artifact_name]
        assert isinstance(definition, dict)
        relative_path = definition["path"]
        assert isinstance(relative_path, str)
        output_path = prior_workspace / relative_path
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_bytes((project_path / relative_path).read_bytes())

    transaction_id = "CODEX-TASK-0000000000000001"
    prior_inputs = prior_trace["input_hashes"]
    assert isinstance(prior_inputs, dict)
    prior_commit_sha = prior_trace["commit_sha"]
    assert isinstance(prior_commit_sha, str)
    write_json_object(
        project_path / f".runtime/codex_tasks/{transaction_id}/task.json",
        {
            "schema_family": "gate-transaction",
            "schema_version": "1.0.0",
            "transaction_id": transaction_id,
            "project_id": "PRJ-006",
            "gate_id": "GATE-08",
            "process_revision": 5,
            "task_ids": [task_id],
            "completed_task_ids": [task_id],
            "task_input_hashes": {task_id: prior_inputs},
            "agent_ids": ["script_writer"],
            "allowed_reads": [],
            "allowed_writes": [],
            "input_hashes": prior_inputs,
            "canonical_hashes": {},
            "workspace_hashes": {},
            "forbidden_paths": [],
            "workspace": str(prior_workspace.relative_to(repository_root)),
            "status": "COMMITTED",
            "changed_paths": [],
            "commit_sha": prior_commit_sha,
            "started_at": "2026-09-02T16:40:53Z",
            "completed_at": "2026-09-02T16:43:01Z",
        },
    )
    return repository_root, project_path


def copied_committed_pilot_repository(tmp_path: Path) -> tuple[Path, Path]:
    """최종 Commit 상태와 실행 이력을 보존한 격리 Pilot Repository를 만든다."""
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
    return repository_root, project_path


def install_gate_seven_reuse_record(
    repository_root: Path,
    project_path: Path,
) -> None:
    """Gate 7 선행 Task의 과거 실제 실행 근거를 격리 Repository에 구성한다."""
    gate_id = "GATE-07"
    process_revision = 4
    task_ids = ("scene.design", "story.design_state_transitions")
    traces = trace_records(repository_root, project_path)
    prior_traces: dict[str, Mapping[str, object]] = {}
    for task_id in task_ids:
        matching_traces = [
            trace
            for trace in traces
            if trace.get("process_revision") == process_revision
            and trace.get("gate_id") == gate_id
            and trace.get("task_id") == task_id
            and trace.get("execution_mode") != "VALIDATED_REUSE"
        ]
        assert len(matching_traces) == 1
        prior_traces[task_id] = matching_traces[0]

    commit_shas = {trace.get("commit_sha") for trace in prior_traces.values()}
    assert len(commit_shas) == 1
    prior_commit_sha = next(iter(commit_shas))
    assert isinstance(prior_commit_sha, str)

    tasks = load_task_catalog(repository_root)
    graph = load_json_object(repository_root / "STANDARD/dependency_graph.json")
    definitions = graph["artifacts"]
    assert isinstance(definitions, dict)
    transaction_id = "CODEX-TASK-0000000000000007"
    prior_workspace = (
        project_path / f".runtime/reuse_fixture/gates/{gate_id}/semantic-attempt-001/staged_project"
    )
    for task_id in task_ids:
        for artifact_name in tasks[task_id]["writes"]:
            definition = definitions[artifact_name]
            assert isinstance(definition, dict)
            relative_path = definition["path"]
            assert isinstance(relative_path, str)
            output_path = prior_workspace / relative_path
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_bytes((project_path / relative_path).read_bytes())

    task_input_hashes: dict[str, dict[str, object]] = {}
    for task_id, trace in prior_traces.items():
        input_hashes = trace.get("input_hashes")
        assert isinstance(input_hashes, dict)
        task_input_hashes[task_id] = input_hashes
    write_json_object(
        project_path / f".runtime/codex_tasks/{transaction_id}/task.json",
        {
            "schema_family": "gate-transaction",
            "schema_version": "1.0.0",
            "transaction_id": transaction_id,
            "project_id": "PRJ-006",
            "gate_id": gate_id,
            "process_revision": process_revision,
            "task_ids": list(task_ids),
            "completed_task_ids": list(task_ids),
            "task_input_hashes": task_input_hashes,
            "agent_ids": [str(tasks[task_id]["agent_id"]) for task_id in task_ids],
            "allowed_reads": [],
            "allowed_writes": [],
            "input_hashes": {},
            "canonical_hashes": {},
            "workspace_hashes": {},
            "forbidden_paths": [],
            "workspace": str(prior_workspace.relative_to(repository_root)),
            "status": "COMMITTED",
            "changed_paths": [],
            "commit_sha": prior_commit_sha,
            "started_at": "2026-09-02T13:31:17Z",
            "completed_at": "2026-09-02T13:31:43Z",
        },
    )


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


def assert_task_input_hashes_match_canonical(
    repository_root: Path,
    project_path: Path,
    traces: Sequence[Mapping[str, object]],
    task_id: str,
    artifact_names: Sequence[str],
) -> None:
    """Task Trace의 입력 Hash가 같은 Project의 Canonical Byte와 일치하는지 검사한다."""
    matches = [trace for trace in traces if trace.get("task_id") == task_id]
    assert len(matches) == 1, task_id
    input_hashes = matches[0].get("input_hashes")
    assert isinstance(input_hashes, Mapping)
    graph = load_json_object(repository_root / "STANDARD/dependency_graph.json")
    definitions = graph["artifacts"]
    assert isinstance(definitions, dict)
    for artifact_name in artifact_names:
        definition = definitions[artifact_name]
        assert isinstance(definition, dict)
        relative_path = definition["path"]
        assert isinstance(relative_path, str)
        expected_hash = artifact_hash((project_path / relative_path).read_bytes())
        assert input_hashes.get(artifact_name) == expected_hash, (
            task_id,
            artifact_name,
        )


def assert_fixture_gate_hash_chain(
    repository_root: Path,
    project_path: Path,
    traces: Sequence[Mapping[str, object]],
) -> None:
    """GATE-04~09의 Source→파생 Artifact Hash 결속을 Task Trace로 검사한다."""
    expectations = {
        "character.design": ("facts",),
        "story.bind_crime_event": ("facts", "characters", "relationships"),
        "mystery.design": ("facts", "crime_event_contract"),
        "scene.design": ("actual_timeline", "viewer_timeline", "clue_matrix"),
        "scene.design_reactions": (
            "scene_cards",
            "viewer_timeline",
            "clue_matrix",
        ),
        "script.compose_screenplay_units": (
            "crime_event_contract",
            "scene_cards",
            "presentation_plan",
        ),
        "script.render_screenplay_layers": (
            "screenplay_units",
            "facts",
            "crime_event_contract",
        ),
        "continuity.validate_broadcast_readable": (
            "screenplay_units",
            "final_script",
            "broadcast_readable_script",
        ),
    }
    for task_id, artifact_names in expectations.items():
        assert_task_input_hashes_match_canonical(
            repository_root,
            project_path,
            traces,
            task_id,
            artifact_names,
        )


def project_canonical_bytes(project_path: Path) -> dict[str, bytes]:
    """Runtime 운영 경로를 제외한 Project 전체 Byte Snapshot을 반환한다."""
    return {
        path.relative_to(project_path).as_posix(): path.read_bytes()
        for path in sorted(project_path.rglob("*"))
        if path.is_file() and ".runtime" not in path.relative_to(project_path).parts
    }


def write_process_trace_records(
    project_path: Path,
    records: Sequence[Mapping[str, object]],
) -> None:
    """Process Trace 객체 배열을 정규 JSONL Byte로 기록한다."""
    content = "".join(
        json.dumps(dict(record), ensure_ascii=False, sort_keys=True) + "\n" for record in records
    )
    (project_path / "00_PROJECT/process_trace.jsonl").write_text(
        content,
        encoding="utf-8",
    )


def screenplay_source_trace_index(records: Sequence[Mapping[str, object]]) -> int:
    """Config 재사용 Fixture의 실제 Screenplay 실행 Trace 위치를 반환한다."""
    matches = [
        index
        for index, trace in enumerate(records)
        if trace.get("process_revision") == 5
        and trace.get("gate_id") == "GATE-08"
        and trace.get("task_id") == "script.compose_screenplay_units"
        and trace.get("execution_mode") != "VALIDATED_REUSE"
    ]
    assert len(matches) == 1
    return matches[0]


def open_config_reuse_candidate(
    repository_root: Path,
    project_path: Path,
    opened_at: str,
) -> dict[str, object]:
    """공식 Config Admission 뒤 GATE-08 재사용 후보 Task를 연다."""
    admit_broadcast_readable_config(
        project_path,
        project_path / "00_PROJECT/broadcast_readable_config.json",
        "codex-app",
        "재사용 Trace 결속 검증",
        ADMITTED_AT,
    )
    return task_open(
        repository_root,
        project_path,
        "GATE-08",
        opened_at,
        None,
    )


def render_pilot_fixture_machine_master(fixture: PilotFixture) -> str:
    """PRJ-006 계약을 사용해 수정된 Mapping Fixture의 Machine Master를 만든다."""
    overlay: dict[str, object] = dict(fixture)
    overlay.update(
        project_task_outputs(
            "script.render_screenplay_layers",
            PILOT_ROOT,
            overlay,
        )
    )
    overlay.update(
        project_task_outputs(
            "script.render_broadcast_master",
            PILOT_ROOT,
            overlay,
        )
    )
    final_script = overlay["final_script"]
    assert isinstance(final_script, str)
    return final_script


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


def install_gate_fixture(
    repository_root: Path,
    project_path: Path,
    source_fixture: PilotFixture,
) -> set[str]:
    """명시적 Source와 결정론적 GATE-08 파생 후보를 Canonical에 배치한다."""
    fixture = deepcopy(source_fixture)
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


def prepare_gate_project(
    tmp_path: Path,
    fixture: PilotFixture,
    process_revision: int,
    admission_reason: str,
) -> tuple[Path, Path]:
    """명시적 Fixture를 미검증 DIRTY Source로 둔 GATE-04 직전 Project를 만든다."""
    repository_root, project_path = copied_pilot_repository(tmp_path)
    installed = install_gate_fixture(
        repository_root,
        project_path,
        fixture,
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
        admission_reason,
        "2026-09-03T03:01:00Z",
    )
    return repository_root, project_path


def prepare_source_style_gate_project(
    tmp_path: Path,
    fixture_id: str,
) -> tuple[Path, Path]:
    """R1·R2 자체 Source로 정상 GATE-00~03을 통과한 Project를 만든다."""
    fixture = apply_feature_fixture(fixture_id)
    project_id = fixture["project_manifest"]["project_id"]
    assert isinstance(project_id, str)
    repository_root = create_runtime_repository(tmp_path)
    project_path = create_runtime_project(repository_root, project_id)
    fixture_documents: Mapping[str, object] = fixture
    for artifact_name in (
        "project_manifest",
        "production_config",
        "project_constraints",
    ):
        write_json_object(
            project_path / f"00_PROJECT/{artifact_name}.json",
            cast(dict[str, object], fixture_documents[artifact_name]),
        )
    for gate_number in range(4):
        gate_id = f"GATE-{gate_number:02d}"
        result = submit_fixture_gate_until_committed(
            repository_root,
            project_path,
            fixture,
            gate_id,
            f"2026-09-03T02:{gate_number:02d}:00Z",
            f"2026-09-03T02:{gate_number:02d}:30Z",
        )
        assert result["status"] == "COMMITTED"
    assert document_sha256(
        load_json_object(project_path / "01_CASE/facts.json")
    ) == document_sha256(fixture["facts"])
    predecessor_paths = {
        "variation_candidates": "00_PROJECT/variation_candidates.json",
        "candidate_event_briefs": "00_PROJECT/candidate_event_briefs.json",
        "story_dna": "00_PROJECT/story_dna.json",
        "case_input": "01_CASE/case_input.json",
    }
    expected_hashes = fixture_metadata(fixture_id)["expected_artifact_sha256"]
    for artifact_name, relative_path in predecessor_paths.items():
        assert (
            document_sha256(load_json_object(project_path / relative_path))
            == (expected_hashes[artifact_name])
        )
    write_artifact(
        project_path / "00_PROJECT/broadcast_readable_config.json",
        fixture["config"],
    )
    admission = admit_broadcast_readable_config(
        project_path,
        project_path / "00_PROJECT/broadcast_readable_config.json",
        "fixture-builder",
        f"{fixture_id} Config 승인",
        utc_now(),
    )
    assert admission["result"] == "COMMITTED"
    return repository_root, project_path


def fixture_production_package_outputs(
    fixture: SourceFixture,
) -> dict[str, str]:
    """R1 Footprint-off 인계 문서를 자체 사건 Source로 생성한다."""
    presentation_plan = fixture["presentation_plan"]
    reactions = mapping_list(fixture["reaction_segments"], "reaction_segments")
    reaction_cues = "\n".join(
        f"{reaction['reaction_segment_id']} 패널 촬영 Cue" for reaction in reactions
    )
    title = fixture["case_input"]["title_working"]
    assert isinstance(title, str)
    return {
        "shooting_script": f"# {title} 촬영 대본\n\nSCN-01과 SCN-02의 비선정적 사건 재구성 Cue",
        "narration": render_fixture_machine_master(fixture),
        "production_panel_reaction_script": reaction_cues,
        "subtitle_script": f"00:00 본 이야기는 창작입니다. {title}",
        "edit_script": fake_edit_script_from_presentation_plan(presentation_plan),
    }


def fixture_task_outputs(
    repository_root: Path,
    workspace: Path,
    fixture: SourceFixture,
    task_id: str,
) -> dict[str, object]:
    """현재 Test Task에 필요한 정식 Output Contract 문서만 반환한다."""
    fixture_documents: Mapping[str, object] = fixture
    artifacts = load_existing_project_artifacts(
        workspace,
        load_json_object(repository_root / "STANDARD/dependency_graph.json"),
    )
    outputs: dict[str, object] = {}
    for artifact_name, document in fixture_documents.items():
        if isinstance(document, Mapping):
            outputs[artifact_name] = deepcopy(document)
    outputs.update(fixture_production_package_outputs(fixture))
    if task_id == "variation.evaluate":
        candidate_evaluation = deepcopy(fixture["candidate_evaluation"])
        novelty_precheck = cast(Mapping[str, object], artifacts["novelty_precheck"])
        candidate_evaluation["input_hashes"] = candidate_evaluation_input_hashes(
            cast(Mapping[str, object], artifacts["variation_candidates"]),
            cast(Mapping[str, object], artifacts["candidate_event_briefs"]),
            novelty_precheck,
            cast(Mapping[str, object], artifacts["candidate_eligibility"]),
        )
        candidate_evaluation["novelty_report_hash"] = document_sha256(novelty_precheck)
        outputs["candidate_evaluation"] = candidate_evaluation
    if task_id == "editorial.review":
        project_id = fixture["project_manifest"]["project_id"]
        assert isinstance(project_id, str)
        outputs["editorial_review"] = fake_editorial_review(project_id, artifacts)
    return outputs


def write_fixture_task_outputs(
    repository_root: Path,
    record: Mapping[str, object],
    fixture: SourceFixture,
) -> None:
    """현재 Transaction의 allowed_writes만 격리 Workspace에 기록한다."""
    raw_workspace = record.get("workspace")
    raw_allowed_writes = record.get("allowed_writes")
    task_id = record.get("current_task_id")
    if (
        not isinstance(raw_workspace, str)
        or not isinstance(raw_allowed_writes, list)
        or not isinstance(task_id, str)
    ):
        raise AssertionError("Fixture Task에 Workspace, Task ID 또는 allowed_writes가 없습니다.")
    workspace = Path(raw_workspace)
    graph = load_json_object(repository_root / "STANDARD/dependency_graph.json")
    definitions = graph["artifacts"]
    assert isinstance(definitions, dict)
    outputs = fixture_task_outputs(repository_root, workspace, fixture, task_id)
    if task_id == "scene.design_reactions":
        assert_panel_reveal_scope(fixture)
    for artifact_name in raw_allowed_writes:
        assert isinstance(artifact_name, str)
        if artifact_name not in outputs:
            raise AssertionError(f"Fixture Task Output이 없습니다: {artifact_name}")
        definition = definitions[artifact_name]
        assert isinstance(definition, dict)
        relative_path = definition["path"]
        assert isinstance(relative_path, str)
        write_artifact(workspace / relative_path, outputs[artifact_name])


def submit_fixture_gate_until_committed(
    repository_root: Path,
    project_path: Path,
    fixture: SourceFixture,
    gate_id: str,
    started_at: str,
    completed_at: str,
) -> dict[str, object]:
    """Fixture Adapter와 Production CORE를 순서대로 실행해 Gate를 Commit한다."""
    result = task_open(
        repository_root,
        project_path,
        gate_id,
        started_at,
        None,
    )
    for _attempt in range(16):
        if result.get("status") == "COMMITTED":
            return result
        if result.get("gate_phase") == "AWAITING_LLM":
            write_fixture_task_outputs(repository_root, result, fixture)
        result = task_submit(
            repository_root,
            project_path,
            gate_id,
            completed_at,
            None,
        )
    raise AssertionError(f"Fixture Gate Transaction이 완료되지 않았습니다: {gate_id}")


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
    process_issues = [issue for issue in raw_process_issues if isinstance(issue, dict)]
    assert "CANONICAL_ARTIFACT_DRIFT" in issue_codes(process_issues)


def test_audit_fails_closed_when_config_admission_commits_mid_snapshot(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Audit 도중 Admission Commit이 발생하면 혼합 Revision PASS를 거부한다."""
    repository_root, project_path = copied_committed_pilot_repository(tmp_path)
    disabled_config_path = tmp_path / "disabled-readable-config.json"
    write_json_object(
        disabled_config_path,
        {
            "$schema": ("../../../STANDARD/schemas/broadcast_readable_config.schema.json"),
            "schema_family": "broadcast-readable-config",
            "schema_version": "1.0.0",
            "project_id": "PRJ-006",
            "enabled": False,
        },
    )
    original_validation = gate_transaction_module.full_validation_report
    admission_committed = False
    committed_snapshot: dict[str, bytes] | None = None

    def commit_during_validation(
        current_repository_root: Path,
        current_project_path: Path,
        reference_source: Path | None,
        channel_path: Path | None,
    ) -> object:
        """검증 중 한 번만 공식 Config Admission을 Commit한다."""
        nonlocal admission_committed, committed_snapshot
        if not admission_committed:
            admit_broadcast_readable_config(
                current_project_path,
                disabled_config_path,
                "concurrency-test",
                "Audit Snapshot 중 Config 변경",
                "2026-09-03T05:00:00Z",
            )
            admission_committed = True
            committed_snapshot = project_canonical_bytes(current_project_path)
        return original_validation(
            current_repository_root,
            current_project_path,
            reference_source,
            channel_path,
        )

    monkeypatch.setattr(
        gate_transaction_module,
        "full_validation_report",
        commit_during_validation,
    )
    report = audit_project(
        repository_root,
        project_path,
        None,
        None,
        "2026-09-03T05:01:00Z",
    )

    assert admission_committed is True
    assert committed_snapshot is not None
    assert project_canonical_bytes(project_path) == committed_snapshot
    assert report["result"] == "FAIL"
    assert report["state_unchanged"] is False
    assert report["snapshot_consistent"] is False
    raw_issues = report["process_issues"]
    assert isinstance(raw_issues, list)
    assert any(
        issue.get("code") == "AUDIT_SNAPSHOT_CHANGED"
        for issue in raw_issues
        if isinstance(issue, dict)
    )


def test_audit_fails_closed_when_gate_commits_mid_snapshot(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Audit 도중 Gate Commit이 발생하면 시작 Revision의 PASS를 허용하지 않는다."""
    repository_root, project_path = copied_committed_pilot_repository(tmp_path)
    return_task_to_owner(
        repository_root,
        project_path,
        "script_writer",
        "concurrency-test",
        "Gate Commit Snapshot 경계 검증",
        "2026-09-03T05:02:00Z",
    )
    opened = task_open(
        repository_root,
        project_path,
        "GATE-08",
        "2026-09-03T05:03:00Z",
        None,
    )
    assert opened["gate_phase"] == "AWAITING_LLM"
    original_validation = gate_transaction_module.full_validation_report
    gate_committed = False
    committed_snapshot: dict[str, bytes] | None = None

    def commit_during_validation(
        current_repository_root: Path,
        current_project_path: Path,
        reference_source: Path | None,
        channel_path: Path | None,
    ) -> object:
        """검증 중 열린 Gate를 한 번만 공식 Transaction으로 Commit한다."""
        nonlocal gate_committed, committed_snapshot
        if not gate_committed:
            submit_gate_until_committed(
                current_repository_root,
                current_project_path,
                "GATE-08",
                "2026-09-03T05:03:00Z",
                "2026-09-03T05:04:00Z",
            )
            gate_committed = True
            committed_snapshot = project_canonical_bytes(current_project_path)
        return original_validation(
            current_repository_root,
            current_project_path,
            reference_source,
            channel_path,
        )

    monkeypatch.setattr(
        gate_transaction_module,
        "full_validation_report",
        commit_during_validation,
    )
    report = audit_project(
        repository_root,
        project_path,
        None,
        None,
        "2026-09-03T05:05:00Z",
    )

    assert gate_committed is True
    assert committed_snapshot is not None
    assert project_canonical_bytes(project_path) == committed_snapshot
    assert report["result"] == "FAIL"
    assert report["state_unchanged"] is False
    assert report["snapshot_consistent"] is False
    raw_issues = report["process_issues"]
    assert isinstance(raw_issues, list)
    assert any(
        issue.get("code") == "AUDIT_SNAPSHOT_CHANGED"
        for issue in raw_issues
        if isinstance(issue, dict)
    )


def test_stable_audit_measures_equal_snapshot_without_writing_canonical_bytes(
    tmp_path: Path,
) -> None:
    """변동 없는 Audit는 동일 Token을 측정하고 Canonical Byte를 쓰지 않는다."""
    repository_root, project_path = copied_committed_pilot_repository(tmp_path)
    before = project_canonical_bytes(project_path)

    report = audit_project(
        repository_root,
        project_path,
        None,
        None,
        "2026-09-03T05:06:00Z",
    )

    assert report["result"] == "PASS"
    assert report["snapshot_start_token"] == report["snapshot_end_token"]
    assert report["state_unchanged"] is True
    assert report["snapshot_consistent"] is True
    assert project_canonical_bytes(project_path) == before


def test_never_admitted_optional_config_can_remain_absent(tmp_path: Path) -> None:
    """Admission 이력과 CLEAN State가 없으면 Config 부재를 비활성 경로로 본다."""
    repository_root, project_path = copied_pilot_repository(tmp_path)
    (project_path / "00_PROJECT/broadcast_readable_config.json").unlink()
    state = cast(
        ProjectState,
        load_json_object(project_path / "00_PROJECT/project_state.json"),
    )

    issues = broadcast_readable_config_admission_issues(
        repository_root,
        project_path,
        state,
    )

    assert issues == []


def test_clean_config_state_rejects_deleted_canonical_file(tmp_path: Path) -> None:
    """CLEAN State가 가리키는 Config 파일 삭제는 Canonical Drift다."""
    repository_root, project_path = copied_pilot_repository(tmp_path)
    config_path = project_path / "00_PROJECT/broadcast_readable_config.json"
    config_hash = artifact_hash(config_path.read_bytes())
    config_path.unlink()
    state_path = project_path / "00_PROJECT/project_state.json"
    state = cast(ProjectState, load_json_object(state_path))
    state["artifacts"]["broadcast_readable_config"] = {
        "status": "CLEAN",
        "content_hash": config_hash,
        "invalidated_by": [],
    }

    issues = broadcast_readable_config_admission_issues(
        repository_root,
        project_path,
        state,
    )

    assert any(issue.get("reason") == "CANONICAL_FILE_MISSING" for issue in issues)


def test_disabled_admission_still_rejects_deleted_config_file(tmp_path: Path) -> None:
    """enabled=false도 공식 Config 파일 삭제로 비활성화할 수 없다."""
    repository_root, project_path = copied_pilot_repository(tmp_path)
    disabled_config_path = tmp_path / "disabled-config.json"
    write_json_object(
        disabled_config_path,
        {
            "schema_family": "broadcast-readable-config",
            "schema_version": "1.0.0",
            "project_id": "PRJ-006",
            "enabled": False,
        },
    )
    admit_broadcast_readable_config(
        project_path,
        disabled_config_path,
        "config-test",
        "Readable 기능을 공식적으로 비활성화",
        "2026-09-03T05:07:00Z",
    )
    canonical_path = project_path / "00_PROJECT/broadcast_readable_config.json"
    canonical_path.unlink()
    state = cast(
        ProjectState,
        load_json_object(project_path / "00_PROJECT/project_state.json"),
    )
    state["artifacts"]["broadcast_readable_config"] = {
        "status": "MISSING",
        "content_hash": None,
        "invalidated_by": [],
    }

    issues = broadcast_readable_config_admission_issues(
        repository_root,
        project_path,
        state,
    )

    assert any(issue.get("reason") == "CONFIG_FILE_MISSING_AFTER_ADMISSION" for issue in issues)


@pytest.mark.parametrize("state_entry_mode", ["missing", "absent"])
def test_deleted_config_after_successful_admission_is_drift(
    tmp_path: Path,
    state_entry_mode: str,
) -> None:
    """성공 Admission 이력 뒤 Config와 State 결속이 사라지면 실패한다."""
    repository_root, project_path = copied_committed_pilot_repository(tmp_path)
    config_path = project_path / "00_PROJECT/broadcast_readable_config.json"
    config_path.unlink()
    state_path = project_path / "00_PROJECT/project_state.json"
    state = load_json_object(state_path)
    artifacts = state["artifacts"]
    assert isinstance(artifacts, dict)
    if state_entry_mode == "missing":
        config_state = artifacts["broadcast_readable_config"]
        assert isinstance(config_state, dict)
        config_state.update({"status": "MISSING", "content_hash": None, "invalidated_by": []})
    else:
        artifacts.pop("broadcast_readable_config")
    write_json_object(state_path, state)

    issues = broadcast_readable_config_admission_issues(
        repository_root,
        project_path,
        cast(ProjectState, state),
    )

    assert any(issue.get("reason") == "CONFIG_FILE_MISSING_AFTER_ADMISSION" for issue in issues)


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
    revision_trigger = state_after["revision_trigger"]
    assert isinstance(revision_trigger, dict)
    assert revision_trigger == {
        "type": "CONFIG_ADMISSION",
        "source_id": result["admission_id"],
        "target_owner_agent": None,
        "target_gate": None,
        "target_task_ids": [],
        "actor": "codex-app",
        "reason": "기존 v2 Config를 공식 경로로 등록",
        "triggered_at": ADMITTED_AT,
    }
    for artifact_name, artifact_state in artifacts_after.items():
        assert isinstance(artifact_state, dict)
        if artifact_name in READABLE_INVALIDATION:
            assert artifact_state["status"] == "DIRTY"
            assert artifact_state["invalidated_by"] == ["broadcast_readable_config"]
        elif artifact_name != "broadcast_readable_config":
            assert artifact_state == artifacts_before[artifact_name]
    typed_state = cast(ProjectState, state_after)
    assert (
        broadcast_readable_config_admission_issues(
            repository_root,
            project_path,
            typed_state,
        )
        == []
    )


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
    candidate = load_json_object(project_path / "00_PROJECT/broadcast_readable_config.json")
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
        raise AssertionError(f"알 수 없는 Registry Mutation입니다: {registry_mutation}")
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
    candidate = load_json_object(project_path / "00_PROJECT/broadcast_readable_config.json")
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
    records = list((project_path / ".runtime/transactions").glob("*/transaction.json"))
    assert len(records) == 1
    assert load_json_object(records[0])["status"] == "ROLLED_BACK"


def test_config_admission_recovers_prepared_transaction_before_commit(
    tmp_path: Path,
) -> None:
    """중단된 PREPARED Transaction을 복구한 뒤 새 Admission을 Commit한다."""
    repository_root, project_path = copied_pilot_repository(tmp_path)
    dependency_graph = load_json_object(repository_root / "STANDARD/dependency_graph.json")
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
    record_path = project_path / ".runtime/transactions" / transaction_id / "transaction.json"
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
        if isinstance(issue, dict) and issue.get("code") == "CANONICAL_ARTIFACT_DRIFT"
    )
    details = drift["artifacts"]
    assert isinstance(details, list)
    assert expected_reason in {
        str(detail.get("reason")) for detail in details if isinstance(detail, dict)
    }
    assert project_canonical_bytes(project_path) == before


def test_disabled_config_overrides_v1_pins_and_reactivation_is_explicit(
    tmp_path: Path,
) -> None:
    """disabled 우선순위와 후속 명시적 v2 재활성화를 보존한다."""
    _repository_root, project_path = copied_pilot_repository(tmp_path)
    active_config = load_json_object(project_path / "00_PROJECT/broadcast_readable_config.json")
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
    production_config = load_json_object(project_path / "00_PROJECT/production_config.json")
    assert disabled_result["result"] == "COMMITTED"
    assert (
        broadcast_readable_activation_mode(
            production_config,
            {"broadcast_readable_config": disabled_config},
        )
        == "DISABLED"
    )

    active_result = admit_broadcast_readable_config(
        project_path,
        active_path,
        "codex-app",
        "Readable v2 재활성화",
        "2026-09-03T01:01:00Z",
    )
    canonical_config = load_json_object(project_path / "00_PROJECT/broadcast_readable_config.json")
    assert active_result["result"] == "COMMITTED"
    assert (
        broadcast_readable_activation_mode(
            production_config,
            {"broadcast_readable_config": canonical_config},
        )
        == "V2_CONFIG"
    )


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
    prior_trace = next(
        trace
        for trace in trace_records(repository_root, project_path)
        if trace.get("process_revision") == 5
        and trace.get("task_id") == "script.compose_screenplay_units"
    )
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
        trace for trace in revision_traces if trace.get("execution_mode") == "VALIDATED_REUSE"
    ]
    assert {trace["task_id"] for trace in reused} == {
        "script.compose_screenplay_units",
    }
    assert len(reused) == 1
    assert reused[0]["reused_trace_id"] == prior_trace["trace_id"]
    assert reused[0]["input_hashes"] == prior_trace["input_hashes"]


def test_config_reuse_rejects_missing_prior_actual_trace(tmp_path: Path) -> None:
    """과거 실제 Trace ID가 사라지면 동일 Byte도 재사용하지 않는다."""
    repository_root, project_path = copied_pilot_repository_with_runtime(tmp_path)
    records = trace_records(repository_root, project_path)
    source_index = screenplay_source_trace_index(records)
    retained = [record for index, record in enumerate(records) if index != source_index]
    write_process_trace_records(project_path, retained)

    opened = open_config_reuse_candidate(
        repository_root,
        project_path,
        "2026-09-03T05:08:00Z",
    )

    assert opened["current_task_id"] == "script.compose_screenplay_units"
    assert opened["gate_phase"] == "AWAITING_LLM"


def test_config_reuse_rejects_prior_trace_input_hash_mismatch(
    tmp_path: Path,
) -> None:
    """과거 Trace와 Task Record의 입력 Hash가 다르면 재사용하지 않는다."""
    repository_root, project_path = copied_pilot_repository_with_runtime(tmp_path)
    records = trace_records(repository_root, project_path)
    source = records[screenplay_source_trace_index(records)]
    raw_hashes = source["input_hashes"]
    assert isinstance(raw_hashes, dict)
    first_artifact = sorted(raw_hashes)[0]
    raw_hashes[first_artifact] = "0" * 64
    write_process_trace_records(project_path, records)

    opened = open_config_reuse_candidate(
        repository_root,
        project_path,
        "2026-09-03T05:09:00Z",
    )

    assert opened["current_task_id"] == "script.compose_screenplay_units"
    assert opened["gate_phase"] == "AWAITING_LLM"


def test_config_reuse_rejects_prior_trace_commit_mismatch(tmp_path: Path) -> None:
    """과거 Trace와 Task Record의 Commit 결속이 다르면 재사용하지 않는다."""
    repository_root, project_path = copied_pilot_repository_with_runtime(tmp_path)
    records = trace_records(repository_root, project_path)
    source = records[screenplay_source_trace_index(records)]
    source["commit_sha"] = "0" * 64
    write_process_trace_records(project_path, records)

    opened = open_config_reuse_candidate(
        repository_root,
        project_path,
        "2026-09-03T05:10:00Z",
    )

    assert opened["current_task_id"] == "script.compose_screenplay_units"
    assert opened["gate_phase"] == "AWAITING_LLM"


def test_owner_return_requires_target_llm_task_execution(tmp_path: Path) -> None:
    """Owner Return 대상은 같은 입력·기존 Byte가 있어도 재사용하지 않는다."""
    repository_root, project_path = copied_committed_pilot_repository(tmp_path)
    result = return_task_to_owner(
        repository_root,
        project_path,
        "script_writer",
        "critic-reviewer",
        "대본의 의미 수정이 필요함",
        "2026-09-03T05:10:00Z",
    )

    opened = task_open(
        repository_root,
        project_path,
        "GATE-08",
        "2026-09-03T05:11:00Z",
        None,
    )

    assert result["target_gate"] == "GATE-08"
    assert result["target_task_ids"] == ["script.compose_screenplay_units"]
    state = load_json_object(project_path / "00_PROJECT/project_state.json")
    revision_trigger = state["revision_trigger"]
    assert isinstance(revision_trigger, dict)
    assert revision_trigger["type"] == "OWNER_RETURN"
    assert revision_trigger["target_owner_agent"] == "script_writer"
    assert revision_trigger["target_gate"] == "GATE-08"
    assert revision_trigger["target_task_ids"] == result["target_task_ids"]
    assert revision_trigger["actor"] == "critic-reviewer"
    assert revision_trigger["reason"] == "대본의 의미 수정이 필요함"
    assert revision_trigger["returned_at"] == "2026-09-03T05:10:00Z"
    assert opened["revision_trigger"] == revision_trigger
    assert opened["current_task_id"] == "script.compose_screenplay_units"
    assert opened["gate_phase"] == "AWAITING_LLM"
    execution_modes = opened["task_execution_modes"]
    assert isinstance(execution_modes, dict)
    assert "script.compose_screenplay_units" not in execution_modes


def test_other_owner_return_blocks_target_and_reuses_unaffected_upstream_task(
    tmp_path: Path,
) -> None:
    """다른 Owner 반환도 대상은 재실행하고 영향 없는 선행 Task는 재사용한다."""
    repository_root, project_path = copied_committed_pilot_repository(tmp_path)
    install_gate_seven_reuse_record(repository_root, project_path)
    result = return_task_to_owner(
        repository_root,
        project_path,
        "story_architect",
        "critic-reviewer",
        "상태 전이 의미 수정이 필요함",
        "2026-09-03T05:12:00Z",
    )

    opened = task_open(
        repository_root,
        project_path,
        "GATE-07",
        "2026-09-03T05:13:00Z",
        None,
    )

    assert result["target_gate"] == "GATE-07"
    target_task_ids = result["target_task_ids"]
    assert isinstance(target_task_ids, list)
    assert target_task_ids == ["story.design_state_transitions"]
    assert opened["current_task_id"] == "story.design_state_transitions"
    assert opened["gate_phase"] == "AWAITING_LLM"
    execution_modes = opened["task_execution_modes"]
    assert isinstance(execution_modes, dict)
    assert execution_modes["scene.design"] == "VALIDATED_REUSE"
    assert "story.design_state_transitions" not in execution_modes


@pytest.mark.parametrize(
    "trigger_type",
    ["HUMAN_REVISION_REQUEST", "SEMANTIC_CORRECTION"],
)
def test_explicit_revision_trigger_blocks_target_task_reuse(
    tmp_path: Path,
    trigger_type: str,
) -> None:
    """Human·Semantic 재작성 Trigger는 지정 LLM Task를 반드시 다시 연다."""
    repository_root, project_path = copied_committed_pilot_repository(tmp_path)
    return_task_to_owner(
        repository_root,
        project_path,
        "script_writer",
        "critic-reviewer",
        "대본 재작성 범위 설정",
        "2026-09-03T05:14:00Z",
    )
    state_path = project_path / "00_PROJECT/project_state.json"
    state = load_json_object(state_path)
    revision_trigger = state["revision_trigger"]
    assert isinstance(revision_trigger, dict)
    revision_trigger["type"] = trigger_type
    revision_trigger["source_id"] = f"{trigger_type}:TEST"
    write_json_object(state_path, state)

    opened = task_open(
        repository_root,
        project_path,
        "GATE-08",
        "2026-09-03T05:15:00Z",
        None,
    )

    assert opened["current_task_id"] == "script.compose_screenplay_units"
    assert opened["gate_phase"] == "AWAITING_LLM"
    execution_modes = opened["task_execution_modes"]
    assert isinstance(execution_modes, dict)
    assert "script.compose_screenplay_units" not in execution_modes


def test_missing_revision_trigger_is_not_treated_as_config_only(tmp_path: Path) -> None:
    """누락된 Trigger는 Config-only 최적화로 추정하지 않는다."""
    repository_root, project_path = copied_pilot_repository_with_runtime(tmp_path)
    admit_broadcast_readable_config(
        project_path,
        project_path / "00_PROJECT/broadcast_readable_config.json",
        "codex-app",
        "Config Trigger 생성",
        ADMITTED_AT,
    )
    state_path = project_path / "00_PROJECT/project_state.json"
    state = load_json_object(state_path)
    state.pop("revision_trigger")
    write_json_object(state_path, state)

    opened = task_open(
        repository_root,
        project_path,
        "GATE-08",
        "2026-09-03T05:16:00Z",
        None,
    )

    assert opened["current_task_id"] == "script.compose_screenplay_units"
    assert opened["gate_phase"] == "AWAITING_LLM"


def test_unknown_revision_trigger_is_rejected_by_task_record_schema(
    tmp_path: Path,
) -> None:
    """알 수 없는 Trigger를 Config-only로 추정하지 않고 계약 오류로 거부한다."""
    repository_root, project_path = copied_pilot_repository_with_runtime(tmp_path)
    admit_broadcast_readable_config(
        project_path,
        project_path / "00_PROJECT/broadcast_readable_config.json",
        "codex-app",
        "Config Trigger 생성",
        ADMITTED_AT,
    )
    state_path = project_path / "00_PROJECT/project_state.json"
    state = load_json_object(state_path)
    revision_trigger = state["revision_trigger"]
    assert isinstance(revision_trigger, dict)
    revision_trigger["type"] = "UNKNOWN_TRIGGER"
    write_json_object(state_path, state)

    with pytest.raises(GateTransactionError) as raised:
        task_open(
            repository_root,
            project_path,
            "GATE-08",
            "2026-09-03T05:17:00Z",
            None,
        )

    assert raised.value.code == "GATE_TRANSACTION_RECORD_INVALID"


@pytest.mark.parametrize("tampered_field", ["reason", "target_task_ids"])
def test_revision_trigger_task_snapshot_rejects_owner_return_tampering(
    tmp_path: Path,
    tampered_field: str,
) -> None:
    """Task Snapshot의 Owner 반환 사유·대상 변조는 재사용 권한을 잃는다."""
    repository_root, project_path = copied_committed_pilot_repository(tmp_path)
    return_task_to_owner(
        repository_root,
        project_path,
        "scene_designer",
        "critic-reviewer",
        "Scene 의미 수정이 필요함",
        "2026-09-03T05:18:00Z",
    )
    state = load_json_object(project_path / "00_PROJECT/project_state.json")
    state_trigger = state["revision_trigger"]
    assert isinstance(state_trigger, dict)
    task_trigger = deepcopy(state_trigger)
    if tampered_field == "reason":
        task_trigger["reason"] = "변조된 사유"
    else:
        task_trigger["target_task_ids"] = []
    task_id = "story.design_state_transitions"
    task = load_task_catalog(repository_root)[task_id]

    assert revision_trigger_allows_validated_reuse(
        task_id,
        task,
        state_trigger,
        state_trigger,
    )
    assert not revision_trigger_allows_validated_reuse(
        task_id,
        task,
        task_trigger,
        state_trigger,
    )


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


def prefix_overlap_fixture() -> PilotFixture:
    """짧은 Screen Text가 확장 Block의 Prefix인 A→B→A Source를 만든다."""
    fixture = pilot_fixture()
    segments = mapping_list(fixture["presentation_plan"], "segments")
    narration_segment = next(
        segment for segment in segments if segment.get("segment_id") == "SEG-002"
    )
    narration_segment["segment_type"] = "DRAMA"
    narration_segment["source_artifact"] = "drama_script"
    narration_segment.pop("narrator_character_id", None)
    narration_segment.pop("narration_function", None)
    texts = {
        "UNIT-002": "한글",
        "UNIT-011": "한글 확장\n둘째 줄",
        "UNIT-009": "한글",
        "UNIT-010": "다른 화면",
    }
    for unit_id, text in texts.items():
        unit = unit_by_id(fixture, unit_id)
        unit["type"] = "SCREEN_TEXT"
        unit["text"] = text
        unit.pop("speaker_id", None)
        unit.pop("delivery", None)
    fixture["final_script"] = render_pilot_fixture_machine_master(fixture)
    return fixture


def set_dialogue_unit(
    fixture: PilotFixture,
    unit_id: str,
    speaker_id: str,
    text: str,
) -> None:
    """지정 Unit을 전달 지시 없는 대사 Block으로 만든다."""
    unit = unit_by_id(fixture, unit_id)
    unit["type"] = "DIALOGUE"
    unit["speaker_id"] = speaker_id
    unit["text"] = text
    unit.pop("delivery", None)


def test_internal_blank_paragraph_prefix_maps_only_owned_units() -> None:
    """긴 대사 내부 빈 문단이 짧은 대사의 추가 발생으로 계산되지 않는다."""
    fixture = pilot_fixture()
    set_dialogue_unit(fixture, "UNIT-003", "CHAR-05", "안녕")
    set_dialogue_unit(
        fixture,
        "UNIT-006",
        "CHAR-05",
        "안녕\n\n추가 설명",
    )
    rendered = render_fixture(fixture)
    report = build_report(fixture, rendered)

    assert report["result"] == "NEEDS_REVIEW"
    assert report["issues"] == []


def test_identical_drama_and_panel_blocks_keep_container_ownership() -> None:
    """동일한 대사와 Panel Block은 서로의 발생 개수에 포함되지 않는다."""
    fixture = pilot_fixture()
    set_dialogue_unit(fixture, "UNIT-003", "CHAR-05", "확인했습니다.")
    characters = mapping_list(fixture["characters"], "characters")
    speaker = next(
        character for character in characters if character.get("character_id") == "CHAR-05"
    )
    reactions = mapping_list(fixture["reaction_segments"], "reaction_segments")
    first_turn = mapping_list(reactions[0], "turns")[0]
    panelists = mapping_list(fixture["panel_cast"], "panelists")
    panelist = next(
        item for item in panelists if item.get("panelist_id") == first_turn["panelist_id"]
    )
    panelist["display_name"] = speaker["name"]
    first_turn["spoken_line"] = "확인했습니다."
    rendered = render_fixture(fixture)
    report = build_report(fixture, rendered)

    assert report["result"] == "NEEDS_REVIEW"
    assert report["issues"] == []
    unit_mapping = next(
        mapping
        for mapping in mapping_records(report, "unit_mappings")
        if mapping.get("unit_id") == "UNIT-003"
    )
    turn_mapping = next(
        mapping
        for mapping in mapping_records(report, "panel_turn_mappings")
        if mapping.get("turn_id") == first_turn["turn_id"]
    )
    assert unit_mapping["container_type"] == "DRAMA"
    assert turn_mapping["container_type"] == "PANEL_REACTION"
    assert unit_mapping["exact_occurrence_index"] == 1
    assert turn_mapping["exact_occurrence_index"] == 1
    assert unit_mapping["actual_byte_range"] != turn_mapping["actual_byte_range"]


def test_unit_text_inside_context_does_not_change_owner_count() -> None:
    """Context 내부의 동일 가시 Block은 Unit 소유권과 개수에 관여하지 않는다."""
    fixture = pilot_fixture()
    unit = unit_by_id(fixture, "UNIT-002")
    unit["type"] = "SCREEN_TEXT"
    unit["text"] = "공통 문구"
    unit.pop("speaker_id", None)
    unit.pop("delivery", None)
    scenes = mapping_list(fixture["screenplay_units"], "scenes")
    context = scenes[0]["context"]
    assert isinstance(context, dict)
    context["location_description"] = "세탁실 입구\n\n**화면 문구**\n공통 문구\n\n관리실 복도"
    rendered = render_fixture(fixture)
    report = build_report(fixture, rendered)

    assert report["result"] == "NEEDS_REVIEW"
    assert report["issues"] == []


def test_prefix_overlap_passes_source_renderer_verifier_report_and_gate(
    tmp_path: Path,
) -> None:
    """Prefix 정상 입력이 Source부터 GATE-09까지 전체 소비 경로를 통과한다."""
    fixture = prefix_overlap_fixture()
    rendered = render_fixture(fixture)
    conformance = independent_conformance(
        fixture["screenplay_units"],
        fixture["characters"],
        fixture["relationships"],
        fixture["panel_cast"],
        fixture["reaction_segments"],
        fixture["presentation_plan"],
        fixture["profile"],
        rendered,
    )
    assert conformance["issues"] == []
    report = build_report(fixture, rendered)
    assert report["result"] == "NEEDS_REVIEW"
    assert report["issues"] == []

    repository_root, project_path = prepare_gate_project(
        tmp_path,
        fixture,
        93,
        "Prefix 중첩 정상 경로 Config 승인",
    )
    for gate_number in range(4, 10):
        gate_id = f"GATE-{gate_number:02d}"
        gate_result = submit_gate_until_committed(
            repository_root,
            project_path,
            gate_id,
            f"2026-09-03T04:{gate_number:02d}:00Z",
            f"2026-09-03T04:{gate_number:02d}:30Z",
        )
        assert gate_result["status"] == "COMMITTED"

    assert (project_path / "07_SCRIPT/broadcast_readable_script.md").read_text(
        encoding="utf-8"
    ) == rendered
    gate_report = load_json_object(project_path / "08_QA/broadcast_readable_report.json")
    assert gate_report["result"] == "NEEDS_REVIEW"
    assert gate_report["issues"] == []
    gate_traces = [
        trace
        for trace in trace_records(repository_root, project_path)
        if trace.get("process_revision") == 93
    ]
    assert any(trace.get("task_id") == "script.render_broadcast_readable" for trace in gate_traces)
    assert any(
        trace.get("task_id") == "continuity.validate_broadcast_readable" for trace in gate_traces
    )


def test_prefix_overlap_extra_standalone_block_fails_global_count() -> None:
    """긴 Prefix 내부는 제외하되 독립 Short Block 중복은 전역 개수로 거부한다."""
    fixture = prefix_overlap_fixture()
    rendered = render_fixture(fixture)
    short_block = "**화면 문구**\n한글"
    duplicated = rendered.replace(
        f"{short_block}\n\n",
        f"{short_block}\n\n{short_block}\n\n",
        1,
    )

    report = build_report(fixture, duplicated)
    raw_issues = report["issues"]
    assert isinstance(raw_issues, list)
    assert all(isinstance(issue, dict) for issue in raw_issues)

    assert "BROADCAST_READABLE_V2_UNIT_OCCURRENCE_MISMATCH" in issue_codes(
        [issue for issue in raw_issues if isinstance(issue, dict)]
    )


def test_identical_blocks_follow_a_b_a_presentation_segments() -> None:
    """동일 Block 세 개도 Scene 순서가 아닌 A→B→A 표시 순서로 소비한다."""
    fixture = pilot_fixture()
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
    fixture["final_script"] = render_pilot_fixture_machine_master(fixture)

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
    for unit_id in ("UNIT-001", "UNIT-009", "UNIT-011"):
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
    assert block_occurrence_ranges(actual, "한글") == [
        {"byte_start": 0, "byte_end": 6},
        {"byte_start": 34, "byte_end": 40},
    ]
    assert block_occurrence_ranges(actual, "한글 확장\n둘째 줄") == [
        {"byte_start": 8, "byte_end": 32}
    ]

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
    fixture = pilot_fixture()
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
        panelist for panelist in panelists if panelist.get("panelist_id") == turns[0]["panelist_id"]
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
        if isinstance(mapping, dict) and mapping.get("unit_id") in {"UNIT-003", "UNIT-013"}
    ]
    repeated_panel_mappings = [
        mapping
        for mapping in panel_mappings
        if isinstance(mapping, dict) and mapping.get("turn_id") in {"TURN-001-01", "TURN-001-02"}
    ]
    assert [mapping["exact_occurrence_index"] for mapping in repeated_action_mappings] == [1, 2, 3]
    assert [mapping["exact_occurrence_index"] for mapping in repeated_dialogue_mappings] == [1, 2]
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
    channel = load_json_object(ROOT / "CHANNELS/mystery_main/versions/2.1.0/channel_dna.json")

    issues = validate_presentation_design(
        fixture["panel_cast"],
        fixture["reaction_segments"],
        fixture["presentation_plan"],
        fixture["scene_cards"],
        fixture["viewer_timeline"],
        fixture["facts"],
        fixture["clue_matrix"],
        channel,
        fixture["production_config"],
    )

    assert issues == []


@pytest.mark.parametrize("fixture_id", ["R1", "R2"])
def test_source_style_fixture_passes_real_gate_transactions(
    tmp_path: Path,
    fixture_id: str,
) -> None:
    """R1·R2가 정상 GATE-04~09 Transaction과 의미 Validator를 통과한다."""
    fixture = apply_feature_fixture(fixture_id)
    repository_root, project_path = prepare_source_style_gate_project(
        tmp_path,
        fixture_id,
    )
    state_before = load_json_object(project_path / "00_PROJECT/project_state.json")
    readiness_before = state_before["readiness"]
    assert isinstance(readiness_before, dict)
    process_revision = readiness_before["process_revision"]
    for gate_number in range(4, 10):
        gate_id = f"GATE-{gate_number:02d}"
        result = submit_fixture_gate_until_committed(
            repository_root,
            project_path,
            fixture,
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
    expected_gate_ids = {
        "GATE-04",
        "GATE-05",
        "GATE-06",
        "GATE-07",
        "GATE-08",
        "GATE-09",
    }
    assert expected_gate_ids <= {trace["gate_id"] for trace in gate_traces}
    acceptance_gate_traces = [
        trace for trace in gate_traces if trace["gate_id"] in expected_gate_ids
    ]
    assert any(
        trace["task_id"] == "script.render_broadcast_readable" for trace in acceptance_gate_traces
    )
    assert any(
        trace["task_id"] == "continuity.validate_broadcast_readable"
        for trace in acceptance_gate_traces
    )
    assert_fixture_gate_hash_chain(
        repository_root,
        project_path,
        acceptance_gate_traces,
    )
    expected_hashes = fixture_metadata(fixture_id)["expected_artifact_sha256"]
    assert (
        document_sha256(load_json_object(project_path / "01_CASE/facts.json"))
        == expected_hashes["facts"]
    )
    assert (
        document_sha256(load_json_object(project_path / "01_CASE/crime_event_contract.json"))
        == expected_hashes["crime_event_contract"]
    )
    assert (
        document_sha256(load_json_object(project_path / "07_SCRIPT/screenplay_units.json"))
        == expected_hashes["screenplay_units"]
    )
    assert (project_path / "07_SCRIPT/final_script.md").read_text(
        encoding="utf-8"
    ) == render_fixture_machine_master(fixture)
    report = load_json_object(project_path / "08_QA/broadcast_readable_report.json")
    assert report["schema_version"] == "2.1.0"
    assert report["mapping_contract_version"] == "OWNER_BOUND_1"
    assert report["result"] == "NEEDS_REVIEW"
    assert report["issues"] == []


@pytest.mark.parametrize("fixture_id", ["R1", "R2"])
def test_gate_four_contract_matches_fixture_source_hash(
    tmp_path: Path,
    fixture_id: str,
) -> None:
    """실제 GATE-04 CORE Contract는 Fixture가 선언한 상위 사건 입력과 결속된다."""
    fixture = apply_feature_fixture(fixture_id)
    repository_root, project_path = prepare_source_style_gate_project(
        tmp_path,
        fixture_id,
    )
    result = submit_fixture_gate_until_committed(
        repository_root,
        project_path,
        fixture,
        "GATE-04",
        "2026-09-03T03:40:00Z",
        "2026-09-03T03:40:30Z",
    )
    actual_contract = load_json_object(project_path / "01_CASE/crime_event_contract.json")
    actual_facts = load_json_object(project_path / "01_CASE/facts.json")

    assert result["status"] == "COMMITTED"
    assert document_sha256(actual_facts) == document_sha256(fixture["facts"])
    assert document_sha256(actual_contract) == document_sha256(fixture["crime_event_contract"])


def test_cross_fixture_gate_three_facts_fail_gate_four_snapshot(tmp_path: Path) -> None:
    """R1 GATE-03에 R2 Facts를 주입하면 GATE-04가 Canonical Drift를 거부한다."""
    repository_root, project_path = prepare_source_style_gate_project(tmp_path, "R1")
    foreign_fixture = apply_feature_fixture("R2")
    write_json_object(project_path / "01_CASE/facts.json", foreign_fixture["facts"])

    with pytest.raises(GateTransactionError):
        task_open(
            repository_root,
            project_path,
            "GATE-04",
            "2026-09-03T03:41:00Z",
            None,
        )


def test_unrevealed_panel_evidence_fails_real_gate_seven(tmp_path: Path) -> None:
    """미공개 Fact를 아는 Panel 후보는 실제 GATE-07 Commit에서 거부된다."""
    fixture = apply_feature_fixture("R2")
    reactions = mapping_list(fixture["reaction_segments"], "reaction_segments")
    result_first_turn = mapping_list(reactions[2], "turns")[0]
    result_first_turn["known_fact_ids"] = ["FACT-01", "FACT-02"]
    repository_root, project_path = prepare_source_style_gate_project(tmp_path, "R2")
    for gate_number in range(4, 7):
        result = submit_fixture_gate_until_committed(
            repository_root,
            project_path,
            fixture,
            f"GATE-{gate_number:02d}",
            f"2026-09-03T03:{gate_number:02d}:00Z",
            f"2026-09-03T03:{gate_number:02d}:30Z",
        )
        assert result["status"] == "COMMITTED"

    with pytest.raises(AssertionError):
        submit_fixture_gate_until_committed(
            repository_root,
            project_path,
            fixture,
            "GATE-07",
            "2026-09-03T03:07:00Z",
            "2026-09-03T03:07:30Z",
        )


def test_prj_006_master_injection_fails_gate_nine_snapshot(tmp_path: Path) -> None:
    """R1 GATE-08 Master를 PRJ-006 Byte로 바꾸면 GATE-09가 Drift를 거부한다."""
    fixture = apply_feature_fixture("R1")
    repository_root, project_path = prepare_source_style_gate_project(tmp_path, "R1")
    for gate_number in range(4, 9):
        result = submit_fixture_gate_until_committed(
            repository_root,
            project_path,
            fixture,
            f"GATE-{gate_number:02d}",
            f"2026-09-03T03:{gate_number:02d}:00Z",
            f"2026-09-03T03:{gate_number:02d}:30Z",
        )
        assert result["status"] == "COMMITTED"
    (project_path / "07_SCRIPT/final_script.md").write_bytes(
        (PILOT_ROOT / "07_SCRIPT/final_script.md").read_bytes()
    )

    with pytest.raises(GateTransactionError):
        task_open(
            repository_root,
            project_path,
            "GATE-09",
            "2026-09-03T03:09:00Z",
            None,
        )


def test_v2_enabled_requires_manifest_when_footprint_is_disabled() -> None:
    """v2 활성 경로는 Footprint와 무관하게 GATE-13 Manifest를 요구한다."""
    fixture = apply_feature_fixture("R1")
    production_config = load_json_object(PILOT_ROOT / "00_PROJECT/production_config.json")
    channel = load_json_object(ROOT / "CHANNELS/mystery_main/versions/2.1.0/channel_dna.json")
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
    production_config = load_json_object(PILOT_ROOT / "00_PROJECT/production_config.json")
    channel = load_json_object(ROOT / "CHANNELS/mystery_main/versions/2.1.0/channel_dna.json")
    constraints = deepcopy(load_json_object(PILOT_ROOT / "00_PROJECT/project_constraints.json"))
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
    assert (
        task_condition_matches(
            task["condition"],
            production_config,
            channel,
            artifacts,
        )
        is expected
    )
    assert (
        artifact_required_for_project(
            manifest_definition,
            channel,
            production_config,
            artifacts,
        )
        is expected
    )


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
    _readable, _report, _production_copy, manifest = build_footprint_off_readable_chain(
        project_path, project_constraints
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
    constraints = load_json_object(project_path / "00_PROJECT/project_constraints.json")
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
    """독립 R1 Source가 v2+Footprint-off 상태로 실제 GATE-13까지 완주한다."""
    fixture = apply_feature_fixture("R1")
    repository_root, project_path = prepare_source_style_gate_project(
        tmp_path,
        "R1",
    )
    footprint_path = project_path / "06_SCENE/production_footprint.json"
    assert not footprint_path.exists()
    expected_master = render_fixture_machine_master(fixture)
    for gate_number in range(4, 14):
        gate_id = f"GATE-{gate_number:02d}"
        gate_result = submit_fixture_gate_until_committed(
            repository_root,
            project_path,
            fixture,
            gate_id,
            utc_now(),
            utc_now(),
        )
        assert gate_result["status"] == "COMMITTED"
    assert (project_path / "07_SCRIPT/final_script.md").read_text(
        encoding="utf-8"
    ) == expected_master
    expected_hashes = fixture_metadata("R1")["expected_artifact_sha256"]
    assert (
        document_sha256(load_json_object(project_path / "07_SCRIPT/screenplay_units.json"))
        == expected_hashes["screenplay_units"]
    )
    assert not footprint_path.exists()
    readable_report = load_json_object(project_path / "08_QA/broadcast_readable_report.json")
    assert readable_report["schema_version"] == "2.1.0"
    assert readable_report["mapping_contract_version"] == "OWNER_BOUND_1"
    assert readable_report["result"] == "NEEDS_REVIEW"
    assert readable_report["issues"] == []
    production_copy = project_path / "09_PRODUCTION/broadcast_readable_script.md"
    canonical_readable = project_path / "07_SCRIPT/broadcast_readable_script.md"
    assert production_copy.read_bytes() == canonical_readable.read_bytes()
    manifest = load_json_object(project_path / "09_PRODUCTION/production_manifest.json")
    assert manifest["schema_version"] == "1.2.0"
    deliverables = mapping_list(manifest, "deliverables")
    readable_deliverable = next(
        item
        for item in deliverables
        if item.get("artifact_name") == "production_broadcast_readable_script"
    )
    assert readable_deliverable["source_report_sha256"] == document_sha256(readable_report)
    state = load_json_object(project_path / "00_PROJECT/project_state.json")
    assert state["current_gate"] == "GATE-13"
    assert state["state"] == "EDITORIAL_REVIEW_REQUIRED"
    assert state.get("editorial_approved") is not True
    assert state.get("production_ready") is not True
    gate_thirteen_traces = [
        trace
        for trace in trace_records(repository_root, project_path)
        if trace.get("gate_id") == "GATE-13"
    ]
    assert_task_input_hashes_match_canonical(
        repository_root,
        project_path,
        gate_thirteen_traces,
        "production.package_broadcast_readable",
        ("broadcast_readable_script", "broadcast_readable_report"),
    )
    assert_task_input_hashes_match_canonical(
        repository_root,
        project_path,
        gate_thirteen_traces,
        "production.build_manifest",
        ("broadcast_readable_report", "production_broadcast_readable_script"),
    )
    audit = audit_project(
        repository_root,
        project_path,
        None,
        None,
        "2026-09-03T02:00:00Z",
    )
    assert audit["result"] == "PASS"
