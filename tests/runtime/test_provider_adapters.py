"""In-process와 Sidecar Provider의 공통 Wire 계약 검증."""

import asyncio
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import cast

from RUNTIME.models import (
    GenerationOptions,
    LLMMessage,
    LLMRequest,
    LLMResponse,
    OutputContract,
    ProviderDescriptor,
    TokenUsage,
)
from RUNTIME.providers.in_process import InProcessProviderAdapter
from RUNTIME.providers.sidecar import create_sidecar_provider


def sample_request(request_id: str) -> LLMRequest:
    """Adapter Conformance에 필요한 최소 공통 요청을 만든다."""
    return LLMRequest(
        request_id=request_id,
        idempotency_key=f"IDEMPOTENCY-{request_id}",
        model_ref="adapter-test-model",
        messages=(LLMMessage(role="user", content="테스트"),),
        output_contract=OutputContract(mode="JSON_OBJECT", name="TEST", json_schema=None),
        generation=GenerationOptions(
            max_output_tokens=100,
            temperature=0.0,
            top_p=1.0,
            seed=None,
            stop=(),
        ),
        tools=(),
        deadline_ms=5000,
        metadata={"task_id": "adapter.test"},
        extensions={},
    )


def completed_response(request_id: str) -> LLMResponse:
    """공통 응답 모델을 만족하는 완료 응답을 만든다."""
    return LLMResponse(
        request_id=request_id,
        provider_request_id=f"PROVIDER-{request_id}",
        status="COMPLETED",
        finish_reason="STOP",
        text=None,
        structured_output={"result": "PASS"},
        tool_calls=(),
        usage=TokenUsage(input_tokens=1, output_tokens=1, cached_tokens=0),
        model_resolved="adapter-test-model-v1",
        warnings=(),
    )


def test_in_process_adapter_preserves_common_models() -> None:
    """In-process Adapter는 SDK 객체 없이 Request와 Response를 그대로 중개한다."""
    requests: list[str] = []
    closed: list[bool] = []

    async def handler(request: LLMRequest) -> LLMResponse:
        requests.append(request.request_id)
        return completed_response(request.request_id)

    async def close_handler() -> None:
        closed.append(True)

    adapter = InProcessProviderAdapter(
        ProviderDescriptor(
            interface_version="1.0.0",
            provider_id="in-process-test",
            adapter_id="test-handler",
            adapter_version="1.0.0",
            capabilities=("TEXT_GENERATION", "JSON_OBJECT"),
            max_context_tokens=1000,
            max_output_tokens=1000,
        ),
        handler,
        close_handler,
    )

    response = asyncio.run(adapter.generate(sample_request("REQ-IN-PROCESS")))
    asyncio.run(adapter.close())

    assert response.request_id == "REQ-IN-PROCESS"
    assert requests == ["REQ-IN-PROCESS"]
    assert closed == [True]


class SidecarHandler(BaseHTTPRequestHandler):
    """Sidecar 공통 Endpoint를 제공하는 격리 Test Server."""

    protocol_version = "HTTP/1.1"

    def write_document(self, document: dict[str, object]) -> None:
        """응답 객체를 길이가 명시된 JSON으로 기록한다."""
        encoded = json.dumps(document).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def do_GET(self) -> None:
        """Descriptor와 Health Endpoint를 응답한다."""
        if self.path == "/v1/descriptor":
            self.write_document(
                {
                    "interface_version": "1.0.0",
                    "provider_id": "sidecar-test",
                    "adapter_id": "http-test",
                    "adapter_version": "1.0.0",
                    "capabilities": ["TEXT_GENERATION", "JSON_OBJECT", "CANCELLATION"],
                    "max_context_tokens": 4096,
                    "max_output_tokens": 1024,
                }
            )
            return
        if self.path == "/v1/health":
            self.write_document({"status": "PASS"})
            return
        self.send_error(404)

    def do_POST(self) -> None:
        """Generate와 Cancel Endpoint를 공통 Wire 형식으로 응답한다."""
        content_length = int(self.headers.get("Content-Length", "0"))
        payload: object = json.loads(self.rfile.read(content_length).decode("utf-8") or "{}")
        if self.path == "/v1/generate" and isinstance(payload, dict):
            request_id = payload.get("request_id")
            assert isinstance(request_id, str)
            self.write_document(
                {
                    "request_id": request_id,
                    "provider_request_id": f"SIDECAR-{request_id}",
                    "status": "COMPLETED",
                    "finish_reason": "STOP",
                    "text": None,
                    "structured_output": {"result": "PASS"},
                    "tool_calls": [],
                    "usage": {"input_tokens": 1, "output_tokens": 1, "cached_tokens": 0},
                    "model_resolved": "sidecar-test-v1",
                    "warnings": [],
                }
            )
            return
        if self.path.startswith("/v1/cancel/"):
            self.write_document({"cancelled": True})
            return
        self.send_error(404)

    def log_message(self, format: str, *args: object) -> None:
        """Test 출력에 HTTP 접근 로그를 남기지 않는다."""
        del format, args


def run_sidecar_scenario(endpoint: str) -> tuple[str, str]:
    """Descriptor, Health, Generate, Cancel을 한 Event Loop에서 실행한다."""

    async def scenario() -> tuple[str, str]:
        adapter = await create_sidecar_provider(endpoint, None, 2.0, 2)
        try:
            response = await adapter.generate(sample_request("REQ-SIDECAR"))
            await adapter.cancel("REQ-SIDECAR")
            return adapter.descriptor.provider_id, response.request_id
        finally:
            await adapter.close()

    return asyncio.run(scenario())


def test_sidecar_adapter_conforms_to_descriptor_health_generate_and_cancel() -> None:
    """Sidecar Adapter는 네 필수 HTTP Endpoint와 공통 Wire 모델을 보존한다."""
    server = ThreadingHTTPServer(("127.0.0.1", 0), SidecarHandler)
    server_thread = threading.Thread(target=server.serve_forever, daemon=True)
    server_thread.start()
    host, port = cast(tuple[str, int], server.server_address)
    try:
        provider_id, request_id = run_sidecar_scenario(f"http://{host}:{port}")
    finally:
        server.shutdown()
        server.server_close()
        server_thread.join(timeout=2.0)

    assert provider_id == "sidecar-test"
    assert request_id == "REQ-SIDECAR"
