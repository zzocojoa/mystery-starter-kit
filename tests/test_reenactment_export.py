"""재연극 Export Report와 의미 결속 Validator 테스트."""

from copy import deepcopy
from hashlib import sha256
from pathlib import Path

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

from RUNTIME.screenplay_renderers import (
    render_broadcast_master,
    render_drama_layer,
    render_narration_layer,
    render_panel_layer,
    render_reenactment_character_script,
)
from VALIDATORS.io import load_json_object
from VALIDATORS.reenactment_export import (
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
    return contract


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
        characters,
        relationships,
        crime_contract,
        clues,
        profile,
        profile_sha256(),
        markdown,
        presentation_plan(),
        canonical_broadcast_master(),
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
        "estimated_minutes": None,
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

    report = build_reenactment_export_report(
        production_config(),
        screenplay,
        characters_document(),
        relationships_document(),
        crime_event_contract(),
        clue_matrix(),
        profile,
        profile_sha256(),
        markdown,
        presentation_plan(),
        broadcast,
    )

    assert "UNIT_RENDER_MISMATCH" in report_codes(report)


def test_output_mutation_after_report_creation_is_stale() -> None:
    """Report 생성 뒤 Markdown bytes가 바뀌면 기존 Hash를 써도 stale로 실패한다."""
    report, markdown = valid_report()
    mutated = markdown.replace("23:47 잠금 해제", "23:48 잠금 해제", 1)

    issues = validate_reenactment_export_report(
        report,
        production_config(),
        screenplay_document(),
        characters_document(),
        relationships_document(),
        crime_event_contract(),
        clue_matrix(),
        output_profile(),
        profile_sha256(),
        mutated,
        presentation_plan(),
        canonical_broadcast_master(),
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
        characters_document(),
        relationships_document(),
        crime_event_contract(),
        clue_matrix(),
        output_profile(),
        profile_sha256(),
        markdown,
        presentation_plan(),
        canonical_broadcast_master(),
    )

    assert {issue["code"] for issue in issues} == {"REENACTMENT_EXPORT_REPORT_STALE"}
