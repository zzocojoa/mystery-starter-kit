"""Task 최소 권한과 CLEAN 상태를 적용하는 Context Builder."""

import json
from collections.abc import Mapping
from hashlib import sha256
from pathlib import Path
from typing import cast

from RUNTIME.errors import RuntimeErrorCode, RuntimeExecutionError
from RUNTIME.models import ContextItem, DataClass, RuntimeTask
from VALIDATORS.channel_registry import resolve_project_channel
from VALIDATORS.dependency import dependency_artifacts
from VALIDATORS.io import load_json_object
from VALIDATORS.models import ProjectState
from VALIDATORS.source_truth import source_truth_requires_evidence
from VALIDATORS.source_truth_contract import (
    SOURCE_TRUTH_BOUND_ARTIFACTS,
    validate_source_truth_contract_integrity,
)

ArtifactContent = Mapping[str, object] | str


def serialize_content(content: object) -> str:
    """Context Hash와 Prompt에 사용할 안정적인 문자열을 만든다."""
    if isinstance(content, str):
        return content
    return json.dumps(content, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def content_hash(content: object) -> str:
    """Context Content의 SHA-256을 계산한다."""
    return sha256(serialize_content(content).encode("utf-8")).hexdigest()


def artifact_data_class(artifact_name: str) -> DataClass:
    """Artifact 이름에 따라 Provider Egress 분류를 반환한다."""
    if artifact_name == "reference_profile":
        return "REFERENCE_SANITIZED"
    if artifact_name in {
        "sources",
        "claim_evidence",
        "source_case_brief",
        "verified_fact_ledger",
        "source_subjects",
        "verified_event_ledger",
        "source_truth_contract",
        "clinical_labels",
    }:
        return "SENSITIVE"
    return "INTERNAL"


def read_artifact_content(path: Path) -> ArtifactContent:
    """Artifact 확장자에 따라 JSON 객체 또는 UTF-8 문자열을 읽는다."""
    if path.suffix == ".json":
        return load_json_object(path)
    try:
        return path.read_text(encoding="utf-8")
    except OSError as error:
        raise RuntimeExecutionError(
            "RUNTIME_CONFIGURATION_ERROR",
            False,
            "TASK",
            "Context Artifact를 읽지 못했습니다.",
            None,
            None,
            {"path": str(path)},
        ) from error


def load_project_state(project_path: Path) -> ProjectState:
    """Runtime Context 판정용 Project State를 읽는다."""
    document = load_json_object(project_path / "00_PROJECT" / "project_state.json")
    return cast(ProjectState, document)


def context_json_artifact(
    project_path: Path,
    definitions: Mapping[str, Mapping[str, object]],
    overlay: Mapping[str, ArtifactContent],
    artifact_name: str,
) -> Mapping[str, object] | None:
    """Context 검증에 필요한 JSON Artifact를 Overlay 우선으로 읽는다."""
    staged = overlay.get(artifact_name)
    if isinstance(staged, Mapping):
        return staged
    definition = definitions.get(artifact_name)
    relative_path = definition.get("path") if isinstance(definition, Mapping) else None
    if not isinstance(relative_path, str):
        return None
    path = project_path / relative_path
    return load_json_object(path) if path.is_file() else None


def validate_source_truth_before_llm_context(
    project_path: Path,
    task_id: str,
    task: RuntimeTask,
    definitions: Mapping[str, Mapping[str, object]],
    overlay: Mapping[str, ArtifactContent],
) -> None:
    """사실 기반 Evidence Bundle을 LLM Context 구성 전에 검증한다."""
    if task["executor"] != "LLM":
        return
    production_config = context_json_artifact(
        project_path,
        definitions,
        overlay,
        "production_config",
    )
    if production_config is None or not source_truth_requires_evidence(
        production_config.get("source_truth_classification")
    ):
        return
    bundle_names = (*SOURCE_TRUTH_BOUND_ARTIFACTS, "source_truth_contract")
    documents = {
        artifact_name: context_json_artifact(
            project_path,
            definitions,
            overlay,
            artifact_name,
        )
        for artifact_name in bundle_names
    }
    issues = validate_source_truth_contract_integrity(
        documents["source_truth_contract"],
        documents["sources"],
        documents["claim_evidence"],
        documents["verified_fact_ledger"],
        documents["source_subjects"],
        documents["verified_event_ledger"],
    )
    if not issues:
        return
    first_issue = issues[0]
    raise RuntimeExecutionError(
        cast(RuntimeErrorCode, first_issue["code"]),
        False,
        "TASK",
        "Source Truth Evidence Bundle이 LLM Context 생성 전에 검증되지 않았습니다.",
        task_id,
        "source_truth_contract",
        {"issues": issues},
    )


def build_minimal_context(
    repository_root: Path,
    project_path: Path,
    task_id: str,
    task: RuntimeTask,
    dependency_graph: Mapping[str, object],
    overlay: Mapping[str, ArtifactContent],
) -> list[ContextItem]:
    """Task Reads와 명시 Resource만 포함한 비명령성 Context를 만든다."""
    state = load_project_state(project_path)
    definitions = dependency_artifacts(dependency_graph)
    validate_source_truth_before_llm_context(
        project_path,
        task_id,
        task,
        definitions,
        overlay,
    )
    items: list[ContextItem] = []
    required_reads = task["reads"]
    optional_reads = task.get("optional_reads", [])
    selected_optional_reads = [
        artifact_name
        for artifact_name in optional_reads
        if artifact_name in overlay
        or (
            artifact_name in definitions
            and isinstance(definitions[artifact_name].get("path"), str)
            and (project_path / cast(str, definitions[artifact_name]["path"])).is_file()
        )
    ]
    for index, artifact_name in enumerate(
        [*required_reads, *selected_optional_reads],
        start=1,
    ):
        definition = definitions.get(artifact_name)
        if definition is None or not isinstance(definition.get("path"), str):
            raise RuntimeExecutionError(
                "RUNTIME_CONFIGURATION_ERROR",
                False,
                "TASK",
                "Task Context Artifact 정의가 없습니다.",
                task_id,
                artifact_name,
                {},
            )
        if artifact_name in overlay:
            content: object = overlay[artifact_name]
            status = "STAGED"
        else:
            artifact_state = state["artifacts"].get(artifact_name)
            if artifact_state is None or artifact_state["status"] != "CLEAN":
                raise RuntimeExecutionError(
                    "RUNTIME_CONFIGURATION_ERROR",
                    False,
                    "TASK",
                    "Task 입력 Artifact가 CLEAN 상태가 아닙니다.",
                    task_id,
                    artifact_name,
                    {"status": None if artifact_state is None else artifact_state["status"]},
                )
            content = read_artifact_content(project_path / cast(str, definition["path"]))
            status = "CLEAN"
        items.append(
            ContextItem(
                context_id=f"CTX-{index:03d}",
                artifact_name=artifact_name,
                media_type="application/json" if isinstance(content, Mapping) else "text/markdown",
                sha256=content_hash(content),
                status=status,
                trust_level=artifact_data_class(artifact_name),
                instructional=False,
                content=dict(content) if isinstance(content, Mapping) else content,
            )
        )
    next_index = len(items) + 1
    for offset, resource in enumerate(task["standard_resources"]):
        resource_path = (repository_root / resource).resolve()
        try:
            resource_path.relative_to(repository_root.resolve())
        except ValueError as error:
            raise RuntimeExecutionError(
                "RUNTIME_CONFIGURATION_ERROR",
                False,
                "TASK",
                "Task Resource가 Repository 밖을 참조합니다.",
                task_id,
                None,
                {"resource": resource},
            ) from error
        if "EXAMPLES" in resource_path.parts:
            raise RuntimeExecutionError(
                "DATA_POLICY_VIOLATION",
                False,
                "TASK",
                "Production Context에 EXAMPLES를 포함할 수 없습니다.",
                task_id,
                None,
                {"resource": resource},
            )
        content = read_artifact_content(resource_path)
        items.append(
            ContextItem(
                context_id=f"CTX-{next_index + offset:03d}",
                artifact_name=f"resource:{resource}",
                media_type="application/json" if isinstance(content, Mapping) else "text/markdown",
                sha256=content_hash(content),
                status="CONTRACT",
                trust_level="PUBLIC",
                instructional=False,
                content=dict(content) if isinstance(content, Mapping) else content,
            )
        )
    if any(
        Path(resource).name == "channel_manifest.json"
        for resource in task["standard_resources"]
    ):
        production_content = overlay.get("production_config")
        if production_content is None:
            production_content = read_artifact_content(
                project_path / "00_PROJECT" / "production_config.json"
            )
        if not isinstance(production_content, Mapping):
            raise RuntimeExecutionError(
                "RUNTIME_CONFIGURATION_ERROR",
                False,
                "TASK",
                "Pinned Channel Context에는 Production Config 객체가 필요합니다.",
                task_id,
                "production_config",
                {},
            )
        channel, _manifest, channel_path = resolve_project_channel(
            repository_root,
            production_content,
            None,
        )
        items.append(
            ContextItem(
                context_id=f"CTX-{len(items) + 1:03d}",
                artifact_name=(
                    "resource:pinned_channel_dna:"
                    f"{production_content.get('channel_content_version')}"
                ),
                media_type="application/json",
                sha256=content_hash(channel),
                status=f"CONTRACT:{channel_path.relative_to(repository_root)}",
                trust_level="PUBLIC",
                instructional=False,
                content=channel,
            )
        )
    leaked = [item["artifact_name"] for item in items if "EXAMPLES" in item["artifact_name"]]
    if leaked:
        raise RuntimeExecutionError(
            "DATA_POLICY_VIOLATION",
            False,
            "TASK",
            "Production Context에 EXAMPLES가 유출되었습니다.",
            task_id,
            None,
            {"items": leaked},
        )
    return items


def context_input_hashes(items: list[ContextItem]) -> dict[str, str]:
    """Artifact Context만 입력 Hash 사전으로 반환한다."""
    return {
        item["artifact_name"]: item["sha256"]
        for item in items
        if not item["artifact_name"].startswith("resource:")
    }


def context_data_classes(items: list[ContextItem]) -> set[DataClass]:
    """Provider Router가 검사할 Data Class 집합을 반환한다."""
    return {item["trust_level"] for item in items}


def estimated_tokens(items: list[ContextItem]) -> int:
    """Provider 독립 보수적 문자 기반 Token 추정치를 반환한다."""
    total_characters = sum(len(serialize_content(item["content"])) for item in items)
    return max(1, total_characters // 3)
