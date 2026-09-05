"""독립 Source ID가 Readable Report와 Gateway까지 보존되는지 검증한다."""

from collections.abc import Callable, Mapping
from copy import deepcopy
from pathlib import Path
from typing import cast

import pytest
from test_broadcast_readable_v2_source_fixtures import (
    SourceFixture,
    apply_feature_fixture,
    render_fixture_machine_master,
)
from test_broadcast_readable_v2_validation import (
    build_report,
    mapping_records,
    render_fixture,
    validate_report,
)

from RUNTIME.contracts import load_artifact_contracts
from RUNTIME.errors import RuntimeExecutionError
from RUNTIME.output_gateway import validate_artifact_content
from VALIDATORS.broadcast_readable_v2 import legacy_report_2_0_from_current

ROOT = Path(__file__).resolve().parents[1]
ReportProjection = Callable[[Mapping[str, object]], dict[str, object]]


def replace_identifier(value: object, original_id: str, replacement_id: str) -> object:
    """JSON의 정확한 ID 값과 재구성 참조를 입력 변경 없이 함께 교체한다."""
    if isinstance(value, str):
        return replacement_id if value == original_id else value
    if isinstance(value, list):
        return [replace_identifier(item, original_id, replacement_id) for item in value]
    if isinstance(value, Mapping):
        return {
            key: replace_identifier(item, original_id, replacement_id)
            for key, item in value.items()
        }
    return value


def screenplay_with_unit_id(unit_id: str) -> dict[str, object]:
    """독립 R1의 첫 Unit ID와 관련 참조를 교체한 Source 사본을 만든다."""
    fixture = apply_feature_fixture("R1")
    screenplay = fixture["screenplay_units"]
    scene = mapping_records(screenplay, "scenes")[0]
    original_id = mapping_records(scene, "units")[0]["unit_id"]
    assert isinstance(original_id, str)
    return cast(dict[str, object], replace_identifier(screenplay, original_id, unit_id))


def fixture_with_unit_id(unit_id: str) -> SourceFixture:
    """변경된 독립 Source에서 Machine Master를 다시 렌더링한다."""
    fixture = apply_feature_fixture("R1")
    fixture["screenplay_units"] = screenplay_with_unit_id(unit_id)
    fixture["final_script"] = render_fixture_machine_master(fixture)
    return fixture


def validate_source_artifact(artifact_name: str, document: Mapping[str, object]) -> None:
    """문서를 해당 Artifact의 정식 Source 계약으로 검증한다."""
    contract = load_artifact_contracts(ROOT)[artifact_name]
    validate_artifact_content(
        ROOT,
        "test.source_identifier",
        artifact_name,
        contract["media_type"],
        document,
        contract,
    )


def assert_report_roundtrip(
    fixture: SourceFixture,
    report: dict[str, object],
    actual_markdown: str,
) -> None:
    """의미 검증과 등록 Version의 Output Gateway가 같은 Report를 승인한다."""
    assert report["result"] == "NEEDS_REVIEW"
    assert report["issues"] == []
    assert validate_report(report, fixture, actual_markdown) == []
    validate_source_artifact("broadcast_readable_report", report)


@pytest.mark.parametrize("unit_id", ["UNIT-01-001", "UNIT-ALPHA_01", "UNIT-1", "UNIT-999"])
@pytest.mark.parametrize(
    "report_projection",
    [dict, legacy_report_2_0_from_current],
    ids=["current-2.1", "legacy-2.0"],
)
def test_source_valid_unit_ids_survive_report_gateway(
    unit_id: str,
    report_projection: ReportProjection,
) -> None:
    """Source가 허용한 ID를 현재·역사적 Report가 변환 없이 보존한다."""
    fixture = fixture_with_unit_id(unit_id)
    validate_source_artifact("screenplay_units", fixture["screenplay_units"])
    actual = render_fixture(fixture)
    report = report_projection(build_report(fixture, actual))
    matching = [
        mapping
        for mapping in mapping_records(report, "unit_mappings")
        if mapping["unit_id"] == unit_id
    ]

    assert len(matching) == 1
    assert matching[0]["owner_id"] == unit_id
    assert unit_id not in actual
    assert_report_roundtrip(fixture, report, actual)


@pytest.mark.parametrize("unit_id", ["UNIT-", "UNIT-lower", "UNIT 01", "TURN-001-01", "UNIT-한글"])
def test_source_invalid_unit_ids_remain_rejected(unit_id: str) -> None:
    """Report 범위 정합화가 잘못된 Source ID까지 허용하지 않는다."""
    document = screenplay_with_unit_id(unit_id)

    with pytest.raises(RuntimeExecutionError) as caught:
        validate_source_artifact("screenplay_units", document)

    assert caught.value.code == "OUTPUT_SCHEMA_ERROR"
    assert caught.value.artifact_name == "screenplay_units"


def test_compound_unit_owner_mismatch_remains_rejected() -> None:
    """복합 ID에서도 다른 Owner로 바꾼 Report는 의미 검증에서 거부된다."""
    fixture = fixture_with_unit_id("UNIT-01-001")
    actual = render_fixture(fixture)
    report = build_report(fixture, actual)
    tampered = deepcopy(report)
    mapping_records(tampered, "unit_mappings")[0]["owner_id"] = "UNIT-ALPHA_01"

    assert "BROADCAST_READABLE_V2_OWNER_ID_MISMATCH" in {
        issue["code"] for issue in validate_report(tampered, fixture, actual)
    }
    assert mapping_records(report, "unit_mappings")[0]["owner_id"] == "UNIT-01-001"


def fixture_with_non_speaking_character() -> SourceFixture:
    """Source 계약에 맞는 비발화 인물과 관계를 독립 R1 사본에 추가한다."""
    fixture = apply_feature_fixture("R1")
    characters = mapping_records(fixture["characters"], "characters")
    relationships = mapping_records(fixture["relationships"], "relationships")
    existing_id = characters[0]["character_id"]
    assert isinstance(existing_id, str)
    assert existing_id.startswith("CHAR-")
    assert all(character["character_id"] != "CHARACTER-99" for character in characters)
    assert all(relationship["relationship_id"] != "LINK-99" for relationship in relationships)
    fixture["characters"] = {
        **fixture["characters"],
        "characters": [
            *characters,
            {
                "character_id": "CHARACTER-99",
                "name": "비발화 확인 인물",
                "role": "BACKGROUND",
                "production_role": "BACKGROUND",
            },
        ],
    }
    fixture["relationships"] = {
        **fixture["relationships"],
        "relationships": [
            *relationships,
            {
                "relationship_id": "LINK-99",
                "from": "CHARACTER-99",
                "to": existing_id,
                "engine": "BACKGROUND_CONNECTION",
                "display_summary": "인물 표에만 표시되는 비발화 관계.",
            },
        ],
    }
    fixture["final_script"] = render_fixture_machine_master(fixture)
    return fixture


@pytest.mark.parametrize(
    "report_projection",
    [dict, legacy_report_2_0_from_current],
    ids=["current-2.1", "legacy-2.0"],
)
def test_canonical_non_speaking_character_survives_relationship_mapping(
    report_projection: ReportProjection,
) -> None:
    """Characters 계약의 비발화 인물 ID도 관계 Mapping과 Gateway에 보존한다."""
    fixture = fixture_with_non_speaking_character()
    validate_source_artifact("characters", fixture["characters"])
    validate_source_artifact("relationships", fixture["relationships"])
    validate_source_artifact("screenplay_units", fixture["screenplay_units"])
    speakers = {
        unit.get("speaker_id")
        for scene in mapping_records(fixture["screenplay_units"], "scenes")
        for unit in mapping_records(scene, "units")
        if isinstance(unit.get("speaker_id"), str)
    }
    actual = render_fixture(fixture)
    report = report_projection(build_report(fixture, actual))
    relationship = next(
        mapping
        for mapping in mapping_records(report, "relationship_mappings")
        if mapping["relationship_id"] == "LINK-99"
    )

    assert "CHARACTER-99" not in speakers
    assert "비발화 확인 인물" in actual
    assert "CHARACTER-99" in cast(list[str], relationship["affected_character_rows"])
    assert_report_roundtrip(fixture, report, actual)
