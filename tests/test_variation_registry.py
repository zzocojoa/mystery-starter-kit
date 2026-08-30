"""Variation Engine·Catalog Registry와 Project Pin 검증."""

from pathlib import Path

import pytest

from VALIDATORS.exceptions import ConfigurationError
from VALIDATORS.io import load_json_object
from VALIDATORS.schema_validation import collect_schema_errors
from VALIDATORS.variation_registry import resolve_variation_runtime

ROOT = Path(__file__).resolve().parents[1]


def test_variation_registries_and_engine_specifications_pass_schema() -> None:
    """Version Registry와 모든 Engine Specification이 자체 Schema를 통과한다."""
    pairs = (
        (
            ROOT / "STANDARD" / "variation_engines" / "registry.json",
            ROOT / "STANDARD" / "schemas" / "variation_engine_registry.schema.json",
        ),
        (
            ROOT / "STANDARD" / "variation_catalogs" / "registry.json",
            ROOT / "STANDARD" / "schemas" / "variation_catalog_registry.schema.json",
        ),
    )
    for document_path, schema_path in pairs:
        assert (
            collect_schema_errors(
                load_json_object(document_path),
                load_json_object(schema_path),
                str(document_path),
            )
            == []
        )
    engine_schema = load_json_object(
        ROOT / "STANDARD" / "schemas" / "variation_engine_specification.schema.json"
    )
    for version in ("1.0.0", "2.0.0"):
        path = ROOT / "STANDARD" / "variation_engines" / f"{version}.json"
        assert collect_schema_errors(load_json_object(path), engine_schema, str(path)) == []


def test_project_pins_resolve_exact_engine_catalog_and_hashes() -> None:
    """Project Pin은 Registry의 정확한 Engine·Catalog와 Content Hash를 해석한다."""
    runtime = resolve_variation_runtime(
        ROOT,
        {
            "channel_content_version": "1.1.0",
            "variation_engine_version": "1.0.0",
            "variation_catalog_version": "1.0.0",
        },
    )
    assert runtime["engine_version"] == "1.0.0"
    assert runtime["catalog_version"] == "1.0.0"
    assert len(runtime["algorithm_sha256"]) == 64
    assert len(runtime["catalog_sha256"]) == 64


def test_channel_version_does_not_implicitly_override_project_pin() -> None:
    """Channel 세대와 다른 Project Pin은 암묵 변환하지 않고 실패한다."""
    with pytest.raises(ConfigurationError, match="VARIATION_VERSION_CHANNEL_MISMATCH"):
        resolve_variation_runtime(
            ROOT,
            {
                "channel_content_version": "1.1.0",
                "variation_engine_version": "2.0.0",
                "variation_catalog_version": "2.0.0",
            },
        )
