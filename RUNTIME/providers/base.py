"""Provider Adapter 공통 직렬화 경계."""

from collections.abc import Mapping
from typing import cast

from RUNTIME.errors import RuntimeExecutionError
from RUNTIME.models import (
    GenerationOptions,
    LLMMessage,
    LLMProvider,
    LLMRequest,
    LLMResponse,
    OutputContract,
    OutputMode,
    ProviderDescriptor,
    ProviderFinishReason,
    ProviderResponseStatus,
    TokenUsage,
    ToolDefinition,
)

__all__ = ["LLMProvider"]


def provider_descriptor_document(descriptor: ProviderDescriptor) -> dict[str, object]:
    """Provider Descriptor를 Wire 객체로 변환한다."""
    return {
        "interface_version": descriptor.interface_version,
        "provider_id": descriptor.provider_id,
        "adapter_id": descriptor.adapter_id,
        "adapter_version": descriptor.adapter_version,
        "capabilities": list(descriptor.capabilities),
        "max_context_tokens": descriptor.max_context_tokens,
        "max_output_tokens": descriptor.max_output_tokens,
    }


def request_document(request: LLMRequest) -> dict[str, object]:
    """Provider Request를 SDK 비종속 Wire 객체로 변환한다."""
    return {
        "request_id": request.request_id,
        "idempotency_key": request.idempotency_key,
        "model_ref": request.model_ref,
        "messages": [
            {"role": message.role, "content": message.content} for message in request.messages
        ],
        "output_contract": {
            "mode": request.output_contract.mode,
            "name": request.output_contract.name,
            "json_schema": request.output_contract.json_schema,
        },
        "generation": {
            "max_output_tokens": request.generation.max_output_tokens,
            "temperature": request.generation.temperature,
            "top_p": request.generation.top_p,
            "seed": request.generation.seed,
            "stop": list(request.generation.stop),
        },
        "tools": [
            {
                "name": tool.name,
                "description": tool.description,
                "input_schema": tool.input_schema,
            }
            for tool in request.tools
        ],
        "deadline_ms": request.deadline_ms,
        "metadata": request.metadata.copy(),
        "extensions": request.extensions.copy(),
    }


def response_document(response: LLMResponse) -> dict[str, object]:
    """Provider Response를 Wire 객체로 변환한다."""
    return {
        "request_id": response.request_id,
        "provider_request_id": response.provider_request_id,
        "status": response.status,
        "finish_reason": response.finish_reason,
        "text": response.text,
        "structured_output": response.structured_output,
        "tool_calls": list(response.tool_calls),
        "usage": {
            "input_tokens": response.usage.input_tokens,
            "output_tokens": response.usage.output_tokens,
            "cached_tokens": response.usage.cached_tokens,
        },
        "model_resolved": response.model_resolved,
        "warnings": list(response.warnings),
    }


def require_string(document: Mapping[str, object], key: str, source: str) -> str:
    """Wire 객체에서 비어 있지 않은 문자열을 읽는다."""
    value = document.get(key)
    if not isinstance(value, str) or not value:
        raise RuntimeExecutionError(
            "OUTPUT_PARSE_ERROR",
            False,
            "PROVIDER_RESPONSE",
            "Provider Wire 응답의 문자열 필드가 올바르지 않습니다.",
            None,
            None,
            {"source": source, "field": key},
        )
    return value


def optional_integer(document: Mapping[str, object], key: str) -> int | None:
    """Wire 객체의 선택 정수를 엄격하게 읽는다."""
    value = document.get(key)
    if value is None:
        return None
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise RuntimeExecutionError(
            "OUTPUT_PARSE_ERROR",
            False,
            "PROVIDER_RESPONSE",
            "Provider Usage 값이 올바르지 않습니다.",
            None,
            None,
            {"field": key},
        )
    return value


def response_from_document(document: Mapping[str, object]) -> LLMResponse:
    """Wire 객체를 Provider 독립 응답으로 변환한다."""
    status = document.get("status")
    finish_reason = document.get("finish_reason")
    if status not in {"COMPLETED", "REFUSED", "FAILED"}:
        raise RuntimeExecutionError(
            "OUTPUT_PARSE_ERROR",
            False,
            "PROVIDER_RESPONSE",
            "Provider 응답 Status가 올바르지 않습니다.",
            None,
            None,
            {"status": status},
        )
    if finish_reason not in {"STOP", "LENGTH", "TOOL_CALL", "FILTERED", "ERROR"}:
        raise RuntimeExecutionError(
            "OUTPUT_PARSE_ERROR",
            False,
            "PROVIDER_RESPONSE",
            "Provider Finish Reason이 올바르지 않습니다.",
            None,
            None,
            {"finish_reason": finish_reason},
        )
    structured = document.get("structured_output")
    if structured is not None and not isinstance(structured, Mapping):
        raise RuntimeExecutionError(
            "OUTPUT_PARSE_ERROR",
            False,
            "PROVIDER_RESPONSE",
            "Provider Structured Output이 객체가 아닙니다.",
            None,
            None,
            {},
        )
    usage_value = document.get("usage")
    if not isinstance(usage_value, Mapping):
        raise RuntimeExecutionError(
            "OUTPUT_PARSE_ERROR",
            False,
            "PROVIDER_RESPONSE",
            "Provider Usage 객체가 없습니다.",
            None,
            None,
            {},
        )
    tool_calls_value = document.get("tool_calls")
    warnings_value = document.get("warnings")
    if not isinstance(tool_calls_value, list) or not all(
        isinstance(item, Mapping) for item in tool_calls_value
    ):
        raise RuntimeExecutionError(
            "OUTPUT_PARSE_ERROR",
            False,
            "PROVIDER_RESPONSE",
            "Provider Tool Call 배열이 올바르지 않습니다.",
            None,
            None,
            {},
        )
    if not isinstance(warnings_value, list) or not all(
        isinstance(item, str) for item in warnings_value
    ):
        raise RuntimeExecutionError(
            "OUTPUT_PARSE_ERROR",
            False,
            "PROVIDER_RESPONSE",
            "Provider Warning 배열이 올바르지 않습니다.",
            None,
            None,
            {},
        )
    text = document.get("text")
    provider_request_id = document.get("provider_request_id")
    if text is not None and not isinstance(text, str):
        raise RuntimeExecutionError(
            "OUTPUT_PARSE_ERROR",
            False,
            "PROVIDER_RESPONSE",
            "Provider Text가 문자열이 아닙니다.",
            None,
            None,
            {},
        )
    if provider_request_id is not None and not isinstance(provider_request_id, str):
        raise RuntimeExecutionError(
            "OUTPUT_PARSE_ERROR",
            False,
            "PROVIDER_RESPONSE",
            "Provider Request ID가 문자열이 아닙니다.",
            None,
            None,
            {},
        )
    return LLMResponse(
        request_id=require_string(document, "request_id", "llm_response"),
        provider_request_id=provider_request_id,
        status=cast(ProviderResponseStatus, status),
        finish_reason=cast(ProviderFinishReason, finish_reason),
        text=text,
        structured_output=dict(structured) if isinstance(structured, Mapping) else None,
        tool_calls=tuple(dict(item) for item in tool_calls_value),
        usage=TokenUsage(
            input_tokens=optional_integer(usage_value, "input_tokens"),
            output_tokens=optional_integer(usage_value, "output_tokens"),
            cached_tokens=optional_integer(usage_value, "cached_tokens"),
        ),
        model_resolved=require_string(document, "model_resolved", "llm_response"),
        warnings=tuple(cast(list[str], warnings_value)),
    )


def request_from_document(document: Mapping[str, object]) -> LLMRequest:
    """Sidecar Conformance Test용 Wire 요청 역직렬화."""
    messages_value = document.get("messages")
    output_value = document.get("output_contract")
    generation_value = document.get("generation")
    tools_value = document.get("tools")
    metadata_value = document.get("metadata")
    extensions_value = document.get("extensions")
    if not isinstance(messages_value, list) or not all(
        isinstance(item, Mapping) for item in messages_value
    ):
        raise ValueError("messages")
    if not isinstance(output_value, Mapping) or not isinstance(generation_value, Mapping):
        raise ValueError("output_contract/generation")
    if not isinstance(tools_value, list) or not all(
        isinstance(item, Mapping) for item in tools_value
    ):
        raise ValueError("tools")
    if not isinstance(metadata_value, Mapping) or not isinstance(extensions_value, Mapping):
        raise ValueError("metadata/extensions")
    messages = tuple(
        LLMMessage(
            role=require_string(item, "role", "llm_request.messages"),
            content=str(item.get("content", "")),
        )
        for item in messages_value
    )
    tool_definitions = tuple(
        ToolDefinition(
            name=require_string(item, "name", "llm_request.tools"),
            description=require_string(item, "description", "llm_request.tools"),
            input_schema=dict(item["input_schema"])
            if isinstance(item.get("input_schema"), Mapping)
            else {},
        )
        for item in tools_value
    )
    max_output_tokens = generation_value.get("max_output_tokens")
    if not isinstance(max_output_tokens, int) or isinstance(max_output_tokens, bool):
        raise ValueError("max_output_tokens")
    return LLMRequest(
        request_id=require_string(document, "request_id", "llm_request"),
        idempotency_key=require_string(document, "idempotency_key", "llm_request"),
        model_ref=require_string(document, "model_ref", "llm_request"),
        messages=messages,
        output_contract=OutputContract(
            mode=cast(OutputMode, require_string(output_value, "mode", "output_contract")),
            name=require_string(output_value, "name", "output_contract"),
            json_schema=dict(output_value["json_schema"])
            if isinstance(output_value.get("json_schema"), Mapping)
            else None,
        ),
        generation=GenerationOptions(
            max_output_tokens=max_output_tokens,
            temperature=cast(float | None, generation_value.get("temperature")),
            top_p=cast(float | None, generation_value.get("top_p")),
            seed=cast(int | None, generation_value.get("seed")),
            stop=tuple(
                item
                for item in cast(list[object], generation_value.get("stop", []))
                if isinstance(item, str)
            ),
        ),
        tools=tool_definitions,
        deadline_ms=cast(int | None, document.get("deadline_ms")),
        metadata={str(key): str(value) for key, value in metadata_value.items()},
        extensions=dict(extensions_value),
    )
