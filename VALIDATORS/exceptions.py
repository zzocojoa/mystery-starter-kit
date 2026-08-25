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


class InvalidProjectIdError(StarterKitError):
    """프로젝트 ID 형식이 올바르지 않은 오류."""


class ProjectAlreadyExistsError(StarterKitError):
    """동일한 프로젝트가 이미 존재하는 오류."""


class ProjectScaffoldError(StarterKitError):
    """프로젝트 Scaffold 생성에 실패한 오류."""


class StateTransitionError(StarterKitError):
    """Project Gate 순서 또는 Artifact 상태가 전이 조건을 충족하지 못한 오류."""


class StoryLibraryError(StarterKitError):
    """Production Ready Story Library 등록 조건을 충족하지 못한 오류."""


class DuplicateStoryFingerprintError(StoryLibraryError):
    """동일 Project의 Story Fingerprint가 이미 등록된 오류."""
