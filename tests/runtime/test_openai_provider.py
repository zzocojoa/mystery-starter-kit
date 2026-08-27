"""OpenAI Responses Provider의 공통 계약과 오류 정규화 검증."""

import asyncio
import json
import threading
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import TypedDict, cast

import pytest

from RUNTIME.errors import RuntimeErrorCode, RuntimeExecutionError
from RUNTIME.models import (
    GenerationOptions,
    LLMMessage,
    LLMRequest,
    LLMResponse,
    OutputContract,
    OutputMode,
)
from RUNTIME.providers.registry import load_entry_point_factory
from RUNTIME_ADAPTERS.openai_responses import OpenAIResponsesProvider, create_provider


class CapturedRequest(TypedDict):
    """Test Server가 받은 OpenAI 요청의 안전한 관찰값."""

    path: str
    headers: dict[str, str]
    body: dict[str, object]


class OpenAITestServer(ThreadingHTTPServer):
    """응답과 수신 요청을 소유하는 격리 OpenAI HTTP Server."""

    def __init__(self, status_code: int, response_document: Mapping[str, object]) -> None:
        self.status_code = status_code
        self.response_document = dict(response_document)
        self.captured_requests: list[CapturedRequest] = []
        super().__init__(("127.0.0.1", 0), OpenAITestHandler)


class OpenAITestHandler(BaseHTTPRequestHandler):
    """Responses API의 최소 POST 경계를 재현한다."""

    protocol_version = "HTTP/1.1"

    def do_POST(self) -> None:
        """요청을 기록하고 지정된 JSON 응답을 반환한다."""
        server = cast(OpenAITestServer, self.server)
        content_length = int(self.headers.get("Content-Length", "0"))
        raw_body = self.rfile.read(content_length).decode("utf-8")
        parsed: object = json.loads(raw_body)
        assert isinstance(parsed, Mapping)
        server.captured_requests.append(
            {
                "path": self.path,
                "headers": dict(self.headers.items()),
                "body": dict(parsed),
            }
        )
        encoded = json.dumps(server.response_document).encode("utf-8")
        self.send_response(server.status_code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(encoded)))
        self.send_header("x-request-id", "req_header_test")
        self.end_headers()
        self.wfile.write(encoded)

    def log_message(self, format: str, *args: object) -> None:
        """Test 출력에 HTTP 접근 로그를 남기지 않는다."""
        del format, args


@contextmanager
def openai_test_server(
    status_code: int,
    response_document: Mapping[str, object],
) -> Iterator[tuple[str, OpenAITestServer]]:
    """격리 HTTP Server를 시작하고 종료한다."""
    server = OpenAITestServer(status_code, response_document)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    host, port = cast(tuple[str, int], server.server_address)
    try:
        yield f"http://{host}:{port}/v1/responses", server
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2.0)


def sample_request(
    request_id: str,
    mode: OutputMode,
    stop: tuple[str, ...],
) -> LLMRequest:
    """OpenAI Adapter 검증용 공통 요청을 만든다."""
    json_schema: dict[str, object] | None = None
    if mode == "JSON_SCHEMA":
        json_schema = {
            "type": "object",
            "additionalProperties": False,
            "required": ["result"],
            "properties": {"result": {"type": "string"}},
        }
    return LLMRequest(
        request_id=request_id,
        idempotency_key=f"IDEMPOTENCY-{request_id}",
        model_ref="gpt-5.4-mini",
        messages=(
            LLMMessage(role="system", content="계약을 지켜라."),
            LLMMessage(role="user", content="결과를 생성하라."),
        ),
        output_contract=OutputContract(
            mode=mode,
            name="AGENT_RESULT",
            json_schema=json_schema,
        ),
        generation=GenerationOptions(
            max_output_tokens=512,
            temperature=0.3,
            top_p=1.0,
            seed=None,
            stop=stop,
        ),
        tools=(),
        deadline_ms=2000,
        metadata={"task_id": "story.test"},
        extensions={},
    )


def completed_document(output_text: str) -> dict[str, object]:
    """실제 Responses API와 같은 완료 응답을 만든다."""
    return {
        "id": "resp_test_123",
        "status": "completed",
        "model": "gpt-5.4-mini-2026-03-17",
        "output": [
            {
                "type": "message",
                "role": "assistant",
                "content": [{"type": "output_text", "text": output_text}],
            }
        ],
        "usage": {
            "input_tokens": 21,
            "output_tokens": 7,
            "input_tokens_details": {"cached_tokens": 4},
        },
    }


def test_openai_provider_normalizes_structured_response_and_request() -> None:
    """공통 요청과 응답 Identity, Format, Usage를 보존한다."""
    request = sample_request("REQ-OPENAI", "JSON_SCHEMA", ())
    with openai_test_server(200, completed_document('{"result":"PASS"}')) as (
        endpoint,
        server,
    ):
        provider = OpenAIResponsesProvider("openai", "test-secret", endpoint, 2.0)
        response = asyncio.run(provider.generate(request))
        asyncio.run(provider.close())

    assert response == LLMResponse(
        request_id="REQ-OPENAI",
        provider_request_id="resp_test_123",
        status="COMPLETED",
        finish_reason="STOP",
        text='{"result":"PASS"}',
        structured_output={"result": "PASS"},
        tool_calls=(),
        usage=response.usage,
        model_resolved="gpt-5.4-mini-2026-03-17",
        warnings=(),
    )
    assert response.usage.input_tokens == 21
    assert response.usage.output_tokens == 7
    assert response.usage.cached_tokens == 4
    assert provider.descriptor.capabilities == (
        "TEXT_GENERATION",
        "JSON_OBJECT",
        "JSON_SCHEMA_OUTPUT",
        "SYSTEM_MESSAGES",
        "USAGE_REPORTING",
    )

    assert len(server.captured_requests) == 1
    captured = server.captured_requests[0]
    assert captured["path"] == "/v1/responses"
    assert captured["headers"]["Authorization"] == "Bearer test-secret"
    assert captured["headers"]["Idempotency-Key"] == "IDEMPOTENCY-REQ-OPENAI"
    assert captured["body"] == {
        "model": "gpt-5.4-mini",
        "input": [{"role": "user", "content": "결과를 생성하라."}],
        "max_output_tokens": 512,
        "store": False,
        "text": {
            "format": {
                "type": "json_schema",
                "name": "AGENT_RESULT",
                "schema": request.output_contract.json_schema,
                "strict": True,
            }
        },
        "instructions": "계약을 지켜라.",
        "temperature": 0.3,
    }
    assert "top_p" not in captured["body"]


@pytest.mark.parametrize(
    ("status_code", "expected_code", "retryable"),
    [
        (408, "PROVIDER_TIMEOUT", True),
        (409, "PROVIDER_NOT_AVAILABLE", True),
        (429, "PROVIDER_RATE_LIMIT", True),
        (500, "PROVIDER_NOT_AVAILABLE", True),
        (401, "PROVIDER_FAILURE", False),
    ],
)
def test_openai_provider_normalizes_http_errors(
    status_code: int,
    expected_code: RuntimeErrorCode,
    retryable: bool,
) -> None:
    """재시도 가능한 HTTP 상태와 영구 실패를 구분한다."""
    error_document = {
        "error": {
            "type": "test_error",
            "message": "test-secret must never escape",
        }
    }
    with openai_test_server(status_code, error_document) as (endpoint, _server):
        provider = OpenAIResponsesProvider("openai", "test-secret", endpoint, 2.0)
        with pytest.raises(RuntimeExecutionError) as caught:
            asyncio.run(provider.generate(sample_request("REQ-ERROR", "JSON_OBJECT", ())))

    assert caught.value.code == expected_code
    assert caught.value.retryable is retryable
    assert caught.value.safe_context["status_code"] == status_code
    assert caught.value.safe_context["provider_request_id"] == "req_header_test"
    assert "test-secret" not in json.dumps(caught.value.as_dict())
    assert "[REDACTED]" in cast(str, caught.value.safe_context["response_body"])


def test_openai_provider_normalizes_refusal_incomplete_and_failed_response() -> None:
    """거부, 길이 제한, Provider 실패를 Runtime 상태로 구분한다."""
    refusal_document = {
        "id": "resp_refusal",
        "status": "completed",
        "model": "gpt-5.4-mini",
        "output": [
            {
                "type": "message",
                "content": [{"type": "refusal", "refusal": "요청 거부"}],
            }
        ],
        "usage": None,
    }
    with openai_test_server(200, refusal_document) as (endpoint, _server):
        provider = OpenAIResponsesProvider("openai", "test-secret", endpoint, 2.0)
        refusal = asyncio.run(
            provider.generate(sample_request("REQ-REFUSAL", "JSON_OBJECT", ()))
        )

    incomplete_document = completed_document('{"result":')
    incomplete_document["status"] = "incomplete"
    incomplete_document["incomplete_details"] = {"reason": "max_output_tokens"}
    with openai_test_server(200, incomplete_document) as (endpoint, _server):
        provider = OpenAIResponsesProvider("openai", "test-secret", endpoint, 2.0)
        incomplete = asyncio.run(
            provider.generate(sample_request("REQ-INCOMPLETE", "JSON_OBJECT", ()))
        )

    failed_document = completed_document("")
    failed_document["status"] = "failed"
    with openai_test_server(200, failed_document) as (endpoint, _server):
        provider = OpenAIResponsesProvider("openai", "test-secret", endpoint, 2.0)
        failed = asyncio.run(provider.generate(sample_request("REQ-FAILED", "JSON_OBJECT", ())))

    assert refusal.status == "REFUSED"
    assert refusal.finish_reason == "FILTERED"
    assert refusal.text is None
    assert incomplete.status == "COMPLETED"
    assert incomplete.finish_reason == "LENGTH"
    assert incomplete.structured_output is None
    assert failed.status == "FAILED"
    assert failed.finish_reason == "ERROR"
    assert failed.warnings == ("openai_status:failed",)


def test_openai_provider_is_registered_as_runtime_entry_point() -> None:
    """배포 Metadata에서 OpenAI Factory를 정확히 하나 발견한다."""
    factory = load_entry_point_factory("openai-responses")
    provider = factory("openai", "test-secret")

    assert provider.descriptor.provider_id == "openai"
    assert provider.descriptor.adapter_id == "openai-responses"


def test_openai_provider_rejects_undeclared_features_and_missing_credential() -> None:
    """선언하지 않은 기능과 Credential 누락을 명시적으로 거부한다."""
    provider = OpenAIResponsesProvider(
        "openai",
        "test-secret",
        "http://127.0.0.1:1/v1/responses",
        1.0,
    )
    with pytest.raises(RuntimeExecutionError) as unsupported:
        asyncio.run(provider.generate(sample_request("REQ-STOP", "JSON_OBJECT", ("END",))))
    with pytest.raises(RuntimeExecutionError) as missing_credential:
        create_provider("openai", None)

    assert unsupported.value.code == "CAPABILITY_MISMATCH"
    assert unsupported.value.retryable is False
    assert unsupported.value.safe_context["unsupported"] == ["stop"]
    assert missing_credential.value.code == "RUNTIME_CONFIGURATION_ERROR"
    assert missing_credential.value.safe_context == {
        "provider_id": "openai",
        "credential_env": "OPENAI_API_KEY",
    }
