"""Broadcast Readable v2 독립 Report와 변이 탐지를 검증한다."""

from copy import deepcopy
from hashlib import sha256
from pathlib import Path
from typing import TypedDict

import pytest
from jsonschema import Draft202012Validator

from RUNTIME.broadcast_readable_v2_renderer import (
    render_broadcast_readable_script_v2,
)
from RUNTIME.contracts import load_artifact_contracts
from RUNTIME.output_gateway import validate_artifact_content
from VALIDATORS.broadcast_readable_v2 import (
    build_broadcast_readable_report_v2,
    validate_broadcast_readable_report_v2,
)
from VALIDATORS.io import load_json_object
from VALIDATORS.models import ValidationIssue

ROOT = Path(__file__).resolve().parents[1]
PILOT_ROOT = ROOT / "PROJECTS/PRJ-006"
PROFILE_PATH = ROOT / "CHANNELS/mystery_main/output_profiles/broadcast-readable-script/2.0.0.json"
REPORT_SCHEMA_PATH = ROOT / "STANDARD/schemas/broadcast_readable_report_2_1.schema.json"
FORBIDDEN_PREFIXES = (
    "SCN-",
    "SEG-",
    "UNIT-",
    "CHAR-",
    "PANEL-",
    "RSEG-",
    "FACT-",
    "CLUE-",
    "HARM-",
    "CDEV-",
    "REVEAL-",
)


class PilotFixture(TypedDict):
    """v2 Report 생성에 필요한 PRJ-006 입력 묶음."""

    config: dict[str, object]
    screenplay_units: dict[str, object]
    characters: dict[str, object]
    relationships: dict[str, object]
    panel_cast: dict[str, object]
    reaction_segments: dict[str, object]
    presentation_plan: dict[str, object]
    final_script: str
    profile: dict[str, object]
    profile_file_sha256: str


def pilot_fixture() -> PilotFixture:
    """PRJ-006 Canonical 입력과 v2 활성 Config를 읽는다."""
    return {
        "config": {
            "$schema": ("../../../STANDARD/schemas/broadcast_readable_config.schema.json"),
            "schema_family": "broadcast-readable-config",
            "schema_version": "1.0.0",
            "project_id": "PRJ-006",
            "enabled": True,
            "profile_id": "BROADCAST_READABLE_SCRIPT",
            "profile_version": "2.0.0",
        },
        "screenplay_units": load_json_object(PILOT_ROOT / "07_SCRIPT/screenplay_units.json"),
        "characters": load_json_object(PILOT_ROOT / "02_CHARACTER/characters.json"),
        "relationships": load_json_object(PILOT_ROOT / "02_CHARACTER/relationships.json"),
        "panel_cast": load_json_object(PILOT_ROOT / "06_SCENE/panel_cast.json"),
        "reaction_segments": load_json_object(PILOT_ROOT / "06_SCENE/reaction_segments.json"),
        "presentation_plan": load_json_object(PILOT_ROOT / "06_SCENE/presentation_plan.json"),
        "final_script": (PILOT_ROOT / "07_SCRIPT/final_script.md").read_text(),
        "profile": load_json_object(PROFILE_PATH),
        "profile_file_sha256": sha256(PROFILE_PATH.read_bytes()).hexdigest(),
    }


def render_fixture(fixture: PilotFixture) -> str:
    """Fixture에서 v2 Expected Markdown을 렌더링한다."""
    return render_broadcast_readable_script_v2(
        fixture["screenplay_units"],
        fixture["characters"],
        fixture["relationships"],
        fixture["panel_cast"],
        fixture["reaction_segments"],
        fixture["presentation_plan"],
        fixture["profile"],
    )


def build_report(fixture: PilotFixture, actual_markdown: str) -> dict[str, object]:
    """Fixture와 Actual Markdown으로 v2 Report를 만든다."""
    return build_broadcast_readable_report_v2(
        fixture["config"],
        fixture["screenplay_units"],
        fixture["characters"],
        fixture["relationships"],
        fixture["panel_cast"],
        fixture["reaction_segments"],
        fixture["presentation_plan"],
        fixture["final_script"],
        fixture["profile"],
        fixture["profile_file_sha256"],
        actual_markdown,
    )


def validate_report(
    report: dict[str, object],
    fixture: PilotFixture,
    actual_markdown: str,
) -> list[ValidationIssue]:
    """저장 Report를 Fixture와 Actual Markdown에 대조한다."""
    return validate_broadcast_readable_report_v2(
        report,
        fixture["config"],
        fixture["screenplay_units"],
        fixture["characters"],
        fixture["relationships"],
        fixture["panel_cast"],
        fixture["reaction_segments"],
        fixture["presentation_plan"],
        fixture["final_script"],
        fixture["profile"],
        fixture["profile_file_sha256"],
        actual_markdown,
    )


def mapping_records(
    report: dict[str, object],
    field: str,
) -> list[dict[str, object]]:
    """Report Mapping 배열을 수정 없는 사전 목록으로 좁힌다."""
    raw_records = report[field]
    assert isinstance(raw_records, list)
    assert all(isinstance(record, dict) for record in raw_records)
    return [record for record in raw_records if isinstance(record, dict)]


def byte_fragment(actual_markdown: str, mapping: dict[str, object]) -> str:
    """Mapping Byte Range가 가리키는 Actual Fragment를 반환한다."""
    raw_range = mapping["actual_byte_range"]
    assert isinstance(raw_range, dict)
    byte_start = raw_range["byte_start"]
    byte_end = raw_range["byte_end"]
    assert isinstance(byte_start, int)
    assert isinstance(byte_end, int)
    return actual_markdown.encode("utf-8")[byte_start:byte_end].decode("utf-8")


def replace_mapped_fragment(
    actual_markdown: str,
    mapping: dict[str, object],
    replacement: str,
) -> str:
    """Mapping이 지정한 한 발생만 Byte 기준으로 교체한다."""
    raw_range = mapping["actual_byte_range"]
    assert isinstance(raw_range, dict)
    byte_start = raw_range["byte_start"]
    byte_end = raw_range["byte_end"]
    assert isinstance(byte_start, int)
    assert isinstance(byte_end, int)
    encoded = actual_markdown.encode("utf-8")
    return encoded[:byte_start].decode("utf-8") + replacement + encoded[byte_end:].decode("utf-8")


def unique_mapping_pair(
    actual_markdown: str,
    mappings: list[dict[str, object]],
    group_field: str,
) -> tuple[dict[str, object], dict[str, object]]:
    """같은 Group에서 서로 다른 고유 Fragment Mapping 두 개를 고른다."""
    for first_index, first in enumerate(mappings):
        first_fragment = byte_fragment(actual_markdown, first)
        for second in mappings[first_index + 1 :]:
            second_fragment = byte_fragment(actual_markdown, second)
            if (
                first.get(group_field) == second.get(group_field)
                and first_fragment != second_fragment
                and actual_markdown.count(first_fragment) == 1
                and actual_markdown.count(second_fragment) == 1
            ):
                return first, second
    raise AssertionError(f"고유 Mapping Pair가 없습니다: group_field={group_field}")


def replace_once(value: str, old: str, new: str) -> str:
    """고유 Fragment 하나만 교체하며 Fixture 모호성을 거부한다."""
    assert value.count(old) == 1
    return value.replace(old, new, 1)


def swap_ordered_fragments(value: str, first: str, second: str) -> str:
    """서로 겹치지 않는 두 Fragment의 위치만 교환한다."""
    first_start = value.find(first)
    second_start = value.find(second)
    assert first_start >= 0
    assert second_start > first_start + len(first)
    middle = value[first_start + len(first) : second_start]
    return value[:first_start] + second + middle + first + value[second_start + len(second) :]


def issue_codes(report: dict[str, object]) -> set[str]:
    """Report Issue Code 집합을 반환한다."""
    raw_issues = report["issues"]
    assert isinstance(raw_issues, list)
    return {
        str(issue["code"]) for issue in raw_issues if isinstance(issue, dict) and "code" in issue
    }


def validation_issue_codes(issues: list[ValidationIssue]) -> set[str]:
    """독립 Validator Issue Code 집합을 반환한다."""
    return {str(issue["code"]) for issue in issues}


def mutable_records(document: dict[str, object], field: str) -> list[dict[str, object]]:
    """Fixture JSON의 객체 배열을 안전하게 반환한다."""
    raw_records = document[field]
    assert isinstance(raw_records, list)
    assert all(isinstance(record, dict) for record in raw_records)
    return [record for record in raw_records if isinstance(record, dict)]


def reset_start_times(segments: list[dict[str, object]]) -> None:
    """Presentation 재배치 뒤 시작 시간을 배열 순서에 맞춘다."""
    for index, segment in enumerate(segments):
        segment["start_sec"] = index * 100


def reentry_fixture() -> PilotFixture:
    """Scene 재진입이 두 번 발생하는 독립 Presentation Fixture를 만든다."""
    fixture = pilot_fixture()
    segments = mutable_records(fixture["presentation_plan"], "segments")
    by_id = {str(segment["segment_id"]): segment for segment in segments}
    front_ids = ["SEG-001", "SEG-004", "SEG-003", "SEG-002", "SEG-005"]
    reordered = [by_id[segment_id] for segment_id in front_ids]
    reordered.extend(segment for segment in segments if segment["segment_id"] not in front_ids)
    fixture["presentation_plan"]["segments"] = reordered
    reset_start_times(reordered)
    scenes = mutable_records(fixture["screenplay_units"], "scenes")
    scenes[0]["segment_ids"] = ["SEG-001", "SEG-003", "SEG-002"]
    return fixture


def test_v2_report_is_schema_valid_complete_and_issue_free() -> None:
    """정상 Actual은 모든 독립 Mapping과 결속 Hash를 갖춘 NEEDS_REVIEW다."""
    fixture = pilot_fixture()
    actual = render_fixture(fixture)
    report = build_report(fixture, actual)

    assert report["result"] == "NEEDS_REVIEW"
    assert report["issues"] == []
    validator = Draft202012Validator(load_json_object(REPORT_SCHEMA_PATH))
    assert list(validator.iter_errors(report)) == []
    expected_lengths = {
        "scene_mappings": 11,
        "segment_mappings": 23,
        "unit_mappings": 95,
        "relationship_mappings": 7,
        "panel_turn_mappings": 14,
    }
    for field, expected_length in expected_lengths.items():
        records = mapping_records(report, field)
        assert len(records) == expected_length
        if field != "relationship_mappings":
            assert all(byte_fragment(actual, record) for record in records)
    ownership_fields = {
        "owner_type",
        "owner_id",
        "container_type",
        "segment_id",
        "scene_id",
        "rendered_block_sha256",
        "actual_byte_range",
        "container_local_order",
        "global_presentation_order",
        "same_block_occurrence_index_within_owner_type_or_container",
    }
    for field in ("unit_mappings", "panel_turn_mappings"):
        records = mapping_records(report, field)
        assert all(ownership_fields <= set(record) for record in records)
        global_orders: list[int] = []
        for record in records:
            global_order = record["global_presentation_order"]
            assert isinstance(global_order, int)
            global_orders.append(global_order)
        assert global_orders == sorted(global_orders)
    assert validate_report(report, fixture, actual) == []


def test_current_report_uses_owner_bound_contract_version() -> None:
    """현재 CORE용 Report는 Owner-bound 2.1.0 계약을 선언한다."""
    fixture = pilot_fixture()
    report = build_report(fixture, render_fixture(fixture))

    assert report["schema_version"] == "2.1.0"
    assert report["mapping_contract_version"] == "OWNER_BOUND_1"


def test_current_report_passes_versioned_output_gateway() -> None:
    """현재 2.1 Report는 Artifact Contract에 등록된 Schema를 통과한다."""
    fixture = pilot_fixture()
    report = build_report(fixture, render_fixture(fixture))
    contract = load_artifact_contracts(ROOT)["broadcast_readable_report"]

    validate_artifact_content(
        ROOT,
        "test.current_report",
        "broadcast_readable_report",
        contract["media_type"],
        report,
        contract,
    )


def test_prj_006_historical_report_2_0_remains_read_only_compatible() -> None:
    """PRJ-006의 저장된 2.0 Report는 Byte 수정 없이 Legacy 검증을 통과한다."""
    fixture = pilot_fixture()
    report = load_json_object(PILOT_ROOT / "08_QA/broadcast_readable_report.json")
    actual = (PILOT_ROOT / "07_SCRIPT/broadcast_readable_script.md").read_text()
    contract = load_artifact_contracts(ROOT)["broadcast_readable_report"]

    assert report["schema_version"] == "2.0.0"
    validate_artifact_content(
        ROOT,
        "test.legacy_report",
        "broadcast_readable_report",
        contract["media_type"],
        report,
        contract,
    )
    assert validate_report(report, fixture, actual) == []


@pytest.mark.parametrize(
    ("mapping_field", "required_field"),
    [
        ("unit_mappings", "owner_type"),
        ("unit_mappings", "owner_id"),
        ("unit_mappings", "container_type"),
        ("panel_turn_mappings", "owner_type"),
        ("panel_turn_mappings", "owner_id"),
        ("panel_turn_mappings", "container_type"),
    ],
)
def test_current_report_schema_requires_owner_mapping_fields(
    mapping_field: str,
    required_field: str,
) -> None:
    """현재 Report Mapping에서 Owner 계약 필드를 누락하면 Schema가 거부한다."""
    fixture = pilot_fixture()
    report = build_report(fixture, render_fixture(fixture))
    first_mapping = mapping_records(report, mapping_field)[0]
    first_mapping.pop(required_field)
    validator = Draft202012Validator(load_json_object(REPORT_SCHEMA_PATH))

    assert list(validator.iter_errors(report))


def test_current_report_schema_requires_mapping_contract_version() -> None:
    """현재 Report에서 Mapping Contract Version을 누락하면 Schema가 거부한다."""
    fixture = pilot_fixture()
    report = build_report(fixture, render_fixture(fixture))
    report.pop("mapping_contract_version")
    validator = Draft202012Validator(load_json_object(REPORT_SCHEMA_PATH))

    assert list(validator.iter_errors(report))


def test_current_report_rejects_owner_id_mismatch_explicitly() -> None:
    """Owner ID와 Unit ID의 의미 불일치를 명시적 Issue로 거부한다."""
    fixture = pilot_fixture()
    actual = render_fixture(fixture)
    report = build_report(fixture, actual)
    first_mapping = mapping_records(report, "unit_mappings")[0]
    first_mapping["owner_id"] = "UNIT-999"

    assert "BROADCAST_READABLE_V2_OWNER_ID_MISMATCH" in validation_issue_codes(
        validate_report(report, fixture, actual)
    )


def test_current_report_container_order_restarts_for_each_segment() -> None:
    """Container Local Order는 각 Segment에서 1부터 연속한다."""
    fixture = pilot_fixture()
    report = build_report(fixture, render_fixture(fixture))
    mappings = [
        *mapping_records(report, "unit_mappings"),
        *mapping_records(report, "panel_turn_mappings"),
    ]
    orders_by_segment: dict[tuple[object, object], list[int]] = {}
    for mapping in mappings:
        raw_order = mapping["container_local_order"]
        assert isinstance(raw_order, int)
        key = (mapping["owner_type"], mapping["segment_id"])
        orders_by_segment.setdefault(key, []).append(raw_order)

    assert all(orders == list(range(1, len(orders) + 1)) for orders in orders_by_segment.values())


@pytest.mark.parametrize(
    ("mutation", "expected_code"),
    [
        ("owner_type", "BROADCAST_READABLE_V2_OWNER_TYPE_MISMATCH"),
        ("owner_id", "BROADCAST_READABLE_V2_OWNER_ID_MISMATCH"),
        ("container_type", "BROADCAST_READABLE_V2_CONTAINER_BINDING_MISMATCH"),
        ("segment_id", "BROADCAST_READABLE_V2_CONTAINER_BINDING_MISMATCH"),
        ("scene_id", "BROADCAST_READABLE_V2_SEGMENT_BINDING_MISMATCH"),
        ("block_hash", "BROADCAST_READABLE_V2_BLOCK_HASH_MISMATCH"),
        ("byte_range", "BROADCAST_READABLE_V2_BLOCK_HASH_MISMATCH"),
        ("global_order", "BROADCAST_READABLE_V2_GLOBAL_ORDER_MISMATCH"),
        ("container_order", "BROADCAST_READABLE_V2_CONTAINER_ORDER_MISMATCH"),
        ("occurrence_order", "BROADCAST_READABLE_V2_OCCURRENCE_ORDER_MISMATCH"),
        ("duplicate_range", "BROADCAST_READABLE_V2_DUPLICATE_BYTE_RANGE"),
    ],
)
def test_current_report_owner_mapping_mutations_fail(
    mutation: str,
    expected_code: str,
) -> None:
    """2.1 Owner·Container·Hash·순서·Range 변조를 독립 의미 Issue로 거부한다."""
    fixture = pilot_fixture()
    actual = render_fixture(fixture)
    report = build_report(fixture, actual)
    mappings = mapping_records(report, "unit_mappings")
    first = mappings[0]
    if mutation == "owner_type":
        first["owner_type"] = "PANEL_TURN"
    elif mutation == "owner_id":
        first["owner_id"] = "UNIT-999"
    elif mutation == "container_type":
        first["container_type"] = "NARRATION"
    elif mutation == "segment_id":
        first["segment_id"] = "SEG-999"
    elif mutation == "scene_id":
        first["scene_id"] = "SCN-999"
    elif mutation == "block_hash":
        first["rendered_block_sha256"] = "0" * 64
    elif mutation == "byte_range":
        byte_range = first["actual_byte_range"]
        assert isinstance(byte_range, dict)
        byte_start = byte_range["byte_start"]
        assert isinstance(byte_start, int)
        byte_range["byte_start"] = byte_start + 1
    elif mutation == "global_order":
        first["global_presentation_order"] = mappings[1]["global_presentation_order"]
    elif mutation == "container_order":
        first["container_local_order"] = 0
    elif mutation == "occurrence_order":
        first["same_block_occurrence_index_within_owner_type_or_container"] = 2
    elif mutation == "duplicate_range":
        mappings[1]["actual_byte_range"] = deepcopy(first["actual_byte_range"])
    else:
        raise AssertionError(f"알 수 없는 Owner Mapping Mutation입니다: {mutation}")

    assert expected_code in validation_issue_codes(validate_report(report, fixture, actual))


def test_current_report_simple_legacy_version_downgrade_fails() -> None:
    """현재 2.1 Report의 Version만 2.0으로 낮춰 Legacy로 위장할 수 없다."""
    fixture = pilot_fixture()
    actual = render_fixture(fixture)
    report = build_report(fixture, actual)
    report["schema_version"] = "2.0.0"
    report["$schema"] = "../../../STANDARD/schemas/broadcast_readable_report_2_0.schema.json"
    legacy_schema = load_json_object(
        ROOT / "STANDARD/schemas/broadcast_readable_report_2_0.schema.json"
    )

    assert list(Draft202012Validator(legacy_schema).iter_errors(report))
    assert "BROADCAST_READABLE_V2_REPORT_STALE" in validation_issue_codes(
        validate_report(report, fixture, actual)
    )


@pytest.mark.parametrize(
    ("old", "new", "expected_code"),
    [
        (
            "| 한서윤 | 사망 피해자의 동생이자 기록 보존사 |",
            "| 한서연 | 사망 피해자의 동생이자 기록 보존사 |",
            "BROADCAST_READABLE_V2_RELATIONSHIP_ROW_MISMATCH",
        ),
        (
            "같은 야간 근무를 맡던 동료",
            "같은 야간 근무를 맡았던 동료",
            "BROADCAST_READABLE_V2_RELATIONSHIP_ROW_MISMATCH",
        ),
    ],
)
def test_character_or_relationship_text_mutation_fails(
    old: str,
    new: str,
    expected_code: str,
) -> None:
    """인물명 또는 관계 요약 한 글자 변조를 Actual Table에서 탐지한다."""
    fixture = pilot_fixture()
    actual = render_fixture(fixture)
    if old == "같은 야간 근무를 맡던 동료":
        row = next(
            line for line in actual.splitlines() if line.startswith("| 정세린 |") and old in line
        )
        mutated = replace_once(actual, row, row.replace(old, new, 1))
    else:
        mutated = replace_once(actual, old, new)

    assert expected_code in issue_codes(build_report(fixture, mutated))


def test_relationship_row_deletion_fails() -> None:
    """등장인물 관계 Row 하나의 완전 삭제를 탐지한다."""
    fixture = pilot_fixture()
    actual = render_fixture(fixture)
    row = next(line for line in actual.splitlines() if "같은 야간 근무를 맡던 동료" in line)
    mutated = replace_once(actual, f"{row}\n", "")

    assert "BROADCAST_READABLE_V2_RELATIONSHIP_ROW_MISMATCH" in issue_codes(
        build_report(fixture, mutated)
    )


@pytest.mark.parametrize("context_prefix", ["*[상황 설명:", "*[음향·행동 설명:"])
def test_context_deletion_or_duplication_fails(context_prefix: str) -> None:
    """상황 설명 삭제와 음향·행동 설명 중복을 독립 발생 횟수로 탐지한다."""
    fixture = pilot_fixture()
    actual = render_fixture(fixture)
    context = next(line for line in actual.splitlines() if line.startswith(context_prefix))
    mutated = (
        replace_once(actual, f"{context}\n\n", "")
        if context_prefix == "*[상황 설명:"
        else replace_once(actual, context, f"{context}\n\n{context}")
    )

    assert "BROADCAST_READABLE_V2_CONTEXT_OCCURRENCE_MISMATCH" in issue_codes(
        build_report(fixture, mutated)
    )


@pytest.mark.parametrize("mutation", ["character", "omit", "duplicate", "order"])
def test_unit_mutations_fail(mutation: str) -> None:
    """Unit 문자·누락·중복·순서 변이를 각각 탐지한다."""
    fixture = pilot_fixture()
    actual = render_fixture(fixture)
    baseline = build_report(fixture, actual)
    unit_mappings = mapping_records(baseline, "unit_mappings")
    first_mapping, second_mapping = unique_mapping_pair(
        actual,
        unit_mappings,
        "segment_id",
    )
    first = byte_fragment(actual, first_mapping)
    second = byte_fragment(actual, second_mapping)
    if mutation == "character":
        mutated = replace_mapped_fragment(actual, first_mapping, f"{first[:-1]}X")
    elif mutation == "omit":
        mutated = replace_mapped_fragment(actual, first_mapping, "")
    elif mutation == "duplicate":
        mutated = replace_mapped_fragment(
            actual,
            first_mapping,
            f"{first}\n\n{first}",
        )
    else:
        mutated = swap_ordered_fragments(actual, first, second)

    codes = issue_codes(build_report(fixture, mutated))
    assert "BROADCAST_READABLE_V2_RECONSTRUCTION_MISMATCH" in codes
    assert (
        "BROADCAST_READABLE_V2_UNIT_ORDER_MISMATCH" in codes
        if mutation == "order"
        else "BROADCAST_READABLE_V2_UNIT_OCCURRENCE_MISMATCH" in codes
    )


@pytest.mark.parametrize(
    "mutation",
    ["character", "omit", "duplicate", "order", "panelist_identity"],
)
def test_panel_turn_mutations_fail(mutation: str) -> None:
    """Panel 원문·누락·중복·순서·화자 변이를 각각 탐지한다."""
    fixture = pilot_fixture()
    actual = render_fixture(fixture)
    baseline = build_report(fixture, actual)
    panel_mappings = mapping_records(baseline, "panel_turn_mappings")
    first_mapping, second_mapping = unique_mapping_pair(
        actual,
        panel_mappings,
        "reaction_segment_id",
    )
    first = byte_fragment(actual, first_mapping)
    second = byte_fragment(actual, second_mapping)
    if mutation == "character":
        mutated = replace_mapped_fragment(actual, first_mapping, f"{first[:-1]}X")
    elif mutation == "omit":
        mutated = replace_mapped_fragment(actual, first_mapping, "")
    elif mutation == "duplicate":
        mutated = replace_mapped_fragment(
            actual,
            first_mapping,
            f"{first}\n\n{first}",
        )
    elif mutation == "order":
        mutated = swap_ordered_fragments(actual, first, second)
    else:
        first_line = first.splitlines()[0]
        mutated = replace_mapped_fragment(
            actual,
            first_mapping,
            first.replace(first_line, "**잘못된 패널**", 1),
        )

    codes = issue_codes(build_report(fixture, mutated))
    assert "BROADCAST_READABLE_V2_RECONSTRUCTION_MISMATCH" in codes
    assert (
        "BROADCAST_READABLE_V2_PANEL_TURN_ORDER_MISMATCH" in codes
        if mutation == "order"
        else "BROADCAST_READABLE_V2_PANEL_TURN_OCCURRENCE_MISMATCH" in codes
    )


def test_global_segment_order_mutation_fails() -> None:
    """전역 Presentation Segment Source Block의 위치 교환을 탐지한다."""
    fixture = pilot_fixture()
    actual = render_fixture(fixture)
    baseline = build_report(fixture, actual)
    segments = mapping_records(baseline, "segment_mappings")
    first = byte_fragment(actual, segments[0])
    second = byte_fragment(actual, segments[1])
    mutated = swap_ordered_fragments(actual, first, second)

    assert "BROADCAST_READABLE_V2_GLOBAL_SEGMENT_ORDER_MISMATCH" in issue_codes(
        build_report(fixture, mutated)
    )


def test_scene_reentry_heading_reorder_fails() -> None:
    """Scene 재진입 Heading을 잘못된 Segment 경계로 옮기면 실패한다."""
    fixture = reentry_fixture()
    actual = render_fixture(fixture)
    heading = "### 장면 1 재개. 멈춘 폐장 음악"
    without_heading = replace_once(actual, f"{heading}\n\n", "")
    first_scene_heading = "## 장면 1. 멈춘 폐장 음악"
    mutated = replace_once(
        without_heading,
        first_scene_heading,
        f"{heading}\n\n{first_scene_heading}",
    )

    assert "BROADCAST_READABLE_V2_SCENE_REENTRY_POSITION_MISMATCH" in issue_codes(
        build_report(fixture, mutated)
    )


@pytest.mark.parametrize("mutation", ["before_first_segment", "duplicate"])
def test_retrospective_mutations_fail(mutation: str) -> None:
    """반전 후 의미의 조기 배치와 중복을 각각 탐지한다."""
    fixture = pilot_fixture()
    actual = render_fixture(fixture)
    retrospective = next(line for line in actual.splitlines() if line.startswith("*[반전 후 의미:"))
    if mutation == "duplicate":
        mutated = replace_once(
            actual,
            retrospective,
            f"{retrospective}\n\n{retrospective}",
        )
    else:
        baseline = build_report(fixture, actual)
        first_mapping, _second_mapping = unique_mapping_pair(
            actual,
            mapping_records(baseline, "unit_mappings"),
            "segment_id",
        )
        first_unit = byte_fragment(actual, first_mapping)
        without_retrospective = replace_once(actual, f"{retrospective}\n\n", "")
        mutated = replace_mapped_fragment(
            without_retrospective,
            first_mapping,
            f"{retrospective}\n\n{first_unit}",
        )

    codes = issue_codes(build_report(fixture, mutated))
    assert "BROADCAST_READABLE_V2_RETROSPECTIVE_OCCURRENCE_MISMATCH" in codes or (
        "BROADCAST_READABLE_V2_RETROSPECTIVE_POSITION_MISMATCH" in codes
    )


@pytest.mark.parametrize(
    "token",
    [*FORBIDDEN_PREFIXES, "<!--", "-->", "[청취 불명확]", "[화자 불명확]"],
)
def test_each_visibility_token_in_actual_fails(token: str) -> None:
    """모든 내부 ID·HTML·Original Fiction 불확실성 Token을 각각 탐지한다."""
    fixture = pilot_fixture()
    mutated = f"{render_fixture(fixture)}\n{token}TEST\n"

    assert "BROADCAST_READABLE_V2_VISIBILITY_FORBIDDEN" in issue_codes(
        build_report(fixture, mutated)
    )


def test_unsupported_segment_type_is_reported_without_fallback() -> None:
    """Source 계약이 없는 Segment를 삭제하거나 성공으로 대체하지 않는다."""
    fixture = pilot_fixture()
    segments = mutable_records(fixture["presentation_plan"], "segments")
    segments[0]["segment_type"] = "EXPERT_ANALYSIS"
    actual = render_fixture(pilot_fixture())

    report = build_report(fixture, actual)
    assert report["result"] == "FAIL"
    assert "BROADCAST_READABLE_UNSUPPORTED_SEGMENT_TYPE" in issue_codes(report)


def test_profile_content_mutation_invalidates_actual_and_saved_report() -> None:
    """Profile 내용 변경은 재구성 불일치와 저장 Report Stale을 함께 만든다."""
    fixture = pilot_fixture()
    actual = render_fixture(fixture)
    saved_report = build_report(fixture, actual)
    mutated_fixture = deepcopy(fixture)
    document_contract = mutated_fixture["profile"]["document_contract"]
    assert isinstance(document_contract, dict)
    labels = document_contract["context_labels"]
    assert isinstance(labels, dict)
    labels["location_description"] = "현장"

    codes = validation_issue_codes(validate_report(saved_report, mutated_fixture, actual))
    assert "BROADCAST_READABLE_V2_RECONSTRUCTION_MISMATCH" in codes
    assert "BROADCAST_READABLE_V2_REPORT_STALE" in codes


def test_config_version_mutation_fails_binding() -> None:
    """Config Profile Version Drift를 v2 Report 생성 전에 거부한다."""
    fixture = pilot_fixture()
    actual = render_fixture(fixture)
    report = build_report(fixture, actual)
    fixture["config"]["profile_version"] = "1.0.0"

    assert validation_issue_codes(validate_report(report, fixture, actual)) == {
        "BROADCAST_READABLE_V2_CONFIG_BINDING_INVALID"
    }


def test_final_script_drift_and_saved_report_mutation_fail_stale_check() -> None:
    """final_script Drift와 저장 Report 자체 변조를 각각 Stale로 탐지한다."""
    fixture = pilot_fixture()
    actual = render_fixture(fixture)
    report = build_report(fixture, actual)
    final_drift = deepcopy(fixture)
    final_drift["final_script"] += "\n변조"
    assert "BROADCAST_READABLE_V2_REPORT_STALE" in validation_issue_codes(
        validate_report(report, final_drift, actual)
    )

    stale_report = deepcopy(report)
    stale_report["project_id"] = "PRJ-999"
    assert "BROADCAST_READABLE_V2_REPORT_STALE" in validation_issue_codes(
        validate_report(stale_report, fixture, actual)
    )


@pytest.mark.parametrize(
    "mutation",
    ["offset", "occurrence", "membership", "container", "duplicate_range"],
)
def test_saved_report_mapping_mutations_fail_stale_check(mutation: str) -> None:
    """저장 Report의 Offset·발생 번호·Segment Membership 조작을 탐지한다."""
    fixture = pilot_fixture()
    actual = render_fixture(fixture)
    report = build_report(fixture, actual)
    mappings = mapping_records(report, "unit_mappings")
    first = mappings[0]
    if mutation == "offset":
        byte_range = first["actual_byte_range"]
        assert isinstance(byte_range, dict)
        byte_start = byte_range["byte_start"]
        assert isinstance(byte_start, int)
        byte_range["byte_start"] = byte_start + 1
    elif mutation == "occurrence":
        occurrence = first["exact_occurrence_index"]
        assert isinstance(occurrence, int)
        first["exact_occurrence_index"] = occurrence + 1
    elif mutation == "membership":
        first["segment_id"] = "SEG-999"
    elif mutation == "container":
        first["container_type"] = "NARRATION"
    elif mutation == "duplicate_range":
        second = mappings[1]
        second["actual_byte_range"] = deepcopy(first["actual_byte_range"])
    else:
        raise AssertionError(f"알 수 없는 Mapping Mutation입니다: {mutation}")

    codes = validation_issue_codes(validate_report(report, fixture, actual))
    assert "BROADCAST_READABLE_V2_REPORT_STALE" in codes
    if mutation == "duplicate_range":
        assert "BROADCAST_READABLE_V2_DUPLICATE_BYTE_RANGE" in codes
