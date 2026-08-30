"""Project 변경 이력 기록."""

import json
from collections.abc import Mapping
from pathlib import Path

from VALIDATORS.exceptions import ConfigurationError


def append_change_log(
    project_path: Path,
    event: str,
    detail: Mapping[str, object],
    occurred_at: str,
) -> None:
    """Project 변경 이력을 JSONL에 추가한다."""
    record = {
        "occurred_at": occurred_at,
        "event": event,
        "detail": dict(detail),
    }
    log_path = project_path / "00_PROJECT" / "change_log.jsonl"
    try:
        with log_path.open("a", encoding="utf-8") as output_file:
            output_file.write(json.dumps(record, ensure_ascii=False) + "\n")
    except OSError as error:
        raise ConfigurationError(
            f"Project Change Log 기록에 실패했습니다: path={log_path}, detail={error}"
        ) from error


def change_log_bytes(
    existing: bytes,
    event: str,
    detail: Mapping[str, object],
    occurred_at: str,
) -> bytes:
    """기존 Log를 수정하지 않고 다음 JSONL Byte열을 만든다."""
    record = {
        "occurred_at": occurred_at,
        "event": event,
        "detail": dict(detail),
    }
    prefix = existing if not existing or existing.endswith(b"\n") else existing + b"\n"
    return prefix + (json.dumps(record, ensure_ascii=False) + "\n").encode("utf-8")
