"""Codex App Gate Transaction Protocol의 권한, 원자성, 준비 상태 검증."""

import asyncio
import shutil
from collections.abc import Mapping
from pathlib import Path

import pytest
from runtime.support import create_runtime_project, create_runtime_repository

from RUNTIME.engine import execute_run
from VALIDATORS.exceptions import GateTransactionError
from VALIDATORS.gate_transaction import (
    audit_project,
    process_conformance,
    return_task_to_owner,
    task_abort,
    task_open,
    task_submit,
    trace_records,
)
from VALIDATORS.io import load_json_object, write_json_object
from VALIDATORS.production_cli import run_cli

OPENED_AT = "2026-08-28T00:00:00Z"
COMPLETED_AT = "2026-08-28T00:01:00Z"


def prepare_gate_five_projects(
    tmp_path: Path,
) -> tuple[Path, Path, Path]:
    """GATE-05 직전 Canonical Project와 검증 완료 출력 원본을 만든다."""
    repository_root = create_runtime_repository(tmp_path)
    project_path = create_runtime_project(repository_root, "PRJ-960")
    asyncio.run(
        execute_run(
            repository_root,
            project_path,
            "GATE-00",
            "GATE-04",
            "default",
            None,
            None,
        )
    )
    golden_path = repository_root / "PROJECTS" / "PRJ-960-GOLDEN"
    shutil.copytree(project_path, golden_path)
    asyncio.run(
        execute_run(
            repository_root,
            golden_path,
            "GATE-05",
            "GATE-05",
            "default",
            None,
            None,
        )
    )
    return repository_root, project_path, golden_path


def copy_allowed_outputs(
    repository_root: Path,
    golden_path: Path,
    record: Mapping[str, object],
) -> Path:
    """검증 완료 원본에서 현재 Task Allowlist 출력만 Workspace로 복사한다."""
    raw_workspace = record.get("workspace")
    raw_allowed_writes = record.get("allowed_writes")
    if not isinstance(raw_workspace, str) or not isinstance(raw_allowed_writes, list):
        raise AssertionError("Gate Task 기록에 Workspace 또는 writes가 없습니다.")
    graph = load_json_object(repository_root / "STANDARD" / "dependency_graph.json")
    definitions = graph.get("artifacts")
    if not isinstance(definitions, Mapping):
        raise AssertionError("Dependency Graph artifacts 객체가 없습니다.")
    workspace = Path(raw_workspace)
    for artifact_name in raw_allowed_writes:
        if not isinstance(artifact_name, str):
            raise AssertionError("Task writes 항목은 문자열이어야 합니다.")
        definition = definitions.get(artifact_name)
        if not isinstance(definition, Mapping):
            raise AssertionError(f"Artifact 정의가 없습니다: artifact={artifact_name}")
        relative_path = definition.get("path")
        if not isinstance(relative_path, str):
            raise AssertionError(f"Artifact 경로가 없습니다: artifact={artifact_name}")
        shutil.copy2(golden_path / relative_path, workspace / relative_path)
    return workspace


def assert_error_code(error_info: pytest.ExceptionInfo[GateTransactionError], code: str) -> None:
    """Gate Transaction 오류 Code를 명확히 검증한다."""
    assert error_info.value.code == code
    assert code in str(error_info.value)


def test_gate_transaction_rejects_out_of_scope_changes_and_commits_atomically(
    tmp_path: Path,
) -> None:
    """Future·권한 밖·입력 Drift를 차단하고 성공 Bundle만 원자 Commit한다."""
    repository_root, project_path, golden_path = prepare_gate_five_projects(tmp_path)
    state_path = project_path / "00_PROJECT" / "project_state.json"
    timeline_path = project_path / "03_TIMELINE" / "actual_timeline.json"
    state_before = state_path.read_bytes()
    timeline_before = timeline_path.read_bytes()

    with pytest.raises(GateTransactionError) as not_open:
        task_submit(
            repository_root,
            project_path,
            "GATE-05",
            COMPLETED_AT,
            None,
        )
    assert_error_code(not_open, "GATE_TRANSACTION_NOT_OPEN")

    future_record = task_open(
        repository_root,
        project_path,
        "GATE-05",
        OPENED_AT,
    )
    future_workspace = Path(str(future_record["workspace"]))
    (future_workspace / "07_SCRIPT" / "final_script.md").write_text(
        "Future Gate 직접 수정",
        encoding="utf-8",
    )
    with pytest.raises(GateTransactionError) as future_error:
        task_submit(
            repository_root,
            project_path,
            "GATE-05",
            COMPLETED_AT,
            None,
        )
    assert_error_code(future_error, "FUTURE_GATE_ARTIFACT_MODIFIED")
    task_abort(repository_root, project_path, "GATE-05", COMPLETED_AT)
    assert state_path.read_bytes() == state_before
    assert timeline_path.read_bytes() == timeline_before

    unauthorized_record = task_open(
        repository_root,
        project_path,
        "GATE-05",
        OPENED_AT,
    )
    unauthorized_workspace = Path(str(unauthorized_record["workspace"]))
    (unauthorized_workspace / "task-note.txt").write_text("권한 밖", encoding="utf-8")
    with pytest.raises(GateTransactionError) as unauthorized_error:
        task_submit(
            repository_root,
            project_path,
            "GATE-05",
            COMPLETED_AT,
            None,
        )
    assert_error_code(unauthorized_error, "UNAUTHORIZED_TASK_WRITE")
    task_abort(repository_root, project_path, "GATE-05", COMPLETED_AT)

    task_open(
        repository_root,
        project_path,
        "GATE-05",
        OPENED_AT,
    )
    facts_path = project_path / "01_CASE" / "facts.json"
    facts_before = facts_path.read_bytes()
    facts = load_json_object(facts_path)
    facts["drift_probe"] = True
    write_json_object(facts_path, facts)
    with pytest.raises(GateTransactionError) as drift_error:
        task_submit(
            repository_root,
            project_path,
            "GATE-05",
            COMPLETED_AT,
            None,
        )
    assert_error_code(drift_error, "GATE_TRANSACTION_INPUT_DRIFT")
    facts_path.write_bytes(facts_before)
    task_abort(repository_root, project_path, "GATE-05", COMPLETED_AT)

    trace_path = project_path / "00_PROJECT" / "process_trace.jsonl"
    traces_before = trace_path.read_bytes()
    trace_path.write_text("", encoding="utf-8")
    missing_trace_record = task_open(
        repository_root,
        project_path,
        "GATE-05",
        OPENED_AT,
    )
    copy_allowed_outputs(repository_root, golden_path, missing_trace_record)
    with pytest.raises(GateTransactionError) as missing_trace_error:
        task_submit(
            repository_root,
            project_path,
            "GATE-05",
            COMPLETED_AT,
            None,
        )
    assert_error_code(missing_trace_error, "PROCESS_TRACE_MISSING")
    task_abort(repository_root, project_path, "GATE-05", COMPLETED_AT)
    trace_path.write_bytes(traces_before)

    committed_record = task_open(
        repository_root,
        project_path,
        "GATE-05",
        OPENED_AT,
    )
    copy_allowed_outputs(repository_root, golden_path, committed_record)
    result = task_submit(
        repository_root,
        project_path,
        "GATE-05",
        COMPLETED_AT,
        None,
    )
    state = load_json_object(state_path)

    assert result["status"] == "COMMITTED"
    assert state["current_gate"] == "GATE-05"
    assert state["state"] == "MYSTERY_DESIGNED"
    assert timeline_path.read_bytes() == (
        golden_path / "03_TIMELINE" / "actual_timeline.json"
    ).read_bytes()
    assert any(
        trace["gate_id"] == "GATE-05"
        for trace in trace_records(repository_root, project_path)
    )

    with pytest.raises(GateTransactionError) as already_committed:
        task_submit(
            repository_root,
            project_path,
            "GATE-05",
            COMPLETED_AT,
            None,
        )
    assert_error_code(already_committed, "GATE_TRANSACTION_ALREADY_COMMITTED")


def test_audit_is_state_preserving_and_human_approval_is_separate(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Audit, Process Trace, Editorial 승인, Production 전이를 독립 조건으로 유지한다."""
    repository_root = create_runtime_repository(tmp_path)
    project_path = create_runtime_project(repository_root, "PRJ-961")
    asyncio.run(
        execute_run(
            repository_root,
            project_path,
            "GATE-00",
            "GATE-13",
            "default",
            None,
            None,
        )
    )
    state_path = project_path / "00_PROJECT" / "project_state.json"
    state_before = state_path.read_bytes()
    report = audit_project(
        repository_root,
        project_path,
        None,
        None,
        "2026-08-28T00:02:00Z",
    )

    assert report["result"] == "PASS"
    assert report["process_conformant"] is True
    assert report["production_ready"] is False
    assert state_path.read_bytes() == state_before
    state = load_json_object(state_path)
    assert state["state"] == "EDITORIAL_REVIEW_REQUIRED"

    assert run_cli(["production-finalize", str(project_path)]) == 2
    assert "Editorial Approved" in capsys.readouterr().err
    assert run_cli(
        [
            "editorial-approve",
            str(project_path),
            "--actor",
            "human-editor",
            "--reason",
            "방송 적합성 검토 완료",
        ]
    ) == 0
    assert run_cli(["production-finalize", str(project_path)]) == 0
    finalized = load_json_object(state_path)
    assert finalized["state"] == "PRODUCTION_READY"


def test_missing_process_trace_blocks_production_ready(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Process Trace가 없으면 Editorial 상태와 무관하게 Production Ready를 차단한다."""
    repository_root = create_runtime_repository(tmp_path)
    project_path = create_runtime_project(repository_root, "PRJ-962")
    state_path = project_path / "00_PROJECT" / "project_state.json"
    state = load_json_object(state_path)
    state["state"] = "EDITORIAL_APPROVED"
    state["current_gate"] = "GATE-13"
    state["readiness"] = {
        "artifact_status": "ARTIFACT_COMPLETE",
        "contract_status": "CONTRACT_VALIDATED",
        "process_status": "PROCESS_CONFORMANT",
        "editorial_status": "EDITORIAL_APPROVED",
        "process_start_gate": "GATE-00",
        "process_revision": 1,
    }
    write_json_object(state_path, state)

    assert run_cli(["production-finalize", str(project_path)]) == 2
    assert "PROCESS_TRACE_MISSING" in capsys.readouterr().err
    assert load_json_object(state_path)["state"] == "EDITORIAL_APPROVED"


def test_gate_transaction_cli_opens_reports_and_aborts(tmp_path: Path) -> None:
    """필수 Codex Gate CLI가 동일 OPEN Task를 조회하고 안전하게 중단한다."""
    projects_root = tmp_path / "projects"
    assert run_cli(
        [
            "init",
            "PRJ-963",
            "--projects-root",
            str(projects_root),
            "--created-at",
            OPENED_AT,
        ]
    ) == 0
    project_path = projects_root / "PRJ-963"
    state_path = project_path / "00_PROJECT" / "project_state.json"
    state_before = state_path.read_bytes()

    assert run_cli(["task-open", str(project_path), "GATE-00"]) == 0
    assert run_cli(["task-status", str(project_path)]) == 0
    assert run_cli(["task-abort", str(project_path), "GATE-00"]) == 0
    assert state_path.read_bytes() == state_before


def test_core_outputs_are_generated_by_runtime_and_not_editable_by_codex(
    tmp_path: Path,
) -> None:
    """Codex writes에서 CORE 출력을 제외하고 제출 시 결정론적으로 생성한다."""
    repository_root = create_runtime_repository(tmp_path)
    project_path = create_runtime_project(repository_root, "PRJ-964")
    compatibility_path = project_path / "00_PROJECT" / "compatibility_report.json"

    rejected_record = task_open(
        repository_root,
        project_path,
        "GATE-00",
        OPENED_AT,
    )
    assert rejected_record["allowed_writes"] == []
    rejected_workspace = Path(str(rejected_record["workspace"]))
    rejected_report = load_json_object(
        rejected_workspace / "00_PROJECT" / "compatibility_report.json"
    )
    rejected_report["compatibility"] = "PASS"
    write_json_object(
        rejected_workspace / "00_PROJECT" / "compatibility_report.json",
        rejected_report,
    )
    with pytest.raises(GateTransactionError) as unauthorized_error:
        task_submit(
            repository_root,
            project_path,
            "GATE-00",
            COMPLETED_AT,
            None,
        )
    assert_error_code(unauthorized_error, "UNAUTHORIZED_TASK_WRITE")
    task_abort(repository_root, project_path, "GATE-00", COMPLETED_AT)

    accepted_record = task_open(
        repository_root,
        project_path,
        "GATE-00",
        OPENED_AT,
    )
    assert accepted_record["allowed_writes"] == []
    result = task_submit(
        repository_root,
        project_path,
        "GATE-00",
        COMPLETED_AT,
        None,
    )

    assert result["status"] == "COMMITTED"
    assert result["current_gate"] == "GATE-00"
    assert load_json_object(compatibility_path)["compatibility"] == "PASS"
    assert trace_records(repository_root, project_path)[0]["changed_paths"] == [
        "00_PROJECT/compatibility_report.json"
    ]


def test_current_gate_submit_does_not_require_missing_future_artifacts(
    tmp_path: Path,
) -> None:
    """Migration Project의 아직 생성되지 않은 미래 Artifact가 현재 Gate를 막지 않는다."""
    repository_root, project_path, golden_path = prepare_gate_five_projects(tmp_path)
    for relative_path in (
        "06_SCENE/panel_cast.json",
        "06_SCENE/reaction_segments.json",
        "07_SCRIPT/drama_script.md",
        "07_SCRIPT/narration_script.md",
        "07_SCRIPT/panel_reaction_script.md",
        "09_PRODUCTION/panel_reaction_script.md",
    ):
        path = project_path / relative_path
        if path.exists():
            path.unlink()

    record = task_open(
        repository_root,
        project_path,
        "GATE-05",
        OPENED_AT,
    )
    copy_allowed_outputs(repository_root, golden_path, record)
    result = task_submit(
        repository_root,
        project_path,
        "GATE-05",
        COMPLETED_AT,
        None,
    )

    assert result["status"] == "COMMITTED"
    assert result["current_gate"] == "GATE-05"


def test_task_open_excludes_same_gate_outputs_from_input_hashes(
    tmp_path: Path,
) -> None:
    """같은 Gate의 선행 Task 출력은 Canonical 입력 Hash를 요구하지 않는다."""
    repository_root = create_runtime_repository(tmp_path)
    project_path = create_runtime_project(repository_root, "PRJ-965")
    asyncio.run(
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
    for relative_path in (
        "07_SCRIPT/drama_script.md",
        "07_SCRIPT/narration_script.md",
        "07_SCRIPT/panel_reaction_script.md",
    ):
        path = project_path / relative_path
        if path.exists():
            path.unlink()

    record = task_open(
        repository_root,
        project_path,
        "GATE-08",
        OPENED_AT,
    )

    input_hashes = record["input_hashes"]
    assert isinstance(input_hashes, Mapping)
    assert "drama_script" not in input_hashes
    assert "narration_script" not in input_hashes
    assert "panel_reaction_script" not in input_hashes
    assert "scene_cards" in input_hashes
    assert record["allowed_writes"] == [
        "draft_script",
        "drama_script",
        "final_script",
        "narration_script",
        "panel_reaction_script",
    ]


def test_task_open_and_audit_reject_preexisting_canonical_drift(
    tmp_path: Path,
) -> None:
    """Task Open 전 직접 변경도 State Hash와 대조해 차단하고 Audit에 보고한다."""
    repository_root, project_path, _golden_path = prepare_gate_five_projects(tmp_path)
    facts_path = project_path / "01_CASE" / "facts.json"
    original = facts_path.read_bytes()
    facts_path.write_bytes(original + b"\n")

    with pytest.raises(GateTransactionError) as open_error:
        task_open(repository_root, project_path, "GATE-05", OPENED_AT)

    assert_error_code(open_error, "GATE_TRANSACTION_INPUT_DRIFT")
    facts_path.write_bytes(original)
    asyncio.run(
        execute_run(
            repository_root,
            project_path,
            "GATE-05",
            "GATE-13",
            "default",
            None,
            None,
        )
    )
    final_path = project_path / "07_SCRIPT" / "final_script.md"
    final_path.write_bytes(final_path.read_bytes() + b"\n")
    state_path = project_path / "00_PROJECT" / "project_state.json"
    state_before = state_path.read_bytes()

    report = audit_project(
        repository_root,
        project_path,
        None,
        None,
        "2026-08-28T00:03:00Z",
    )

    assert report["result"] == "FAIL"
    assert report["process_conformant"] is False
    process_issues = report["process_issues"]
    assert isinstance(process_issues, list)
    assert any(
        issue["code"] == "CANONICAL_ARTIFACT_DRIFT"
        for issue in process_issues
        if isinstance(issue, Mapping)
    )
    assert state_path.read_bytes() == state_before


def test_critic_issue_returns_to_owner_in_new_process_revision(
    tmp_path: Path,
) -> None:
    """Owner 반환은 과거 Trace를 보존하고 새 Revision에서 해당 Gate부터 재실행한다."""
    repository_root = create_runtime_repository(tmp_path)
    project_path = create_runtime_project(repository_root, "PRJ-966")
    asyncio.run(
        execute_run(
            repository_root,
            project_path,
            "GATE-00",
            "GATE-13",
            "default",
            None,
            None,
        )
    )

    result = return_task_to_owner(
        repository_root,
        project_path,
        "script_writer",
        "critic-reviewer",
        "Editorial Issue를 Script Writer가 수정해야 함",
        "2026-08-28T00:04:00Z",
    )
    state = load_json_object(project_path / "00_PROJECT" / "project_state.json")
    traces = trace_records(repository_root, project_path)
    conformant, missing = process_conformance(traces, "GATE-08", "GATE-13", 2)
    readiness = state["readiness"]
    artifacts = state["artifacts"]
    assert isinstance(readiness, Mapping)
    assert isinstance(artifacts, Mapping)
    final_script_state = artifacts["final_script"]
    assert isinstance(final_script_state, Mapping)

    assert result["target_gate"] == "GATE-08"
    assert state["current_gate"] == "GATE-07"
    assert readiness["process_start_gate"] == "GATE-08"
    assert readiness["process_revision"] == 2
    assert final_script_state["status"] == "DIRTY"
    assert conformant is False
    assert missing == [
        "GATE-08",
        "GATE-09",
        "GATE-10",
        "GATE-11",
        "GATE-12",
        "GATE-13",
    ]

    record = task_open(repository_root, project_path, "GATE-08", OPENED_AT)
    assert record["agent_ids"] == ["script_writer"]
    assert record["process_revision"] == 2

    assert run_cli(
        [
            "task-return",
            str(project_path),
            "script_writer",
            "--actor",
            "critic-reviewer",
            "--reason",
            "열린 재작업에서도 추가 수정이 필요함",
        ]
    ) == 0
    task_record = load_json_object(
        project_path
        / ".runtime"
        / "codex_tasks"
        / str(record["transaction_id"])
        / "task.json"
    )
    returned_state = load_json_object(
        project_path / "00_PROJECT" / "project_state.json"
    )
    returned_readiness = returned_state["readiness"]
    assert isinstance(returned_readiness, Mapping)
    assert task_record["status"] == "ABORTED"
    assert returned_readiness["process_revision"] == 3


def test_canonical_drift_blocks_finalize_and_registration(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """승인 뒤 정본이 바뀌면 Production 확정과 Library 등록을 모두 차단한다."""
    repository_root = create_runtime_repository(tmp_path)
    project_path = create_runtime_project(repository_root, "PRJ-967")
    asyncio.run(
        execute_run(
            repository_root,
            project_path,
            "GATE-00",
            "GATE-13",
            "default",
            None,
            None,
        )
    )
    assert run_cli(
        [
            "editorial-approve",
            str(project_path),
            "--actor",
            "human-editor",
            "--reason",
            "방송 적합성 검토 완료",
        ]
    ) == 0
    capsys.readouterr()
    final_path = project_path / "07_SCRIPT" / "final_script.md"
    original = final_path.read_bytes()
    final_path.write_bytes(original + b"\n")

    assert run_cli(["production-finalize", str(project_path)]) == 2
    assert "CANONICAL_ARTIFACT_DRIFT" in capsys.readouterr().err
    assert load_json_object(project_path / "00_PROJECT" / "project_state.json")["state"] == (
        "EDITORIAL_APPROVED"
    )

    final_path.write_bytes(original)
    assert run_cli(["production-finalize", str(project_path)]) == 0
    capsys.readouterr()
    final_path.write_bytes(original + b"\n")
    library_path = tmp_path / "story_fingerprints.json"
    history_path = tmp_path / "story_history.jsonl"
    write_json_object(
        library_path,
        {
            "schema_family": "story-library",
            "schema_version": "1.0.0",
            "fingerprints": [],
        },
    )

    assert run_cli(
        [
            "register",
            str(project_path),
            "--library",
            str(library_path),
            "--history",
            str(history_path),
        ]
    ) == 2
    assert "CANONICAL_ARTIFACT_DRIFT" in capsys.readouterr().err
    assert load_json_object(library_path)["fingerprints"] == []
    assert not history_path.exists()
