"""Novelty Index 생명주기와 Published Story Library 등록 규칙."""

from collections.abc import Mapping
from copy import deepcopy

from VALIDATORS.exceptions import DuplicateStoryFingerprintError, StoryLibraryError
from VALIDATORS.models import ProjectState
from VALIDATORS.novelty import build_story_signature

NOVELTY_ACTIVE_STATUSES = frozenset(
    {"DRAFT", "EDITORIAL_PENDING", "PRODUCTION_READY"}
)
NOVELTY_STATUSES = frozenset({*NOVELTY_ACTIVE_STATUSES, "ABANDONED"})


def fingerprint_records(
    library: Mapping[str, object],
) -> list[dict[str, object]]:
    """Story Library의 Fingerprint 객체 배열을 엄격히 복사한다."""
    records = library.get("fingerprints")
    if not isinstance(records, list) or not all(isinstance(record, Mapping) for record in records):
        raise StoryLibraryError("story_library.fingerprints 객체 배열이 필요합니다.")
    return [dict(record) for record in records]


def novelty_records(index: Mapping[str, object]) -> list[dict[str, object]]:
    """Novelty Index Entry 객체 배열을 엄격하게 복사한다."""
    records = index.get("entries")
    if not isinstance(records, list) or not all(
        isinstance(record, Mapping) for record in records
    ):
        raise StoryLibraryError("novelty_index.entries 객체 배열이 필요합니다.")
    return [dict(record) for record in records]


def novelty_history(index: Mapping[str, object]) -> list[Mapping[str, object]]:
    """Abandoned Project를 제외한 시점 순서 Novelty 비교 기록을 반환한다."""
    history: list[Mapping[str, object]] = []
    for record in novelty_records(index):
        status = record.get("status")
        if status not in NOVELTY_STATUSES:
            raise StoryLibraryError(
                f"Novelty Index 상태가 잘못됐습니다: status={status!r}"
            )
        if status == "ABANDONED":
            continue
        fingerprint = record.get("fingerprint")
        if isinstance(fingerprint, Mapping):
            history.append(deepcopy(dict(fingerprint)))
            continue
        signature = record.get("story_signature")
        project_id = record.get("project_id")
        if not isinstance(signature, Mapping) or not isinstance(project_id, str):
            raise StoryLibraryError(
                "Novelty Index Entry에 project_id와 story_signature가 필요합니다."
            )
        history.append(
            {
                "project_id": project_id,
                "story": deepcopy(dict(signature)),
            }
        )
    return history


def upsert_novelty_entry(
    index: Mapping[str, object],
    project_id: str,
    status: str,
    story_signature: Mapping[str, object],
    fingerprint: Mapping[str, object] | None,
    updated_at: str,
) -> dict[str, object]:
    """Project Novelty Entry를 최초 삽입 순서를 보존하며 갱신한다."""
    if status not in NOVELTY_STATUSES:
        raise StoryLibraryError(
            f"Novelty Index 상태가 잘못됐습니다: status={status!r}"
        )
    records = novelty_records(index)
    positions = [
        position
        for position, record in enumerate(records)
        if record.get("project_id") == project_id
    ]
    if len(positions) > 1:
        raise StoryLibraryError(
            f"Novelty Index에 Project가 중복됐습니다: project_id={project_id}"
        )
    next_record: dict[str, object] = {
        "project_id": project_id,
        "status": status,
        "story_signature": deepcopy(dict(story_signature)),
        "updated_at": updated_at,
    }
    if fingerprint is not None:
        next_record["fingerprint"] = deepcopy(dict(fingerprint))
    if positions:
        position = positions[0]
        indexed_at = records[position].get("indexed_at")
        if not isinstance(indexed_at, str):
            raise StoryLibraryError(
                f"Novelty Index indexed_at이 잘못됐습니다: project_id={project_id}"
            )
        next_record["indexed_at"] = indexed_at
        records[position] = next_record
    else:
        next_record["indexed_at"] = updated_at
        records.append(next_record)
    next_index = deepcopy(dict(index))
    next_index["entries"] = records
    return next_index


def abandon_novelty_entry(
    index: Mapping[str, object],
    project_id: str,
    updated_at: str,
) -> dict[str, object]:
    """제작을 종료한 Project를 Novelty 비교 대상에서 제외한다."""
    records = novelty_records(index)
    matches = [record for record in records if record.get("project_id") == project_id]
    if len(matches) != 1:
        raise StoryLibraryError(
            f"ABANDONED로 변경할 Novelty Entry가 하나여야 합니다: project_id={project_id}"
        )
    record = matches[0]
    signature = record.get("story_signature")
    if not isinstance(signature, Mapping):
        raise StoryLibraryError(
            f"Novelty Entry story_signature가 잘못됐습니다: project_id={project_id}"
        )
    fingerprint = record.get("fingerprint")
    return upsert_novelty_entry(
        index,
        project_id,
        "ABANDONED",
        signature,
        fingerprint if isinstance(fingerprint, Mapping) else None,
        updated_at,
    )


def update_novelty_for_gate(
    index: Mapping[str, object],
    gate_id: str,
    story_document: Mapping[str, object],
    fingerprint: Mapping[str, object] | None,
    updated_at: str,
) -> dict[str, object]:
    """Novelty와 관련된 Gate Commit을 Lifecycle Entry에 반영한다."""
    status_by_gate = {
        "GATE-02": "DRAFT",
        "GATE-10": "DRAFT",
        "GATE-13": "EDITORIAL_PENDING",
    }
    status = status_by_gate.get(gate_id)
    if status is None:
        return deepcopy(dict(index))
    project_id = story_document.get("project_id")
    if not isinstance(project_id, str) or not project_id:
        raise StoryLibraryError("Story DNA project_id 문자열이 필요합니다.")
    if gate_id in {"GATE-10", "GATE-13"} and fingerprint is None:
        raise StoryLibraryError(
            f"{gate_id} Novelty Index 갱신에 Story Fingerprint가 필요합니다."
        )
    return upsert_novelty_entry(
        index,
        project_id,
        status,
        build_story_signature(story_document),
        fingerprint,
        updated_at,
    )


def mark_novelty_production_ready(
    index: Mapping[str, object],
    fingerprint: Mapping[str, object],
    updated_at: str,
) -> dict[str, object]:
    """Production Finalize를 통과한 Project의 Novelty 상태를 확정한다."""
    project_id = fingerprint.get("project_id")
    story = fingerprint.get("story")
    if not isinstance(project_id, str) or not isinstance(story, Mapping):
        raise StoryLibraryError(
            "Production Ready Novelty 갱신에 project_id와 story가 필요합니다."
        )
    return upsert_novelty_entry(
        index,
        project_id,
        "PRODUCTION_READY",
        story,
        fingerprint,
        updated_at,
    )


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
    readiness = project_state["readiness"]
    readiness_values: Mapping[str, object] = readiness
    expected = {
        "artifact_status": "ARTIFACT_COMPLETE",
        "contract_status": "CONTRACT_VALIDATED",
        "process_status": "PROCESS_CONFORMANT",
        "editorial_status": "EDITORIAL_APPROVED",
    }
    mismatches = {
        field: {"expected": value, "actual": readiness_values[field]}
        for field, value in expected.items()
        if readiness_values[field] != value
    }
    if mismatches:
        raise StoryLibraryError(
            f"Production Ready 세부 조건이 충족되지 않았습니다: mismatches={mismatches}"
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
