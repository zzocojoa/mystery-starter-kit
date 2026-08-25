"""Production Ready Story Fingerprint Library 등록 규칙."""

from collections.abc import Mapping
from copy import deepcopy

from VALIDATORS.exceptions import DuplicateStoryFingerprintError, StoryLibraryError
from VALIDATORS.models import ProjectState


def fingerprint_records(
    library: Mapping[str, object],
) -> list[dict[str, object]]:
    """Story Library의 Fingerprint 객체 배열을 엄격히 복사한다."""
    records = library.get("fingerprints")
    if not isinstance(records, list) or not all(isinstance(record, Mapping) for record in records):
        raise StoryLibraryError("story_library.fingerprints 객체 배열이 필요합니다.")
    return [dict(record) for record in records]


def validate_registration_state(
    fingerprint: Mapping[str, object],
    project_state: ProjectState,
) -> str:
    """Production Ready와 Project ID 일치를 검사한다."""
    if project_state["state"] != "PRODUCTION_READY":
        raise StoryLibraryError(
            "Production Ready Project만 Story Library에 등록할 수 있습니다: "
            f"state={project_state['state']}"
        )
    project_id = fingerprint.get("project_id")
    if not isinstance(project_id, str):
        raise StoryLibraryError("story_fingerprint.project_id 문자열이 필요합니다.")
    if project_id != project_state["project_id"]:
        raise StoryLibraryError(
            "Story Fingerprint와 Project State ID가 다릅니다: "
            f"fingerprint={project_id}, state={project_state['project_id']}"
        )
    return project_id


def register_story_fingerprint(
    library: Mapping[str, object],
    fingerprint: Mapping[str, object],
    project_state: ProjectState,
) -> dict[str, object]:
    """검증 완료 Fingerprint를 중복 없이 추가한 새 Library를 반환한다."""
    project_id = validate_registration_state(fingerprint, project_state)
    records = fingerprint_records(library)
    existing_ids = {record.get("project_id") for record in records}
    if project_id in existing_ids:
        raise DuplicateStoryFingerprintError(
            f"동일 Project Fingerprint가 이미 등록되었습니다: project_id={project_id}"
        )

    next_library = deepcopy(dict(library))
    next_library["fingerprints"] = [*records, deepcopy(dict(fingerprint))]
    return next_library


def make_history_record(
    fingerprint: Mapping[str, object],
    registered_at: str,
) -> dict[str, object]:
    """감사 가능한 Story Library 등록 이력 한 건을 만든다."""
    project_id = fingerprint.get("project_id")
    if not isinstance(project_id, str):
        raise StoryLibraryError("story_fingerprint.project_id 문자열이 필요합니다.")
    return {
        "registered_at": registered_at,
        "project_id": project_id,
        "story_signature": fingerprint.get("story", {}),
        "causal_signature": fingerprint.get("causal", {}),
    }
