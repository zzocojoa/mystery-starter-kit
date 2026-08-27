"""Python Callable을 Provider Interface로 연결하는 In-process Adapter."""

from collections.abc import Awaitable, Callable

from RUNTIME.models import LLMRequest, LLMResponse, ProviderDescriptor

ProviderHandler = Callable[[LLMRequest], Awaitable[LLMResponse]]


class InProcessProviderAdapter:
    """Provider SDK를 Core 밖 Callable에 캡슐화하는 Adapter."""

    def __init__(
        self,
        descriptor: ProviderDescriptor,
        handler: ProviderHandler,
        close_handler: Callable[[], Awaitable[None]],
    ) -> None:
        self._descriptor = descriptor
        self._handler = handler
        self._close_handler = close_handler

    @property
    def descriptor(self) -> ProviderDescriptor:
        """등록된 Provider Descriptor를 반환한다."""
        return self._descriptor

    async def generate(self, request: LLMRequest) -> LLMResponse:
        """외부 Callable에 정규화 요청만 전달한다."""
        return await self._handler(request)

    async def close(self) -> None:
        """외부 Callable의 연결 정리를 실행한다."""
        await self._close_handler()
