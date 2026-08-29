"""Production Ready Story Library 등록 검증."""

from copy import deepcopy
from pathlib import Path

import pytest
from project_factory import make_complete_project_artifacts

from VALIDATORS.dependency import build_initial_project_state
from VALIDATORS.exceptions import DuplicateStoryFingerprintError, StoryLibraryError
from VALIDATORS.io import load_json_object
from VALIDATORS.library import (
    abandon_novelty_entry,
    novelty_history,
    register_story_fingerprint,
    upsert_novelty_entry,
)
from VALIDATORS.models import ProjectState
from VALIDATORS.schema_validation import collect_schema_errors

ROOT = Path(__file__).resolve().parents[1]


def make_empty_library() -> dict[str, object]:
    """등록 동작을 독립적으로 검증할 빈 Story Library를 생성한다."""
    return {
        "schema_family": "story-library",
        "schema_version": "1.1.0",
        "fingerprints": [],
    }


def make_ready_state() -> ProjectState:
    """Library 등록 테스트용 Production Ready 상태를 만든다."""
    graph = load_json_object(ROOT / "STANDARD" / "dependency_graph.json")
    state = build_initial_project_state(graph, "PRJ-002", "2026-08-25T00:00:00Z")
    state["state"] = "PRODUCTION_READY"
    state["current_gate"] = "GATE-13"
    state["readiness"] = {
        "artifact_status": "ARTIFACT_COMPLETE",
        "contract_status": "CONTRACT_VALIDATED",
        "process_status": "PROCESS_CONFORMANT",
        "editorial_status": "EDITORIAL_APPROVED",
        "process_start_gate": "GATE-00",
        "process_revision": 1,
    }
    return state


def test_story_library_passes_schema() -> None:
    """현재 Story Library는 등록 건수와 무관하게 자체 Schema를 통과해야 한다."""
    library = load_json_object(ROOT / "STORY_LIBRARY" / "published_fingerprints.json")
    schema = load_json_object(ROOT / "STANDARD" / "schemas" / "story_library.schema.json")

    assert collect_schema_errors(library, schema, "story_library") == []


def test_novelty_index_passes_schema_without_project_records() -> None:
    """Novelty Index는 Project가 없어도 Schema를 통과해야 한다."""
    index = load_json_object(ROOT / "STORY_LIBRARY" / "novelty_index.json")
    schema = load_json_object(
        ROOT / "STANDARD" / "schemas" / "novelty_index.schema.json"
    )

    assert collect_schema_errors(index, schema, "novelty_index") == []
    assert novelty_history(index) == []


def test_production_ready_fingerprint_can_be_registered() -> None:
    """Production Ready Project의 Fingerprint는 Library에 한 번 등록할 수 있다."""
    library = make_empty_library()
    fingerprint = make_complete_project_artifacts()["story_fingerprint"]
    assert isinstance(fingerprint, dict)

    registered = register_story_fingerprint(library, fingerprint, make_ready_state())

    records = registered["fingerprints"]
    assert isinstance(records, list)
    assert len(records) == 1
    assert library["fingerprints"] == []
    schema = load_json_object(ROOT / "STANDARD" / "schemas" / "story_library.schema.json")
    assert collect_schema_errors(registered, schema, "registered_library") == []


def test_non_ready_and_duplicate_registration_are_rejected() -> None:
    """미완료 Project와 동일 Project의 중복 등록을 모두 차단해야 한다."""
    library = make_empty_library()
    fingerprint = make_complete_project_artifacts()["story_fingerprint"]
    assert isinstance(fingerprint, dict)
    not_ready = deepcopy(make_ready_state())
    not_ready["state"] = "QA_PASSED"

    with pytest.raises(StoryLibraryError, match="Production Ready"):
        register_story_fingerprint(library, fingerprint, not_ready)

    registered = register_story_fingerprint(library, fingerprint, make_ready_state())
    with pytest.raises(DuplicateStoryFingerprintError, match="이미 등록"):
        register_story_fingerprint(registered, fingerprint, make_ready_state())


def test_novelty_index_tracks_draft_fingerprint_and_abandoned_lifecycle() -> None:
    """Novelty Index는 Draft부터 추적하고 Abandoned를 비교에서 제외해야 한다."""
    index: dict[str, object] = {
        "schema_family": "novelty-index",
        "schema_version": "1.0.0",
        "entries": [],
    }
    fingerprint = make_complete_project_artifacts()["story_fingerprint"]
    assert isinstance(fingerprint, dict)
    story = fingerprint["story"]
    assert isinstance(story, dict)

    draft = upsert_novelty_entry(
        index,
        "PRJ-002",
        "DRAFT",
        story,
        None,
        "2026-08-28T00:00:00Z",
    )
    completed = upsert_novelty_entry(
        draft,
        "PRJ-002",
        "EDITORIAL_PENDING",
        story,
        fingerprint,
        "2026-08-28T01:00:00Z",
    )

    assert novelty_history(completed) == [fingerprint]
    abandoned = abandon_novelty_entry(
        completed,
        "PRJ-002",
        "2026-08-28T02:00:00Z",
    )
    assert novelty_history(abandoned) == []


def test_gate_two_refresh_removes_stale_downstream_fingerprint() -> None:
    """Story DNA 재작성 시 이전 Gate의 완성 Fingerprint를 재사용하지 않아야 한다."""
    fingerprint = make_complete_project_artifacts()["story_fingerprint"]
    assert isinstance(fingerprint, dict)
    story = fingerprint["story"]
    assert isinstance(story, dict)
    index: dict[str, object] = {
        "schema_family": "novelty-index",
        "schema_version": "1.0.0",
        "entries": [
            {
                "project_id": "PRJ-002",
                "status": "EDITORIAL_PENDING",
                "story_signature": story,
                "fingerprint": fingerprint,
                "indexed_at": "2026-08-28T00:00:00Z",
                "updated_at": "2026-08-28T01:00:00Z",
            }
        ],
    }
    revised_story = {**story, "setting": "ISLAND"}

    refreshed = upsert_novelty_entry(
        index,
        "PRJ-002",
        "DRAFT",
        revised_story,
        None,
        "2026-08-28T02:00:00Z",
    )

    entries = refreshed["entries"]
    assert isinstance(entries, list)
    entry = entries[0]
    assert isinstance(entry, dict)
    assert "fingerprint" not in entry
    assert novelty_history(refreshed) == [
        {"project_id": "PRJ-002", "story": revised_story}
    ]
