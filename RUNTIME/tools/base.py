"""Runtime이 중개하는 외부 Tool Interface."""

from typing import Protocol, runtime_checkable


@runtime_checkable
class RuntimeTool(Protocol):
    """Provider가 직접 시스템에 접근하지 않도록 감싼 Tool 계약."""

    @property
    def name(self) -> str:
        """Allowlist 판정용 Tool 이름을 반환한다."""

    @property
    def description(self) -> str:
        """Provider에 공개할 Tool 설명을 반환한다."""

    @property
    def input_schema(self) -> dict[str, object]:
        """Tool 입력 Schema를 반환한다."""

    @property
    def output_schema(self) -> dict[str, object]:
        """Tool 출력 Schema를 반환한다."""

    async def invoke(
        self,
        arguments: dict[str, object],
        context: dict[str, str],
    ) -> dict[str, object]:
        """검증된 인자와 제한된 Context로 Tool을 호출한다."""
