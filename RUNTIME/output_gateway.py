"""Provider 출력을 소유권·Schema·크기 규칙으로 제한하는 Gateway."""

import json
from collections.abc import Mapping
from pathlib import Path

from RUNTIME.errors import RuntimeExecutionError
from RUNTIME.models import ArtifactContract, LLMResponse, RuntimeTask
from VALIDATORS.io import load_json_object
from VALIDATORS.presentation_validation import script_has_complete_segment_markers
from VALIDATORS.schema_validation import collect_schema_errors


def schema_with_fragment(
    repository_root: Path,
    schema_reference: str,
) -> dict[str, object]:
    """파일 Schema와 선택 JSON Pointer Fragment를 검증 가능한 Schema로 결합한다."""
    path_part, separator, fragment = schema_reference.partition("#")
    schema = load_json_object(repository_root / path_part)
    if not separator:
        return schema
    if not fragment.startswith("/"):
        raise RuntimeExecutionError(
            "RUNTIME_CONFIGURATION_ERROR",
            False,
            "RUNTIME",
            "Artifact Schema Fragment가 JSON Pointer 형식이 아닙니다.",
            None,
            None,
            {"schema": schema_reference},
        )
    return {
        "$schema": schema.get("$schema", "https://json-schema.org/draft/2020-12/schema"),
        "$defs": schema.get("$defs", {}),
        "$ref": f"#{fragment}",
    }


def artifact_schema_reference(
    contract: ArtifactContract,
    content: Mapping[str, object],
    task_id: str,
    artifact_name: str,
) -> str:
    """Artifact의 schema_version에 등록된 전용 Schema 경로를 선택한다."""
    schema_versions = contract.get("schema_versions")
    schema_reference = contract["schema"]
    if schema_versions is None:
        if schema_reference is None:
            raise RuntimeExecutionError(
                "RUNTIME_CONFIGURATION_ERROR",
                False,
                "RUNTIME",
                "JSON Artifact Schema 계약이 없습니다.",
                task_id,
                artifact_name,
                {},
            )
        return schema_reference
    schema_version = content.get("schema_version")
    if not isinstance(schema_version, str):
        raise RuntimeExecutionError(
            "OUTPUT_SCHEMA_ERROR",
            True,
            "TASK_ATTEMPT",
            "Versioned JSON Artifact에 schema_version 문자열이 없습니다.",
            task_id,
            artifact_name,
            {},
        )
    versioned_reference = schema_versions.get(schema_version)
    if versioned_reference is not None:
        return versioned_reference
    if schema_version == "1.0.0" and schema_reference is not None:
        return schema_reference
    raise RuntimeExecutionError(
        "OUTPUT_SCHEMA_ERROR",
        False,
        "TASK_ATTEMPT",
        "JSON Artifact schema_version에 등록된 Schema가 없습니다.",
        task_id,
        artifact_name,
        {"schema_version": schema_version},
    )


def parse_response_document(response: LLMResponse, task_id: str) -> dict[str, object]:
    """Provider 상태를 해석하고 Agent Result JSON 객체만 반환한다."""
    if response.status == "REFUSED" or response.finish_reason == "FILTERED":
        raise RuntimeExecutionError(
            "PROVIDER_REFUSAL",
            False,
            "TASK_ATTEMPT",
            "Provider가 Task 수행을 거부했습니다.",
            task_id,
            None,
            {"finish_reason": response.finish_reason},
        )
    if response.status == "FAILED" or response.finish_reason == "ERROR":
        raise RuntimeExecutionError(
            "PROVIDER_FAILURE",
            False,
            "TASK_ATTEMPT",
            "Provider가 실패 응답을 반환했습니다.",
            task_id,
            None,
            {"finish_reason": response.finish_reason},
        )
    if response.finish_reason == "LENGTH":
        raise RuntimeExecutionError(
            "OUTPUT_PARSE_ERROR",
            True,
            "TASK_ATTEMPT",
            "Provider 출력이 길이 제한으로 중단되었습니다.",
            task_id,
            None,
            {},
        )
    if response.structured_output is not None:
        return response.structured_output.copy()
    if response.text is None:
        raise RuntimeExecutionError(
            "OUTPUT_PARSE_ERROR",
            True,
            "TASK_ATTEMPT",
            "Provider 응답에 Structured Output 또는 Text가 없습니다.",
            task_id,
            None,
            {},
        )
    try:
        parsed: object = json.loads(response.text)
    except json.JSONDecodeError as error:
        raise RuntimeExecutionError(
            "OUTPUT_PARSE_ERROR",
            True,
            "TASK_ATTEMPT",
            "Provider Text를 JSON 객체로 해석할 수 없습니다.",
            task_id,
            None,
            {"line": error.lineno, "column": error.colno},
        ) from error
    if not isinstance(parsed, Mapping):
        raise RuntimeExecutionError(
            "OUTPUT_PARSE_ERROR",
            True,
            "TASK_ATTEMPT",
            "Agent Result 최상위 값은 JSON 객체여야 합니다.",
            task_id,
            None,
            {},
        )
    return dict(parsed)


def validate_agent_result_identity(
    result: Mapping[str, object],
    run_id: str,
    task_id: str,
    task: RuntimeTask,
    attempt: int,
) -> None:
    """Provider가 Run, Task, Agent, Attempt Identity를 변경하지 못하게 한다."""
    expected = {
        "run_id": run_id,
        "task_id": task_id,
        "agent_id": task["agent_id"],
        "attempt": attempt,
    }
    mismatches = {
        key: {"expected": value, "actual": result.get(key)}
        for key, value in expected.items()
        if result.get(key) != value
    }
    if mismatches:
        raise RuntimeExecutionError(
            "UNAUTHORIZED_ARTIFACT",
            False,
            "TASK_ATTEMPT",
            "Agent Result Identity가 Runtime 요청과 다릅니다.",
            task_id,
            None,
            {"mismatches": mismatches},
        )


def encoded_artifact(content: object, media_type: str) -> bytes:
    """크기 검증과 Staging에 사용할 Canonical Byte를 반환한다."""
    if media_type == "application/json":
        return (json.dumps(content, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    if not isinstance(content, str):
        raise RuntimeExecutionError(
            "OUTPUT_PARSE_ERROR",
            True,
            "TASK_ATTEMPT",
            "Text Artifact Content가 문자열이 아닙니다.",
            None,
            None,
            {},
        )
    return content.encode("utf-8")


def validate_text_artifact(
    artifact_name: str,
    content: str,
    validators: list[str],
    task_id: str,
) -> None:
    """Text Artifact의 비어 있음과 안전한 문자 경계를 검사한다."""
    if "NON_EMPTY" in validators and not content.strip():
        raise RuntimeExecutionError(
            "OUTPUT_SCHEMA_ERROR",
            True,
            "TASK_ATTEMPT",
            "Text Artifact가 비어 있습니다.",
            task_id,
            artifact_name,
            {},
        )
    if "SCRIPT_INTEGRITY" in validators:
        if "\x00" in content:
            raise RuntimeExecutionError(
                "OUTPUT_SCHEMA_ERROR",
                False,
                "TASK_ATTEMPT",
                "Script Artifact에 Null Byte가 포함되었습니다.",
                task_id,
                artifact_name,
                {},
            )
        if not script_has_complete_segment_markers(content):
            raise RuntimeExecutionError(
                "OUTPUT_SCHEMA_ERROR",
                True,
                "TASK_ATTEMPT",
                "Script Artifact가 완전한 Broadcast Segment Marker를 갖지 않습니다.",
                task_id,
                artifact_name,
                {},
            )


def validate_artifact_content(
    repository_root: Path,
    task_id: str,
    artifact_name: str,
    media_type: str,
    content: object,
    contract: ArtifactContract,
) -> None:
    """Artifact Media Type, Schema, Size, Text Validator를 모두 적용한다."""
    if media_type != contract["media_type"]:
        raise RuntimeExecutionError(
            "OUTPUT_SCHEMA_ERROR",
            True,
            "TASK_ATTEMPT",
            "Artifact Media Type이 계약과 다릅니다.",
            task_id,
            artifact_name,
            {"expected": contract["media_type"], "actual": media_type},
        )
    if media_type == "application/json":
        if not isinstance(content, Mapping):
            raise RuntimeExecutionError(
                "OUTPUT_SCHEMA_ERROR",
                True,
                "TASK_ATTEMPT",
                "JSON Artifact Content가 객체가 아닙니다.",
                task_id,
                artifact_name,
                {},
            )
        schema_reference = artifact_schema_reference(
            contract,
            content,
            task_id,
            artifact_name,
        )
        schema = schema_with_fragment(repository_root, schema_reference)
        errors = collect_schema_errors(content, schema, artifact_name)
        if errors:
            raise RuntimeExecutionError(
                "OUTPUT_SCHEMA_ERROR",
                True,
                "TASK_ATTEMPT",
                "Artifact JSON Schema 검증에 실패했습니다.",
                task_id,
                artifact_name,
                {"errors": errors},
            )
    else:
        if not isinstance(content, str):
            raise RuntimeExecutionError(
                "OUTPUT_SCHEMA_ERROR",
                True,
                "TASK_ATTEMPT",
                "Text Artifact Content가 문자열이 아닙니다.",
                task_id,
                artifact_name,
                {},
            )
        validate_text_artifact(artifact_name, content, contract["validators"], task_id)
    size = len(encoded_artifact(content, media_type))
    if size > contract["max_bytes"]:
        raise RuntimeExecutionError(
            "OUTPUT_SCHEMA_ERROR",
            False,
            "TASK_ATTEMPT",
            "Artifact가 최대 Byte 크기를 초과했습니다.",
            task_id,
            artifact_name,
            {"max_bytes": contract["max_bytes"], "actual_bytes": size},
        )


def validate_core_outputs(
    repository_root: Path,
    task_id: str,
    task: RuntimeTask,
    outputs: Mapping[str, object],
    artifact_contracts: Mapping[str, ArtifactContract],
) -> None:
    """CORE Task에도 Provider와 같은 Artifact 계약을 적용한다."""
    if set(outputs) != set(task["writes"]):
        raise RuntimeExecutionError(
            "UNAUTHORIZED_ARTIFACT",
            False,
            "TASK",
            "CORE Task 출력과 writes 계약이 다릅니다.",
            task_id,
            None,
            {"expected": sorted(task["writes"]), "actual": sorted(outputs)},
        )
    for artifact_name, content in outputs.items():
        contract = artifact_contracts[artifact_name]
        validate_artifact_content(
            repository_root,
            task_id,
            artifact_name,
            contract["media_type"],
            content,
            contract,
        )


def validate_agent_result(
    repository_root: Path,
    response: LLMResponse,
    run_id: str,
    task_id: str,
    task: RuntimeTask,
    attempt: int,
    artifact_contracts: Mapping[str, ArtifactContract],
) -> dict[str, object]:
    """Agent Result를 검증하고 Task 출력 Content 사전을 반환한다."""
    document = parse_response_document(response, task_id)
    result_schema = load_json_object(
        repository_root / "RUNTIME" / "schemas" / "agent_result.schema.json"
    )
    envelope_errors = collect_schema_errors(document, result_schema, "agent_result")
    if envelope_errors:
        raise RuntimeExecutionError(
            "OUTPUT_SCHEMA_ERROR",
            True,
            "TASK_ATTEMPT",
            "Agent Result Envelope Schema 검증에 실패했습니다.",
            task_id,
            None,
            {"errors": envelope_errors},
        )
    validate_agent_result_identity(document, run_id, task_id, task, attempt)
    status = document.get("status")
    if status == "NEEDS_HUMAN":
        raise RuntimeExecutionError(
            "HUMAN_APPROVAL_REQUIRED",
            False,
            "TASK",
            "Agent가 Human 입력을 요청했습니다.",
            task_id,
            None,
            {},
        )
    if status == "REFUSED":
        raise RuntimeExecutionError(
            "PROVIDER_REFUSAL",
            False,
            "TASK",
            "Agent Result가 수행 거부를 선언했습니다.",
            task_id,
            None,
            {},
        )
    if status != "SUCCEEDED":
        raise RuntimeExecutionError(
            "OUTPUT_SCHEMA_ERROR",
            True,
            "TASK_ATTEMPT",
            "Agent Result가 수정 또는 실패 상태입니다.",
            task_id,
            None,
            {"status": status},
        )
    artifacts = document.get("artifacts")
    if not isinstance(artifacts, list) or not all(isinstance(item, Mapping) for item in artifacts):
        raise RuntimeExecutionError(
            "OUTPUT_PARSE_ERROR",
            True,
            "TASK_ATTEMPT",
            "Agent Result Artifact 배열이 올바르지 않습니다.",
            task_id,
            None,
            {},
        )
    names = [item.get("artifact_name") for item in artifacts]
    expected_names = set(task["writes"])
    actual_names = {name for name in names if isinstance(name, str)}
    if len(names) != len(actual_names) or actual_names != expected_names:
        raise RuntimeExecutionError(
            "UNAUTHORIZED_ARTIFACT",
            False,
            "TASK_ATTEMPT",
            "Agent Result가 허가되지 않았거나 누락된 Artifact를 반환했습니다.",
            task_id,
            None,
            {"expected": sorted(expected_names), "actual": sorted(actual_names)},
        )
    outputs: dict[str, object] = {}
    for artifact in artifacts:
        artifact_name = artifact.get("artifact_name")
        media_type = artifact.get("media_type")
        content = artifact.get("content")
        if not isinstance(artifact_name, str) or not isinstance(media_type, str):
            raise RuntimeExecutionError(
                "OUTPUT_PARSE_ERROR",
                True,
                "TASK_ATTEMPT",
                "Agent Artifact 식별 필드가 올바르지 않습니다.",
                task_id,
                None,
                {},
            )
        contract = artifact_contracts.get(artifact_name)
        if contract is None:
            raise RuntimeExecutionError(
                "UNAUTHORIZED_ARTIFACT",
                False,
                "TASK_ATTEMPT",
                "Artifact Contract가 없는 출력을 거부했습니다.",
                task_id,
                artifact_name,
                {},
            )
        validate_artifact_content(
            repository_root,
            task_id,
            artifact_name,
            media_type,
            content,
            contract,
        )
        outputs[artifact_name] = dict(content) if isinstance(content, Mapping) else content
    return outputs
