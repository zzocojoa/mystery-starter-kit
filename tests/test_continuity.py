"""연속성 Gate의 Timeline, Clue, Knowledge, Runtime 검증."""

from copy import deepcopy

from VALIDATORS.continuity import validate_continuity


def make_valid_artifacts() -> dict[str, dict[str, object]]:
    """모든 연속성 규칙을 통과하는 최소 Artifact 집합을 만든다."""
    return {
        "production_config": {
            "project_id": "PRJ-001",
            "target_runtime_minutes": 2,
            "runtime_tolerance_ratio": 0.1,
        },
        "characters": {
            "characters": [
                {"character_id": "CHAR-01", "name": "도윤"},
                {"character_id": "CHAR-02", "name": "서진"},
            ]
        },
        "facts": {"facts": [{"fact_id": "FACT-01", "statement": "기록이 비었다"}]},
        "knowledge_matrix": {
            "knowledge_events": [
                {
                    "character_id": "CHAR-01",
                    "fact_id": "FACT-01",
                    "learned_scene_order": 1,
                }
            ]
        },
        "actual_timeline": {
            "events": [
                {
                    "event_id": "EVT-01",
                    "start_minute": 0,
                    "end_minute": 10,
                    "location_id": "LOC-01",
                    "participant_ids": ["CHAR-01"],
                },
                {
                    "event_id": "EVT-02",
                    "start_minute": 10,
                    "end_minute": 20,
                    "location_id": "LOC-02",
                    "participant_ids": ["CHAR-01", "CHAR-02"],
                },
            ]
        },
        "clue_matrix": {
            "clues": [
                {
                    "clue_id": "CLUE-01",
                    "role": "CORE",
                    "introduced_scene_order": 1,
                    "introduced_scene_id": "SCN-01",
                    "resolved_scene_order": 2,
                    "resolved_scene_id": "SCN-02",
                },
                {
                    "clue_id": "CLUE-02",
                    "role": "RED_HERRING",
                    "introduced_scene_order": 1,
                    "introduced_scene_id": "SCN-01",
                    "resolved_scene_order": 2,
                    "resolved_scene_id": "SCN-02",
                },
            ]
        },
        "beat_sheet": {
            "beats": [
                {"beat_id": "BEAT-01", "type": "HOOK"},
                {"beat_id": "BEAT-02", "type": "REVEAL"},
            ]
        },
        "scene_cards": {
            "scenes": [
                {
                    "scene_id": "SCN-01",
                    "order": 1,
                    "beat_id": "BEAT-01",
                    "estimated_seconds": 60,
                    "clue_ids": ["CLUE-01", "CLUE-02"],
                    "knowledge_claims": [
                        {"character_id": "CHAR-01", "fact_id": "FACT-01"}
                    ],
                },
                {
                    "scene_id": "SCN-02",
                    "order": 2,
                    "beat_id": "BEAT-02",
                    "estimated_seconds": 60,
                    "clue_ids": ["CLUE-01", "CLUE-02"],
                    "knowledge_claims": [],
                },
            ]
        },
    }


def run_continuity(artifacts: dict[str, dict[str, object]]) -> dict[str, object]:
    """Artifact 사전을 통합 연속성 검사 인자로 전달한다."""
    return validate_continuity(
        artifacts["production_config"],
        artifacts["characters"],
        artifacts["facts"],
        artifacts["knowledge_matrix"],
        artifacts["actual_timeline"],
        artifacts["clue_matrix"],
        artifacts["beat_sheet"],
        artifacts["scene_cards"],
    )


def test_valid_artifacts_pass_continuity_gate() -> None:
    """정합한 Timeline과 지식·단서·Runtime은 통과해야 한다."""
    report = run_continuity(make_valid_artifacts())

    assert report["result"] == "PASS"
    assert report["issues"] == []


def test_timeline_and_knowledge_conflicts_are_detected() -> None:
    """동시 다중 장소와 학습 전 지식 사용을 함께 검출해야 한다."""
    artifacts = deepcopy(make_valid_artifacts())
    events = artifacts["actual_timeline"]["events"]
    knowledge_events = artifacts["knowledge_matrix"]["knowledge_events"]
    assert isinstance(events, list)
    assert isinstance(knowledge_events, list)
    second_event = events[1]
    knowledge_event = knowledge_events[0]
    assert isinstance(second_event, dict)
    assert isinstance(knowledge_event, dict)
    second_event["start_minute"] = 5
    knowledge_event["learned_scene_order"] = 2

    report = run_continuity(artifacts)
    issues = report["issues"]
    assert isinstance(issues, list)
    codes = {issue["code"] for issue in issues}

    assert "SIMULTANEOUS_LOCATION_CONFLICT" in codes
    assert "KNOWLEDGE_BOUNDARY_VIOLATION" in codes


def test_unresolved_clues_broken_reference_and_runtime_fail() -> None:
    """미회수 단서, 깨진 ID, Runtime 초과를 한 Gate에서 모두 보고해야 한다."""
    artifacts = deepcopy(make_valid_artifacts())
    clues = artifacts["clue_matrix"]["clues"]
    scenes = artifacts["scene_cards"]["scenes"]
    assert isinstance(clues, list)
    assert isinstance(scenes, list)
    first_clue = clues[0]
    first_scene = scenes[0]
    second_scene = scenes[1]
    assert isinstance(first_clue, dict)
    assert isinstance(first_scene, dict)
    assert isinstance(second_scene, dict)
    first_clue.pop("resolved_scene_order")
    first_scene["beat_id"] = "BEAT-404"
    first_scene["estimated_seconds"] = 300
    second_scene["estimated_seconds"] = 300

    report = run_continuity(artifacts)
    issues = report["issues"]
    assert isinstance(issues, list)
    codes = {issue["code"] for issue in issues}

    assert "CORE_CLUE_UNRESOLVED" in codes
    assert "BROKEN_ARTIFACT_REFERENCE" in codes
    assert "RUNTIME_OUT_OF_TOLERANCE" in codes
