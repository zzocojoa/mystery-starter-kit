"""Provider SDK를 별도 Process로 격리하는 Sidecar HTTP Adapter."""

import asyncio
import json
import logging
from collections.abc import Mapping
from typing import cast
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from RUNTIME.errors import RuntimeErrorCode, RuntimeExecutionError
from RUNTIME.models import (
    LLMRequest,
    LLMResponse,
    ProviderCapability,
    ProviderDescriptor,
)
from RUNTIME.providers.base import request_document, response_from_document

LOGGER = logging.getLogger(__name__)


def sidecar_error(
    code: str,
    retryable: bool,
    message: str,
    safe_context: dict[str, object],
) -> RuntimeExecutionError:
    """Sidecar 오류를 Provider 세부정보 없는 Runtime 오류로 변환한다."""
    allowed_codes = {
        "PROVIDER_RATE_LIMIT",
        "PROVIDER_TIMEOUT",
        "PROVIDER_NOT_AVAILABLE",
        "PROVIDER_FAILURE",
        "OUTPUT_PARSE_ERROR",
        "CAPABILITY_MISMATCH",
    }
    normalized_code = code if code in allowed_codes else "PROVIDER_FAILURE"
    return RuntimeExecutionError(
        cast(RuntimeErrorCode, normalized_code),
        retryable,
        "PROVIDER",
        message,
        None,
        None,
        safe_context,
    )


def descriptor_from_document(document: Mapping[str, object]) -> ProviderDescriptor:
    """Sidecar Descriptor Wire 객체를 엄격한 모델로 변환한다."""
    required_strings = (
        "interface_version",
        "provider_id",
        "adapter_id",
        "adapter_version",
    )
    values = {key: document.get(key) for key in required_strings}
    if not all(isinstance(value, str) and value for value in values.values()):
        raise sidecar_error(
            "OUTPUT_PARSE_ERROR",
            False,
            "Sidecar Descriptor 문자열 필드가 올바르지 않습니다.",
            {},
        )
    capabilities = document.get("capabilities")
    if not isinstance(capabilities, list) or not all(
        isinstance(capability, str) for capability in capabilities
    ):
        raise sidecar_error(
            "OUTPUT_PARSE_ERROR",
            False,
            "Sidecar Capability 배열이 올바르지 않습니다.",
            {},
        )
    max_context = document.get("max_context_tokens")
    max_output = document.get("max_output_tokens")
    if max_context is not None and (
        not isinstance(max_context, int) or isinstance(max_context, bool) or max_context < 1
    ):
        raise sidecar_error(
            "OUTPUT_PARSE_ERROR", False, "Sidecar Context Limit이 올바르지 않습니다.", {}
        )
    if max_output is not None and (
        not isinstance(max_output, int) or isinstance(max_output, bool) or max_output < 1
    ):
        raise sidecar_error(
            "OUTPUT_PARSE_ERROR", False, "Sidecar Output Limit이 올바르지 않습니다.", {}
        )
    return ProviderDescriptor(
        interface_version=cast(str, values["interface_version"]),
        provider_id=cast(str, values["provider_id"]),
        adapter_id=cast(str, values["adapter_id"]),
        adapter_version=cast(str, values["adapter_version"]),
        capabilities=tuple(cast(list[ProviderCapability], capabilities)),
        max_context_tokens=max_context,
        max_output_tokens=max_output,
    )


class SidecarProvider:
    """동일 Wire 계약을 HTTP Sidecar에 전달하는 Provider Adapter."""

    def __init__(
        self,
        descriptor: ProviderDescriptor,
        endpoint: str,
        credential: str | None,
        timeout_seconds: float,
        retry_attempts: int,
    ) -> None:
        self._descriptor = descriptor
        self._endpoint = endpoint.rstrip("/")
        self._credential = credential
        self._timeout_seconds = timeout_seconds
        self._retry_attempts = retry_attempts

    @property
    def descriptor(self) -> ProviderDescriptor:
        """Sidecar가 선언한 Capability를 반환한다."""
        return self._descriptor

    def _wire_request(
        self,
        method: str,
        path: str,
        payload: Mapping[str, object] | None,
    ) -> dict[str, object]:
        """Sidecar HTTP 요청을 실행하고 JSON 객체를 반환한다."""
        data = (
            json.dumps(dict(payload), ensure_ascii=False).encode("utf-8")
            if payload is not None
            else None
        )
        headers = {"Accept": "application/json", "Content-Type": "application/json"}
        if self._credential is not None:
            headers["Authorization"] = f"Bearer {self._credential}"
        request = Request(
            f"{self._endpoint}{path}",
            data=data,
            headers=headers,
            method=method,
        )
        try:
            with urlopen(request, timeout=self._timeout_seconds) as response:
                body = response.read().decode("utf-8")
        except HTTPError as error:
            status_code = error.code
            response_body = error.read(2048).decode("utf-8", errors="replace")
            if status_code == 429:
                raise sidecar_error(
                    "PROVIDER_RATE_LIMIT",
                    True,
                    "Sidecar Provider 요청 한도를 초과했습니다.",
                    {
                        "status_code": status_code,
                        "path": path,
                        "response_body": response_body,
                    },
                ) from error
            if status_code in {408, 504}:
                raise sidecar_error(
                    "PROVIDER_TIMEOUT",
                    True,
                    "Sidecar Provider 요청 시간이 초과되었습니다.",
                    {
                        "status_code": status_code,
                        "path": path,
                        "response_body": response_body,
                    },
                ) from error
            raise sidecar_error(
                "PROVIDER_NOT_AVAILABLE" if status_code >= 500 else "PROVIDER_FAILURE",
                status_code >= 500,
                "Sidecar Provider HTTP 요청이 실패했습니다.",
                {
                    "status_code": status_code,
                    "path": path,
                    "response_body": response_body,
                },
            ) from error
        except TimeoutError as error:
            raise sidecar_error(
                "PROVIDER_TIMEOUT",
                True,
                "Sidecar Provider 연결 시간이 초과되었습니다.",
                {"path": path},
            ) from error
        except URLError as error:
            raise sidecar_error(
                "PROVIDER_NOT_AVAILABLE",
                True,
                "Sidecar Provider에 연결할 수 없습니다.",
                {"path": path},
            ) from error
        try:
            document: object = json.loads(body)
        except json.JSONDecodeError as error:
            raise sidecar_error(
                "OUTPUT_PARSE_ERROR",
                False,
                "Sidecar 응답이 JSON이 아닙니다.",
                {"path": path, "line": error.lineno, "column": error.colno},
            ) from error
        if not isinstance(document, Mapping):
            raise sidecar_error(
                "OUTPUT_PARSE_ERROR",
                False,
                "Sidecar 응답의 최상위 값이 객체가 아닙니다.",
                {"path": path},
            )
        return dict(document)

    async def _request_with_retry(
        self,
        method: str,
        path: str,
        payload: Mapping[str, object] | None,
    ) -> dict[str, object]:
        """일시적 Sidecar 실패를 경고 후 제한 횟수만 재시도한다."""
        last_error: RuntimeExecutionError | None = None
        for attempt in range(1, self._retry_attempts + 1):
            try:
                return await asyncio.to_thread(self._wire_request, method, path, payload)
            except RuntimeExecutionError as error:
                last_error = error
                if not error.retryable or attempt == self._retry_attempts:
                    raise
                LOGGER.warning(
                    "Sidecar Provider 요청을 재시도합니다.",
                    extra={
                        "provider_id": self._descriptor.provider_id,
                        "attempt": attempt,
                        "code": error.code,
                    },
                )
                await asyncio.sleep(min(0.1 * (2 ** (attempt - 1)), 1.0))
        if last_error is None:
            raise sidecar_error(
                "PROVIDER_FAILURE",
                False,
                "Sidecar Provider 재시도 상태가 손상되었습니다.",
                {"path": path},
            )
        raise last_error

    async def generate(self, request: LLMRequest) -> LLMResponse:
        """공통 Request를 Sidecar Wire Endpoint에 전달한다."""
        document = await self._request_with_retry(
            "POST",
            "/v1/generate",
            request_document(request),
        )
        response = response_from_document(document)
        if response.request_id != request.request_id:
            raise sidecar_error(
                "OUTPUT_PARSE_ERROR",
                False,
                "Sidecar가 Request ID를 보존하지 않았습니다.",
                {
                    "expected_request_id": request.request_id,
                    "actual_request_id": response.request_id,
                },
            )
        return response

    async def cancel(self, request_id: str) -> None:
        """Capability가 있을 때 Provider 요청 취소를 전달한다."""
        if "CANCELLATION" not in self._descriptor.capabilities:
            raise sidecar_error(
                "CAPABILITY_MISMATCH",
                False,
                "Sidecar Provider가 취소 Capability를 선언하지 않았습니다.",
                {"provider_id": self._descriptor.provider_id},
            )
        await self._request_with_retry("POST", f"/v1/cancel/{request_id}", {})

    async def close(self) -> None:
        """HTTP 요청별 연결 방식에는 유지 자원이 없다."""
        return None


async def create_sidecar_provider(
    endpoint: str,
    credential: str | None,
    timeout_seconds: float,
    retry_attempts: int,
) -> SidecarProvider:
    """Sidecar Descriptor와 Health를 확인한 Adapter를 생성한다."""
    placeholder = ProviderDescriptor(
        interface_version="1.0.0",
        provider_id="unresolved-sidecar",
        adapter_id="sidecar-http",
        adapter_version="1.0.0",
        capabilities=("TEXT_GENERATION",),
        max_context_tokens=None,
        max_output_tokens=None,
    )
    adapter = SidecarProvider(
        placeholder,
        endpoint,
        credential,
        timeout_seconds,
        retry_attempts,
    )
    descriptor_document = await adapter._request_with_retry("GET", "/v1/descriptor", None)
    await adapter._request_with_retry("GET", "/v1/health", None)
    return SidecarProvider(
        descriptor_from_document(descriptor_document),
        endpoint,
        credential,
        timeout_seconds,
        retry_attempts,
    )
