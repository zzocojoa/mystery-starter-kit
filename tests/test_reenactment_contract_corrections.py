"""재연극 계약 독립 검토 결함의 하위 의미 불변식을 검증한다."""

from copy import deepcopy
from pathlib import Path

import pytest

from VALIDATORS.crime_harms import derived_harm_fields, structured_harm_issues
from VALIDATORS.io import load_json_object
from VALIDATORS.models import ValidationIssue
from VALIDATORS.schema_validation import collect_schema_errors
from VALIDATORS.screenplay_units import (
    validate_screenplay_unit_references,
    validate_screenplay_units,
)

ROOT = Path(__file__).resolve().parents[1]


def issue_codes(issues: list[ValidationIssue]) -> set[str]:
    """검증 Issue의 안정된 Code 집합을 반환한다."""
    return {issue["code"] for issue in issues}


def harm(
    harm_id: str,
    classification: str,
    timing: str,
    victim_ids: list[str],
) -> dict[str, object]:
    """구조화 피해 한 건을 만든다."""
    return {
        "harm_id": harm_id,
        "classification": classification,
        "timing": timing,
        "victim_ids": victim_ids,
        "summary": f"{harm_id}의 구체 피해 결과",
    }


def harm_event(
    core_action_type: str,
    primary_crime: str,
    related_crimes: list[str],
    harms: list[dict[str, object]],
    victim_ids: list[str],
) -> dict[str, object]:
    """현재 피해 SSOT와 호환 필드가 일치하는 사건을 만든다."""
    event: dict[str, object] = {
        "core_action_type": core_action_type,
        "primary_crime": primary_crime,
        "related_crimes": related_crimes,
        "victim_ids": victim_ids,
        "harms": harms,
    }
    event.update(derived_harm_fields(harms))
    return event


def harm_validation_codes(event: dict[str, object]) -> set[str]:
    """구조화 피해 Contract의 오류 Code를 반환한다."""
    victim_ids = event["victim_ids"]
    assert isinstance(victim_ids, list)
    return issue_codes(
        structured_harm_issues(
            event,
            "01_CASE/crime_event_contract.json",
            "victim_ids",
            {value for value in victim_ids if isinstance(value, str)},
            True,
        )
    )


def test_legacy_single_harm_contract_remains_valid() -> None:
    """고정 Version의 Legacy 단일 피해 계약은 harms[] 없이 유지된다."""
    event = {
        "core_action_type": "ASSAULT",
        "harm_ids": ["HARM-01"],
        "harm_classifications": ["BODILY_INJURY"],
        "victim_ids": ["CHAR-01"],
    }

    assert structured_harm_issues(
        event,
        "01_CASE/crime_event_contract.json",
        "victim_ids",
        {"CHAR-01"},
        False,
    ) == []


@pytest.mark.parametrize(
    "event",
    (
        harm_event(
            "ASSAULT",
            "ASSAULT",
            [],
            [
                harm("HARM-01", "BODILY_INJURY", "IMMEDIATE", ["CHAR-01"]),
                harm("HARM-02", "THREAT_OR_TRAUMA", "LASTING", ["CHAR-01"]),
            ],
            ["CHAR-01"],
        ),
        harm_event(
            "ASSAULT",
            "ASSAULT",
            ["CONFINEMENT"],
            [
                harm("HARM-01", "BODILY_INJURY", "IMMEDIATE", ["CHAR-01"]),
                harm("HARM-02", "LIBERTY_DEPRIVATION", "OUTCOME", ["CHAR-01"]),
            ],
            ["CHAR-01"],
        ),
        harm_event(
            "STALKING",
            "STALKING",
            ["ASSAULT"],
            [
                harm("HARM-01", "THREAT_OR_TRAUMA", "IMMEDIATE", ["CHAR-01"]),
                harm("HARM-02", "BODILY_INJURY", "LASTING", ["CHAR-01"]),
            ],
            ["CHAR-01"],
        ),
        harm_event(
            "CONFINEMENT",
            "DOMESTIC_VIOLENCE",
            ["CONFINEMENT"],
            [
                harm("HARM-01", "LIBERTY_DEPRIVATION", "COMPOUND", ["CHAR-01"])
            ],
            ["CHAR-01"],
        ),
        harm_event(
            "ASSAULT",
            "DATING_VIOLENCE",
            [],
            [
                harm("HARM-01", "BODILY_INJURY", "IMMEDIATE", ["CHAR-01"]),
                harm("HARM-02", "THREAT_OR_TRAUMA", "LASTING", ["CHAR-02"]),
            ],
            ["CHAR-01", "CHAR-02"],
        ),
    ),
)
def test_multi_harm_accepts_core_primary_related_and_compound_structures(
    event: dict[str, object],
) -> None:
    """Core·Primary·Related 정책과 복합 timing을 함께 적용한다."""
    assert harm_validation_codes(event) == set()


@pytest.mark.parametrize(
    ("event", "expected_code"),
    (
        (
            harm_event(
                "ASSAULT",
                "ASSAULT",
                [],
                [harm("HARM-01", "THREAT_OR_TRAUMA", "IMMEDIATE", ["CHAR-01"])],
                ["CHAR-01"],
            ),
            "HARM_CLASSIFICATION_ACTION_MISMATCH",
        ),
        (
            harm_event(
                "ASSAULT",
                "ASSAULT",
                [],
                [
                    harm("HARM-01", "BODILY_INJURY", "IMMEDIATE", ["CHAR-01"]),
                    harm("HARM-02", "FATALITY", "OUTCOME", ["CHAR-01"]),
                ],
                ["CHAR-01"],
            ),
            "HARM_CLASSIFICATION_ACTION_MISMATCH",
        ),
        (
            harm_event(
                "ASSAULT",
                "ASSAULT",
                [],
                [
                    harm("HARM-01", "BODILY_INJURY", "IMMEDIATE", ["CHAR-01"]),
                    harm("HARM-01", "THREAT_OR_TRAUMA", "LASTING", ["CHAR-01"]),
                ],
                ["CHAR-01"],
            ),
            "HARM_ID_DUPLICATED",
        ),
        (
            harm_event(
                "ASSAULT",
                "ASSAULT",
                [],
                [harm("HARM-01", "BODILY_INJURY", "IMMEDIATE", ["CHAR-99"])],
                ["CHAR-01"],
            ),
            "HARM_VICTIM_BINDING_INVALID",
        ),
        (
            harm_event(
                "ASSAULT",
                "ASSAULT",
                [],
                [harm("HARM-01", "BODILY_INJURY", "IMMEDIATE", ["CHAR-01"])],
                ["CHAR-01", "CHAR-02"],
            ),
            "HARM_VICTIM_COVERAGE_MISSING",
        ),
        (
            harm_event(
                "ASSAULT",
                "DOMESTIC_VIOLENCE",
                [],
                [
                    harm("HARM-01", "BODILY_INJURY", "IMMEDIATE", ["CHAR-01"]),
                    harm("HARM-02", "COMPOUND_HARM", "LASTING", ["CHAR-01"]),
                ],
                ["CHAR-01"],
            ),
            "HARM_COMPOUND_OUTCOME_INVALID",
        ),
    ),
)
def test_multi_harm_rejects_incompatible_or_unbound_structures(
    event: dict[str, object],
    expected_code: str,
) -> None:
    """직접 피해·추가 피해·ID·피해자·복합 결과 오류를 각각 차단한다."""
    assert expected_code in harm_validation_codes(event)


def test_multi_harm_rejects_derived_compatibility_field_mismatch() -> None:
    """Legacy 호환 필드는 harms[]와 정확히 같아야 한다."""
    event = harm_event(
        "ASSAULT",
        "ASSAULT",
        [],
        [harm("HARM-01", "BODILY_INJURY", "IMMEDIATE", ["CHAR-01"])],
        ["CHAR-01"],
    )
    event["immediate_harm"] = "임의로 바꾼 피해 요약"

    assert "HARM_COMPATIBILITY_FIELDS_MISMATCH" in harm_validation_codes(event)


def unit_references() -> dict[str, list[str]]:
    """모든 참조 Family를 가진 정상 Unit 참조를 반환한다."""
    return {
        "fact_ids": ["FACT-01"],
        "clue_ids": ["CLUE-01"],
        "crime_event_ids": ["EVENT-01"],
        "harm_ids": ["HARM-01"],
        "development_function_ids": ["CDEV-001"],
        "reveal_target_ids": ["REVEAL-TARGET-01"],
    }


def reference_document() -> dict[str, object]:
    """상위 Artifact 참조가 모두 유효한 Screenplay Unit 문서를 만든다."""
    return {
        "schema_version": "1.1.0",
        "scenes": [
            {
                "scene_id": "SCN-01",
                "order": 1,
                "segment_ids": ["SEG-001"],
                "context": {"previous_scene_id": None, "sound_cues": []},
                "units": [
                    {
                        "unit_id": "UNIT-001",
                        "order": 1,
                        "type": "DIALOGUE",
                        "text": "현재 증거를 확인한다.",
                        "segment_id": "SEG-001",
                        "speaker_id": "CHAR-01",
                        "delivery": {"instruction": "낮고 분명하게"},
                        "references": unit_references(),
                    }
                ],
            }
        ],
    }


def reference_inputs() -> tuple[dict[str, object], ...]:
    """Screenplay 참조 검증용 상위 Artifact 묶음을 반환한다."""
    return (
        {"facts": [{"fact_id": "FACT-01"}]},
        {"clues": [{"clue_id": "CLUE-01"}]},
        {
            "event_id": "EVENT-01",
            "harm_ids": ["HARM-01"],
            "harms": [{"harm_id": "HARM-01"}],
            "development_functions": [
                {"development_function_id": "CDEV-001"}
            ],
            "reveal_targets": [{"reveal_target_id": "REVEAL-TARGET-01"}],
        },
        {"characters": [{"character_id": "CHAR-01"}]},
        {"segments": [{"segment_id": "SEG-001", "scene_id": "SCN-01"}]},
    )


def reference_issue_codes(document: dict[str, object]) -> set[str]:
    """현재 상위 Artifact에 대한 Screenplay 참조 오류 Code를 반환한다."""
    facts, clues, event, characters, presentation = reference_inputs()
    return issue_codes(
        validate_screenplay_unit_references(
            document,
            facts,
            clues,
            event,
            characters,
            presentation,
        )
    )


def first_unit(document: dict[str, object]) -> dict[str, object]:
    """단일 Unit Fixture의 Unit 객체를 반환한다."""
    scenes = document["scenes"]
    assert isinstance(scenes, list)
    scene = scenes[0]
    assert isinstance(scene, dict)
    units = scene["units"]
    assert isinstance(units, list)
    unit = units[0]
    assert isinstance(unit, dict)
    return unit


def test_every_screenplay_reference_resolves_to_current_upstream_artifact() -> None:
    """정상 Unit의 모든 참조와 화자·Segment 소유권이 현재 입력에 결속된다."""
    assert reference_issue_codes(reference_document()) == set()


@pytest.mark.parametrize(
    ("field", "expected_code"),
    (
        ("fact_ids", "SCREENPLAY_FACT_REFERENCE_UNKNOWN"),
        ("clue_ids", "SCREENPLAY_CLUE_REFERENCE_UNKNOWN"),
        ("crime_event_ids", "SCREENPLAY_EVENT_REFERENCE_UNKNOWN"),
        ("harm_ids", "SCREENPLAY_HARM_REFERENCE_UNKNOWN"),
        (
            "development_function_ids",
            "SCREENPLAY_DEVELOPMENT_FUNCTION_REFERENCE_UNKNOWN",
        ),
        ("reveal_target_ids", "SCREENPLAY_REVEAL_TARGET_REFERENCE_UNKNOWN"),
    ),
)
def test_each_screenplay_reference_family_rejects_unknown_id(
    field: str,
    expected_code: str,
) -> None:
    """참조 Family별 알 수 없는 ID가 독립적으로 실패한다."""
    document = reference_document()
    unit = first_unit(document)
    references = unit["references"]
    assert isinstance(references, dict)
    references[field] = ["UNKNOWN-99"]

    assert expected_code in reference_issue_codes(document)


def test_screenplay_reference_rejects_unknown_speaker_and_segment_owner() -> None:
    """화자와 Presentation Segment의 Scene 소유권도 상위 입력에 결속한다."""
    document = reference_document()
    unit = first_unit(document)
    unit["speaker_id"] = "CHAR-99"
    unit["segment_id"] = "SEG-999"

    assert {
        "REENACTMENT_SPEAKER_UNKNOWN",
        "SCREENPLAY_SEGMENT_REFERENCE_INVALID",
    }.issubset(reference_issue_codes(document))


def test_screenplay_harm_reference_requires_same_event_reference() -> None:
    """Harm ID만 숨은 Trace로 남기고 Event 결속을 생략할 수 없다."""
    document = reference_document()
    unit = first_unit(document)
    references = unit["references"]
    assert isinstance(references, dict)
    references["crime_event_ids"] = []

    assert "SCREENPLAY_HARM_EVENT_BINDING_INVALID" in reference_issue_codes(document)


def reconstruction_document() -> dict[str, object]:
    """가시 정체성과 참조를 보존한 재구성 Fixture를 만든다."""
    source_unit = {
        "unit_id": "UNIT-001",
        "order": 1,
        "type": "DIALOGUE",
        "text": "문이 안에서 닫힌 게 아니에요.",
        "segment_id": "SEG-001",
        "speaker_id": "CHAR-01",
        "delivery": {"instruction": "숨을 고르고 낮게"},
        "references": unit_references(),
    }
    repeated_unit = deepcopy(source_unit)
    repeated_unit["unit_id"] = "UNIT-002"
    repeated_unit["segment_id"] = "SEG-002"
    return {
        "schema_family": "screenplay-units",
        "schema_version": "1.1.0",
        "project_id": "PRJ-006",
        "title": "재구성 계약",
        "source_truth_classification": "ORIGINAL_FICTION",
        "scenes": [
            {
                "scene_id": "SCN-01",
                "order": 1,
                "title": "원본",
                "time_layer": "COLD_OPEN",
                "location_id": "LOC-01",
                "segment_ids": ["SEG-001"],
                "context": {"previous_scene_id": None, "sound_cues": []},
                "units": [source_unit],
            },
            {
                "scene_id": "SCN-02",
                "order": 2,
                "title": "재구성",
                "time_layer": "RECONSTRUCTION",
                "location_id": "LOC-01",
                "segment_ids": ["SEG-002"],
                "reconstruction_of_scene_id": "SCN-01",
                "reconstruction_bindings": [
                    {
                        "source_unit_id": "UNIT-001",
                        "repeated_unit_id": "UNIT-002",
                        "preservation": "EXACT_VISIBLE_IDENTITY",
                        "reference_policy": "PRESERVE_REFERENCES",
                    }
                ],
                "context": {"previous_scene_id": "SCN-01", "sound_cues": []},
                "units": [repeated_unit],
            },
        ],
    }


def repeated_unit(document: dict[str, object]) -> dict[str, object]:
    """재구성 Fixture의 반복 Unit을 반환한다."""
    scenes = document["scenes"]
    assert isinstance(scenes, list)
    scene = scenes[1]
    assert isinstance(scene, dict)
    units = scene["units"]
    assert isinstance(units, list)
    unit = units[0]
    assert isinstance(unit, dict)
    return unit


def reconstruction_bindings(document: dict[str, object]) -> list[dict[str, object]]:
    """재구성 Fixture의 Binding 배열을 반환한다."""
    scenes = document["scenes"]
    assert isinstance(scenes, list)
    scene = scenes[1]
    assert isinstance(scene, dict)
    bindings = scene["reconstruction_bindings"]
    assert isinstance(bindings, list)
    assert all(isinstance(binding, dict) for binding in bindings)
    return bindings


def test_reconstruction_exact_visible_identity_passes() -> None:
    """동일 text·type·speaker·delivery와 참조는 재구성 계약을 통과한다."""
    document = reconstruction_document()

    assert validate_screenplay_units(document) == []


@pytest.mark.parametrize("field", ("text", "type", "speaker_id", "delivery"))
def test_reconstruction_visible_identity_mutation_fails(field: str) -> None:
    """가시 정체성 구성요소 하나라도 바뀌면 재구성 결속이 실패한다."""
    document = reconstruction_document()
    unit = repeated_unit(document)
    replacements: dict[str, object] = {
        "text": "다른 문장",
        "type": "NARRATION",
        "speaker_id": "CHAR-02",
        "delivery": {"instruction": "빠르고 크게"},
    }
    unit[field] = replacements[field]

    assert "RECONSTRUCTION_REPETITION_MISMATCH" in issue_codes(
        validate_screenplay_units(document)
    )


def test_reconstruction_reference_change_requires_explicit_policy() -> None:
    """재맥락화 참조 변경은 명시 정책 없이는 실패하고 정책이 있으면 통과한다."""
    document = reconstruction_document()
    unit = repeated_unit(document)
    references = unit["references"]
    assert isinstance(references, dict)
    references["clue_ids"] = ["CLUE-02"]

    assert "RECONSTRUCTION_REPETITION_MISMATCH" in issue_codes(
        validate_screenplay_units(document)
    )

    bindings = reconstruction_bindings(document)
    bindings[0]["reference_policy"] = "ALLOW_RECONTEXTUALIZATION"
    assert validate_screenplay_units(document) == []


def test_reconstruction_schema_preserves_legacy_and_explicit_binding_forms() -> None:
    """기존 EXACT_TEXT와 새 가시 정체성·참조 정책 형식을 함께 허용한다."""
    root_schema = load_json_object(ROOT / "STANDARD/schemas/screenplay_units.schema.json")
    definitions = root_schema.get("$defs")
    assert isinstance(definitions, dict)
    schema = {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$ref": "#/$defs/reconstructionBinding",
        "$defs": definitions,
    }
    document = reconstruction_document()
    bindings = reconstruction_bindings(document)
    assert collect_schema_errors(
        bindings[0],
        schema,
        "explicit reconstruction",
    ) == []

    bindings[0]["preservation"] = "EXACT_TEXT"
    bindings[0].pop("reference_policy")
    assert collect_schema_errors(bindings[0], schema, "legacy reconstruction") == []


def relationship_schema() -> dict[str, object]:
    """Versioned Relationship 계약을 반환한다."""
    return load_json_object(ROOT / "STANDARD/schemas/relationships.schema.json")


def relationship_document(include_display_summary: bool) -> dict[str, object]:
    """Machine Engine과 선택적 관객용 설명을 가진 관계 문서를 만든다."""
    relationship: dict[str, object] = {
        "relationship_id": "REL-01",
        "from": "CHAR-01",
        "to": "CHAR-02",
        "engine": "TRUST_TO_RESPONSIBILITY",
    }
    if include_display_summary:
        relationship["display_summary"] = "서로를 믿었지만 책임을 두고 갈라진 동료"
    document: dict[str, object] = {
        "project_id": "PRJ-006",
        "relationships": [relationship],
    }
    if include_display_summary:
        document.update(
            {
                "schema_family": "relationships",
                "schema_version": "1.1.0",
            }
        )
    return document


def test_relationship_contract_accepts_display_summary_and_legacy_record() -> None:
    """표시 설명은 Machine Engine을 대체하지 않으며 Legacy 문서도 유지한다."""
    schema = relationship_schema()

    assert collect_schema_errors(
        relationship_document(True),
        schema,
        "relationship with display summary",
    ) == []
    assert collect_schema_errors(
        relationship_document(False),
        schema,
        "legacy relationship",
    ) == []

    versioned_without_display = relationship_document(False)
    versioned_without_display.update(
        {"schema_family": "relationships", "schema_version": "1.1.0"}
    )
    assert collect_schema_errors(
        versioned_without_display,
        schema,
        "versioned relationship without display summary",
    )


def test_stacked_pull_request_ci_is_not_restricted_to_main_base() -> None:
    """Stacked PR Base도 동일 CI Workflow를 실행할 수 있어야 한다."""
    workflow = (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")

    assert "pull_request:\n    branches:" not in workflow
