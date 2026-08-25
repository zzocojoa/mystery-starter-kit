"""Story DNA v1.3 구조와 의미 규칙 검증."""

from copy import deepcopy
from pathlib import Path

from VALIDATORS.io import load_json_object
from VALIDATORS.schema_validation import collect_schema_errors
from VALIDATORS.story_validation import (
    validate_reference_profile_alignment,
    validate_story_dna_semantics,
    validate_user_case_constraints,
)

ROOT = Path(__file__).resolve().parents[1]
STORY_PATH = ROOT / "EXAMPLES" / "story_dna.example.json"
STORY_SCHEMA_PATH = ROOT / "STANDARD" / "schemas" / "story_dna.schema.json"
REFERENCE_POLICY_PATH = ROOT / "STANDARD" / "reference_policy.json"
REFERENCE_POLICY_SCHEMA_PATH = ROOT / "STANDARD" / "schemas" / "reference_policy.schema.json"
REFERENCE_PROFILE_SCHEMA_PATH = ROOT / "STANDARD" / "schemas" / "reference_profile.schema.json"
REFERENCE_PROFILE_TEMPLATE_PATH = (
    ROOT / "TEMPLATES" / "PROJECT" / "00_PROJECT" / "reference_profile.json"
)


def test_full_story_dna_example_passes_structure_and_semantics() -> None:
    """확장된 Story Diversity 필드를 포함한 기준 예제는 모든 검증을 통과해야 한다."""
    story = load_json_object(STORY_PATH)
    story_schema = load_json_object(STORY_SCHEMA_PATH)
    reference_policy = load_json_object(REFERENCE_POLICY_PATH)

    assert collect_schema_errors(story, story_schema, str(STORY_PATH)) == []
    assert validate_story_dna_semantics(story, reference_policy) == []


def test_reference_policy_matches_its_schema() -> None:
    """Reference Firewall 기준 문서는 자체 Schema를 통과해야 한다."""
    policy = load_json_object(REFERENCE_POLICY_PATH)
    schema = load_json_object(REFERENCE_POLICY_SCHEMA_PATH)

    assert collect_schema_errors(policy, schema, str(REFERENCE_POLICY_PATH)) == []


def test_empty_reference_profile_template_passes_schema() -> None:
    """Original Project용 NONE Profile은 별도 Artifact Schema를 통과해야 한다."""
    profile = load_json_object(REFERENCE_PROFILE_TEMPLATE_PATH)
    schema = load_json_object(REFERENCE_PROFILE_SCHEMA_PATH)

    assert collect_schema_errors(profile, schema, str(REFERENCE_PROFILE_TEMPLATE_PATH)) == []


def test_no_culprit_story_requires_causal_truth() -> None:
    """범인이 없는 구조는 범인 대신 인과적 진실을 명시해야 한다."""
    story = load_json_object(STORY_PATH)
    reference_policy = load_json_object(REFERENCE_POLICY_PATH)
    changed_story = deepcopy(story)
    story_dna = changed_story["story_dna"]
    assert isinstance(story_dna, dict)
    story_dna.pop("causal_truth", None)

    errors = validate_story_dna_semantics(changed_story, reference_policy)

    assert [error["code"] for error in errors] == ["CAUSAL_TRUTH_REQUIRED"]


def test_reference_inspired_story_rejects_story_content_leak() -> None:
    """Reference Profile은 정책이 금지한 Story Content를 모두 차단해야 한다."""
    story = load_json_object(STORY_PATH)
    reference_policy = load_json_object(REFERENCE_POLICY_PATH)
    changed_story = deepcopy(story)
    changed_story["story_source_mode"] = "REFERENCE_INSPIRED"
    changed_story["reference_profile"] = {
        "reference_id": "REF-001",
        "allowed_style_features": ["PRESENTATION_MODE", "CHARACTERS"],
        "prohibited_story_content": ["CHARACTERS"],
        "separation_attestation": True,
    }

    errors = validate_story_dna_semantics(changed_story, reference_policy)
    codes = {error["code"] for error in errors}

    assert "REFERENCE_STYLE_FEATURE_NOT_ALLOWED" in codes
    assert "REFERENCE_FIREWALL_INCOMPLETE" in codes


def test_reference_artifact_must_match_embedded_profile() -> None:
    """Story DNA와 별도 정제 Profile의 Reference ID가 다르면 차단해야 한다."""
    story = load_json_object(STORY_PATH)
    changed_story = deepcopy(story)
    changed_story["story_source_mode"] = "REFERENCE_INSPIRED"
    changed_story["reference_profile"] = {
        "reference_id": "REF-001",
        "allowed_style_features": ["PACING"],
        "prohibited_story_content": ["CHARACTERS"],
        "separation_attestation": True,
    }
    separate_profile = {
        "project_id": "PRJ-002",
        "mode": "REFERENCE_INSPIRED",
        "reference_id": "REF-002",
        "allowed_style_features": ["PACING"],
        "prohibited_story_content": ["CHARACTERS"],
        "separation_attestation": True,
    }

    issues = validate_reference_profile_alignment(changed_story, separate_profile)

    assert [issue["code"] for issue in issues] == [
        "REFERENCE_ARTIFACT_CONTENT_MISMATCH"
    ]


def test_user_case_locked_value_cannot_change_in_story_dna() -> None:
    """USER_CASE의 LOCKED 값과 다른 Story DNA는 GATE-02에서 차단해야 한다."""
    story = load_json_object(STORY_PATH)
    changed_story = deepcopy(story)
    changed_story["story_source_mode"] = "USER_CASE"
    production_config = {
        "story_source_mode": "USER_CASE",
        "user_case_constraints": [
            {"field": "protagonist_role", "value": "REPORTER", "status": "LOCKED"},
            {"field": "incident_type", "value": "DISAPPEARANCE", "status": "FLEXIBLE"},
            {"field": "primary_twist", "value": None, "status": "UNKNOWN"},
        ],
    }

    issues = validate_user_case_constraints(production_config, changed_story)

    assert [issue["code"] for issue in issues] == [
        "USER_CASE_LOCKED_VALUE_CHANGED"
    ]
