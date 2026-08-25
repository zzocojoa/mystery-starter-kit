"""검증 도구가 사용하는 구체적 오류 형식."""


class StarterKitError(Exception):
    """Starter Kit 입력 또는 구성 오류."""


class InputFileNotFoundError(StarterKitError):
    """필수 입력 파일을 찾을 수 없는 오류."""


class InputFileReadError(StarterKitError):
    """입력 파일을 읽을 수 없는 오류."""


class InvalidJsonDocumentError(StarterKitError):
    """JSON 문서가 올바르지 않은 오류."""


class InvalidDocumentShapeError(StarterKitError):
    """JSON 최상위 구조가 객체가 아닌 오류."""


class OutputFileWriteError(StarterKitError):
    """결과 파일을 쓸 수 없는 오류."""


class ConfigurationError(StarterKitError):
    """계약 또는 기본값 구성이 올바르지 않은 오류."""


class InvalidSemanticVersionError(StarterKitError):
    """Semantic Version 문자열이 올바르지 않은 오류."""
