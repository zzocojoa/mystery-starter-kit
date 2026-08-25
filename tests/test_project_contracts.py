"""Project Manifest와 Production Config 구조 계약 검증."""

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
