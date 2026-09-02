"""Broadcast Readable v2 Runtime Task·Packaging·Trace 통합을 검증한다."""

from copy import deepcopy
from hashlib import sha256
from pathlib import Path
from shutil import copytree

import pytest
from test_broadcast_readable_v2_validation import (
    PilotFixture,
    pilot_fixture,
)

from RUNTIME.contracts import load_artifact_contracts, load_task_catalog
from RUNTIME.core_tasks import (
    core_task_outputs,
    runtime_validation_inputs_for_project,
    story_history,
)
from RUNTIME.errors import RuntimeExecutionError
from RUNTIME.gate_control import validation_report_through
from RUNTIME.output_gateway import validate_artifact_content, validate_core_outputs
from RUNTIME.planner import task_condition_matches
from VALIDATORS.broadcast_readable import production_readable_deliverable_issues
from VALIDATORS.candidate_evaluation import document_sha256
from VALIDATORS.editorial import editorial_artifact_hashes
from VALIDATORS.gate_transaction import task_artifact_hashes
from VALIDATORS.io import load_json_object, write_json_object
from VALIDATORS.pipeline import (
    load_existing_project_artifacts,
    run_production_validation,
)

ROOT = Path(__file__).resolve().parents[1]
PILOT_ROOT = ROOT / "PROJECTS/PRJ-006"
PROFILE_PATH = (
    ROOT
    / "CHANNELS/mystery_main/output_profiles/broadcast-readable-script/2.0.0.json"
)
V1_READABLE_SHA256 = "a823e34f69132c857d6eea6a93b9842dd5f40add50edfe6409b1a2f6c4fbe2fa"


def task_outputs(
    task_id: str,
    overlay: dict[str, object],
) -> dict[str, object]:
    """PRJ-006에서 지정 CORE Task의 Staging 출력만 반환한다."""
    return project_task_outputs(task_id, PILOT_ROOT, overlay)


def project_task_outputs(
    task_id: str,
    project_path: Path,
    overlay: dict[str, object],
) -> dict[str, object]:
    """지정 Project에서 CORE Task의 Staging 출력만 반환한다."""
    return core_task_outputs(
        task_id,
        ROOT,
        project_path,
        overlay,
        load_json_object(ROOT / "STANDARD/dependency_graph.json"),
        None,
        None,
        "RUNTIME-V2-TEST",
        {},
    )


def v2_runtime_overlay(fixture: PilotFixture) -> dict[str, object]:
    """v2 전용 Config를 가진 Runtime Overlay를 반환한다."""
    return {"broadcast_readable_config": fixture["config"]}


def generated_v2_chain(
    fixture: PilotFixture,
) -> tuple[str, dict[str, object], str, dict[str, object]]:
    """GATE-08·09·13 CORE 산출물과 Manifest를 순서대로 생성한다."""
    overlay = v2_runtime_overlay(fixture)
    script_outputs = task_outputs("script.render_broadcast_readable", overlay)
    readable_script = script_outputs["broadcast_readable_script"]
    assert isinstance(readable_script, str)
    overlay.update(script_outputs)
    report_outputs = task_outputs("continuity.validate_broadcast_readable", overlay)
    readable_report = report_outputs["broadcast_readable_report"]
    assert isinstance(readable_report, dict)
    overlay.update(report_outputs)
    overlay["validation_report"] = {"result": "PASS"}
    production_outputs = task_outputs(
        "production.package_broadcast_readable",
        overlay,
    )
    production_readable = production_outputs[
        "production_broadcast_readable_script"
    ]
    assert isinstance(production_readable, str)
    overlay.update(production_outputs)
    manifest_outputs = task_outputs("production.build_manifest", overlay)
    manifest = manifest_outputs["production_manifest"]
    assert isinstance(manifest, dict)
    return readable_script, readable_report, production_readable, manifest


def test_runtime_conditions_keep_v1_v2_and_inactive_paths_distinct() -> None:
    """동일 Task가 v1 호환·v2 Config·비활성 경로를 결정론적으로 선택한다."""
    task = load_task_catalog(ROOT)["script.render_broadcast_readable"]
    production_config = load_json_object(
        PILOT_ROOT / "00_PROJECT/production_config.json"
    )
    channel: dict[str, object] = {"capabilities": {}}
    assert task_condition_matches(task["condition"], production_config, channel, {})
    assert task_condition_matches(
        task["condition"],
        production_config,
        channel,
        {"broadcast_readable_config": pilot_fixture()["config"]},
    )
    disabled = deepcopy(pilot_fixture()["config"])
    disabled["enabled"] = False
    disabled.pop("profile_id")
    disabled.pop("profile_version")
    assert not task_condition_matches(
        task["condition"],
        production_config,
        channel,
        {"broadcast_readable_config": disabled},
    )
    inactive = deepcopy(production_config)
    inactive.pop("broadcast_readable_output_profile_id")
    inactive.pop("broadcast_readable_output_profile_version")
    assert not task_condition_matches(task["condition"], inactive, channel, {})


def test_v2_tasks_are_core_with_minimum_reads_and_single_writes() -> None:
    """v2는 LLM Task 없이 Config·Relationship를 최소 선택 입력으로 읽는다."""
    tasks = load_task_catalog(ROOT)
    expectations = {
        "script.render_broadcast_readable": "broadcast_readable_script",
        "continuity.validate_broadcast_readable": "broadcast_readable_report",
        "production.package_broadcast_readable": (
            "production_broadcast_readable_script"
        ),
    }
    for task_id, output_name in expectations.items():
        task = tasks[task_id]
        assert task["executor"] == "CORE"
        assert task["writes"] == [output_name]
        assert "broadcast_readable_config" in task["optional_reads"]
        assert "relationships" in task["optional_reads"]
        assert task["allowed_tools"] == []


def test_runtime_v1_dispatch_keeps_registered_output_bytes(tmp_path: Path) -> None:
    """별도 Config가 없는 기존 PRJ-006 Runtime은 v1 Byte를 그대로 생성한다."""
    project_path = tmp_path / "PRJ-006"
    copytree(PILOT_ROOT, project_path)
    (project_path / "00_PROJECT/broadcast_readable_config.json").unlink()
    outputs = project_task_outputs(
        "script.render_broadcast_readable",
        project_path,
        {},
    )
    readable = outputs["broadcast_readable_script"]
    assert isinstance(readable, str)
    assert sha256(readable.encode("utf-8")).hexdigest() == V1_READABLE_SHA256


def test_gate_08_09_13_core_chain_and_manifest_are_v2_bound() -> None:
    """v2 CORE Chain은 NEEDS_REVIEW Report와 byte-identical Copy를 Manifest에 묶는다."""
    fixture = pilot_fixture()
    final_hash_before = sha256(
        (PILOT_ROOT / "07_SCRIPT/final_script.md").read_bytes()
    ).hexdigest()
    readable, report, production_readable, manifest = generated_v2_chain(fixture)

    assert report["result"] == "NEEDS_REVIEW"
    assert report["issues"] == []
    assert production_readable == readable
    assert manifest["schema_version"] == "1.1.0"
    assert production_readable_deliverable_issues(
        manifest,
        readable,
        production_readable,
        document_sha256(report),
        "BROADCAST_READABLE_SCRIPT",
        "2.0.0",
    ) == []
    contracts = load_artifact_contracts(ROOT)
    validate_artifact_content(
        ROOT,
        "production.build_manifest",
        "production_manifest",
        "application/json",
        manifest,
        contracts["production_manifest"],
    )
    assert (
        sha256((PILOT_ROOT / "07_SCRIPT/final_script.md").read_bytes()).hexdigest()
        == final_hash_before
    )


def test_v2_pass_report_is_rejected_before_production_copy() -> None:
    """v2 Report가 PASS를 사칭하면 GATE-13 Packaging이 실패한다."""
    fixture = pilot_fixture()
    overlay = v2_runtime_overlay(fixture)
    overlay.update(task_outputs("script.render_broadcast_readable", overlay))
    overlay.update(task_outputs("continuity.validate_broadcast_readable", overlay))
    report = overlay["broadcast_readable_report"]
    assert isinstance(report, dict)
    report["result"] = "PASS"
    overlay["validation_report"] = {"result": "PASS"}

    with pytest.raises(RuntimeExecutionError) as captured:
        task_outputs("production.package_broadcast_readable", overlay)
    assert captured.value.code == "GATE_REJECTED"
    raw_codes = captured.value.safe_context["issue_codes"]
    assert isinstance(raw_codes, list)
    assert "BROADCAST_READABLE_V2_PASS_RESULT_FORBIDDEN" in raw_codes


def test_integrated_gate_08_09_12_13_validation_passes() -> None:
    """v2 파생 Chain을 포함한 통합 Gate 검증이 GATE-13까지 통과한다."""
    fixture = pilot_fixture()
    readable, report, production_readable, manifest = generated_v2_chain(fixture)
    graph = load_json_object(ROOT / "STANDARD/dependency_graph.json")
    artifacts = load_existing_project_artifacts(PILOT_ROOT, graph)
    artifacts.update(
        {
            "broadcast_readable_config": fixture["config"],
            "broadcast_readable_script": readable,
            "broadcast_readable_report": report,
            "production_broadcast_readable_script": production_readable,
            "production_manifest": manifest,
        }
    )
    editorial_review = deepcopy(artifacts["editorial_review"])
    assert isinstance(editorial_review, dict)
    editorial_review["artifact_hashes"] = editorial_artifact_hashes(artifacts)
    artifacts["editorial_review"] = editorial_review
    production_config = artifacts["production_config"]
    assert isinstance(production_config, dict)
    (
        channel,
        story_schema,
        fingerprint_schema,
        presentation_schemas,
        reference_policy,
        thresholds,
    ) = runtime_validation_inputs_for_project(
        ROOT,
        production_config,
        artifacts,
        None,
    )

    validation = validation_report_through(
        "GATE-13",
        artifacts,
        channel,
        story_schema,
        fingerprint_schema,
        presentation_schemas,
        reference_policy,
        thresholds,
        story_history(ROOT),
        None,
    )

    assert validation["result"] == "PASS"
    for gate_id in ("GATE-08", "GATE-09", "GATE-12", "GATE-13"):
        assert validation["gate_results"][gate_id] == "PASS"


def test_full_production_validation_dispatches_v2_profile() -> None:
    """전체 validate 진입점도 Gate Validator와 동일한 v2 계약을 선택한다."""
    fixture = pilot_fixture()
    readable, report, production_readable, manifest = generated_v2_chain(fixture)
    graph = load_json_object(ROOT / "STANDARD/dependency_graph.json")
    artifacts = load_existing_project_artifacts(PILOT_ROOT, graph)
    artifacts.update(
        {
            "broadcast_readable_config": fixture["config"],
            "broadcast_readable_script": readable,
            "broadcast_readable_report": report,
            "production_broadcast_readable_script": production_readable,
            "production_manifest": manifest,
        }
    )
    editorial_review = deepcopy(artifacts["editorial_review"])
    assert isinstance(editorial_review, dict)
    editorial_review["artifact_hashes"] = editorial_artifact_hashes(artifacts)
    artifacts["editorial_review"] = editorial_review
    production_config = artifacts["production_config"]
    assert isinstance(production_config, dict)
    (
        channel,
        story_schema,
        fingerprint_schema,
        presentation_schemas,
        reference_policy,
        thresholds,
    ) = runtime_validation_inputs_for_project(
        ROOT,
        production_config,
        artifacts,
        None,
    )

    validation = run_production_validation(
        artifacts,
        channel,
        story_schema,
        fingerprint_schema,
        presentation_schemas,
        reference_policy,
        thresholds,
        story_history(ROOT),
        None,
    )

    assert validation["result"] == "PASS"
    assert validation["gate_results"]["GATE-13"] == "PASS"


def test_manifest_copy_or_report_hash_mutation_fails() -> None:
    """Production Copy와 Manifest Report Hash 변이를 서로 독립적으로 탐지한다."""
    fixture = pilot_fixture()
    readable, report, production_readable, manifest = generated_v2_chain(fixture)
    copy_codes = {
        issue["code"]
        for issue in production_readable_deliverable_issues(
            manifest,
            readable,
            f"{production_readable}\n변조",
            document_sha256(report),
            "BROADCAST_READABLE_SCRIPT",
            "2.0.0",
        )
    }
    assert "PRODUCTION_BROADCAST_READABLE_COPY_MISMATCH" in copy_codes
    stale_codes = {
        issue["code"]
        for issue in production_readable_deliverable_issues(
            manifest,
            readable,
            production_readable,
            "0" * 64,
            "BROADCAST_READABLE_SCRIPT",
            "2.0.0",
        )
    }
    assert stale_codes == {"PRODUCTION_READABLE_DELIVERABLE_STALE"}


def test_output_gateway_rejects_unauthorized_v2_task_write() -> None:
    """v2 CORE Task의 단일 Write 경계를 벗어난 출력은 Gateway가 거부한다."""
    tasks = load_task_catalog(ROOT)
    task = tasks["script.render_broadcast_readable"]
    with pytest.raises(RuntimeExecutionError) as captured:
        validate_core_outputs(
            ROOT,
            "script.render_broadcast_readable",
            task,
            {"final_script": "권한 밖 출력"},
            load_artifact_contracts(ROOT),
        )
    assert captured.value.code == "UNAUTHORIZED_ARTIFACT"


def test_gate_trace_hashes_include_v2_config_and_profile(
    tmp_path: Path,
) -> None:
    """Gate Transaction 입력 Hash에 Config와 실제 Profile File Hash를 기록한다."""
    project_path = tmp_path / "PRJ-006"
    copytree(PILOT_ROOT, project_path)
    config = pilot_fixture()["config"]
    write_json_object(
        project_path / "00_PROJECT/broadcast_readable_config.json",
        config,
    )
    task = load_task_catalog(ROOT)["script.render_broadcast_readable"]
    graph = load_json_object(ROOT / "STANDARD/dependency_graph.json")
    hashes = task_artifact_hashes(ROOT, project_path, task, graph)

    assert hashes["broadcast_readable_config"] == sha256(
        (project_path / "00_PROJECT/broadcast_readable_config.json").read_bytes()
    ).hexdigest()
    assert hashes["broadcast_readable_output_profile"] == sha256(
        PROFILE_PATH.read_bytes()
    ).hexdigest()
