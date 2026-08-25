"""Production Ready Story Library 등록 검증."""

from copy import deepcopy
from pathlib import Path

import pytest
from project_factory import make_complete_project_artifacts

from VALIDATORS.dependency import build_initial_project_state
from VALIDATORS.exceptions import DuplicateStoryFingerprintError, StoryLibraryError
from VALIDATORS.io import load_json_object
from VALIDATORS.library import register_story_fingerprint
from VALIDATORS.models import ProjectState
from VALIDATORS.schema_validation import collect_schema_errors

ROOT = Path(__file__).resolve().parents[1]


def make_ready_state() -> ProjectState:
    """Library 등록 테스트용 Production Ready 상태를 만든다."""
    graph = load_json_object(ROOT / "STANDARD" / "dependency_graph.json")
    state = build_initial_project_state(graph, "PRJ-002", "2026-08-25T00:00:00Z")
    state["state"] = "PRODUCTION_READY"
    state["current_gate"] = "GATE-13"
    return state


def test_empty_story_library_passes_schema() -> None:
    """초기 Story Library는 자체 Schema를 통과해야 한다."""
    library = load_json_object(ROOT / "STORY_LIBRARY" / "story_fingerprints.json")
    schema = load_json_object(ROOT / "STANDARD" / "schemas" / "story_library.schema.json")

    assert collect_schema_errors(library, schema, "story_library") == []


def test_production_ready_fingerprint_can_be_registered() -> None:
    """Production Ready Project의 Fingerprint는 Library에 한 번 등록할 수 있다."""
    library = load_json_object(ROOT / "STORY_LIBRARY" / "story_fingerprints.json")
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
    library = load_json_object(ROOT / "STORY_LIBRARY" / "story_fingerprints.json")
    fingerprint = make_complete_project_artifacts()["story_fingerprint"]
    assert isinstance(fingerprint, dict)
    not_ready = deepcopy(make_ready_state())
    not_ready["state"] = "QA_PASSED"

    with pytest.raises(StoryLibraryError, match="Production Ready"):
        register_story_fingerprint(library, fingerprint, not_ready)

    registered = register_story_fingerprint(library, fingerprint, make_ready_state())
    with pytest.raises(DuplicateStoryFingerprintError, match="이미 등록"):
        register_story_fingerprint(registered, fingerprint, make_ready_state())
