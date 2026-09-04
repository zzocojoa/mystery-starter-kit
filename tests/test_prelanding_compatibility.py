"""배포 전 Legacy 계약과 실제 Gate 경로의 호환성 회귀를 검증한다."""

import asyncio
from collections.abc import Mapping
from copy import deepcopy
from pathlib import Path
from shutil import copytree

import pytest
from project_factory import make_complete_project_artifacts
from runtime.support import create_runtime_project, create_runtime_repository
from test_broadcast_readable_script import pilot_documents, pilot_profile, rendered_pilot
from test_broadcast_readable_v2_validation import build_report, pilot_fixture, render_fixture
from test_gate_transaction import OPENED_AT, submit_allowed_outputs
from test_production_cli import configure_legacy_v1_project

from RUNTIME.context import build_minimal_context
from RUNTIME.contracts import load_task_catalog
from RUNTIME.core_tasks import runtime_validation_inputs_for_project, story_history
from RUNTIME.engine import execute_run
from RUNTIME.errors import RuntimeExecutionError
from RUNTIME.gate_control import validate_gate
from VALIDATORS.broadcast_readable import build_broadcast_readable_report
from VALIDATORS.exceptions import ConfigurationError
from VALIDATORS.gate_transaction import task_open
from VALIDATORS.io import load_json_object, write_json_object
from VALIDATORS.pipeline import (
    ArtifactContent,
    load_existing_project_artifacts,
    run_production_validation,
)
from VALIDATORS.schema_validation import collect_schema_errors
from VALIDATORS.state_machine import GATES

ROOT = Path(__file__).resolve().parents[1]
PILOT_ROOT = ROOT / "PROJECTS/PRJ-006"


def legacy_gate_project(tmp_path: Path, channel_version: str) -> tuple[Path, Path]:
    """기존 Pin을 가진 격리 Project를 정식 GATE-00부터 GATE-04까지 실행한다."""
    repository_root = create_runtime_repository(tmp_path.resolve())
    project_path = create_runtime_project(repository_root, "PRJ-960")
    configure_legacy_v1_project(project_path)
    config_path = project_path / "00_PROJECT/production_config.json"
    config = load_json_object(config_path)
    for key in (
        "script_source_mode",
        "reenactment_output_profile_id",
        "reenactment_output_profile_version",
    ):
        config.pop(key)
    engine_version = "1.0.0" if channel_version == "1.1.0" else "2.0.0"
    config.update(
        channel_content_version=channel_version,
        variation_engine_version=engine_version,
        variation_catalog_version=engine_version,
        genre="MYSTERY" if channel_version == "1.1.0" else "CRIME_PSYCHOLOGICAL_THRILLER",
    )
    write_json_object(config_path, config)
    asyncio.run(
        execute_run(
            repository_root, project_path, "GATE-00", "GATE-04", "default", None, None
        )
    )
    return repository_root, project_path


@pytest.mark.parametrize("channel_version", ["1.1.0", "2.0.0"])
def test_legacy_channel_runs_and_submits_gate_five(
    tmp_path: Path, channel_version: str
) -> None:
    """Legacy는 2.1 전용 Dummy 없이 Runtime과 App Transaction을 모두 통과한다."""
    repository_root, project_path = legacy_gate_project(tmp_path, channel_version)
    graph = load_json_object(repository_root / "STANDARD/dependency_graph.json")
    assert "crime_event_contract" not in load_existing_project_artifacts(project_path, graph)
    golden_path = repository_root / "PROJECTS/PRJ-960-GOLDEN"
    copytree(project_path, golden_path)
    asyncio.run(
        execute_run(
            repository_root, golden_path, "GATE-05", "GATE-05", "default", None, None
        )
    )
    record = task_open(repository_root, project_path, "GATE-05", OPENED_AT, None)
    assert record["current_task_id"] == "mystery.design"
    result = submit_allowed_outputs(
        repository_root, project_path, golden_path, record, "GATE-05"
    )
    assert result["status"] == "COMMITTED"
    assert "crime_event_contract" not in load_existing_project_artifacts(project_path, graph)


def test_channel_two_still_requires_clean_facts(tmp_path: Path) -> None:
    """Channel 2.0의 실제 필수 Facts가 누락되면 Context는 명시적으로 실패한다."""
    repository_root, project_path = legacy_gate_project(tmp_path, "2.0.0")
    graph = load_json_object(repository_root / "STANDARD/dependency_graph.json")
    task = load_task_catalog(repository_root)["mystery.design"]
    state_path = project_path / "00_PROJECT/project_state.json"
    state = load_json_object(state_path)
    states = state["artifacts"]
    assert isinstance(states, dict)
    states.pop("facts")
    write_json_object(state_path, state)
    before = state_path.read_bytes()
    with pytest.raises(RuntimeExecutionError) as captured:
        build_minimal_context(repository_root, project_path, "mystery.design", task, graph, {})
    assert captured.value.code == "RUNTIME_CONFIGURATION_ERROR"
    assert captured.value.artifact_name == "facts"
    assert state_path.read_bytes() == before


def test_channel_two_one_still_requires_crime_event_contract() -> None:
    """GATE-05 입력을 선택화해도 2.1의 선행 GATE-04 필수 계약은 유지된다."""
    artifacts = load_existing_project_artifacts(
        PILOT_ROOT, load_json_object(ROOT / "STANDARD/dependency_graph.json")
    )
    config = artifacts["production_config"]
    assert isinstance(config, Mapping)
    inputs = runtime_validation_inputs_for_project(ROOT, config, artifacts, None)
    assert validate_gate("GATE-04", artifacts, *inputs, story_history(ROOT), None) == []
    artifacts.pop("crime_event_contract")
    issues = validate_gate("GATE-04", artifacts, *inputs, story_history(ROOT), None)
    assert any(
        issue["code"] == "REQUIRED_CHANNEL_ARTIFACT_MISSING"
        and issue["artifact"] == "crime_event_contract"
        for issue in issues
    )


def v1_readable_artifacts() -> dict[str, ArtifactContent]:
    """Canonical 입력을 변경하지 않고 정식 v1 Renderer와 Report를 메모리에서 만든다."""
    artifacts = load_existing_project_artifacts(
        PILOT_ROOT, load_json_object(ROOT / "STANDARD/dependency_graph.json")
    )
    artifacts.pop("broadcast_readable_config")
    config, profile, profile_hash = pilot_profile()
    screenplay, characters, panel_cast, reactions, plan = pilot_documents()
    readable = rendered_pilot()
    artifacts["broadcast_readable_script"] = readable
    artifacts["broadcast_readable_report"] = build_broadcast_readable_report(
        config, screenplay, characters, panel_cast, reactions, plan, profile, profile_hash, readable
    )
    return artifacts


def readable_gate_nine_issues(artifacts: dict[str, ArtifactContent]) -> list[str]:
    """실제 GATE-09 Production Validator의 Issue Code를 반환한다."""
    config = artifacts["production_config"]
    assert isinstance(config, Mapping)
    inputs = runtime_validation_inputs_for_project(ROOT, config, artifacts, None)
    return [
        issue["code"]
        for issue in validate_gate("GATE-09", artifacts, *inputs, story_history(ROOT), None)
    ]


def test_readable_v1_passes_production_gate_nine() -> None:
    """정상 v1 Report는 명시적인 v1 Schema와 Validator로 GATE-09를 통과한다."""
    artifacts = v1_readable_artifacts()
    config = artifacts["production_config"]
    assert isinstance(config, Mapping)
    inputs = runtime_validation_inputs_for_project(ROOT, config, artifacts, None)
    report = run_production_validation(artifacts, *inputs, story_history(ROOT), None)
    assert report["gate_results"]["GATE-09"] == "PASS"
    assert readable_gate_nine_issues(artifacts) == []


def test_readable_v1_malformed_report_fails_gate_nine() -> None:
    """v1 선택 복원 뒤에도 실제 필수 Report 필드 누락은 거부한다."""
    artifacts = v1_readable_artifacts()
    report = artifacts["broadcast_readable_report"]
    assert isinstance(report, dict)
    report.pop("input_artifact_hashes")
    assert "ARTIFACT_SCHEMA_VIOLATION" in readable_gate_nine_issues(artifacts)


def test_unregistered_readable_report_fails_closed_at_gate_nine() -> None:
    """미등록 Version을 최신 Report Schema로 대체하지 않는다."""
    artifacts = v1_readable_artifacts()
    report = artifacts["broadcast_readable_report"]
    assert isinstance(report, dict)
    report["schema_version"] = "99.0.0"
    config = artifacts["production_config"]
    assert isinstance(config, Mapping)
    inputs = runtime_validation_inputs_for_project(ROOT, config, artifacts, None)
    with pytest.raises(ConfigurationError, match=r"schema_version=99\.0\.0"):
        run_production_validation(artifacts, *inputs, story_history(ROOT), None)
    with pytest.raises(ConfigurationError, match=r"schema_version=99\.0\.0"):
        readable_gate_nine_issues(artifacts)


@pytest.mark.parametrize("report_version", ["2.0.0", "2.1.0"])
def test_readable_v2_historical_and_owner_bound_gate_nine(report_version: str) -> None:
    """Historical 2.0과 현재 Owner-bound 2.1은 각각의 명시 계약으로 통과한다."""
    artifacts = load_existing_project_artifacts(
        PILOT_ROOT, load_json_object(ROOT / "STANDARD/dependency_graph.json")
    )
    if report_version == "2.1.0":
        fixture = pilot_fixture()
        artifacts["broadcast_readable_report"] = build_report(fixture, render_fixture(fixture))
    report = artifacts["broadcast_readable_report"]
    assert isinstance(report, Mapping)
    assert report["schema_version"] == report_version
    assert readable_gate_nine_issues(artifacts) == []
    config = artifacts["production_config"]
    assert isinstance(config, Mapping)
    inputs = runtime_validation_inputs_for_project(ROOT, config, artifacts, None)
    validation = run_production_validation(artifacts, *inputs, story_history(ROOT), None)
    assert validation["gate_results"]["GATE-09"] == "PASS"


def test_current_readable_owner_mapping_missing_fails_gate_nine() -> None:
    """Owner-bound 2.1의 Owner 누락을 실제 GATE-09 Schema가 거부한다."""
    artifacts = load_existing_project_artifacts(
        PILOT_ROOT, load_json_object(ROOT / "STANDARD/dependency_graph.json")
    )
    fixture = pilot_fixture()
    report = build_report(fixture, render_fixture(fixture))
    mappings = report["unit_mappings"]
    assert isinstance(mappings, list)
    mappings[0].pop("owner_id")
    artifacts["broadcast_readable_report"] = report
    assert "ARTIFACT_SCHEMA_VIOLATION" in readable_gate_nine_issues(artifacts)


def historical_novelty_precheck() -> dict[str, object]:
    """Legacy Project의 정식 결과에서 당시 존재하지 않던 확장 필드만 제외한다."""
    report = make_complete_project_artifacts()["novelty_precheck"]
    assert isinstance(report, Mapping)
    document = deepcopy(dict(report))
    candidates = document["candidate_results"]
    assert isinstance(candidates, list)
    for candidate in candidates:
        assert isinstance(candidate, dict)
        candidate.pop("comparison_status")
    assert document["schema_version"] == "1.1.0"
    return document


def test_historical_novelty_precheck_remains_valid() -> None:
    """등록 당시 유효한 Novelty 1.1에 신규 필드를 소급해서 요구하지 않는다."""
    schema = load_json_object(ROOT / "STANDARD/schemas/novelty_precheck.schema.json")
    assert collect_schema_errors(historical_novelty_precheck(), schema, "novelty_precheck") == []


def test_historical_novelty_still_requires_comparisons() -> None:
    """Legacy의 원래 필수 비교 배열을 제거하면 Schema가 계속 거부한다."""
    report = historical_novelty_precheck()
    candidates = report["candidate_results"]
    assert isinstance(candidates, list)
    candidates[0].pop("comparisons")
    schema = load_json_object(ROOT / "STANDARD/schemas/novelty_precheck.schema.json")
    errors = collect_schema_errors(report, schema, "novelty_precheck")
    assert any(error["message"] == "'comparisons' is a required property" for error in errors)


@pytest.mark.parametrize("report_version", ["1.1.0", "1.2.0"])
def test_current_novelty_builders_remain_valid(report_version: str) -> None:
    """현재 Builder의 Legacy·신규 Version 출력은 각각의 Schema를 통과한다."""
    report = (
        make_complete_project_artifacts()["novelty_precheck"]
        if report_version == "1.1.0"
        else load_json_object(PILOT_ROOT / "08_QA/novelty_precheck.json")
    )
    assert isinstance(report, Mapping)
    assert report["schema_version"] == report_version
    schema = load_json_object(ROOT / "STANDARD/schemas/novelty_precheck.schema.json")
    assert collect_schema_errors(report, schema, "novelty_precheck") == []


@pytest.mark.parametrize(
    "field", ["comparison_status", "candidate_event_briefs_hash", "candidate_event_brief_hashes"]
)
def test_current_novelty_requires_new_fields(field: str) -> None:
    """Novelty 1.2의 신규 필드는 계속 필수이며 Legacy 완화가 전파되지 않는다."""
    report = load_json_object(PILOT_ROOT / "08_QA/novelty_precheck.json")
    if field == "comparison_status":
        candidates = report["candidate_results"]
        assert isinstance(candidates, list)
        candidates[0].pop(field)
    else:
        report.pop(field)
    schema = load_json_object(ROOT / "STANDARD/schemas/novelty_precheck.schema.json")
    errors = collect_schema_errors(report, schema, "novelty_precheck")
    assert len(errors) == 1
    assert errors[0]["code"] == "SCHEMA_VALIDATION_ERROR"
    assert errors[0]["message"] == f"'{field}' is a required property"


def test_state_transition_documentation_matches_runtime_gate() -> None:
    """State Transition 문서의 표와 실행도는 Runtime의 실제 Gate를 명시한다."""
    task = load_task_catalog(ROOT)["story.design_state_transitions"]
    assert task["target_gate"] == "GATE-07"
    assert task["depends_on_tasks"] == ["scene.design"]
    graph = load_json_object(ROOT / "STANDARD/dependency_graph.json")
    definitions = graph["artifacts"]
    assert isinstance(definitions, dict)
    assert "scene_cards" in definitions["character_state_transitions"]["depends_on"]
    owning_gates = [
        gate["gate_id"]
        for gate in GATES
        if "character_state_transitions" in gate["required_artifacts"]
    ]
    assert owning_gates == [task["target_gate"]]
    document = (ROOT / "docs/02-design/llm-agent-runtime-v1.md").read_text(encoding="utf-8")
    assert "| `character_state_transitions` | Story Architect LLM | GATE-07 |" in document
    assert "GATE-06  LLM  beat_sheet / retention_plan" in document
    assert "scene_cards → character_state_transitions" in document
