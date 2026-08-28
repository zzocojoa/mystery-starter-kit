"""Provider 독립 LLM Agent Runtime 공개 패키지."""

from importlib import import_module
from typing import TYPE_CHECKING, cast

if TYPE_CHECKING:
    from RUNTIME.engine import execute_run, resume_run
    from RUNTIME.planner import build_execution_plan

__all__ = ["build_execution_plan", "execute_run", "resume_run"]


def __getattr__(name: str) -> object:
    """공개 Runtime 함수를 순환 의존 없이 지연 로드한다."""
    if name == "build_execution_plan":
        return cast(object, getattr(import_module("RUNTIME.planner"), name))
    if name in {"execute_run", "resume_run"}:
        return cast(object, getattr(import_module("RUNTIME.engine"), name))
    raise AttributeError(f"RUNTIME 모듈에 공개 속성이 없습니다: name={name}")
