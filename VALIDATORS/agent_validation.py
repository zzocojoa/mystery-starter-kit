"""Agent Manifest 계약과 Production Context 격리 검증."""

from collections.abc import Mapping
from pathlib import Path
from typing import cast

from VALIDATORS.dependency import dependency_artifacts
from VALIDATORS.exceptions import ConfigurationError, InputFileNotFoundError


def manifest_agents(manifest: Mapping[str, object]) -> dict[str, dict[str, object]]:
    """Agent Manifest의 Agent 정의를 엄격하게 읽는다."""
    agents = manifest.get("agents")
    if not isinstance(agents, Mapping):
        raise ConfigurationError("agent_manifest.agents 객체가 필요합니다.")
    normalized: dict[str, dict[str, object]] = {}
    for agent_name, definition in agents.items():
        if not isinstance(agent_name, str) or not isinstance(definition, Mapping):
            raise ConfigurationError(
                f"Agent 정의 형식이 올바르지 않습니다: agent={agent_name!r}"
            )
        normalized[agent_name] = cast(dict[str, object], dict(definition))
    return normalized


def string_list(
    definition: Mapping[str, object],
    field: str,
    source: str,
) -> list[str]:
    """Manifest의 문자열 배열 필드를 읽는다."""
    value = definition.get(field)
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise ConfigurationError(
            f"Manifest 필드는 문자열 배열이어야 합니다: source={source}, field={field}"
        )
    return cast(list[str], value.copy())


def validate_agent_manifest(
    manifest: Mapping[str, object],
    dependency_graph: Mapping[str, object],
    agents_root: Path,
) -> None:
    """Agent 입출력, 실행 의존성, Prompt 존재, Example 격리를 검사한다."""
    agents = manifest_agents(manifest)
    artifacts = dependency_artifacts(dependency_graph)
    artifact_names = set(artifacts)

    for agent_name, definition in agents.items():
        prompt_file = definition.get("prompt_file")
        if not isinstance(prompt_file, str):
            raise ConfigurationError(
                f"Agent prompt_file이 올바르지 않습니다: agent={agent_name}"
            )
        prompt_path = agents_root / prompt_file
        if not prompt_path.is_file():
            raise InputFileNotFoundError(
                f"Agent Prompt를 찾을 수 없습니다: agent={agent_name}, path={prompt_path}"
            )
        if definition.get("may_read_examples") is not False:
            raise ConfigurationError(
                f"Production Agent는 EXAMPLES를 읽을 수 없습니다: agent={agent_name}"
            )

        reads = set(string_list(definition, "reads", agent_name))
        writes = set(string_list(definition, "writes", agent_name))
        unknown_artifacts = sorted((reads | writes) - artifact_names)
        if unknown_artifacts:
            raise ConfigurationError(
                f"Agent가 알 수 없는 Artifact를 참조합니다: "
                f"agent={agent_name}, artifacts={unknown_artifacts}"
            )

        required_agents = string_list(definition, "requires_agents", agent_name)
        unknown_agents = sorted(set(required_agents) - set(agents))
        if unknown_agents:
            raise ConfigurationError(
                f"Agent가 알 수 없는 선행 Agent를 참조합니다: "
                f"agent={agent_name}, agents={unknown_agents}"
            )
        stage = definition.get("stage")
        if not isinstance(stage, int):
            raise ConfigurationError(f"Agent stage는 정수여야 합니다: agent={agent_name}")
        for required_agent in required_agents:
            required_stage = agents[required_agent].get("stage")
            if not isinstance(required_stage, int) or required_stage > stage:
                raise ConfigurationError(
                    f"Agent 실행 순서가 역전되었습니다: agent={agent_name}, "
                    f"requires={required_agent}"
                )

        resources = string_list(definition, "resources", agent_name)
        for resource in resources:
            repository_root = repository_root_placeholder(agents_root)
            resource_path = repository_root / resource
            if not is_inside(resource_path, repository_root):
                raise ConfigurationError(
                    f"Agent Resource가 Repository 밖을 참조합니다: agent={agent_name}"
                )
            if not resource_path.is_file():
                raise InputFileNotFoundError(
                    f"Agent Resource를 찾을 수 없습니다: agent={agent_name}, path={resource_path}"
                )
            if "EXAMPLES" in resource_path.parts:
                raise ConfigurationError(
                    f"Agent Resource에 EXAMPLES를 사용할 수 없습니다: agent={agent_name}"
                )

    unknown_owners = sorted(
        {
            owner
            for definition in artifacts.values()
            if isinstance((owner := definition.get("owner_agent")), str)
            and owner not in agents
        }
    )
    if unknown_owners:
        raise ConfigurationError(
            f"Dependency Graph가 알 수 없는 Agent를 소유자로 사용합니다: agents={unknown_owners}"
        )

    ownership_mismatches = sorted(
        artifact_name
        for artifact_name, artifact_definition in artifacts.items()
        if isinstance((owner := artifact_definition.get("owner_agent")), str)
        and owner in agents
        and artifact_name not in set(string_list(agents[owner], "writes", owner))
    )
    if ownership_mismatches:
        raise ConfigurationError(
            "Artifact Owner Agent의 writes 계약이 누락되었습니다: "
            f"artifacts={ownership_mismatches}"
        )


def is_inside(path: Path, root: Path) -> bool:
    """경로가 지정 Root 내부인지 판정한다."""
    try:
        path.resolve().relative_to(root.resolve())
    except ValueError:
        return False
    return True


def repository_root_placeholder(agents_root: Path) -> Path:
    """AGENTS 디렉터리에서 Repository Root를 계산한다."""
    return agents_root.parent


def build_production_context_paths(
    manifest: Mapping[str, object],
    dependency_graph: Mapping[str, object],
    agent_name: str,
    repository_root: Path,
    project_root: Path,
) -> list[Path]:
    """Agent가 읽을 수 있는 파일만 반환하고 EXAMPLES를 기술적으로 제외한다."""
    agents = manifest_agents(manifest)
    if agent_name not in agents:
        raise ConfigurationError(f"알 수 없는 Agent입니다: agent={agent_name}")
    definition = agents[agent_name]
    if definition.get("may_read_examples") is not False:
        raise ConfigurationError(
            f"Production Context는 EXAMPLES 접근이 금지됩니다: agent={agent_name}"
        )

    prompt_file = definition.get("prompt_file")
    if not isinstance(prompt_file, str):
        raise ConfigurationError(f"Agent Prompt가 정의되지 않았습니다: agent={agent_name}")
    context_paths = [repository_root / "AGENTS" / prompt_file]
    artifacts = dependency_artifacts(dependency_graph)
    for artifact_name in string_list(definition, "reads", agent_name):
        relative_path = artifacts[artifact_name].get("path")
        if not isinstance(relative_path, str):
            raise ConfigurationError(
                f"Artifact path가 올바르지 않습니다: artifact={artifact_name}"
            )
        context_paths.append(project_root / relative_path)

    for resource in string_list(definition, "resources", agent_name):
        resource_path = repository_root / resource
        if not is_inside(resource_path, repository_root):
            raise ConfigurationError(
                f"Production Resource가 Repository 밖을 참조합니다: agent={agent_name}"
            )
        if not resource_path.is_file():
            raise InputFileNotFoundError(
                f"Production Resource를 찾을 수 없습니다: agent={agent_name}, path={resource_path}"
            )
        context_paths.append(resource_path)

    context_paths.extend(sorted((repository_root / "STANDARD").glob("*.json")))
    context_paths.extend(sorted((repository_root / "CHANNELS").glob("*/*.json")))
    examples_root = repository_root / "EXAMPLES"
    leaked_paths = sorted(
        str(path) for path in context_paths if is_inside(path, examples_root)
    )
    if leaked_paths:
        raise ConfigurationError(
            f"Production Context에 EXAMPLES 경로가 포함되었습니다: paths={leaked_paths}"
        )
    return context_paths
