# Runtime Provider Adapter Guide

## 공통 Interface

Provider Adapter는 `RUNTIME.models.LLMProvider` Protocol을 구현하고 Vendor SDK 객체를 Runtime Core로 노출하지 않는다.

- `descriptor`: `provider_descriptor.schema.json`과 일치하는 Capability·Token Limit
- `generate(request)`: 공통 `LLMRequest`를 받아 공통 `LLMResponse` 반환
- `close()`: 연결·Client 자원을 명시적으로 정리

Adapter는 Project 파일, Project State, Gate 상태를 쓰지 않는다. Credential은 생성 시 환경 변수에서 전달받고 Request, Response, Event, 오류에 복사하지 않는다.

## In-process Plugin

Registry의 `adapter_type`을 `IN_PROCESS_PLUGIN`으로 설정하고 `adapter_entry_point`에 `mystery_runtime.providers` Entry Point 이름을 쓴다. Factory Signature는 다음과 같다.

```python
def create_provider(provider_id: str, credential: str | None) -> LLMProvider:
    ...
```

Factory는 Registry Key와 같은 `descriptor.provider_id`를 반환해야 한다. Vendor SDK Import와 예외 정규화는 이 Adapter 패키지 내부에만 둔다. Runtime의 `InProcessProviderAdapter`는 비동기 Handler를 공통 Protocol로 감싸는 최소 구현을 제공한다.

## HTTP Sidecar

Registry의 `adapter_type`을 `SIDECAR_HTTP`로 설정하고 `endpoint`를 지정한다. Sidecar는 다음 Endpoint를 제공한다.

| Method | Path | 계약 |
|---|---|---|
| `GET` | `/v1/descriptor` | Provider Descriptor JSON |
| `GET` | `/v1/health` | 연결 가능한 JSON 객체 |
| `POST` | `/v1/generate` | `llm_request.schema.json` → `llm_response.schema.json` |
| `POST` | `/v1/cancel/{request_id}` | `CANCELLATION` Capability가 있을 때 취소 |

Sidecar는 Request ID를 Response에 그대로 보존한다. HTTP 429, 408/504, 5xx는 각각 Rate Limit, Timeout, Unavailable로 정규화하며 제한 재시도 후 마지막 오류를 반환한다. 그 밖의 오류와 잘못된 JSON은 Retry 불가능한 명시 오류다.

## 등록 예시

```json
{
  "adapter_type": "SIDECAR_HTTP",
  "adapter_entry_point": "sidecar-http",
  "enabled": true,
  "credential_env": "MYSTERY_PROVIDER_TOKEN",
  "endpoint": "http://127.0.0.1:8080",
  "data_policy": {
    "allowed_classes": ["PUBLIC", "INTERNAL", "REFERENCE_SANITIZED"]
  }
}
```

실제 Secret 값은 JSON에 넣지 않는다. 등록 후 `mystery-runtime providers`와 `mystery-runtime doctor`로 Descriptor, Health, Credential 참조, Data Policy를 검증한다. 새 Adapter는 In-process 또는 Sidecar Conformance Test를 추가해야 한다.

## OpenAI Responses Plugin

`openai-responses` Entry Point는 Python 표준 HTTP Client만 사용해 [OpenAI Responses API](https://developers.openai.com/api/reference/resources/responses/methods/create)를 호출한다. Runtime Core에는 Vendor SDK 객체나 OpenAI 전용 요청 형식을 노출하지 않는다. Text, JSON Object, JSON Schema Output, System Message, Usage Reporting만 Capability로 선언하며 Tool Calling, Streaming, Cancellation은 구현하지 않는다.

기본 Registry의 `openai` 정의는 비활성화되어 Fake Provider Golden Path를 바꾸지 않는다. 실제 연결 시 Secret을 파일에 쓰지 말고 Process 환경에만 주입한 뒤 정의를 활성화한다.

```bash
export OPENAI_API_KEY='...'
# RUNTIME/contracts/provider_registry.json에서 openai.enabled를 true로 변경한다.
.venv/bin/mystery-runtime doctor
.venv/bin/mystery-runtime providers
```

기본 Route는 Responses API와 Structured Outputs를 지원하는 [`gpt-5.4-mini`](https://developers.openai.com/api/docs/models/gpt-5.4-mini)다. HTTP 429, 408/504, 409, 5xx와 연결 오류는 Runtime 재시도가 가능한 공통 오류로 정규화한다. 인증·권한·그 밖의 4xx, 잘못된 응답 JSON, 거부 응답은 재시도하지 않는다.
