"""명시적 대인범죄 최종 계약의 실패·성공 행렬을 검증한다."""

from copy import deepcopy
from pathlib import Path

import pytest

from VALIDATORS.candidate_event_briefs import (
    canonical_json_hash,
    cardinality_issues,
    fiction_resolution_issues,
    placeholder_issues,
    validate_candidate_event_briefs,
)
from VALIDATORS.candidate_projection import validate_approved_candidate_projection
from VALIDATORS.crime_event import (
    explicit_crime_policy,
    required_semantic_subjects,
    validate_crime_event_traceability,
    validate_crime_role_bindings,
    validate_scene_crime_realization,
    validate_script_crime_realization,
    validate_truth_basis,
)
from VALIDATORS.crime_functions import DEFAULT_DEVELOPMENT_FUNCTIONS
from VALIDATORS.editorial import (
    explicit_crime_runtime_evidence_issues,
    make_editorial_evidence,
    validate_editorial_crime_assessments,
)
from VALIDATORS.io import load_json_object
from VALIDATORS.models import ValidationIssue
from VALIDATORS.scene_realization import (
    validate_panel_design_realization,
    validate_panel_script_density,
)

ROOT = Path(__file__).resolve().parents[1]
CHANNEL = load_json_object(ROOT / "CHANNELS/mystery_main/versions/2.1.0/channel_dna.json")
FIELD_EVIDENCE_KEYS = (
    "PRIMARY_CRIME",
    "CULPRIT",
    "MOTIVE",
    "METHOD",
    "HARM_RESULT",
    "LEGAL_OUTCOME",
)


def issue_codes(issues: list[ValidationIssue]) -> set[str]:
    """검증 결과에서 오류 코드 집합을 반환한다."""
    return {issue["code"] for issue in issues}


def fiction_truth_basis() -> dict[str, object]:
    """창작 사건의 필드별 Truth Basis를 만든다."""
    return {
        "source_truth_classification": "ORIGINAL_FICTION",
        "field_evidence": {
            field: {"classification": "ORIGINAL_FICTION", "claim_ids": []}
            for field in FIELD_EVIDENCE_KEYS
        },
    }


def event_contract() -> dict[str, object]:
    """교차 Artifact 검증용 최소 사건 계약을 만든다."""
    return {
        "event_id": "EVENT-01",
        "primary_crime": "ASSAULT",
        "core_action_type": "ASSAULT",
        "responsible_agent_structure": "SINGLE_AGENT",
        "victim_structure": "SINGLE_VICTIM",
        "offender_role_slots": ["OFFENDER-01"],
        "victim_role_slots": ["VICTIM-01"],
        "protagonist_role_slot": "PROTAGONIST-01",
        "role_bindings": [
            {
                "role_slot": "OFFENDER-01",
                "character_id": "CHAR-01",
                "role_type": "OFFENDER",
            },
            {
                "role_slot": "VICTIM-01",
                "character_id": "CHAR-02",
                "role_type": "VICTIM",
            },
            {
                "role_slot": "PROTAGONIST-01",
                "character_id": "CHAR-02",
                "role_type": "PROTAGONIST",
            },
        ],
        "actor_ids": ["CHAR-01"],
        "victim_ids": ["CHAR-02"],
        "protagonist_id": "CHAR-02",
        "motive_summary": "접근 거절에 대한 보복을 선택했다.",
        "non_actionable_method_summary": "퇴로를 막고 비선정적 폭력을 가했다.",
        "immediate_harm": "피해자는 치료가 필요한 상해를 입었다.",
        "lasting_harm": "피해자는 업무 공간에 돌아가지 못했다.",
        "responsibility_path": "목격과 출입 기록이 책임 주체를 확인했다.",
        "harm_ids": ["HARM-01"],
        "development_functions": [
            {
                "development_function_id": f"CDEV-{index:03d}",
                "function_type": function_type,
                "summary": f"{function_type} 기능을 인물의 선택과 결과 변화로 구현한다.",
                "required": True,
            }
            for index, function_type in enumerate(
                DEFAULT_DEVELOPMENT_FUNCTIONS["RELATIONAL_VIOLENCE"],
                1,
            )
        ],
        "reveal_targets": [
            {
                "reveal_target_id": f"REVEAL-TARGET-{index:02d}",
                "target_type": target_type,
                "summary": f"{target_type}의 구체 공개",
                "planned_phase": "LATE",
                "planned_segment_id": None,
            }
            for index, target_type in enumerate(
                ("CULPRIT", "MOTIVE", "METHOD", "HARM_RESULT"),
                1,
            )
        ],
        "truth_basis": fiction_truth_basis(),
    }


def participant_contract(
    offender_structure: str,
    actor_ids: list[str],
    victim_structure: str,
    victim_ids: list[str],
) -> tuple[dict[str, object], dict[str, object]]:
    """Participant 구조와 실제 Character 결속 묶음을 만든다."""
    offender_slot_count = {
        "SINGLE_AGENT": 1,
        "DUAL_AGENTS": 2,
        "COMPLICIT_GROUP": 3,
    }[offender_structure]
    victim_slot_count = {"SINGLE_VICTIM": 1, "MULTIPLE_VICTIMS": 2}[victim_structure]
    offender_slots = [f"OFFENDER-{index:02d}" for index in range(1, offender_slot_count + 1)]
    victim_slots = [f"VICTIM-{index:02d}" for index in range(1, victim_slot_count + 1)]
    bindings = [
        {
            "role_slot": slot,
            "character_id": actor_ids[index],
            "role_type": "OFFENDER",
        }
        for index, slot in enumerate(offender_slots[: len(actor_ids)])
    ]
    bindings.extend(
        {
            "role_slot": slot,
            "character_id": victim_ids[index],
            "role_type": "VICTIM",
        }
        for index, slot in enumerate(victim_slots[: len(victim_ids)])
    )
    contract: dict[str, object] = {
        "responsible_agent_structure": offender_structure,
        "victim_structure": victim_structure,
        "offender_role_slots": offender_slots,
        "victim_role_slots": victim_slots,
        "actor_ids": actor_ids,
        "victim_ids": victim_ids,
        "role_bindings": bindings,
    }
    characters: dict[str, object] = {
        "characters": [
            {
                "character_id": character_id,
                "crime_role_slots": [
                    str(binding["role_slot"])
                    for binding in bindings
                    if binding["character_id"] == character_id
                ],
            }
            for character_id in dict.fromkeys([*actor_ids, *victim_ids])
        ]
    }
    return contract, characters


@pytest.mark.parametrize(
    ("offender_structure", "actor_ids", "expected_error"),
    (
        ("DUAL_AGENTS", ["CHAR-01"], True),
        ("DUAL_AGENTS", ["CHAR-01", "CHAR-02"], False),
        ("COMPLICIT_GROUP", ["CHAR-01", "CHAR-02"], True),
        ("COMPLICIT_GROUP", ["CHAR-01", "CHAR-02", "CHAR-03"], False),
        ("SINGLE_AGENT", ["CHAR-01", "CHAR-02"], True),
    ),
)
def test_offender_participant_cardinality(
    offender_structure: str,
    actor_ids: list[str],
    expected_error: bool,
) -> None:
    """가해자 구조는 서로 다른 실제 actor_id 수와 일치해야 한다."""
    contract, characters = participant_contract(
        offender_structure,
        actor_ids,
        "SINGLE_VICTIM",
        ["CHAR-90"],
    )
    has_error = "OFFENDER_CARDINALITY_MISMATCH" in issue_codes(
        validate_crime_role_bindings(contract, characters)
    )
    assert has_error is expected_error


@pytest.mark.parametrize(
    ("victim_ids", "expected_error"),
    ((["CHAR-10"], True), (["CHAR-10", "CHAR-11"], False)),
)
def test_multiple_victim_cardinality(victim_ids: list[str], expected_error: bool) -> None:
    """복수 피해 구조는 서로 다른 피해자 두 명 이상을 요구한다."""
    contract, characters = participant_contract(
        "SINGLE_AGENT",
        ["CHAR-01"],
        "MULTIPLE_VICTIMS",
        victim_ids,
    )
    has_error = "VICTIM_CARDINALITY_MISMATCH" in issue_codes(
        validate_crime_role_bindings(contract, characters)
    )
    assert has_error is expected_error


def selection() -> dict[str, object]:
    """Candidate Event Brief에 결속할 구조 선택을 만든다."""
    return {
        "primary_crime": "ASSAULT",
        "core_action_type": "ASSAULT",
        "responsible_agent_structure": "SINGLE_AGENT",
        "victim_structure": "SINGLE_VICTIM",
        "relationship_context": "WORKPLACE",
        "motive_category": "RETALIATION",
    }


def event_brief(candidate_id: str, causal_index: int) -> dict[str, object]:
    """서로 다른 구체 인과를 가진 Candidate Event Brief를 만든다."""
    causal_profiles = (
        (
            "혼자 마감하는 근무 시간을 반복 관찰했다.",
            "사적 접근을 거절한 순간 보복을 결심했다.",
            "폐점 직전 퇴로를 막고 비선정적 폭력을 가했다.",
            "치료가 필요한 상해와 즉각적인 안전 상실이 생겼다.",
            "동료 목격과 출입 기록이 책임을 특정했다.",
        ),
        (
            "피해자의 정기 귀가 동선을 알고 있었다.",
            "관계 종료 의사를 들은 날 통제를 선택했다.",
            "귀가 길에서 반복 접근해 이동 자유를 제한했다.",
            "도움을 요청하지 못하는 동안 자유가 박탈됐다.",
            "약속 불참과 주변인 기록이 계획된 접근을 확인했다.",
        ),
        (
            "공동 주거의 출입 권한과 가족 일정을 악용했다.",
            "경제 문제에 대한 책임 요구 직후 위협했다.",
            "허락 없이 주거에 들어와 위협으로 통제했다.",
            "거주 공간 안전이 무너지고 방어 중 상처를 입었다.",
            "이웃 신고와 훼손 흔적이 침입 책임을 입증했다.",
        ),
        (
            "업무 평가권으로 피해자를 고립시킬 수 있었다.",
            "부당한 지시를 공식 문제 삼자 감금을 선택했다.",
            "밀폐된 업무 공간에서 외부 이동을 막았다.",
            "장시간 자유 박탈과 공포 반응이 이어졌다.",
            "중단된 통화와 동료 수색이 장소와 책임을 연결했다.",
        ),
        (
            "공개 행사에서 이동과 연락 상대를 반복 관찰했다.",
            "접근 금지 요구가 알려진 직후 추적을 계속했다.",
            "여러 장소에서 기다리며 접근을 반복했다.",
            "신변 위협으로 직장과 주거지를 바꾸게 됐다.",
            "독립된 장소 기록이 지속적 추적 책임을 확정했다.",
        ),
    )
    profile = causal_profiles[causal_index]
    locked_selection = selection()
    return {
        "candidate_id": candidate_id,
        "candidate_selection_sha256": canonical_json_hash(locked_selection),
        **locked_selection,
        "offender_role_slots": ["OFFENDER-01"],
        "victim_role_slots": ["VICTIM-01"],
        "protagonist_role_slot": "PROTAGONIST-01",
        "target_selection_reason": profile[0],
        "initiating_context": "반복 접근이 가능한 조건이 사건 전부터 형성됐다.",
        "trigger_event": profile[1],
        "motive_summary": "거절 이후 통제력을 되찾으려는 보복 동기였다.",
        "non_actionable_method_summary": profile[2],
        "immediate_harm": profile[3],
        "lasting_harm": "피해자는 기존 생활 공간을 이용하지 못하게 됐다.",
        "concealment_or_denial": "우발적 충돌이었다고 주장하며 책임을 부인했다.",
        "discovery_path": "독립된 목격과 기록이 피해 진술을 뒷받침했다.",
        "responsibility_path": profile[4],
        "central_pursuit_question": "어떤 증거가 범죄 선택과 책임 주체를 확인하는가?",
        "development_functions": [
            {
                "development_function_id": f"CDEV-{index:03d}",
                "function_type": function_type,
                "summary": f"{function_type} 기능을 인물의 선택과 결과 변화로 구현한다.",
                "required": True,
            }
            for index, function_type in enumerate(
                DEFAULT_DEVELOPMENT_FUNCTIONS["RELATIONAL_VIOLENCE"],
                1,
            )
        ],
        "reveal_targets": [
            {
                "reveal_target_id": "REVEAL-TARGET-01",
                "target_type": "CULPRIT",
                "summary": profile[4],
                "planned_phase": "LATE",
                "planned_segment_id": None,
            }
        ],
        "truth_basis": fiction_truth_basis(),
    }


@pytest.mark.parametrize(
    ("field", "placeholder"),
    (
        ("non_actionable_method_summary", "CHAR-01의 ASSAULT 행위"),
        ("immediate_harm", "HARM-01의 피해 결과"),
    ),
)
def test_candidate_event_placeholder_is_rejected(field: str, placeholder: str) -> None:
    """ID를 자연어처럼 감싼 사건 Placeholder를 거부한다."""
    brief = event_brief("VAR-01", 0)
    brief[field] = placeholder
    assert "CANDIDATE_EVENT_PLACEHOLDER_FORBIDDEN" in issue_codes(placeholder_issues(brief))


def test_candidate_event_causal_collision_and_distinct_pass() -> None:
    """같은 인과 사건 다섯 건은 실패하고 서로 다른 다섯 건은 통과한다."""
    candidates = [
        {"candidate_id": f"VAR-{index:02d}", "selection": selection()} for index in range(1, 6)
    ]
    variations = {"candidates": candidates, "approved_candidate_id": "VAR-01"}
    collided = [event_brief(f"VAR-{index:02d}", 0) for index in range(1, 6)]
    distinct = [event_brief(f"VAR-{index:02d}", index - 1) for index in range(1, 6)]
    assert "CANDIDATE_EVENT_CAUSAL_COLLISION" in issue_codes(
        validate_candidate_event_briefs(
            variations,
            {"briefs": collided},
            explicit_crime_policy(CHANNEL),
        )
    )
    assert (
        validate_candidate_event_briefs(
            variations,
            {"briefs": distinct},
            explicit_crime_policy(CHANNEL),
        )
        == []
    )


def test_required_false_and_ambiguous_function_declarations_are_rejected() -> None:
    """LLM이 필수 기능을 완화하거나 중복 선언해 검증을 우회할 수 없다."""
    variations = {
        "candidates": [{"candidate_id": "VAR-01", "selection": selection()}],
        "approved_candidate_id": "VAR-01",
    }
    weakened = event_brief("VAR-01", 0)
    weakened_functions = weakened["development_functions"]
    assert isinstance(weakened_functions, list)
    weakened_functions[0]["required"] = False
    assert "CRIME_DEVELOPMENT_FUNCTION_REQUIRED_WEAKENED" in issue_codes(
        validate_candidate_event_briefs(
            variations,
            {"briefs": [weakened]},
            explicit_crime_policy(CHANNEL),
        )
    )

    duplicated_id = event_brief("VAR-01", 0)
    duplicated_id_functions = duplicated_id["development_functions"]
    assert isinstance(duplicated_id_functions, list)
    duplicated_id_functions[1]["development_function_id"] = "CDEV-001"
    assert "CRIME_DEVELOPMENT_FUNCTION_ID_DUPLICATED" in issue_codes(
        validate_candidate_event_briefs(
            variations,
            {"briefs": [duplicated_id]},
            explicit_crime_policy(CHANNEL),
        )
    )

    ambiguous = event_brief("VAR-01", 0)
    ambiguous_functions = ambiguous["development_functions"]
    assert isinstance(ambiguous_functions, list)
    ambiguous_functions[1]["function_type"] = ambiguous_functions[0]["function_type"]
    codes = issue_codes(
        validate_candidate_event_briefs(
            variations,
            {"briefs": [ambiguous]},
            explicit_crime_policy(CHANNEL),
        )
    )
    assert "CRIME_DEVELOPMENT_FUNCTION_AMBIGUOUS" in codes
    assert "CRIME_DEVELOPMENT_FUNCTION_MISSING" in codes


def test_original_fiction_requires_concrete_motive_and_resolution() -> None:
    """창작 사건은 UNKNOWN 동기나 미해결 발견 경로를 사용할 수 없다."""
    unresolved = event_brief("VAR-01", 0)
    unresolved["motive_category"] = "UNKNOWN_UNLESS_EVIDENCED"
    unresolved["discovery_path"] = "UNKNOWN"
    codes = issue_codes(fiction_resolution_issues(unresolved))
    assert "FICTION_MOTIVE_UNRESOLVED" in codes
    assert "FICTION_DISCOVERY_PATH_UNRESOLVED" in codes
    assert fiction_resolution_issues(event_brief("VAR-01", 0)) == []


def trace_bundle() -> tuple[
    dict[str, object],
    dict[str, object],
    dict[str, object],
    dict[str, object],
    dict[str, object],
    dict[str, object],
    dict[str, object],
]:
    """정상 Candidate→Viewer 교차 추적 묶음을 만든다."""
    contract = event_contract()
    characters: dict[str, object] = {
        "characters": [
            {"character_id": "CHAR-01", "crime_role_slots": ["OFFENDER-01"]},
            {
                "character_id": "CHAR-02",
                "crime_role_slots": ["VICTIM-01", "PROTAGONIST-01"],
            },
        ]
    }
    case_input: dict[str, object] = {
        "primary_crime": contract["primary_crime"],
        "responsible_actor_ids": contract["actor_ids"],
        "victim_ids": contract["victim_ids"],
        "motive_summary": contract["motive_summary"],
        "crime_method_summary": contract["non_actionable_method_summary"],
        "harm_result": f"{contract['immediate_harm']} / {contract['lasting_harm']}",
        "final_case_truth": contract["responsibility_path"],
    }
    facts: dict[str, object] = {
        "facts": [
            {"crime_fact_type": fact_type}
            for fact_type in (
                "CRIME_ACTION",
                "HARM_RESULT",
                "MOTIVE_STATUS",
                "RESPONSIBILITY",
            )
        ]
    }
    actual_timeline: dict[str, object] = {
        "events": [
            {
                "crime_event_id": "EVENT-01",
                "event_type": "CRIME_EVENT",
                "actor_ids": ["CHAR-01"],
                "victim_ids": ["CHAR-02"],
                "harm_ids": ["HARM-01"],
            },
            {
                "crime_event_id": "EVENT-01",
                "event_type": "HARM_RESULT",
                "actor_ids": ["CHAR-01"],
                "victim_ids": ["CHAR-02"],
                "harm_ids": ["HARM-01"],
            },
        ]
    }
    node_types = (
        ("MOTIVE-01", "MOTIVE_OR_TRIGGER"),
        ("CRIME-01", "CRIME_EVENT"),
        ("HARM-01", "HARM_RESULT"),
        ("DENIAL-01", "CONCEALMENT_OR_DENIAL"),
        ("DISCOVERY-01", "DISCOVERY_PATH"),
        ("RESPONSIBILITY-01", "RESPONSIBILITY_CONFIRMATION"),
    )
    nodes: list[dict[str, object]] = [
        {"node_id": node_id, "type": node_type, "crime_event_id": "EVENT-01"}
        for node_id, node_type in node_types
    ]
    nodes[1].update(
        {
            "actor_ids": ["CHAR-01"],
            "victim_ids": ["CHAR-02"],
            "harm_ids": ["HARM-01"],
        }
    )
    nodes[2]["harm_ids"] = ["HARM-01"]
    causal_graph: dict[str, object] = {
        "nodes": nodes,
        "edges": [
            {"from": "MOTIVE-01", "to": "CRIME-01"},
            {"from": "CRIME-01", "to": "HARM-01"},
            {"from": "DENIAL-01", "to": "DISCOVERY-01"},
            {"from": "DISCOVERY-01", "to": "RESPONSIBILITY-01"},
        ],
    }
    raw_reveal_targets = contract.get("reveal_targets")
    assert isinstance(raw_reveal_targets, list)
    reveal_targets = [target for target in raw_reveal_targets if isinstance(target, dict)]
    viewer_timeline: dict[str, object] = {
        "reveals": [
            {
                "reveal_target_id": target["reveal_target_id"],
                "target_type": target["target_type"],
            }
            for target in reveal_targets
        ]
    }
    return (
        contract,
        characters,
        case_input,
        facts,
        actual_timeline,
        causal_graph,
        viewer_timeline,
    )


def trace_issues(
    bundle: tuple[
        dict[str, object],
        dict[str, object],
        dict[str, object],
        dict[str, object],
        dict[str, object],
        dict[str, object],
        dict[str, object],
    ],
) -> list[ValidationIssue]:
    """교차 추적 묶음을 Validator에 전달한다."""
    return validate_crime_event_traceability(*bundle)


def test_cross_artifact_trace_matrix() -> None:
    """Character·Case·Timeline·Causal 결속 실패와 정상 경로를 검증한다."""
    valid = trace_bundle()
    assert trace_issues(valid) == []

    actor_missing = deepcopy(valid)
    missing_characters = actor_missing[1].get("characters")
    assert isinstance(missing_characters, list)
    actor_missing[1]["characters"] = missing_characters[1:]
    assert "CRIME_ROLE_CHARACTER_NOT_FOUND" in issue_codes(trace_issues(actor_missing))

    actor_as_victim = deepcopy(valid)
    victim_role_characters = actor_as_victim[1].get("characters")
    assert isinstance(victim_role_characters, list)
    first_character = victim_role_characters[0]
    assert isinstance(first_character, dict)
    first_character["crime_role_slots"] = ["VICTIM-01"]
    assert "CRIME_CHARACTER_TRACE_MISMATCH" in issue_codes(trace_issues(actor_as_victim))

    case_mismatch = deepcopy(valid)
    case_mismatch[2]["motive_summary"] = "계약과 다른 동기"
    assert "CRIME_CASE_TRACE_MISMATCH" in issue_codes(trace_issues(case_mismatch))

    timeline_missing_harm = deepcopy(valid)
    timeline_events = timeline_missing_harm[4].get("events")
    assert isinstance(timeline_events, list)
    timeline_missing_harm[4]["events"] = timeline_events[:1]
    assert "CRIME_TIMELINE_TRACE_MISMATCH" in issue_codes(trace_issues(timeline_missing_harm))

    causal_missing_path = deepcopy(valid)
    causal_missing_path[5]["edges"] = []
    assert "CRIME_CAUSAL_TRACE_MISMATCH" in issue_codes(trace_issues(causal_missing_path))


def true_case_bundle() -> tuple[dict[str, object], dict[str, object]]:
    """필드별 FACT Evidence가 완전한 실화 사건을 만든다."""
    facts: dict[str, object] = {
        "facts": [
            {
                "fact_id": f"FACT-{index:02d}",
                "classification": "FACT",
                "basis_fact_ids": [],
                "presented_as_fact": True,
            }
            for index in range(1, 7)
        ]
    }
    contract = event_contract()
    contract["truth_basis"] = {
        "source_truth_classification": "VERIFIED_TRUE_CASE",
        "field_evidence": {
            field: {"classification": "FACT", "claim_ids": [f"FACT-{index:02d}"]}
            for index, field in enumerate(FIELD_EVIDENCE_KEYS, 1)
        },
    }
    return contract, facts


@pytest.mark.parametrize("missing_field", ("CULPRIT", "METHOD", "HARM_RESULT"))
def test_true_case_requires_each_field_evidence(missing_field: str) -> None:
    """실화의 범인·방식·피해 결과 Evidence 누락을 각각 차단한다."""
    contract, facts = true_case_bundle()
    truth_basis = contract["truth_basis"]
    assert isinstance(truth_basis, dict)
    field_evidence = truth_basis["field_evidence"]
    assert isinstance(field_evidence, dict)
    field_evidence.pop(missing_field)
    assert "CRIME_FIELD_EVIDENCE_MISSING" in issue_codes(
        validate_truth_basis(
            {"source_truth_classification": "VERIFIED_TRUE_CASE"},
            contract,
            facts,
        )
    )


def test_true_case_unknown_motive_is_honest_and_unsupported_fact_fails() -> None:
    """미상 동기는 정직하게 표시하고 무근거 FACT 승격은 거부한다."""
    contract, facts = true_case_bundle()
    truth_basis = contract["truth_basis"]
    assert isinstance(truth_basis, dict)
    field_evidence = truth_basis["field_evidence"]
    assert isinstance(field_evidence, dict)
    field_evidence["MOTIVE"] = {"classification": "UNKNOWN", "claim_ids": []}
    contract["motive_summary"] = "수사기관이 확인한 범행 동기는 공개되지 않았다."
    config = {"source_truth_classification": "VERIFIED_TRUE_CASE"}
    assert validate_truth_basis(config, contract, facts) == []

    contract["motive_summary"] = "질투가 범행 동기였다고 확정한다."
    assert "CRIME_UNKNOWN_PROMOTED_TO_FACT" in issue_codes(
        validate_truth_basis(config, contract, facts)
    )

    field_evidence["MOTIVE"] = {"classification": "FACT", "claim_ids": ["FACT-99"]}
    assert "CRIME_FIELD_FACT_UNSUPPORTED" in issue_codes(
        validate_truth_basis(config, contract, facts)
    )


def development_bundle(
    realization_mode: str,
    include_scene_function: bool,
    include_script_trace: bool,
) -> tuple[
    dict[str, object],
    dict[str, object],
    dict[str, object],
    dict[str, object],
    dict[str, object],
    str,
]:
    """Development Function의 Scene·Layer·Script 검증 묶음을 만든다."""
    contract = event_contract()
    contract["reveal_targets"] = []
    function_ids = [
        f"CDEV-{index:03d}"
        for index, _function_type in enumerate(
            DEFAULT_DEVELOPMENT_FUNCTIONS["RELATIONAL_VIOLENCE"],
            1,
        )
    ]
    mode_to_segment = {"DRAMA": "SEG-001", "NARRATION": "SEG-002", "PANEL_REACTION": "SEG-003"}
    target_segment = mode_to_segment[realization_mode]
    realization: dict[str, object] = {
        "event_id": "EVENT-01",
        "harm_ids": ["HARM-01"],
        "actor_ids": ["CHAR-01"],
        "victim_ids": ["CHAR-02"],
        "realization_mode": "IMPLIED_ACTION",
        "action_evidence": "퇴로를 막는 행동",
        "dialogue_or_behavior_evidence": "피해자의 방어 행동",
        "choice_or_emotion_change": "피해자가 도주를 선택한다.",
        "result_change": "상해와 장기 불안이 남는다.",
        "planned_segment_ids": [target_segment],
        "development_function_ids": list(function_ids) if include_scene_function else [],
        "expected_excerpt_anchor": "실제 범죄 행동 문구",
    }
    scene_cards: dict[str, object] = {
        "scenes": [
            {
                "scene_id": "SCN-01",
                "crime_realization": [realization],
            }
        ]
    }
    segments: list[dict[str, object]] = [
        {
            "segment_id": "SEG-001",
            "segment_type": "DRAMA",
            "scene_id": "SCN-01",
            "crime_development_function_ids": (
                list(function_ids)
                if realization_mode == "DRAMA" and include_scene_function
                else []
            ),
            "referenced_reveal_target_ids": [],
            "revealed_reveal_target_ids": [],
            "intentional_prereveal_ids": [],
        },
        {
            "segment_id": "SEG-002",
            "segment_type": "NARRATION",
            "scene_id": "SCN-01",
            "narrator_character_id": "CHAR-02",
            "narration_function": "FEAR",
            "crime_development_function_ids": (
                list(function_ids)
                if realization_mode == "NARRATION" and include_scene_function
                else []
            ),
            "referenced_reveal_target_ids": [],
            "revealed_reveal_target_ids": [],
            "intentional_prereveal_ids": [],
        },
        {
            "segment_id": "SEG-003",
            "segment_type": "PANEL_REACTION",
            "scene_id": "SCN-01",
            "reaction_segment_id": "RSEG-001",
            "crime_development_function_ids": (
                list(function_ids)
                if realization_mode == "PANEL_REACTION" and include_scene_function
                else []
            ),
            "referenced_reveal_target_ids": [],
            "revealed_reveal_target_ids": [],
            "intentional_prereveal_ids": [],
        },
    ]
    presentation: dict[str, object] = {"segments": segments}
    reactions: dict[str, object] = {
        "reaction_segments": [
            {
                "reaction_segment_id": "RSEG-001",
                "turns": [
                    {"function": "EMOTIONAL_REACTION"},
                    {"function": "HYPOTHESIS_REVISION"},
                ],
            }
        ]
    }
    viewer: dict[str, object] = {"reveals": []}
    trace = (
        "<!-- CRIME_TRACE\nEVENT=EVENT-01\nACTION=ASSAULT\nHARM=HARM-01\n"
        f"DEV={','.join(function_ids)}\n-->\n"
        "퇴로를 막고 비선정적 폭력을 가했다. "
        "피해자는 치료가 필요한 상해를 입었다. "
        "피해자는 업무 공간에 돌아가지 못했다."
    )
    bodies: dict[str, str] = {
        "SEG-001": trace
        if target_segment == "SEG-001" and include_script_trace
        else "사건 전 행동",
        "SEG-002": trace
        if target_segment == "SEG-002" and include_script_trace
        else "그때의 공포를 기억했다.",
        "SEG-003": trace
        if target_segment == "SEG-003" and include_script_trace
        else "패널이 가설을 고친다.",
    }
    modes: dict[str, str] = {
        "SEG-001": "DRAMA",
        "SEG-002": "NARRATION",
        "SEG-003": "PANEL_REACTION",
    }
    script = "\n\n".join(
        f"<!-- SEGMENT:{segment_id} TYPE:{mode} SCENE:SCN-01 DURATION:30 -->\n"
        f"{bodies[segment_id]}\n<!-- END_SEGMENT:{segment_id} -->"
        for segment_id, mode in modes.items()
    )
    return contract, scene_cards, presentation, reactions, viewer, script


def test_development_function_coverage_matrix() -> None:
    """필수 Function은 Scene과 실제 Drama Script에 모두 있어야 한다."""
    missing_scene = development_bundle("DRAMA", False, False)
    assert "CRIME_DEVELOPMENT_FUNCTION_UNMAPPED" in issue_codes(
        validate_scene_crime_realization(CHANNEL, *missing_scene[:3])
    )

    missing_script = development_bundle("DRAMA", True, False)
    assert "CRIME_DEVELOPMENT_FUNCTION_SCRIPT_MISSING" in issue_codes(
        validate_script_crime_realization(CHANNEL, *missing_script)
    )

    narration_only = development_bundle("NARRATION", True, True)
    assert "CRIME_FUNCTION_NARRATION_ONLY" in issue_codes(
        validate_script_crime_realization(CHANNEL, *narration_only)
    )

    panel_only = development_bundle("PANEL_REACTION", True, True)
    assert "CRIME_FUNCTION_PANEL_ONLY" in issue_codes(
        validate_script_crime_realization(CHANNEL, *panel_only)
    )

    valid = development_bundle("DRAMA", True, True)
    assert validate_script_crime_realization(CHANNEL, *valid) == []


def test_policy_required_function_and_unknown_references_cannot_be_evaded() -> None:
    """required 값과 무관하게 정책 필수 ID를 추적하고 미선언 참조를 거부한다."""
    weakened = development_bundle("DRAMA", True, True)
    contract, cards, presentation, reactions, viewer, script = weakened
    functions = contract["development_functions"]
    assert isinstance(functions, list)
    functions[0]["required"] = False
    realization = cards["scenes"][0]["crime_realization"][0]  # type: ignore[index]
    realization["development_function_ids"].remove("CDEV-001")
    presentation["segments"][0]["crime_development_function_ids"].remove(  # type: ignore[index]
        "CDEV-001"
    )
    script = script.replace(
        "DEV=CDEV-001,CDEV-002,CDEV-003,CDEV-004",
        "DEV=CDEV-002,CDEV-003,CDEV-004",
    )
    codes = issue_codes(
        validate_script_crime_realization(
            CHANNEL,
            contract,
            cards,
            presentation,
            reactions,
            viewer,
            script,
        )
    )
    assert "CRIME_DEVELOPMENT_FUNCTION_UNMAPPED" in codes
    assert "CRIME_DEVELOPMENT_FUNCTION_SCRIPT_MISSING" in codes

    unknown = development_bundle("DRAMA", True, True)
    unknown_script = unknown[-1].replace(
        "DEV=CDEV-001,CDEV-002,CDEV-003,CDEV-004",
        "DEV=CDEV-001,CDEV-002,CDEV-003,CDEV-004,CDEV-999",
    )
    assert "CRIME_DEVELOPMENT_FUNCTION_REFERENCE_UNKNOWN" in issue_codes(
        validate_script_crime_realization(CHANNEL, *unknown[:-1], unknown_script)
    )


def panel_reactions(with_exchange: bool) -> dict[str, object]:
    """Panel 상호 응답 여부를 선택한 Segment를 만든다."""
    second_turn: dict[str, object] = {
        "turn_id": "TURN-002",
        "panelist_id": "PANEL-02",
        "function": "HYPOTHESIS_REVISION",
    }
    if with_exchange:
        second_turn["responds_to_turn_id"] = "TURN-001"
    return {
        "reaction_segments": [
            {
                "reaction_segment_id": "RSEG-001",
                "duration_sec": 50,
                "turns": [
                    {
                        "turn_id": "TURN-001",
                        "panelist_id": "PANEL-01",
                        "function": "EMOTIONAL_REACTION",
                    },
                    second_turn,
                ],
            }
        ]
    }


def panel_script(word_count: int) -> str:
    """지정 어절 수의 Panel 방송 발화를 만든다."""
    spoken = " ".join(f"단어{index}" for index in range(word_count))
    return f'[RSEG-001] [PANEL-01] [EMOTIONAL_REACTION]\n[PANEL-01] "{spoken}"'


def runtime_review(spoken_seconds: int, graphic_seconds: int) -> dict[str, object]:
    """Panel 발화·Graphic 시간 근거를 만든다."""
    return {
        "runtime_evidence": {
            "method": "ESTIMATE",
            "language_unit": "KOREAN_EOJEOL",
            "estimation_assumptions": ["초당 2.5어절"],
            "panel_segments": [
                {
                    "segment_id": "SEG-001",
                    "planned_duration_sec": 50,
                    "estimated_spoken_duration_sec": spoken_seconds,
                    "action_duration_sec": 0,
                    "non_speaking_duration_sec": graphic_seconds,
                    "non_speech_elements": [
                        {
                            "element_type": "GRAPHIC",
                            "duration_sec": graphic_seconds,
                            "time_class": "NON_SPEAKING",
                            "support_status": "SUPPORTED",
                            "source_reference": "편집 계획 SEG-001",
                        }
                    ],
                }
            ],
        }
    }


def test_panel_density_graphic_and_exchange_matrix() -> None:
    """발화 40%, 비발화 60%, 상호 응답 50% 경계를 검증한다."""
    low_density = validate_panel_script_density(CHANNEL, panel_reactions(True), panel_script(20))
    assert "PANEL_SPOKEN_DENSITY_LOW" in issue_codes(low_density)
    assert (
        validate_panel_script_density(
            CHANNEL,
            panel_reactions(True),
            panel_script(50),
        )
        == []
    )

    no_exchange = validate_panel_design_realization(
        CHANNEL, panel_reactions(False), {"segments": []}
    )
    assert "PANEL_EXCHANGE_RATIO_LOW" in issue_codes(no_exchange)
    assert (
        validate_panel_design_realization(
            CHANNEL,
            panel_reactions(True),
            {"segments": []},
        )
        == []
    )

    graphic_heavy = issue_codes(
        explicit_crime_runtime_evidence_issues(CHANNEL, runtime_review(20, 35))
    )
    assert "PANEL_NON_SPEECH_RATIO_HIGH" in graphic_heavy
    assert "PANEL_FILLER_TIME_EXCESSIVE" in graphic_heavy
    assert explicit_crime_runtime_evidence_issues(CHANNEL, runtime_review(20, 10)) == []


def editorial_script(body: str) -> str:
    """Semantic Review Evidence용 단일 Segment Script를 만든다."""
    return (
        "<!-- SEGMENT:SEG-001 TYPE:NARRATION SCENE:SCN-01 DURATION:30 -->\n"
        f"{body}\n<!-- END_SEGMENT:SEG-001 -->"
    )


def semantic_review(
    contract: dict[str, object],
    artifacts: dict[str, object],
    scan_status: str,
) -> dict[str, object]:
    """한 Reveal Target의 조기 공개 판정을 선택한 Editorial Review를 만든다."""
    assessments: list[dict[str, object]] = []
    for index, (category, subject_id) in enumerate(
        sorted(required_semantic_subjects(CHANNEL, contract)),
        1,
    ):
        status = (
            scan_status
            if category == "PREMATURE_DISCLOSURE_SCAN" and subject_id == "REVEAL-TARGET-01"
            else "NOT_DISCLOSED"
            if category == "PREMATURE_DISCLOSURE_SCAN"
            else "EVIDENCED"
        )
        assessments.append(
            {
                "assessment_id": f"ASSESS-{index:02d}",
                "category": category,
                "subject_id": subject_id,
                "status": status,
                "evidence": [
                    make_editorial_evidence(
                        artifacts,
                        "final_script",
                        "SEGMENT_ID",
                        "SEG-001",
                    )
                ],
                "notes": "실제 Segment 발췌를 의미 검토했다.",
            }
        )
    return {"semantic_assessments": assessments}


@pytest.mark.parametrize(
    "body",
    (
        "첫 내레이션이 범인의 정체를 확정해 공개한다.",
        "첫 내레이션이 주요 인물의 결백을 확정해 공개한다.",
    ),
)
def test_unrecorded_early_disclosure_semantic_review_fails(body: str) -> None:
    """Metadata에 없는 조기 정답도 Semantic Critic의 실패 판정을 통과하지 못한다."""
    contract = event_contract()
    artifacts: dict[str, object] = {"final_script": editorial_script(body)}
    review = semantic_review(contract, artifacts, "PREMATURE_DISCLOSURE")
    assert "PREMATURE_DISCLOSURE_SCAN_FAILED" in issue_codes(
        validate_editorial_crime_assessments(CHANNEL, review, contract, artifacts)
    )


def test_planned_intentional_prereveal_passes_semantic_review() -> None:
    """Presentation과 Viewer에 함께 기록된 의도적 선공개는 통과한다."""
    contract = event_contract()
    artifacts: dict[str, object] = {
        "final_script": editorial_script("의도적으로 부분 단서를 먼저 보여 준다."),
        "presentation_plan": {
            "segments": [
                {
                    "segment_id": "SEG-001",
                    "intentional_prereveal_ids": ["REVEAL-TARGET-01"],
                }
            ]
        },
        "viewer_timeline": {
            "reveals": [
                {
                    "reveal_target_id": "REVEAL-TARGET-01",
                    "intentional_prereveal": True,
                }
            ]
        },
    }
    review = semantic_review(contract, artifacts, "INTENTIONAL_PREREVEAL")
    assert validate_editorial_crime_assessments(CHANNEL, review, contract, artifacts) == []


def test_projection_inactive_and_missing_targets_fail() -> None:
    """비활성 Capability Target과 최종 누락 Target을 조용히 건너뛰지 않는다."""
    production_config = {"variation_engine_version": "2.1.0"}
    variations = {
        "approved_candidate_id": "VAR-01",
        "candidates": [{"candidate_id": "VAR-01", "selection": {"motive_category": "CONTROL"}}],
    }
    inactive_contract = {
        "dimensions": {
            "motive_category": {
                "classification": "PROJECTED",
                "targets": [{"artifact": "crime_psychology", "json_path": "$.motive_category"}],
            }
        }
    }
    assert "CANDIDATE_PROJECTION_TARGET_INACTIVE" in issue_codes(
        validate_approved_candidate_projection(
            production_config,
            variations,
            inactive_contract,
            {},
            CHANNEL,
        )
    )

    missing_contract = {
        "dimensions": {
            "motive_category": {
                "classification": "PROJECTED",
                "targets": [{"artifact": "case_input", "json_path": "$.motive_category"}],
            }
        }
    }
    assert "CANDIDATE_PROJECTION_TARGET_MISSING" in issue_codes(
        validate_approved_candidate_projection(
            production_config,
            variations,
            missing_contract,
            {"final_script": "완성본"},
            CHANNEL,
        )
    )


def test_role_slot_cardinality_validator_rejects_duplicate_people() -> None:
    """Role Slot 수뿐 아니라 실제 Participant 수가 서로 달라야 한다."""
    brief = event_brief("VAR-01", 0)
    brief["responsible_agent_structure"] = "DUAL_AGENTS"
    brief["offender_role_slots"] = ["OFFENDER-01", "OFFENDER-02"]
    assert cardinality_issues(brief) == []
    contract, characters = participant_contract(
        "DUAL_AGENTS",
        ["CHAR-01", "CHAR-01"],
        "SINGLE_VICTIM",
        ["CHAR-90"],
    )
    assert "OFFENDER_CARDINALITY_MISMATCH" in issue_codes(
        validate_crime_role_bindings(contract, characters)
    )
