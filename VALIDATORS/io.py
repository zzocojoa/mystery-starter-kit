"""JSON 파일 입출력 경계."""

import json
from collections.abc import Mapping
from pathlib import Path
from typing import cast

from VALIDATORS.exceptions import (
    InputFileNotFoundError,
    InputFileReadError,
    InvalidDocumentShapeError,
    InvalidJsonDocumentError,
    OutputFileWriteError,
)


def load_json_object(path: Path) -> dict[str, object]:
    """JSON 객체를 읽고 구체적인 입력 오류를 발생시킨다."""
    try:
        with path.open("r", encoding="utf-8") as input_file:
            document: object = json.load(input_file)
    except FileNotFoundError as error:
        raise InputFileNotFoundError(f"필수 JSON 파일을 찾을 수 없습니다: path={path}") from error
    except PermissionError as error:
        raise InputFileReadError(f"JSON 파일 읽기 권한이 없습니다: path={path}") from error
    except json.JSONDecodeError as error:
        raise InvalidJsonDocumentError(
            f"JSON 문법이 올바르지 않습니다: path={path}, line={error.lineno}, "
            f"column={error.colno}, detail={error.msg}"
        ) from error
    except OSError as error:
        raise InputFileReadError(
            f"JSON 파일을 읽지 못했습니다: path={path}, detail={error}"
        ) from error

    if not isinstance(document, Mapping):
        raise InvalidDocumentShapeError(
            f"JSON 최상위 값은 객체여야 합니다: path={path}, actual_type={type(document).__name__}"
        )

    return cast(dict[str, object], dict(document))


def write_json_object(path: Path, document: Mapping[str, object]) -> None:
    """JSON 객체를 UTF-8 형식으로 기록한다."""
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8") as output_file:
            json.dump(document, output_file, ensure_ascii=False, indent=2)
            output_file.write("\n")
    except PermissionError as error:
        raise OutputFileWriteError(f"결과 파일 쓰기 권한이 없습니다: path={path}") from error
    except OSError as error:
        raise OutputFileWriteError(
            f"결과 파일을 쓰지 못했습니다: path={path}, detail={error}"
        ) from error
