"""Broadcast Readable v2 Source-style Renderer 계약을 검증한다."""

from copy import deepcopy
from hashlib import sha256
from pathlib import Path

import pytest

from RUNTIME.broadcast_readable_renderer import render_readable_unit
from RUNTIME.broadcast_readable_v2_renderer import (
    render_broadcast_readable_script_v2,
    render_broadcast_readable_script_versioned,
)
from RUNTIME.screenplay_renderers import characters_by_id, mapping_items
from VALIDATORS.exceptions import ConfigurationError
from VALIDATORS.io import load_json_object

ROOT = Path(__file__).resolve().parents[1]
PILOT_ROOT = ROOT / "PROJECTS/PRJ-006"
V1_PROFILE_PATH = (
    ROOT
    / "CHANNELS/mystery_main/output_profiles/broadcast-readable-script/1.0.0.json"
)
V2_PROFILE_PATH = (
    ROOT
    / "CHANNELS/mystery_main/output_profiles/broadcast-readable-script/2.0.0.json"
)
V1_OUTPUT_SHA256 = "a823e34f69132c857d6eea6a93b9842dd5f40add50edfe6409b1a2f6c4fbe2fa"
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


def pilot_documents() -> dict[str, dict[str, object]]:
    """PRJ-006 Canonical Readable 입력을 독립 사전으로 읽는다."""
    return {
        "screenplay_units": load_json_object(
            PILOT_ROOT / "07_SCRIPT/screenplay_units.json"
        ),
        "characters": load_json_object(PILOT_ROOT / "02_CHARACTER/characters.json"),
        "relationships": load_json_object(
            PILOT_ROOT / "02_CHARACTER/relationships.json"
        ),
        "panel_cast": load_json_object(PILOT_ROOT / "06_SCENE/panel_cast.json"),
        "reaction_segments": load_json_object(
            PILOT_ROOT / "06_SCENE/reaction_segments.json"
        ),
        "presentation_plan": load_json_object(
            PILOT_ROOT / "06_SCENE/presentation_plan.json"
        ),
        "profile": load_json_object(V2_PROFILE_PATH),
    }


def render_documents(documents: dict[str, dict[str, object]]) -> str:
    """Fixture 사전에서 v2 Markdown을 렌더링한다."""
    return render_broadcast_readable_script_v2(
        documents["screenplay_units"],
        documents["characters"],
        documents["relationships"],
        documents["panel_cast"],
        documents["reaction_segments"],
        documents["presentation_plan"],
        documents["profile"],
    )


def screenplay_scenes(document: dict[str, object]) -> list[dict[str, object]]:
    """수정 가능한 Screenplay Scene Fixture 배열을 반환한다."""
    scenes = document["scenes"]
    assert isinstance(scenes, list)
    assert all(isinstance(scene, dict) for scene in scenes)
    return [scene for scene in scenes if isinstance(scene, dict)]


def presentation_records(document: dict[str, object]) -> list[dict[str, object]]:
    """수정 가능한 Presentation Segment Fixture 배열을 반환한다."""
    segments = document["segments"]
    assert isinstance(segments, list)
    assert all(isinstance(segment, dict) for segment in segments)
    return [segment for segment in segments if isinstance(segment, dict)]


def reset_start_times(segments: list[dict[str, object]]) -> None:
    """Fixture 재배치 뒤 start_sec를 배열 순서와 일치시킨다."""
    for index, segment in enumerate(segments):
        segment["start_sec"] = index * 100


def test_v2_source_style_structure_relationships_and_exact_text() -> None:
    """필수 Heading·3열 관계·분리 Context와 Canonical 원문을 모두 보존한다."""
    documents = pilot_documents()
    rendered = render_documents(documents)

    rendered_lines = rendered.splitlines()
    assert [rendered_lines.count(f"## {heading}") for heading in (
        "정리 기준",
        "등장인물",
        "패널",
        "방송 대본",
    )] == [1, 1, 1, 1]
    assert "| 인물 | 역할 | 관계 |" in rendered
    assert "|---|---|---|" in rendered
    assert "오민재: 같은 야간 근무를 맡던 동료" in rendered
    assert "한서윤: 처음에는 불완전한 기억을 의심하지만" in rendered
    scene_count = len(screenplay_scenes(documents["screenplay_units"]))
    assert rendered.count("*[상황 설명:") == scene_count
    assert rendered.count("*[음향·행동 설명:") == scene_count
    for scene in screenplay_scenes(documents["screenplay_units"]):
        units = scene["units"]
        assert isinstance(units, list)
        for unit in units:
            assert isinstance(unit, dict)
            text = unit["text"]
            assert isinstance(text, str)
            assert text in rendered
    reactions = documents["reaction_segments"]["reaction_segments"]
    assert isinstance(reactions, list)
    for reaction in reactions:
        assert isinstance(reaction, dict)
        turns = reaction["turns"]
        assert isinstance(turns, list)
        for turn in turns:
            assert isinstance(turn, dict)
            spoken_line = turn["spoken_line"]
            assert isinstance(spoken_line, str)
            assert spoken_line in rendered
    for token in (*FORBIDDEN_PREFIXES, "<!--", "-->"):
        assert token not in rendered


def test_relationship_aggregation_is_deterministic_by_relationship_id() -> None:
    """Relationship 입력 배열 순서가 바뀌어도 인물별 집계 Byte는 같다."""
    documents = pilot_documents()
    baseline = render_documents(documents)
    reversed_documents = deepcopy(documents)
    relationships = reversed_documents["relationships"]["relationships"]
    assert isinstance(relationships, list)
    relationships.reverse()

    assert render_documents(reversed_documents) == baseline


def test_global_reentry_order_context_once_and_continuation_heading() -> None:
    """Scene 재진입 Fixture에서 전역 D→Scene2→P→Scene1 순서를 보존한다."""
    documents = pilot_documents()
    segments = presentation_records(documents["presentation_plan"])
    by_id = {str(segment["segment_id"]): segment for segment in segments}
    front_ids = ["SEG-001", "SEG-004", "SEG-003", "SEG-002", "SEG-005"]
    reordered = [by_id[segment_id] for segment_id in front_ids]
    reordered.extend(
        segment for segment in segments if segment["segment_id"] not in front_ids
    )
    documents["presentation_plan"]["segments"] = reordered
    reset_start_times(reordered)
    scenes = screenplay_scenes(documents["screenplay_units"])
    scenes[0]["segment_ids"] = ["SEG-001", "SEG-003", "SEG-002"]
    rendered = render_documents(documents)

    scene_1_drama = "안에 지석 씨가 있어요. 저 혼자 나온 게 아니에요."
    scene_2_drama = "제출 전 원본과 수정본을 대조할 것."
    panel_line = "음악 중단과 배수구 단추가 같은 장면에 남았습니다."
    scene_1_narration = "그날 내가 처음 무서웠던 건 비명이 아니었다."
    assert (
        rendered.index(scene_1_drama)
        < rendered.index(scene_2_drama)
        < rendered.index(panel_line)
        < rendered.index(scene_1_narration)
    )
    assert rendered.count("### 장면 1 재개. 멈춘 폐장 음악") == 1
    assert rendered.count("### 장면 2 재개. 보관하라는 메모") == 1
    assert rendered.count("장소 — 불이 반만 꺼진 폐장 실내 수영장") == 1


def test_retrospective_occurs_after_last_scene_segment_and_empty_is_omitted() -> None:
    """재해석은 Scene 마지막 전역 Segment 뒤에 한 번만 나오며 빈 값은 생략한다."""
    documents = pilot_documents()
    rendered = render_documents(documents)
    retrospective = "하나의 소매가 반사된 것이라던 첫 해석은 후반의 역할 분담으로 뒤집힌다."
    scene_4_panel_line = "얼굴은 없지만 소매가 세 방향입니다."
    assert rendered.count(retrospective) == 1
    assert rendered.index(retrospective) > rendered.index(scene_4_panel_line)

    without_retrospective = deepcopy(documents)
    scene = screenplay_scenes(without_retrospective["screenplay_units"])[3]
    context = scene["context"]
    assert isinstance(context, dict)
    context["retrospective_meaning"] = "해당 없음"
    omitted = render_documents(without_retrospective)
    assert retrospective not in omitted
    assert "*[반전 후 의미: 해당 없음]*" not in omitted


def test_all_character_authored_special_unit_labels_preserve_text() -> None:
    """모든 Character-authored 특수 Unit을 한국어 Label과 원문으로 표시한다."""
    documents = pilot_documents()
    character_map = characters_by_id(documents["characters"])
    render_contract = documents["profile"]["render_contract"]
    assert isinstance(render_contract, dict)
    expected = {
        "NARRATION": "내레이션",
        "INNER_MONOLOGUE": "내면 독백",
        "HALLUCINATION": "환각",
        "MESSAGE": "메시지",
        "CHAT": "채팅",
        "NOTE": "쪽지",
        "RECORDING": "녹음",
    }
    for unit_type, label in expected.items():
        text = f"{unit_type} 원문"
        rendered = render_readable_unit(
            {
                "unit_id": "UNIT-TEST",
                "type": unit_type,
                "speaker_id": "CHAR-06",
                "text": text,
            },
            character_map,
            render_contract,
        )
        assert f"**한서윤({label})**" in rendered
        assert rendered.endswith(text)


def test_multiple_panel_segments_in_same_scene_remain_in_global_order() -> None:
    """같은 Scene의 Panel Segment 두 개를 누락·병합하지 않는다."""
    documents = pilot_documents()
    segments = presentation_records(documents["presentation_plan"])
    copied_segment = deepcopy(segments[2])
    copied_segment["segment_id"] = "SEG-900"
    copied_segment["reaction_segment_id"] = "RSEG-900"
    segments.insert(3, copied_segment)
    documents["presentation_plan"]["segments"] = segments
    reset_start_times(segments)
    scene = screenplay_scenes(documents["screenplay_units"])[0]
    scene["segment_ids"] = ["SEG-001", "SEG-002", "SEG-003", "SEG-900"]
    reactions = documents["reaction_segments"]["reaction_segments"]
    assert isinstance(reactions, list)
    copied_reaction = deepcopy(reactions[0])
    assert isinstance(copied_reaction, dict)
    copied_reaction["reaction_segment_id"] = "RSEG-900"
    turns = copied_reaction["turns"]
    assert isinstance(turns, list)
    for index, turn in enumerate(turns, start=1):
        assert isinstance(turn, dict)
        turn["turn_id"] = f"TURN-900-{index:02d}"
        turn["spoken_line"] = f"두 번째 패널 원문 {index}"
    reactions.append(copied_reaction)

    rendered = render_documents(documents)

    assert rendered.index("### 패널 반응 1") < rendered.index("### 패널 반응 2")
    assert "두 번째 패널 원문 1" in rendered
    assert "두 번째 패널 원문 2" in rendered


def test_unknown_relationship_character_fails() -> None:
    """Relationship의 미등록 인물 참조를 이름 추측 없이 거부한다."""
    documents = pilot_documents()
    relationships = documents["relationships"]["relationships"]
    assert isinstance(relationships, list)
    relationship = relationships[0]
    assert isinstance(relationship, dict)
    relationship["from"] = "CHAR-99"

    with pytest.raises(
        ConfigurationError,
        match="BROADCAST_READABLE_RELATIONSHIP_CHARACTER_UNKNOWN",
    ):
        render_documents(documents)


def test_required_relationship_display_summary_missing_fails() -> None:
    """relationships@1.1.0의 display_summary 누락은 Legacy 문구로 숨기지 않는다."""
    documents = pilot_documents()
    relationships = documents["relationships"]["relationships"]
    assert isinstance(relationships, list)
    relationship = relationships[0]
    assert isinstance(relationship, dict)
    relationship.pop("display_summary")

    with pytest.raises(
        ConfigurationError,
        match="BROADCAST_READABLE_RELATIONSHIP_SUMMARY_MISSING",
    ):
        render_documents(documents)


def test_unsupported_segment_type_fails_closed() -> None:
    """Source 계약이 없는 Segment 유형을 조용히 삭제하지 않는다."""
    documents = pilot_documents()
    segment = presentation_records(documents["presentation_plan"])[0]
    segment["segment_type"] = "EXPERT_ANALYSIS"

    with pytest.raises(
        ConfigurationError,
        match="BROADCAST_READABLE_UNSUPPORTED_SEGMENT_TYPE",
    ):
        render_documents(documents)


def test_duplicate_presentation_segment_fails_scene_boundary_mapping() -> None:
    """Scene 첫·마지막 경계를 모호하게 만드는 중복 Segment를 거부한다."""
    documents = pilot_documents()
    segments = presentation_records(documents["presentation_plan"])
    segments.insert(1, deepcopy(segments[0]))
    documents["presentation_plan"]["segments"] = segments
    reset_start_times(segments)

    with pytest.raises(
        ConfigurationError,
        match="BROADCAST_READABLE_SEGMENT_DUPLICATED",
    ):
        render_documents(documents)


@pytest.mark.parametrize("forbidden_prefix", FORBIDDEN_PREFIXES)
def test_each_forbidden_id_prefix_in_visible_output_fails(
    forbidden_prefix: str,
) -> None:
    """각 Canonical ID Prefix가 보이는 Markdown으로 유출되면 독립 실패한다."""
    documents = pilot_documents()
    documents["screenplay_units"]["title"] = f"금지 토큰 {forbidden_prefix}001"

    with pytest.raises(
        ConfigurationError,
        match="BROADCAST_READABLE_VISIBLE_TOKEN_FORBIDDEN",
    ):
        render_documents(documents)


@pytest.mark.parametrize("forbidden_token", ["<!--", "-->"])
def test_each_html_comment_token_in_visible_output_fails(
    forbidden_token: str,
) -> None:
    """HTML Comment 시작·종료 Token을 각각 차단한다."""
    documents = pilot_documents()
    documents["screenplay_units"]["title"] = f"금지 토큰 {forbidden_token}"

    with pytest.raises(
        ConfigurationError,
        match="BROADCAST_READABLE_VISIBLE_TOKEN_FORBIDDEN",
    ):
        render_documents(documents)


@pytest.mark.parametrize("marker", ["[청취 불명확]", "[화자 불명확]"])
def test_original_fiction_uncertainty_marker_fails(marker: str) -> None:
    """Original Fiction에서 사실 원문용 불확실성 Marker를 각각 거부한다."""
    documents = pilot_documents()
    documents["screenplay_units"]["title"] = f"금지 토큰 {marker}"

    with pytest.raises(
        ConfigurationError,
        match="BROADCAST_READABLE_VISIBLE_TOKEN_FORBIDDEN",
    ):
        render_documents(documents)


def test_version_dispatch_keeps_v1_output_bytes_unchanged() -> None:
    """Version Dispatch의 v1 경로는 등록 기준 Renderer Byte를 그대로 유지한다."""
    documents = pilot_documents()
    v1_output = render_broadcast_readable_script_versioned(
        documents["screenplay_units"],
        documents["characters"],
        documents["relationships"],
        documents["panel_cast"],
        documents["reaction_segments"],
        documents["presentation_plan"],
        load_json_object(V1_PROFILE_PATH),
    )

    assert sha256(v1_output.encode("utf-8")).hexdigest() == V1_OUTPUT_SHA256


def test_mapping_fixture_helper_rejects_non_mapping_arrays() -> None:
    """Renderer Test Fixture도 Canonical 객체 배열 가정을 숨기지 않는다."""
    with pytest.raises(ConfigurationError, match="SCREENPLAY_RENDER_INPUT_INVALID"):
        mapping_items(["invalid"], "fixture")
