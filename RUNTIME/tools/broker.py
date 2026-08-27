"""Task별 Tool Allowlist와 입출력 Schema를 강제하는 Broker."""

from collections.abc import Mapping, Sequence

from RUNTIME.errors import RuntimeExecutionError
from RUNTIME.models import ToolDefinition
from RUNTIME.tools.base import RuntimeTool
from VALIDATORS.schema_validation import collect_schema_errors

FORBIDDEN_TOOL_NAMES = {
    "arbitrary_shell",
    "arbitrary_file_write",
    "unrestricted_http",
    "credential_read",
}


def tool_definitions(
    registry: Mapping[str, RuntimeTool],
    allowed_tools: Sequence[str],
) -> tuple[ToolDefinition, ...]:
    """Task가 허용한 Tool 정의만 Provider에 공개한다."""
    definitions: list[ToolDefinition] = []
    for tool_name in allowed_tools:
        if tool_name in FORBIDDEN_TOOL_NAMES:
            raise RuntimeExecutionError(
                "TOOL_NOT_ALLOWED",
                False,
                "TASK",
                "Runtime에서 금지한 Tool을 Task가 요청했습니다.",
                None,
                None,
                {"tool_name": tool_name},
            )
        tool = registry.get(tool_name)
        if tool is None:
            raise RuntimeExecutionError(
                "TOOL_NOT_ALLOWED",
                False,
                "TASK",
                "Task가 허용했지만 등록되지 않은 Tool입니다.",
                None,
                None,
                {"tool_name": tool_name},
            )
        definitions.append(
            ToolDefinition(
                name=tool.name,
                description=tool.description,
                input_schema=tool.input_schema.copy(),
            )
        )
    return tuple(definitions)


async def invoke_tool(
    registry: Mapping[str, RuntimeTool],
    allowed_tools: Sequence[str],
    tool_name: str,
    arguments: dict[str, object],
    context: dict[str, str],
) -> dict[str, object]:
    """Allowlist와 Schema를 통과한 Tool만 호출한다."""
    if tool_name in FORBIDDEN_TOOL_NAMES or tool_name not in allowed_tools:
        raise RuntimeExecutionError(
            "TOOL_NOT_ALLOWED",
            False,
            "TASK",
            "Task가 허가하지 않은 Tool 호출입니다.",
            context.get("task_id"),
            None,
            {"tool_name": tool_name},
        )
    tool = registry.get(tool_name)
    if tool is None:
        raise RuntimeExecutionError(
            "TOOL_NOT_ALLOWED",
            False,
            "TASK",
            "등록되지 않은 Tool 호출입니다.",
            context.get("task_id"),
            None,
            {"tool_name": tool_name},
        )
    input_errors = collect_schema_errors(arguments, tool.input_schema, tool_name)
    if input_errors:
        raise RuntimeExecutionError(
            "OUTPUT_SCHEMA_ERROR",
            False,
            "TOOL_CALL",
            "Tool 입력 Schema 검증에 실패했습니다.",
            context.get("task_id"),
            None,
            {"tool_name": tool_name, "errors": input_errors},
        )
    result = await tool.invoke(arguments.copy(), context.copy())
    output_errors = collect_schema_errors(result, tool.output_schema, tool_name)
    if output_errors:
        raise RuntimeExecutionError(
            "OUTPUT_SCHEMA_ERROR",
            False,
            "TOOL_CALL",
            "Tool 출력 Schema 검증에 실패했습니다.",
            context.get("task_id"),
            None,
            {"tool_name": tool_name, "errors": output_errors},
        )
    return result
