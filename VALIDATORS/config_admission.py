"""Broadcast Readable Config의 명시적 승인과 감사 결속."""

import json
from collections.abc import Mapping
from copy import deepcopy
from hashlib import sha256
from pathlib import Path
from typing import TypedDict, cast
from uuid import uuid4

from RUNTIME.errors import RuntimeExecutionError
from RUNTIME.output_gateway import encoded_artifact
from RUNTIME.transactions import (
    acquire_project_lock,
    commit_gate_transaction,
    recover_prepared_transactions,
    release_project_lock,
)
from VALIDATORS.change_log import change_log_bytes
from VALIDATORS.dependency import (
    artifact_hash,
    invalidate_artifact_dependents,
    mark_artifact_clean,
    reconcile_project_state_artifacts,
    transitive_dependents,
)
from VALIDATORS.exceptions import ConfigurationError
from VALIDATORS.io import load_json_object
from VALIDATORS.models import ProjectState, RevisionTrigger
from VALIDATORS.output_profiles import (
    ResolvedOutputProfile,
    resolve_active_broadcast_readable_output_profile,
)
from VALIDATORS.schema_validation import collect_schema_errors
from VALIDATORS.state_machine import gate_index

CONFIG_ARTIFACT = "broadcast_readable_config"
CONFIG_RELATIVE_PATH = "00_PROJECT/broadcast_readable_config.json"
CHANGE_LOG_RELATIVE_PATH = "00_PROJECT/change_log.jsonl"
ADMISSION_EVENT = "BROADCAST_READABLE_CONFIG_ADMITTED"
READABLE_REENTRY_GATE = "GATE-08"
READABLE_REENTRY_CURRENT_GATE = "GATE-07"


class ConfigAdmissionResult(TypedDict):
    """Config Admission 실행 결과."""

    admission_id: str
    transaction_id: str | None
    project_id: str
    result: str
    config_file_sha256: str
    invalidated_artifacts: list[str]
    process_revision: int
    recovered_transaction_ids: list[str]


def decode_json_object(content: bytes, source: str) -> dict[str, object]:
    """UTF-8 JSON 객체를 엄격하게 해석한다."""
    try:
        decoded = content.decode("utf-8")
        value = json.loads(decoded)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ConfigurationError(
            f"CONFIG_ADMISSION_INVALID: JSON을 읽지 못했습니다: "
            f"source={source}, detail={error}"
        ) from error
    if not isinstance(value, dict):
        raise ConfigurationError(
            f"CONFIG_ADMISSION_INVALID: JSON 객체가 필요합니다: source={source}"
        )
    return cast(dict[str, object], value)


def read_bytes(path: Path, code: str) -> bytes:
    """파일 Byte를 읽고 경로 문맥이 있는 오류를 반환한다."""
    try:
        return path.read_bytes()
    except OSError as error:
        raise ConfigurationError(
            f"{code}: 파일을 읽지 못했습니다: path={path}, detail={error}"
        ) from error


def repository_root_for_admission(project_path: Path) -> Path:
    """Project가 속한 Repository Root를 검증해 반환한다."""
    resolved_project = project_path.resolve()
    for candidate in (resolved_project, *resolved_project.parents):
        graph_path = candidate / "STANDARD/dependency_graph.json"
        library_path = candidate / "STORY_LIBRARY/novelty_index.json"
        projects_root = candidate / "PROJECTS"
        if graph_path.is_file() and library_path.is_file():
            if not resolved_project.is_relative_to(projects_root.resolve()):
                raise ConfigurationError(
                    "CONFIG_ADMISSION_INVALID: Project 경로가 Repository의 "
                    f"PROJECTS 밖입니다: project_path={project_path}"
                )
            return candidate
    raise ConfigurationError(
        "CONFIG_ADMISSION_INVALID: Repository Root를 찾을 수 없습니다: "
        f"project_path={project_path}"
    )


def validate_candidate_config(
    repository_root: Path,
    project_path: Path,
    candidate: Mapping[str, object],
) -> ResolvedOutputProfile | None:
    """Config Schema·Project·Profile 결속을 검증한다."""
    schema_path = repository_root / "STANDARD/schemas/broadcast_readable_config.schema.json"
    errors = collect_schema_errors(
        candidate,
        load_json_object(schema_path),
        str(schema_path),
    )
    if errors:
        raise ConfigurationError(
            f"CONFIG_ADMISSION_INVALID: Config Schema 오류입니다: errors={errors}"
        )
    project_manifest = load_json_object(
        project_path / "00_PROJECT/project_manifest.json"
    )
    production_config = load_json_object(
        project_path / "00_PROJECT/production_config.json"
    )
    project_id = project_manifest.get("project_id")
    if (
        not isinstance(project_id, str)
        or production_config.get("project_id") != project_id
        or candidate.get("project_id") != project_id
    ):
        raise ConfigurationError(
            "CONFIG_ADMISSION_INVALID: Project ID가 일치하지 않습니다: "
            f"manifest={project_id!r}, production={production_config.get('project_id')!r}, "
            f"candidate={candidate.get('project_id')!r}"
        )
    return resolve_active_broadcast_readable_output_profile(
        repository_root,
        production_config,
        {CONFIG_ARTIFACT: candidate},
    )


def open_gate_transaction_ids(project_path: Path) -> list[str]:
    """현재 OPEN 상태인 Codex Gate Transaction ID를 반환한다."""
    transaction_ids: list[str] = []
    task_root = project_path / ".runtime/codex_tasks"
    for task_path in sorted(task_root.glob("*/task.json")):
        task = load_json_object(task_path)
        transaction_id = task.get("transaction_id")
        if task.get("status") == "OPEN" and isinstance(transaction_id, str):
            transaction_ids.append(transaction_id)
    return transaction_ids


def change_log_records(project_path: Path) -> list[Mapping[str, object]]:
    """Project Change Log의 JSON 객체 Record를 반환한다."""
    log_path = project_path / CHANGE_LOG_RELATIVE_PATH
    content = read_bytes(log_path, "CONFIG_ADMISSION_REQUIRED")
    records: list[Mapping[str, object]] = []
    for line_number, raw_line in enumerate(content.decode("utf-8").splitlines(), 1):
        if not raw_line.strip():
            continue
        try:
            value = json.loads(raw_line)
        except json.JSONDecodeError as error:
            raise ConfigurationError(
                "CONFIG_ADMISSION_REQUIRED: Change Log JSONL이 손상됐습니다: "
                f"path={log_path}, line={line_number}, detail={error}"
            ) from error
        if not isinstance(value, Mapping):
            raise ConfigurationError(
                "CONFIG_ADMISSION_REQUIRED: Change Log Record가 객체가 아닙니다: "
                f"path={log_path}, line={line_number}"
            )
        records.append(value)
    return records


def matching_admission_detail(
    project_path: Path,
    project_id: str,
    config_file_sha256: str,
    resolved_profile: ResolvedOutputProfile | None,
) -> Mapping[str, object] | None:
    """현재 Config와 Profile에 결속된 마지막 Admission Detail을 반환한다."""
    expected_profile_id = (
        None if resolved_profile is None else resolved_profile["profile_id"]
    )
    expected_profile_version = (
        None if resolved_profile is None else resolved_profile["profile_version"]
    )
    expected_profile_hash = (
        None if resolved_profile is None else resolved_profile["sha256"]
    )
    for record in reversed(change_log_records(project_path)):
        if record.get("event") != ADMISSION_EVENT:
            continue
        detail = record.get("detail")
        if not isinstance(detail, Mapping):
            continue
        if (
            detail.get("project_id") == project_id
            and detail.get("new_config_file_sha256") == config_file_sha256
            and detail.get("profile_id") == expected_profile_id
            and detail.get("profile_version") == expected_profile_version
            and detail.get("profile_file_sha256") == expected_profile_hash
            and detail.get("commit_result") == "COMMITTED"
        ):
            return detail
    return None


def config_admission_state(
    dependency_graph: Mapping[str, object],
    state: ProjectState,
    config_file_sha256: str,
    admission_id: str,
    actor: str,
    reason: str,
    admitted_at: str,
) -> tuple[ProjectState, list[str]]:
    """Config를 CLEAN으로 승인하고 정확한 Readable 하위만 무효화한다."""
    expanded = reconcile_project_state_artifacts(dependency_graph, state)
    invalidated_names = sorted(
        transitive_dependents(dependency_graph, CONFIG_ARTIFACT)
    )
    invalidated = invalidate_artifact_dependents(
        dependency_graph,
        expanded,
        CONFIG_ARTIFACT,
        config_file_sha256,
        admitted_at,
    )
    admitted = mark_artifact_clean(
        invalidated,
        CONFIG_ARTIFACT,
        config_file_sha256,
        admitted_at,
    )
    next_state = deepcopy(admitted)
    current_gate = state["current_gate"]
    if current_gate != "NONE" and gate_index(current_gate) >= gate_index(
        READABLE_REENTRY_GATE
    ):
        next_state["current_gate"] = READABLE_REENTRY_CURRENT_GATE
        next_state["readiness"] = {
            "artifact_status": "INCOMPLETE",
            "contract_status": "UNVALIDATED",
            "process_status": "NONCONFORMANT",
            "editorial_status": "NOT_REVIEWED",
            "process_start_gate": READABLE_REENTRY_GATE,
            "process_revision": state["readiness"]["process_revision"] + 1,
        }
    next_state["state"] = "BLOCKED"
    next_state["updated_at"] = admitted_at
    next_state["revision_trigger"] = RevisionTrigger(
        type="CONFIG_ADMISSION",
        source_id=admission_id,
        target_owner_agent=None,
        target_gate=None,
        target_task_ids=[],
        actor=actor,
        reason=reason,
        triggered_at=admitted_at,
    )
    return next_state, invalidated_names


def admission_result(
    admission_id: str,
    transaction_id: str | None,
    project_id: str,
    result: str,
    config_file_sha256: str,
    invalidated_artifacts: list[str],
    process_revision: int,
    recovered_transaction_ids: list[str],
) -> ConfigAdmissionResult:
    """CLI와 Runtime이 공유하는 Admission 결과를 만든다."""
    return ConfigAdmissionResult(
        admission_id=admission_id,
        transaction_id=transaction_id,
        project_id=project_id,
        result=result,
        config_file_sha256=config_file_sha256,
        invalidated_artifacts=invalidated_artifacts,
        process_revision=process_revision,
        recovered_transaction_ids=recovered_transaction_ids,
    )


def admit_broadcast_readable_config(
    project_path: Path,
    input_path: Path,
    actor: str,
    reason: str,
    admitted_at: str,
) -> ConfigAdmissionResult:
    """Writer Lock과 복구 Transaction으로 Broadcast Readable Config를 승인한다."""
    if not actor.strip() or not reason.strip():
        raise ConfigurationError(
            "CONFIG_ADMISSION_INVALID: actor와 reason은 비어 있을 수 없습니다."
        )
    repository_root = repository_root_for_admission(project_path)
    resolved_project = project_path.resolve()
    input_snapshot = read_bytes(input_path, "CONFIG_ADMISSION_INVALID")
    input_snapshot_hash = sha256(input_snapshot).hexdigest()
    candidate = decode_json_object(input_snapshot, str(input_path))
    admission_id = f"CONFIG-ADMISSION-{uuid4().hex[:16].upper()}"
    lock_path = acquire_project_lock(resolved_project, admission_id)
    try:
        current_input = read_bytes(input_path, "CONFIG_ADMISSION_INVALID")
        current_input_hash = sha256(current_input).hexdigest()
        if current_input_hash != input_snapshot_hash:
            raise ConfigurationError(
                "CONFIG_ADMISSION_STALE_INPUT: Lock 획득 전후 Input이 변경됐습니다: "
                f"path={input_path}, expected={input_snapshot_hash}, "
                f"actual={current_input_hash}"
            )
        candidate = decode_json_object(current_input, str(input_path))
        recovered = recover_prepared_transactions(resolved_project)
        open_transactions = open_gate_transaction_ids(resolved_project)
        if open_transactions:
            raise ConfigurationError(
                "CONFIG_ADMISSION_CONFLICT: 열린 Gate Transaction이 있습니다: "
                f"transaction_ids={open_transactions}"
            )
        resolved_profile = validate_candidate_config(
            repository_root,
            resolved_project,
            candidate,
        )
        dependency_graph = load_json_object(
            repository_root / "STANDARD/dependency_graph.json"
        )
        state = cast(
            ProjectState,
            load_json_object(
                resolved_project / "00_PROJECT/project_state.json"
            ),
        )
        project_id = state["project_id"]
        canonical_bytes = encoded_artifact(candidate, "application/json")
        config_file_sha256 = artifact_hash(canonical_bytes)
        canonical_path = resolved_project / CONFIG_RELATIVE_PATH
        existing_bytes = canonical_path.read_bytes() if canonical_path.is_file() else None
        existing_state = state["artifacts"].get(CONFIG_ARTIFACT)
        existing_clean = (
            existing_state is not None
            and existing_state["status"] == "CLEAN"
            and existing_state["content_hash"] == config_file_sha256
        )
        admitted_detail = matching_admission_detail(
            resolved_project,
            project_id,
            config_file_sha256,
            resolved_profile,
        )
        if (
            existing_bytes == canonical_bytes
            and existing_clean
            and admitted_detail is not None
        ):
            return admission_result(
                str(admitted_detail["admission_id"]),
                None,
                project_id,
                "NO_OP",
                config_file_sha256,
                [],
                state["readiness"]["process_revision"],
                recovered,
            )
        next_state, invalidated_artifacts = config_admission_state(
            dependency_graph,
            state,
            config_file_sha256,
            admission_id,
            actor,
            reason,
            admitted_at,
        )
        profile_id = None if resolved_profile is None else resolved_profile["profile_id"]
        profile_version = (
            None if resolved_profile is None else resolved_profile["profile_version"]
        )
        profile_hash = None if resolved_profile is None else resolved_profile["sha256"]
        previous_hash = (
            None if existing_bytes is None else artifact_hash(existing_bytes)
        )
        log_path = resolved_project / CHANGE_LOG_RELATIVE_PATH
        next_log = change_log_bytes(
            read_bytes(log_path, "CONFIG_ADMISSION_INVALID"),
            ADMISSION_EVENT,
            {
                "admission_id": admission_id,
                "project_id": project_id,
                "actor": actor,
                "reason": reason,
                "previous_config_file_sha256": previous_hash,
                "new_config_file_sha256": config_file_sha256,
                "profile_id": profile_id,
                "profile_version": profile_version,
                "profile_file_sha256": profile_hash,
                "invalidated_artifacts": invalidated_artifacts,
                "process_revision": next_state["readiness"]["process_revision"],
                "recovered_transaction_ids": recovered,
                "commit_result": "COMMITTED",
            },
            admitted_at,
        )
        transaction_id = commit_gate_transaction(
            resolved_project,
            admission_id,
            "CONFIG-ADMISSION",
            input_path,
            {CONFIG_ARTIFACT: candidate},
            dependency_graph,
            next_state,
            {CHANGE_LOG_RELATIVE_PATH: next_log},
        )
        return admission_result(
            admission_id,
            transaction_id,
            project_id,
            "COMMITTED",
            config_file_sha256,
            invalidated_artifacts,
            next_state["readiness"]["process_revision"],
            recovered,
        )
    except RuntimeExecutionError:
        raise
    finally:
        release_project_lock(lock_path, admission_id)


def broadcast_readable_config_admission_issues(
    repository_root: Path,
    project_path: Path,
    state: ProjectState,
) -> list[dict[str, object]]:
    """현재 Config File·State·Admission·Profile의 결속 문제를 반환한다."""
    config_path = project_path / CONFIG_RELATIVE_PATH
    config_state = state["artifacts"].get(CONFIG_ARTIFACT)
    if not config_path.is_file():
        if config_state is not None and config_state["status"] == "CLEAN":
            return [
                {
                    "artifact": CONFIG_ARTIFACT,
                    "path": CONFIG_RELATIVE_PATH,
                    "reason": "CANONICAL_FILE_MISSING",
                }
            ]
        admitted_before = any(
            record.get("event") == ADMISSION_EVENT
            and isinstance((detail := record.get("detail")), Mapping)
            and detail.get("commit_result") == "COMMITTED"
            for record in change_log_records(project_path)
        )
        if admitted_before:
            return [
                {
                    "artifact": CONFIG_ARTIFACT,
                    "path": CONFIG_RELATIVE_PATH,
                    "reason": "CONFIG_FILE_MISSING_AFTER_ADMISSION",
                }
            ]
        return []
    actual_bytes = read_bytes(config_path, "CONFIG_ADMISSION_REQUIRED")
    actual_hash = artifact_hash(actual_bytes)
    if config_state is None:
        return [
            {
                "artifact": CONFIG_ARTIFACT,
                "path": CONFIG_RELATIVE_PATH,
                "reason": "STATE_ENTRY_MISSING",
                "actual_hash": actual_hash,
            }
        ]
    if config_state["status"] != "CLEAN":
        return [
            {
                "artifact": CONFIG_ARTIFACT,
                "path": CONFIG_RELATIVE_PATH,
                "reason": "STATE_STATUS_MISMATCH",
                "expected_status": "CLEAN",
                "actual_status": config_state["status"],
                "actual_hash": actual_hash,
            }
        ]
    expected_hash = config_state["content_hash"]
    if expected_hash is None:
        return [
            {
                "artifact": CONFIG_ARTIFACT,
                "path": CONFIG_RELATIVE_PATH,
                "reason": "CLEAN_HASH_MISSING",
                "actual_hash": actual_hash,
            }
        ]
    if expected_hash != actual_hash:
        return [
            {
                "artifact": CONFIG_ARTIFACT,
                "path": CONFIG_RELATIVE_PATH,
                "reason": "CONTENT_HASH_MISMATCH",
                "expected_hash": expected_hash,
                "actual_hash": actual_hash,
            }
        ]
    config = decode_json_object(actual_bytes, str(config_path))
    resolved_profile = validate_candidate_config(
        repository_root,
        project_path,
        config,
    )
    if matching_admission_detail(
        project_path,
        state["project_id"],
        actual_hash,
        resolved_profile,
    ) is None:
        return [
            {
                "artifact": CONFIG_ARTIFACT,
                "path": CONFIG_RELATIVE_PATH,
                "reason": "CONFIG_ADMISSION_REQUIRED",
                "actual_hash": actual_hash,
            }
        ]
    return []
