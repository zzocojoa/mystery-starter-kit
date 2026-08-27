"""Runtime 계약 로딩과 권한·버전 정합성 검증."""

from collections.abc import Mapping
from pathlib import Path
from typing import cast

from RUNTIME.errors import RuntimeExecutionError
from RUNTIME.models import ArtifactContract, RuntimeTask
from VALIDATORS.agent_validation import manifest_agents, string_list, validate_agent_manifest
from VALIDATORS.compatibility import parse_semantic_version
from VALIDATORS.dependency import dependency_artifacts, validate_dependency_graph
from VALIDATORS.io import load_json_object
from VALIDATORS.schema_validation import collect_schema_errors
from VALIDATORS.state_machine import gate_index


def configuration_error(message: str, context: dict[str, object]) -> RuntimeExecutionError:
    """계약 오류를 공통 Runtime 오류로 변환한다."""
    return RuntimeExecutionError(
        "RUNTIME_CONFIGURATION_ERROR",
        False,
        "RUNTIME",
        message,
        None,
        None,
        context,
    )


def require_mapping(
    document: Mapping[str, object],
    key: str,
    source: str,
) -> dict[str, object]:
    """계약 문서의 필수 객체를 엄격하게 읽는다."""
    value = document.get(key)
    if not isinstance(value, Mapping):
        raise configuration_error(
            "Runtime 계약의 필수 객체가 없습니다.",
            {"source": source, "field": key},
        )
    return cast(dict[str, object], dict(value))


def require_string_list(
    document: Mapping[str, object],
    key: str,
    source: str,
) -> list[str]:
    """계약 문서의 필수 문자열 배열을 엄격하게 읽는다."""
    value = document.get(key)
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise configuration_error(
            "Runtime 계약의 문자열 배열 형식이 올바르지 않습니다.",
            {"source": source, "field": key},
        )
    return cast(list[str], value.copy())


def validate_against_schema(
    document: Mapping[str, object],
    schema_path: Path,
    source_path: Path,
) -> None:
    """Runtime JSON 계약을 선언 Schema로 검증한다."""
    schema = load_json_object(schema_path)
    errors = collect_schema_errors(document, schema, str(source_path))
    if errors:
        raise configuration_error(
            "Runtime 계약 Schema 검증에 실패했습니다.",
            {"source": str(source_path), "errors": errors},
        )


def load_contract(
    repository_root: Path,
    relative_path: str,
    schema_relative_path: str,
) -> dict[str, object]:
    """Repository 내부 Runtime 계약을 읽고 Schema를 검증한다."""
    contract_path = repository_root / relative_path
    schema_path = repository_root / schema_relative_path
    document = load_json_object(contract_path)
    validate_against_schema(document, schema_path, contract_path)
    return document


def load_runtime_contract(repository_root: Path) -> dict[str, object]:
    """Runtime Compatibility Contract를 반환한다."""
    return load_contract(
        repository_root,
        "RUNTIME/contracts/runtime_contract.json",
        "RUNTIME/schemas/runtime_contract.schema.json",
    )


def load_runtime_config(repository_root: Path) -> dict[str, object]:
    """Runtime 구성 파일 경계와 기본 Route Profile을 반환한다."""
    return load_contract(
        repository_root,
        "RUNTIME/contracts/runtime_config.json",
        "RUNTIME/schemas/runtime_config.schema.json",
    )


def configured_contract_path(
    repository_root: Path,
    field: str,
) -> str:
    """Runtime Config에서 필수 계약의 Repository 상대 경로를 읽는다."""
    runtime_config = load_runtime_config(repository_root)
    relative_path = runtime_config.get(field)
    if not isinstance(relative_path, str):
        raise configuration_error(
            "Runtime Config 계약 경로가 문자열이 아닙니다.",
            {"field": field},
        )
    return relative_path


def load_task_catalog(repository_root: Path) -> dict[str, RuntimeTask]:
    """Task Catalog를 엄격한 Task 사전으로 반환한다."""
    document = load_contract(
        repository_root,
        configured_contract_path(repository_root, "task_catalog"),
        "RUNTIME/schemas/runtime_task_catalog.schema.json",
    )
    tasks = require_mapping(document, "tasks", "runtime_tasks")
    normalized: dict[str, RuntimeTask] = {}
    for task_id, definition in tasks.items():
        if not isinstance(definition, Mapping):
            raise configuration_error(
                "Runtime Task 정의가 객체가 아닙니다.",
                {"task_id": task_id},
            )
        normalized[task_id] = cast(RuntimeTask, dict(definition))
    return normalized


def load_artifact_contracts(repository_root: Path) -> dict[str, ArtifactContract]:
    """Artifact 출력 계약을 엄격한 사전으로 반환한다."""
    document = load_contract(
        repository_root,
        configured_contract_path(repository_root, "artifact_contracts"),
        "RUNTIME/schemas/artifact_contracts.schema.json",
    )
    artifacts = require_mapping(document, "artifacts", "artifact_contracts")
    normalized: dict[str, ArtifactContract] = {}
    for artifact_name, definition in artifacts.items():
        if not isinstance(definition, Mapping):
            raise configuration_error(
                "Artifact Contract 정의가 객체가 아닙니다.",
                {"artifact_name": artifact_name},
            )
        normalized[artifact_name] = cast(ArtifactContract, dict(definition))
    return normalized


def load_model_routes(repository_root: Path) -> dict[str, object]:
    """Model Profile, Route, Budget, Retry 계약을 반환한다."""
    return load_contract(
        repository_root,
        configured_contract_path(repository_root, "model_routes"),
        "RUNTIME/schemas/model_routes.schema.json",
    )


def load_provider_registry(repository_root: Path) -> dict[str, object]:
    """비밀 값이 아닌 Credential 환경 변수 참조만 포함한 Registry를 반환한다."""
    return load_contract(
        repository_root,
        configured_contract_path(repository_root, "provider_registry"),
        "RUNTIME/schemas/provider_registry.schema.json",
    )


def validate_supported_version(
    source_name: str,
    source_document: Mapping[str, object],
    version_range: Mapping[str, object],
) -> None:
    """Runtime이 소비하는 계약 Version이 선언 범위인지 검사한다."""
    family = source_document.get("schema_family")
    version = source_document.get("schema_version")
    expected_family = version_range.get("schema_family")
    minimum = version_range.get("min_inclusive")
    maximum = version_range.get("max_exclusive")
    if not all(
        isinstance(value, str) for value in (family, version, expected_family, minimum, maximum)
    ):
        raise configuration_error(
            "Runtime Version 계약 문자열이 누락되었습니다.",
            {"source": source_name},
        )
    family_value = cast(str, family)
    version_value = cast(str, version)
    expected_family_value = cast(str, expected_family)
    minimum_value = cast(str, minimum)
    maximum_value = cast(str, maximum)
    if family_value != expected_family_value:
        raise configuration_error(
            "Runtime이 지원하지 않는 계약 Family입니다.",
            {"source": source_name, "expected": expected_family_value, "actual": family_value},
        )
    parsed = parse_semantic_version(version_value)
    if not parse_semantic_version(minimum_value) <= parsed < parse_semantic_version(maximum_value):
        raise configuration_error(
            "Runtime이 지원하지 않는 계약 Version입니다.",
            {
                "source": source_name,
                "version": version_value,
                "minimum": minimum_value,
                "maximum": maximum_value,
            },
        )


def validate_task_subset_contracts(
    repository_root: Path,
    tasks: Mapping[str, RuntimeTask],
    agent_manifest: Mapping[str, object],
    dependency_graph: Mapping[str, object],
    artifact_contracts: Mapping[str, ArtifactContract],
    model_routes: Mapping[str, object],
) -> None:
    """Task가 Agent 최대 권한과 Artifact Owner를 확장하지 않는지 검사한다."""
    agents = manifest_agents(agent_manifest)
    artifact_definitions = dependency_artifacts(dependency_graph)
    profiles = require_mapping(model_routes, "profiles", "model_routes")
    known_tasks = set(tasks)
    for task_id, task in tasks.items():
        agent_id = task["agent_id"]
        agent = agents.get(agent_id)
        if agent is None:
            raise configuration_error(
                "Task가 알 수 없는 Agent를 참조합니다.",
                {"task_id": task_id, "agent_id": agent_id},
            )
        agent_reads = set(string_list(agent, "reads", agent_id))
        agent_writes = set(string_list(agent, "writes", agent_id))
        widened_reads = sorted(set(task["reads"]) - agent_reads)
        widened_writes = sorted(set(task["writes"]) - agent_writes)
        if widened_reads or widened_writes:
            raise configuration_error(
                "Task가 Agent 최대 권한을 확장합니다.",
                {
                    "task_id": task_id,
                    "widened_reads": widened_reads,
                    "widened_writes": widened_writes,
                },
            )
        agent_gates = set(string_list(agent, "gates", agent_id))
        if task["target_gate"] not in agent_gates:
            raise configuration_error(
                "Task Gate가 Agent Gate 계약에 없습니다.",
                {"task_id": task_id, "gate": task["target_gate"]},
            )
        unknown_dependencies = sorted(set(task["depends_on_tasks"]) - known_tasks)
        if unknown_dependencies:
            raise configuration_error(
                "Task가 알 수 없는 선행 Task를 참조합니다.",
                {"task_id": task_id, "depends_on_tasks": unknown_dependencies},
            )
        later_dependencies = sorted(
            dependency
            for dependency in task["depends_on_tasks"]
            if gate_index(tasks[dependency]["target_gate"]) > gate_index(task["target_gate"])
        )
        if later_dependencies:
            raise configuration_error(
                "Task 선행 관계가 Gate 순서를 역전합니다.",
                {"task_id": task_id, "depends_on_tasks": later_dependencies},
            )
        for artifact_name in task["writes"]:
            artifact_definition = artifact_definitions.get(artifact_name)
            if artifact_definition is None:
                raise configuration_error(
                    "Task가 Dependency Graph에 없는 Artifact를 씁니다.",
                    {"task_id": task_id, "artifact_name": artifact_name},
                )
            if artifact_definition.get("owner_agent") != agent_id:
                raise configuration_error(
                    "Task Agent와 Artifact Owner가 다릅니다.",
                    {
                        "task_id": task_id,
                        "artifact_name": artifact_name,
                        "owner_agent": artifact_definition.get("owner_agent"),
                    },
                )
            if artifact_name not in artifact_contracts:
                raise configuration_error(
                    "Task 출력의 Artifact Contract가 없습니다.",
                    {"task_id": task_id, "artifact_name": artifact_name},
                )
        for resource in task["standard_resources"]:
            resource_path = (repository_root / resource).resolve()
            try:
                resource_path.relative_to(repository_root.resolve())
            except ValueError as error:
                raise configuration_error(
                    "Task Resource가 Repository 밖을 참조합니다.",
                    {"task_id": task_id, "resource": resource},
                ) from error
            if "EXAMPLES" in resource_path.parts or not resource_path.is_file():
                raise configuration_error(
                    "Task Resource가 없거나 EXAMPLES를 참조합니다.",
                    {"task_id": task_id, "resource": resource},
                )
        profile = task["model_profile"]
        if task["executor"] == "LLM" and (profile is None or profile not in profiles):
            raise configuration_error(
                "LLM Task의 Model Profile이 없거나 알 수 없습니다.",
                {"task_id": task_id, "model_profile": profile},
            )
        if task["executor"] == "CORE" and profile is not None:
            raise configuration_error(
                "CORE Task는 Model Profile을 참조할 수 없습니다.",
                {"task_id": task_id, "model_profile": profile},
            )


def validate_artifact_schema_paths(
    repository_root: Path,
    contracts: Mapping[str, ArtifactContract],
) -> None:
    """모든 JSON Artifact가 실제 Schema를 참조하는지 검사한다."""
    for artifact_name, contract in contracts.items():
        schema_reference = contract["schema"]
        if contract["media_type"] == "application/json" and schema_reference is None:
            raise configuration_error(
                "JSON Artifact에 Schema가 없습니다.",
                {"artifact_name": artifact_name},
            )
        if schema_reference is None:
            continue
        schema_path = repository_root / schema_reference.split("#", maxsplit=1)[0]
        if not schema_path.is_file():
            raise configuration_error(
                "Artifact Schema 파일을 찾을 수 없습니다.",
                {"artifact_name": artifact_name, "schema": schema_reference},
            )


def validate_runtime_config_paths(
    repository_root: Path,
    runtime_config: Mapping[str, object],
) -> None:
    """Runtime Config가 Repository 내부의 실제 계약 파일만 가리키는지 검사한다."""
    for field in ("provider_registry", "model_routes", "task_catalog", "artifact_contracts"):
        relative_path = runtime_config.get(field)
        if not isinstance(relative_path, str):
            raise configuration_error(
                "Runtime Config 계약 경로가 문자열이 아닙니다.",
                {"field": field},
            )
        contract_path = (repository_root / relative_path).resolve()
        try:
            contract_path.relative_to(repository_root.resolve())
        except ValueError as error:
            raise configuration_error(
                "Runtime Config 계약 경로가 Repository 밖을 참조합니다.",
                {"field": field, "path": relative_path},
            ) from error
        if not contract_path.is_file():
            raise configuration_error(
                "Runtime Config 계약 파일을 찾을 수 없습니다.",
                {"field": field, "path": relative_path},
            )


def validate_runtime_contracts(repository_root: Path) -> dict[str, object]:
    """Runtime v1.0의 모든 정적 계약을 교차 검증하고 요약을 반환한다."""
    runtime_contract = load_runtime_contract(repository_root)
    runtime_config = load_runtime_config(repository_root)
    task_catalog = load_task_catalog(repository_root)
    artifact_contracts = load_artifact_contracts(repository_root)
    model_routes = load_model_routes(repository_root)
    provider_registry = load_provider_registry(repository_root)
    agent_manifest = load_json_object(repository_root / "AGENTS" / "manifest.json")
    dependency_graph = load_json_object(repository_root / "STANDARD" / "dependency_graph.json")
    validate_agent_manifest(agent_manifest, dependency_graph, repository_root / "AGENTS")
    validate_dependency_graph(dependency_graph)
    supported = require_mapping(runtime_contract, "supported_contracts", "runtime_contract")
    for source_name, document in (
        ("agent_manifest", agent_manifest),
        ("dependency_graph", dependency_graph),
    ):
        version_range = supported.get(source_name)
        if not isinstance(version_range, Mapping):
            raise configuration_error(
                "Runtime 지원 계약 범위가 없습니다.",
                {"source": source_name},
            )
        validate_supported_version(source_name, document, version_range)
    validate_task_subset_contracts(
        repository_root,
        task_catalog,
        agent_manifest,
        dependency_graph,
        artifact_contracts,
        model_routes,
    )
    validate_runtime_config_paths(repository_root, runtime_config)
    validate_artifact_schema_paths(repository_root, artifact_contracts)
    providers = require_mapping(provider_registry, "providers", "provider_registry")
    return {
        "runtime_version": runtime_contract["schema_version"],
        "route_profile": runtime_config["route_profile"],
        "task_count": len(task_catalog),
        "artifact_contract_count": len(artifact_contracts),
        "provider_count": len(providers),
        "result": "PASS",
    }
