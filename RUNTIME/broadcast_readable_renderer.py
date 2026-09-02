"""Canonical JSON에서 사람이 읽는 방송 대본 View를 결정론적으로 만든다."""

from collections.abc import Mapping, Sequence

from RUNTIME.screenplay_renderers import (
    CHARACTER_AUTHORED_TYPES,
    CONTEXT_LABELS,
    DRAMA_UNIT_TYPES,
    NARRATION_UNIT_TYPES,
    cast_order,
    characters_by_id,
    fail,
    mapping_items,
    markdown_cell,
    normalize_line_endings,
    presentation_segments,
    reaction_by_id,
    render_context_value,
    required_mapping,
    required_string,
    sorted_scenes,
    string_items,
    unit_records_by_segment,
)

READABLE_CONTEXT_FIELDS = (
    "location_description",
    "time_description",
    "previous_scene_id",
    "background_music_description",
    "sound_cues",
    "opening_character_state",
    "opening_emotional_state",
    "action_summary",
    "audience_information_gain",
    "retrospective_meaning",
)
READABLE_CHARACTER_LABELS = {
    "NARRATION": "내레이션",
    "INNER_MONOLOGUE": "내면 독백",
    "HALLUCINATION": "환각",
    "MESSAGE": "메시지",
    "CHAT": "채팅",
    "NOTE": "쪽지",
    "RECORDING": "녹음",
}


def matching_project_id(documents: Sequence[Mapping[str, object]]) -> str:
    """모든 Canonical 입력이 같은 Project에 속하는지 확인한다."""
    project_ids = [required_string(document, "project_id") for document in documents]
    if len(set(project_ids)) != 1:
        raise fail(
            "BROADCAST_READABLE_PROJECT_MISMATCH",
            f"Canonical 입력의 project_id가 다릅니다: {project_ids}",
        )
    return project_ids[0]


def panelists_by_id(
    panel_cast: Mapping[str, object],
) -> dict[str, Mapping[str, object]]:
    """Canonical Panel Cast를 고유 ID로 색인한다."""
    panelists: dict[str, Mapping[str, object]] = {}
    for panelist in mapping_items(panel_cast.get("panelists"), "panelists"):
        panelist_id = required_string(panelist, "panelist_id")
        if panelist_id in panelists:
            raise fail(
                "BROADCAST_READABLE_PANELIST_DUPLICATED",
                f"중복 Panelist ID입니다: {panelist_id}",
            )
        required_string(panelist, "display_name")
        required_string(panelist, "voice_style")
        panelists[panelist_id] = panelist
    if not panelists:
        raise fail(
            "BROADCAST_READABLE_PANELIST_MISSING",
            "Canonical Panel Cast가 비었습니다.",
        )
    return panelists


def scene_labels(
    screenplay_units: Mapping[str, object],
) -> dict[str, str]:
    """Scene ID를 사람이 읽는 장면 번호와 제목으로 변환한다."""
    labels: dict[str, str] = {}
    for scene in sorted_scenes(screenplay_units):
        scene_id = required_string(scene, "scene_id")
        if scene_id in labels:
            raise fail(
                "BROADCAST_READABLE_SCENE_DUPLICATED",
                f"중복 Scene ID입니다: {scene_id}",
            )
        order = scene.get("order")
        if not isinstance(order, int) or isinstance(order, bool):
            raise fail(
                "BROADCAST_READABLE_SCENE_SEQUENCE_INVALID",
                f"Scene order가 정수가 아닙니다: scene_id={scene_id}",
            )
        title = normalize_line_endings(required_string(scene, "title"))
        labels[scene_id] = f"장면 {order}. {title}"
    return labels


def readable_context_value(
    field: str,
    value: object,
    labels: Mapping[str, str],
) -> str:
    """내부 Scene ID를 노출하지 않는 Context 표시 값을 만든다."""
    if field != "previous_scene_id":
        return render_context_value(field, value)
    if value is None:
        return "없음"
    if not isinstance(value, str) or value not in labels:
        raise fail(
            "BROADCAST_READABLE_PREVIOUS_SCENE_INVALID",
            f"직전 Scene 참조를 해석할 수 없습니다: {value}",
        )
    return labels[value]


def render_scene_context(
    scene: Mapping[str, object],
    labels: Mapping[str, str],
) -> str:
    """Reference의 상황 설명 형식으로 Canonical Scene Context를 표시한다."""
    context = required_mapping(scene, "context")
    parts: list[str] = []
    for field in READABLE_CONTEXT_FIELDS:
        label = CONTEXT_LABELS.get(field)
        if label is None:
            raise fail(
                "BROADCAST_READABLE_CONTEXT_UNSUPPORTED",
                f"지원하지 않는 Scene Context 필드입니다: {field}",
            )
        rendered = readable_context_value(field, context.get(field), labels)
        parts.append(f"{label} — {rendered}")
    return f"*[상황 설명: {' / '.join(parts)}]*"


def delivery_instruction(unit: Mapping[str, object]) -> str | None:
    """선택 Canonical Delivery의 사람용 연기 지시를 반환한다."""
    raw_delivery = unit.get("delivery")
    if raw_delivery is None:
        return None
    if not isinstance(raw_delivery, Mapping):
        raise fail(
            "BROADCAST_READABLE_DELIVERY_INVALID",
            "delivery는 객체이거나 생략되어야 합니다.",
        )
    delivery = raw_delivery
    instruction = normalize_line_endings(required_string(delivery, "instruction"))
    return instruction.replace("\n", "<br>")


def render_character_unit(
    unit: Mapping[str, object],
    character_map: Mapping[str, Mapping[str, object]],
) -> str:
    """인물 발화를 실제 이름과 Canonical 원문으로 렌더링한다."""
    unit_type = required_string(unit, "type")
    text = normalize_line_endings(required_string(unit, "text"))
    speaker_id = required_string(unit, "speaker_id")
    character = character_map.get(speaker_id)
    if character is None:
        raise fail(
            "BROADCAST_READABLE_SPEAKER_UNKNOWN",
            f"Canonical Characters에 없는 speaker_id입니다: {speaker_id}",
        )
    speaker_name = normalize_line_endings(required_string(character, "name"))
    instruction = delivery_instruction(unit)
    if unit_type == "DIALOGUE":
        heading = speaker_name
    else:
        label = READABLE_CHARACTER_LABELS.get(unit_type)
        if unit_type not in CHARACTER_AUTHORED_TYPES or label is None:
            raise fail(
                "BROADCAST_READABLE_UNIT_TYPE_UNSUPPORTED",
                f"지원하지 않는 인물 Unit 유형입니다: {unit_type}",
            )
        heading = f"{speaker_name}({label})"
    delivery_text = f" *({instruction})*" if instruction is not None else ""
    return f"**{heading}**{delivery_text}\n{text}"


def render_readable_unit(
    unit: Mapping[str, object],
    character_map: Mapping[str, Mapping[str, object]],
) -> str:
    """Unit 유형을 Source-style 가시 블록으로 렌더링한다."""
    unit_type = required_string(unit, "type")
    text = normalize_line_endings(required_string(unit, "text"))
    if unit_type == "ACTION":
        return f"*[지문: {text}]*"
    if unit_type == "SOUND":
        return f"*[음향: {text}]*"
    if unit_type == "SCREEN_TEXT":
        return f"**화면 문구**\n{text}"
    return render_character_unit(unit, character_map)


def render_panel_turns(
    reaction: Mapping[str, object],
    panelist_map: Mapping[str, Mapping[str, object]],
    seen_turn_ids: set[str],
) -> list[str]:
    """Canonical Panel Turn을 실제 표시 이름과 원문으로 렌더링한다."""
    turns = mapping_items(reaction.get("turns"), "turns")
    if not turns:
        raise fail(
            "BROADCAST_READABLE_PANEL_TURN_MISSING",
            "Panel Reaction에 Turn이 없습니다.",
        )
    blocks: list[str] = []
    for turn in turns:
        turn_id = required_string(turn, "turn_id")
        if turn_id in seen_turn_ids:
            raise fail(
                "BROADCAST_READABLE_PANEL_TURN_DUPLICATED",
                f"중복 Panel Turn입니다: {turn_id}",
            )
        seen_turn_ids.add(turn_id)
        panelist_id = required_string(turn, "panelist_id")
        panelist = panelist_map.get(panelist_id)
        if panelist is None:
            raise fail(
                "BROADCAST_READABLE_PANELIST_UNKNOWN",
                f"Canonical Panel Cast에 없는 panelist_id입니다: {panelist_id}",
            )
        display_name = normalize_line_endings(required_string(panelist, "display_name"))
        spoken_line = normalize_line_endings(required_string(turn, "spoken_line"))
        blocks.append(f"**{display_name}(패널)**\n{spoken_line}")
    return blocks


def render_cast_sections(
    screenplay_units: Mapping[str, object],
    character_map: Mapping[str, Mapping[str, object]],
    panel_cast: Mapping[str, object],
) -> list[str]:
    """실제 인물과 Panel 표시 이름을 별도 표로 만든다."""
    lines = [
        "## 등장인물",
        "",
        "| 인물 | 설명 |",
        "|---|---|",
    ]
    for character_id in cast_order(screenplay_units, character_map):
        character = character_map[character_id]
        lines.append(
            f"| {markdown_cell(required_string(character, 'name'))} | "
            f"{markdown_cell(required_string(character, 'role'))} |"
        )
    lines.extend(
        (
            "",
            "## 패널",
            "",
            "| 패널 | 진행 역할 |",
            "|---|---|",
        )
    )
    for panelist in mapping_items(panel_cast.get("panelists"), "panelists"):
        lines.append(
            f"| {markdown_cell(required_string(panelist, 'display_name'))} | "
            f"{markdown_cell(required_string(panelist, 'voice_style'))} |"
        )
    return lines


def render_broadcast_readable_script(
    screenplay_units: Mapping[str, object],
    characters: Mapping[str, object],
    panel_cast: Mapping[str, object],
    reaction_segments: Mapping[str, object],
    presentation_plan: Mapping[str, object],
) -> str:
    """동일 Canonical JSON에서 Marker 없는 사람용 Broadcast View를 만든다."""
    project_id = matching_project_id(
        (
            screenplay_units,
            characters,
            panel_cast,
            reaction_segments,
            presentation_plan,
        )
    )
    title = normalize_line_endings(required_string(screenplay_units, "title"))
    truth_classification = required_string(
        screenplay_units,
        "source_truth_classification",
    )
    character_map = characters_by_id(characters)
    panelist_map = panelists_by_id(panel_cast)
    reactions = reaction_by_id(reaction_segments)
    labels = scene_labels(screenplay_units)
    records_by_segment = unit_records_by_segment(screenplay_units)

    plan_by_scene: dict[str, list[Mapping[str, object]]] = {}
    seen_segment_ids: set[str] = set()
    for segment in presentation_segments(presentation_plan):
        segment_id = required_string(segment, "segment_id")
        if segment_id in seen_segment_ids:
            raise fail(
                "BROADCAST_READABLE_SEGMENT_DUPLICATED",
                f"중복 Presentation Segment입니다: {segment_id}",
            )
        seen_segment_ids.add(segment_id)
        scene_id = required_string(segment, "scene_id")
        if scene_id not in labels:
            raise fail(
                "BROADCAST_READABLE_SCENE_UNKNOWN",
                f"Presentation이 알 수 없는 Scene을 참조합니다: {scene_id}",
            )
        plan_by_scene.setdefault(scene_id, []).append(segment)

    lines = [
        f"# 「{title}」 방송용 읽기 대본",
        "",
        f"- 프로젝트: {project_id}",
        f"- 작품 구분: {truth_classification}",
        "- 생성 기준: Canonical Screenplay Unit·Scene Context·Panel Reaction",
        "",
        *render_cast_sections(screenplay_units, character_map, panel_cast),
        "",
    ]
    used_reaction_ids: set[str] = set()
    seen_turn_ids: set[str] = set()
    used_unit_segment_ids: set[str] = set()
    panel_index = 1
    for scene in sorted_scenes(screenplay_units):
        scene_id = required_string(scene, "scene_id")
        lines.extend((f"## {labels[scene_id]}", "", render_scene_context(scene, labels), ""))
        planned_segments = plan_by_scene.get(scene_id, [])
        declared_segment_ids = string_items(scene, "segment_ids")
        planned_segment_ids = [
            required_string(segment, "segment_id") for segment in planned_segments
        ]
        if declared_segment_ids != planned_segment_ids:
            raise fail(
                "BROADCAST_READABLE_SCENE_SEGMENTS_MISMATCH",
                f"{scene_id}의 Scene/Presentation Segment 순서가 다릅니다: "
                f"declared={declared_segment_ids}, planned={planned_segment_ids}",
            )
        for segment in planned_segments:
            segment_id = required_string(segment, "segment_id")
            segment_type = required_string(segment, "segment_type")
            records = records_by_segment.get(segment_id, [])
            if segment_type in {"DRAMA", "NARRATION"}:
                if not records:
                    raise fail(
                        "BROADCAST_READABLE_UNIT_MISSING",
                        f"{segment_id}에 표시할 Unit이 없습니다.",
                    )
                expected_types = (
                    DRAMA_UNIT_TYPES if segment_type == "DRAMA" else NARRATION_UNIT_TYPES
                )
                invalid_types = sorted(
                    {
                        required_string(unit, "type")
                        for record_scene_id, unit in records
                        if record_scene_id != scene_id or unit.get("type") not in expected_types
                    }
                )
                if invalid_types or any(
                    record_scene_id != scene_id for record_scene_id, _unit in records
                ):
                    raise fail(
                        "BROADCAST_READABLE_UNIT_LAYER_MISMATCH",
                        f"{segment_id}의 Scene 또는 Unit 유형이 다릅니다: {invalid_types}",
                    )
                for _record_scene_id, unit in records:
                    lines.extend((render_readable_unit(unit, character_map), ""))
                used_unit_segment_ids.add(segment_id)
                continue
            if segment_type != "PANEL_REACTION":
                raise fail(
                    "BROADCAST_READABLE_SEGMENT_UNSUPPORTED",
                    f"Canonical JSON으로 렌더링할 수 없는 Segment 유형입니다: {segment_type}",
                )
            if records:
                raise fail(
                    "BROADCAST_READABLE_PANEL_UNIT_CONFLICT",
                    f"Panel Segment에 Screenplay Unit이 연결되었습니다: {segment_id}",
                )
            reaction_id = required_string(segment, "reaction_segment_id")
            reaction = reactions.get(reaction_id)
            if reaction is None:
                raise fail(
                    "BROADCAST_READABLE_REACTION_MISSING",
                    f"{segment_id}가 참조한 Reaction이 없습니다: {reaction_id}",
                )
            if reaction_id in used_reaction_ids:
                raise fail(
                    "BROADCAST_READABLE_REACTION_DUPLICATED",
                    f"Reaction이 여러 번 배치되었습니다: {reaction_id}",
                )
            if required_string(reaction, "after_scene_id") != scene_id:
                raise fail(
                    "BROADCAST_READABLE_REACTION_SCENE_MISMATCH",
                    f"Reaction의 Scene 결속이 다릅니다: {reaction_id}",
                )
            lines.extend((f"### 패널 반응 {panel_index}", ""))
            for block in render_panel_turns(reaction, panelist_map, seen_turn_ids):
                lines.extend((block, ""))
            used_reaction_ids.add(reaction_id)
            panel_index += 1

    unused_unit_segments = sorted(set(records_by_segment) - used_unit_segment_ids)
    if unused_unit_segments:
        raise fail(
            "BROADCAST_READABLE_UNIT_SEGMENT_UNPLANNED",
            f"표시되지 않은 Unit Segment가 있습니다: {unused_unit_segments}",
        )
    unused_reactions = sorted(set(reactions) - used_reaction_ids)
    if unused_reactions:
        raise fail(
            "BROADCAST_READABLE_REACTION_UNPLANNED",
            f"표시되지 않은 Panel Reaction이 있습니다: {unused_reactions}",
        )
    if not lines or lines[-1] != "":
        raise fail(
            "BROADCAST_READABLE_RENDER_INVALID",
            "Renderer 소유의 마지막 Block 구분자가 없습니다.",
        )
    return "\n".join(lines[:-1]) + "\n"
