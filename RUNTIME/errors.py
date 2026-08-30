"""Runtime의 표준화된 오류 모델."""

from typing import Literal

RuntimeErrorCode = Literal[
    "RUNTIME_CONFIGURATION_ERROR",
    "PROVIDER_NOT_AVAILABLE",
    "PROVIDER_RATE_LIMIT",
    "PROVIDER_TIMEOUT",
    "PROVIDER_REFUSAL",
    "PROVIDER_FAILURE",
    "CAPABILITY_MISMATCH",
    "DATA_POLICY_VIOLATION",
    "CONTEXT_LIMIT_EXCEEDED",
    "OUTPUT_PARSE_ERROR",
    "OUTPUT_SCHEMA_ERROR",
    "ARTIFACT_OWNERSHIP_VIOLATION",
    "UNAUTHORIZED_ARTIFACT",
    "INPUT_HASH_CHANGED",
    "GATE_REJECTED",
    "PROCESS_TRACE_MISSING",
    "BUDGET_EXCEEDED",
    "HUMAN_APPROVAL_REQUIRED",
    "HUMAN_INPUT_REQUIRED",
    "HUMAN_INPUT_INVALID",
    "HUMAN_INPUT_NOT_EXPECTED",
    "HUMAN_INPUT_SOURCE_TRUTH_MISMATCH",
    "HUMAN_INPUT_CONFLICT",
    "CLINICAL_SUBJECT_MAPPING_MISSING",
    "CLINICAL_SUBJECT_MAPPING_AMBIGUOUS",
    "RUN_CANCELLED",
    "PROJECT_LOCKED",
    "TRANSACTION_ERROR",
    "TOOL_NOT_ALLOWED",
]


class RuntimeExecutionError(Exception):
    """Runtime 경계에서 전달하는 안전한 구조화 오류."""

    def __init__(
        self,
        code: RuntimeErrorCode,
        retryable: bool,
        scope: str,
        message: str,
        task_id: str | None,
        artifact_name: str | None,
        safe_context: dict[str, object],
    ) -> None:
        super().__init__(message)
        self.code = code
        self.retryable = retryable
        self.scope = scope
        self.task_id = task_id
        self.artifact_name = artifact_name
        self.safe_context = safe_context.copy()

    def as_dict(self) -> dict[str, object]:
        """비밀이나 Provider 원본 예외를 제외한 오류 객체를 반환한다."""
        return {
            "code": self.code,
            "retryable": self.retryable,
            "scope": self.scope,
            "task_id": self.task_id,
            "artifact_name": self.artifact_name,
            "message": str(self),
            "safe_context": self.safe_context.copy(),
        }
