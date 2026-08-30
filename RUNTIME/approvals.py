"""입력 Artifact Hash에 결합된 Human Approval 저장과 검증."""

from collections.abc import Mapping
from pathlib import Path
from typing import cast
from uuid import uuid4

from RUNTIME.errors import RuntimeExecutionError
from RUNTIME.event_store import run_root, utc_now
from RUNTIME.models import ApprovalDecision, RuntimeApproval
from VALIDATORS.io import load_json_object, write_json_object
from VALIDATORS.schema_validation import collect_schema_errors


def approval_path(project_path: Path, run_id: str, task_id: str) -> Path:
    """Task별 Human Approval Record 경로를 반환한다."""
    return run_root(project_path, run_id) / "approvals" / f"{task_id}.json"


def create_approval(
    project_path: Path,
    run_id: str,
    task_id: str,
    decision: str,
    actor: str,
    reason: str,
    input_hashes: Mapping[str, str],
) -> RuntimeApproval:
    """비어 있지 않은 이유와 현재 Input Hash에 결합된 승인을 기록한다."""
    if decision not in {"APPROVED", "REJECTED"}:
        raise RuntimeExecutionError(
            "RUNTIME_CONFIGURATION_ERROR",
            False,
            "APPROVAL",
            "Human Approval Decision이 올바르지 않습니다.",
            task_id,
            None,
            {"decision": decision},
        )
    if not actor.strip() or not reason.strip() or not input_hashes:
        raise RuntimeExecutionError(
            "RUNTIME_CONFIGURATION_ERROR",
            False,
            "APPROVAL",
            "Human Approval에는 Actor, Reason, Input Hash가 필요합니다.",
            task_id,
            None,
            {},
        )
    approval = RuntimeApproval(
        schema_family="runtime-approval",
        schema_version="1.0.0",
        approval_id=f"APR-{uuid4().hex[:12].upper()}",
        run_id=run_id,
        task_id=task_id,
        decision=cast(ApprovalDecision, decision),
        actor=actor,
        reason=reason,
        bound_input_hashes=dict(input_hashes),
        created_at=utc_now(),
    )
    schema = load_json_object(Path(__file__).resolve().parent / "schemas" / "approval.schema.json")
    errors = collect_schema_errors(approval, schema, "runtime_approval")
    if errors:
        raise RuntimeExecutionError(
            "RUNTIME_CONFIGURATION_ERROR",
            False,
            "APPROVAL",
            "Human Approval Schema 검증에 실패했습니다.",
            task_id,
            None,
            {"errors": errors},
        )
    write_json_object(approval_path(project_path, run_id, task_id), approval)
    return approval


def approval_is_current(
    project_path: Path,
    run_id: str,
    task_id: str,
    input_hashes: Mapping[str, str],
) -> bool:
    """승인 Decision과 결합 Input Hash가 현재 입력과 같은지 판정한다."""
    return current_approval(project_path, run_id, task_id, input_hashes) is not None


def current_approval(
    project_path: Path,
    run_id: str,
    task_id: str,
    input_hashes: Mapping[str, str],
) -> RuntimeApproval | None:
    """현재 입력 Hash와 일치하는 검증된 승인 레코드를 반환한다."""
    path = approval_path(project_path, run_id, task_id)
    if not path.is_file():
        return None
    approval = load_json_object(path)
    schema = load_json_object(
        Path(__file__).resolve().parent / "schemas" / "approval.schema.json"
    )
    errors = collect_schema_errors(approval, schema, "runtime_approval")
    if errors:
        raise RuntimeExecutionError(
            "RUNTIME_CONFIGURATION_ERROR",
            False,
            "APPROVAL",
            "저장된 Human Approval Schema가 손상되었습니다.",
            task_id,
            None,
            {"errors": errors},
        )
    bound = approval.get("bound_input_hashes")
    if not (
        approval.get("decision") == "APPROVED"
        and isinstance(bound, Mapping)
        and dict(bound) == dict(input_hashes)
    ):
        return None
    return cast(RuntimeApproval, approval)
