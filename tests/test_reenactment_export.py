"""재연극 Export Report와 의미 결속 Validator 테스트."""

from collections.abc import Mapping
from copy import deepcopy
from hashlib import sha256
from pathlib import Path
from typing import cast

import pytest
from jsonschema import Draft202012Validator
from test_screenplay_renderers import (
    characters_document,
    output_profile,
    presentation_plan,
    reaction_segments,
    relationships_document,
    screenplay_document,
)
from test_screenplay_renderers import (
    crime_event_contract as renderer_crime_event_contract,
)

from RUNTIME.core_tasks import screenplay_layer_outputs
from RUNTIME.errors import RuntimeExecutionError
from RUNTIME.screenplay_renderers import (
    render_broadcast_master,
    render_drama_layer,
    render_narration_layer,
    render_panel_layer,
    render_reenactment_character_script,
)
from VALIDATORS.io import load_json_object
from VALIDATORS.reenactment_export import (
    ScreenplayDerivedOutputs,
    build_reenactment_export_report,
    validate_reenactment_export_report,
)

ROOT = Path(__file__).resolve().parents[1]
PROFILE_PATH = (
    ROOT
    / "CHANNELS"
    / "mystery_main"
    / "output_profiles"
    / "reenactment-character-script"
    / "1.0.0.json"
)
REPORT_SCHEMA_PATH = ROOT / "STANDARD" / "schemas" / "reenactment_export_report.schema.json"


def production_config() -> dict[str, object]:
    """새 Screenplay Unit 경로의 최소 Production Config를 만든다."""
    return {
        "project_id": "PRJ-005",
        "script_source_mode": "SCREENPLAY_UNITS",
        "source_truth_classification": "ORIGINAL_FICTION",
        "reenactment_output_profile_id": "REENACTMENT_CHARACTER_SCRIPT",
        "reenactment_output_profile_version": "1.0.0",
        "target_runtime_minutes": 25,
        "runtime_tolerance_ratio": 0.1,
    }


def clue_matrix() -> dict[str, object]:
    """선행 Seed와 재구성 Reveal을 갖는 Clue Fixture를 만든다."""
    return {
        "schema_family": "clue-matrix",
        "schema_version": "1.1.0",
        "project_id": "PRJ-005",
        "clues": [
            {
                "clue_id": "CLUE-01",
                "reveal_mode": "SEEDED_REINTERPRETATION",
                "surface_meaning": "경보는 침입이 끝난 뒤 울렸다.",
                "actual_meaning": "경보는 공범이 잠금을 해제하라는 신호였다.",
                "first_seen_scene_id": "SCN-001",
                "reveal_scene_id": "SCN-002",
                "recontextualized_scene_ids": ["SCN-001"],
            }
        ],
    }


def crime_event_contract() -> dict[str, object]:
    """두 Harm을 명시한 Export Coverage용 Crime Contract를 만든다."""
    contract = renderer_crime_event_contract()
    contract["harm_ids"] = ["HARM-01", "HARM-02"]
    contract["development_functions"] = [
        {"development_function_id": "CDEV-001", "required": True}
    ]
    contract["reveal_targets"] = [{"reveal_target_id": "REVEAL-TARGET-01"}]
    return contract


def facts_document() -> dict[str, object]:
    """Screenplay 참조를 해석할 Canonical Fact Fixture를 만든다."""
    return {
        "project_id": "PRJ-005",
        "facts": [
            {
                "fact_id": "FACT-01",
                "statement": "경보는 잠금 해제 직후 울렸다.",
            }
        ],
    }


def profile_sha256() -> str:
    """Registry가 고정한 Output Profile 원본 bytes Hash를 반환한다."""
    return sha256(PROFILE_PATH.read_bytes()).hexdigest()


def rendered_markdown(
    screenplay: dict[str, object],
    characters: dict[str, object],
    relationships: dict[str, object],
    profile: dict[str, object],
) -> str:
    """Report 대상 Canonical 재연극 Markdown을 만든다."""
    return render_reenactment_character_script(
        screenplay,
        characters,
        relationships,
        profile,
    )


def canonical_broadcast_master() -> str:
    """Unit-derived Trace를 포함하는 정상 Broadcast Master를 만든다."""
    screenplay = screenplay_document()
    plan = presentation_plan()
    contract = crime_event_contract()
    return render_broadcast_master(
        plan,
        {
            "drama_script": render_drama_layer(screenplay, plan, contract),
            "narration_script": render_narration_layer(screenplay, plan, contract),
            "panel_reaction_script": render_panel_layer(reaction_segments(), plan),
        },
    )


def canonical_derived_outputs(reenactment_markdown: str) -> ScreenplayDerivedOutputs:
    """정상 Unit·Reaction 입력의 모든 결정론적 출력 Fixture를 만든다."""
    screenplay = screenplay_document()
    plan = presentation_plan()
    contract = crime_event_contract()
    drama = render_drama_layer(screenplay, plan, contract)
    narration = render_narration_layer(screenplay, plan, contract)
    panel = render_panel_layer(reaction_segments(), plan)
    master = render_broadcast_master(
        plan,
        {
            "drama_script": drama,
            "narration_script": narration,
            "panel_reaction_script": panel,
        },
    )
    return ScreenplayDerivedOutputs(
        drama_script=drama,
        narration_script=narration,
        panel_reaction_script=panel,
        draft_script=master,
        final_script=master,
        reenactment_character_script=reenactment_markdown,
    )


def build_report(
    screenplay: dict[str, object],
    characters: dict[str, object],
    relationships: dict[str, object],
    crime_contract: dict[str, object],
    clues: dict[str, object],
    profile: dict[str, object],
    markdown: str,
) -> dict[str, object]:
    """공통 Fixture에서 Export Report를 만든다."""
    return build_reenactment_export_report(
        production_config(),
        screenplay,
        facts_document(),
        characters,
        relationships,
        crime_contract,
        clues,
        profile,
        profile_sha256(),
        presentation_plan(),
        reaction_segments(),
        canonical_derived_outputs(markdown),
    )


def build_report_with_sources(
    screenplay: dict[str, object],
    facts: dict[str, object],
    characters: dict[str, object],
    relationships: dict[str, object],
    crime_contract: dict[str, object],
    clues: dict[str, object],
    profile: dict[str, object],
    plan: dict[str, object],
    reactions: dict[str, object],
    outputs: ScreenplayDerivedOutputs,
) -> dict[str, object]:
    """지정한 현재 입력·출력 전체에서 Export Report를 만든다."""
    return build_reenactment_export_report(
        production_config(),
        screenplay,
        facts,
        characters,
        relationships,
        crime_contract,
        clues,
        profile,
        profile_sha256(),
        plan,
        reactions,
        outputs,
    )


def report_codes(report: dict[str, object]) -> set[str]:
    """Report Issue code 집합을 반환한다."""
    issues = report["issues"]
    assert isinstance(issues, list)
    return {
        str(issue["code"])
        for issue in issues
        if isinstance(issue, dict) and isinstance(issue.get("code"), str)
    }


def valid_report() -> tuple[dict[str, object], str]:
    """정상 입력의 NEEDS_REVIEW Report와 Markdown을 만든다."""
    screenplay = screenplay_document()
    characters = characters_document()
    relationships = relationships_document()
    profile = output_profile()
    markdown = rendered_markdown(screenplay, characters, relationships, profile)
    return (
        build_report(
            screenplay,
            characters,
            relationships,
            crime_event_contract(),
            clue_matrix(),
            profile,
            markdown,
        ),
        markdown,
    )


def test_valid_export_report_is_schema_valid_and_never_claims_editorial_pass() -> None:
    """정상 Report는 증거를 완성하되 Editorial PASS를 선언하지 않는다."""
    report, _markdown = valid_report()
    validator = Draft202012Validator(load_json_object(REPORT_SCHEMA_PATH))

    assert sorted(validator.iter_errors(report), key=lambda error: list(error.path)) == []
    assert report["result"] == "NEEDS_REVIEW"
    assert report["issues"] == []
    assert report["runtime_status"] == {
        "target_minutes": None,
        "tolerance_ratio": None,
        "planning_basis": "PRESENTATION_PLAN_INCLUDED_SEGMENTS",
        "included_segment_ids": ["SEG-001", "SEG-002", "SEG-004"],
        "excluded_segment_ids": ["SEG-003"],
        "planned_duration_sec": 100.0,
        "estimated_minutes": 1.666667,
        "measured_minutes": None,
        "status": "NOT_CONFIGURED",
    }
    unit_coverage = report["unit_coverage"]
    harm_coverage = report["harm_coverage"]
    clue_coverage = report["clue_reveal_coverage"]
    assert isinstance(unit_coverage, dict)
    assert isinstance(harm_coverage, dict)
    assert isinstance(clue_coverage, dict)
    assert unit_coverage["missing_ids"] == []
    assert harm_coverage["rendered_ids"] == ["HARM-01", "HARM-02"]
    assert clue_coverage["rendered_ids"] == ["CLUE-01"]


def test_unknown_speaker_cannot_be_hidden_by_old_markdown() -> None:
    """Unit speaker_id 변경은 기존 가시 문구가 남아 있어도 실패한다."""
    screenplay = screenplay_document()
    scenes = screenplay["scenes"]
    assert isinstance(scenes, list)
    first_scene = scenes[0]
    assert isinstance(first_scene, dict)
    units = first_scene["units"]
    assert isinstance(units, list)
    dialogue = units[2]
    assert isinstance(dialogue, dict)
    dialogue["speaker_id"] = "CHAR-999"
    profile = output_profile()
    markdown = rendered_markdown(
        screenplay_document(),
        characters_document(),
        relationships_document(),
        profile,
    )

    report = build_report(
        screenplay,
        characters_document(),
        relationships_document(),
        crime_event_contract(),
        clue_matrix(),
        profile,
        markdown,
    )

    assert report["result"] == "FAIL"
    assert "REENACTMENT_SPEAKER_UNKNOWN" in report_codes(report)


def test_unit_text_and_order_mutations_fail_exact_render_binding() -> None:
    """Unit text나 order를 바꾸고 이전 Markdown을 쓰면 무결성 검증이 실패한다."""
    original = screenplay_document()
    profile = output_profile()
    markdown = rendered_markdown(
        original,
        characters_document(),
        relationships_document(),
        profile,
    )
    changed_text = deepcopy(original)
    changed_scenes = changed_text["scenes"]
    assert isinstance(changed_scenes, list)
    changed_scene = changed_scenes[0]
    assert isinstance(changed_scene, dict)
    changed_units = changed_scene["units"]
    assert isinstance(changed_units, list)
    changed_unit = changed_units[0]
    assert isinstance(changed_unit, dict)
    changed_unit["text"] = "조작된 Unit text"

    text_report = build_report(
        changed_text,
        characters_document(),
        relationships_document(),
        crime_event_contract(),
        clue_matrix(),
        profile,
        markdown,
    )
    changed_order = deepcopy(original)
    order_scenes = changed_order["scenes"]
    assert isinstance(order_scenes, list)
    order_scene = order_scenes[0]
    assert isinstance(order_scene, dict)
    order_units = order_scene["units"]
    assert isinstance(order_units, list)
    first = order_units[0]
    second = order_units[1]
    assert isinstance(first, dict)
    assert isinstance(second, dict)
    first["order"] = 2
    second["order"] = 1
    order_report = build_report(
        changed_order,
        characters_document(),
        relationships_document(),
        crime_event_contract(),
        clue_matrix(),
        profile,
        markdown,
    )

    assert "UNIT_RENDER_MISMATCH" in report_codes(text_report)
    assert "REENACTMENT_UNIT_ORDER_INVALID" in report_codes(order_report)


def test_internal_trace_and_uncertainty_marker_leakage_fail() -> None:
    """방송 Trace와 Original Fiction 불명확 Marker를 추가하면 실패한다."""
    screenplay = screenplay_document()
    profile = output_profile()
    markdown = rendered_markdown(
        screenplay,
        characters_document(),
        relationships_document(),
        profile,
    )
    leaked = markdown + "<!-- CRIME_TRACE\nEVENT=EVENT-01\n-->\n[화자 불명확]\n"

    report = build_report(
        screenplay,
        characters_document(),
        relationships_document(),
        crime_event_contract(),
        clue_matrix(),
        profile,
        leaked,
    )

    assert {
        "INTERNAL_MARKER_LEAKED",
        "ORIGINAL_FICTION_UNCLEAR_MARKER",
        "UNIT_RENDER_MISMATCH",
    }.issubset(report_codes(report))


def test_panel_content_and_duplicate_unit_block_fail() -> None:
    """Panel 발화 유입과 Unit Block 중복은 profile coverage를 위반한다."""
    screenplay = screenplay_document()
    profile = output_profile()
    markdown = rendered_markdown(
        screenplay,
        characters_document(),
        relationships_document(),
        profile,
    )
    dialogue = "지안: 이 소리는 문이 열린 뒤에만 나요.\n\n"
    leaked = markdown.replace(
        dialogue,
        dialogue + "[PANEL-01] 경보의 순서를 다시 봐야 합니다.\n\n" + dialogue,
        1,
    )

    report = build_report(
        screenplay,
        characters_document(),
        relationships_document(),
        crime_event_contract(),
        clue_matrix(),
        profile,
        leaked,
    )
    unit_coverage = report["unit_coverage"]
    assert isinstance(unit_coverage, dict)

    assert "PANEL_CONTENT_IN_REENACTMENT_EXPORT" in report_codes(report)
    assert unit_coverage["duplicate_ids"] == ["UNIT-003"]


def test_profile_filter_mutation_and_special_unit_loss_fail() -> None:
    """Profile 포함 규칙 변경이나 특수 Unit 삭제는 이전 Markdown과 일치할 수 없다."""
    screenplay = screenplay_document()
    profile = output_profile()
    markdown = rendered_markdown(
        screenplay,
        characters_document(),
        relationships_document(),
        profile,
    )
    changed_profile = deepcopy(profile)
    filter_contract = changed_profile["filter_contract"]
    assert isinstance(filter_contract, dict)
    included = filter_contract["included_unit_types"]
    excluded = filter_contract["excluded_unit_types"]
    assert isinstance(included, list)
    assert isinstance(excluded, list)
    included.remove("MESSAGE")
    excluded.append("MESSAGE")
    profile_report = build_report(
        screenplay,
        characters_document(),
        relationships_document(),
        crime_event_contract(),
        clue_matrix(),
        changed_profile,
        markdown,
    )
    message_line = "[메시지] 민호: 기록실에서 기다려.\n\n"
    lost_markdown = markdown.replace(message_line, "", 1)
    lost_report = build_report(
        screenplay,
        characters_document(),
        relationships_document(),
        crime_event_contract(),
        clue_matrix(),
        profile,
        lost_markdown,
    )

    assert "UNIT_RENDER_MISMATCH" in report_codes(profile_report)
    assert "SPECIAL_UNIT_TYPE_LOST" in report_codes(lost_report)


def test_harm_and_clue_reference_mutations_fail_semantic_coverage() -> None:
    """가시 Unit의 Harm이나 Seed/Reveal Clue 참조를 제거하면 실패한다."""
    profile = output_profile()
    original = screenplay_document()
    markdown = rendered_markdown(
        original,
        characters_document(),
        relationships_document(),
        profile,
    )
    harm_changed = deepcopy(original)
    harm_scenes = harm_changed["scenes"]
    assert isinstance(harm_scenes, list)
    for scene in harm_scenes:
        assert isinstance(scene, dict)
        units = scene["units"]
        assert isinstance(units, list)
        for unit in units:
            assert isinstance(unit, dict)
            references = unit["references"]
            assert isinstance(references, dict)
            harm_ids = references["harm_ids"]
            assert isinstance(harm_ids, list)
            references["harm_ids"] = [harm_id for harm_id in harm_ids if harm_id != "HARM-02"]
    harm_report = build_report(
        harm_changed,
        characters_document(),
        relationships_document(),
        crime_event_contract(),
        clue_matrix(),
        profile,
        markdown,
    )
    clue_changed = deepcopy(original)
    clue_scenes = clue_changed["scenes"]
    assert isinstance(clue_scenes, list)
    reveal_scene = clue_scenes[1]
    assert isinstance(reveal_scene, dict)
    reveal_units = reveal_scene["units"]
    assert isinstance(reveal_units, list)
    for unit in reveal_units:
        assert isinstance(unit, dict)
        references = unit["references"]
        assert isinstance(references, dict)
        references["clue_ids"] = []
    clue_report = build_report(
        clue_changed,
        characters_document(),
        relationships_document(),
        crime_event_contract(),
        clue_matrix(),
        profile,
        markdown,
    )

    assert "HARM_REALIZATION_MISSING" in report_codes(harm_report)
    assert "REVEAL_WITHOUT_PRIOR_SEED" in report_codes(clue_report)


def test_retrospective_meaning_and_reconstruction_reference_are_required() -> None:
    """Reveal 회고 의미와 선행 Reconstruction 결속을 Metadata만으로 대신할 수 없다."""
    profile = output_profile()
    original = screenplay_document()
    markdown = rendered_markdown(
        original,
        characters_document(),
        relationships_document(),
        profile,
    )
    changed = deepcopy(original)
    scenes = changed["scenes"]
    assert isinstance(scenes, list)
    reconstruction = scenes[1]
    assert isinstance(reconstruction, dict)
    context = reconstruction["context"]
    assert isinstance(context, dict)
    context.pop("retrospective_meaning")
    reconstruction["reconstruction_of_scene_id"] = "SCN-999"

    report = build_report(
        changed,
        characters_document(),
        relationships_document(),
        crime_event_contract(),
        clue_matrix(),
        profile,
        markdown,
    )

    assert {
        "RETROSPECTIVE_MEANING_MISSING",
        "RECONSTRUCTION_REFERENCE_INVALID",
    }.issubset(report_codes(report))


def test_broadcast_hidden_trace_mutation_fails_unit_reference_binding() -> None:
    """Broadcast CRIME_TRACE만 조작해도 가시 Unit References 재계산과 달라 실패한다."""
    screenplay = screenplay_document()
    profile = output_profile()
    markdown = rendered_markdown(
        screenplay,
        characters_document(),
        relationships_document(),
        profile,
    )
    broadcast = canonical_broadcast_master().replace(
        "HARM=HARM-01,HARM-02",
        "HARM=HARM-01",
        1,
    )
    outputs = canonical_derived_outputs(markdown)
    outputs["final_script"] = broadcast

    report = build_reenactment_export_report(
        production_config(),
        screenplay,
        facts_document(),
        characters_document(),
        relationships_document(),
        crime_event_contract(),
        clue_matrix(),
        profile,
        profile_sha256(),
        presentation_plan(),
        reaction_segments(),
        outputs,
    )

    assert "UNIT_RENDER_MISMATCH" in report_codes(report)


@pytest.mark.parametrize(
    ("artifact_name", "expected_code"),
    (
        ("drama_script", "DRAMA_LAYER_RENDER_MISMATCH"),
        ("narration_script", "NARRATION_LAYER_RENDER_MISMATCH"),
        ("panel_reaction_script", "PANEL_LAYER_RENDER_MISMATCH"),
    ),
)
def test_visible_layer_mutation_fails_with_exact_hash_evidence(
    artifact_name: str,
    expected_code: str,
) -> None:
    """Trace ID를 보존한 가시 Layer 변조도 기대 bytes 비교에서 실패한다."""
    screenplay = screenplay_document()
    characters = characters_document()
    relationships = relationships_document()
    profile = output_profile()
    markdown = rendered_markdown(screenplay, characters, relationships, profile)
    canonical_outputs = canonical_derived_outputs(markdown)
    mutable_outputs: dict[str, str] = {
        "drama_script": canonical_outputs["drama_script"],
        "narration_script": canonical_outputs["narration_script"],
        "panel_reaction_script": canonical_outputs["panel_reaction_script"],
        "draft_script": canonical_outputs["draft_script"],
        "final_script": canonical_outputs["final_script"],
        "reenactment_character_script": canonical_outputs[
            "reenactment_character_script"
        ],
    }
    mutable_outputs[artifact_name] += "가시 문구 변조\n"

    report = build_report_with_sources(
        screenplay,
        facts_document(),
        characters,
        relationships,
        crime_event_contract(),
        clue_matrix(),
        profile,
        presentation_plan(),
        reaction_segments(),
        cast(ScreenplayDerivedOutputs, mutable_outputs),
    )
    issues = report["issues"]
    assert isinstance(issues, list)
    matching = [
        issue
        for issue in issues
        if isinstance(issue, dict) and issue.get("code") == expected_code
    ]

    assert len(matching) == 1
    context = matching[0]["context"]
    assert isinstance(context, dict)
    assert context["affected_artifact"]
    assert len(str(context["expected_sha256"])) == 64
    assert len(str(context["actual_sha256"])) == 64
    assert context["expected_sha256"] != context["actual_sha256"]


def test_mutating_layer_and_final_together_cannot_redefine_expected_output() -> None:
    """Layer와 Final을 같은 문구로 함께 바꿔도 현재 원본 재렌더 결과와 모두 다르다."""
    screenplay = screenplay_document()
    characters = characters_document()
    relationships = relationships_document()
    profile = output_profile()
    markdown = rendered_markdown(screenplay, characters, relationships, profile)
    outputs = canonical_derived_outputs(markdown)
    outputs["drama_script"] += "공동 변조\n"
    outputs["final_script"] += "공동 변조\n"

    report = build_report_with_sources(
        screenplay,
        facts_document(),
        characters,
        relationships,
        crime_event_contract(),
        clue_matrix(),
        profile,
        presentation_plan(),
        reaction_segments(),
        outputs,
    )

    assert {
        "DRAMA_LAYER_RENDER_MISMATCH",
        "BROADCAST_MASTER_RENDER_MISMATCH",
    }.issubset(report_codes(report))


def test_final_only_mutation_fails_broadcast_master_binding() -> None:
    """Final만 바꿔도 Draft와 무관하게 현재 Master bytes 결속이 실패한다."""
    screenplay = screenplay_document()
    characters = characters_document()
    relationships = relationships_document()
    profile = output_profile()
    markdown = rendered_markdown(screenplay, characters, relationships, profile)
    outputs = canonical_derived_outputs(markdown)
    outputs["final_script"] += "Final 단독 변조\n"

    report = build_report_with_sources(
        screenplay,
        facts_document(),
        characters,
        relationships,
        crime_event_contract(),
        clue_matrix(),
        profile,
        presentation_plan(),
        reaction_segments(),
        outputs,
    )

    assert "BROADCAST_MASTER_RENDER_MISMATCH" in report_codes(report)


def test_unit_source_mutation_invalidates_old_layers_masters_export_and_report() -> None:
    """Unit 원문 변경 뒤 이전 출력과 Report를 재사용하면 모든 하위 결속이 실패한다."""
    original = screenplay_document()
    characters = characters_document()
    relationships = relationships_document()
    profile = output_profile()
    markdown = rendered_markdown(original, characters, relationships, profile)
    outputs = canonical_derived_outputs(markdown)
    old_report = build_report_with_sources(
        original,
        facts_document(),
        characters,
        relationships,
        crime_event_contract(),
        clue_matrix(),
        profile,
        presentation_plan(),
        reaction_segments(),
        outputs,
    )
    changed = deepcopy(original)
    scenes = changed["scenes"]
    assert isinstance(scenes, list)
    scene = scenes[0]
    assert isinstance(scene, dict)
    units = scene["units"]
    assert isinstance(units, list)
    first_unit = units[0]
    assert isinstance(first_unit, dict)
    first_unit["text"] = "현재 입력에서 바뀐 가시 행동"

    issues = validate_reenactment_export_report(
        old_report,
        production_config(),
        changed,
        facts_document(),
        characters,
        relationships,
        crime_event_contract(),
        clue_matrix(),
        profile,
        profile_sha256(),
        presentation_plan(),
        reaction_segments(),
        outputs,
    )
    codes = {issue["code"] for issue in issues}

    assert {
        "DRAMA_LAYER_RENDER_MISMATCH",
        "BROADCAST_MASTER_RENDER_MISMATCH",
        "UNIT_RENDER_MISMATCH",
        "REENACTMENT_EXPORT_REPORT_STALE",
    }.issubset(codes)


def test_reaction_source_mutation_invalidates_old_panel_and_master() -> None:
    """Reaction Contract 변경 뒤 이전 Panel과 Master 출력은 재사용할 수 없다."""
    screenplay = screenplay_document()
    characters = characters_document()
    relationships = relationships_document()
    profile = output_profile()
    markdown = rendered_markdown(screenplay, characters, relationships, profile)
    outputs = canonical_derived_outputs(markdown)
    reactions = reaction_segments()
    records = reactions["reaction_segments"]
    assert isinstance(records, list)
    record = records[0]
    assert isinstance(record, dict)
    turns = record["turns"]
    assert isinstance(turns, list)
    turn = turns[0]
    assert isinstance(turn, dict)
    turn["spoken_line"] = "현재 증거 순서를 다시 검증해야 합니다."

    report = build_report_with_sources(
        screenplay,
        facts_document(),
        characters,
        relationships,
        crime_event_contract(),
        clue_matrix(),
        profile,
        presentation_plan(),
        reactions,
        outputs,
    )

    assert {
        "PANEL_LAYER_RENDER_MISMATCH",
        "BROADCAST_MASTER_RENDER_MISMATCH",
    }.issubset(report_codes(report))


def test_profile_mutation_invalidates_old_reenactment_output_and_report_hash() -> None:
    """Profile 의미 변경은 기존 Export bytes와 기존 Report 신선도를 함께 무효화한다."""
    screenplay = screenplay_document()
    characters = characters_document()
    relationships = relationships_document()
    profile = output_profile()
    markdown = rendered_markdown(screenplay, characters, relationships, profile)
    outputs = canonical_derived_outputs(markdown)
    old_report = build_report_with_sources(
        screenplay,
        facts_document(),
        characters,
        relationships,
        crime_event_contract(),
        clue_matrix(),
        profile,
        presentation_plan(),
        reaction_segments(),
        outputs,
    )
    changed_profile = deepcopy(profile)
    render_contract = changed_profile["render_contract"]
    assert isinstance(render_contract, dict)
    labels = render_contract["special_unit_labels"]
    assert isinstance(labels, dict)
    labels["SCREEN_TEXT"] = "스크린 자막"

    issues = validate_reenactment_export_report(
        old_report,
        production_config(),
        screenplay,
        facts_document(),
        characters,
        relationships,
        crime_event_contract(),
        clue_matrix(),
        changed_profile,
        profile_sha256(),
        presentation_plan(),
        reaction_segments(),
        outputs,
    )
    codes = {issue["code"] for issue in issues}

    assert {"UNIT_RENDER_MISMATCH", "REENACTMENT_EXPORT_REPORT_STALE"}.issubset(codes)


def test_profile_version_only_change_alters_bytes_hash_and_stale_detection() -> None:
    """동일 계약의 후속 Profile Version도 출력 bytes와 Report 결속을 바꾼다."""
    screenplay = screenplay_document()
    characters = characters_document()
    relationships = relationships_document()
    profile = output_profile()
    markdown = rendered_markdown(screenplay, characters, relationships, profile)
    outputs = canonical_derived_outputs(markdown)
    old_report = build_report_with_sources(
        screenplay,
        facts_document(),
        characters,
        relationships,
        crime_event_contract(),
        clue_matrix(),
        profile,
        presentation_plan(),
        reaction_segments(),
        outputs,
    )
    later_profile = deepcopy(profile)
    later_profile["profile_version"] = "1.1.0"
    later_markdown = rendered_markdown(
        screenplay,
        characters,
        relationships,
        later_profile,
    )

    issues = validate_reenactment_export_report(
        old_report,
        production_config(),
        screenplay,
        facts_document(),
        characters,
        relationships,
        crime_event_contract(),
        clue_matrix(),
        later_profile,
        "1" * 64,
        presentation_plan(),
        reaction_segments(),
        outputs,
    )

    assert sha256(markdown.encode("utf-8")).hexdigest() != sha256(
        later_markdown.encode("utf-8")
    ).hexdigest()
    assert {"UNIT_RENDER_MISMATCH", "REENACTMENT_EXPORT_REPORT_STALE"}.issubset(
        {issue["code"] for issue in issues}
    )


@pytest.mark.parametrize(
    ("reference_field", "expected_code"),
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
def test_core_render_rejects_every_unknown_reference_before_rendering(
    reference_field: str,
    expected_code: str,
) -> None:
    """CORE Renderer는 모든 상위 참조 Family를 Layer 생성 전에 거부한다."""
    screenplay = screenplay_document()
    scenes = screenplay["scenes"]
    assert isinstance(scenes, list)
    scene = scenes[0]
    assert isinstance(scene, dict)
    units = scene["units"]
    assert isinstance(units, list)
    unit = units[0]
    assert isinstance(unit, dict)
    references = unit["references"]
    assert isinstance(references, dict)
    references[reference_field] = ["UNKNOWN-99"]
    artifacts: dict[str, Mapping[str, object] | str] = {
        "screenplay_units": screenplay,
        "facts": facts_document(),
        "clue_matrix": clue_matrix(),
        "characters": characters_document(),
        "crime_event_contract": crime_event_contract(),
        "presentation_plan": presentation_plan(),
        "reaction_segments": reaction_segments(),
    }

    with pytest.raises(RuntimeExecutionError) as error_info:
        screenplay_layer_outputs(
            "script.render_screenplay_layers",
            ROOT,
            production_config(),
            artifacts,
        )

    assert error_info.value.code == "GATE_REJECTED"
    assert error_info.value.safe_context["validation_code"] == expected_code


def test_output_mutation_after_report_creation_is_stale() -> None:
    """Report 생성 뒤 Markdown bytes가 바뀌면 기존 Hash를 써도 stale로 실패한다."""
    report, markdown = valid_report()
    mutated = markdown.replace("23:47 잠금 해제", "23:48 잠금 해제", 1)
    outputs = canonical_derived_outputs(markdown)
    outputs["reenactment_character_script"] = mutated

    issues = validate_reenactment_export_report(
        report,
        production_config(),
        screenplay_document(),
        facts_document(),
        characters_document(),
        relationships_document(),
        crime_event_contract(),
        clue_matrix(),
        output_profile(),
        profile_sha256(),
        presentation_plan(),
        reaction_segments(),
        outputs,
    )
    codes = {issue["code"] for issue in issues}

    assert "UNIT_RENDER_MISMATCH" in codes
    assert "REENACTMENT_EXPORT_REPORT_STALE" in codes


def test_metadata_only_spoof_cannot_pass_rebuilt_report_comparison() -> None:
    """Evidence 배열이나 result만 고친 Report는 재구성 비교를 통과하지 못한다."""
    report, markdown = valid_report()
    spoofed = deepcopy(report)
    spoofed["result"] = "FAIL"
    spoofed["issues"] = [
        {
            "severity": "INFO",
            "code": "SPOOFED_EVIDENCE",
            "message": "본문을 검사하지 않은 임의 Metadata",
            "artifact": "08_QA/reenactment_export_report.json",
            "context": {},
        }
    ]

    issues = validate_reenactment_export_report(
        spoofed,
        production_config(),
        screenplay_document(),
        facts_document(),
        characters_document(),
        relationships_document(),
        crime_event_contract(),
        clue_matrix(),
        output_profile(),
        profile_sha256(),
        presentation_plan(),
        reaction_segments(),
        canonical_derived_outputs(markdown),
    )

    assert {issue["code"] for issue in issues} == {"REENACTMENT_EXPORT_REPORT_STALE"}
