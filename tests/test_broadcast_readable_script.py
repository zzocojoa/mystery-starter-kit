"""사람용 Broadcast companion view의 결정성과 불변 경계를 검증한다."""

from copy import deepcopy
from hashlib import sha256
from pathlib import Path

import pytest

from RUNTIME.broadcast_readable_renderer import render_broadcast_readable_script
from VALIDATORS.exceptions import ConfigurationError
from VALIDATORS.io import load_json_object, write_json_object
from VALIDATORS.production_cli import run_cli

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
    return render_broadcast_readable_script(
        screenplay,
        characters,
        panel_cast,
        reactions,
        plan,
    )


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
        )


def test_readable_broadcast_rejects_scene_segment_drift() -> None:
    """Scene과 Presentation의 Segment 순서가 달라지면 stale view 생성을 막는다."""
    screenplay, characters, panel_cast, reactions, plan = pilot_documents()
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
        )


def test_readable_broadcast_rejects_canonical_project_mismatch() -> None:
    """서로 다른 Project의 Canonical JSON을 섞어 렌더링하지 않는다."""
    screenplay, characters, panel_cast, reactions, plan = pilot_documents()
    mutated_panel_cast = deepcopy(panel_cast)
    mutated_panel_cast["project_id"] = "PRJ-OTHER"

    with pytest.raises(ConfigurationError, match="BROADCAST_READABLE_PROJECT_MISMATCH"):
        render_broadcast_readable_script(
            screenplay,
            characters,
            mutated_panel_cast,
            reactions,
            plan,
        )


def test_cli_writes_only_fixed_readable_view_and_preserves_master(
    tmp_path: Path,
) -> None:
    """CLI 반복 실행은 동일 View만 쓰고 기존 Broadcast Master Byte를 보존한다."""
    project_path = tmp_path / "PRJ-006"
    screenplay, characters, panel_cast, reactions, plan = pilot_documents()
    config = load_json_object(PILOT_ROOT / "00_PROJECT" / "production_config.json")
    inputs = {
        "00_PROJECT/production_config.json": config,
        "07_SCRIPT/screenplay_units.json": screenplay,
        "02_CHARACTER/characters.json": characters,
        "06_SCENE/panel_cast.json": panel_cast,
        "06_SCENE/reaction_segments.json": reactions,
        "06_SCENE/presentation_plan.json": plan,
    }
    for relative_path, document in inputs.items():
        write_json_object(project_path / relative_path, document)
    final_script_path = project_path / "07_SCRIPT" / "final_script.md"
    final_script_path.parent.mkdir(parents=True, exist_ok=True)
    final_script_bytes = (PILOT_ROOT / "07_SCRIPT" / "final_script.md").read_bytes()
    final_script_path.write_bytes(final_script_bytes)

    assert run_cli(["render-broadcast-readable", str(project_path)]) == 0
    output_path = project_path / "07_SCRIPT" / "broadcast_readable_script.md"
    first_output = output_path.read_bytes()
    assert first_output == rendered_pilot().encode("utf-8")
    assert final_script_path.read_bytes() == final_script_bytes

    assert run_cli(["render-broadcast-readable", str(project_path)]) == 0
    assert output_path.read_bytes() == first_output
    assert final_script_path.read_bytes() == final_script_bytes


def test_legacy_mode_has_no_readable_fallback(tmp_path: Path) -> None:
    """Legacy Project에는 readable view를 추측 생성하는 fallback을 두지 않는다."""
    project_path = tmp_path / "PRJ-LEGACY"
    config = load_json_object(PILOT_ROOT / "00_PROJECT" / "production_config.json")
    config["script_source_mode"] = "LEGACY_MARKDOWN"
    write_json_object(project_path / "00_PROJECT" / "production_config.json", config)

    assert run_cli(["render-broadcast-readable", str(project_path)]) == 2
    assert not (project_path / "07_SCRIPT" / "broadcast_readable_script.md").exists()


def test_existing_broadcast_master_contract_and_bytes_are_unchanged() -> None:
    """Readable companion view는 기존 Master 계약과 Pilot Byte를 바꾸지 않는다."""
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
    assert "broadcast_readable_script" not in artifacts
    assert (
        sha256((PILOT_ROOT / "07_SCRIPT" / "final_script.md").read_bytes()).hexdigest()
        == FINAL_SCRIPT_SHA256
    )


def test_tracked_pilot_view_matches_current_canonical_json() -> None:
    """Commit된 PRJ-006 View가 현재 Canonical JSON의 재렌더 결과와 일치한다."""
    output_path = PILOT_ROOT / "07_SCRIPT" / "broadcast_readable_script.md"
    assert output_path.read_bytes() == rendered_pilot().encode("utf-8")
