"""Runtime 계약 경계에서 사용하는 엄격한 데이터 형식."""

from dataclasses import dataclass
from typing import Literal, NotRequired, Protocol, TypedDict, runtime_checkable

ProviderCapability = Literal[
    "TEXT_GENERATION",
    "JSON_OBJECT",
    "JSON_SCHEMA_OUTPUT",
    "TOOL_CALLING",
    "STREAMING",
    "SYSTEM_MESSAGES",
    "CANCELLATION",
    "USAGE_REPORTING",
]
DataClass = Literal[
    "PUBLIC",
    "INTERNAL",
    "SENSITIVE",
    "REFERENCE_SANITIZED",
    "REFERENCE_RAW",
    "PERSONAL_DATA",
]
ExecutorKind = Literal["CORE", "LLM", "HYBRID", "HUMAN", "COMPOSITE"]
RunStatus = Literal[
    "CREATED",
    "PLANNED",
    "RUNNING",
    "WAITING_PROVIDER",
    "VALIDATING",
    "REVISING",
    "WAITING_HUMAN",
    "COMPLETED",
    "FAILED",
    "CANCELLED",
]
TaskStatus = Literal[
    "PENDING",
    "READY",
    "RUNNING",
    "RETRYING",
    "SUCCEEDED",
    "FAILED",
    "BLOCKED",
    "SKIPPED",
    "CANCELLED",
]
AgentResultStatus = Literal[
    "SUCCEEDED",
    "NEEDS_REVISION",
    "NEEDS_HUMAN",
    "REFUSED",
    "FAILED",
]
OutputMode = Literal["JSON_SCHEMA", "JSON_OBJECT", "TEXT"]
ProviderResponseStatus = Literal["COMPLETED", "REFUSED", "FAILED"]
ProviderFinishReason = Literal["STOP", "LENGTH", "TOOL_CALL", "FILTERED", "ERROR"]
ApprovalDecision = Literal["APPROVED", "REJECTED"]


@dataclass(frozen=True)
class ProviderDescriptor:
    """Provider Adapter의 교체 가능한 Capability 설명."""

    interface_version: str
    provider_id: str
    adapter_id: str
    adapter_version: str
    capabilities: tuple[ProviderCapability, ...]
    max_context_tokens: int | None
    max_output_tokens: int | None


@dataclass(frozen=True)
class LLMMessage:
    """Provider 독립 Prompt 메시지."""

    role: str
    content: str


@dataclass(frozen=True)
class OutputContract:
    """Task가 요구하는 Provider 출력 형식."""

    mode: OutputMode
    name: str
    json_schema: dict[str, object] | None


@dataclass(frozen=True)
class GenerationOptions:
    """Provider 독립 생성 제한."""

    max_output_tokens: int
    temperature: float | None
    top_p: float | None
    seed: int | None
    stop: tuple[str, ...]


@dataclass(frozen=True)
class ToolDefinition:
    """Provider에 공개할 Allowlist Tool 계약."""

    name: str
    description: str
    input_schema: dict[str, object]


@dataclass(frozen=True)
class LLMRequest:
    """Provider Adapter 공통 요청."""

    request_id: str
    idempotency_key: str
    model_ref: str
    messages: tuple[LLMMessage, ...]
    output_contract: OutputContract
    generation: GenerationOptions
    tools: tuple[ToolDefinition, ...]
    deadline_ms: int | None
    metadata: dict[str, str]
    extensions: dict[str, object]


@dataclass(frozen=True)
class TokenUsage:
    """Provider 사용량의 정규화 형식."""

    input_tokens: int | None
    output_tokens: int | None
    cached_tokens: int | None


@dataclass(frozen=True)
class LLMResponse:
    """Provider SDK 객체를 노출하지 않는 공통 응답."""

    request_id: str
    provider_request_id: str | None
    status: ProviderResponseStatus
    finish_reason: ProviderFinishReason
    text: str | None
    structured_output: dict[str, object] | None
    tool_calls: tuple[dict[str, object], ...]
    usage: TokenUsage
    model_resolved: str
    warnings: tuple[str, ...]


@runtime_checkable
class LLMProvider(Protocol):
    """외부 또는 Local LLM Adapter가 구현할 Interface."""

    @property
    def descriptor(self) -> ProviderDescriptor:
        """Provider Capability를 반환한다."""

    async def generate(self, request: LLMRequest) -> LLMResponse:
        """Provider에 정규화된 생성 요청을 전달한다."""

    async def close(self) -> None:
        """Provider 연결 자원을 정리한다."""


class ArtifactCandidate(TypedDict):
    """검증 전 Provider Artifact 후보."""

    artifact_name: str
    media_type: str
    content: object


class AgentResult(TypedDict):
    """Provider가 반환할 수 있는 유일한 결과 Envelope."""

    schema_family: str
    schema_version: str
    run_id: str
    task_id: str
    agent_id: str
    attempt: int
    status: AgentResultStatus
    artifacts: list[ArtifactCandidate]
    assumptions: list[str]
    warnings: list[str]
    change_summary: list[str]


class RuntimeTask(TypedDict):
    """한 번의 실제 호출을 정의하는 최소 권한 계약."""

    agent_id: str
    executor: ExecutorKind
    target_gate: str
    reads: list[str]
    optional_reads: NotRequired[list[str]]
    writes: list[str]
    depends_on_tasks: list[str]
    condition: str
    model_profile: str | None
    output_contract: str
    commit_policy: str
    retry_policy: str
    budget_profile: str
    standard_resources: list[str]
    allowed_tools: list[str]
    required_data_classes: list[DataClass]
    approval_required: bool


class ContextItem(TypedDict):
    """Prompt에 전달되는 비명령성 Context."""

    context_id: str
    artifact_name: str
    media_type: str
    sha256: str
    status: str
    trust_level: DataClass
    instructional: bool
    content: object


class PromptBundle(TypedDict):
    """컴파일된 Prompt와 감사 Hash."""

    messages: tuple[LLMMessage, ...]
    prompt_hash: str
    input_hashes: dict[str, str]


class RuntimeTaskState(TypedDict):
    """한 Runtime Task의 운영 상태."""

    status: TaskStatus
    attempt: int
    provider_id: str | None
    model_resolved: str | None
    input_hashes: dict[str, str]
    prompt_hash: str | None
    error: dict[str, object] | None


class RuntimeRun(TypedDict):
    """Project State와 분리된 Provider 실행 상태."""

    schema_family: str
    schema_version: str
    run_id: str
    project_id: str
    project_path: str
    status: RunStatus
    from_gate: str
    to_gate: str
    route_profile: str
    reference_source: str | None
    current_task_id: str | None
    tasks: dict[str, RuntimeTaskState]
    created_at: str
    updated_at: str
    cancel_requested: bool
    error: dict[str, object] | None


class RuntimeApproval(TypedDict):
    """입력 Hash에 결합된 Human 승인."""

    schema_family: str
    schema_version: str
    approval_id: str
    run_id: str
    task_id: str
    decision: ApprovalDecision
    actor: str
    reason: str
    bound_input_hashes: dict[str, str]
    created_at: str


class ProviderRoute(TypedDict):
    """선택 가능한 Provider와 Model 조합."""

    provider_id: str
    model_ref: str


class SelectedRoute(TypedDict):
    """Capability와 정책을 통과한 실제 Route."""

    provider_id: str
    model_ref: str
    provider: LLMProvider


class ArtifactContract(TypedDict):
    """출력 Artifact의 형식과 커밋 제한."""

    media_type: str
    schema: str | None
    validators: list[str]
    commit_policy: str
    max_bytes: int


class PlannedTask(TypedDict):
    """실행 순서가 확정된 Task 요약."""

    task_id: str
    target_gate: str
    executor: ExecutorKind
    status: Literal["PLANNED", "SKIPPED"]


class ExecutionPlan(TypedDict):
    """현재 Project State에서 건너뛰지 않는 실행 계획."""

    project_id: str
    current_gate: str
    from_gate: str
    to_gate: str
    tasks: list[PlannedTask]
