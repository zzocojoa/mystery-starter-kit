"""LLM Agent Runtime v1.0 운영 명령행 인터페이스."""

import argparse
import asyncio
import json
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path

from RUNTIME.approvals import create_approval
from RUNTIME.contracts import load_provider_registry, validate_runtime_contracts
from RUNTIME.engine import execute_run, request_cancel, resume_run
from RUNTIME.errors import RuntimeExecutionError
from RUNTIME.event_store import append_event, find_run, load_run
from RUNTIME.human_inputs import submit_evidence_input
from RUNTIME.models import ExecutionPlan, LLMProvider, RuntimeRun
from RUNTIME.planner import build_execution_plan, next_gate_id
from RUNTIME.providers.base import provider_descriptor_document
from RUNTIME.providers.registry import build_provider_registry, close_providers
from VALIDATORS.exceptions import StarterKitError
from VALIDATORS.io import load_json_object
from VALIDATORS.schema_validation import collect_schema_errors


def gate_id(value: str) -> str:
    """CLI Gate 값을 GATE-00부터 GATE-13 범위로 제한한다."""
    allowed = {f"GATE-{index:02d}" for index in range(14)}
    if value not in allowed:
        raise argparse.ArgumentTypeError("Gate는 GATE-00부터 GATE-13까지여야 합니다.")
    return value


def build_parser() -> argparse.ArgumentParser:
    """Runtime v1.0 명령과 명시적 실행 인자를 구성한다."""
    parser = argparse.ArgumentParser(prog="mystery-runtime")
    parser.add_argument("--repository-root", type=Path, default=Path.cwd())
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("doctor", help="계약과 활성 Provider 구성을 진단합니다.")

    plan_parser = subparsers.add_parser("plan", help="현재 Gate 이후 실행 계획을 출력합니다.")
    plan_parser.add_argument("project_path", type=Path)
    plan_parser.add_argument("--from", dest="from_gate", type=gate_id)
    plan_parser.add_argument("--to", dest="to_gate", type=gate_id, default="GATE-13")

    run_parser = subparsers.add_parser("run", help="새 Runtime Run을 실행합니다.")
    run_parser.add_argument("project_path", type=Path)
    run_parser.add_argument("--from", dest="from_gate", type=gate_id)
    run_parser.add_argument("--to", dest="to_gate", type=gate_id, default="GATE-13")
    run_parser.add_argument("--route-profile", default="default")
    run_parser.add_argument("--reference-source", type=Path)

    resume_parser = subparsers.add_parser("resume", help="중단된 Runtime Run을 재개합니다.")
    resume_parser.add_argument("run_id")

    status_parser = subparsers.add_parser("status", help="Project 또는 Run 상태를 출력합니다.")
    status_parser.add_argument("target")

    approve_parser = subparsers.add_parser(
        "approve",
        help="현재 입력 Hash에 결합된 Human 승인을 기록합니다.",
    )
    approve_parser.add_argument("run_id")
    approve_parser.add_argument("task_id")
    approve_parser.add_argument("--actor", required=True)
    approve_parser.add_argument("--reason", required=True)

    input_parser = subparsers.add_parser(
        "submit-input",
        help="WAITING_HUMAN Run에 현재 Hash와 결속된 Human Input을 제출합니다.",
    )
    input_parser.add_argument("run_id")
    input_parser.add_argument("task_id")
    input_parser.add_argument("input_path", type=Path)

    cancel_parser = subparsers.add_parser("cancel", help="Runtime Run 취소를 요청합니다.")
    cancel_parser.add_argument("run_id")

    subparsers.add_parser("providers", help="활성 Provider Descriptor를 출력합니다.")
    return parser


def print_json(document: object, output: object) -> None:
    """운영 결과를 안정적인 UTF-8 JSON으로 출력한다."""
    if not hasattr(output, "write"):
        raise TypeError("출력 대상은 write를 지원해야 합니다.")
    serialized = json.dumps(document, ensure_ascii=False, indent=2)
    output.write(serialized + "\n")


def resolved_project_path(project_path: Path) -> Path:
    """필수 Project State가 있는 절대 Project 경로를 반환한다."""
    resolved = project_path.expanduser().resolve()
    state_path = resolved / "00_PROJECT" / "project_state.json"
    if not state_path.is_file():
        raise RuntimeExecutionError(
            "RUNTIME_CONFIGURATION_ERROR",
            False,
            "RUN",
            "Project State 파일을 찾을 수 없습니다.",
            None,
            None,
            {"project_path": str(resolved)},
        )
    return resolved


def inferred_from_gate(project_path: Path, requested_gate: str | None) -> str:
    """명시 Gate가 없으면 Canonical Project State의 다음 Gate를 반환한다."""
    if requested_gate is not None:
        return requested_gate
    state = load_json_object(project_path / "00_PROJECT" / "project_state.json")
    current_gate = state.get("current_gate")
    if not isinstance(current_gate, str):
        raise RuntimeExecutionError(
            "RUNTIME_CONFIGURATION_ERROR",
            False,
            "RUN",
            "Project State current_gate가 문자열이 아닙니다.",
            None,
            None,
            {"project_path": str(project_path)},
        )
    return next_gate_id(current_gate)


async def provider_documents(repository_root: Path) -> list[dict[str, object]]:
    """활성 Provider를 생성하고 공통 Descriptor Schema를 검증한다."""
    registry = load_provider_registry(repository_root)
    providers: Mapping[str, LLMProvider] = await build_provider_registry(registry)
    try:
        schema = load_json_object(
            repository_root / "RUNTIME" / "schemas" / "provider_descriptor.schema.json"
        )
        documents: list[dict[str, object]] = []
        for provider_id, provider in sorted(providers.items()):
            document = provider_descriptor_document(provider.descriptor)
            errors = collect_schema_errors(document, schema, f"provider:{provider_id}")
            if errors:
                raise RuntimeExecutionError(
                    "RUNTIME_CONFIGURATION_ERROR",
                    False,
                    "PROVIDER",
                    "Provider Descriptor Schema 검증에 실패했습니다.",
                    None,
                    None,
                    {"provider_id": provider_id, "errors": errors},
                )
            documents.append(document)
        return documents
    finally:
        await close_providers(providers)


async def doctor_document(repository_root: Path) -> dict[str, object]:
    """계약과 Provider를 실제 로딩한 진단 결과를 반환한다."""
    validate_runtime_contracts(repository_root)
    providers = await provider_documents(repository_root)
    return {
        "runtime_version": "1.0.0",
        "status": "PASS",
        "checks": {
            "contracts": "PASS",
            "provider_descriptors": "PASS",
        },
        "providers": providers,
    }


def project_run_status(project_path: Path) -> dict[str, object]:
    """Project의 Canonical 상태와 최신순 Runtime Run 목록을 반환한다."""
    state = load_json_object(project_path / "00_PROJECT" / "project_state.json")
    run_paths = sorted(
        (project_path / ".runtime" / "runs").glob("*/run.json"),
        key=lambda path: path.stat().st_mtime_ns,
        reverse=True,
    )
    runs = [load_run(project_path, path.parent.name) for path in run_paths]
    return {
        "project_path": str(project_path),
        "project_state": state,
        "runs": runs,
    }


def status_document(repository_root: Path, target: str) -> dict[str, object]:
    """Directory Target은 Project, 그 외 Target은 Run ID로 해석한다."""
    candidate = Path(target).expanduser()
    if candidate.is_dir():
        return project_run_status(resolved_project_path(candidate))
    project_path, run = find_run(repository_root, target)
    return {"project_path": str(project_path), "run": run}


def approval_document(
    repository_root: Path, run_id: str, task_id: str, actor: str, reason: str
) -> dict[str, object]:
    """대기 Task의 현재 Input Hash에 APPROVED 결정을 결합한다."""
    project_path, run = find_run(repository_root, run_id)
    task_state = run["tasks"].get(task_id)
    if task_state is None:
        raise RuntimeExecutionError(
            "RUNTIME_CONFIGURATION_ERROR",
            False,
            "APPROVAL",
            "Run에 승인 대상 Task가 없습니다.",
            task_id,
            None,
            {"run_id": run_id},
        )
    input_hashes = task_state["input_hashes"]
    approval = create_approval(
        project_path,
        run_id,
        task_id,
        "APPROVED",
        actor,
        reason,
        input_hashes,
    )
    append_event(
        project_path,
        run_id,
        "HUMAN_APPROVED",
        task_id,
        {"approval_id": approval["approval_id"], "actor": actor},
    )
    return dict(approval)


async def dispatch(args: argparse.Namespace, repository_root: Path) -> object:
    """검증된 CLI 인자를 단일 Runtime 명령에 전달한다."""
    if args.command == "doctor":
        return await doctor_document(repository_root)
    if args.command == "providers":
        return {"providers": await provider_documents(repository_root)}
    if args.command == "plan":
        project_path = resolved_project_path(args.project_path)
        from_gate = inferred_from_gate(project_path, args.from_gate)
        plan: ExecutionPlan = build_execution_plan(
            repository_root,
            project_path,
            from_gate,
            args.to_gate,
        )
        return plan
    if args.command == "run":
        project_path = resolved_project_path(args.project_path)
        from_gate = inferred_from_gate(project_path, args.from_gate)
        reference_source = (
            args.reference_source.expanduser().resolve()
            if args.reference_source is not None
            else None
        )
        run: RuntimeRun = await execute_run(
            repository_root,
            project_path,
            from_gate,
            args.to_gate,
            args.route_profile,
            reference_source,
            None,
        )
        return run
    if args.command == "resume":
        return await resume_run(repository_root, args.run_id, None)
    if args.command == "status":
        return status_document(repository_root, args.target)
    if args.command == "approve":
        return approval_document(
            repository_root,
            args.run_id,
            args.task_id,
            args.actor,
            args.reason,
        )
    if args.command == "submit-input":
        if args.task_id != "reference.build_evidence":
            raise RuntimeExecutionError(
                "RUNTIME_CONFIGURATION_ERROR",
                False,
                "CLI",
                "현재 지원하는 Human Input Task는 reference.build_evidence뿐입니다.",
                args.task_id,
                None,
                {},
            )
        project_path, _run = find_run(repository_root, args.run_id)
        return submit_evidence_input(
            project_path,
            args.run_id,
            load_json_object(args.input_path.expanduser().resolve()),
        )
    if args.command == "cancel":
        return request_cancel(repository_root, args.run_id)
    raise RuntimeExecutionError(
        "RUNTIME_CONFIGURATION_ERROR",
        False,
        "CLI",
        "구현되지 않은 Runtime 명령입니다.",
        None,
        None,
        {"command": args.command},
    )


def run_cli(argv: Sequence[str]) -> int:
    """테스트 가능한 Runtime CLI 진입점을 실행하고 종료 코드를 반환한다."""
    parser = build_parser()
    args = parser.parse_args(list(argv))
    repository_root = args.repository_root.expanduser().resolve()
    try:
        result = asyncio.run(dispatch(args, repository_root))
    except RuntimeExecutionError as error:
        print_json({"status": "ERROR", "error": error.as_dict()}, sys.stderr)
        return 2
    except StarterKitError as error:
        print_json(
            {
                "status": "ERROR",
                "error": {
                    "code": "RUNTIME_CONFIGURATION_ERROR",
                    "message": str(error),
                },
            },
            sys.stderr,
        )
        return 2
    print_json(result, sys.stdout)
    return 0


def main() -> None:
    """Console Script에서 Runtime CLI 종료 코드를 전달한다."""
    raise SystemExit(run_cli(sys.argv[1:]))


if __name__ == "__main__":
    main()
