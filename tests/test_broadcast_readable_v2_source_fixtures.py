"""추상 기능군 R1·R2의 독립 Original Fiction Fixture를 검증한다."""

import json
from collections.abc import Mapping
from copy import deepcopy
from hashlib import sha256
from pathlib import Path
from typing import TypedDict, cast

import pytest
from jsonschema import Draft202012Validator
from test_broadcast_readable_v2_validation import (
    PilotFixture,
    build_report,
    byte_fragment,
    issue_codes,
    mapping_records,
    render_fixture,
    replace_mapped_fragment,
    replace_once,
)

from RUNTIME.contracts import load_artifact_contracts
from RUNTIME.core_tasks import approved_variation_output
from RUNTIME.output_gateway import validate_artifact_content
from RUNTIME.screenplay_renderers import (
    render_broadcast_master,
    render_drama_layer,
    render_narration_layer,
    render_panel_layer,
)
from VALIDATORS.candidate_approval import build_candidate_approval, validate_candidate_approval
from VALIDATORS.candidate_eligibility import build_candidate_eligibility_bound
from VALIDATORS.candidate_evaluation import (
    candidate_evaluation_input_hashes,
    validate_candidate_evaluation,
)
from VALIDATORS.candidate_event_briefs import (
    build_bound_crime_event_contract,
    canonical_json_hash,
)
from VALIDATORS.io import load_json_object
from VALIDATORS.novelty import evaluate_variation_precheck_bound
from VALIDATORS.variation_engines.common import candidate_signature
from VALIDATORS.variation_engines.v2_1_0 import derived_policy_profile

ROOT = Path(__file__).resolve().parents[1]
CANONICAL_BUNDLES_PATH = ROOT / "tests/fixtures/broadcast_readable_v2/canonical_source_bundles.json"
PROFILE_PATH = ROOT / "CHANNELS/mystery_main/output_profiles/broadcast-readable-script/2.0.0.json"
FORBIDDEN_VISIBLE_TOKENS = (
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
    "<!--",
    "-->",
    "[청취 불명확]",
    "[화자 불명확]",
)
INDEPENDENT_BUNDLE_DOCUMENTS = {
    "project_manifest",
    "production_config",
    "project_constraints",
    "config",
    "variation_candidates",
    "candidate_event_briefs",
    "candidate_evaluation",
    "candidate_approval",
    "story_dna",
    "case_input",
    "crime_event_contract",
    "facts",
    "characters",
    "relationships",
    "actual_timeline",
    "viewer_timeline",
    "clue_matrix",
    "scene_cards",
    "panel_cast",
    "reaction_segments",
    "presentation_plan",
    "screenplay_units",
}
RUNTIME_SCHEMA_DOCUMENTS = {
    "variation_candidates",
    "candidate_event_briefs",
    "candidate_evaluation",
    "candidate_approval",
    "story_dna",
    "case_input",
    "project_constraints",
    "crime_event_contract",
    "facts",
    "characters",
    "relationships",
    "knowledge_matrix",
    "actual_timeline",
    "viewer_timeline",
    "audience_belief",
    "clue_matrix",
    "hypothesis_ledger",
    "causal_graph",
    "beat_sheet",
    "retention_plan",
    "character_state_transitions",
    "scene_cards",
    "panel_cast",
    "reaction_segments",
    "presentation_plan",
    "screenplay_units",
}
PRJ_006_STORY_TOKENS = {
    "PRJ-006",
    "강태수",
    "오민재",
    "박도윤",
    "한지석",
    "정세린",
    "한서윤",
    "폐장 실내 수영장",
    "수영장 제어실",
}
FOREIGN_STORY_TOKENS = {
    "R1": {
        "7분의 공백",
        "작업자",
        "기계 로그",
        "센서 작동 상태",
        "점검 모드",
        "이동 기록",
    },
    "R2": {
        "7분의 공백",
        "작업자",
        "기계 로그",
        "센서 차단",
        "점검 모드",
        "자발적 이탈",
        "혼자 마감 근무",
        "폐점 직전 출입구",
    },
}


class SourceFixture(PilotFixture):
    """Gate 의미 검증까지 필요한 독립 Canonical 입력 묶음."""

    project_manifest: dict[str, object]
    production_config: dict[str, object]
    project_constraints: dict[str, object]
    variation_candidates: dict[str, object]
    candidate_event_briefs: dict[str, object]
    candidate_evaluation: dict[str, object]
    candidate_approval: dict[str, object]
    story_dna: dict[str, object]
    case_input: dict[str, object]
    crime_event_contract: dict[str, object]
    facts: dict[str, object]
    knowledge_matrix: dict[str, object]
    actual_timeline: dict[str, object]
    viewer_timeline: dict[str, object]
    audience_belief: dict[str, object]
    clue_matrix: dict[str, object]
    hypothesis_ledger: dict[str, object]
    causal_graph: dict[str, object]
    beat_sheet: dict[str, object]
    retention_plan: dict[str, object]
    character_state_transitions: dict[str, object]
    scene_cards: dict[str, object]


class FixtureMetadata(TypedDict):
    """Runtime Artifact와 분리된 Fixture 검증 Metadata."""

    source_classification: str
    allowed_story_tokens: list[str]
    required_story_tokens_by_artifact: dict[str, list[str]]
    forbidden_story_tokens_by_artifact: dict[str, list[str]]
    expected_artifact_sha256: dict[str, str]


class DimensionIssue(TypedDict):
    """승인 경로의 차원·결속 불일치를 나타내는 Test 전용 진단."""

    code: str
    artifact: str
    expected: object
    actual: object


def r1_dimension_targets() -> dict[str, str]:
    """Candidate나 Metadata에서 추론하지 않는 R1 사건의 고정 차원."""
    return {
        "protagonist_role": "VICTIM",
        "setting": "WORKPLACE",
        "relationship_context": "WORKPLACE",
    }


def dimension_value_issues(
    dimension: str,
    values: Mapping[str, object],
    expected: object,
) -> list[DimensionIssue]:
    """서로 독립된 구조 필드를 명시적 Expected와 비교한다."""
    return [
        {
            "code": f"FIXTURE_{dimension.upper()}_MISMATCH",
            "artifact": artifact,
            "expected": expected,
            "actual": actual,
        }
        for artifact, actual in values.items()
        if actual != expected
    ]


def fixture_dimension_coherence_issues(
    fixture: SourceFixture,
    expected_dimensions: Mapping[str, str],
) -> list[DimensionIssue]:
    """승인 Candidate만 따라 차원·인물·관계와 선택 Brief Hash를 교차 검증한다."""
    approval = fixture["candidate_approval"]
    selected_id = approval.get("selected_candidate_id")
    candidates = [
        record
        for record in mapping_list(fixture["variation_candidates"], "candidates")
        if record.get("candidate_id") == selected_id
    ]
    briefs = [
        record
        for record in mapping_list(fixture["candidate_event_briefs"], "briefs")
        if record.get("candidate_id") == selected_id
    ]
    evaluations = [
        record
        for record in mapping_list(fixture["candidate_evaluation"], "evaluations")
        if record.get("candidate_id") == selected_id
    ]
    cardinalities = (len(candidates), len(briefs), len(evaluations))
    if not isinstance(selected_id, str) or cardinalities != (1, 1, 1):
        return [
            {
                "code": "FIXTURE_SELECTED_PATH_MISMATCH",
                "artifact": "candidate_approval.selected_candidate_id",
                "expected": "고유 Candidate·Brief·Evaluation 하나",
                "actual": cardinalities,
            }
        ]
    selection = mapping_value(candidates[0], "selection")
    brief = briefs[0]
    dna = mapping_value(fixture["story_dna"], "story_dna")
    contract = fixture["crime_event_contract"]
    protagonist_id = contract.get("protagonist_id")
    protagonists = [
        character
        for character in mapping_list(fixture["characters"], "characters")
        if character.get("character_id") == protagonist_id
    ]
    protagonist = protagonists[0] if len(protagonists) == 1 else {}
    issues = dimension_value_issues(
        "selected_path",
        {
            "variation_candidates.approved_candidate_id": fixture["variation_candidates"].get(
                "approved_candidate_id"
            ),
            "candidate_evaluation.recommended_candidate_id": fixture["candidate_evaluation"].get(
                "recommended_candidate_id"
            ),
            "candidate_approval.recommended_candidate_id": approval.get("recommended_candidate_id"),
        },
        selected_id,
    )
    issues.extend(
        dimension_value_issues(
            "protagonist_role",
            {
                "selected_candidate.selection.protagonist_role": selection.get("protagonist_role"),
                "story_dna.story_dna.protagonist_role": dna.get("protagonist_role"),
                "characters.protagonist.role": protagonist.get("role"),
                "case_input.victim_ids": (
                    "VICTIM"
                    if protagonist_id in string_list(fixture["case_input"], "victim_ids")
                    else None
                ),
            },
            expected_dimensions["protagonist_role"],
        )
    )
    issues.extend(
        dimension_value_issues(
            "protagonist_role", {"crime_event_contract.protagonist_id": protagonist_id}, "CHAR-02"
        )
    )
    role_slots = protagonist.get("crime_role_slots")
    bindings = mapping_list(contract, "role_bindings")
    role_bound = (
        isinstance(role_slots, list)
        and {"VICTIM-01", "PROTAGONIST-01"} <= set(role_slots)
        and all(
            any(
                binding.get("role_slot") == slot
                and binding.get("character_id") == protagonist_id
                and binding.get("role_type") == role_type
                for binding in bindings
            )
            for slot, role_type in (("VICTIM-01", "VICTIM"), ("PROTAGONIST-01", "PROTAGONIST"))
        )
        and protagonist_id in string_list(contract, "victim_ids")
    )
    issues.extend(
        dimension_value_issues(
            "protagonist_role", {"crime_event_contract.role_bindings": role_bound}, True
        )
    )
    issues.extend(
        dimension_value_issues(
            "setting",
            {
                "selected_candidate.selection.setting": selection.get("setting"),
                "story_dna.story_dna.setting": dna.get("setting"),
                "case_input.setting": fixture["case_input"].get("setting"),
            },
            expected_dimensions["setting"],
        )
    )
    actor_ids = string_list(contract, "actor_ids")
    relationships = [
        relationship
        for relationship in mapping_list(fixture["relationships"], "relationships")
        if any(
            {relationship.get("from"), relationship.get("to")} == {actor_id, protagonist_id}
            for actor_id in actor_ids
        )
    ]
    relationship_values: dict[str, object] = {
        "selected_candidate.selection.relationship_context": selection.get("relationship_context"),
        "candidate_event_brief.relationship_context": brief.get("relationship_context"),
        "crime_event_contract.relationship_context": contract.get("relationship_context"),
    }
    if not relationships:
        relationship_values["relationships.offender_protagonist.engine"] = None
    for relationship in relationships:
        relationship_id = str(relationship["relationship_id"])
        relationship_values[f"relationships.{relationship_id}.engine"] = relationship.get("engine")
        summary = relationship.get("display_summary")
        workplace_summary = (
            isinstance(summary, str)
            and any(token in summary for token in ("업무", "동료", "근무"))
            and not any(token in summary for token in ("연인", "배우자", "연애"))
        )
        issues.extend(
            dimension_value_issues(
                "relationship_context",
                {f"relationships.{relationship_id}.display_summary": workplace_summary},
                True,
            )
        )
    issues.extend(
        dimension_value_issues(
            "relationship_context", relationship_values, expected_dimensions["relationship_context"]
        )
    )
    selection_hash = canonical_json_hash(selection)
    brief_hash = canonical_json_hash(brief)
    selected_hash_key = f"candidate_event_brief_{selected_id.lower().replace('-', '_')}"
    issues.extend(
        dimension_value_issues(
            "selected_path_hash",
            {
                "candidate_event_brief.candidate_selection_sha256": brief.get(
                    "candidate_selection_sha256"
                ),
                "crime_event_contract.candidate_selection_sha256": contract.get(
                    "candidate_selection_sha256"
                ),
            },
            selection_hash,
        )
    )
    issues.extend(
        dimension_value_issues(
            "selected_path_hash",
            {
                "crime_event_contract.candidate_event_brief_sha256": contract.get(
                    "candidate_event_brief_sha256"
                ),
                "candidate_evaluation.selected_brief_hash": mapping_value(
                    fixture["candidate_evaluation"], "input_hashes"
                ).get(selected_hash_key),
                "candidate_approval.selected_brief_hash": mapping_value(
                    approval, "input_hashes"
                ).get(selected_hash_key),
            },
            brief_hash,
        )
    )
    return issues


def mapping_value(document: Mapping[str, object], field: str) -> dict[str, object]:
    """Fixture 필수 객체 필드를 반환한다."""
    value = document[field]
    assert isinstance(value, dict)
    return value


def mapping_list(
    document: Mapping[str, object],
    field: str,
) -> list[dict[str, object]]:
    """Fixture 필수 객체 배열을 반환한다."""
    value = document[field]
    assert isinstance(value, list)
    assert all(isinstance(item, dict) for item in value)
    return [item for item in value if isinstance(item, dict)]


def string_list(document: Mapping[str, object], field: str) -> list[str]:
    """Fixture 필수 문자열 배열을 반환한다."""
    value = document[field]
    assert isinstance(value, list)
    assert all(isinstance(item, str) for item in value)
    return [item for item in value if isinstance(item, str)]


def mapping_byte_start(mapping: Mapping[str, object]) -> int:
    """Report Mapping의 Byte 시작 위치를 정수로 반환한다."""
    value = mapping_value(mapping, "actual_byte_range")["byte_start"]
    assert isinstance(value, int)
    return value


def fixture_record(fixture_id: str) -> dict[str, object]:
    """Versioned Bundle에서 요청한 Fixture 레코드를 반환한다."""
    document = load_json_object(CANONICAL_BUNDLES_PATH)
    matches = [
        fixture
        for fixture in mapping_list(document, "fixtures")
        if fixture.get("fixture_id") == fixture_id
    ]
    assert len(matches) == 1
    return matches[0]


def fixture_metadata(fixture_id: str) -> FixtureMetadata:
    """Artifact Namespace 밖의 Fixture 검증 Metadata를 반환한다."""
    record = fixture_record(fixture_id)
    raw_metadata = record.get("fixture_metadata")
    assert isinstance(raw_metadata, dict)
    return cast(FixtureMetadata, raw_metadata)


def render_fixture_machine_master(fixture: PilotFixture) -> str:
    """각 Fixture의 자체 Canonical Source에서 Machine Master를 생성한다."""
    source_fixture = cast(SourceFixture, fixture)
    drama_script = render_drama_layer(
        source_fixture["screenplay_units"],
        source_fixture["presentation_plan"],
        source_fixture["crime_event_contract"],
    )
    narration_script = render_narration_layer(
        source_fixture["screenplay_units"],
        source_fixture["presentation_plan"],
        source_fixture["crime_event_contract"],
    )
    panel_reaction_script = render_panel_layer(
        source_fixture["reaction_segments"],
        source_fixture["presentation_plan"],
    )
    return render_broadcast_master(
        source_fixture["presentation_plan"],
        {
            "drama_script": drama_script,
            "narration_script": narration_script,
            "panel_reaction_script": panel_reaction_script,
        },
    )


def apply_feature_fixture(fixture_id: str) -> SourceFixture:
    """독립 Versioned Canonical Bundle 하나를 읽고 파생 입력을 결속한다."""
    record = fixture_record(fixture_id)
    raw_artifacts = record["artifacts"]
    assert isinstance(raw_artifacts, dict)
    assert all(isinstance(value, dict) for value in raw_artifacts.values())
    artifacts = deepcopy(raw_artifacts)
    profile = load_json_object(PROFILE_PATH)
    fixture_values: dict[str, object] = {
        **artifacts,
        "profile": profile,
        "profile_file_sha256": sha256(PROFILE_PATH.read_bytes()).hexdigest(),
    }
    fixture = cast(SourceFixture, fixture_values)
    fixture["final_script"] = render_fixture_machine_master(fixture)
    return fixture


def artifact_ids(document: Mapping[str, object], field: str, id_field: str) -> set[str]:
    """Canonical Record 배열의 ID 집합을 반환한다."""
    return {
        str(record[id_field])
        for record in mapping_list(document, field)
        if isinstance(record.get(id_field), str)
    }


def assert_reference_subset(
    actual: object,
    expected: set[str],
    label: str,
) -> None:
    """참조 ID 배열이 자체 Fixture의 ID 집합 안인지 검증한다."""
    assert isinstance(actual, list), label
    assert all(isinstance(item, str) for item in actual), label
    assert set(actual) <= expected, label


def assert_fixture_reference_integrity(fixture: SourceFixture) -> None:
    """Screenplay와 Presentation 참조가 자체 Contract에만 결속됐는지 검사한다."""
    character_ids = artifact_ids(fixture["characters"], "characters", "character_id")
    fact_ids = artifact_ids(fixture["facts"], "facts", "fact_id")
    clue_ids = artifact_ids(fixture["clue_matrix"], "clues", "clue_id")
    scene_ids = artifact_ids(fixture["scene_cards"], "scenes", "scene_id")
    contract = fixture["crime_event_contract"]
    event_ids = {str(contract["event_id"])}
    harm_ids = set(string_list(contract, "harm_ids"))
    development_ids = artifact_ids(
        contract,
        "development_functions",
        "development_function_id",
    )
    reveal_ids = artifact_ids(contract, "reveal_targets", "reveal_target_id")
    characters = {
        str(character["character_id"]): str(character["name"])
        for character in mapping_list(fixture["characters"], "characters")
    }
    for relationship in mapping_list(fixture["relationships"], "relationships"):
        source_id = relationship["from"]
        target_id = relationship["to"]
        summary = relationship["display_summary"]
        assert isinstance(source_id, str)
        assert isinstance(target_id, str)
        assert isinstance(summary, str)
        assert {source_id, target_id} <= character_ids
        assert characters[source_id] in summary
        assert characters[target_id] in summary
    for scene in mapping_list(fixture["screenplay_units"], "scenes"):
        assert scene["scene_id"] in scene_ids
        for unit in mapping_list(scene, "units"):
            speaker_id = unit.get("speaker_id")
            if speaker_id is not None:
                assert speaker_id in character_ids
            references = mapping_value(unit, "references")
            assert_reference_subset(references["fact_ids"], fact_ids, "fact_ids")
            assert_reference_subset(references["clue_ids"], clue_ids, "clue_ids")
            assert_reference_subset(
                references["crime_event_ids"],
                event_ids,
                "crime_event_ids",
            )
            assert_reference_subset(references["harm_ids"], harm_ids, "harm_ids")
            assert_reference_subset(
                references["development_function_ids"],
                development_ids,
                "development_function_ids",
            )
            assert_reference_subset(
                references["reveal_target_ids"],
                reveal_ids,
                "reveal_target_ids",
            )


def assert_fixture_story_token_isolation(
    fixture: SourceFixture,
    fixture_id: str,
) -> None:
    """PRJ-006과 반대 Fixture의 고유 Story Token이 없는지 검증한다."""
    serialized = json.dumps(fixture, ensure_ascii=False, sort_keys=True)
    assert all(token not in serialized for token in PRJ_006_STORY_TOKENS)
    other_fixture_id = "R2" if fixture_id == "R1" else "R1"
    for token in fixture_metadata(other_fixture_id)["allowed_story_tokens"]:
        assert token not in serialized


def assert_fixture_token_contract(fixture: SourceFixture, fixture_id: str) -> None:
    """Artifact별 필수 Anchor와 외래 사건 Anchor 부재를 함께 검사한다."""
    metadata = fixture_metadata(fixture_id)
    fixture_documents: Mapping[str, object] = fixture
    for artifact_name, tokens in metadata["required_story_tokens_by_artifact"].items():
        serialized = json.dumps(
            fixture_documents[artifact_name],
            ensure_ascii=False,
            sort_keys=True,
        )
        assert all(token in serialized for token in tokens), artifact_name
    for artifact_name, tokens in metadata["forbidden_story_tokens_by_artifact"].items():
        serialized = json.dumps(
            fixture_documents[artifact_name],
            ensure_ascii=False,
            sort_keys=True,
        )
        assert all(token not in serialized for token in tokens), artifact_name


def assert_panel_reveal_scope(fixture: SourceFixture) -> None:
    """Panel Turn이 해당 Presentation 시점까지 공개된 Fact·Clue만 참조하는지 검사한다."""
    reactions = {
        str(reaction["reaction_segment_id"]): reaction
        for reaction in mapping_list(fixture["reaction_segments"], "reaction_segments")
    }
    revealed_fact_ids: set[str] = set()
    revealed_clue_ids: set[str] = set()
    segments = sorted(
        mapping_list(fixture["presentation_plan"], "segments"),
        key=lambda segment: float(cast(float | int, segment["start_sec"])),
    )
    for segment in segments:
        revealed_fact_ids.update(string_list(segment, "revealed_fact_ids"))
        revealed_clue_ids.update(string_list(segment, "revealed_clue_ids"))
        reaction_id = segment.get("reaction_segment_id")
        if not isinstance(reaction_id, str):
            continue
        reaction = reactions[reaction_id]
        for turn in mapping_list(reaction, "turns"):
            assert set(string_list(turn, "known_fact_ids")) <= revealed_fact_ids
            assert set(string_list(turn, "evidence_ids")) <= revealed_clue_ids


def assert_character_state_trigger_integrity(fixture: SourceFixture) -> None:
    """상태 전이 Trigger 참조와 같은 인물의 연속 상태를 검사한다."""
    character_ids = artifact_ids(fixture["characters"], "characters", "character_id")
    fact_ids = artifact_ids(fixture["facts"], "facts", "fact_id")
    clue_ids = artifact_ids(fixture["clue_matrix"], "clues", "clue_id")
    event_ids = {str(fixture["crime_event_contract"]["event_id"])}
    prior_state_by_character: dict[str, str] = {}
    transitions = sorted(
        mapping_list(fixture["character_state_transitions"], "transitions"),
        key=lambda transition: int(cast(int, transition["order"])),
    )
    for transition in transitions:
        character_id = transition["character_id"]
        state_before = transition["state_before"]
        state_after = transition["state_after"]
        assert isinstance(character_id, str)
        assert isinstance(state_before, str)
        assert isinstance(state_after, str)
        assert character_id in character_ids
        if character_id in prior_state_by_character:
            assert state_before == prior_state_by_character[character_id]
        prior_state_by_character[character_id] = state_after
        triggers = mapping_value(transition, "triggers")
        assert set(string_list(triggers, "fact_ids")) <= fact_ids
        assert set(string_list(triggers, "clue_ids")) <= clue_ids
        assert set(string_list(triggers, "crime_event_ids")) <= event_ids


def assert_crime_realization_coverage(fixture: SourceFixture) -> None:
    """Crime Contract의 Method·피해·기능이 Timeline·Scene·Unit에 실현됐는지 검사한다."""
    contract = fixture["crime_event_contract"]
    method = contract["non_actionable_method_summary"]
    immediate_harm = contract["immediate_harm"]
    lasting_harm = contract["lasting_harm"]
    assert isinstance(method, str)
    assert isinstance(immediate_harm, str)
    assert isinstance(lasting_harm, str)
    fact_statements = {str(fact["statement"]) for fact in mapping_list(fixture["facts"], "facts")}
    timeline_descriptions = {
        str(event["description"]) for event in mapping_list(fixture["actual_timeline"], "events")
    }
    realizations = [
        realization
        for scene in mapping_list(fixture["scene_cards"], "scenes")
        if "crime_realization" in scene
        for realization in mapping_list(scene, "crime_realization")
    ]
    screenplay_units = [
        unit
        for scene in mapping_list(fixture["screenplay_units"], "scenes")
        for unit in mapping_list(scene, "units")
    ]
    screenplay_text = "\n".join(str(unit["text"]) for unit in screenplay_units)
    assert method in fact_statements
    assert method in timeline_descriptions
    assert any(realization.get("action_evidence") == method for realization in realizations)
    assert method in screenplay_text
    assert immediate_harm in screenplay_text
    assert lasting_harm in screenplay_text
    development_ids = artifact_ids(
        contract,
        "development_functions",
        "development_function_id",
    )
    scene_development_ids = {
        development_id
        for realization in realizations
        for development_id in string_list(realization, "development_function_ids")
    }
    unit_development_ids = {
        development_id
        for unit in screenplay_units
        for development_id in string_list(
            mapping_value(unit, "references"),
            "development_function_ids",
        )
    }
    assert development_ids <= scene_development_ids
    assert development_ids <= unit_development_ids


def assert_fixture_semantic_consistency(
    fixture: SourceFixture,
    fixture_id: str,
) -> None:
    """작품 Anchor·공개 범위·상태·범죄 실현을 하나의 의미 계약으로 검사한다."""
    assert_fixture_reference_integrity(fixture)
    assert_fixture_story_token_isolation(fixture, fixture_id)
    assert_fixture_token_contract(fixture, fixture_id)
    assert_panel_reveal_scope(fixture)
    assert_character_state_trigger_integrity(fixture)
    assert_crime_realization_coverage(fixture)


def assert_fixture_source_style(fixture_id: str) -> None:
    """공통 Source-style 구조·원문·순서·가시성 불변식을 검증한다."""
    fixture = apply_feature_fixture(fixture_id)
    rendered = render_fixture(fixture)
    report = build_report(fixture, rendered)
    assert report["result"] == "NEEDS_REVIEW"
    assert report["issues"] == []
    assert "| 인물 | 역할 | 관계 |" in rendered
    rendered_lines = rendered.splitlines()
    for heading in ("정리 기준", "등장인물", "패널", "방송 대본"):
        assert rendered_lines.count(f"## {heading}") == 1
    for token in FORBIDDEN_VISIBLE_TOKENS:
        assert token not in rendered
    segment_mappings = mapping_records(report, "segment_mappings")
    segment_starts = [mapping_byte_start(mapping) for mapping in segment_mappings]
    assert segment_starts == sorted(segment_starts)
    for scene in mapping_list(fixture["screenplay_units"], "scenes"):
        for unit in mapping_list(scene, "units"):
            unit_text = unit["text"]
            assert isinstance(unit_text, str)
            assert unit_text in rendered
    for reaction in mapping_list(fixture["reaction_segments"], "reaction_segments"):
        for turn in mapping_list(reaction, "turns"):
            spoken_line = turn["spoken_line"]
            assert isinstance(spoken_line, str)
            assert spoken_line in rendered
    retrospective = report["retrospective_meaning_coverage"]
    assert isinstance(retrospective, dict)
    assert retrospective["mappings_complete"] is True
    assert fixture["final_script"] == render_fixture_machine_master(fixture)


@pytest.mark.parametrize("fixture_id", ["R1", "R2"])
def test_source_style_fixture_is_issue_free(fixture_id: str) -> None:
    """R1·R2는 Raw Reference 없이 독립 Original Fiction 문서를 만든다."""
    assert_fixture_source_style(fixture_id)


@pytest.mark.parametrize("fixture_id", ["R1", "R2"])
def test_source_style_fixture_is_a_complete_independent_bundle(
    fixture_id: str,
) -> None:
    """R1·R2가 PRJ-006 의미 Source 없이 자체 Canonical 문서를 소유한다."""
    fixture = apply_feature_fixture(fixture_id)
    assert set(fixture) >= INDEPENDENT_BUNDLE_DOCUMENTS
    assert_fixture_story_token_isolation(fixture, fixture_id)
    project_id = fixture["screenplay_units"]["project_id"]
    fixture_documents: Mapping[str, object] = fixture
    for document_name in INDEPENDENT_BUNDLE_DOCUMENTS:
        document = fixture_documents[document_name]
        assert isinstance(document, dict)
        if "project_id" in document:
            assert document["project_id"] == project_id
    assert_fixture_semantic_consistency(fixture, fixture_id)


@pytest.mark.parametrize("fixture_id", ["R1", "R2"])
def test_source_style_fixture_excludes_foreign_story_language(
    fixture_id: str,
) -> None:
    """각 Fixture의 전체 Runtime Artifact에 다른 사건 언어가 없다."""
    fixture = apply_feature_fixture(fixture_id)
    serialized = json.dumps(fixture, ensure_ascii=False, sort_keys=True)

    assert all(token not in serialized for token in FOREIGN_STORY_TOKENS[fixture_id])
    assert_fixture_token_contract(fixture, fixture_id)


@pytest.mark.parametrize("fixture_id", ["R1", "R2"])
def test_fixture_inventory_excludes_synthetic_truth_artifact(fixture_id: str) -> None:
    """Original Fiction Bundle은 가짜 Truth Contract를 Runtime Artifact로 두지 않는다."""
    record = fixture_record(fixture_id)
    artifacts = record["artifacts"]
    assert isinstance(artifacts, dict)

    assert "source_truth_contract" not in artifacts


@pytest.mark.parametrize("fixture_id", ["R1", "R2"])
def test_fixture_inventory_contains_gate_four_source_chain(fixture_id: str) -> None:
    """Fixture는 GATE-04 Contract을 결정하는 상위 사건 입력을 자체 소유한다."""
    record = fixture_record(fixture_id)
    artifacts = record["artifacts"]
    assert isinstance(artifacts, dict)
    required_sources = {
        "story_dna",
        "case_input",
        "facts",
        "variation_candidates",
        "candidate_event_briefs",
        "candidate_approval",
    }

    assert required_sources <= set(artifacts)


@pytest.mark.parametrize("fixture_id", ["R1", "R2"])
def test_fixture_metadata_hashes_match_canonical_artifacts(fixture_id: str) -> None:
    """Metadata의 Expected Hash는 같은 Bundle의 Canonical Artifact와 일치한다."""
    fixture = apply_feature_fixture(fixture_id)
    fixture_documents: Mapping[str, object] = fixture
    for artifact_name, expected_hash in fixture_metadata(fixture_id)[
        "expected_artifact_sha256"
    ].items():
        document = fixture_documents[artifact_name]
        assert isinstance(document, Mapping)
        assert canonical_json_hash(document) == expected_hash


@pytest.mark.parametrize("fixture_id", ["R1", "R2"])
def test_source_style_fixture_passes_composite_semantics(fixture_id: str) -> None:
    """R1·R2가 작품별 Composite Semantic Contract를 통과한다."""
    assert_fixture_semantic_consistency(apply_feature_fixture(fixture_id), fixture_id)


@pytest.mark.parametrize(
    ("dimension", "expected"),
    [
        ("protagonist_role", "VICTIM"),
        ("setting", "WORKPLACE"),
        ("relationship_context", "WORKPLACE"),
    ],
)
def test_r1_selected_candidate_dimensions_match_story(
    dimension: str,
    expected: str,
) -> None:
    """R1 승인 차원은 피해자 주인공과 업무 공간·전 동료 사건에 일치한다."""
    fixture = apply_feature_fixture("R1")
    selected_id = fixture["candidate_approval"]["selected_candidate_id"]
    selected = [
        candidate
        for candidate in mapping_list(fixture["variation_candidates"], "candidates")
        if candidate["candidate_id"] == selected_id
    ]

    assert len(selected) == 1
    assert mapping_value(selected[0], "selection")[dimension] == expected


def test_r1_selected_path_dimension_coherence() -> None:
    """R1 승인 경로의 차원·Hash·실제 인물 결속이 독립 목표와 일치한다."""
    fixture = apply_feature_fixture("R1")
    original = deepcopy(fixture)

    assert fixture_dimension_coherence_issues(fixture, r1_dimension_targets()) == []
    assert fixture == original
    assert fixture["candidate_approval"]["selected_candidate_id"] == "VAR-01"


def test_r1_derived_hashes_rebuild_with_normal_evaluation_and_approval() -> None:
    """기존 Builder로 전체 파생 결속을 재계산하며 점수·선택을 조작하지 않는다."""
    fixture = apply_feature_fixture("R1")
    variations = fixture["variation_candidates"]
    briefs = fixture["candidate_event_briefs"]
    candidate = mapping_list(variations, "candidates")[0]
    selection = cast(dict[str, str], mapping_value(candidate, "selection"))
    profile = derived_policy_profile(selection, "ORIGINAL_FICTION")
    assert candidate["policy_profile"] == profile
    assert candidate["signature"] == candidate_signature(selection, profile)
    novelty = evaluate_variation_precheck_bound(
        variations, briefs, [], load_json_object(ROOT / "STANDARD/novelty_thresholds.json")
    )
    eligibility = build_candidate_eligibility_bound(
        fixture["production_config"],
        fixture["project_constraints"],
        load_json_object(ROOT / "CHANNELS/mystery_main/versions/2.1.0/channel_dna.json"),
        variations,
        briefs,
        novelty,
    )
    evaluation = fixture["candidate_evaluation"]
    assert evaluation["input_hashes"] == candidate_evaluation_input_hashes(
        variations, briefs, novelty, eligibility
    )
    assert evaluation["novelty_report_hash"] == canonical_json_hash(novelty)
    assert validate_candidate_evaluation(variations, briefs, evaluation, novelty, eligibility) == []
    approved, selected_id = approved_variation_output(
        variations, briefs, evaluation, novelty, eligibility
    )
    assert selected_id == "VAR-01"
    assert approved == variations
    approval = fixture["candidate_approval"]
    rebuilt_approval = build_candidate_approval(
        str(approval["project_id"]),
        selected_id,
        str(evaluation["recommended_candidate_id"]),
        str(approval["actor"]),
        str(approval["reason"]),
        str(approval["approved_at"]),
        fixture["production_config"],
        variations,
        briefs,
        novelty,
        eligibility,
        evaluation,
        str(fixture["production_config"]["approval_policy"]),
        None,
    )
    assert rebuilt_approval == approval
    assert (
        validate_candidate_approval(
            fixture["production_config"],
            variations,
            briefs,
            novelty,
            eligibility,
            evaluation,
            approval,
        )
        == []
    )
    contract, issues = build_bound_crime_event_contract(
        str(approval["project_id"]),
        variations,
        briefs,
        fixture["case_input"],
        fixture["facts"],
        fixture["characters"],
        fixture["relationships"],
        {},
    )
    assert issues == []
    assert contract == fixture["crime_event_contract"]


def source_output_baseline_hashes(fixture_id: str) -> tuple[str, str]:
    """기준 e7bd177에서 실제 Renderer로 캡처한 불변 출력 Hash를 반환한다."""
    return {
        "R1": (
            "9c2f0f0c09bfe9505fc9a48404a56be2f6cfd47d2b47cae60148ea19fdd9a2ac",
            "f79b0bd9b54feaf5fecf34a5f30f3ff89dcfd9100c2d2d91cfebc999cbfd2c37",
        ),
        "R2": (
            "89a1a099c084f9c56e8416b57d387aa9efd4b6db1c238408bf3d254851636cc9",
            "7ebe714f4f7954932d05cf92d6caa7a446c049bf94f01b94ea3730959c9791eb",
        ),
    }[fixture_id]


@pytest.mark.parametrize("fixture_id", ["R1", "R2"])
def test_dimension_fix_preserves_baseline_script_bytes(fixture_id: str) -> None:
    """Metadata 보정이 Machine·Readable·예상 Production 사본을 바꾸지 않는다."""
    fixture = apply_feature_fixture(fixture_id)
    machine_hash, readable_hash = source_output_baseline_hashes(fixture_id)
    assert sha256(fixture["final_script"].encode("utf-8")).hexdigest() == machine_hash
    assert sha256(render_fixture(fixture).encode("utf-8")).hexdigest() == readable_hash


def test_dimension_fix_preserves_r2_complete_bundle() -> None:
    """R2 전체 레코드와 Metadata는 기준 Head 그대로 유지한다."""
    assert canonical_json_hash(fixture_record("R2")) == (
        "e8ec178264a53a29a27e911a63012d79a44bc7fa784d58e6a2e68b4f2d26c27e"
    )


@pytest.mark.parametrize(
    ("artifact_name", "baseline_hash"),
    [
        ("facts", "f7696506d237f236aec1cf2647ffaefa7a56b91c131d4511d76c069accbbaf6f"),
        ("characters", "407a1ef9681461b9f3f93a048fe250053acd64899d592c0344245de1954029a8"),
        ("actual_timeline", "653f0d2180dc9274393dec7fff3ab15fedf5e280fc1b90ebc801ba6fef59375b"),
        ("viewer_timeline", "bf50951bda2c89db87ad882d49053df5b3352003f3ac2780997bbf6d75ec1397"),
        ("clue_matrix", "2e7643e1677d9dfebb09ba55e0fbcfe0172d9149746b30613825bfc7481d6164"),
        ("scene_cards", "10a50b1aa28e5d83903d36ff1ed63a3f8a3b72e467ad9764e9347fc20eb6df82"),
        ("reaction_segments", "5e868671beae44f2189d2a4b68033b845bc0cefa595d60a3fc4599c5056ff1f3"),
        ("presentation_plan", "b116b49733059562fda821d4c5194beb323a7d93733800b22e34e037fd56059b"),
        ("screenplay_units", "68129fefd7aa6dd7ce48df322eaff76c76d42794b59dddd51ddff38503662245"),
    ],
)
def test_dimension_fix_preserves_r1_visible_artifacts(
    artifact_name: str,
    baseline_hash: str,
) -> None:
    """수정 가능한 Expected Metadata와 독립적으로 원본 Artifact Hash를 고정한다."""
    artifacts = mapping_value(fixture_record("R1"), "artifacts")
    assert canonical_json_hash(artifacts[artifact_name]) == baseline_hash


def test_r1_protagonist_role_mutation_fails() -> None:
    """MUT-01: Story DNA만 가족 역할로 바꾸면 실제 피해자 주인공과 충돌한다."""
    fixture = apply_feature_fixture("R1")
    assert fixture_dimension_coherence_issues(fixture, r1_dimension_targets()) == []
    mapping_value(fixture["story_dna"], "story_dna")["protagonist_role"] = "VICTIM_FAMILY"

    issues = fixture_dimension_coherence_issues(fixture, r1_dimension_targets())

    assert {issue["code"] for issue in issues} == {"FIXTURE_PROTAGONIST_ROLE_MISMATCH"}
    assert issues[0]["artifact"] == "story_dna.story_dna.protagonist_role"


def test_r1_setting_mutation_fails() -> None:
    """MUT-02: Case Input만 숙박시설로 바꾸면 업무 공간 분류와 충돌한다."""
    fixture = apply_feature_fixture("R1")
    assert fixture_dimension_coherence_issues(fixture, r1_dimension_targets()) == []
    fixture["case_input"]["setting"] = "LODGING"

    issues = fixture_dimension_coherence_issues(fixture, r1_dimension_targets())

    assert {issue["code"] for issue in issues} == {"FIXTURE_SETTING_MISMATCH"}
    assert issues[0]["artifact"] == "case_input.setting"


@pytest.mark.parametrize("artifact_name", ["crime_event_contract", "relationships"])
def test_r1_relationship_context_mutation_fails(artifact_name: str) -> None:
    """MUT-03: Contract 또는 실제 관계만 연인 관계로 바꾸면 독립 실패한다."""
    fixture = apply_feature_fixture("R1")
    assert fixture_dimension_coherence_issues(fixture, r1_dimension_targets()) == []
    if artifact_name == "crime_event_contract":
        fixture["crime_event_contract"]["relationship_context"] = "DATING_PARTNER"
    else:
        mapping_list(fixture["relationships"], "relationships")[0]["engine"] = "DATING_PARTNER"

    issues = fixture_dimension_coherence_issues(fixture, r1_dimension_targets())

    assert {issue["code"] for issue in issues} == {"FIXTURE_RELATIONSHIP_CONTEXT_MISMATCH"}


def test_r1_unselected_candidate_dimension_does_not_pollute_selected_path() -> None:
    """MUT-04: 비선택 후보의 차원은 승인 경로 차원 Oracle의 대상이 아니다."""
    fixture = apply_feature_fixture("R1")
    selected_id = fixture["candidate_approval"]["selected_candidate_id"]
    unselected = next(
        candidate
        for candidate in mapping_list(fixture["variation_candidates"], "candidates")
        if candidate["candidate_id"] != selected_id
    )
    mapping_value(unselected, "selection")["relationship_context"] = "DATING_PARTNER"

    assert fixture_dimension_coherence_issues(fixture, r1_dimension_targets()) == []


def test_r1_coupled_wrong_dimensions_cannot_replace_character_truth() -> None:
    """MUT-05: 잘못된 Candidate·Story·Expected끼리 같아도 실제 피해자 결속이 거부한다."""
    fixture = apply_feature_fixture("R1")
    selected_id = fixture["candidate_approval"]["selected_candidate_id"]
    candidate = next(
        candidate
        for candidate in mapping_list(fixture["variation_candidates"], "candidates")
        if candidate["candidate_id"] == selected_id
    )
    selection = mapping_value(candidate, "selection")
    selection["protagonist_role"] = "VICTIM_FAMILY"
    mapping_value(fixture["story_dna"], "story_dna")["protagonist_role"] = "VICTIM_FAMILY"
    brief = next(
        brief
        for brief in mapping_list(fixture["candidate_event_briefs"], "briefs")
        if brief["candidate_id"] == selected_id
    )
    brief["candidate_selection_sha256"] = canonical_json_hash(selection)
    fixture["crime_event_contract"]["candidate_selection_sha256"] = canonical_json_hash(selection)
    fixture["crime_event_contract"]["candidate_event_brief_sha256"] = canonical_json_hash(brief)
    for artifact_name in ("candidate_evaluation", "candidate_approval"):
        document = cast(Mapping[str, object], fixture)[artifact_name]
        assert isinstance(document, dict)
        mapping_value(document, "input_hashes")["candidate_event_brief_var_01"] = (
            canonical_json_hash(brief)
        )
    wrong_expected = {**r1_dimension_targets(), "protagonist_role": "VICTIM_FAMILY"}

    fixed_target_issues = fixture_dimension_coherence_issues(fixture, r1_dimension_targets())
    coupled_target_issues = fixture_dimension_coherence_issues(fixture, wrong_expected)

    assert "FIXTURE_PROTAGONIST_ROLE_MISMATCH" in {issue["code"] for issue in fixed_target_issues}
    assert {issue["code"] for issue in coupled_target_issues} == {
        "FIXTURE_PROTAGONIST_ROLE_MISMATCH"
    }
    assert "characters.protagonist.role" in {issue["artifact"] for issue in coupled_target_issues}


@pytest.mark.parametrize("document_name", ["variation_candidates", "candidate_event_briefs"])
def test_r1_duplicate_selected_candidate_path_fails(document_name: str) -> None:
    """승인 ID가 Candidate 또는 Brief에 중복되면 임의 첫 레코드를 선택하지 않는다."""
    fixture = apply_feature_fixture("R1")
    document = cast(Mapping[str, object], fixture)[document_name]
    assert isinstance(document, dict)
    field = "candidates" if document_name == "variation_candidates" else "briefs"
    records = document[field]
    assert isinstance(records, list)
    records.append(deepcopy(records[0]))

    assert {
        issue["code"]
        for issue in fixture_dimension_coherence_issues(fixture, r1_dimension_targets())
    } == {"FIXTURE_SELECTED_PATH_MISMATCH"}


@pytest.mark.parametrize("artifact_name", ["candidate_evaluation", "candidate_approval"])
def test_r1_selected_brief_hash_mutation_fails(artifact_name: str) -> None:
    """승인 경로의 평가·승인 기록은 동일한 선택 Brief Hash를 보유해야 한다."""
    fixture = apply_feature_fixture("R1")
    assert fixture_dimension_coherence_issues(fixture, r1_dimension_targets()) == []
    document = cast(Mapping[str, object], fixture)[artifact_name]
    assert isinstance(document, dict)
    mapping_value(document, "input_hashes")["candidate_event_brief_var_01"] = "0" * 64

    assert {
        issue["code"]
        for issue in fixture_dimension_coherence_issues(fixture, r1_dimension_targets())
    } == {"FIXTURE_SELECTED_PATH_HASH_MISMATCH"}


def test_prj_006_story_token_injection_fails_fixture_isolation() -> None:
    """PRJ-006 고유 인물명을 R1에 주입하면 독립성 검사가 실패한다."""
    fixture = apply_feature_fixture("R1")
    characters = mapping_list(fixture["characters"], "characters")
    characters[0]["name"] = sorted(PRJ_006_STORY_TOKENS)[0]

    with pytest.raises(AssertionError):
        assert_fixture_story_token_isolation(fixture, "R1")


@pytest.mark.parametrize(
    ("fixture_id", "foreign_anchor"),
    [("R1", "마지막 좌석"), ("R2", "세 번째 종료음")],
)
def test_foreign_story_anchor_injection_fails_fixture_contract(
    fixture_id: str,
    foreign_anchor: str,
) -> None:
    """반대 작품의 사건 Anchor를 관련 Artifact에 주입하면 계약 검사가 실패한다."""
    fixture = apply_feature_fixture(fixture_id)
    facts = mapping_list(fixture["facts"], "facts")
    facts[0]["statement"] = f"{facts[0]['statement']} {foreign_anchor}"

    with pytest.raises(AssertionError):
        assert_fixture_token_contract(fixture, fixture_id)


def test_cross_fixture_character_injection_fails_fixture_isolation() -> None:
    """다른 Fixture 인물명을 주입하면 Project Story 격리가 실패한다."""
    fixture = apply_feature_fixture("R2")
    characters = mapping_list(fixture["characters"], "characters")
    characters[0]["name"] = "서도훈"

    with pytest.raises(AssertionError):
        assert_fixture_story_token_isolation(fixture, "R2")


def test_unknown_clue_reference_fails_fixture_integrity() -> None:
    """자체 Clue Contract에 없는 Unit 참조는 독립 Bundle 검사를 실패시킨다."""
    fixture = apply_feature_fixture("R2")
    first_scene = mapping_list(fixture["screenplay_units"], "scenes")[0]
    first_unit = mapping_list(first_scene, "units")[0]
    references = mapping_value(first_unit, "references")
    clue_ids = references["clue_ids"]
    assert isinstance(clue_ids, list)
    clue_ids.append("CLUE-999")

    with pytest.raises(AssertionError, match="clue_ids"):
        assert_fixture_reference_integrity(fixture)


def test_panel_unrevealed_fact_reference_fails_fixture_semantics() -> None:
    """Panel이 해당 Segment까지 미공개 Fact를 말하면 의미 검사가 실패한다."""
    fixture = apply_feature_fixture("R2")
    reactions = mapping_list(fixture["reaction_segments"], "reaction_segments")
    result_first_turn = mapping_list(reactions[2], "turns")[0]
    result_first_turn["known_fact_ids"] = ["FACT-01", "FACT-02"]

    with pytest.raises(AssertionError):
        assert_panel_reveal_scope(fixture)


def test_cross_story_state_trigger_fails_fixture_semantics() -> None:
    """다른 사건의 Clue를 상태 전이 Trigger로 주입하면 의미 검사가 실패한다."""
    fixture = apply_feature_fixture("R1")
    transitions = mapping_list(fixture["character_state_transitions"], "transitions")
    triggers = mapping_value(transitions[1], "triggers")
    triggers["clue_ids"] = ["CLUE-902"]

    with pytest.raises(AssertionError):
        assert_character_state_trigger_integrity(fixture)


def test_disconnected_state_transition_fails_fixture_semantics() -> None:
    """같은 인물의 전후 상태가 끊기면 Composite 의미 검사가 실패한다."""
    fixture = apply_feature_fixture("R2")
    transitions = mapping_list(fixture["character_state_transitions"], "transitions")
    transitions[1]["state_before"] = "다른 사건의 상태"

    with pytest.raises(AssertionError):
        assert_character_state_trigger_integrity(fixture)


def test_unrealized_crime_method_fails_fixture_semantics() -> None:
    """Crime Contract Method가 Scene·Unit에 실현되지 않으면 의미 검사가 실패한다."""
    fixture = apply_feature_fixture("R1")
    fixture["crime_event_contract"]["non_actionable_method_summary"] = (
        "Fixture 어디에도 실현되지 않은 사건 방식"
    )

    with pytest.raises(AssertionError):
        assert_crime_realization_coverage(fixture)


@pytest.mark.parametrize("fixture_id", ["R1", "R2"])
def test_source_style_fixture_canonical_json_matches_runtime_schemas(
    fixture_id: str,
) -> None:
    """독립 Bundle의 Runtime Artifact를 각 정식 JSON Schema로 검증한다."""
    fixture = apply_feature_fixture(fixture_id)
    for artifact_name in ("project_manifest", "production_config"):
        schema = load_json_object(ROOT / f"STANDARD/schemas/{artifact_name}.schema.json")
        validator = Draft202012Validator(schema)
        assert list(validator.iter_errors(fixture[artifact_name])) == []
    contracts = load_artifact_contracts(ROOT)
    config_contract = contracts["broadcast_readable_config"]
    validate_artifact_content(
        ROOT,
        "fixture.schema_validation",
        "broadcast_readable_config",
        config_contract["media_type"],
        fixture["config"],
        config_contract,
    )
    fixture_documents: Mapping[str, object] = fixture
    for artifact_name in sorted(RUNTIME_SCHEMA_DOCUMENTS):
        contract = contracts[artifact_name]
        validate_artifact_content(
            ROOT,
            "fixture.schema_validation",
            artifact_name,
            contract["media_type"],
            fixture_documents[artifact_name],
            contract,
        )


def test_r1_reentry_note_signal_and_retrospective_positions() -> None:
    """R1의 Note·반복 신호·Scene 재진입·후행 재해석을 증명한다."""
    fixture = apply_feature_fixture("R1")
    rendered = render_fixture(fixture)
    report = build_report(fixture, rendered)
    assert "**김세라(쪽지)**" in rendered
    assert rendered.count("## 장면 1. 세 번째 종료음") == 1
    assert rendered.count("### 장면 1 재개. 세 번째 종료음") == 1
    assert "건조기 종료음이 두 번 일정하게 울린다." in rendered
    scene_mapping = mapping_records(report, "scene_mappings")[0]
    scene_fragment = byte_fragment(rendered, scene_mapping)
    assert scene_fragment.index("세 번째 종료음 수기 확인") < scene_fragment.index(
        "수동 재시작 신호로 다시 읽힌다"
    )


def test_r2_result_first_flashback_message_and_responsibility() -> None:
    """R2의 결과 선제시·회상·Message 위협·책임 진술을 증명한다."""
    fixture = apply_feature_fixture("R2")
    rendered = render_fixture(fixture)
    assert rendered.index("폭설 다음 날 오전, 결과 장면") < rendered.index(
        "결과 장면보다 열두 시간 전, 조사 인터뷰 직전"
    )
    assert "**문강석(메시지)**" in rendered
    assert "장부를 바꾸고 위협 메시지를 보낸 책임은 각자 말해야 합니다" in rendered
    assert "문강석과 차유진이 연수원 장부의 책임 진술" in rendered


def test_r1_context_and_retrospective_negative_mutations_fail() -> None:
    """R1의 시작 Sound Context 누락과 Scene-end 재해석 조기 배치를 탐지한다."""
    fixture = apply_feature_fixture("R1")
    rendered = render_fixture(fixture)
    sound_context = next(
        line for line in rendered.splitlines() if line.startswith("*[음향·행동 설명:")
    )
    missing_context = replace_once(rendered, f"{sound_context}\n\n", "")
    assert "BROADCAST_READABLE_V2_CONTEXT_OCCURRENCE_MISMATCH" in issue_codes(
        build_report(fixture, missing_context)
    )
    retrospective = next(line for line in rendered.splitlines() if "평범한 종료음의 반복" in line)
    first_mapping = mapping_records(build_report(fixture, rendered), "unit_mappings")[0]
    first_unit = byte_fragment(rendered, first_mapping)
    moved = replace_once(rendered, retrospective, "")
    moved = replace_mapped_fragment(
        moved,
        first_mapping,
        f"{retrospective}\n\n{first_unit}",
    )
    assert "BROADCAST_READABLE_V2_RETROSPECTIVE_POSITION_MISMATCH" in issue_codes(
        build_report(fixture, moved)
    )


def test_r2_relationship_panel_and_unsupported_negative_mutations_fail() -> None:
    """R2 관계 Row·Panel 원문 변조와 미지원 Segment를 각각 탐지한다."""
    fixture = apply_feature_fixture("R2")
    rendered = render_fixture(fixture)
    relationship_row = next(line for line in rendered.splitlines() if line.startswith("| 문강석 |"))
    relationship_mutation = replace_once(
        rendered,
        relationship_row,
        relationship_row.replace("책임 진술", "책임 회피", 1),
    )
    assert "BROADCAST_READABLE_V2_RELATIONSHIP_ROW_MISMATCH" in issue_codes(
        build_report(fixture, relationship_mutation)
    )
    panel_line = next(
        turn["spoken_line"]
        for reaction in mapping_list(fixture["reaction_segments"], "reaction_segments")
        for turn in mapping_list(reaction, "turns")
    )
    assert isinstance(panel_line, str)
    panel_mutation = replace_once(rendered, panel_line, f"{panel_line} 변조")
    assert "BROADCAST_READABLE_V2_PANEL_TURN_OCCURRENCE_MISMATCH" in issue_codes(
        build_report(fixture, panel_mutation)
    )
    unsupported = deepcopy(fixture)
    first_segment = mapping_list(unsupported["presentation_plan"], "segments")[0]
    first_segment["segment_type"] = "EXPERT_ANALYSIS"
    assert "BROADCAST_READABLE_UNSUPPORTED_SEGMENT_TYPE" in issue_codes(
        build_report(unsupported, rendered)
    )


def test_r1_r2_have_distinct_source_derived_machine_masters() -> None:
    """두 Fixture의 Machine Master는 각자의 Canonical Source에서 생성한다."""
    r1 = apply_feature_fixture("R1")
    r2 = apply_feature_fixture("R2")
    assert render_fixture(r1) != render_fixture(r2)
    original_hash = sha256(
        (ROOT / "PROJECTS/PRJ-006/07_SCRIPT/final_script.md").read_bytes()
    ).hexdigest()
    r1_hash = sha256(r1["final_script"].encode("utf-8")).hexdigest()
    r2_hash = sha256(r2["final_script"].encode("utf-8")).hexdigest()
    assert r1_hash != original_hash
    assert r2_hash != original_hash
    assert r1_hash != r2_hash
