"""Project Manifest와 Production Config 구조 계약 검증."""

from copy import deepcopy
from pathlib import Path

from VALIDATORS.io import load_json_object
from VALIDATORS.schema_validation import collect_schema_errors

ROOT = Path(__file__).resolve().parents[1]
TEMPLATE_ROOT = ROOT / "TEMPLATES" / "PROJECT" / "00_PROJECT"
SCHEMA_ROOT = ROOT / "STANDARD" / "schemas"


def test_project_manifest_template_passes_schema() -> None:
    """Project Manifest Template은 식별과 Source Mode 계약을 통과해야 한다."""
    document = load_json_object(TEMPLATE_ROOT / "project_manifest.json")
    schema = load_json_object(SCHEMA_ROOT / "project_manifest.schema.json")

    assert collect_schema_errors(document, schema, "project_manifest") == []


def test_production_config_template_passes_schema() -> None:
    """Production Config Template은 Runtime과 승인 정책 계약을 통과해야 한다."""
    document = load_json_object(TEMPLATE_ROOT / "production_config.json")
    schema = load_json_object(SCHEMA_ROOT / "production_config.schema.json")

    assert collect_schema_errors(document, schema, "production_config") == []
    assert document["channel_content_version"] == "2.0.0"
    assert document["variation_engine_version"] == "2.0.0"
    assert document["variation_catalog_version"] == "2.0.0"
    assert document["genre"] == "CRIME_PSYCHOLOGICAL_THRILLER"


def test_user_case_config_requires_explicit_constraint_statuses() -> None:
    """USER_CASE는 LOCKED, FLEXIBLE, UNKNOWN 입력 상태를 구조적으로 보존해야 한다."""
    config_template = load_json_object(TEMPLATE_ROOT / "production_config.json")
    config = deepcopy(config_template)
    config["story_source_mode"] = "USER_CASE"
    config["user_case_constraints"] = [
        {"field": "protagonist_role", "value": "REPORTER", "status": "LOCKED"},
        {"field": "incident_type", "value": "DISAPPEARANCE", "status": "FLEXIBLE"},
        {"field": "primary_twist", "value": None, "status": "UNKNOWN"},
    ]
    manifest = load_json_object(TEMPLATE_ROOT / "project_manifest.json")
    manifest["story_source_mode"] = "USER_CASE"
    story = load_json_object(ROOT / "EXAMPLES" / "story_dna.example.json")
    story["story_source_mode"] = "USER_CASE"
    config_schema = load_json_object(SCHEMA_ROOT / "production_config.schema.json")
    manifest_schema = load_json_object(SCHEMA_ROOT / "project_manifest.schema.json")
    story_schema = load_json_object(SCHEMA_ROOT / "story_dna.schema.json")

    assert collect_schema_errors(config, config_schema, "user_case_config") == []
    assert collect_schema_errors(manifest, manifest_schema, "user_case_manifest") == []
    assert collect_schema_errors(story, story_schema, "user_case_story") == []
