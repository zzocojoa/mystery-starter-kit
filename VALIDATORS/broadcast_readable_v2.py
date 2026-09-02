"""Broadcast Readable v2 Actual Markdown의 독립 증거와 Report를 검증한다."""

from collections import Counter, defaultdict
from collections.abc import Mapping, Sequence
from hashlib import sha256

from RUNTIME.broadcast_readable_renderer import (
    format_profile_template,
    profile_mapping,
    profile_string,
    profile_strings,
)
from RUNTIME.broadcast_readable_v2_renderer import (
    EMPTY_RETROSPECTIVE_VALUES,
    render_broadcast_readable_script_v2,
)
from RUNTIME.screenplay_renderers import (
    CHARACTER_AUTHORED_TYPES,
    cast_order,
    characters_by_id,
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
from VALIDATORS.candidate_evaluation import document_sha256
from VALIDATORS.exceptions import ConfigurationError
from VALIDATORS.models import ValidationIssue

READABLE_PATH = "07_SCRIPT/broadcast_readable_script.md"
REPORT_PATH = "08_QA/broadcast_readable_report.json"
PROFILE_PATH = (
    "CHANNELS/mystery_main/output_profiles/broadcast-readable-script/2.0.0.json"
)
PROFILE_SCHEMA_PATH = "STANDARD/schemas/broadcast_readable_output_profile_2_0.schema.json"


def v2_issue(
    code: str,
    message: str,
    artifact: str,
    context: dict[str, object],
) -> ValidationIssue:
    """v2 Readable 검증 문제를 표준 Issue로 반환한다."""
    return ValidationIssue(
        severity="ERROR",
        code=code,
        message=message,
        artifact=artifact,
        context=context,
    )


def text_sha256(value: str) -> str:
    """LF 정규화 외 변경 없는 Text의 SHA-256을 계산한다."""
    return sha256(normalize_line_endings(value).encode("utf-8")).hexdigest()


def byte_offset(value: str, character_offset: int) -> int:
    """문자 위치를 UTF-8 Byte 위치로 변환한다."""
    return len(value[:character_offset].encode("utf-8"))


def occurrence_ranges(value: str, fragment: str) -> list[dict[str, int]]:
    """겹치지 않는 모든 Exact Fragment의 UTF-8 Byte 범위를 반환한다."""
    if not fragment:
        raise ConfigurationError("BROADCAST_READABLE_V2_EMPTY_FRAGMENT")
    ranges: list[dict[str, int]] = []
    start = 0
    while True:
        index = value.find(fragment, start)
        if index < 0:
            return ranges
        end = index + len(fragment)
        ranges.append(
            {
                "byte_start": byte_offset(value, index),
                "byte_end": byte_offset(value, end),
            }
        )
        start = end


def range_for_occurrence(
    ranges: Sequence[dict[str, int]],
    occurrence_index: int,
) -> dict[str, int] | None:
    """1-based Exact 발생 번호에 해당하는 Byte 범위를 반환한다."""
    if occurrence_index < 1 or occurrence_index > len(ranges):
        return None
    return dict(ranges[occurrence_index - 1])


def required_byte_start(value: object) -> int:
    """Byte Range에서 검증된 시작 위치를 반환한다."""
    if not isinstance(value, Mapping):
        raise ConfigurationError("BROADCAST_READABLE_V2_BYTE_RANGE_INVALID")
    byte_start = value.get("byte_start")
    if not isinstance(byte_start, int) or isinstance(byte_start, bool):
        raise ConfigurationError("BROADCAST_READABLE_V2_BYTE_START_INVALID")
    return byte_start


def visible_match_sort_key(item: Mapping[str, object]) -> tuple[int, str]:
    """가시성 위반을 Byte 위치와 Token으로 정렬할 Key를 반환한다."""
    return required_byte_start(item), str(item.get("token"))


def scene_map(
    screenplay_units: Mapping[str, object],
) -> dict[str, Mapping[str, object]]:
    """순서 검증된 Scene을 고유 ID로 색인한다."""
    result: dict[str, Mapping[str, object]] = {}
    for scene in sorted_scenes(screenplay_units):
        scene_id = required_string(scene, "scene_id")
        if scene_id in result:
            raise ConfigurationError(
                f"BROADCAST_READABLE_SCENE_DUPLICATED: scene_id={scene_id}"
            )
        result[scene_id] = scene
    return result


def scene_order_title(scene: Mapping[str, object]) -> tuple[int, str]:
    """Scene Heading의 순서와 제목을 검증해 반환한다."""
    order = scene.get("order")
    if not isinstance(order, int) or isinstance(order, bool):
        raise ConfigurationError(
            f"BROADCAST_READABLE_SCENE_SEQUENCE_INVALID: order={order!r}"
        )
    return order, normalize_line_endings(required_string(scene, "title"))


def scene_reference_text(
    scene: Mapping[str, object],
    document_contract: Mapping[str, object],
) -> str:
    """독립 Verifier가 기대하는 사람용 Scene 참조를 만든다."""
    order, title = scene_order_title(scene)
    return format_profile_template(
        profile_string(document_contract, "scene_reference_template"),
        {"order": order, "title": title},
        "scene_reference_template",
    )


def verifier_context_value(
    field: str,
    value: object,
    scenes: Mapping[str, Mapping[str, object]],
    document_contract: Mapping[str, object],
) -> str:
    """Actual Context 비교용 값을 Renderer 상태 없이 계산한다."""
    if field != "previous_scene_id":
        return render_context_value(field, value)
    if value is None:
        return profile_string(document_contract, "no_previous_scene_label")
    if not isinstance(value, str) or value not in scenes:
        raise ConfigurationError(
            f"BROADCAST_READABLE_PREVIOUS_SCENE_INVALID: value={value!r}"
        )
    return scene_reference_text(scenes[value], document_contract)


def verifier_context_block(
    scene: Mapping[str, object],
    group: Mapping[str, object],
    scenes: Mapping[str, Mapping[str, object]],
    document_contract: Mapping[str, object],
) -> str | None:
    """Actual Markdown에서 찾을 Context Block을 독립 계산한다."""
    context = required_mapping(scene, "context")
    fields = string_items(group, "fields")
    group_id = required_string(group, "group_id")
    template = profile_string(group, "template")
    if group_id == "RETROSPECTIVE":
        raw_value = context.get(fields[0])
        if raw_value is None:
            return None
        if not isinstance(raw_value, str):
            raise ConfigurationError(
                "BROADCAST_READABLE_RETROSPECTIVE_INVALID: 문자열 또는 null이 필요합니다."
            )
        normalized = normalize_line_endings(raw_value)
        if normalized.strip() in EMPTY_RETROSPECTIVE_VALUES:
            return None
        return format_profile_template(
            template,
            {"content": normalized},
            "context_groups.RETROSPECTIVE.template",
        )
    labels = profile_mapping(document_contract, "context_labels")
    entry_template = profile_string(document_contract, "context_entry_template")
    entries = [
        format_profile_template(
            entry_template,
            {
                "label": profile_string(labels, field),
                "value": verifier_context_value(
                    field,
                    context.get(field),
                    scenes,
                    document_contract,
                ),
            },
            "context_entry_template",
        )
        for field in fields
    ]
    return format_profile_template(
        template,
        {
            "content": profile_string(
                document_contract,
                "context_separator",
            ).join(entries)
        },
        f"context_groups.{group_id}.template",
    )


def verifier_delivery_block(
    unit: Mapping[str, object],
    render_contract: Mapping[str, object],
) -> str:
    """Canonical Delivery를 Actual Unit Block 비교용 문자열로 만든다."""
    raw_delivery = unit.get("delivery")
    if raw_delivery is None:
        return ""
    if not isinstance(raw_delivery, Mapping):
        raise ConfigurationError("BROADCAST_READABLE_DELIVERY_INVALID")
    instruction = normalize_line_endings(required_string(raw_delivery, "instruction"))
    instruction = instruction.replace(
        "\n",
        profile_string(render_contract, "delivery_line_separator"),
    )
    return format_profile_template(
        profile_string(render_contract, "delivery_template"),
        {"instruction": instruction},
        "delivery_template",
    )


def verifier_unit_block(
    unit: Mapping[str, object],
    characters: Mapping[str, Mapping[str, object]],
    render_contract: Mapping[str, object],
) -> str:
    """Actual Markdown에서 찾을 Unit 가시 Block을 독립 계산한다."""
    unit_type = required_string(unit, "type")
    text = normalize_line_endings(required_string(unit, "text"))
    simple_template = {
        "ACTION": "direction_template",
        "SOUND": "sound_template",
        "SCREEN_TEXT": "screen_text_template",
    }.get(unit_type)
    if simple_template is not None:
        return format_profile_template(
            profile_string(render_contract, simple_template),
            {"text": text},
            simple_template,
        )
    speaker_id = required_string(unit, "speaker_id")
    character = characters.get(speaker_id)
    if character is None:
        raise ConfigurationError(
            f"BROADCAST_READABLE_SPEAKER_UNKNOWN: speaker_id={speaker_id}"
        )
    speaker_name = normalize_line_endings(required_string(character, "name"))
    delivery_block = verifier_delivery_block(unit, render_contract)
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
        raise ConfigurationError(
            f"BROADCAST_READABLE_UNIT_TYPE_UNSUPPORTED: unit_type={unit_type}"
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


def verifier_panel_turn_block(
    turn: Mapping[str, object],
    panelists: Mapping[str, Mapping[str, object]],
    render_contract: Mapping[str, object],
) -> str:
    """Actual Markdown에서 찾을 Panel Turn Block을 독립 계산한다."""
    panelist_id = required_string(turn, "panelist_id")
    panelist = panelists.get(panelist_id)
    if panelist is None:
        raise ConfigurationError(
            f"BROADCAST_READABLE_PANELIST_UNKNOWN: panelist_id={panelist_id}"
        )
    return format_profile_template(
        profile_string(render_contract, "panel_turn_template"),
        {
            "display_name": normalize_line_endings(
                required_string(panelist, "display_name")
            ),
            "spoken_line": normalize_line_endings(required_string(turn, "spoken_line")),
        },
        "panel_turn_template",
    )


def panelists_by_id_v2(
    panel_cast: Mapping[str, object],
) -> dict[str, Mapping[str, object]]:
    """Panelist를 ID로 색인하고 중복을 거부한다."""
    result: dict[str, Mapping[str, object]] = {}
    for panelist in mapping_items(panel_cast.get("panelists"), "panelists"):
        panelist_id = required_string(panelist, "panelist_id")
        if panelist_id in result:
            raise ConfigurationError(
                f"BROADCAST_READABLE_PANELIST_DUPLICATED: panelist_id={panelist_id}"
            )
        result[panelist_id] = panelist
    return result


def relationship_rows_and_mappings(
    relationships: Mapping[str, object],
    characters: Mapping[str, Mapping[str, object]],
    character_order: Sequence[str],
    document_contract: Mapping[str, object],
    actual_markdown: str,
) -> tuple[list[dict[str, object]], list[ValidationIssue]]:
    """3열 관계표 Actual Row와 Relationship별 결속을 독립 검증한다."""
    records = sorted(
        mapping_items(relationships.get("relationships"), "relationships"),
        key=lambda item: required_string(item, "relationship_id"),
    )
    entries: dict[str, list[str]] = {character_id: [] for character_id in characters}
    mappings: list[dict[str, object]] = []
    issues: list[ValidationIssue] = []
    for relationship in records:
        relationship_id = required_string(relationship, "relationship_id")
        from_id = required_string(relationship, "from")
        to_id = required_string(relationship, "to")
        summary = required_string(relationship, "display_summary")
        if from_id not in characters or to_id not in characters:
            issues.append(
                v2_issue(
                    "BROADCAST_READABLE_V2_RELATIONSHIP_CHARACTER_UNKNOWN",
                    "Relationship가 미등록 인물을 참조합니다.",
                    READABLE_PATH,
                    {"relationship_id": relationship_id},
                )
            )
            continue
        from_name = required_string(characters[from_id], "name")
        to_name = required_string(characters[to_id], "name")
        normalized = normalize_line_endings(summary)
        entries[from_id].append(f"{to_name}: {normalized}")
        entries[to_id].append(f"{from_name}: {normalized}")
        mappings.append(
            {
                "relationship_id": relationship_id,
                "affected_character_rows": sorted([from_id, to_id]),
                "display_summary_sha256": text_sha256(normalized),
            }
        )
    separator = profile_string(document_contract, "relationship_separator")
    row_template = profile_string(document_contract, "character_table_row_template")
    for character_id in character_order:
        character = characters[character_id]
        row = format_profile_template(
            row_template,
            {
                "name": markdown_cell(required_string(character, "name")),
                "role": markdown_cell(required_string(character, "role")),
                "relationships": markdown_cell(
                    separator.join(entries[character_id])
                    if entries[character_id]
                    else "—"
                ),
            },
            "character_table_row_template",
        )
        count = len(occurrence_ranges(actual_markdown, row))
        if count != 1:
            issues.append(
                v2_issue(
                    "BROADCAST_READABLE_V2_RELATIONSHIP_ROW_MISMATCH",
                    "Actual 등장인물 관계 Row가 누락·중복·변조되었습니다.",
                    READABLE_PATH,
                    {"character_id": character_id, "actual_count": count},
                )
            )
    return mappings, issues


def visible_matches(
    actual_markdown: str,
    tokens: Sequence[str],
) -> list[dict[str, object]]:
    """금지 Token의 실제 Byte 위치를 모두 반환한다."""
    matches: list[dict[str, object]] = []
    for token in tokens:
        for byte_range in occurrence_ranges(actual_markdown, token):
            matches.append({"token": token, **byte_range})
    return sorted(
        matches,
        key=visible_match_sort_key,
    )


def fragment_occurrence_issues(
    actual_markdown: str,
    expected_fragments: Sequence[str],
    code: str,
    label: str,
) -> list[ValidationIssue]:
    """Canonical Fragment별 기대·실제 발생 횟수 차이를 Issue로 반환한다."""
    issues: list[ValidationIssue] = []
    expected_counts = Counter(expected_fragments)
    for fragment, expected_count in expected_counts.items():
        actual_count = len(occurrence_ranges(actual_markdown, fragment))
        if actual_count != expected_count:
            issues.append(
                v2_issue(
                    code,
                    f"Actual {label}의 발생 횟수가 Canonical과 다릅니다.",
                    READABLE_PATH,
                    {
                        "fragment_sha256": text_sha256(fragment),
                        "expected_count": expected_count,
                        "actual_count": actual_count,
                    },
                )
            )
    return issues


def independent_conformance(
    screenplay_units: Mapping[str, object],
    characters_document: Mapping[str, object],
    relationships: Mapping[str, object],
    panel_cast: Mapping[str, object],
    reaction_segments: Mapping[str, object],
    presentation_plan: Mapping[str, object],
    output_profile: Mapping[str, object],
    actual_markdown: str,
) -> dict[str, object]:
    """Actual Markdown에서 Mapping·Coverage·Issue를 Renderer와 독립 계산한다."""
    document_contract = profile_mapping(output_profile, "document_contract")
    render_contract = profile_mapping(output_profile, "render_contract")
    scenes = scene_map(screenplay_units)
    characters = characters_by_id(characters_document)
    panelists = panelists_by_id_v2(panel_cast)
    reactions = reaction_by_id(reaction_segments)
    segments = presentation_segments(presentation_plan)
    unit_records = unit_records_by_segment(screenplay_units)
    character_order = cast_order(screenplay_units, characters)
    issues: list[ValidationIssue] = []
    relationship_mappings, relationship_issues = relationship_rows_and_mappings(
        relationships,
        characters,
        character_order,
        document_contract,
        actual_markdown,
    )
    issues.extend(relationship_issues)

    groups = mapping_items(document_contract.get("context_groups"), "context_groups")
    situation_group = next(group for group in groups if group.get("group_id") == "SITUATION")
    sound_group = next(group for group in groups if group.get("group_id") == "SOUND_ACTION")
    retrospective_group = next(
        group for group in groups if group.get("group_id") == "RETROSPECTIVE"
    )
    scene_fragments: dict[str, dict[str, str | None]] = {}
    expected_contexts: list[str] = []
    expected_retrospectives: list[str] = []
    for scene_id, scene in scenes.items():
        order, title = scene_order_title(scene)
        heading = format_profile_template(
            profile_string(document_contract, "scene_heading_template"),
            {"order": order, "title": title},
            "scene_heading_template",
        )
        situation = verifier_context_block(
            scene,
            situation_group,
            scenes,
            document_contract,
        )
        sound = verifier_context_block(
            scene,
            sound_group,
            scenes,
            document_contract,
        )
        retrospective = verifier_context_block(
            scene,
            retrospective_group,
            scenes,
            document_contract,
        )
        assert situation is not None and sound is not None
        scene_fragments[scene_id] = {
            "heading": heading,
            "situation": situation,
            "sound": sound,
            "retrospective": retrospective,
        }
        expected_contexts.extend((situation, sound))
        if retrospective is not None:
            expected_retrospectives.append(retrospective)
    issues.extend(
        fragment_occurrence_issues(
            actual_markdown,
            expected_contexts,
            "BROADCAST_READABLE_V2_CONTEXT_OCCURRENCE_MISMATCH",
            "Context Group",
        )
    )
    issues.extend(
        fragment_occurrence_issues(
            actual_markdown,
            expected_retrospectives,
            "BROADCAST_READABLE_V2_RETROSPECTIVE_OCCURRENCE_MISMATCH",
            "Retrospective",
        )
    )

    expected_unit_blocks: list[str] = []
    unit_blocks: dict[str, str] = {}
    for records in unit_records.values():
        for _scene_id, unit in records:
            unit_id = required_string(unit, "unit_id")
            block = verifier_unit_block(unit, characters, render_contract)
            expected_unit_blocks.append(block)
            unit_blocks[unit_id] = block
    issues.extend(
        fragment_occurrence_issues(
            actual_markdown,
            expected_unit_blocks,
            "BROADCAST_READABLE_V2_UNIT_OCCURRENCE_MISMATCH",
            "Unit Block",
        )
    )

    panel_blocks: dict[str, str] = {}
    expected_panel_blocks: list[str] = []
    for reaction in reactions.values():
        for turn in mapping_items(reaction.get("turns"), "turns"):
            turn_id = required_string(turn, "turn_id")
            block = verifier_panel_turn_block(turn, panelists, render_contract)
            panel_blocks[turn_id] = block
            expected_panel_blocks.append(block)
    issues.extend(
        fragment_occurrence_issues(
            actual_markdown,
            expected_panel_blocks,
            "BROADCAST_READABLE_V2_PANEL_TURN_OCCURRENCE_MISMATCH",
            "Panel Turn Block",
        )
    )

    unit_occurrence_index: defaultdict[str, int] = defaultdict(int)
    unit_mappings: list[dict[str, object]] = []
    unit_ranges_by_segment: defaultdict[str, list[dict[str, int]]] = defaultdict(list)
    special_expected = Counter[str]()
    special_actual = Counter[str]()
    for scene in sorted_scenes(screenplay_units):
        units = mapping_items(scene.get("units"), "units")
        for unit in units:
            unit_id = required_string(unit, "unit_id")
            segment_id = required_string(unit, "segment_id")
            unit_type = required_string(unit, "type")
            block = unit_blocks[unit_id]
            unit_occurrence_index[block] += 1
            occurrence_index = unit_occurrence_index[block]
            byte_range = range_for_occurrence(
                occurrence_ranges(actual_markdown, block),
                occurrence_index,
            )
            special_expected[unit_type] += 1
            if byte_range is None:
                continue
            special_actual[unit_type] += 1
            unit_ranges_by_segment[segment_id].append(byte_range)
            unit_mappings.append(
                {
                    "unit_id": unit_id,
                    "segment_id": segment_id,
                    "canonical_order": unit.get("order"),
                    "text_sha256": text_sha256(required_string(unit, "text")),
                    "exact_occurrence_index": occurrence_index,
                    "actual_byte_range": byte_range,
                }
            )

    panel_occurrence_index: defaultdict[str, int] = defaultdict(int)
    panel_turn_mappings: list[dict[str, object]] = []
    panel_ranges_by_reaction: defaultdict[str, list[dict[str, int]]] = defaultdict(list)
    global_turn_order = 0
    for segment in segments:
        if segment.get("segment_type") != "PANEL_REACTION":
            continue
        reaction_id = required_string(segment, "reaction_segment_id")
        selected_reaction = reactions.get(reaction_id)
        if selected_reaction is None:
            continue
        for turn in mapping_items(selected_reaction.get("turns"), "turns"):
            turn_id = required_string(turn, "turn_id")
            block = panel_blocks[turn_id]
            panel_occurrence_index[block] += 1
            occurrence_index = panel_occurrence_index[block]
            byte_range = range_for_occurrence(
                occurrence_ranges(actual_markdown, block),
                occurrence_index,
            )
            if byte_range is not None:
                panel_ranges_by_reaction[reaction_id].append(byte_range)
                panel_turn_mappings.append(
                    {
                        "reaction_segment_id": reaction_id,
                        "turn_id": turn_id,
                        "global_order": global_turn_order,
                        "spoken_line_sha256": text_sha256(
                            required_string(turn, "spoken_line")
                        ),
                        "actual_byte_range": byte_range,
                    }
                )
            global_turn_order += 1

    segment_mappings: list[dict[str, object]] = []
    segment_ranges: dict[str, dict[str, int]] = {}
    unsupported_types: set[str] = set()
    for global_index, segment in enumerate(segments):
        segment_id = required_string(segment, "segment_id")
        segment_type = required_string(segment, "segment_type")
        scene_id = required_string(segment, "scene_id")
        if segment_type not in {"DRAMA", "NARRATION", "PANEL_REACTION"}:
            unsupported_types.add(segment_type)
            continue
        ranges = (
            panel_ranges_by_reaction.get(
                required_string(segment, "reaction_segment_id"),
                [],
            )
            if segment_type == "PANEL_REACTION"
            else unit_ranges_by_segment.get(segment_id, [])
        )
        if not ranges:
            issues.append(
                v2_issue(
                    "BROADCAST_READABLE_V2_SEGMENT_MAPPING_MISSING",
                    "Actual Markdown에서 Segment Source 범위를 찾지 못했습니다.",
                    READABLE_PATH,
                    {"segment_id": segment_id},
                )
            )
            continue
        byte_range = {
            "byte_start": min(item["byte_start"] for item in ranges),
            "byte_end": max(item["byte_end"] for item in ranges),
        }
        segment_ranges[segment_id] = byte_range
        segment_mappings.append(
            {
                "segment_id": segment_id,
                "type": segment_type,
                "global_presentation_index": global_index,
                "scene_id": scene_id,
                "actual_byte_range": byte_range,
            }
        )
    if unsupported_types:
        issues.append(
            v2_issue(
                "BROADCAST_READABLE_UNSUPPORTED_SEGMENT_TYPE",
                "v2 Source 계약이 없는 Segment가 Presentation에 있습니다.",
                READABLE_PATH,
                {"segment_types": sorted(unsupported_types)},
            )
        )
    mapped_starts = [
        required_byte_start(mapping.get("actual_byte_range"))
        for mapping in segment_mappings
    ]
    if mapped_starts != sorted(mapped_starts) or len(mapped_starts) != len(segments):
        issues.append(
            v2_issue(
                "BROADCAST_READABLE_V2_GLOBAL_SEGMENT_ORDER_MISMATCH",
                "Actual Segment Byte 순서가 전역 Presentation 순서와 다릅니다.",
                READABLE_PATH,
                {"actual_starts": mapped_starts},
            )
        )
    for segment_id, ranges in unit_ranges_by_segment.items():
        starts = [item["byte_start"] for item in ranges]
        if starts != sorted(starts):
            issues.append(
                v2_issue(
                    "BROADCAST_READABLE_V2_UNIT_ORDER_MISMATCH",
                    "Actual Unit Byte 순서가 Canonical 순서와 다릅니다.",
                    READABLE_PATH,
                    {"segment_id": segment_id, "actual_starts": starts},
                )
            )
    for reaction_id, ranges in panel_ranges_by_reaction.items():
        starts = [item["byte_start"] for item in ranges]
        if starts != sorted(starts):
            issues.append(
                v2_issue(
                    "BROADCAST_READABLE_V2_PANEL_TURN_ORDER_MISMATCH",
                    "Actual Panel Turn Byte 순서가 Canonical 순서와 다릅니다.",
                    READABLE_PATH,
                    {"reaction_segment_id": reaction_id, "actual_starts": starts},
                )
            )

    scene_segment_indexes: defaultdict[str, list[int]] = defaultdict(list)
    for index, segment in enumerate(segments):
        scene_segment_indexes[required_string(segment, "scene_id")].append(index)
    scene_mappings: list[dict[str, object]] = []
    retrospective_actual_count = 0
    for scene_id, indexes in scene_segment_indexes.items():
        scene = scenes[scene_id]
        fragments = scene_fragments[scene_id]
        scene_heading = fragments["heading"]
        situation = fragments["situation"]
        sound = fragments["sound"]
        retrospective = fragments["retrospective"]
        assert isinstance(scene_heading, str)
        assert isinstance(situation, str)
        assert isinstance(sound, str)
        heading_ranges = occurrence_ranges(actual_markdown, scene_heading)
        situation_ranges = occurrence_ranges(actual_markdown, situation)
        sound_ranges = occurrence_ranges(actual_markdown, sound)
        scene_segment_ids = [
            required_string(segments[index], "segment_id") for index in indexes
        ]
        mapped_scene_ranges = [
            segment_ranges[segment_id]
            for segment_id in scene_segment_ids
            if segment_id in segment_ranges
        ]
        if (
            len(heading_ranges) != 1
            or len(situation_ranges) != 1
            or len(sound_ranges) != 1
            or not mapped_scene_ranges
        ):
            issues.append(
                v2_issue(
                    "BROADCAST_READABLE_V2_SCENE_CONTEXT_MAPPING_MISSING",
                    "Scene Heading 또는 시작 Context의 Actual 범위가 불완전합니다.",
                    READABLE_PATH,
                    {"scene_id": scene_id},
                )
            )
            continue
        first_segment_start = min(item["byte_start"] for item in mapped_scene_ranges)
        last_segment_end = max(item["byte_end"] for item in mapped_scene_ranges)
        if not (
            heading_ranges[0]["byte_start"]
            < situation_ranges[0]["byte_start"]
            < sound_ranges[0]["byte_start"]
            < first_segment_start
        ):
            issues.append(
                v2_issue(
                    "BROADCAST_READABLE_V2_CONTEXT_POSITION_MISMATCH",
                    "Scene 시작 Context가 첫 전역 Segment 앞의 올바른 순서가 아닙니다.",
                    READABLE_PATH,
                    {"scene_id": scene_id},
                )
            )
        retrospective_hash: str | None = None
        actual_end = last_segment_end
        if isinstance(retrospective, str):
            retrospective_ranges = occurrence_ranges(actual_markdown, retrospective)
            retrospective_actual_count += len(retrospective_ranges)
            retrospective_hash = text_sha256(retrospective)
            if (
                len(retrospective_ranges) != 1
                or retrospective_ranges[0]["byte_start"] <= last_segment_end
            ):
                issues.append(
                    v2_issue(
                        "BROADCAST_READABLE_V2_RETROSPECTIVE_POSITION_MISMATCH",
                        "Retrospective가 Scene의 마지막 전역 Segment 뒤에 있지 않습니다.",
                        READABLE_PATH,
                        {"scene_id": scene_id},
                    )
                )
            elif retrospective_ranges:
                actual_end = retrospective_ranges[0]["byte_end"]
        scene_mappings.append(
            {
                "scene_id": scene_id,
                "first_global_segment_index": min(indexes),
                "last_global_segment_index": max(indexes),
                "heading_sha256": text_sha256(scene_heading),
                "situation_context_sha256": text_sha256(situation),
                "sound_action_context_sha256": text_sha256(sound),
                "retrospective_sha256": retrospective_hash,
                "actual_byte_range": {
                    "byte_start": heading_ranges[0]["byte_start"],
                    "byte_end": actual_end,
                },
            }
        )

    expected_reentry_records: list[tuple[str, str, str | None]] = []
    seen_scene_ids: set[str] = set()
    previous_scene_id: str | None = None
    previous_segment_id: str | None = None
    for segment in segments:
        scene_id = required_string(segment, "scene_id")
        segment_id = required_string(segment, "segment_id")
        if scene_id in seen_scene_ids and previous_scene_id != scene_id:
            order, title = scene_order_title(scenes[scene_id])
            resume_heading = format_profile_template(
                profile_string(
                    document_contract,
                    "scene_resume_heading_template",
                ),
                {"order": order, "title": title},
                "scene_resume_heading_template",
            )
            expected_reentry_records.append(
                (resume_heading, segment_id, previous_segment_id)
            )
        seen_scene_ids.add(scene_id)
        previous_scene_id = scene_id
        previous_segment_id = segment_id
    expected_reentry_counts = Counter(
        heading for heading, _segment_id, _previous_id in expected_reentry_records
    )
    possible_reentry_headings = {
        format_profile_template(
            profile_string(document_contract, "scene_resume_heading_template"),
            {"order": scene_order_title(scene)[0], "title": scene_order_title(scene)[1]},
            "scene_resume_heading_template",
        )
        for scene in scenes.values()
    }
    for resume_heading in possible_reentry_headings:
        actual_count = len(occurrence_ranges(actual_markdown, resume_heading))
        expected_count = expected_reentry_counts[resume_heading]
        if actual_count != expected_count:
            issues.append(
                v2_issue(
                    "BROADCAST_READABLE_V2_SCENE_REENTRY_MISMATCH",
                    "Scene 재진입 Heading의 발생 횟수가 전역 순서와 다릅니다.",
                    READABLE_PATH,
                    {
                        "heading_sha256": text_sha256(resume_heading),
                        "expected_count": expected_count,
                        "actual_count": actual_count,
                    },
                )
            )
    reentry_occurrence_indexes: defaultdict[str, int] = defaultdict(int)
    for resume_heading, segment_id, preceding_segment_id in expected_reentry_records:
        reentry_occurrence_indexes[resume_heading] += 1
        heading_range = range_for_occurrence(
            occurrence_ranges(actual_markdown, resume_heading),
            reentry_occurrence_indexes[resume_heading],
        )
        current_range = segment_ranges.get(segment_id)
        preceding_range = (
            segment_ranges.get(preceding_segment_id)
            if preceding_segment_id is not None
            else None
        )
        if (
            heading_range is None
            or current_range is None
            or preceding_range is None
            or not (
                preceding_range["byte_end"]
                < heading_range["byte_start"]
                < current_range["byte_start"]
            )
        ):
            issues.append(
                v2_issue(
                    "BROADCAST_READABLE_V2_SCENE_REENTRY_POSITION_MISMATCH",
                    "Scene 재진입 Heading이 전역 Segment 경계 사이에 있지 않습니다.",
                    READABLE_PATH,
                    {"segment_id": segment_id},
                )
            )

    visibility = profile_mapping(output_profile, "visibility_contract")
    prefix_matches = visible_matches(
        actual_markdown,
        profile_strings(visibility, "forbidden_visible_prefixes"),
    )
    html_matches = visible_matches(
        actual_markdown,
        profile_strings(visibility, "forbidden_html_comment_tokens"),
    )
    uncertainty_matches = (
        visible_matches(
            actual_markdown,
            profile_strings(
                visibility,
                "original_fiction_forbidden_uncertainty_markers",
            ),
        )
        if screenplay_units.get("source_truth_classification") == "ORIGINAL_FICTION"
        else []
    )
    if prefix_matches or html_matches or uncertainty_matches:
        issues.append(
            v2_issue(
                "BROADCAST_READABLE_V2_VISIBILITY_FORBIDDEN",
                "Actual Markdown에 내부 ID·Comment·불확실성 Marker가 노출되었습니다.",
                READABLE_PATH,
                {
                    "forbidden_prefix_count": len(prefix_matches),
                    "html_comment_count": len(html_matches),
                    "uncertainty_marker_count": len(uncertainty_matches),
                },
            )
        )

    special_unit_type_coverage = [
        {
            "unit_type": unit_type,
            "canonical_count": special_expected[unit_type],
            "actual_count": special_actual[unit_type],
        }
        for unit_type in sorted(special_expected)
    ]
    return {
        "scene_mappings": scene_mappings,
        "segment_mappings": segment_mappings,
        "unit_mappings": unit_mappings,
        "relationship_mappings": relationship_mappings,
        "panel_turn_mappings": panel_turn_mappings,
        "special_unit_type_coverage": special_unit_type_coverage,
        "retrospective_meaning_coverage": {
            "expected_count": len(expected_retrospectives),
            "actual_count": retrospective_actual_count,
            "mappings_complete": len(expected_retrospectives)
            == retrospective_actual_count,
        },
        "visibility_scan": {
            "forbidden_prefix_matches": prefix_matches,
            "html_comment_matches": html_matches,
            "uncertainty_marker_matches": uncertainty_matches,
        },
        "unsupported_segment_types": sorted(unsupported_types),
        "issues": issues,
    }


def build_broadcast_readable_report_v2(
    broadcast_readable_config: Mapping[str, object],
    screenplay_units: Mapping[str, object],
    characters: Mapping[str, object],
    relationships: Mapping[str, object],
    panel_cast: Mapping[str, object],
    reaction_segments: Mapping[str, object],
    presentation_plan: Mapping[str, object],
    final_script: str,
    output_profile: Mapping[str, object],
    output_profile_file_sha256: str,
    actual_markdown: str,
) -> dict[str, object]:
    """Expected Byte와 Actual Mapping을 결합한 v2 Report를 만든다."""
    issues: list[ValidationIssue] = []
    expected_markdown: str | None = None
    try:
        expected_markdown = render_broadcast_readable_script_v2(
            screenplay_units,
            characters,
            relationships,
            panel_cast,
            reaction_segments,
            presentation_plan,
            output_profile,
        )
    except ConfigurationError as error:
        detail = str(error)
        code = (
            "BROADCAST_READABLE_UNSUPPORTED_SEGMENT_TYPE"
            if detail.startswith("BROADCAST_READABLE_UNSUPPORTED_SEGMENT_TYPE")
            else "BROADCAST_READABLE_V2_RECONSTRUCTION_FAILED"
        )
        issues.append(
            v2_issue(
                code,
                "Canonical 입력에서 v2 Expected Markdown을 재구성하지 못했습니다.",
                READABLE_PATH,
                {"detail": detail},
            )
        )
    conformance = independent_conformance(
        screenplay_units,
        characters,
        relationships,
        panel_cast,
        reaction_segments,
        presentation_plan,
        output_profile,
        actual_markdown,
    )
    conformance_issues = conformance["issues"]
    if isinstance(conformance_issues, list):
        issues.extend(conformance_issues)
    actual_hash = sha256(actual_markdown.encode("utf-8")).hexdigest()
    expected_hash = (
        sha256(expected_markdown.encode("utf-8")).hexdigest()
        if expected_markdown is not None
        else "0" * 64
    )
    byte_identical = expected_markdown == actual_markdown
    if expected_markdown is not None and not byte_identical:
        issues.append(
            v2_issue(
                "BROADCAST_READABLE_V2_RECONSTRUCTION_MISMATCH",
                "Actual Markdown Byte가 결정론적 Expected Markdown과 다릅니다.",
                READABLE_PATH,
                {"expected_sha256": expected_hash, "actual_sha256": actual_hash},
            )
        )
    if not actual_markdown:
        issues.append(
            v2_issue(
                "BROADCAST_READABLE_V2_OUTPUT_MISSING",
                "v2 Readable Markdown이 없습니다.",
                READABLE_PATH,
                {},
            )
        )
    result = "MISSING" if not actual_markdown else "FAIL" if issues else "NEEDS_REVIEW"
    config_hash = document_sha256(broadcast_readable_config)
    profile_document_hash = document_sha256(output_profile)
    return {
        "$schema": "../../../STANDARD/schemas/broadcast_readable_report_2_0.schema.json",
        "schema_family": "broadcast-readable-report",
        "schema_version": "2.0.0",
        "project_id": screenplay_units.get("project_id"),
        "result": result,
        "config_binding": {
            "schema_version": "1.0.0",
            "enabled": True,
            "profile_id": "BROADCAST_READABLE_SCRIPT",
            "profile_version": "2.0.0",
            "sha256": config_hash,
        },
        "output_profile_binding": {
            "profile_id": "BROADCAST_READABLE_SCRIPT",
            "profile_version": "2.0.0",
            "profile_path": PROFILE_PATH,
            "schema_path": PROFILE_SCHEMA_PATH,
            "document_sha256": profile_document_hash,
            "file_sha256": output_profile_file_sha256,
        },
        "input_artifact_hashes": {
            "broadcast_readable_config": config_hash,
            "screenplay_units": document_sha256(screenplay_units),
            "characters": document_sha256(characters),
            "relationships": document_sha256(relationships),
            "panel_cast": document_sha256(panel_cast),
            "reaction_segments": document_sha256(reaction_segments),
            "presentation_plan": document_sha256(presentation_plan),
            "final_script": sha256(final_script.encode("utf-8")).hexdigest(),
        },
        "output_artifact_hashes": {
            "canonical_readable_script": actual_hash,
            "expected_production_copy": actual_hash,
        },
        "scene_mappings": conformance["scene_mappings"],
        "segment_mappings": conformance["segment_mappings"],
        "unit_mappings": conformance["unit_mappings"],
        "relationship_mappings": conformance["relationship_mappings"],
        "panel_turn_mappings": conformance["panel_turn_mappings"],
        "special_unit_type_coverage": conformance["special_unit_type_coverage"],
        "reconstruction_coverage": {
            "expected_sha256": expected_hash,
            "actual_sha256": actual_hash,
            "byte_identical": byte_identical,
        },
        "retrospective_meaning_coverage": conformance[
            "retrospective_meaning_coverage"
        ],
        "visibility_scan": conformance["visibility_scan"],
        "unsupported_segment_types": conformance["unsupported_segment_types"],
        "issues": issues,
    }


def validate_broadcast_readable_report_v2(
    report: Mapping[str, object],
    broadcast_readable_config: Mapping[str, object],
    screenplay_units: Mapping[str, object],
    characters: Mapping[str, object],
    relationships: Mapping[str, object],
    panel_cast: Mapping[str, object],
    reaction_segments: Mapping[str, object],
    presentation_plan: Mapping[str, object],
    final_script: str,
    output_profile: Mapping[str, object],
    output_profile_file_sha256: str,
    actual_markdown: str,
) -> list[ValidationIssue]:
    """저장 Report를 현재 입력·Output의 독립 재계산 결과와 대조한다."""
    if (
        broadcast_readable_config.get("enabled") is not True
        or broadcast_readable_config.get("profile_id")
        != "BROADCAST_READABLE_SCRIPT"
        or broadcast_readable_config.get("profile_version") != "2.0.0"
    ):
        return [
            v2_issue(
                "BROADCAST_READABLE_V2_CONFIG_BINDING_INVALID",
                "v2 Config Profile 결속이 활성 2.0.0 계약과 다릅니다.",
                "00_PROJECT/broadcast_readable_config.json",
                {},
            )
        ]
    expected = build_broadcast_readable_report_v2(
        broadcast_readable_config,
        screenplay_units,
        characters,
        relationships,
        panel_cast,
        reaction_segments,
        presentation_plan,
        final_script,
        output_profile,
        output_profile_file_sha256,
        actual_markdown,
    )
    raw_issues = expected["issues"]
    issues = list(raw_issues) if isinstance(raw_issues, list) else []
    if dict(report) != expected:
        issues.append(
            v2_issue(
                "BROADCAST_READABLE_V2_REPORT_STALE",
                "저장 v2 Report가 현재 입력·Actual Output Mapping과 다릅니다.",
                REPORT_PATH,
                {
                    "expected_report_sha256": document_sha256(expected),
                    "actual_report_sha256": document_sha256(report),
                },
            )
        )
    return issues
