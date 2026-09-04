"""Canonical JSON에서 사람이 읽는 방송 대본 View를 결정론적으로 만든다."""

from collections.abc import Mapping, Sequence
from string import Formatter

from RUNTIME.screenplay_renderers import (
    CHARACTER_AUTHORED_TYPES,
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

SUPPORTED_CONTEXT_FIELDS = (
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
EXPECTED_SOURCE_STYLE_CONTRACT = {
    "ordering_source": "PRESENTATION_PLAN",
    "unit_text_policy": "CANONICAL_EXACT",
    "character_name_source": "CHARACTERS_NAME",
    "panel_name_source": "PANEL_CAST_DISPLAY_NAME",
    "scene_context_position": "BEFORE_SCENE_CONTENT",
    "internal_identifier_visibility": "HIDDEN",
    "unknown_identity_policy": "FAIL",
}


def profile_mapping(
    parent: Mapping[str, object],
    field: str,
) -> Mapping[str, object]:
    """Profile의 필수 객체를 엄격하게 읽는다."""
    value = parent.get(field)
    if not isinstance(value, Mapping):
        raise fail(
            "BROADCAST_READABLE_OUTPUT_PROFILE_INVALID",
            f"Output Profile의 {field}가 객체가 아닙니다.",
        )
    return value


def profile_string(parent: Mapping[str, object], field: str) -> str:
    """Profile의 비어 있지 않은 필수 문자열을 읽는다."""
    value = parent.get(field)
    if not isinstance(value, str) or not value:
        raise fail(
            "BROADCAST_READABLE_OUTPUT_PROFILE_INVALID",
            f"Output Profile의 {field}가 비어 있지 않은 문자열이 아닙니다.",
        )
    return value


def profile_strings(parent: Mapping[str, object], field: str) -> list[str]:
    """Profile의 문자열 배열을 순서를 보존해 읽는다."""
    value = parent.get(field)
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise fail(
            "BROADCAST_READABLE_OUTPUT_PROFILE_INVALID",
            f"Output Profile의 {field}가 문자열 배열이 아닙니다.",
        )
    return list(value)


def format_profile_template(
    template: str,
    values: Mapping[str, object],
    field: str,
) -> str:
    """선언된 자리표시자만 허용해 Profile Template을 렌더링한다."""
    try:
        fields = {
            name
            for _literal, name, _format_spec, _conversion in Formatter().parse(template)
            if name is not None
        }
    except ValueError as error:
        raise fail(
            "BROADCAST_READABLE_OUTPUT_PROFILE_INVALID",
            f"{field} Template 구문이 올바르지 않습니다: {error}",
        ) from error
    expected_fields = set(values)
    if fields != expected_fields:
        raise fail(
            "BROADCAST_READABLE_OUTPUT_PROFILE_INVALID",
            f"{field} Template 자리표시자가 다릅니다: "
            f"expected={sorted(expected_fields)}, actual={sorted(fields)}",
        )
    try:
        return template.format_map(values)
    except (KeyError, ValueError) as error:
        raise fail(
            "BROADCAST_READABLE_OUTPUT_PROFILE_INVALID",
            f"{field} Template을 렌더링할 수 없습니다: {error}",
        ) from error


def validate_source_style_contract(output_profile: Mapping[str, object]) -> None:
    """Renderer가 구현하는 Source-style 의미 계약과 Profile을 대조한다."""
    contract = profile_mapping(output_profile, "source_style_contract")
    if dict(contract) != EXPECTED_SOURCE_STYLE_CONTRACT:
        raise fail(
            "BROADCAST_READABLE_SOURCE_STYLE_CONTRACT_UNSUPPORTED",
            "Renderer가 지원하지 않는 Source-style 의미 계약입니다.",
        )


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
    document_contract: Mapping[str, object],
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
        labels[scene_id] = format_profile_template(
            profile_string(document_contract, "scene_label_template"),
            {"order": order, "title": title},
            "scene_label_template",
        )
    return labels


def readable_context_value(
    field: str,
    value: object,
    labels: Mapping[str, str],
    no_previous_scene_label: str,
) -> str:
    """내부 Scene ID를 노출하지 않는 Context 표시 값을 만든다."""
    if field != "previous_scene_id":
        return render_context_value(field, value)
    if value is None:
        return no_previous_scene_label
    if not isinstance(value, str) or value not in labels:
        raise fail(
            "BROADCAST_READABLE_PREVIOUS_SCENE_INVALID",
            f"직전 Scene 참조를 해석할 수 없습니다: {value}",
        )
    return labels[value]


def render_scene_context(
    scene: Mapping[str, object],
    labels: Mapping[str, str],
    document_contract: Mapping[str, object],
) -> str:
    """Reference의 상황 설명 형식으로 Canonical Scene Context를 표시한다."""
    context = required_mapping(scene, "context")
    context_fields = profile_strings(document_contract, "scene_context_fields")
    if set(context_fields) != set(SUPPORTED_CONTEXT_FIELDS):
        raise fail(
            "BROADCAST_READABLE_OUTPUT_PROFILE_INVALID",
            "scene_context_fields는 지원되는 Canonical Context 전체를 한 번씩 포함해야 합니다.",
        )
    context_labels = profile_mapping(document_contract, "scene_context_labels")
    entry_template = profile_string(document_contract, "scene_context_entry_template")
    no_previous_scene_label = profile_string(
        document_contract,
        "no_previous_scene_label",
    )
    parts: list[str] = []
    for field in context_fields:
        label = profile_string(context_labels, field)
        rendered = readable_context_value(
            field,
            context.get(field),
            labels,
            no_previous_scene_label,
        )
        parts.append(
            format_profile_template(
                entry_template,
                {"label": label, "value": rendered},
                "scene_context_entry_template",
            )
        )
    context_text = profile_string(document_contract, "scene_context_separator").join(
        parts
    )
    return format_profile_template(
        profile_string(document_contract, "scene_context_template"),
        {"context": context_text},
        "scene_context_template",
    )


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
    return instruction


def render_character_unit(
    unit: Mapping[str, object],
    character_map: Mapping[str, Mapping[str, object]],
    render_contract: Mapping[str, object],
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
    delivery_block = ""
    if instruction is not None:
        normalized_instruction = instruction.replace(
            "\n",
            profile_string(render_contract, "delivery_line_separator"),
        )
        delivery_block = format_profile_template(
            profile_string(render_contract, "delivery_template"),
            {"instruction": normalized_instruction},
            "delivery_template",
        )
    if unit_type == "DIALOGUE":
        return format_profile_template(
            profile_string(render_contract, "dialogue_template"),
            {
                "speaker_name": speaker_name,
                "delivery_block": delivery_block,
                "text": text,
            },
            "dialogue_template",
        )
    labels = profile_mapping(render_contract, "special_unit_labels")
    label = labels.get(unit_type)
    if unit_type not in CHARACTER_AUTHORED_TYPES or not isinstance(label, str):
        raise fail(
            "BROADCAST_READABLE_UNIT_TYPE_UNSUPPORTED",
            f"지원하지 않는 인물 Unit 유형입니다: {unit_type}",
        )
    return format_profile_template(
        profile_string(render_contract, "character_authored_template"),
        {
            "speaker_name": speaker_name,
            "label": label,
            "delivery_block": delivery_block,
            "text": text,
        },
        "character_authored_template",
    )


def render_readable_unit(
    unit: Mapping[str, object],
    character_map: Mapping[str, Mapping[str, object]],
    render_contract: Mapping[str, object],
) -> str:
    """Unit 유형을 Source-style 가시 블록으로 렌더링한다."""
    unit_type = required_string(unit, "type")
    text = normalize_line_endings(required_string(unit, "text"))
    if unit_type == "ACTION":
        template_field = "direction_template"
        return format_profile_template(
            profile_string(render_contract, template_field),
            {"text": text},
            template_field,
        )
    if unit_type == "SOUND":
        template_field = "sound_template"
        return format_profile_template(
            profile_string(render_contract, template_field),
            {"text": text},
            template_field,
        )
    if unit_type == "SCREEN_TEXT":
        template_field = "screen_text_template"
        return format_profile_template(
            profile_string(render_contract, template_field),
            {"text": text},
            template_field,
        )
    return render_character_unit(unit, character_map, render_contract)


def render_panel_turns(
    reaction: Mapping[str, object],
    panelist_map: Mapping[str, Mapping[str, object]],
    seen_turn_ids: set[str],
    render_contract: Mapping[str, object],
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
        blocks.append(
            format_profile_template(
                profile_string(render_contract, "panel_turn_template"),
                {"display_name": display_name, "spoken_line": spoken_line},
                "panel_turn_template",
            )
        )
    return blocks


def render_cast_sections(
    screenplay_units: Mapping[str, object],
    character_map: Mapping[str, Mapping[str, object]],
    panel_cast: Mapping[str, object],
    document_contract: Mapping[str, object],
) -> list[str]:
    """실제 인물과 Panel 표시 이름을 별도 표로 만든다."""
    character_columns = profile_strings(document_contract, "character_table_columns")
    panel_columns = profile_strings(document_contract, "panel_table_columns")
    if len(character_columns) != 2 or len(panel_columns) != 2:
        raise fail(
            "BROADCAST_READABLE_OUTPUT_PROFILE_INVALID",
            "등장인물과 Panel 표는 각각 정확히 두 열이어야 합니다.",
        )
    lines = [
        profile_string(document_contract, "character_heading"),
        "",
        f"| {character_columns[0]} | {character_columns[1]} |",
        profile_string(document_contract, "table_divider"),
    ]
    for character_id in cast_order(screenplay_units, character_map):
        character = character_map[character_id]
        lines.append(
            format_profile_template(
                profile_string(document_contract, "character_table_row_template"),
                {
                    "name": markdown_cell(required_string(character, "name")),
                    "role": markdown_cell(required_string(character, "role")),
                },
                "character_table_row_template",
            )
        )
    lines.extend(
        (
            "",
            profile_string(document_contract, "panel_heading"),
            "",
            f"| {panel_columns[0]} | {panel_columns[1]} |",
            profile_string(document_contract, "table_divider"),
        )
    )
    for panelist in mapping_items(panel_cast.get("panelists"), "panelists"):
        lines.append(
            format_profile_template(
                profile_string(document_contract, "panel_table_row_template"),
                {
                    "display_name": markdown_cell(
                        required_string(panelist, "display_name")
                    ),
                    "voice_style": markdown_cell(
                        required_string(panelist, "voice_style")
                    ),
                },
                "panel_table_row_template",
            )
        )
    return lines


def render_broadcast_readable_script(
    screenplay_units: Mapping[str, object],
    characters: Mapping[str, object],
    panel_cast: Mapping[str, object],
    reaction_segments: Mapping[str, object],
    presentation_plan: Mapping[str, object],
    output_profile: Mapping[str, object],
) -> str:
    """동일 Canonical JSON에서 Marker 없는 사람용 Broadcast View를 만든다."""
    validate_source_style_contract(output_profile)
    document_contract = profile_mapping(output_profile, "document_contract")
    render_contract = profile_mapping(output_profile, "render_contract")
    filter_contract = profile_mapping(output_profile, "filter_contract")
    included_segment_types = set(
        profile_strings(filter_contract, "included_segment_types")
    )
    excluded_segment_types = set(
        profile_strings(filter_contract, "excluded_segment_types")
    )
    if included_segment_types != {"DRAMA", "NARRATION", "PANEL_REACTION"}:
        raise fail(
            "BROADCAST_READABLE_OUTPUT_PROFILE_INVALID",
            "included_segment_types는 현재 Canonical Broadcast Layer 전체여야 합니다.",
        )
    if included_segment_types & excluded_segment_types:
        raise fail(
            "BROADCAST_READABLE_OUTPUT_PROFILE_INVALID",
            "포함·제외 Segment 유형이 겹칩니다.",
        )
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
    labels = scene_labels(screenplay_units, document_contract)
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

    metadata_templates = profile_mapping(document_contract, "metadata_templates")
    lines = [
        format_profile_template(
            profile_string(document_contract, "title_template"),
            {"title": title},
            "title_template",
        ),
        "",
        format_profile_template(
            profile_string(metadata_templates, "project"),
            {"project_id": project_id},
            "metadata_templates.project",
        ),
        format_profile_template(
            profile_string(metadata_templates, "source_truth"),
            {"source_truth_classification": truth_classification},
            "metadata_templates.source_truth",
        ),
        profile_string(metadata_templates, "generation_basis"),
        "",
        *render_cast_sections(
            screenplay_units,
            character_map,
            panel_cast,
            document_contract,
        ),
        "",
    ]
    used_reaction_ids: set[str] = set()
    seen_turn_ids: set[str] = set()
    used_unit_segment_ids: set[str] = set()
    panel_index = 1
    for scene in sorted_scenes(screenplay_units):
        scene_id = required_string(scene, "scene_id")
        lines.extend(
            (
                format_profile_template(
                    profile_string(document_contract, "scene_heading_template"),
                    {"scene_label": labels[scene_id]},
                    "scene_heading_template",
                ),
                "",
                render_scene_context(scene, labels, document_contract),
                "",
            )
        )
        planned_segments = plan_by_scene.get(scene_id, [])
        declared_segment_ids = string_items(scene, "segment_ids")
        planned_segment_ids = [
            required_string(segment, "segment_id") for segment in planned_segments
        ]
        declared_segment_id_set = set(declared_segment_ids)
        ordered_declared_segment_ids = [
            segment_id
            for segment_id in planned_segment_ids
            if segment_id in declared_segment_id_set
        ]
        unit_segment_ids = {
            segment_id
            for segment_id, records in records_by_segment.items()
            if any(record_scene_id == scene_id for record_scene_id, _unit in records)
        }
        if (
            declared_segment_ids != ordered_declared_segment_ids
            or not unit_segment_ids.issubset(declared_segment_id_set)
        ):
            raise fail(
                "BROADCAST_READABLE_SCENE_SEGMENTS_MISMATCH",
                f"{scene_id}의 Scene/Presentation Segment 순서가 다릅니다: "
                f"declared={declared_segment_ids}, planned={planned_segment_ids}, "
                f"unit_segments={sorted(unit_segment_ids)}",
            )
        for segment in planned_segments:
            segment_id = required_string(segment, "segment_id")
            segment_type = required_string(segment, "segment_type")
            records = records_by_segment.get(segment_id, [])
            if segment_type in excluded_segment_types:
                if records:
                    raise fail(
                        "BROADCAST_READABLE_EXCLUDED_SEGMENT_HAS_UNITS",
                        f"제외 Segment에 Screenplay Unit이 있습니다: {segment_id}",
                    )
                continue
            if segment_type not in included_segment_types:
                raise fail(
                    "BROADCAST_READABLE_SEGMENT_UNSUPPORTED",
                    f"Profile이 분류하지 않은 Segment 유형입니다: {segment_type}",
                )
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
                    lines.extend(
                        (render_readable_unit(unit, character_map, render_contract), "")
                    )
                used_unit_segment_ids.add(segment_id)
                continue
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
            lines.extend(
                (
                    format_profile_template(
                        profile_string(
                            document_contract,
                            "panel_section_heading_template",
                        ),
                        {"index": panel_index},
                        "panel_section_heading_template",
                    ),
                    "",
                )
            )
            for block in render_panel_turns(
                reaction,
                panelist_map,
                seen_turn_ids,
                render_contract,
            ):
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
    output = "\n".join(lines[:-1]) + "\n"
    forbidden_markers = profile_strings(
        filter_contract,
        "forbidden_internal_markers",
    )
    if truth_classification == "ORIGINAL_FICTION":
        forbidden_markers.extend(
            profile_strings(
                filter_contract,
                "original_fiction_forbidden_uncertainty_markers",
            )
        )
    matches = sorted(marker for marker in forbidden_markers if marker in output)
    if matches:
        raise fail(
            "BROADCAST_READABLE_FORBIDDEN_MARKER",
            f"사람용 Broadcast에 금지 Marker가 노출되었습니다: {matches}",
        )
    return output
