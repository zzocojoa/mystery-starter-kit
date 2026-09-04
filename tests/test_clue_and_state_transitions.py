"""Clue 재맥락화와 유연한 Character State Transition 계약 검증."""

from copy import deepcopy
from pathlib import Path

from VALIDATORS.character_state_transitions import (
    validate_character_state_transitions,
)
from VALIDATORS.clue_recontextualization import validate_clue_recontextualization
from VALIDATORS.dependency import (
    artifact_required_for_project,
    dependency_artifacts,
    validate_dependency_graph,
)
from VALIDATORS.io import load_json_object
from VALIDATORS.schema_validation import collect_schema_errors

ROOT = Path(__file__).resolve().parents[1]
CLUE_SCHEMA_PATH = ROOT / "STANDARD/schemas/clue_matrix.schema.json"
TRANSITION_SCHEMA_PATH = (
    ROOT / "STANDARD/schemas/character_state_transitions.schema.json"
)
CHANNEL = load_json_object(ROOT / "CHANNELS/mystery_main/versions/2.1.0/channel_dna.json")


def scene_cards() -> dict[str, object]:
    """Seed, 중간 재맥락, Reveal 순서가 있는 Scene Fixture를 만든다."""
    return {
        "project_id": "PRJ-005",
        "scenes": [
            {"scene_id": "SCN-01", "order": 1},
            {"scene_id": "SCN-02", "order": 2},
            {"scene_id": "SCN-03", "order": 3},
        ],
    }


def versioned_clue_matrix() -> dict[str, object]:
    """표면 의미가 Reveal 뒤 바뀌는 Clue Matrix 1.1 Fixture를 만든다."""
    return {
        "$schema": "../../../STANDARD/schemas/clue_matrix.schema.json",
        "schema_family": "clue-matrix",
        "schema_version": "1.1.0",
        "project_id": "PRJ-005",
        "clues": [
            {
                "clue_id": "CLUE-01",
                "role": "CORE",
                "supports_final_reveal": True,
                "introduced_scene_order": 1,
                "introduced_scene_id": "SCN-01",
                "resolved_scene_order": 3,
                "resolved_scene_id": "SCN-03",
                "reveal_mode": "SEEDED_REINTERPRETATION",
                "surface_meaning": "빈 의자가 피해자의 자발적 이탈을 암시한다.",
                "actual_meaning": "의자 위치는 강제로 이동된 시간을 증명한다.",
                "first_seen_scene_id": "SCN-01",
                "reveal_scene_id": "SCN-03",
                "recontextualized_scene_ids": ["SCN-01", "SCN-02"],
            }
        ],
    }


def production_config() -> dict[str, object]:
    """새 Screenplay mode를 활성화한 최소 Config를 반환한다."""
    return {
        "script_source_mode": "SCREENPLAY_UNITS",
        "source_truth_classification": "ORIGINAL_FICTION",
    }


def transition_document(narrative_path: str) -> dict[str, object]:
    """회복 Stage를 강제하지 않는 Beat 단위 상태 변화 Fixture를 만든다."""
    return {
        "$schema": "../../../STANDARD/schemas/character_state_transitions.schema.json",
        "schema_family": "character-state-transitions",
        "schema_version": "1.0.0",
        "project_id": "PRJ-005",
        "narrative_path": narrative_path,
        "transitions": [
            {
                "transition_id": "CSTATE-001",
                "order": 1,
                "character_id": "CHAR-01",
                "scope_type": "BEAT",
                "scope_id": "BEAT-01",
                "state_before": "목격한 소리를 우연으로 여긴다.",
                "state_after": "소리가 사건 시각과 연결된다고 의심한다.",
                "triggers": {
                    "fact_ids": ["FACT-01"],
                    "clue_ids": [],
                    "crime_event_ids": [],
                },
                "change_category": "BELIEF",
            },
            {
                "transition_id": "CSTATE-002",
                "order": 2,
                "character_id": "CHAR-01",
                "scope_type": "BEAT",
                "scope_id": "BEAT-02",
                "state_before": "소리가 사건 시각과 연결된다고 의심한다.",
                "state_after": "위험을 감수하고 기록을 보존하기로 선택한다.",
                "triggers": {
                    "fact_ids": [],
                    "clue_ids": ["CLUE-01"],
                    "crime_event_ids": ["EVENT-01"],
                },
                "change_category": "CHOICE",
            },
        ],
    }


def transition_inputs() -> tuple[dict[str, object], ...]:
    """Transition 참조 검증에 필요한 상위 Artifact 묶음을 반환한다."""
    return (
        {"characters": [{"character_id": "CHAR-01"}]},
        {"facts": [{"fact_id": "FACT-01"}]},
        versioned_clue_matrix(),
        {"event_id": "EVENT-01"},
        {"beats": [{"beat_id": "BEAT-01"}, {"beat_id": "BEAT-02"}]},
        scene_cards(),
    )


def transition_issue_codes(document: dict[str, object]) -> set[str]:
    """Transition 의미 오류 코드 집합을 반환한다."""
    characters, facts, clues, event, beats, scenes = transition_inputs()
    return {
        issue["code"]
        for issue in validate_character_state_transitions(
            production_config(),
            CHANNEL,
            document,
            characters,
            facts,
            clues,
            event,
            beats,
            scenes,
        )
    }


def test_legacy_clue_matrix_remains_valid_without_version_fields() -> None:
    """기존 Clue 문서는 새 재해석 필드나 Migration 없이 계속 유효하다."""
    legacy = {
        "project_id": "PRJ-005",
        "clues": [
            {
                "clue_id": "CLUE-01",
                "role": "CORE",
                "introduced_scene_order": 1,
                "introduced_scene_id": "SCN-01",
                "resolved_scene_order": 3,
                "resolved_scene_id": "SCN-03",
            }
        ],
    }

    assert collect_schema_errors(
        legacy,
        load_json_object(CLUE_SCHEMA_PATH),
        "legacy clue matrix",
    ) == []
    assert validate_clue_recontextualization(legacy, scene_cards()) == []


def test_seeded_clue_reinterpretation_passes() -> None:
    """Seed가 Reveal보다 앞서고 실제 의미가 달라지면 재해석 계약을 통과한다."""
    document = versioned_clue_matrix()

    assert collect_schema_errors(
        document,
        load_json_object(CLUE_SCHEMA_PATH),
        "versioned clue matrix",
    ) == []
    assert validate_clue_recontextualization(document, scene_cards()) == []


def test_reveal_without_prior_seed_fails() -> None:
    """Seed와 Reveal이 같은 장면이면 Mystery 재해석으로 인정하지 않는다."""
    document = versioned_clue_matrix()
    clues = document["clues"]
    assert isinstance(clues, list)
    clue = clues[0]
    assert isinstance(clue, dict)
    clue["first_seen_scene_id"] = "SCN-03"
    clue["introduced_scene_id"] = "SCN-03"
    clue["introduced_scene_order"] = 3
    clue["recontextualized_scene_ids"] = ["SCN-03"]

    issues = validate_clue_recontextualization(document, scene_cards())

    assert "REVEAL_WITHOUT_PRIOR_SEED" in {issue["code"] for issue in issues}


def test_identical_surface_and_actual_meaning_fails() -> None:
    """공백·대소문자만 다른 의미는 재해석으로 위장할 수 없다."""
    document = versioned_clue_matrix()
    clues = document["clues"]
    assert isinstance(clues, list)
    clue = clues[0]
    assert isinstance(clue, dict)
    clue["actual_meaning"] = "  빈 의자가 피해자의 자발적 이탈을 암시한다.  "

    issues = validate_clue_recontextualization(document, scene_cards())

    assert "CLUE_MEANING_NOT_RECONTEXTUALIZED" in {
        issue["code"] for issue in issues
    }


def test_intentional_non_mystery_disclosure_does_not_require_prior_seed() -> None:
    """명시적 비미스터리 공개는 같은 Scene에서 처음 보여도 허용한다."""
    document = versioned_clue_matrix()
    clues = document["clues"]
    assert isinstance(clues, list)
    clue = clues[0]
    assert isinstance(clue, dict)
    clue["reveal_mode"] = "INTENTIONAL_NON_MYSTERY_DISCLOSURE"
    for field in (
        "surface_meaning",
        "actual_meaning",
        "first_seen_scene_id",
        "recontextualized_scene_ids",
    ):
        clue.pop(field)

    assert collect_schema_errors(
        document,
        load_json_object(CLUE_SCHEMA_PATH),
        "direct disclosure clue matrix",
    ) == []
    assert validate_clue_recontextualization(document, scene_cards()) == []


def test_fatality_path_passes_without_agency_recovery() -> None:
    """사망 피해 구조는 AGENCY_RECOVERY Transition 없이 유효하다."""
    document = transition_document("FATALITY")
    schema = load_json_object(TRANSITION_SCHEMA_PATH)

    assert collect_schema_errors(document, schema, "fatality transitions") == []
    assert transition_issue_codes(document) == set()
    transitions = document["transitions"]
    assert isinstance(transitions, list)
    assert all(
        isinstance(transition, dict) and "recovery_function" not in transition
        for transition in transitions
    )


def test_witness_path_passes_without_agency_recovery() -> None:
    """목격자 중심 구조도 회복 Stage를 강제하지 않는다."""
    document = transition_document("WITNESS_CENTERED")

    assert transition_issue_codes(document) == set()


def test_beat_transition_validates_before_scene_set_is_available() -> None:
    """BEAT Scope 검증은 Scene Card가 없어도 독립적으로 성립한다."""
    document = transition_document("NON_RECOVERY")
    characters, facts, clues, event, beats, _scenes = transition_inputs()

    issues = validate_character_state_transitions(
        production_config(),
        CHANNEL,
        document,
        characters,
        facts,
        clues,
        event,
        beats,
        {},
    )

    assert issues == []


def test_scene_transition_validates_only_against_realized_scene() -> None:
    """SCENE Scope는 Scene Card 생성 뒤 실제 Scene ID에 결속된다."""
    document = transition_document("NON_RECOVERY")
    transitions = document["transitions"]
    assert isinstance(transitions, list)
    first = transitions[0]
    assert isinstance(first, dict)
    first["scope_type"] = "SCENE"
    first["scope_id"] = "SCN-01"

    assert transition_issue_codes(document) == set()

    first["scope_id"] = "SCN-99"
    assert "CHARACTER_STATE_REFERENCE_INVALID" in transition_issue_codes(document)


def test_transition_dependency_order_is_cycle_free() -> None:
    """Scene이 먼저, Transition과 Presentation이 그 뒤에 오는 DAG를 고정한다."""
    graph = load_json_object(ROOT / "STANDARD/dependency_graph.json")
    definitions = dependency_artifacts(graph)

    validate_dependency_graph(graph)
    scene_dependencies = definitions["scene_cards"]["depends_on"]
    transition_dependencies = definitions["character_state_transitions"]["depends_on"]
    presentation_dependencies = definitions["presentation_plan"]["depends_on"]
    assert isinstance(scene_dependencies, list)
    assert isinstance(transition_dependencies, list)
    assert isinstance(presentation_dependencies, list)
    assert "character_state_transitions" not in scene_dependencies
    assert "scene_cards" in transition_dependencies
    assert "character_state_transitions" in presentation_dependencies


def test_transition_rejects_broken_state_chain_and_unknown_trigger() -> None:
    """상태 연속성과 상위 Trigger 참조를 Metadata만으로 위조할 수 없다."""
    document = transition_document("WITNESS_CENTERED")
    transitions = document["transitions"]
    assert isinstance(transitions, list)
    second = transitions[1]
    assert isinstance(second, dict)
    second["state_before"] = "앞선 상태와 무관한 상태"
    triggers = second["triggers"]
    assert isinstance(triggers, dict)
    triggers["fact_ids"] = ["FACT-99"]

    assert {
        "CHARACTER_STATE_CHAIN_BROKEN",
        "CHARACTER_STATE_REFERENCE_INVALID",
    }.issubset(transition_issue_codes(document))


def test_new_transition_artifact_replaces_fixed_arc_only_in_new_mode() -> None:
    """Legacy mode는 고정 Arc를, 새 mode는 유연한 Transition을 조건부 요구한다."""
    graph = load_json_object(ROOT / "STANDARD/dependency_graph.json")
    definitions = dependency_artifacts(graph)
    legacy_config = {
        "channel_content_version": "2.1.0",
        "source_truth_classification": "ORIGINAL_FICTION",
    }
    screenplay_config = deepcopy(legacy_config)
    screenplay_config["script_source_mode"] = "SCREENPLAY_UNITS"
    legacy_channel = deepcopy(CHANNEL)
    capabilities = legacy_channel["capabilities"]
    assert isinstance(capabilities, dict)
    capabilities["SCENE_REALIZATION_POLICY"] = {"enabled": True}

    assert artifact_required_for_project(
        definitions["psychological_arc"],
        legacy_channel,
        legacy_config,
        {},
    )
    assert not artifact_required_for_project(
        definitions["character_state_transitions"],
        legacy_channel,
        legacy_config,
        {},
    )
    assert not artifact_required_for_project(
        definitions["psychological_arc"],
        legacy_channel,
        screenplay_config,
        {},
    )
    assert artifact_required_for_project(
        definitions["character_state_transitions"],
        legacy_channel,
        screenplay_config,
        {},
    )
