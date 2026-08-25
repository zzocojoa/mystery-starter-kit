"""Reference Firewall 정제와 충돌 검증."""

from pathlib import Path

import pytest

from VALIDATORS.exceptions import ConfigurationError
from VALIDATORS.io import load_json_object
from VALIDATORS.reference_validation import (
    REFERENCE_STORY_CATEGORIES,
    build_story_element_profile,
    sanitize_reference_profile,
    validate_reference_collision,
)

ROOT = Path(__file__).resolve().parents[1]
POLICY_PATH = ROOT / "STANDARD" / "reference_policy.json"


def empty_story_content() -> dict[str, object]:
    """Policy 전체 Category를 빈 배열로 갖는 Candidate Story Content를 만든다."""
    return {category: [] for category in REFERENCE_STORY_CATEGORIES}


def make_reference_material() -> dict[str, object]:
    """원문과 Story Content가 포함된 격리 전 Reference를 만든다."""
    return {
        "reference_id": "REF-001",
        "selected_style_features": ["PACING", "SUSPENSE_HANDLING"],
        "raw_text": "닫힌 통제실에서 여섯 번째 경보가 울리자 민서는 서버 전원을 내렸다",
        "story_content": {
            "CHARACTERS": ["민서"],
            "LOCATIONS": ["닫힌 통제실"],
            "INCIDENTS": ["여섯 번째 경보"],
            "UNIQUE_OBJECTS": ["서버 전원"],
        },
    }


def test_sanitized_profile_contains_no_raw_story_content() -> None:
    """Production Agent용 Profile에는 원문과 Story Content가 남아서는 안 된다."""
    policy = load_json_object(POLICY_PATH)

    profile = sanitize_reference_profile(make_reference_material(), policy)

    serialized = str(profile)
    assert "raw_text" not in profile
    assert "story_content" not in profile
    assert "민서" not in serialized
    assert profile["separation_attestation"] is True
    prohibited = policy.get("prohibited_story_content")
    assert isinstance(prohibited, list)
    assert tuple(prohibited) == REFERENCE_STORY_CATEGORIES


def test_reference_phrase_and_story_element_collision_fails() -> None:
    """긴 동일 문구와 다중 Story Element 재사용은 Reference Gate를 차단해야 한다."""
    policy = load_json_object(POLICY_PATH)
    story_content = empty_story_content()
    story_content.update(
        {
            "CHARACTERS": ["민서"],
            "LOCATIONS": ["닫힌 통제실"],
            "INCIDENTS": ["다른 사건"],
        }
    )
    candidate = {
        "project_id": "PRJ-001",
        "story_content": story_content,
    }
    script = (
        "기록에는 이렇게 적혔다. 닫힌 통제실에서 여섯 번째 경보가 울리자 "
        "민서는 서버 전원을 내렸다."
    )

    report = validate_reference_collision(
        script,
        candidate,
        make_reference_material(),
        policy,
    )

    assert report["result"] == "FAIL"
    issues = report["issues"]
    assert isinstance(issues, list)
    assert {issue["code"] for issue in issues} == {
        "REFERENCE_LEXICAL_COLLISION",
        "REFERENCE_STORY_ELEMENT_COLLISION",
    }


def test_distinct_candidate_passes_without_exposing_reference_text() -> None:
    """Story Element와 문구가 다른 후보는 통과하고 보고서에 원문을 노출하지 않는다."""
    policy = load_json_object(POLICY_PATH)
    story_content = empty_story_content()
    story_content.update(
        {
            "CHARACTERS": ["도윤"],
            "LOCATIONS": ["야외 주차장"],
        }
    )
    candidate = {
        "project_id": "PRJ-001",
        "story_content": story_content,
    }

    report = validate_reference_collision(
        "도윤은 비어 있는 차의 블랙박스 시간을 대조했다.",
        candidate,
        make_reference_material(),
        policy,
    )

    assert report["result"] == "PASS"
    assert "민서" not in str(report)


def test_project_profile_covers_every_prohibited_story_category() -> None:
    """Production Artifact는 Policy의 금지 Story Category 14개를 모두 추출해야 한다."""
    story = load_json_object(ROOT / "EXAMPLES" / "story_dna.example.json")
    case_input = {
        "central_mystery": "경보 뒤에 누가 사라졌는가",
        "final_truth": "통제실의 장치가 사건을 만들었다",
        "causal_truth": "안전 장치가 차단됐다",
        "culprit": "민서",
        "victim": "도윤",
        "culprit_motive": "기록 은폐",
        "method": "센서 차단",
        "unique_objects": ["붉은 출입 카드"],
    }
    characters = {
        "characters": [
            {"character_id": "CHAR-01", "name": "민서", "role": "CULPRIT"},
            {"character_id": "CHAR-02", "name": "도윤", "role": "VICTIM"},
        ]
    }
    relationships = {
        "relationships": [
            {
                "from": "CHAR-01",
                "to": "CHAR-02",
                "engine": "BROKEN_TRUST",
            }
        ]
    }
    actual_timeline = {"events": [{"location_id": "CONTROL_ROOM"}]}
    clue_matrix = {
        "clues": [
            {
                "description": "삭제된 출입 기록",
                "object_name": "붉은 출입 카드",
            }
        ]
    }
    causal_graph = {
        "fingerprint": {
            "root_cause": "기록 은폐",
            "mechanism": "센서 차단",
            "concealment": "로그 삭제",
            "discovery_path": "출입 기록 복구",
            "resolution": "구조",
        }
    }
    beat_sheet = {
        "beats": [
            {"type": "HOOK"},
            {"type": "FALSE_SOLUTION"},
            {"type": "REVEAL"},
        ]
    }
    final_script = "[DIALOGUE] 기록은 거짓말하지 않아. 체온은 37.2도였다."

    profile = build_story_element_profile(
        "PRJ-001",
        story,
        case_input,
        characters,
        relationships,
        actual_timeline,
        clue_matrix,
        causal_graph,
        beat_sheet,
        final_script,
    )
    story_content = profile.get("story_content")
    assert isinstance(story_content, dict)

    assert tuple(story_content) == REFERENCE_STORY_CATEGORIES
    assert story_content["CHARACTER_RELATIONSHIPS"] == [
        "민서 BROKEN_TRUST 도윤"
    ]
    assert story_content["VICTIM"] == ["도윤"]
    assert story_content["METHOD"] == ["센서 차단"]
    assert story_content["CLUES"] == ["삭제된 출입 기록"]
    assert story_content["UNIQUE_DIALOGUE"] == ["기록은 거짓말하지 않아. 체온은 37.2도였다."]
    assert story_content["UNIQUE_NUMBERS"] == ["37.2"]
    assert story_content["UNIQUE_OBJECTS"] == ["붉은 출입 카드"]
    assert story_content["BEAT_SEQUENCE"] == [
        "HOOK -> FALSE_SOLUTION -> REVEAL"
    ]


def test_extended_project_elements_trigger_reference_collision() -> None:
    """관계, 피해자, 방법, 단서, 반전, 숫자, 사물, Beat 재사용을 모두 탐지한다."""
    policy = load_json_object(POLICY_PATH)
    story_content = {
        "CHARACTERS": [],
        "CHARACTER_RELATIONSHIPS": ["민서 BROKEN_TRUST 도윤"],
        "LOCATIONS": [],
        "INCIDENTS": [],
        "CULPRIT": [],
        "VICTIM": ["도윤"],
        "MOTIVE": [],
        "METHOD": ["센서 차단"],
        "CLUES": ["삭제된 출입 기록"],
        "TWISTS": ["TW-05_TIMELINE"],
        "UNIQUE_DIALOGUE": ["기록은 거짓말하지 않아"],
        "UNIQUE_NUMBERS": ["37.2"],
        "UNIQUE_OBJECTS": ["붉은 출입 카드"],
        "BEAT_SEQUENCE": ["HOOK -> FALSE_SOLUTION -> REVEAL"],
    }
    candidate = {"project_id": "PRJ-001", "story_content": story_content}
    reference = {
        "reference_id": "REF-001",
        "raw_text": "서로 다른 문장으로 구성된 격리 원문",
        "story_content": story_content,
    }

    report = validate_reference_collision(
        "원문과 겹치지 않는 최종 대본",
        candidate,
        reference,
        policy,
    )

    assert report["result"] == "FAIL"
    assert report["matched_story_element_categories"] == sorted(
        category
        for category, values in story_content.items()
        if values
    )


def test_candidate_profile_missing_policy_category_is_rejected() -> None:
    """Policy Category가 하나라도 없는 Candidate Profile은 조용히 통과할 수 없다."""
    policy = load_json_object(POLICY_PATH)
    story_content = empty_story_content()
    del story_content["BEAT_SEQUENCE"]
    candidate = {"project_id": "PRJ-001", "story_content": story_content}

    with pytest.raises(ConfigurationError, match="Category가 누락"):
        validate_reference_collision(
            "서로 다른 최종 대본",
            candidate,
            make_reference_material(),
            policy,
        )
