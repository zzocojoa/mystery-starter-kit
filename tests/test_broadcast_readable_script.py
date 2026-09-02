"""Canonical 사람용 Broadcast Artifact 추적 체인을 검증한다."""

from copy import deepcopy
from hashlib import sha256
from pathlib import Path

import pytest

from RUNTIME.broadcast_readable_renderer import render_broadcast_readable_script
from VALIDATORS.broadcast_readable import (
    build_broadcast_readable_report,
    production_broadcast_readable_copy_issues,
    validate_broadcast_readable_report,
)
from VALIDATORS.dependency import (
    artifact_hash,
    artifact_required_for_project,
    build_initial_project_state,
    invalidate_artifact_dependents,
)
from VALIDATORS.exceptions import ConfigurationError
from VALIDATORS.io import load_json_object
from VALIDATORS.output_profiles import resolve_broadcast_readable_output_profile
from VALIDATORS.schema_validation import collect_schema_errors

ROOT = Path(__file__).resolve().parents[1]
PILOT_ROOT = ROOT / "PROJECTS" / "PRJ-006"
FINAL_SCRIPT_SHA256 = "df995516ec1337de81b5b4aebc74cbd2af3c75a7a44393d851e768517749e602"


def pilot_documents() -> tuple[
    dict[str, object],
    dict[str, object],
    dict[str, object],
    dict[str, object],
    dict[str, object],
]:
    """PRJ-006의 Canonical JSON 다섯 개를 읽는다."""
    return (
        load_json_object(PILOT_ROOT / "07_SCRIPT" / "screenplay_units.json"),
        load_json_object(PILOT_ROOT / "02_CHARACTER" / "characters.json"),
        load_json_object(PILOT_ROOT / "06_SCENE" / "panel_cast.json"),
        load_json_object(PILOT_ROOT / "06_SCENE" / "reaction_segments.json"),
        load_json_object(PILOT_ROOT / "06_SCENE" / "presentation_plan.json"),
    )


def rendered_pilot() -> str:
    """PRJ-006 Canonical JSON에서 readable view를 렌더링한다."""
    screenplay, characters, panel_cast, reactions, plan = pilot_documents()
    _config, output_profile, _profile_hash = pilot_profile()
    return render_broadcast_readable_script(
        screenplay,
        characters,
        panel_cast,
        reactions,
        plan,
        output_profile,
    )


def pilot_profile() -> tuple[dict[str, object], dict[str, object], str]:
    """PRJ-006 Config로 Registry 검증된 Readable Profile을 읽는다."""
    config = load_json_object(PILOT_ROOT / "00_PROJECT" / "production_config.json")
    resolved = resolve_broadcast_readable_output_profile(ROOT, config)
    assert resolved is not None
    return config, resolved["document"], resolved["sha256"]


def mapping_list(document: dict[str, object], field: str) -> list[dict[str, object]]:
    """테스트 Mutation에 사용할 객체 배열을 엄격하게 읽는다."""
    value = document[field]
    assert isinstance(value, list)
    assert all(isinstance(item, dict) for item in value)
    return [item for item in value if isinstance(item, dict)]


def assert_texts_in_order(rendered: str, texts: list[str]) -> None:
    """동일 문자열의 반복을 포함해 모든 Text가 지정 순서로 나타나는지 확인한다."""
    cursor = 0
    for value in texts:
        position = rendered.find(value, cursor)
        assert position >= cursor
        cursor = position + len(value)


def test_readable_broadcast_is_deterministic_and_human_named() -> None:
    """Scene Context·실제 이름·Canonical Panel 발화를 순서대로 표시한다."""
    screenplay, characters, panel_cast, reactions, _plan = pilot_documents()
    rendered = rendered_pilot()

    assert rendered.encode("utf-8") == rendered_pilot().encode("utf-8")
    assert rendered.startswith("# 「폐장 음악이 멈춘 7분」 방송용 읽기 대본\n")
    assert "*[상황 설명: 장소 — " in rendered
    assert "이전 장면 — 장면 1. 멈춘 폐장 음악" in rendered
    assert "### 패널 반응" in rendered

    for character in mapping_list(characters, "characters"):
        name = character["name"]
        assert isinstance(name, str)
        assert f"| {name} |" in rendered
    for panelist in mapping_list(panel_cast, "panelists"):
        display_name = panelist["display_name"]
        assert isinstance(display_name, str)
        assert f"**{display_name}(패널)**" in rendered
    for reaction in mapping_list(reactions, "reaction_segments"):
        ordered_panel_lines: list[str] = []
        for turn in mapping_list(reaction, "turns"):
            spoken_line = turn["spoken_line"]
            assert isinstance(spoken_line, str)
            assert spoken_line in rendered
            ordered_panel_lines.append(spoken_line)
        assert_texts_in_order(rendered, ordered_panel_lines)
    ordered_unit_texts: list[str] = []
    for scene in mapping_list(screenplay, "scenes"):
        for unit in mapping_list(scene, "units"):
            text = unit["text"]
            assert isinstance(text, str)
            assert text in rendered
            ordered_unit_texts.append(text)
    assert_texts_in_order(rendered, ordered_unit_texts)

    assert rendered.count("### 패널 반응") == 7
    assert all(
        marker not in rendered
        for marker in (
            "<!-- SEGMENT:",
            "<!-- UNIT:",
            "CRIME_TRACE",
            "CHAR-",
            "PANEL-",
            "RSEG-",
            "SEG-",
            "SCN-",
            "[청취 불명확]",
            "[화자 불명확]",
        )
    )


def test_readable_broadcast_rejects_unknown_character_and_panelist() -> None:
    """실제 이름으로 해석할 수 없는 Speaker와 Panelist를 명시적으로 거부한다."""
    screenplay, characters, panel_cast, reactions, plan = pilot_documents()
    _config, output_profile, _profile_hash = pilot_profile()
    mutated_screenplay = deepcopy(screenplay)
    scenes = mapping_list(mutated_screenplay, "scenes")
    units = mapping_list(scenes[0], "units")
    dialogue = next(unit for unit in units if unit.get("type") == "DIALOGUE")
    dialogue["speaker_id"] = "CHAR-UNKNOWN"

    with pytest.raises(ConfigurationError, match="REENACTMENT_SPEAKER_UNKNOWN"):
        render_broadcast_readable_script(
            mutated_screenplay,
            characters,
            panel_cast,
            reactions,
            plan,
            output_profile,
        )

    mutated_reactions = deepcopy(reactions)
    reaction = mapping_list(mutated_reactions, "reaction_segments")[0]
    turn = mapping_list(reaction, "turns")[0]
    turn["panelist_id"] = "PANEL-UNKNOWN"

    with pytest.raises(ConfigurationError, match="BROADCAST_READABLE_PANELIST_UNKNOWN"):
        render_broadcast_readable_script(
            screenplay,
            characters,
            panel_cast,
            mutated_reactions,
            plan,
            output_profile,
        )


def test_readable_broadcast_rejects_scene_segment_drift() -> None:
    """Scene과 Presentation의 Segment 순서가 달라지면 stale view 생성을 막는다."""
    screenplay, characters, panel_cast, reactions, plan = pilot_documents()
    _config, output_profile, _profile_hash = pilot_profile()
    mutated_screenplay = deepcopy(screenplay)
    scene = mapping_list(mutated_screenplay, "scenes")[0]
    segment_ids = scene["segment_ids"]
    assert isinstance(segment_ids, list)
    scene["segment_ids"] = list(reversed(segment_ids))

    with pytest.raises(
        ConfigurationError,
        match="BROADCAST_READABLE_SCENE_SEGMENTS_MISMATCH",
    ):
        render_broadcast_readable_script(
            mutated_screenplay,
            characters,
            panel_cast,
            reactions,
            plan,
            output_profile,
        )


def test_readable_broadcast_rejects_canonical_project_mismatch() -> None:
    """서로 다른 Project의 Canonical JSON을 섞어 렌더링하지 않는다."""
    screenplay, characters, panel_cast, reactions, plan = pilot_documents()
    _config, output_profile, _profile_hash = pilot_profile()
    mutated_panel_cast = deepcopy(panel_cast)
    mutated_panel_cast["project_id"] = "PRJ-OTHER"

    with pytest.raises(ConfigurationError, match="BROADCAST_READABLE_PROJECT_MISMATCH"):
        render_broadcast_readable_script(
            screenplay,
            characters,
            mutated_panel_cast,
            reactions,
            plan,
            output_profile,
        )


def test_readable_report_binds_inputs_output_and_schema() -> None:
    """QA Report는 모든 입력과 출력 Hash 및 Coverage를 결정론적으로 결속한다."""
    screenplay, characters, panel_cast, reactions, plan = pilot_documents()
    config, output_profile, profile_hash = pilot_profile()
    rendered = rendered_pilot()
    report = build_broadcast_readable_report(
        config,
        screenplay,
        characters,
        panel_cast,
        reactions,
        plan,
        output_profile,
        profile_hash,
        rendered,
    )
    schema = load_json_object(
        ROOT / "STANDARD/schemas/broadcast_readable_report.schema.json"
    )

    assert collect_schema_errors(report, schema, "broadcast readable report") == []
    assert report["result"] == "PASS"
    assert report["output_profile"] == {
        "profile_id": "BROADCAST_READABLE_SCRIPT",
        "profile_version": "1.0.0",
        "sha256": profile_hash,
    }
    assert report["output_markdown_sha256"] == sha256(
        rendered.encode("utf-8")
    ).hexdigest()
    assert report["coverage"] == {
        "scene_count": 11,
        "unit_count": 95,
        "character_count": 6,
        "panelist_count": 3,
        "panel_reaction_segment_count": 7,
        "panel_turn_count": 14,
        "presentation_segment_count": 23,
    }
    assert report["source_style_evidence"] == {
        "ordering_source": "PRESENTATION_PLAN",
        "unit_text_policy": "CANONICAL_EXACT",
        "character_name_source": "CHARACTERS_NAME",
        "panel_name_source": "PANEL_CAST_DISPLAY_NAME",
        "scene_context_position": "BEFORE_SCENE_CONTENT",
        "internal_identifier_visibility": "HIDDEN",
        "scene_context_count": 11,
        "canonical_unit_count": 95,
        "character_row_count": 6,
        "panelist_row_count": 3,
        "panel_turn_count": 14,
        "forbidden_marker_matches": [],
    }


def test_readable_artifacts_are_not_required_for_legacy_mode() -> None:
    """Legacy Project에는 Canonical Readable Artifact 추측 생성을 요구하지 않는다."""
    graph = load_json_object(ROOT / "STANDARD/dependency_graph.json")
    definitions = graph["artifacts"]
    assert isinstance(definitions, dict)
    config = load_json_object(PILOT_ROOT / "00_PROJECT" / "production_config.json")
    config["script_source_mode"] = "LEGACY_MARKDOWN"
    channel: dict[str, object] = {"capabilities": {}}

    for artifact_name in (
        "broadcast_readable_script",
        "broadcast_readable_report",
        "production_broadcast_readable_script",
    ):
        definition = definitions[artifact_name]
        assert isinstance(definition, dict)
        assert not artifact_required_for_project(definition, channel, config, {})


def test_existing_broadcast_master_contract_and_bytes_are_unchanged() -> None:
    """Readable Artifact 등록은 기존 Master 계약과 Pilot Byte를 바꾸지 않는다."""
    contracts = load_json_object(ROOT / "RUNTIME" / "contracts" / "artifact_contracts.json")
    artifacts = contracts["artifacts"]
    assert isinstance(artifacts, dict)
    assert artifacts["final_script"] == {
        "media_type": "text/markdown",
        "schema": None,
        "validators": ["NON_EMPTY", "SCRIPT_INTEGRITY"],
        "commit_policy": "ATOMIC_ON_PASS",
        "max_bytes": 2097152,
    }
    assert artifacts["broadcast_readable_script"] == {
        "media_type": "text/markdown",
        "schema": None,
        "validators": ["NON_EMPTY"],
        "commit_policy": "ATOMIC_ON_PASS",
        "max_bytes": 2097152,
    }
    assert artifacts["broadcast_readable_report"]["schema"] == (
        "STANDARD/schemas/broadcast_readable_report.schema.json"
    )
    assert artifacts["production_broadcast_readable_script"]["commit_policy"] == (
        "ATOMIC_ON_PASS"
    )
    assert (
        sha256((PILOT_ROOT / "07_SCRIPT" / "final_script.md").read_bytes()).hexdigest()
        == FINAL_SCRIPT_SHA256
    )


def test_tracked_pilot_chain_matches_current_canonical_json() -> None:
    """Commit된 PRJ-006 View·QA Report·Production Copy가 Canonical 입력과 일치한다."""
    screenplay, characters, panel_cast, reactions, plan = pilot_documents()
    config, output_profile, profile_hash = pilot_profile()
    rendered = rendered_pilot()
    output_path = PILOT_ROOT / "07_SCRIPT" / "broadcast_readable_script.md"
    report_path = PILOT_ROOT / "08_QA" / "broadcast_readable_report.json"
    production_path = PILOT_ROOT / "09_PRODUCTION" / "broadcast_readable_script.md"

    assert output_path.read_bytes() == rendered.encode("utf-8")
    assert load_json_object(report_path) == build_broadcast_readable_report(
        config,
        screenplay,
        characters,
        panel_cast,
        reactions,
        plan,
        output_profile,
        profile_hash,
        rendered,
    )
    assert production_path.read_bytes() == output_path.read_bytes()


def test_stale_report_and_production_copy_are_rejected() -> None:
    """입력·Report·Production Copy 중 하나라도 바뀌면 추적 체인이 실패한다."""
    screenplay, characters, panel_cast, reactions, plan = pilot_documents()
    config, output_profile, profile_hash = pilot_profile()
    rendered = rendered_pilot()
    report = build_broadcast_readable_report(
        config,
        screenplay,
        characters,
        panel_cast,
        reactions,
        plan,
        output_profile,
        profile_hash,
        rendered,
    )
    stale_report = deepcopy(report)
    stale_report["output_markdown_sha256"] = "0" * 64

    issues = validate_broadcast_readable_report(
        stale_report,
        config,
        screenplay,
        characters,
        panel_cast,
        reactions,
        plan,
        output_profile,
        profile_hash,
        rendered,
    )

    assert {issue["code"] for issue in issues} == {"BROADCAST_READABLE_REPORT_STALE"}
    assert production_broadcast_readable_copy_issues(rendered, rendered) == []
    assert {
        issue["code"]
        for issue in production_broadcast_readable_copy_issues(
            rendered,
            f"{rendered}\n변조",
        )
    } == {"PRODUCTION_BROADCAST_READABLE_COPY_MISMATCH"}


def test_contract_chain_has_gate_owned_runtime_tasks() -> None:
    """Artifact 세 개가 Dependency와 GATE-08·09·13 Runtime Task에 결속된다."""
    graph = load_json_object(ROOT / "STANDARD/dependency_graph.json")
    tasks = load_json_object(ROOT / "RUNTIME/contracts/runtime_tasks.json")["tasks"]
    definitions = graph["artifacts"]
    assert isinstance(definitions, dict)
    assert isinstance(tasks, dict)

    assert definitions["broadcast_readable_script"]["owner_agent"] == "script_writer"
    assert definitions["broadcast_readable_report"]["depends_on"][-1] == (
        "broadcast_readable_script"
    )
    assert definitions["production_broadcast_readable_script"]["depends_on"] == [
        "production_config",
        "broadcast_readable_script",
        "broadcast_readable_report",
        "validation_report",
    ]
    expected = {
        "script.render_broadcast_readable": ("GATE-08", "broadcast_readable_script"),
        "continuity.validate_broadcast_readable": (
            "GATE-09",
            "broadcast_readable_report",
        ),
        "production.package_broadcast_readable": (
            "GATE-13",
            "production_broadcast_readable_script",
        ),
    }
    for task_id, (gate_id, output_name) in expected.items():
        task = tasks[task_id]
        assert task["executor"] == "CORE"
        assert task["target_gate"] == gate_id
        assert task["writes"] == [output_name]
        assert "production_config" in task["reads"]
        assert (
            "STANDARD/schemas/broadcast_readable_output_profile.schema.json"
            in task["standard_resources"]
        )


def test_output_profile_field_change_changes_rendered_bytes() -> None:
    """Profile 표시 규칙만 바꿔도 Task Catalog 수정 없이 출력 Byte가 달라진다."""
    screenplay, characters, panel_cast, reactions, plan = pilot_documents()
    _config, output_profile, _profile_hash = pilot_profile()
    changed_profile = deepcopy(output_profile)
    document_contract = changed_profile["document_contract"]
    assert isinstance(document_contract, dict)
    document_contract["title_template"] = "# {title} — 읽기용"

    rendered = render_broadcast_readable_script(
        screenplay,
        characters,
        panel_cast,
        reactions,
        plan,
        changed_profile,
    )

    assert rendered != rendered_pilot()
    assert rendered.startswith("# 폐장 음악이 멈춘 7분 — 읽기용\n")


def test_internal_identifier_leakage_is_rejected() -> None:
    """Canonical 가시 Text에 내부 식별자가 섞이면 사람용 출력 생성을 거부한다."""
    screenplay, characters, panel_cast, reactions, plan = pilot_documents()
    _config, output_profile, _profile_hash = pilot_profile()
    changed_screenplay = deepcopy(screenplay)
    first_scene = mapping_list(changed_screenplay, "scenes")[0]
    first_unit = mapping_list(first_scene, "units")[0]
    first_unit["text"] = "내부 참조 SCN-999가 노출되었다."

    with pytest.raises(
        ConfigurationError,
        match="BROADCAST_READABLE_FORBIDDEN_MARKER",
    ):
        render_broadcast_readable_script(
            changed_screenplay,
            characters,
            panel_cast,
            reactions,
            plan,
            output_profile,
        )


def test_profile_or_config_change_makes_report_stale() -> None:
    """Profile 문서와 Config Pin 결속 중 하나만 바뀌어도 기존 Report를 거부한다."""
    screenplay, characters, panel_cast, reactions, plan = pilot_documents()
    config, output_profile, profile_hash = pilot_profile()
    rendered = rendered_pilot()
    report = build_broadcast_readable_report(
        config,
        screenplay,
        characters,
        panel_cast,
        reactions,
        plan,
        output_profile,
        profile_hash,
        rendered,
    )
    changed_config = deepcopy(config)
    changed_config["broadcast_readable_output_profile_version"] = "1.0.1"

    issues = validate_broadcast_readable_report(
        report,
        changed_config,
        screenplay,
        characters,
        panel_cast,
        reactions,
        plan,
        output_profile,
        profile_hash,
        rendered,
    )

    assert "BROADCAST_READABLE_REPORT_STALE" in {
        issue["code"] for issue in issues
    }


def test_profile_pin_change_invalidates_entire_readable_chain() -> None:
    """Production Config Pin 변경은 Source·QA·Production·Editorial을 모두 무효화한다."""
    graph = load_json_object(ROOT / "STANDARD/dependency_graph.json")
    state = build_initial_project_state(graph, "PRJ-006", "2026-09-02T00:00:00Z")

    changed = invalidate_artifact_dependents(
        graph,
        state,
        "production_config",
        artifact_hash(b"readable-profile-pin-changed"),
        "2026-09-02T00:01:00Z",
    )

    for artifact_name in (
        "broadcast_readable_script",
        "broadcast_readable_report",
        "production_broadcast_readable_script",
        "editorial_review",
    ):
        assert changed["artifacts"][artifact_name]["status"] == "DIRTY"
