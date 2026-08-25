"""Reference Firewall 정제와 충돌 검증."""

from pathlib import Path

from VALIDATORS.io import load_json_object
from VALIDATORS.reference_validation import (
    sanitize_reference_profile,
    validate_reference_collision,
)

ROOT = Path(__file__).resolve().parents[1]
POLICY_PATH = ROOT / "STANDARD" / "reference_policy.json"


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


def test_reference_phrase_and_story_element_collision_fails() -> None:
    """긴 동일 문구와 다중 Story Element 재사용은 Reference Gate를 차단해야 한다."""
    policy = load_json_object(POLICY_PATH)
    candidate = {
        "project_id": "PRJ-001",
        "story_content": {
            "CHARACTERS": ["민서"],
            "LOCATIONS": ["닫힌 통제실"],
            "INCIDENTS": ["다른 사건"],
        },
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
    candidate = {
        "project_id": "PRJ-001",
        "story_content": {
            "CHARACTERS": ["도윤"],
            "LOCATIONS": ["야외 주차장"],
        },
    }

    report = validate_reference_collision(
        "도윤은 비어 있는 차의 블랙박스 시간을 대조했다.",
        candidate,
        make_reference_material(),
        policy,
    )

    assert report["result"] == "PASS"
    assert "민서" not in str(report)
