"""Staging Overlay, Project Lock, Write-ahead 원자 Artifact Transaction."""

import json
import os
import shutil
from collections.abc import Mapping, Sequence
from copy import deepcopy
from pathlib import Path
from uuid import uuid4

from RUNTIME.errors import RuntimeExecutionError
from RUNTIME.event_store import run_root, utc_now
from RUNTIME.output_gateway import encoded_artifact
from VALIDATORS.dependency import (
    artifact_hash,
    dependency_artifacts,
    invalidate_artifact_dependents,
    mark_artifact_clean,
)
from VALIDATORS.io import load_json_object, write_json_object
from VALIDATORS.models import ProjectState
from VALIDATORS.state_machine import advance_gate


def project_lock_path(project_path: Path) -> Path:
    """Project 단일 Writer Lock 경로를 반환한다."""
    return project_path / ".runtime" / "locks" / "project.lock"


def lock_owner_is_running(lock_path: Path) -> bool:
    """Lock 문서의 PID가 현재 실행 중인지 확인한다."""
    try:
        document: object = json.loads(lock_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise RuntimeExecutionError(
            "PROJECT_LOCKED",
            False,
            "RUN",
            "기존 Project Lock 정보를 읽을 수 없습니다.",
            None,
            None,
            {"lock_path": str(lock_path)},
        ) from error
    if not isinstance(document, Mapping):
        raise RuntimeExecutionError(
            "PROJECT_LOCKED",
            False,
            "RUN",
            "기존 Project Lock 문서가 객체가 아닙니다.",
            None,
            None,
            {"lock_path": str(lock_path)},
        )
    pid = document.get("pid")
    if not isinstance(pid, int) or isinstance(pid, bool) or pid < 1:
        raise RuntimeExecutionError(
            "PROJECT_LOCKED",
            False,
            "RUN",
            "기존 Project Lock PID가 올바르지 않습니다.",
            None,
            None,
            {"lock_path": str(lock_path), "pid": pid},
        )
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError as error:
        raise RuntimeExecutionError(
            "PROJECT_LOCKED",
            False,
            "RUN",
            "기존 Project Lock Process 상태를 확인하지 못했습니다.",
            None,
            None,
            {"lock_path": str(lock_path), "pid": pid},
        ) from error
    return True


def remove_stale_lock(lock_path: Path) -> None:
    """종료된 Process가 남긴 Lock만 Inode 확인 후 제거한다."""
    try:
        original_stat = lock_path.stat()
    except OSError as error:
        raise RuntimeExecutionError(
            "PROJECT_LOCKED",
            True,
            "RUN",
            "기존 Project Lock 상태를 읽지 못했습니다.",
            None,
            None,
            {"lock_path": str(lock_path)},
        ) from error
    if lock_owner_is_running(lock_path):
        raise RuntimeExecutionError(
            "PROJECT_LOCKED",
            True,
            "RUN",
            "다른 Runtime Run이 Project Lock을 보유하고 있습니다.",
            None,
            None,
            {"lock_path": str(lock_path)},
        )
    try:
        current_stat = lock_path.stat()
        if (current_stat.st_dev, current_stat.st_ino) != (
            original_stat.st_dev,
            original_stat.st_ino,
        ):
            raise RuntimeExecutionError(
                "PROJECT_LOCKED",
                True,
                "RUN",
                "Project Lock 소유자가 확인 중 변경되었습니다.",
                None,
                None,
                {"lock_path": str(lock_path)},
            )
        lock_path.unlink()
    except RuntimeExecutionError:
        raise
    except OSError as error:
        raise RuntimeExecutionError(
            "PROJECT_LOCKED",
            True,
            "RUN",
            "종료된 Process의 Project Lock을 제거하지 못했습니다.",
            None,
            None,
            {"lock_path": str(lock_path)},
        ) from error


def acquire_project_lock(project_path: Path, run_id: str) -> Path:
    """원자적 Exclusive Create로 Project Writer Lock을 획득한다."""
    path = project_lock_path(project_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor: int | None = None
    for acquisition_attempt in range(2):
        try:
            descriptor = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
            break
        except FileExistsError as error:
            if acquisition_attempt == 1:
                raise RuntimeExecutionError(
                    "PROJECT_LOCKED",
                    True,
                    "RUN",
                    "다른 Runtime Run이 Project Lock을 보유하고 있습니다.",
                    None,
                    None,
                    {"lock_path": str(path)},
                ) from error
            remove_stale_lock(path)
    if descriptor is None:
        raise RuntimeExecutionError(
            "PROJECT_LOCKED",
            True,
            "RUN",
            "Project Lock 획득 상태가 손상되었습니다.",
            None,
            None,
            {"lock_path": str(path)},
        )
    try:
        payload = json.dumps({"run_id": run_id, "pid": os.getpid(), "acquired_at": utc_now()})
        os.write(descriptor, payload.encode("utf-8"))
    finally:
        os.close(descriptor)
    return path


def release_project_lock(lock_path: Path, run_id: str) -> None:
    """현재 Run이 소유한 Project Lock만 해제한다."""
    if not lock_path.exists():
        return
    try:
        document: object = json.loads(lock_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise RuntimeExecutionError(
            "PROJECT_LOCKED",
            False,
            "RUN",
            "Project Lock 소유권을 확인할 수 없습니다.",
            None,
            None,
            {"lock_path": str(lock_path)},
        ) from error
    if not isinstance(document, Mapping) or document.get("run_id") != run_id:
        raise RuntimeExecutionError(
            "PROJECT_LOCKED",
            False,
            "RUN",
            "다른 Run이 소유한 Project Lock은 해제할 수 없습니다.",
            None,
            None,
            {"lock_path": str(lock_path)},
        )
    try:
        lock_path.unlink()
    except OSError as error:
        raise RuntimeExecutionError(
            "PROJECT_LOCKED",
            False,
            "RUN",
            "Project Lock 해제에 실패했습니다.",
            None,
            None,
            {"lock_path": str(lock_path)},
        ) from error


def ignore_runtime_directory(directory: str, names: list[str]) -> set[str]:
    """Project Overlay 복제 시 Runtime 운영 디렉터리를 제외한다."""
    del directory
    return {".runtime"} if ".runtime" in names else set()


def write_artifact(path: Path, content: object) -> None:
    """Staging Artifact를 JSON 객체 또는 UTF-8 Text로 기록한다."""
    if path.suffix == ".json":
        if not isinstance(content, Mapping):
            raise RuntimeExecutionError(
                "TRANSACTION_ERROR",
                False,
                "TRANSACTION",
                "JSON Staging Artifact Content가 객체가 아닙니다.",
                None,
                None,
                {"path": str(path)},
            )
        write_json_object(path, content)
        return
    if not isinstance(content, str):
        raise RuntimeExecutionError(
            "TRANSACTION_ERROR",
            False,
            "TRANSACTION",
            "Text Staging Artifact Content가 문자열이 아닙니다.",
            None,
            None,
            {"path": str(path)},
        )
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
    except OSError as error:
        raise RuntimeExecutionError(
            "TRANSACTION_ERROR",
            False,
            "TRANSACTION",
            "Text Staging Artifact 기록에 실패했습니다.",
            None,
            None,
            {"path": str(path)},
        ) from error


def create_staging_overlay(
    project_path: Path,
    run_id: str,
    gate_id: str,
    semantic_attempt: int,
    outputs: Mapping[str, object],
    dependency_graph: Mapping[str, object],
) -> Path:
    """Canonical Project를 수정하지 않는 Gate Overlay를 생성한다."""
    overlay_path = (
        run_root(project_path, run_id)
        / "gates"
        / gate_id
        / f"semantic-attempt-{semantic_attempt:03d}"
        / "staged_project"
    )
    if overlay_path.exists():
        raise RuntimeExecutionError(
            "TRANSACTION_ERROR",
            False,
            "TRANSACTION",
            "동일한 Staging Overlay가 이미 존재합니다.",
            None,
            None,
            {"path": str(overlay_path)},
        )
    try:
        shutil.copytree(
            project_path,
            overlay_path,
            ignore=ignore_runtime_directory,
        )
    except OSError as error:
        raise RuntimeExecutionError(
            "TRANSACTION_ERROR",
            False,
            "TRANSACTION",
            "Project Staging Overlay 생성에 실패했습니다.",
            None,
            None,
            {"path": str(overlay_path)},
        ) from error
    definitions = dependency_artifacts(dependency_graph)
    for artifact_name, content in outputs.items():
        definition = definitions.get(artifact_name)
        relative_path = None if definition is None else definition.get("path")
        if not isinstance(relative_path, str):
            raise RuntimeExecutionError(
                "TRANSACTION_ERROR",
                False,
                "TRANSACTION",
                "Staging Artifact 경로가 없습니다.",
                None,
                artifact_name,
                {},
            )
        write_artifact(overlay_path / relative_path, content)
    return overlay_path


def capture_artifact_hashes(
    project_path: Path,
    artifact_names: Sequence[str],
    dependency_graph: Mapping[str, object],
) -> dict[str, str]:
    """Input Drift 판정용 Canonical Artifact Byte Hash를 캡처한다."""
    definitions = dependency_artifacts(dependency_graph)
    hashes: dict[str, str] = {}
    for artifact_name in artifact_names:
        definition = definitions.get(artifact_name)
        relative_path = None if definition is None else definition.get("path")
        if not isinstance(relative_path, str):
            raise RuntimeExecutionError(
                "RUNTIME_CONFIGURATION_ERROR",
                False,
                "TASK",
                "Input Artifact 경로가 없습니다.",
                None,
                artifact_name,
                {},
            )
        try:
            hashes[artifact_name] = artifact_hash((project_path / relative_path).read_bytes())
        except OSError as error:
            raise RuntimeExecutionError(
                "RUNTIME_CONFIGURATION_ERROR",
                False,
                "TASK",
                "Input Artifact Hash를 계산하지 못했습니다.",
                None,
                artifact_name,
                {"path": relative_path},
            ) from error
    return hashes


def verify_artifact_hashes(
    project_path: Path,
    expected_hashes: Mapping[str, str],
    dependency_graph: Mapping[str, object],
) -> None:
    """Provider 실행 중 Canonical 입력이 바뀌었으면 Commit을 차단한다."""
    current = capture_artifact_hashes(project_path, list(expected_hashes), dependency_graph)
    changed = sorted(
        artifact_name
        for artifact_name, expected in expected_hashes.items()
        if current.get(artifact_name) != expected
    )
    if changed:
        raise RuntimeExecutionError(
            "INPUT_HASH_CHANGED",
            True,
            "TRANSACTION",
            "Provider 실행 중 입력 Artifact가 변경되었습니다.",
            None,
            None,
            {"artifacts": changed},
        )


def next_project_state(
    current_state: ProjectState,
    gate_id: str,
    validated_input_hashes: Mapping[str, str],
    outputs: Mapping[str, object],
    dependency_graph: Mapping[str, object],
    updated_at: str,
) -> ProjectState:
    """검증된 입력·출력 Hash와 Gate PASS를 반영한 새 Project State를 계산한다."""
    next_state = deepcopy(current_state)
    output_hashes = {
        artifact_name: artifact_hash(
            encoded_artifact(
                content,
                "application/json" if isinstance(content, Mapping) else "text/markdown",
            )
        )
        for artifact_name, content in outputs.items()
    }
    validated_hashes = {**validated_input_hashes, **output_hashes}
    for artifact_name, output_hash in validated_hashes.items():
        current_artifact = next_state["artifacts"].get(artifact_name)
        if current_artifact is None:
            raise RuntimeExecutionError(
                "TRANSACTION_ERROR",
                False,
                "TRANSACTION",
                "Project State에 Runtime 검증 Artifact가 없습니다.",
                None,
                artifact_name,
                {},
            )
        if current_artifact["content_hash"] != output_hash:
            next_state = invalidate_artifact_dependents(
                dependency_graph,
                next_state,
                artifact_name,
                output_hash,
                updated_at,
            )
    for artifact_name, output_hash in validated_hashes.items():
        next_state = mark_artifact_clean(
            next_state,
            artifact_name,
            output_hash,
            updated_at,
        )
    return advance_gate(next_state, gate_id, True, updated_at)


def transaction_root(project_path: Path, transaction_id: str) -> Path:
    """Write-ahead Transaction 디렉터리를 반환한다."""
    return project_path / ".runtime" / "transactions" / transaction_id


def transaction_record_path(project_path: Path, transaction_id: str) -> Path:
    """Transaction 상태 파일 경로를 반환한다."""
    return transaction_root(project_path, transaction_id) / "transaction.json"


def transaction_member_path(path_value: str, root: Path, field: str) -> Path:
    """Transaction 기록 경로가 허용 Root 내부인지 검증한다."""
    path = Path(path_value).resolve()
    try:
        path.relative_to(root.resolve())
    except ValueError as error:
        raise RuntimeExecutionError(
            "TRANSACTION_ERROR",
            False,
            "TRANSACTION",
            "Transaction 기록이 허용 경로 밖을 참조합니다.",
            None,
            None,
            {"field": field, "path": path_value, "root": str(root)},
        ) from error
    return path


def restore_transaction_backups(
    project_path: Path,
    record: Mapping[str, object],
) -> None:
    """Prepared Transaction의 모든 Canonical 파일을 백업으로 복구한다."""
    transaction_id = record.get("transaction_id")
    if not isinstance(transaction_id, str):
        raise RuntimeExecutionError(
            "TRANSACTION_ERROR",
            False,
            "TRANSACTION",
            "Transaction ID가 손상되었습니다.",
            None,
            None,
            {},
        )
    backup_root = transaction_root(project_path, transaction_id) / "backups"
    targets = record.get("targets")
    if not isinstance(targets, list) or not all(isinstance(item, Mapping) for item in targets):
        raise RuntimeExecutionError(
            "TRANSACTION_ERROR",
            False,
            "TRANSACTION",
            "Transaction Target 목록이 손상되었습니다.",
            None,
            None,
            {},
        )
    for target in reversed(targets):
        target_path_value = target.get("target_path")
        backup_path_value = target.get("backup_path")
        existed_before = target.get("existed_before", True)
        if not isinstance(target_path_value, str) or not isinstance(existed_before, bool):
            raise RuntimeExecutionError(
                "TRANSACTION_ERROR",
                False,
                "TRANSACTION",
                "Transaction 복구 경로가 손상되었습니다.",
                None,
                None,
                {},
            )
        target_path = transaction_member_path(target_path_value, project_path, "target_path")
        if not existed_before:
            try:
                target_path.unlink(missing_ok=True)
            except OSError as error:
                raise RuntimeExecutionError(
                    "TRANSACTION_ERROR",
                    False,
                    "TRANSACTION",
                    "Prepared Transaction 신규 Artifact 제거에 실패했습니다.",
                    None,
                    None,
                    {"target_path": str(target_path)},
                ) from error
            continue
        if not isinstance(backup_path_value, str):
            raise RuntimeExecutionError(
                "TRANSACTION_ERROR",
                False,
                "TRANSACTION",
                "Transaction 백업 경로가 손상되었습니다.",
                None,
                None,
                {"target_path": str(target_path)},
            )
        backup_path = transaction_member_path(backup_path_value, backup_root, "backup_path")
        temporary_path = target_path.with_name(f".{target_path.name}.rollback.tmp")
        try:
            shutil.copy2(backup_path, temporary_path)
            os.replace(temporary_path, target_path)
        except OSError as error:
            raise RuntimeExecutionError(
                "TRANSACTION_ERROR",
                False,
                "TRANSACTION",
                "Prepared Transaction 복구에 실패했습니다.",
                None,
                None,
                {"target_path": str(target_path)},
            ) from error


def commit_gate_transaction(
    project_path: Path,
    run_id: str,
    gate_id: str,
    overlay_path: Path,
    outputs: Mapping[str, object],
    dependency_graph: Mapping[str, object],
    next_state: ProjectState,
    additional_targets: Mapping[str, bytes],
) -> str:
    """Gate 출력과 Project State를 Write-ahead 기록 후 전부 반영하거나 복구한다."""
    transaction_id = f"TX-{uuid4().hex[:16].upper()}"
    root = transaction_root(project_path, transaction_id)
    backup_root = root / "backups"
    backup_root.mkdir(parents=True, exist_ok=False)
    definitions = dependency_artifacts(dependency_graph)
    target_specs: list[tuple[Path, bytes, str]] = []
    for artifact_name, content in outputs.items():
        definition = definitions.get(artifact_name)
        relative_path = None if definition is None else definition.get("path")
        if not isinstance(relative_path, str):
            raise RuntimeExecutionError(
                "TRANSACTION_ERROR",
                False,
                "TRANSACTION",
                "Commit Artifact 경로가 없습니다.",
                None,
                artifact_name,
                {},
            )
        media_type = "application/json" if isinstance(content, Mapping) else "text/markdown"
        target_specs.append(
            (project_path / relative_path, encoded_artifact(content, media_type), artifact_name)
        )
    state_bytes = (json.dumps(next_state, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    target_specs.append(
        (project_path / "00_PROJECT" / "project_state.json", state_bytes, "project_state")
    )
    existing_targets = {target.resolve() for target, _content, _name in target_specs}
    for relative_path, intended_bytes in additional_targets.items():
        target_path = (project_path / relative_path).resolve()
        try:
            target_path.relative_to(project_path.resolve())
        except ValueError as error:
            raise RuntimeExecutionError(
                "TRANSACTION_ERROR",
                False,
                "TRANSACTION",
                "추가 Transaction Target이 Project 밖을 참조합니다.",
                None,
                None,
                {"path": relative_path},
            ) from error
        if target_path in existing_targets:
            raise RuntimeExecutionError(
                "TRANSACTION_ERROR",
                False,
                "TRANSACTION",
                "추가 Transaction Target이 기존 Target과 중복됩니다.",
                None,
                None,
                {"path": relative_path},
            )
        target_specs.append((target_path, intended_bytes, relative_path))
        existing_targets.add(target_path)
    targets: list[dict[str, object]] = []
    for index, (target_path, intended_bytes, artifact_name) in enumerate(target_specs):
        backup_path = backup_root / f"{index:03d}-{target_path.name}"
        existed_before = target_path.exists()
        before_hash: str | None = None
        backup_path_value: str | None = None
        if existed_before:
            try:
                before_bytes = target_path.read_bytes()
                shutil.copy2(target_path, backup_path)
            except OSError as error:
                raise RuntimeExecutionError(
                    "TRANSACTION_ERROR",
                    False,
                    "TRANSACTION",
                    "Canonical Artifact 백업에 실패했습니다.",
                    None,
                    artifact_name,
                    {"target_path": str(target_path)},
                ) from error
            before_hash = artifact_hash(before_bytes)
            backup_path_value = str(backup_path)
        targets.append(
            {
                "artifact_name": artifact_name,
                "target_path": str(target_path),
                "backup_path": backup_path_value,
                "existed_before": existed_before,
                "before_hash": before_hash,
                "after_hash": artifact_hash(intended_bytes),
            }
        )
    record: dict[str, object] = {
        "transaction_id": transaction_id,
        "run_id": run_id,
        "gate_id": gate_id,
        "status": "PREPARED",
        "prepared_at": utc_now(),
        "committed_at": None,
        "rolled_back_at": None,
        "overlay_path": str(overlay_path),
        "targets": targets,
    }
    write_json_object(transaction_record_path(project_path, transaction_id), record)
    try:
        for target_path, intended_bytes, _artifact_name in target_specs:
            temporary_path = target_path.with_name(f".{target_path.name}.{transaction_id}.tmp")
            temporary_path.write_bytes(intended_bytes)
            os.replace(temporary_path, target_path)
    except OSError as error:
        restore_transaction_backups(project_path, record)
        record["status"] = "ROLLED_BACK"
        record["rolled_back_at"] = utc_now()
        write_json_object(transaction_record_path(project_path, transaction_id), record)
        raise RuntimeExecutionError(
            "TRANSACTION_ERROR",
            True,
            "TRANSACTION",
            "Artifact Transaction Commit에 실패하여 모두 복구했습니다.",
            None,
            None,
            {"transaction_id": transaction_id},
        ) from error
    record["status"] = "COMMITTED"
    record["committed_at"] = utc_now()
    write_json_object(transaction_record_path(project_path, transaction_id), record)
    return transaction_id


def recover_prepared_transactions(project_path: Path) -> list[str]:
    """Crash 뒤 PREPARED 상태 Transaction을 Canonical 백업으로 복구한다."""
    recovered: list[str] = []
    for record_path in sorted(
        (project_path / ".runtime" / "transactions").glob("*/transaction.json")
    ):
        record = load_json_object(record_path)
        if record.get("status") != "PREPARED":
            continue
        restore_transaction_backups(project_path, record)
        record["status"] = "ROLLED_BACK"
        record["rolled_back_at"] = utc_now()
        write_json_object(record_path, record)
        transaction_id = record.get("transaction_id")
        if isinstance(transaction_id, str):
            recovered.append(transaction_id)
    return recovered
