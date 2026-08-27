"""Runtime Tool 인스턴스 Registry."""

from collections.abc import Iterable

from RUNTIME.contracts import configuration_error
from RUNTIME.tools.base import RuntimeTool


def build_tool_registry(tools: Iterable[RuntimeTool]) -> dict[str, RuntimeTool]:
    """중복 없는 Tool 이름 사전을 만든다."""
    registry: dict[str, RuntimeTool] = {}
    for tool in tools:
        if tool.name in registry:
            raise configuration_error(
                "Runtime Tool 이름이 중복됩니다.",
                {"tool_name": tool.name},
            )
        registry[tool.name] = tool
    return registry
