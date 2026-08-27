"""OpenAI Responses API를 공통 Runtime 모델로 격리하는 Provider Adapter."""

import asyncio
import json
import logging
from collections.abc import Mapping
from typing import cast
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from RUNTIME.errors import RuntimeErrorCode, RuntimeExecutionError
from RUNTIME.models import (
    LLMMessage,
    LLMRequest,
    LLMResponse,
    OutputContract,
    ProviderDescriptor,
    TokenUsage,
)

OPENAI_RESPONSES_ENDPOINT = "https://api.openai.com/v1/responses"
LOGGER = logging.getLogger(__name__)


def provider_error(
    code: RuntimeErrorCode,
    retryable: bool,
    message: str,
    task_id: str | None,
    safe_context: dict[str, object],
) -> RuntimeExecutionError:
    """OpenAI 오류를 Credential이 없는 공통 Runtime 오류로 만든다."""
    return RuntimeExecutionError(
        code,
        retryable,
        "PROVIDER",
        message,
        task_id,
        None,
        safe_context,
    )


def require_non_empty_string(
    document: Mapping[str, object],
    field: str,
    request: LLMRequest,
) -> str:
    """Provider 응답에서 비어 있지 않은 필수 문자열을 읽는다."""
    value = document.get(field)
    if not isinstance(value, str) or not value:
        raise provider_error(
            "OUTPUT_PARSE_ERROR",
            False,
            "OpenAI 응답의 필수 문자열 필드가 올바르지 않습니다.",
            request.metadata.get("task_id"),
            {"field": field, "request_id": request.request_id},
        )
    return value


def optional_token_count(document: Mapping[str, object], field: str) -> int | None:
    """Usage 객체의 선택 Token 수를 엄격하게 읽는다."""
    value = document.get(field)
    if value is None:
        return None
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise ValueError(field)
    return value


def normalized_usage(document: Mapping[str, object], request: LLMRequest) -> TokenUsage:
    """OpenAI Usage를 Provider 독립 Token 사용량으로 정규화한다."""
    raw_usage = document.get("usage")
    if raw_usage is None:
        return TokenUsage(input_tokens=None, output_tokens=None, cached_tokens=None)
    if not isinstance(raw_usage, Mapping):
        raise provider_error(
            "OUTPUT_PARSE_ERROR",
            False,
            "OpenAI 응답의 Usage 객체가 올바르지 않습니다.",
            request.metadata.get("task_id"),
            {"request_id": request.request_id},
        )
    input_details = raw_usage.get("input_tokens_details")
    details = input_details if isinstance(input_details, Mapping) else {}
    try:
        return TokenUsage(
            input_tokens=optional_token_count(raw_usage, "input_tokens"),
            output_tokens=optional_token_count(raw_usage, "output_tokens"),
            cached_tokens=optional_token_count(details, "cached_tokens"),
        )
    except ValueError as error:
        raise provider_error(
            "OUTPUT_PARSE_ERROR",
            False,
            "OpenAI 응답의 Token 사용량이 올바르지 않습니다.",
            request.metadata.get("task_id"),
            {"field": str(error), "request_id": request.request_id},
        ) from error


def output_text_and_refusal(document: Mapping[str, object]) -> tuple[str | None, bool]:
    """Responses API 출력 배열에서 Text와 Refusal 여부를 추출한다."""
    direct_text = document.get("output_text")
    if isinstance(direct_text, str):
        return direct_text, False
    output = document.get("output")
    if not isinstance(output, list):
        return None, False
    text_parts: list[str] = []
    refused = False
    for item in output:
        if not isinstance(item, Mapping):
            continue
        content = item.get("content")
        if not isinstance(content, list):
            continue
        for part in content:
            if not isinstance(part, Mapping):
                continue
            part_type = part.get("type")
            if part_type == "refusal":
                refused = True
            if part_type == "output_text" and isinstance(part.get("text"), str):
                text_parts.append(cast(str, part["text"]))
    return ("".join(text_parts) if text_parts else None), refused


def incomplete_reason(document: Mapping[str, object]) -> str | None:
    """미완료 응답의 표준 Reason 문자열을 읽는다."""
    details = document.get("incomplete_details")
    if not isinstance(details, Mapping):
        return None
    reason = details.get("reason")
    return reason if isinstance(reason, str) else None


def structured_output(
    text: str | None,
    output_contract: OutputContract,
) -> dict[str, object] | None:
    """JSON 출력이면 객체로 정규화하고 실패 시 Gateway 수리를 위해 Text를 유지한다."""
    if text is None or output_contract.mode == "TEXT":
        return None
    try:
        parsed: object = json.loads(text)
    except json.JSONDecodeError:
        return None
    return dict(parsed) if isinstance(parsed, Mapping) else None


def output_format(output_contract: OutputContract, request: LLMRequest) -> dict[str, object]:
    """공통 출력 계약을 Responses API Text Format으로 변환한다."""
    if output_contract.mode == "TEXT":
        return {"type": "text"}
    if output_contract.mode == "JSON_OBJECT":
        return {"type": "json_object"}
    if output_contract.json_schema is None:
        raise provider_error(
            "RUNTIME_CONFIGURATION_ERROR",
            False,
            "JSON Schema 출력 계약에 Schema가 없습니다.",
            request.metadata.get("task_id"),
            {"request_id": request.request_id, "output_contract": output_contract.name},
        )
    return {
        "type": "json_schema",
        "name": output_contract.name,
        "schema": output_contract.json_schema.copy(),
        "strict": True,
    }


def input_messages(
    messages: tuple[LLMMessage, ...],
    request: LLMRequest,
) -> list[dict[str, object]]:
    """System 지시를 제외한 메시지를 Responses API Input으로 변환한다."""
    converted: list[dict[str, object]] = []
    for message in messages:
        if message.role in {"system", "developer"}:
            continue
        if message.role not in {"user", "assistant"}:
            raise provider_error(
                "CAPABILITY_MISMATCH",
                False,
                "OpenAI Adapter가 지원하지 않는 메시지 Role입니다.",
                request.metadata.get("task_id"),
                {"request_id": request.request_id, "role": message.role},
            )
        converted.append({"role": message.role, "content": message.content})
    if not converted:
        raise provider_error(
            "RUNTIME_CONFIGURATION_ERROR",
            False,
            "OpenAI 요청에는 System 외 메시지가 하나 이상 필요합니다.",
            request.metadata.get("task_id"),
            {"request_id": request.request_id},
        )
    return converted


def request_payload(request: LLMRequest) -> dict[str, object]:
    """공통 LLM 요청을 Responses API 요청 객체로 변환한다."""
    unsupported: list[str] = []
    if request.tools:
        unsupported.append("tools")
    if request.generation.seed is not None:
        unsupported.append("seed")
    if request.generation.stop:
        unsupported.append("stop")
    if request.extensions:
        unsupported.append("extensions")
    if unsupported:
        raise provider_error(
            "CAPABILITY_MISMATCH",
            False,
            "OpenAI Adapter가 선언하지 않은 요청 기능을 받았습니다.",
            request.metadata.get("task_id"),
            {"request_id": request.request_id, "unsupported": unsupported},
        )
    system_parts = [
        message.content for message in request.messages if message.role in {"system", "developer"}
    ]
    payload: dict[str, object] = {
        "model": request.model_ref,
        "input": input_messages(request.messages, request),
        "max_output_tokens": request.generation.max_output_tokens,
        "store": False,
        "text": {"format": output_format(request.output_contract, request)},
    }
    if system_parts:
        payload["instructions"] = "\n\n".join(system_parts)
    if request.generation.temperature is not None:
        payload["temperature"] = request.generation.temperature
    elif request.generation.top_p is not None:
        payload["top_p"] = request.generation.top_p
    return payload


def sanitized_response_body(body: str, credential: str) -> str:
    """오류 응답에서 Credential을 제거하고 진단 크기를 제한한다."""
    return body.replace(credential, "[REDACTED]")[:2048]


def http_error_code(status_code: int) -> tuple[RuntimeErrorCode, bool, str]:
    """OpenAI HTTP 상태를 공통 오류 코드와 재시도 정책으로 변환한다."""
    if status_code == 429:
        return "PROVIDER_RATE_LIMIT", True, "OpenAI API 요청 한도를 초과했습니다."
    if status_code in {408, 504}:
        return "PROVIDER_TIMEOUT", True, "OpenAI API 요청 시간이 초과되었습니다."
    if status_code == 409 or status_code >= 500:
        return "PROVIDER_NOT_AVAILABLE", True, "OpenAI API를 일시적으로 사용할 수 없습니다."
    return "PROVIDER_FAILURE", False, "OpenAI API 요청이 실패했습니다."


def warn_retryable_error(
    code: RuntimeErrorCode,
    request: LLMRequest,
    status_code: int | None,
) -> None:
    """Runtime 재시도 대상인 외부 호출 오류를 구조화해 경고한다."""
    LOGGER.warning(
        "OpenAI Provider 호출을 Runtime이 재시도할 수 있습니다.",
        extra={
            "provider_error_code": code,
            "request_id": request.request_id,
            "model_ref": request.model_ref,
            "status_code": status_code,
        },
    )


class OpenAIResponsesProvider:
    """Responses API HTTP 경계를 소유하는 외부 시스템 Connector."""

    def __init__(
        self,
        provider_id: str,
        credential: str,
        endpoint: str,
        timeout_seconds: float,
    ) -> None:
        if not provider_id:
            raise ValueError("provider_id")
        if not credential:
            raise ValueError("credential")
        if not endpoint:
            raise ValueError("endpoint")
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds")
        self._credential = credential
        self._endpoint = endpoint
        self._timeout_seconds = timeout_seconds
        self._descriptor = ProviderDescriptor(
            interface_version="1.0.0",
            provider_id=provider_id,
            adapter_id="openai-responses",
            adapter_version="1.0.0",
            capabilities=(
                "TEXT_GENERATION",
                "JSON_OBJECT",
                "JSON_SCHEMA_OUTPUT",
                "SYSTEM_MESSAGES",
                "USAGE_REPORTING",
            ),
            max_context_tokens=None,
            max_output_tokens=None,
        )

    @property
    def descriptor(self) -> ProviderDescriptor:
        """Adapter가 실제 구현하는 Capability만 반환한다."""
        return self._descriptor

    def _request_context(self, request: LLMRequest) -> dict[str, object]:
        """Prompt와 Credential을 제외한 안전한 요청 Context를 반환한다."""
        return {
            "provider_id": self._descriptor.provider_id,
            "request_id": request.request_id,
            "model_ref": request.model_ref,
            "output_mode": request.output_contract.mode,
            "max_output_tokens": request.generation.max_output_tokens,
        }

    def _wire_request(self, request: LLMRequest) -> dict[str, object]:
        """동기 HTTP 요청을 실행하고 JSON 객체를 반환한다."""
        encoded = json.dumps(request_payload(request), ensure_ascii=False).encode("utf-8")
        wire_request = Request(
            self._endpoint,
            data=encoded,
            headers={
                "Accept": "application/json",
                "Authorization": f"Bearer {self._credential}",
                "Content-Type": "application/json",
                "Idempotency-Key": request.idempotency_key,
            },
            method="POST",
        )
        timeout_seconds = (
            request.deadline_ms / 1000 if request.deadline_ms is not None else self._timeout_seconds
        )
        if timeout_seconds <= 0:
            raise provider_error(
                "RUNTIME_CONFIGURATION_ERROR",
                False,
                "OpenAI 요청 Deadline은 0보다 커야 합니다.",
                request.metadata.get("task_id"),
                self._request_context(request),
            )
        try:
            with urlopen(wire_request, timeout=timeout_seconds) as response:
                body = response.read().decode("utf-8")
        except HTTPError as error:
            status_code = error.code
            response_body = error.read(2048).decode("utf-8", errors="replace")
            code, retryable, message = http_error_code(status_code)
            if retryable:
                warn_retryable_error(code, request, status_code)
            context = self._request_context(request)
            context.update(
                {
                    "status_code": status_code,
                    "provider_request_id": error.headers.get("x-request-id"),
                    "response_body": sanitized_response_body(
                        response_body,
                        self._credential,
                    ),
                }
            )
            raise provider_error(
                code,
                retryable,
                message,
                request.metadata.get("task_id"),
                context,
            ) from error
        except TimeoutError as error:
            warn_retryable_error("PROVIDER_TIMEOUT", request, None)
            raise provider_error(
                "PROVIDER_TIMEOUT",
                True,
                "OpenAI API 연결 시간이 초과되었습니다.",
                request.metadata.get("task_id"),
                self._request_context(request),
            ) from error
        except URLError as error:
            warn_retryable_error("PROVIDER_NOT_AVAILABLE", request, None)
            raise provider_error(
                "PROVIDER_NOT_AVAILABLE",
                True,
                "OpenAI API에 연결할 수 없습니다.",
                request.metadata.get("task_id"),
                self._request_context(request),
            ) from error
        try:
            parsed: object = json.loads(body)
        except json.JSONDecodeError as error:
            raise provider_error(
                "OUTPUT_PARSE_ERROR",
                False,
                "OpenAI API 응답이 JSON이 아닙니다.",
                request.metadata.get("task_id"),
                {
                    **self._request_context(request),
                    "line": error.lineno,
                    "column": error.colno,
                },
            ) from error
        if not isinstance(parsed, Mapping):
            raise provider_error(
                "OUTPUT_PARSE_ERROR",
                False,
                "OpenAI API 응답의 최상위 값이 객체가 아닙니다.",
                request.metadata.get("task_id"),
                self._request_context(request),
            )
        return dict(parsed)

    async def generate(self, request: LLMRequest) -> LLMResponse:
        """Responses API 호출을 비동기 Runtime에서 실행하고 공통 응답으로 변환한다."""
        document = await asyncio.to_thread(self._wire_request, request)
        response_id = require_non_empty_string(document, "id", request)
        status = require_non_empty_string(document, "status", request)
        model = require_non_empty_string(document, "model", request)
        text, refused = output_text_and_refusal(document)
        usage = normalized_usage(document, request)
        if refused:
            return LLMResponse(
                request_id=request.request_id,
                provider_request_id=response_id,
                status="REFUSED",
                finish_reason="FILTERED",
                text=None,
                structured_output=None,
                tool_calls=(),
                usage=usage,
                model_resolved=model,
                warnings=(),
            )
        reason = incomplete_reason(document)
        if status == "incomplete" and reason == "content_filter":
            return LLMResponse(
                request_id=request.request_id,
                provider_request_id=response_id,
                status="REFUSED",
                finish_reason="FILTERED",
                text=None,
                structured_output=None,
                tool_calls=(),
                usage=usage,
                model_resolved=model,
                warnings=(),
            )
        if status == "incomplete" and reason == "max_output_tokens":
            return LLMResponse(
                request_id=request.request_id,
                provider_request_id=response_id,
                status="COMPLETED",
                finish_reason="LENGTH",
                text=text,
                structured_output=None,
                tool_calls=(),
                usage=usage,
                model_resolved=model,
                warnings=(),
            )
        if status != "completed":
            return LLMResponse(
                request_id=request.request_id,
                provider_request_id=response_id,
                status="FAILED",
                finish_reason="ERROR",
                text=None,
                structured_output=None,
                tool_calls=(),
                usage=usage,
                model_resolved=model,
                warnings=(f"openai_status:{status}",)
                + ((f"openai_reason:{reason}",) if reason is not None else ()),
            )
        return LLMResponse(
            request_id=request.request_id,
            provider_request_id=response_id,
            status="COMPLETED",
            finish_reason="STOP",
            text=text,
            structured_output=structured_output(text, request.output_contract),
            tool_calls=(),
            usage=usage,
            model_resolved=model,
            warnings=(),
        )

    async def close(self) -> None:
        """요청별 HTTP 연결 방식에는 유지 자원이 없다."""
        return None


def create_provider(provider_id: str, credential: str | None) -> OpenAIResponsesProvider:
    """Registry Entry Point에서 OpenAI Adapter를 생성한다."""
    if credential is None or not credential:
        raise provider_error(
            "RUNTIME_CONFIGURATION_ERROR",
            False,
            "OpenAI Provider Credential이 설정되지 않았습니다.",
            None,
            {"provider_id": provider_id, "credential_env": "OPENAI_API_KEY"},
        )
    return OpenAIResponsesProvider(
        provider_id,
        credential,
        OPENAI_RESPONSES_ENDPOINT,
        120.0,
    )
