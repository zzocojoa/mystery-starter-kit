"""Task 계획, Provider 호출, Gate 검증, 원자 Commit을 조정하는 Runtime Core."""

import json
from collections.abc import Mapping, Sequence
from copy import deepcopy
from hashlib import sha256
from pathlib import Path
from typing import cast
from uuid import uuid4

from RUNTIME.approvals import approval_is_current
from RUNTIME.context import build_minimal_context, context_data_classes, context_input_hashes
from RUNTIME.contracts import (
    load_artifact_contracts,
    load_model_routes,
    load_provider_registry,
    load_runtime_config,
    load_task_catalog,
    validate_runtime_contracts,
)
from RUNTIME.core_tasks import (
    combined_artifacts,
    core_task_outputs,
    mapping_artifact,
    runtime_validation_inputs,
    story_history,
)
from RUNTIME.errors import RuntimeExecutionError
from RUNTIME.event_store import (
    append_event,
    create_run,
    find_run,
    load_run,
    save_run,
    update_run_status,
    update_task_state,
    utc_now,
    write_attempt_document,
    write_provenance,
)
from RUNTIME.gate_control import validate_gate
from RUNTIME.models import (
    ContextItem,
    GenerationOptions,
    LLMMessage,
    LLMProvider,
    LLMRequest,
    OutputContract,
    OutputMode,
    PromptBundle,
    RunStatus,
    RuntimeRun,
    RuntimeTask,
    SelectedRoute,
    TokenUsage,
)
from RUNTIME.output_gateway import (
    encoded_artifact,
    validate_agent_result,
    validate_core_outputs,
)
from RUNTIME.planner import (
    build_execution_plan,
    next_gate_id,
    task_condition_matches,
    tasks_in_gate_range,
    topological_task_ids,
)
from RUNTIME.prompt_compiler import compile_prompt, prompt_token_estimate
from RUNTIME.providers.base import request_document, response_document
from RUNTIME.providers.registry import build_provider_registry, close_providers
from RUNTIME.router import budget_values, retry_values, route_candidates
from RUNTIME.transactions import (
    acquire_project_lock,
    capture_artifact_hashes,
    commit_gate_transaction,
    create_staging_overlay,
    next_project_state,
    recover_prepared_transactions,
    release_project_lock,
    verify_artifact_hashes,
)
from VALIDATORS.agent_validation import manifest_agents
from VALIDATORS.change_log import append_change_log
from VALIDATORS.dependency import artifact_hash, dependency_artifacts
from VALIDATORS.exceptions import StarterKitError
from VALIDATORS.gate_transaction import (
    PROCESS_TRACE_PATH,
    build_gate_traces,
    gate_commit_sha,
    process_conformance,
    process_trace_bytes,
    trace_records,
)
from VALIDATORS.io import load_json_object, write_json_object
from VALIDATORS.models import ProjectState, ValidationIssue
from VALIDATORS.pipeline import load_project_artifacts
from VALIDATORS.schema_validation import collect_schema_errors
from VALIDATORS.state_machine import gate_index


def project_state(project_path: Path) -> ProjectState:
    """현재 Canonical Project State를 반환한다."""
    return cast(
        ProjectState,
        load_json_object(project_path / "00_PROJECT" / "project_state.json"),
    )


def mark_project_blocked(project_path: Path) -> None:
    """최대 시도 초과로 Project의 마지막 통과 Gate를 유지한 채 BLOCKED 처리한다."""
    state = deepcopy(project_state(project_path))
    state["state"] = "BLOCKED"
    state["updated_at"] = utc_now()
    write_json_object(project_path / "00_PROJECT" / "project_state.json", state)


def gate_ids(from_gate: str, to_gate: str) -> list[str]:
    """시작부터 종료까지 포함하는 연속 Gate ID를 반환한다."""
    return [f"GATE-{index:02d}" for index in range(gate_index(from_gate), gate_index(to_gate) + 1)]


def task_prompt_file(
    agent_manifest: Mapping[str, object],
    task: RuntimeTask,
) -> str:
    """Task Agent의 Prompt 파일 이름을 반환한다."""
    agents = manifest_agents(agent_manifest)
    definition = agents.get(task["agent_id"])
    prompt_file = None if definition is None else definition.get("prompt_file")
    if not isinstance(prompt_file, str):
        raise RuntimeExecutionError(
            "RUNTIME_CONFIGURATION_ERROR",
            False,
            "TASK",
            "Task Agent Prompt가 없습니다.",
            None,
            None,
            {"agent_id": task["agent_id"]},
        )
    return prompt_file


def approved_selection_document(
    project_path: Path,
    dependency_graph: Mapping[str, object],
    overlay: Mapping[str, object],
) -> dict[str, str]:
    """승인 Variation Selection을 Provider Metadata용 문자열 사전으로 읽는다."""
    artifacts = combined_artifacts(project_path, dependency_graph, overlay)
    variations = mapping_artifact(artifacts, "variation_candidates")
    approved_id = variations.get("approved_candidate_id")
    candidates = variations.get("candidates")
    if not isinstance(approved_id, str) or not isinstance(candidates, list):
        raise RuntimeExecutionError(
            "RUNTIME_CONFIGURATION_ERROR",
            False,
            "TASK",
            "승인 Variation이 없습니다.",
            None,
            "variation_candidates",
            {},
        )
    approved = next(
        (
            candidate
            for candidate in candidates
            if isinstance(candidate, Mapping) and candidate.get("candidate_id") == approved_id
        ),
        None,
    )
    selection = None if approved is None else approved.get("selection")
    if not isinstance(selection, Mapping) or not all(
        isinstance(key, str) and isinstance(value, str) for key, value in selection.items()
    ):
        raise RuntimeExecutionError(
            "RUNTIME_CONFIGURATION_ERROR",
            False,
            "TASK",
            "승인 Variation Selection 형식이 올바르지 않습니다.",
            None,
            "variation_candidates",
            {},
        )
    return {str(key): cast(str, value) for key, value in selection.items()}


def output_mode(provider: LLMProvider) -> OutputMode:
    """Provider Capability에 맞는 가장 엄격한 출력 Mode를 선택한다."""
    capabilities = set(provider.descriptor.capabilities)
    if "JSON_SCHEMA_OUTPUT" in capabilities:
        return "JSON_SCHEMA"
    if "JSON_OBJECT" in capabilities:
        return "JSON_OBJECT"
    return "TEXT"


def revision_message(
    issues: Sequence[ValidationIssue], allowed_artifacts: Sequence[str]
) -> LLMMessage:
    """Gate Issue와 허용 수정 범위만 포함한 Semantic Revision 메시지를 만든다."""
    document = {
        "instruction": "아래 검증 Issue만 수정하고 Task writes 밖의 Artifact는 반환하지 않는다.",
        "allowed_artifacts": list(allowed_artifacts),
        "issues": list(issues),
    }
    body = json.dumps(document, ensure_ascii=False, sort_keys=True)
    return LLMMessage(role="user", content=f"<REVISION_REQUEST>\n{body}\n</REVISION_REQUEST>")


def build_request(
    run: RuntimeRun,
    task_id: str,
    task: RuntimeTask,
    attempt: int,
    route: SelectedRoute,
    bundle: PromptBundle,
    output_schema: dict[str, object],
    max_output_tokens: int,
    source_mode: str,
    target_runtime_minutes: int,
    approved_selection: Mapping[str, str],
    revision_issues: Sequence[ValidationIssue],
) -> LLMRequest:
    """감사 Metadata와 Output Contract를 포함한 Provider 요청을 만든다."""
    messages = bundle["messages"]
    if revision_issues:
        messages = (*messages, revision_message(revision_issues, task["writes"]))
    request_id = f"REQ-{uuid4().hex[:16].upper()}"
    idempotency_payload = f"{run['run_id']}|{task_id}|{bundle['prompt_hash']}|{attempt}"
    return LLMRequest(
        request_id=request_id,
        idempotency_key=sha256(idempotency_payload.encode("utf-8")).hexdigest(),
        model_ref=route["model_ref"],
        messages=messages,
        output_contract=OutputContract(
            mode=output_mode(route["provider"]),
            name=task["output_contract"],
            json_schema=output_schema,
        ),
        generation=GenerationOptions(
            max_output_tokens=max_output_tokens,
            temperature=0.3,
            top_p=1.0,
            seed=None,
            stop=(),
        ),
        tools=(),
        deadline_ms=120000,
        metadata={
            "run_id": run["run_id"],
            "task_id": task_id,
            "agent_id": task["agent_id"],
            "attempt": str(attempt),
            "project_id": run["project_id"],
            "story_source_mode": source_mode,
            "target_runtime_minutes": str(target_runtime_minutes),
            "approved_selection": json.dumps(
                dict(approved_selection),
                ensure_ascii=False,
                sort_keys=True,
            ),
        },
        extensions={},
    )


def validate_request_schema(repository_root: Path, request: LLMRequest) -> None:
    """Provider 호출 전에 공통 Wire Request Schema를 검증한다."""
    document = request_document(request)
    schema = load_json_object(repository_root / "RUNTIME" / "schemas" / "llm_request.schema.json")
    errors = collect_schema_errors(document, schema, "llm_request")
    if errors:
        raise RuntimeExecutionError(
            "RUNTIME_CONFIGURATION_ERROR",
            False,
            "TASK_ATTEMPT",
            "LLM Request Schema 검증에 실패했습니다.",
            request.metadata.get("task_id"),
            None,
            {"errors": errors},
        )


def validate_response_schema(
    repository_root: Path,
    response: Mapping[str, object],
    expected_request_id: str,
    task_id: str,
) -> None:
    """Provider 공통 응답 Schema와 Request Identity를 검증한다."""
    schema = load_json_object(repository_root / "RUNTIME" / "schemas" / "llm_response.schema.json")
    errors = collect_schema_errors(response, schema, "llm_response")
    if errors:
        raise RuntimeExecutionError(
            "OUTPUT_PARSE_ERROR",
            True,
            "TASK_ATTEMPT",
            "LLM Response Schema 검증에 실패했습니다.",
            task_id,
            None,
            {"errors": errors},
        )
    if response.get("request_id") != expected_request_id:
        raise RuntimeExecutionError(
            "PROVIDER_FAILURE",
            False,
            "TASK_ATTEMPT",
            "Provider Response가 Request ID를 보존하지 않았습니다.",
            task_id,
            None,
            {
                "expected_request_id": expected_request_id,
                "actual_request_id": response.get("request_id"),
            },
        )


async def generate_with_transport_retry(
    project_path: Path,
    run: RuntimeRun,
    task_id: str,
    task: RuntimeTask,
    routes: Sequence[SelectedRoute],
    bundle: PromptBundle,
    output_schema: dict[str, object],
    max_output_tokens: int,
    source_mode: str,
    target_runtime_minutes: int,
    approved_selection: Mapping[str, str],
    revision_issues: Sequence[ValidationIssue],
    starting_attempt: int,
    transport_attempts: int,
    max_attempts: int,
    repository_root: Path,
) -> tuple[dict[str, object], str, str, int, TokenUsage, RuntimeRun]:
    """Transport 실패에만 같은 Route 재시도와 다음 Route 전환을 허용한다."""
    current_run = run
    attempt = starting_attempt
    last_error: RuntimeExecutionError | None = None
    for route in routes:
        for _transport_attempt in range(transport_attempts):
            if attempt > max_attempts:
                break
            request = build_request(
                current_run,
                task_id,
                task,
                attempt,
                route,
                bundle,
                output_schema,
                max_output_tokens,
                source_mode,
                target_runtime_minutes,
                approved_selection,
                revision_issues,
            )
            validate_request_schema(repository_root, request)
            current_run = update_task_state(
                project_path,
                current_run,
                task_id,
                "RUNNING",
                attempt,
                route["provider_id"],
                route["model_ref"],
                bundle["input_hashes"],
                bundle["prompt_hash"],
                None,
            )
            append_event(
                project_path,
                current_run["run_id"],
                "PROVIDER_SELECTED",
                task_id,
                {"provider_id": route["provider_id"], "model_ref": route["model_ref"]},
            )
            write_attempt_document(
                project_path,
                current_run["run_id"],
                task_id,
                attempt,
                "request.json",
                request_document(request),
            )
            append_event(
                project_path,
                current_run["run_id"],
                "PROVIDER_REQUESTED",
                task_id,
                {"attempt": attempt},
            )
            try:
                response = await route["provider"].generate(request)
            except RuntimeExecutionError as error:
                last_error = error
                attempt += 1
                if not error.retryable:
                    raise
                continue
            response_wire = response_document(response)
            write_attempt_document(
                project_path,
                current_run["run_id"],
                task_id,
                attempt,
                "response.json",
                response_wire,
            )
            validate_response_schema(
                repository_root,
                response_wire,
                request.request_id,
                task_id,
            )
            append_event(
                project_path,
                current_run["run_id"],
                "PROVIDER_RESPONDED",
                task_id,
                {
                    "attempt": attempt,
                    "status": response.status,
                    "finish_reason": response.finish_reason,
                    "input_tokens": response.usage.input_tokens,
                    "output_tokens": response.usage.output_tokens,
                },
            )
            return (
                validate_agent_result(
                    repository_root,
                    response,
                    current_run["run_id"],
                    task_id,
                    task,
                    attempt,
                    load_artifact_contracts(repository_root),
                ),
                route["provider_id"],
                response.model_resolved,
                attempt,
                response.usage,
                current_run,
            )
    if last_error is not None:
        raise last_error
    raise RuntimeExecutionError(
        "BUDGET_EXCEEDED",
        False,
        "TASK",
        "Task 최대 Provider 시도 횟수를 초과했습니다.",
        task_id,
        None,
        {"max_attempts": max_attempts},
    )


async def execute_llm_task(
    repository_root: Path,
    project_path: Path,
    run: RuntimeRun,
    task_id: str,
    task: RuntimeTask,
    dependency_graph: Mapping[str, object],
    gate_outputs: Mapping[str, object],
    providers: Mapping[str, LLMProvider],
    provider_registry: Mapping[str, object],
    model_routes: Mapping[str, object],
    agent_manifest: Mapping[str, object],
    source_mode: str,
    target_runtime_minutes: int,
    revision_issues: Sequence[ValidationIssue],
) -> tuple[dict[str, object], dict[str, object], RuntimeRun]:
    """Context, Prompt, Route, Retry, Output Gateway를 거쳐 LLM Task를 실행한다."""
    items = build_minimal_context(
        repository_root,
        project_path,
        task_id,
        task,
        dependency_graph,
        cast(Mapping[str, Mapping[str, object] | str], gate_outputs),
    )
    output_schema = load_json_object(
        repository_root / "RUNTIME" / "schemas" / "agent_result.schema.json"
    )
    bundle = compile_prompt(
        repository_root,
        task_id,
        task,
        task_prompt_file(agent_manifest, task),
        items,
        output_schema,
    )
    max_input_tokens, max_output_tokens, max_attempts = budget_values(
        model_routes,
        task["budget_profile"],
    )
    input_tokens = prompt_token_estimate(bundle)
    if input_tokens > max_input_tokens:
        raise RuntimeExecutionError(
            "CONTEXT_LIMIT_EXCEEDED",
            False,
            "TASK",
            "Task Prompt가 Budget Context Limit을 초과했습니다.",
            task_id,
            None,
            {"estimated_tokens": input_tokens, "max_input_tokens": max_input_tokens},
        )
    profile = task["model_profile"]
    if profile is None:
        raise RuntimeExecutionError(
            "RUNTIME_CONFIGURATION_ERROR",
            False,
            "TASK",
            "LLM Task Model Profile이 없습니다.",
            task_id,
            None,
            {},
        )
    routes = route_candidates(
        profile,
        providers,
        provider_registry,
        model_routes,
        context_data_classes(items),
        input_tokens,
        max_output_tokens,
    )
    transport_attempts, format_attempts, _semantic_attempts = retry_values(
        model_routes,
        task["retry_policy"],
    )
    current_run = run
    last_error: RuntimeExecutionError | None = None
    for _format_attempt in range(format_attempts):
        starting_attempt = current_run["tasks"][task_id]["attempt"] + 1
        try:
            (
                outputs,
                provider_id,
                model_resolved,
                attempt,
                usage,
                current_run,
            ) = await generate_with_transport_retry(
                project_path,
                current_run,
                task_id,
                task,
                routes,
                bundle,
                output_schema,
                max_output_tokens,
                source_mode,
                target_runtime_minutes,
                approved_selection_document(project_path, dependency_graph, gate_outputs),
                revision_issues,
                starting_attempt,
                transport_attempts,
                max_attempts,
                repository_root,
            )
            provenance = {
                "task_id": task_id,
                "provider_id": provider_id,
                "model_resolved": model_resolved,
                "attempt": attempt,
                "prompt_hash": bundle["prompt_hash"],
                "input_hashes": bundle["input_hashes"],
                "usage": {
                    "input_tokens": usage.input_tokens,
                    "output_tokens": usage.output_tokens,
                    "cached_tokens": usage.cached_tokens,
                },
            }
            current_run = update_task_state(
                project_path,
                current_run,
                task_id,
                "SUCCEEDED",
                attempt,
                provider_id,
                model_resolved,
                bundle["input_hashes"],
                bundle["prompt_hash"],
                None,
            )
            append_event(
                project_path,
                current_run["run_id"],
                "OUTPUT_VALIDATED",
                task_id,
                {"artifacts": sorted(outputs)},
            )
            return outputs, provenance, current_run
        except RuntimeExecutionError as error:
            last_error = error
            if (
                error.code not in {"OUTPUT_PARSE_ERROR", "OUTPUT_SCHEMA_ERROR"}
                or not error.retryable
            ):
                raise
            current_run = load_run(project_path, current_run["run_id"])
            current_run = update_task_state(
                project_path,
                current_run,
                task_id,
                "RETRYING",
                current_run["tasks"][task_id]["attempt"],
                current_run["tasks"][task_id]["provider_id"],
                current_run["tasks"][task_id]["model_resolved"],
                bundle["input_hashes"],
                bundle["prompt_hash"],
                error.as_dict(),
            )
    if last_error is not None:
        raise last_error
    raise RuntimeExecutionError(
        "OUTPUT_PARSE_ERROR",
        False,
        "TASK",
        "Format Repair 시도 상태가 손상되었습니다.",
        task_id,
        None,
        {},
    )


def gate_canonical_inputs(
    ordered_task_ids: Sequence[str],
    tasks: Mapping[str, RuntimeTask],
) -> list[str]:
    """같은 Gate 이전 Task가 만들지 않는 Canonical Read Artifact를 반환한다."""
    produced: set[str] = set()
    canonical: list[str] = []
    for task_id in ordered_task_ids:
        task = tasks[task_id]
        for artifact_name in task["reads"]:
            if artifact_name not in produced and artifact_name not in canonical:
                canonical.append(artifact_name)
        produced.update(task["writes"])
    return canonical


def semantic_attempt_limit(
    task_ids: Sequence[str],
    tasks: Mapping[str, RuntimeTask],
    model_routes: Mapping[str, object],
) -> int:
    """Gate 안 LLM Task 중 가장 큰 Semantic Revision 횟수를 반환한다."""
    limits = [
        retry_values(model_routes, tasks[task_id]["retry_policy"])[2]
        for task_id in task_ids
        if tasks[task_id]["executor"] == "LLM"
    ]
    return max(limits) if limits else 1


def reference_material(reference_source: Path | None) -> Mapping[str, object] | None:
    """격리된 Reference Source를 CORE Gate 검증에서만 읽는다."""
    return load_json_object(reference_source) if reference_source is not None else None


async def execute_existing_run(
    repository_root: Path,
    project_path: Path,
    run: RuntimeRun,
    provider_overrides: Mapping[str, LLMProvider] | None,
) -> RuntimeRun:
    """생성되었거나 중단된 Run을 현재 Canonical Gate부터 끝까지 실행한다."""
    validate_runtime_contracts(repository_root)
    runtime_config = load_runtime_config(repository_root)
    configured_route_profile = runtime_config.get("route_profile")
    if run["route_profile"] != configured_route_profile:
        raise RuntimeExecutionError(
            "RUNTIME_CONFIGURATION_ERROR",
            False,
            "RUN",
            "Run Route Profile이 Runtime Config와 다릅니다.",
            None,
            None,
            {
                "route_profile": run["route_profile"],
                "configured_route_profile": configured_route_profile,
            },
        )
    task_catalog = load_task_catalog(repository_root)
    artifact_contracts = load_artifact_contracts(repository_root)
    model_routes = load_model_routes(repository_root)
    provider_registry_document = load_provider_registry(repository_root)
    agent_manifest = load_json_object(repository_root / "AGENTS" / "manifest.json")
    dependency_graph = load_json_object(repository_root / "STANDARD" / "dependency_graph.json")
    production_config = load_json_object(project_path / "00_PROJECT" / "production_config.json")
    source_mode = production_config.get("story_source_mode")
    if not isinstance(source_mode, str):
        raise RuntimeExecutionError(
            "RUNTIME_CONFIGURATION_ERROR",
            False,
            "RUN",
            "Production Config Source Mode가 없습니다.",
            None,
            None,
            {},
        )
    target_runtime_minutes = production_config.get("target_runtime_minutes")
    if (
        not isinstance(target_runtime_minutes, int)
        or isinstance(target_runtime_minutes, bool)
        or target_runtime_minutes < 1
    ):
        raise RuntimeExecutionError(
            "RUNTIME_CONFIGURATION_ERROR",
            False,
            "RUN",
            "Production Config Target Runtime이 올바르지 않습니다.",
            None,
            "production_config",
            {"target_runtime_minutes": target_runtime_minutes},
        )
    providers = (
        dict(provider_overrides)
        if provider_overrides is not None
        else await build_provider_registry(provider_registry_document)
    )
    lock_path = acquire_project_lock(project_path, run["run_id"])
    current_run = run
    try:
        recovered = recover_prepared_transactions(project_path)
        current_run = update_run_status(project_path, current_run, "RUNNING", None, None)
        if recovered:
            append_event(
                project_path,
                current_run["run_id"],
                "PLAN_CREATED",
                None,
                {"recovered_transactions": recovered},
            )
        current_gate = project_state(project_path)["current_gate"]
        from_gate = next_gate_id(current_gate)
        ranged_tasks = tasks_in_gate_range(task_catalog, from_gate, current_run["to_gate"])
        ordered_all = topological_task_ids(ranged_tasks)
        reference_source = (
            Path(current_run["reference_source"])
            if current_run["reference_source"] is not None
            else None
        )
        (
            channel,
            story_schema,
            fingerprint_schema,
            presentation_schemas,
            policy,
            thresholds,
        ) = runtime_validation_inputs(repository_root)
        for gate_id in gate_ids(from_gate, current_run["to_gate"]):
            gate_started_at = utc_now()
            latest_run = load_run(project_path, current_run["run_id"])
            if latest_run["cancel_requested"]:
                raise RuntimeExecutionError(
                    "RUN_CANCELLED",
                    False,
                    "RUN",
                    "사용자가 Runtime Run 취소를 요청했습니다.",
                    latest_run["current_task_id"],
                    None,
                    {},
                )
            gate_task_ids = [
                task_id
                for task_id in ordered_all
                if ranged_tasks[task_id]["target_gate"] == gate_id
            ]
            canonical_inputs = gate_canonical_inputs(gate_task_ids, ranged_tasks)
            captured_hashes = capture_artifact_hashes(
                project_path, canonical_inputs, dependency_graph
            )
            revision_issues: list[ValidationIssue] = []
            attempt_limit = semantic_attempt_limit(gate_task_ids, ranged_tasks, model_routes)
            gate_committed = False
            for semantic_attempt in range(1, attempt_limit + 1):
                gate_outputs: dict[str, object] = {}
                output_provenance: dict[str, dict[str, object]] = {}
                for task_id in gate_task_ids:
                    task = ranged_tasks[task_id]
                    if not task_condition_matches(task["condition"], source_mode):
                        current_run = update_task_state(
                            project_path,
                            current_run,
                            task_id,
                            "SKIPPED",
                            current_run["tasks"][task_id]["attempt"],
                            None,
                            None,
                            {},
                            None,
                            None,
                        )
                        continue
                    items: list[ContextItem] = []
                    if task_id != "project.compatibility":
                        items = build_minimal_context(
                            repository_root,
                            project_path,
                            task_id,
                            task,
                            dependency_graph,
                            cast(Mapping[str, Mapping[str, object] | str], gate_outputs),
                        )
                    input_hashes = (
                        context_input_hashes(items)
                        if items
                        else capture_artifact_hashes(project_path, task["reads"], dependency_graph)
                    )
                    human_approval_needed = task["approval_required"] or (
                        task_id == "variation.generate"
                        and production_config.get("approval_policy") == "HUMAN_REVIEW"
                    )
                    approved = approval_is_current(
                        project_path,
                        current_run["run_id"],
                        task_id,
                        input_hashes,
                    )
                    if human_approval_needed and not approved:
                        current_run = update_task_state(
                            project_path,
                            current_run,
                            task_id,
                            "BLOCKED",
                            current_run["tasks"][task_id]["attempt"],
                            None,
                            None,
                            input_hashes,
                            None,
                            None,
                        )
                        raise RuntimeExecutionError(
                            "HUMAN_APPROVAL_REQUIRED",
                            False,
                            "TASK",
                            "Task 실행 전에 현재 Input Hash에 대한 Human Approval이 필요합니다.",
                            task_id,
                            None,
                            {"input_hashes": input_hashes},
                        )
                    append_event(
                        project_path,
                        current_run["run_id"],
                        "TASK_STARTED",
                        task_id,
                        {"semantic_attempt": semantic_attempt},
                    )
                    if task["executor"] == "CORE":
                        outputs = core_task_outputs(
                            task_id,
                            repository_root,
                            project_path,
                            gate_outputs,
                            dependency_graph,
                            reference_source,
                            approved,
                        )
                        validate_core_outputs(
                            repository_root,
                            task_id,
                            task,
                            outputs,
                            artifact_contracts,
                        )
                        current_run = update_task_state(
                            project_path,
                            current_run,
                            task_id,
                            "SUCCEEDED",
                            current_run["tasks"][task_id]["attempt"] + 1,
                            "core",
                            "deterministic",
                            input_hashes,
                            None,
                            None,
                        )
                        provenance = {
                            "task_id": task_id,
                            "provider_id": "core",
                            "model_resolved": "deterministic",
                            "attempt": current_run["tasks"][task_id]["attempt"],
                            "prompt_hash": None,
                            "input_hashes": input_hashes,
                        }
                    elif task["executor"] == "LLM":
                        outputs, provenance, current_run = await execute_llm_task(
                            repository_root,
                            project_path,
                            current_run,
                            task_id,
                            task,
                            dependency_graph,
                            gate_outputs,
                            providers,
                            provider_registry_document,
                            model_routes,
                            agent_manifest,
                            source_mode,
                            target_runtime_minutes,
                            revision_issues,
                        )
                    else:
                        raise RuntimeExecutionError(
                            "RUNTIME_CONFIGURATION_ERROR",
                            False,
                            "TASK",
                            "v1.0 실행기에 구현되지 않은 Executor입니다.",
                            task_id,
                            None,
                            {"executor": task["executor"]},
                        )
                    for artifact_name, content in outputs.items():
                        gate_outputs[artifact_name] = content
                        output_provenance[artifact_name] = provenance.copy()
                    append_event(
                        project_path,
                        current_run["run_id"],
                        "ARTIFACT_STAGED",
                        task_id,
                        {"artifacts": sorted(outputs)},
                    )
                staging_path = create_staging_overlay(
                    project_path,
                    current_run["run_id"],
                    gate_id,
                    semantic_attempt,
                    gate_outputs,
                    dependency_graph,
                )
                staged_artifacts = load_project_artifacts(staging_path, dependency_graph)
                current_run = update_run_status(
                    project_path,
                    current_run,
                    "VALIDATING",
                    current_run["current_task_id"],
                    None,
                )
                issues = validate_gate(
                    gate_id,
                    staged_artifacts,
                    channel,
                    story_schema,
                    fingerprint_schema,
                    presentation_schemas,
                    policy,
                    thresholds,
                    story_history(repository_root),
                    reference_material(reference_source),
                )
                if issues:
                    append_event(
                        project_path,
                        current_run["run_id"],
                        "GATE_FAILED",
                        None,
                        {"gate_id": gate_id, "issues": issues},
                    )
                    revision_issues = issues
                    llm_tasks = [
                        task_id
                        for task_id in gate_task_ids
                        if ranged_tasks[task_id]["executor"] == "LLM"
                    ]
                    if semantic_attempt < attempt_limit and llm_tasks:
                        current_run = update_run_status(
                            project_path, current_run, "REVISING", llm_tasks[0], None
                        )
                        append_event(
                            project_path,
                            current_run["run_id"],
                            "REVISION_REQUESTED",
                            llm_tasks[0],
                            {"gate_id": gate_id, "issue_count": len(issues)},
                        )
                        continue
                    mark_project_blocked(project_path)
                    raise RuntimeExecutionError(
                        "GATE_REJECTED",
                        False,
                        "GATE",
                        "Staging Overlay가 Gate 검증을 통과하지 못했습니다.",
                        current_run["current_task_id"],
                        None,
                        {"gate_id": gate_id, "issues": issues, "attempts": semantic_attempt},
                    )
                verify_artifact_hashes(project_path, captured_hashes, dependency_graph)
                next_state = next_project_state(
                    project_state(project_path),
                    gate_id,
                    captured_hashes,
                    gate_outputs,
                    dependency_graph,
                    utc_now(),
                )
                artifact_definitions = dependency_artifacts(dependency_graph)
                changed_artifacts = {
                    cast(str, artifact_definitions[artifact_name]["path"]): artifact_name
                    for artifact_name in gate_outputs
                }
                commit_sha = gate_commit_sha(gate_outputs, artifact_contracts)
                trace_context: dict[str, object] = {
                    "project_id": next_state["project_id"],
                    "gate_id": gate_id,
                    "input_hashes": captured_hashes,
                    "started_at": gate_started_at,
                }
                completed_at = utc_now()
                gate_tasks = {
                    task_id: ranged_tasks[task_id]
                    for task_id in gate_task_ids
                    if task_condition_matches(
                        ranged_tasks[task_id]["condition"],
                        source_mode,
                    )
                }
                traces = build_gate_traces(
                    trace_context,
                    gate_tasks,
                    changed_artifacts,
                    commit_sha,
                    completed_at,
                )
                existing_traces = trace_records(repository_root, project_path)
                conformant, missing_traces = process_conformance(
                    [*existing_traces, *traces],
                    next_state["readiness"]["process_start_gate"],
                    gate_id,
                )
                if not conformant:
                    raise RuntimeExecutionError(
                        "PROCESS_TRACE_MISSING",
                        False,
                        "GATE",
                        "현재 Gate까지의 Process Trace가 완전하지 않습니다.",
                        None,
                        None,
                        {
                            "process_start_gate": next_state["readiness"][
                                "process_start_gate"
                            ],
                            "through_gate": gate_id,
                            "missing_gate_traces": missing_traces,
                        },
                    )
                next_state["readiness"]["process_status"] = (
                    "PROCESS_CONFORMANT"
                    if conformant and gate_id == "GATE-13"
                    else "NONCONFORMANT"
                )
                transaction_id = commit_gate_transaction(
                    project_path,
                    current_run["run_id"],
                    gate_id,
                    staging_path,
                    gate_outputs,
                    dependency_graph,
                    next_state,
                    {PROCESS_TRACE_PATH: process_trace_bytes(project_path, traces)},
                )
                for artifact_name, content in gate_outputs.items():
                    provenance = output_provenance[artifact_name]
                    contract = artifact_contracts[artifact_name]
                    schema_reference = contract["schema"]
                    schema_hash = None
                    if schema_reference is not None:
                        schema_path = repository_root / schema_reference.split("#", maxsplit=1)[0]
                        schema_hash = artifact_hash(schema_path.read_bytes())
                    write_provenance(
                        project_path,
                        artifact_name,
                        {
                            "artifact_name": artifact_name,
                            "content_hash": artifact_hash(
                                encoded_artifact(content, contract["media_type"])
                            ),
                            "run_id": current_run["run_id"],
                            **provenance,
                            "schema_hash": schema_hash,
                            "transaction_id": transaction_id,
                            "committed_at": utc_now(),
                        },
                    )
                append_change_log(
                    project_path,
                    "RUNTIME_GATE_COMMITTED",
                    {
                        "run_id": current_run["run_id"],
                        "gate_id": gate_id,
                        "transaction_id": transaction_id,
                    },
                    utc_now(),
                )
                append_event(
                    project_path,
                    current_run["run_id"],
                    "ARTIFACT_COMMITTED",
                    None,
                    {
                        "gate_id": gate_id,
                        "transaction_id": transaction_id,
                        "artifacts": sorted(gate_outputs),
                    },
                )
                append_event(
                    project_path, current_run["run_id"], "GATE_PASSED", None, {"gate_id": gate_id}
                )
                current_run = update_run_status(project_path, current_run, "RUNNING", None, None)
                gate_committed = True
                break
            if not gate_committed:
                raise RuntimeExecutionError(
                    "GATE_REJECTED",
                    False,
                    "GATE",
                    "Gate Semantic Revision을 완료하지 못했습니다.",
                    current_run["current_task_id"],
                    None,
                    {"gate_id": gate_id},
                )
        current_run = update_run_status(project_path, current_run, "COMPLETED", None, None)
        append_event(
            project_path,
            current_run["run_id"],
            "RUN_COMPLETED",
            None,
            {"to_gate": current_run["to_gate"]},
        )
        return current_run
    except RuntimeExecutionError as error:
        current_run = load_run(project_path, current_run["run_id"])
        retry_exhausted_codes = {
            "BUDGET_EXCEEDED",
            "OUTPUT_PARSE_ERROR",
            "OUTPUT_SCHEMA_ERROR",
            "PROVIDER_NOT_AVAILABLE",
            "PROVIDER_RATE_LIMIT",
            "PROVIDER_TIMEOUT",
        }
        if error.code == "BUDGET_EXCEEDED" or (
            error.code in retry_exhausted_codes and error.retryable
        ):
            mark_project_blocked(project_path)
        status: RunStatus = (
            "WAITING_HUMAN"
            if error.code == "HUMAN_APPROVAL_REQUIRED"
            else "CANCELLED"
            if error.code == "RUN_CANCELLED"
            else "FAILED"
        )
        current_run = update_run_status(
            project_path,
            current_run,
            status,
            error.task_id,
            error.as_dict(),
        )
        event_type = (
            "HUMAN_REVIEW_REQUIRED"
            if status == "WAITING_HUMAN"
            else "RUN_CANCELLED"
            if status == "CANCELLED"
            else "RUN_FAILED"
        )
        append_event(
            project_path, current_run["run_id"], event_type, error.task_id, error.as_dict()
        )
        raise
    except StarterKitError as error:
        normalized = RuntimeExecutionError(
            "RUNTIME_CONFIGURATION_ERROR",
            False,
            "RUN",
            "Runtime 실행 중 Project 계약 또는 입출력 오류가 발생했습니다.",
            current_run["current_task_id"],
            None,
            {"error_type": type(error).__name__, "detail": str(error)},
        )
        current_run = load_run(project_path, current_run["run_id"])
        current_run = update_run_status(
            project_path,
            current_run,
            "FAILED",
            normalized.task_id,
            normalized.as_dict(),
        )
        append_event(
            project_path,
            current_run["run_id"],
            "RUN_FAILED",
            normalized.task_id,
            normalized.as_dict(),
        )
        raise normalized from error
    finally:
        await close_providers(providers)
        release_project_lock(lock_path, current_run["run_id"])


async def execute_run(
    repository_root: Path,
    project_path: Path,
    from_gate: str,
    to_gate: str,
    route_profile: str,
    reference_source: Path | None,
    provider_overrides: Mapping[str, LLMProvider] | None,
) -> RuntimeRun:
    """새 Runtime Run을 계획하고 실행한다."""
    validate_runtime_contracts(repository_root)
    plan = build_execution_plan(repository_root, project_path, from_gate, to_gate)
    task_ids = [task["task_id"] for task in plan["tasks"]]
    run = create_run(
        project_path,
        plan["project_id"],
        from_gate,
        to_gate,
        route_profile,
        reference_source,
        task_ids,
    )
    run = update_run_status(project_path, run, "PLANNED", None, None)
    append_event(project_path, run["run_id"], "PLAN_CREATED", None, {"tasks": plan["tasks"]})
    return await execute_existing_run(
        repository_root,
        project_path,
        run,
        provider_overrides,
    )


async def resume_run(
    repository_root: Path,
    run_id: str,
    provider_overrides: Mapping[str, LLMProvider] | None,
) -> RuntimeRun:
    """FAILED 또는 WAITING_HUMAN Run을 현재 Canonical 다음 Gate부터 재개한다."""
    project_path, run = find_run(repository_root, run_id)
    if run["status"] not in {"FAILED", "WAITING_HUMAN", "CANCELLED"}:
        raise RuntimeExecutionError(
            "RUNTIME_CONFIGURATION_ERROR",
            False,
            "RUN",
            "재개할 수 없는 Runtime Run 상태입니다.",
            run["current_task_id"],
            None,
            {"status": run["status"]},
        )
    next_run = deepcopy(run)
    next_run["cancel_requested"] = False
    next_run["status"] = "PLANNED"
    next_run["error"] = None
    save_run(project_path, next_run)
    return await execute_existing_run(
        repository_root,
        project_path,
        next_run,
        provider_overrides,
    )


def request_cancel(repository_root: Path, run_id: str) -> RuntimeRun:
    """Run 취소 요청을 Durable 상태로 기록한다."""
    project_path, run = find_run(repository_root, run_id)
    if run["status"] == "COMPLETED":
        raise RuntimeExecutionError(
            "RUNTIME_CONFIGURATION_ERROR",
            False,
            "RUN",
            "완료된 Runtime Run은 취소할 수 없습니다.",
            None,
            None,
            {"run_id": run_id},
        )
    next_run = deepcopy(run)
    next_run["cancel_requested"] = True
    next_run["updated_at"] = utc_now()
    if run["status"] in {"CREATED", "PLANNED", "FAILED", "WAITING_HUMAN"}:
        next_run["status"] = "CANCELLED"
    save_run(project_path, next_run)
    append_event(project_path, run_id, "RUN_CANCELLED", run["current_task_id"], {"requested": True})
    return next_run
