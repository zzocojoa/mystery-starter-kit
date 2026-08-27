"""Project Lock, Input Drift, Write-ahead Transaction 원자성 검증."""

import os
from pathlib import Path
from typing import cast

import pytest

from RUNTIME.errors import RuntimeExecutionError
from RUNTIME.transactions import (
    acquire_project_lock,
    capture_artifact_hashes,
    commit_gate_transaction,
    recover_prepared_transactions,
    release_project_lock,
    verify_artifact_hashes,
)
from VALIDATORS.io import load_json_object, write_json_object
from VALIDATORS.models import ProjectState

from .support import ROOT, create_runtime_project, create_runtime_repository


def test_project_lock_allows_only_one_writer(tmp_path: Path) -> None:
    """동일 Project에 두 Runtime Writer가 동시에 Lock을 획득할 수 없다."""
    repository_root = create_runtime_repository(tmp_path)
    project_path = create_runtime_project(repository_root, "PRJ-930")
    lock_path = acquire_project_lock(project_path, "RUN-ONE")
    try:
        with pytest.raises(RuntimeExecutionError) as error_info:
            acquire_project_lock(project_path, "RUN-TWO")
    finally:
        release_project_lock(lock_path, "RUN-ONE")

    assert error_info.value.code == "PROJECT_LOCKED"


def test_stale_project_lock_is_reclaimed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """종료된 Process가 남긴 Lock은 다음 Run이 안전하게 회수한다."""
    repository_root = create_runtime_repository(tmp_path)
    project_path = create_runtime_project(repository_root, "PRJ-933")
    stale_lock = project_path / ".runtime" / "locks" / "project.lock"
    write_json_object(
        stale_lock,
        {"run_id": "RUN-STALE", "pid": 999999, "acquired_at": "2026-08-27T00:00:00Z"},
    )

    def missing_process(pid: int, signal: int) -> None:
        assert pid == 999999
        assert signal == 0
        raise ProcessLookupError

    monkeypatch.setattr("RUNTIME.transactions.os.kill", missing_process)
    acquired = acquire_project_lock(project_path, "RUN-RECOVERY")
    try:
        assert load_json_object(acquired)["run_id"] == "RUN-RECOVERY"
    finally:
        release_project_lock(acquired, "RUN-RECOVERY")


def test_input_hash_drift_blocks_commit_boundary(tmp_path: Path) -> None:
    """Provider 실행 중 Canonical 입력이 바뀌면 Input Hash 검증이 실패한다."""
    repository_root = create_runtime_repository(tmp_path)
    project_path = create_runtime_project(repository_root, "PRJ-931")
    dependency_graph = load_json_object(ROOT / "STANDARD" / "dependency_graph.json")
    captured = capture_artifact_hashes(
        project_path,
        ["production_config"],
        dependency_graph,
    )
    config_path = project_path / "00_PROJECT" / "production_config.json"
    config = load_json_object(config_path)
    config["target_runtime_minutes"] = 30
    write_json_object(config_path, config)

    with pytest.raises(RuntimeExecutionError) as error_info:
        verify_artifact_hashes(project_path, captured, dependency_graph)

    assert error_info.value.code == "INPUT_HASH_CHANGED"


def test_transaction_failure_restores_every_canonical_target(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """중간 Replace 실패 시 먼저 바뀐 Artifact와 Project State를 모두 복구한다."""
    repository_root = create_runtime_repository(tmp_path)
    project_path = create_runtime_project(repository_root, "PRJ-932")
    dependency_graph = load_json_object(ROOT / "STANDARD" / "dependency_graph.json")
    report_path = project_path / "00_PROJECT" / "compatibility_report.json"
    state_path = project_path / "00_PROJECT" / "project_state.json"
    report_before = report_path.read_bytes()
    state_before = state_path.read_bytes()
    original_replace = os.replace
    calls = 0

    def fail_second_replace(source: Path, target: Path) -> None:
        nonlocal calls
        calls += 1
        if calls == 2:
            raise OSError("의도한 두 번째 Replace 실패")
        original_replace(source, target)

    monkeypatch.setattr("RUNTIME.transactions.os.replace", fail_second_replace)

    with pytest.raises(RuntimeExecutionError) as error_info:
        commit_gate_transaction(
            project_path,
            "RUN-ROLLBACK",
            "GATE-00",
            project_path,
            {
                "compatibility_report": {
                    "project_id": "PRJ-932",
                    "compatibility": "PASS",
                    "errors": [],
                }
            },
            dependency_graph,
            cast(ProjectState, load_json_object(state_path)),
            {},
        )

    assert error_info.value.code == "TRANSACTION_ERROR"
    assert report_path.read_bytes() == report_before
    assert state_path.read_bytes() == state_before
    records = sorted((project_path / ".runtime" / "transactions").glob("*/transaction.json"))
    assert len(records) == 1
    assert load_json_object(records[0])["status"] == "ROLLED_BACK"


def test_transaction_failure_removes_new_canonical_target(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """신규 Artifact 반영 뒤 실패하면 원래 없던 Canonical 파일을 제거한다."""
    repository_root = create_runtime_repository(tmp_path)
    project_path = create_runtime_project(repository_root, "PRJ-933")
    dependency_graph = load_json_object(ROOT / "STANDARD" / "dependency_graph.json")
    panel_path = project_path / "06_SCENE" / "panel_cast.json"
    panel_path.unlink()
    original_replace = os.replace
    calls = 0

    def fail_second_replace(source: Path, target: Path) -> None:
        nonlocal calls
        calls += 1
        if calls == 2:
            raise OSError("의도한 두 번째 Replace 실패")
        original_replace(source, target)

    monkeypatch.setattr("RUNTIME.transactions.os.replace", fail_second_replace)

    with pytest.raises(RuntimeExecutionError) as error_info:
        commit_gate_transaction(
            project_path,
            "RUN-NEW-ROLLBACK",
            "GATE-07",
            project_path,
            {
                "panel_cast": {
                    "schema_family": "panel-cast",
                    "schema_version": "2.0.0",
                    "project_id": "PRJ-933",
                    "panelists": [],
                }
            },
            dependency_graph,
            cast(
                ProjectState,
                load_json_object(project_path / "00_PROJECT" / "project_state.json"),
            ),
            {},
        )

    assert error_info.value.code == "TRANSACTION_ERROR"
    assert not panel_path.exists()
    records = sorted((project_path / ".runtime" / "transactions").glob("*/transaction.json"))
    assert len(records) == 1
    record = load_json_object(records[0])
    assert record["status"] == "ROLLED_BACK"
    targets = record["targets"]
    assert isinstance(targets, list)
    assert targets[0]["existed_before"] is False
    assert targets[0]["backup_path"] is None


def test_prepared_transaction_is_recovered_after_crash(tmp_path: Path) -> None:
    """Commit 완료 표시 전 중단된 Transaction은 다음 Run에서 백업으로 복구한다."""
    repository_root = create_runtime_repository(tmp_path)
    project_path = create_runtime_project(repository_root, "PRJ-934")
    dependency_graph = load_json_object(ROOT / "STANDARD" / "dependency_graph.json")
    report_path = project_path / "00_PROJECT" / "compatibility_report.json"
    report_before = report_path.read_bytes()
    transaction_id = commit_gate_transaction(
        project_path,
        "RUN-CRASH",
        "GATE-00",
        project_path,
        {
            "compatibility_report": {
                "project_id": "PRJ-934",
                "compatibility": "PASS",
                "errors": [],
            }
        },
        dependency_graph,
        cast(
            ProjectState,
            load_json_object(project_path / "00_PROJECT" / "project_state.json"),
        ),
        {},
    )
    record_path = (
        project_path / ".runtime" / "transactions" / transaction_id / "transaction.json"
    )
    record = load_json_object(record_path)
    record["status"] = "PREPARED"
    record["committed_at"] = None
    write_json_object(record_path, record)

    recovered = recover_prepared_transactions(project_path)

    assert recovered == [transaction_id]
    assert report_path.read_bytes() == report_before
    assert load_json_object(record_path)["status"] == "ROLLED_BACK"


def test_recovery_rejects_transaction_target_outside_project(tmp_path: Path) -> None:
    """변조된 Transaction 기록은 Project 밖 파일을 복구할 수 없다."""
    repository_root = create_runtime_repository(tmp_path)
    project_path = create_runtime_project(repository_root, "PRJ-935")
    transaction_id = "TX-UNTRUSTED"
    transaction_path = project_path / ".runtime" / "transactions" / transaction_id
    backup_path = transaction_path / "backups" / "000-outside.txt"
    outside_path = tmp_path / "outside.txt"
    outside_path.write_text("보존", encoding="utf-8")
    backup_path.parent.mkdir(parents=True)
    backup_path.write_text("변조", encoding="utf-8")
    write_json_object(
        transaction_path / "transaction.json",
        {
            "transaction_id": transaction_id,
            "status": "PREPARED",
            "targets": [
                {
                    "target_path": str(outside_path),
                    "backup_path": str(backup_path),
                }
            ],
        },
    )

    with pytest.raises(RuntimeExecutionError) as error_info:
        recover_prepared_transactions(project_path)

    assert error_info.value.code == "TRANSACTION_ERROR"
    assert outside_path.read_text(encoding="utf-8") == "보존"
