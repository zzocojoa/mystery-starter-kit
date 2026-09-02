"""Broadcast Readable 2.0.0 Source-style 문서를 결정론적으로 렌더링한다."""

from collections.abc import Mapping, Sequence

from RUNTIME.broadcast_readable_renderer import (
    format_profile_template,
    panelists_by_id,
    profile_mapping,
    profile_string,
    profile_strings,
    render_broadcast_readable_script,
    render_panel_turns,
    render_readable_unit,
)
from RUNTIME.screenplay_renderers import (
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

EXPECTED_SOURCE_STYLE_CONTRACT_V2: dict[str, str] = {
    "ordering_source": "PRESENTATION_PLAN_GLOBAL",
    "unit_text_policy": "CANONICAL_EXACT",
    "character_name_source": "CHARACTERS_NAME",
    "relationship_source": "RELATIONSHIPS_DISPLAY_SUMMARY",
    "panel_name_source": "PANEL_CAST_DISPLAY_NAME",
    "scene_start_context_position": "BEFORE_FIRST_SCENE_SEGMENT",
    "retrospective_position": "AFTER_LAST_SCENE_SEGMENT",
    "scene_reentry_policy": "CONTINUATION_HEADING",
    "internal_identifier_visibility": "HIDDEN",
    "unknown_identity_policy": "FAIL",
}
EXPECTED_HEADINGS = ["정리 기준", "등장인물", "패널", "방송 대본"]
EXPECTED_CONTEXT_GROUPS: dict[str, tuple[str, tuple[str, ...], bool]] = {
    "SITUATION": (
        "SCENE_START",
        (
            "location_description",
            "time_description",
            "previous_scene_id",
            "opening_character_state",
            "opening_emotional_state",
            "audience_information_gain",
        ),
        False,
    ),
    "SOUND_ACTION": (
        "SCENE_START",
        (
            "background_music_description",
            "sound_cues",
            "action_summary",
        ),
        False,
    ),
    "RETROSPECTIVE": (
        "SCENE_END",
        ("retrospective_meaning",),
        True,
    ),
}
SUPPORTED_SEGMENT_TYPES = frozenset({"DRAMA", "NARRATION", "PANEL_REACTION"})
EMPTY_RETROSPECTIVE_VALUES = frozenset({"", "—", "없음", "해당 없음", "N/A"})


def validate_v2_profile(output_profile: Mapping[str, object]) -> None:
    """v2 Renderer가 구현하는 Profile 의미를 정확히 대조한다."""
    if (
        output_profile.get("profile_id") != "BROADCAST_READABLE_SCRIPT"
        or output_profile.get("profile_version") != "2.0.0"
        or output_profile.get("schema_version") != "2.0.0"
    ):
        raise fail(
            "BROADCAST_READABLE_V2_PROFILE_IDENTITY_INVALID",
            "v2 Renderer에는 BROADCAST_READABLE_SCRIPT@2.0.0이 필요합니다.",
        )
    source_style = profile_mapping(output_profile, "source_style_contract")
    if dict(source_style) != EXPECTED_SOURCE_STYLE_CONTRACT_V2:
        raise fail(
            "BROADCAST_READABLE_V2_SOURCE_STYLE_CONTRACT_UNSUPPORTED",
            "Renderer가 지원하지 않는 v2 Source-style 계약입니다.",
        )
    document_contract = profile_mapping(output_profile, "document_contract")
    if profile_strings(document_contract, "required_headings") != EXPECTED_HEADINGS:
        raise fail(
            "BROADCAST_READABLE_V2_HEADING_CONTRACT_INVALID",
            "v2 필수 Heading 네 개가 정확한 순서로 필요합니다.",
        )
    groups = mapping_items(document_contract.get("context_groups"), "context_groups")
    actual_group_ids = [required_string(group, "group_id") for group in groups]
    if actual_group_ids != list(EXPECTED_CONTEXT_GROUPS):
        raise fail(
            "BROADCAST_READABLE_V2_CONTEXT_CONTRACT_INVALID",
            f"Context Group 순서가 다릅니다: {actual_group_ids}",
        )
    for group in groups:
        group_id = required_string(group, "group_id")
        expected_position, expected_fields, expected_omit = EXPECTED_CONTEXT_GROUPS[
            group_id
        ]
        if (
            group.get("position") != expected_position
            or tuple(string_items(group, "fields")) != expected_fields
            or group.get("omit_when_empty") is not expected_omit
        ):
            raise fail(
                "BROADCAST_READABLE_V2_CONTEXT_CONTRACT_INVALID",
                f"Context Group 의미가 다릅니다: group_id={group_id}",
            )
    segment_contract = profile_mapping(output_profile, "segment_contract")
    if (
        set(profile_strings(segment_contract, "supported_segment_types"))
        != SUPPORTED_SEGMENT_TYPES
        or segment_contract.get("unsupported_segment_policy") != "FAIL"
    ):
        raise fail(
            "BROADCAST_READABLE_V2_SEGMENT_CONTRACT_INVALID",
            "v2 Segment 지원 범위와 FAIL 정책이 다릅니다.",
        )


def matching_project_id_v2(documents: Sequence[Mapping[str, object]]) -> str:
    """v2 Canonical 입력의 Project ID가 모두 같은지 확인한다."""
    project_ids = [required_string(document, "project_id") for document in documents]
    if len(set(project_ids)) != 1:
        raise fail(
            "BROADCAST_READABLE_PROJECT_MISMATCH",
            f"Canonical 입력의 project_id가 다릅니다: {project_ids}",
        )
    return project_ids[0]


def scenes_by_id(
    screenplay_units: Mapping[str, object],
) -> dict[str, Mapping[str, object]]:
    """순서 검증된 Scene을 고유 ID로 색인한다."""
    result: dict[str, Mapping[str, object]] = {}
    for scene in sorted_scenes(screenplay_units):
        scene_id = required_string(scene, "scene_id")
        if scene_id in result:
            raise fail(
                "BROADCAST_READABLE_SCENE_DUPLICATED",
                f"중복 Scene ID입니다: {scene_id}",
            )
        result[scene_id] = scene
    return result


def scene_order_and_title(scene: Mapping[str, object]) -> tuple[int, str]:
    """사람용 Heading에 사용할 Scene 순서와 제목을 반환한다."""
    order = scene.get("order")
    if not isinstance(order, int) or isinstance(order, bool):
        raise fail(
            "BROADCAST_READABLE_SCENE_SEQUENCE_INVALID",
            f"Scene order가 정수가 아닙니다: {order!r}",
        )
    return order, normalize_line_endings(required_string(scene, "title"))


def scene_reference(
    scene: Mapping[str, object],
    document_contract: Mapping[str, object],
) -> str:
    """Raw Scene ID를 사람이 읽는 장면 참조로 변환한다."""
    order, title = scene_order_and_title(scene)
    return format_profile_template(
        profile_string(document_contract, "scene_reference_template"),
        {"order": order, "title": title},
        "scene_reference_template",
    )


def context_value_v2(
    field: str,
    value: object,
    scene_map: Mapping[str, Mapping[str, object]],
    document_contract: Mapping[str, object],
) -> str:
    """Scene 참조를 Raw ID 없이 변환하고 나머지 Context를 보존한다."""
    if field != "previous_scene_id":
        return render_context_value(field, value)
    if value is None:
        return profile_string(document_contract, "no_previous_scene_label")
    if not isinstance(value, str) or value not in scene_map:
        raise fail(
            "BROADCAST_READABLE_PREVIOUS_SCENE_INVALID",
            f"직전 Scene 참조를 해석할 수 없습니다: {value!r}",
        )
    return scene_reference(scene_map[value], document_contract)


def meaningful_retrospective(value: object) -> str | None:
    """의미 없는 Placeholder를 제외한 재해석 원문을 반환한다."""
    if value is None:
        return None
    if not isinstance(value, str):
        raise fail(
            "BROADCAST_READABLE_RETROSPECTIVE_INVALID",
            "retrospective_meaning은 문자열 또는 null이어야 합니다.",
        )
    normalized = normalize_line_endings(value)
    if normalized.strip() in EMPTY_RETROSPECTIVE_VALUES:
        return None
    return normalized


def render_context_group_v2(
    scene: Mapping[str, object],
    group: Mapping[str, object],
    scene_map: Mapping[str, Mapping[str, object]],
    document_contract: Mapping[str, object],
) -> str | None:
    """Profile의 한 Context Group을 위치 의미에 맞게 렌더링한다."""
    context = required_mapping(scene, "context")
    group_id = required_string(group, "group_id")
    template = profile_string(group, "template")
    fields = string_items(group, "fields")
    if group_id == "RETROSPECTIVE":
        retrospective = meaningful_retrospective(context.get(fields[0]))
        if retrospective is None:
            return None
        return format_profile_template(
            template,
            {"content": retrospective},
            "context_groups.RETROSPECTIVE.template",
        )
    labels = profile_mapping(document_contract, "context_labels")
    entry_template = profile_string(document_contract, "context_entry_template")
    entries: list[str] = []
    for field in fields:
        entries.append(
            format_profile_template(
                entry_template,
                {
                    "label": profile_string(labels, field),
                    "value": context_value_v2(
                        field,
                        context.get(field),
                        scene_map,
                        document_contract,
                    ),
                },
                "context_entry_template",
            )
        )
    content = profile_string(document_contract, "context_separator").join(entries)
    return format_profile_template(
        template,
        {"content": content},
        f"context_groups.{group_id}.template",
    )


def relationship_texts_v2(
    relationships: Mapping[str, object],
    character_map: Mapping[str, Mapping[str, object]],
    separator: str,
) -> dict[str, str]:
    """Relationship를 ID 순서로 인물별 3열 표 문구에 집계한다."""
    values: dict[str, list[str]] = {character_id: [] for character_id in character_map}
    records = mapping_items(relationships.get("relationships"), "relationships")
    sorted_records = sorted(records, key=lambda item: required_string(item, "relationship_id"))
    for relationship in sorted_records:
        from_id = required_string(relationship, "from")
        to_id = required_string(relationship, "to")
        if from_id not in character_map or to_id not in character_map:
            raise fail(
                "BROADCAST_READABLE_RELATIONSHIP_CHARACTER_UNKNOWN",
                f"Relationship가 알 수 없는 인물을 참조합니다: {from_id}, {to_id}",
            )
        from_name = required_string(character_map[from_id], "name")
        to_name = required_string(character_map[to_id], "name")
        summary_value = relationship.get("display_summary")
        if relationships.get("schema_version") == "1.1.0" and (
            not isinstance(summary_value, str) or not summary_value.strip()
        ):
            raise fail(
                "BROADCAST_READABLE_RELATIONSHIP_SUMMARY_MISSING",
                "relationships@1.1.0에는 display_summary가 필요합니다.",
            )
        summary = (
            normalize_line_endings(summary_value)
            if isinstance(summary_value, str) and summary_value.strip()
            else "기존 계약에서 연결된 관계"
        )
        values[from_id].append(f"{to_name}: {summary}")
        values[to_id].append(f"{from_name}: {summary}")
    return {
        character_id: separator.join(entries) if entries else "—"
        for character_id, entries in values.items()
    }


def render_cast_sections_v2(
    screenplay_units: Mapping[str, object],
    characters: Mapping[str, object],
    relationships: Mapping[str, object],
    panel_cast: Mapping[str, object],
    document_contract: Mapping[str, object],
) -> list[str]:
    """3열 등장인물 관계표와 2열 Panel 표를 렌더링한다."""
    character_map = characters_by_id(characters)
    character_columns = profile_strings(document_contract, "character_table_columns")
    panel_columns = profile_strings(document_contract, "panel_table_columns")
    if character_columns != ["인물", "역할", "관계"] or len(panel_columns) != 2:
        raise fail(
            "BROADCAST_READABLE_V2_TABLE_CONTRACT_INVALID",
            "등장인물 표는 3열, Panel 표는 2열이어야 합니다.",
        )
    relationship_text = relationship_texts_v2(
        relationships,
        character_map,
        profile_string(document_contract, "relationship_separator"),
    )
    lines = [
        "## 등장인물",
        "",
        f"| {' | '.join(character_columns)} |",
        profile_string(document_contract, "character_table_divider"),
    ]
    for character_id in cast_order(screenplay_units, character_map):
        character = character_map[character_id]
        lines.append(
            format_profile_template(
                profile_string(document_contract, "character_table_row_template"),
                {
                    "name": markdown_cell(required_string(character, "name")),
                    "role": markdown_cell(required_string(character, "role")),
                    "relationships": markdown_cell(relationship_text[character_id]),
                },
                "character_table_row_template",
            )
        )
    lines.extend(
        (
            "",
            "## 패널",
            "",
            f"| {' | '.join(panel_columns)} |",
            profile_string(document_contract, "panel_table_divider"),
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


def scene_segment_bounds(
    segments: Sequence[Mapping[str, object]],
) -> tuple[dict[str, int], dict[str, int]]:
    """각 Scene의 첫·마지막 전역 Segment Index를 계산한다."""
    first: dict[str, int] = {}
    last: dict[str, int] = {}
    for index, segment in enumerate(segments):
        scene_id = required_string(segment, "scene_id")
        first.setdefault(scene_id, index)
        last[scene_id] = index
    return first, last


def validate_scene_segment_bindings(
    scene_map: Mapping[str, Mapping[str, object]],
    segments: Sequence[Mapping[str, object]],
    records_by_segment: Mapping[str, Sequence[tuple[str, Mapping[str, object]]]],
) -> None:
    """Scene 선언과 전역 Presentation·Unit Segment 결속을 검증한다."""
    planned_by_scene: dict[str, list[str]] = {scene_id: [] for scene_id in scene_map}
    seen_segment_ids: set[str] = set()
    for segment in segments:
        segment_id = required_string(segment, "segment_id")
        scene_id = required_string(segment, "scene_id")
        segment_type = required_string(segment, "segment_type")
        if segment_id in seen_segment_ids:
            raise fail(
                "BROADCAST_READABLE_SEGMENT_DUPLICATED",
                f"중복 Presentation Segment입니다: {segment_id}",
            )
        seen_segment_ids.add(segment_id)
        if scene_id not in scene_map:
            raise fail(
                "BROADCAST_READABLE_SCENE_UNKNOWN",
                f"Presentation이 알 수 없는 Scene을 참조합니다: {scene_id}",
            )
        if segment_type not in SUPPORTED_SEGMENT_TYPES:
            raise fail(
                "BROADCAST_READABLE_UNSUPPORTED_SEGMENT_TYPE",
                f"v2에서 지원하지 않는 Segment입니다: {segment_type}",
            )
        planned_by_scene[scene_id].append(segment_id)
    for scene_id, scene in scene_map.items():
        declared = string_items(scene, "segment_ids")
        planned = planned_by_scene[scene_id]
        unit_segments = {
            segment_id
            for segment_id, records in records_by_segment.items()
            if any(record_scene_id == scene_id for record_scene_id, _unit in records)
        }
        if not planned or declared != planned or not unit_segments.issubset(set(declared)):
            raise fail(
                "BROADCAST_READABLE_SCENE_SEGMENTS_MISMATCH",
                f"Scene/Presentation Segment 결속이 다릅니다: scene_id={scene_id}, "
                f"declared={declared}, planned={planned}, units={sorted(unit_segments)}",
            )


def visible_forbidden_tokens(
    output: str,
    truth_classification: str,
    output_profile: Mapping[str, object],
) -> list[str]:
    """실제 가시 Markdown에서 금지 ID·Comment·불확실성 Token을 찾는다."""
    contract = profile_mapping(output_profile, "visibility_contract")
    tokens = [
        *profile_strings(contract, "forbidden_visible_prefixes"),
        *profile_strings(contract, "forbidden_html_comment_tokens"),
    ]
    if truth_classification == "ORIGINAL_FICTION":
        tokens.extend(
            profile_strings(
                contract,
                "original_fiction_forbidden_uncertainty_markers",
            )
        )
    return sorted(token for token in tokens if token in output)


def render_broadcast_readable_script_v2(
    screenplay_units: Mapping[str, object],
    characters: Mapping[str, object],
    relationships: Mapping[str, object],
    panel_cast: Mapping[str, object],
    reaction_segments: Mapping[str, object],
    presentation_plan: Mapping[str, object],
    output_profile: Mapping[str, object],
) -> str:
    """전역 Presentation 순서를 보존한 Source-style v2 Markdown을 만든다."""
    validate_v2_profile(output_profile)
    matching_project_id_v2(
        (
            screenplay_units,
            characters,
            relationships,
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
    document_contract = profile_mapping(output_profile, "document_contract")
    render_contract = profile_mapping(output_profile, "render_contract")
    context_groups = mapping_items(
        document_contract.get("context_groups"),
        "context_groups",
    )
    start_groups = [group for group in context_groups if group.get("position") == "SCENE_START"]
    end_group = next(
        group for group in context_groups if group.get("position") == "SCENE_END"
    )
    scene_map = scenes_by_id(screenplay_units)
    character_map = characters_by_id(characters)
    panelist_map = panelists_by_id(panel_cast)
    reactions = reaction_by_id(reaction_segments)
    records_by_segment = unit_records_by_segment(screenplay_units)
    segments = presentation_segments(presentation_plan)
    validate_scene_segment_bindings(scene_map, segments, records_by_segment)
    first_segment, last_segment = scene_segment_bounds(segments)

    lines = [
        format_profile_template(
            profile_string(document_contract, "title_template"),
            {"title": title},
            "title_template",
        ),
        "",
        "## 정리 기준",
        "",
        *profile_strings(document_contract, "organizing_principle_templates"),
        "",
        *render_cast_sections_v2(
            screenplay_units,
            characters,
            relationships,
            panel_cast,
            document_contract,
        ),
        "",
        "## 방송 대본",
        "",
    ]
    seen_scenes: set[str] = set()
    used_unit_segment_ids: set[str] = set()
    used_reaction_ids: set[str] = set()
    seen_turn_ids: set[str] = set()
    previous_scene_id: str | None = None
    panel_index = 1
    for global_index, segment in enumerate(segments):
        segment_id = required_string(segment, "segment_id")
        segment_type = required_string(segment, "segment_type")
        scene_id = required_string(segment, "scene_id")
        scene = scene_map[scene_id]
        order, scene_title = scene_order_and_title(scene)
        if global_index == first_segment[scene_id]:
            lines.extend(
                (
                    format_profile_template(
                        profile_string(document_contract, "scene_heading_template"),
                        {"order": order, "title": scene_title},
                        "scene_heading_template",
                    ),
                    "",
                )
            )
            for group in start_groups:
                rendered_group = render_context_group_v2(
                    scene,
                    group,
                    scene_map,
                    document_contract,
                )
                if rendered_group is None:
                    raise fail(
                        "BROADCAST_READABLE_CONTEXT_MISSING",
                        f"Scene 시작 Context가 비었습니다: {scene_id}",
                    )
                lines.extend((rendered_group, ""))
            seen_scenes.add(scene_id)
        elif previous_scene_id != scene_id:
            if scene_id not in seen_scenes:
                raise fail(
                    "BROADCAST_READABLE_SCENE_BOUNDARY_INVALID",
                    f"Scene 첫 Segment 경계가 일치하지 않습니다: {scene_id}",
                )
            lines.extend(
                (
                    format_profile_template(
                        profile_string(
                            document_contract,
                            "scene_resume_heading_template",
                        ),
                        {"order": order, "title": scene_title},
                        "scene_resume_heading_template",
                    ),
                    "",
                )
            )

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
                    if record_scene_id != scene_id
                    or required_string(unit, "type") not in expected_types
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
        else:
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
                            render_contract,
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

        if global_index == last_segment[scene_id]:
            retrospective = render_context_group_v2(
                scene,
                end_group,
                scene_map,
                document_contract,
            )
            if retrospective is not None:
                lines.extend((retrospective, ""))
        previous_scene_id = scene_id

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
    forbidden = visible_forbidden_tokens(
        output,
        truth_classification,
        output_profile,
    )
    if forbidden:
        raise fail(
            "BROADCAST_READABLE_VISIBLE_TOKEN_FORBIDDEN",
            f"가시 Markdown에 금지 Token이 있습니다: {forbidden}",
        )
    return output


def render_broadcast_readable_script_versioned(
    screenplay_units: Mapping[str, object],
    characters: Mapping[str, object],
    relationships: Mapping[str, object] | None,
    panel_cast: Mapping[str, object],
    reaction_segments: Mapping[str, object],
    presentation_plan: Mapping[str, object],
    output_profile: Mapping[str, object],
) -> str:
    """Profile Version에 따라 불변 v1 또는 Source-style v2 Renderer를 선택한다."""
    profile_version = output_profile.get("profile_version")
    if profile_version == "1.0.0":
        return render_broadcast_readable_script(
            screenplay_units,
            characters,
            panel_cast,
            reaction_segments,
            presentation_plan,
            output_profile,
        )
    if profile_version == "2.0.0":
        if relationships is None:
            raise fail(
                "BROADCAST_READABLE_RELATIONSHIPS_MISSING",
                "v2 Renderer에는 relationships가 필요합니다.",
            )
        return render_broadcast_readable_script_v2(
            screenplay_units,
            characters,
            relationships,
            panel_cast,
            reaction_segments,
            presentation_plan,
            output_profile,
        )
    raise fail(
        "BROADCAST_READABLE_PROFILE_VERSION_UNSUPPORTED",
        f"지원하지 않는 Readable Profile Version입니다: {profile_version!r}",
    )
