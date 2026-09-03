"""Broadcast Readable v2 Actual Markdown의 독립 증거와 Report를 검증한다."""

from collections import Counter, defaultdict
from collections.abc import Mapping, Sequence
from copy import deepcopy
from hashlib import sha256
from typing import cast

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
    DRAMA_UNIT_TYPES,
    NARRATION_UNIT_TYPES,
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
PROFILE_PATH = "CHANNELS/mystery_main/output_profiles/broadcast-readable-script/2.0.0.json"
PROFILE_SCHEMA_PATH = "STANDARD/schemas/broadcast_readable_output_profile_2_0.schema.json"
CURRENT_REPORT_SCHEMA_PATH = "../../../STANDARD/schemas/broadcast_readable_report_2_1.schema.json"
CURRENT_REPORT_VERSION = "2.1.0"
LEGACY_REPORT_SCHEMA_PATH = "../../../STANDARD/schemas/broadcast_readable_report_2_0.schema.json"
LEGACY_REPORT_VERSION = "2.0.0"
MAPPING_CONTRACT_VERSION = "OWNER_BOUND_1"
MAPPING_EXTENSION_FIELDS = {
    "owner_type",
    "owner_id",
    "container_type",
    "segment_id",
    "scene_id",
    "rendered_block_sha256",
    "container_local_order",
    "global_presentation_order",
    "same_block_occurrence_index_within_owner_type_or_container",
    "exact_occurrence_index",
}


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


def block_occurrence_ranges(value: str, fragment: str) -> list[dict[str, int]]:
    """독립 Markdown Block 경계에 놓인 Exact Fragment 범위를 반환한다."""
    if not fragment:
        raise ConfigurationError("BROADCAST_READABLE_V2_EMPTY_FRAGMENT")
    ranges: list[dict[str, int]] = []
    start = 0
    while True:
        character_start = value.find(fragment, start)
        if character_start < 0:
            return ranges
        character_end = character_start + len(fragment)
        starts_at_boundary = character_start == 0 or (
            character_start >= 2 and value[character_start - 2 : character_start] == "\n\n"
        )
        ends_at_boundary = (
            character_end == len(value)
            or value.startswith("\n\n", character_end)
            or (value.startswith("\n", character_end) and character_end + 1 == len(value))
        )
        if starts_at_boundary and ends_at_boundary:
            ranges.append(actual_byte_range(value, character_start, character_end))
        start = character_start + 1


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
            raise ConfigurationError(f"BROADCAST_READABLE_SCENE_DUPLICATED: scene_id={scene_id}")
        result[scene_id] = scene
    return result


def scene_order_title(scene: Mapping[str, object]) -> tuple[int, str]:
    """Scene Heading의 순서와 제목을 검증해 반환한다."""
    order = scene.get("order")
    if not isinstance(order, int) or isinstance(order, bool):
        raise ConfigurationError(f"BROADCAST_READABLE_SCENE_SEQUENCE_INVALID: order={order!r}")
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
        raise ConfigurationError(f"BROADCAST_READABLE_PREVIOUS_SCENE_INVALID: value={value!r}")
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
        raise ConfigurationError(f"BROADCAST_READABLE_SPEAKER_UNKNOWN: speaker_id={speaker_id}")
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
        raise ConfigurationError(f"BROADCAST_READABLE_UNIT_TYPE_UNSUPPORTED: unit_type={unit_type}")
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
        raise ConfigurationError(f"BROADCAST_READABLE_PANELIST_UNKNOWN: panelist_id={panelist_id}")
    return format_profile_template(
        profile_string(render_contract, "panel_turn_template"),
        {
            "display_name": normalize_line_endings(required_string(panelist, "display_name")),
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
                    separator.join(entries[character_id]) if entries[character_id] else "—"
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


def parsed_count_issue(
    expected_count: int,
    actual_count: int,
    code: str,
    label: str,
) -> list[ValidationIssue]:
    """Parser가 소유권을 확정한 Block 수와 Canonical 수를 비교한다."""
    if actual_count == expected_count:
        return []
    return [
        v2_issue(
            code,
            f"Actual {label}의 소유권 Mapping 수가 Canonical과 다릅니다.",
            READABLE_PATH,
            {
                "expected_count": expected_count,
                "actual_count": actual_count,
            },
        )
    ]


def actual_byte_range(
    actual_markdown: str,
    character_start: int,
    character_end: int,
) -> dict[str, int]:
    """Actual 문자열의 문자 범위를 UTF-8 Half-open Byte 범위로 변환한다."""
    return {
        "byte_start": byte_offset(actual_markdown, character_start),
        "byte_end": byte_offset(actual_markdown, character_end),
    }


def consume_actual_block(
    actual_markdown: str,
    cursor: int,
    expected_block: str,
    error_code: str,
    context: dict[str, object],
) -> tuple[dict[str, int] | None, int, list[ValidationIssue]]:
    """현재 Cursor에서만 Exact Block과 구분자를 소비한다."""
    if not actual_markdown.startswith(expected_block, cursor):
        return (
            None,
            cursor,
            [
                v2_issue(
                    error_code,
                    "Actual Markdown의 다음 Block이 Canonical 순서와 다릅니다.",
                    READABLE_PATH,
                    {
                        **context,
                        "expected_block_sha256": text_sha256(expected_block),
                        "actual_cursor_byte": byte_offset(actual_markdown, cursor),
                    },
                )
            ],
        )
    end = cursor + len(expected_block)
    byte_range = actual_byte_range(actual_markdown, cursor, end)
    if actual_markdown.startswith("\n\n", end):
        return byte_range, end + 2, []
    if actual_markdown.startswith("\n", end) and end + 1 == len(actual_markdown):
        return byte_range, end + 1, []
    return (
        byte_range,
        end,
        [
            v2_issue(
                "BROADCAST_READABLE_V2_BLOCK_BOUNDARY_AMBIGUOUS",
                "Actual Markdown Block 사이의 경계를 확정할 수 없습니다.",
                READABLE_PATH,
                {
                    **context,
                    "block_end_byte": byte_range["byte_end"],
                },
            )
        ],
    )


def next_owned_occurrence_index(
    counts: defaultdict[tuple[str, str, str], int],
    owner_type: str,
    container_type: str,
    rendered_block_sha256: str,
) -> int:
    """소유권·Container·Block Hash 그룹 안의 다음 발생 번호를 반환한다."""
    key = (owner_type, container_type, rendered_block_sha256)
    counts[key] += 1
    return counts[key]


def duplicate_mapping_range_issues(
    mappings: Sequence[Mapping[str, object]],
) -> list[ValidationIssue]:
    """Unit·Turn이 같은 Actual Byte 범위를 재사용하면 실패한다."""
    owners_by_range: defaultdict[tuple[int, int], list[str]] = defaultdict(list)
    for mapping in mappings:
        byte_range = mapping.get("actual_byte_range")
        if not isinstance(byte_range, Mapping):
            continue
        byte_start = byte_range.get("byte_start")
        byte_end = byte_range.get("byte_end")
        if not isinstance(byte_start, int) or not isinstance(byte_end, int):
            continue
        owner = mapping.get("unit_id", mapping.get("turn_id"))
        owners_by_range[(byte_start, byte_end)].append(str(owner))
    duplicates = [
        {
            "byte_start": byte_range[0],
            "byte_end": byte_range[1],
            "owners": owners,
        }
        for byte_range, owners in owners_by_range.items()
        if len(owners) > 1
    ]
    if not duplicates:
        return []
    return [
        v2_issue(
            "BROADCAST_READABLE_V2_DUPLICATE_BYTE_RANGE",
            "둘 이상의 Canonical Block이 같은 Actual Byte 범위를 사용했습니다.",
            REPORT_PATH,
            {"duplicates": duplicates},
        )
    ]


def owner_mapping_contract_issues(
    report: Mapping[str, object],
    actual_markdown: str,
) -> list[ValidationIssue]:
    """2.1 Report Mapping의 소유·Container·Hash·순서 의미를 검사한다."""
    raw_segments = report.get("segment_mappings")
    segment_mappings = (
        [item for item in raw_segments if isinstance(item, Mapping)]
        if isinstance(raw_segments, list)
        else []
    )
    segments_by_id = {str(mapping.get("segment_id")): mapping for mapping in segment_mappings}
    typed_mappings: list[tuple[str, Mapping[str, object]]] = []
    for field in ("unit_mappings", "panel_turn_mappings"):
        raw_mappings = report.get(field)
        if isinstance(raw_mappings, list):
            typed_mappings.extend(
                (field, mapping) for mapping in raw_mappings if isinstance(mapping, Mapping)
            )
    issues: list[ValidationIssue] = []
    encoded_markdown = actual_markdown.encode("utf-8")
    for field, mapping in typed_mappings:
        expected_owner_type = "UNIT" if field == "unit_mappings" else "PANEL_TURN"
        identity_field = "unit_id" if field == "unit_mappings" else "turn_id"
        if mapping.get("owner_type") != expected_owner_type:
            issues.append(
                v2_issue(
                    "BROADCAST_READABLE_V2_OWNER_TYPE_MISMATCH",
                    "Mapping 종류와 Owner Type이 다릅니다.",
                    REPORT_PATH,
                    {"mapping": field, "owner_type": mapping.get("owner_type")},
                )
            )
        if mapping.get("owner_id") != mapping.get(identity_field):
            issues.append(
                v2_issue(
                    "BROADCAST_READABLE_V2_OWNER_ID_MISMATCH",
                    "Mapping Owner ID가 Canonical Unit·Turn ID와 다릅니다.",
                    REPORT_PATH,
                    {
                        "mapping": field,
                        "owner_id": mapping.get("owner_id"),
                        identity_field: mapping.get(identity_field),
                    },
                )
            )
        segment_id = mapping.get("segment_id")
        segment = segments_by_id.get(str(segment_id))
        expected_container = segment.get("type") if segment is not None else None
        if (
            expected_container not in {"DRAMA", "NARRATION", "PANEL_REACTION"}
            or mapping.get("container_type") != expected_container
            or (field == "unit_mappings" and expected_container == "PANEL_REACTION")
            or (field == "panel_turn_mappings" and expected_container != "PANEL_REACTION")
        ):
            issues.append(
                v2_issue(
                    "BROADCAST_READABLE_V2_CONTAINER_BINDING_MISMATCH",
                    "Mapping Container Type이 Presentation Segment와 다릅니다.",
                    REPORT_PATH,
                    {
                        "mapping": field,
                        "segment_id": segment_id,
                        "container_type": mapping.get("container_type"),
                        "expected_container_type": expected_container,
                    },
                )
            )
        if segment is None or mapping.get("scene_id") != segment.get("scene_id"):
            issues.append(
                v2_issue(
                    "BROADCAST_READABLE_V2_SEGMENT_BINDING_MISMATCH",
                    "Mapping Scene·Segment 결속이 Presentation과 다릅니다.",
                    REPORT_PATH,
                    {
                        "mapping": field,
                        "segment_id": segment_id,
                        "scene_id": mapping.get("scene_id"),
                    },
                )
            )
        raw_range = mapping.get("actual_byte_range")
        byte_start = raw_range.get("byte_start") if isinstance(raw_range, Mapping) else None
        byte_end = raw_range.get("byte_end") if isinstance(raw_range, Mapping) else None
        if (
            not isinstance(byte_start, int)
            or not isinstance(byte_end, int)
            or byte_start < 0
            or byte_end <= byte_start
            or byte_end > len(encoded_markdown)
        ):
            issues.append(
                v2_issue(
                    "BROADCAST_READABLE_V2_BYTE_RANGE_INVALID",
                    "Mapping Byte Range가 Actual Markdown 범위와 다릅니다.",
                    REPORT_PATH,
                    {"mapping": field, "actual_byte_range": raw_range},
                )
            )
            continue
        try:
            block = encoded_markdown[byte_start:byte_end].decode("utf-8")
        except UnicodeDecodeError:
            issues.append(
                v2_issue(
                    "BROADCAST_READABLE_V2_BYTE_RANGE_INVALID",
                    "Mapping Byte Range가 UTF-8 Block 경계를 벗어났습니다.",
                    REPORT_PATH,
                    {"mapping": field, "actual_byte_range": raw_range},
                )
            )
            continue
        if mapping.get("rendered_block_sha256") != text_sha256(block):
            issues.append(
                v2_issue(
                    "BROADCAST_READABLE_V2_BLOCK_HASH_MISMATCH",
                    "Mapping Block Hash가 Actual Markdown Byte Range와 다릅니다.",
                    REPORT_PATH,
                    {
                        "mapping": field,
                        "owner_id": mapping.get("owner_id"),
                        "actual_byte_range": raw_range,
                    },
                )
            )

    def global_order(mapping: Mapping[str, object]) -> int:
        """Mapping의 정수 전역 순서를 반환한다."""
        value = mapping.get("global_presentation_order")
        return value if isinstance(value, int) else -1

    globally_ordered = sorted(
        (mapping for _field, mapping in typed_mappings),
        key=global_order,
    )
    global_orders = [mapping.get("global_presentation_order") for mapping in globally_ordered]
    if global_orders != list(range(1, len(globally_ordered) + 1)):
        issues.append(
            v2_issue(
                "BROADCAST_READABLE_V2_GLOBAL_ORDER_MISMATCH",
                "Unit·Panel Mapping의 전역 Presentation Order가 연속하지 않습니다.",
                REPORT_PATH,
                {"global_presentation_orders": global_orders},
            )
        )

    local_groups: defaultdict[tuple[object, object], list[Mapping[str, object]]] = defaultdict(list)
    occurrence_groups: defaultdict[tuple[object, object, object], list[Mapping[str, object]]] = (
        defaultdict(list)
    )
    for mapping in globally_ordered:
        local_groups[(mapping.get("owner_type"), mapping.get("segment_id"))].append(mapping)
        occurrence_groups[
            (
                mapping.get("owner_type"),
                mapping.get("container_type"),
                mapping.get("rendered_block_sha256"),
            )
        ].append(mapping)
    for local_group, mappings in local_groups.items():
        orders = [mapping.get("container_local_order") for mapping in mappings]
        if orders != list(range(1, len(mappings) + 1)):
            issues.append(
                v2_issue(
                    "BROADCAST_READABLE_V2_CONTAINER_ORDER_MISMATCH",
                    "Segment Container Local Order가 1부터 연속하지 않습니다.",
                    REPORT_PATH,
                    {"group": list(local_group), "orders": orders},
                )
            )
    for occurrence_group, mappings in occurrence_groups.items():
        occurrence_orders = [
            mapping.get("same_block_occurrence_index_within_owner_type_or_container")
            for mapping in mappings
        ]
        exact_orders = [mapping.get("exact_occurrence_index") for mapping in mappings]
        expected_orders = list(range(1, len(mappings) + 1))
        if occurrence_orders != expected_orders or exact_orders != expected_orders:
            issues.append(
                v2_issue(
                    "BROADCAST_READABLE_V2_OCCURRENCE_ORDER_MISMATCH",
                    "Owner·Container·Block 발생 번호가 1부터 연속하지 않습니다.",
                    REPORT_PATH,
                    {
                        "group": list(occurrence_group),
                        "occurrence_orders": occurrence_orders,
                        "exact_occurrence_orders": exact_orders,
                    },
                )
            )
    return issues


def legacy_report_2_0_from_current(
    report: Mapping[str, object],
) -> dict[str, object]:
    """현재 Report를 Historical 2.0 비교 계약으로 변환한다."""
    legacy = deepcopy(dict(report))
    legacy["$schema"] = LEGACY_REPORT_SCHEMA_PATH
    legacy["schema_version"] = LEGACY_REPORT_VERSION
    legacy.pop("mapping_contract_version", None)
    ordered_mappings: list[dict[str, object]] = []
    for field in ("unit_mappings", "panel_turn_mappings"):
        raw_mappings = legacy.get(field)
        if isinstance(raw_mappings, list):
            ordered_mappings.extend(
                mapping for mapping in raw_mappings if isinstance(mapping, dict)
            )
    ordered_mappings.sort(key=lambda mapping: cast(int, mapping["global_presentation_order"]))
    legacy_container_orders: defaultdict[str, int] = defaultdict(int)
    for mapping in ordered_mappings:
        container_type = cast(str, mapping["container_type"])
        legacy_container_orders[container_type] += 1
        mapping["container_local_order"] = legacy_container_orders[container_type]
    return legacy


def expected_report_for_mapping_contract(
    expected: Mapping[str, object],
    report: Mapping[str, object],
) -> dict[str, object]:
    """저장 Report가 생략한 Optional Mapping 확장만 비교 기대값에서 제외한다."""
    comparable = deepcopy(dict(expected))
    for field in ("unit_mappings", "panel_turn_mappings"):
        expected_records = comparable.get(field)
        reported_records = report.get(field)
        if not isinstance(expected_records, list) or not isinstance(
            reported_records,
            list,
        ):
            continue
        for expected_record, reported_record in zip(
            expected_records,
            reported_records,
            strict=False,
        ):
            if not isinstance(expected_record, dict) or not isinstance(
                reported_record,
                Mapping,
            ):
                continue
            for extension_field in MAPPING_EXTENSION_FIELDS:
                if extension_field not in reported_record:
                    expected_record.pop(extension_field, None)
    return comparable


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
    """Actual Markdown을 전역 Presentation 순서의 Segment 경계 안에서 검증한다."""
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
        if retrospective is not None:
            expected_retrospectives.append(retrospective)

    unit_blocks: dict[str, str] = {}
    expected_unit_ids: list[str] = []
    for records in unit_records.values():
        for _scene_id, unit in records:
            unit_id = required_string(unit, "unit_id")
            block = verifier_unit_block(unit, characters, render_contract)
            unit_blocks[unit_id] = block
            expected_unit_ids.append(unit_id)
    panel_blocks: dict[str, str] = {}
    expected_panel_turn_ids: list[str] = []
    for reaction in reactions.values():
        for turn in mapping_items(reaction.get("turns"), "turns"):
            turn_id = required_string(turn, "turn_id")
            block = verifier_panel_turn_block(turn, panelists, render_contract)
            panel_blocks[turn_id] = block
            expected_panel_turn_ids.append(turn_id)

    body_heading = "## 방송 대본"
    body_heading_ranges = occurrence_ranges(actual_markdown, body_heading)
    cursor = -1
    if len(body_heading_ranges) == 1:
        body_character_start = actual_markdown.find(body_heading)
        body_end = body_character_start + len(body_heading)
        if actual_markdown.startswith("\n\n", body_end):
            cursor = body_end + 2
    if cursor < 0:
        issues.append(
            v2_issue(
                "BROADCAST_READABLE_V2_SEGMENT_BOUNDARY_MISMATCH",
                "방송 대본 Body의 시작 경계를 확정할 수 없습니다.",
                READABLE_PATH,
                {"heading_count": len(body_heading_ranges)},
            )
        )

    first_segment_by_scene: dict[str, int] = {}
    last_segment_by_scene: dict[str, int] = {}
    for global_index, segment in enumerate(segments):
        scene_id = required_string(segment, "scene_id")
        first_segment_by_scene.setdefault(scene_id, global_index)
        last_segment_by_scene[scene_id] = global_index

    unit_mappings: list[dict[str, object]] = []
    panel_turn_mappings: list[dict[str, object]] = []
    segment_mappings: list[dict[str, object]] = []
    scene_heading_ranges: dict[str, dict[str, int]] = {}
    scene_context_ranges: dict[str, tuple[dict[str, int], dict[str, int]]] = {}
    scene_retrospective_ranges: dict[str, dict[str, int]] = {}
    unsupported_types: set[str] = set()
    special_expected = Counter[str]()
    special_actual = Counter[str]()
    seen_scene_ids: set[str] = set()
    previous_scene_id: str | None = None
    panel_index = 1
    global_turn_order = 0
    global_content_order = 0
    container_orders: defaultdict[tuple[str, str], int] = defaultdict(int)
    owned_occurrence_counts: defaultdict[tuple[str, str, str], int] = defaultdict(int)
    parsing_failed = cursor < 0

    for global_index, segment in enumerate(segments):
        segment_id = required_string(segment, "segment_id")
        segment_type = required_string(segment, "segment_type")
        scene_id = required_string(segment, "scene_id")
        if segment_type not in {"DRAMA", "NARRATION", "PANEL_REACTION"}:
            unsupported_types.add(segment_type)
            parsing_failed = True
            break
        if parsing_failed:
            break
        fragments = scene_fragments[scene_id]
        if global_index == first_segment_by_scene[scene_id]:
            heading_fragment = fragments["heading"]
            situation = fragments["situation"]
            sound = fragments["sound"]
            assert isinstance(heading_fragment, str)
            assert isinstance(situation, str)
            assert isinstance(sound, str)
            heading_range, cursor, boundary_issues = consume_actual_block(
                actual_markdown,
                cursor,
                heading_fragment,
                "BROADCAST_READABLE_V2_CONTEXT_POSITION_MISMATCH",
                {"scene_id": scene_id, "context": "HEADING"},
            )
            issues.extend(boundary_issues)
            if boundary_issues and any(
                actual_markdown.startswith(
                    format_profile_template(
                        profile_string(
                            document_contract,
                            "scene_resume_heading_template",
                        ),
                        {
                            "order": scene_order_title(candidate_scene)[0],
                            "title": scene_order_title(candidate_scene)[1],
                        },
                        "scene_resume_heading_template",
                    ),
                    cursor,
                )
                for candidate_scene in scenes.values()
            ):
                issues.append(
                    v2_issue(
                        "BROADCAST_READABLE_V2_SCENE_REENTRY_POSITION_MISMATCH",
                        "Scene 재진입 Heading이 첫 Scene 경계 앞에 배치됐습니다.",
                        READABLE_PATH,
                        {"scene_id": scene_id, "segment_id": segment_id},
                    )
                )
            situation_range, cursor, situation_issues = consume_actual_block(
                actual_markdown,
                cursor,
                situation,
                "BROADCAST_READABLE_V2_CONTEXT_POSITION_MISMATCH",
                {"scene_id": scene_id, "context": "SITUATION"},
            )
            issues.extend(situation_issues)
            sound_range, cursor, sound_issues = consume_actual_block(
                actual_markdown,
                cursor,
                sound,
                "BROADCAST_READABLE_V2_CONTEXT_POSITION_MISMATCH",
                {"scene_id": scene_id, "context": "SOUND_ACTION"},
            )
            issues.extend(sound_issues)
            if (
                heading_range is None
                or situation_range is None
                or sound_range is None
                or boundary_issues
                or situation_issues
                or sound_issues
            ):
                parsing_failed = True
                break
            scene_heading_ranges[scene_id] = heading_range
            scene_context_ranges[scene_id] = (situation_range, sound_range)
            seen_scene_ids.add(scene_id)
        elif previous_scene_id != scene_id:
            order, title = scene_order_title(scenes[scene_id])
            resume_heading = format_profile_template(
                profile_string(document_contract, "scene_resume_heading_template"),
                {"order": order, "title": title},
                "scene_resume_heading_template",
            )
            _resume_range, cursor, resume_issues = consume_actual_block(
                actual_markdown,
                cursor,
                resume_heading,
                "BROADCAST_READABLE_V2_SCENE_REENTRY_POSITION_MISMATCH",
                {"scene_id": scene_id, "segment_id": segment_id},
            )
            issues.extend(resume_issues)
            if scene_id not in seen_scene_ids or resume_issues:
                parsing_failed = True
                break

        content_ranges: list[dict[str, int]] = []
        records = unit_records.get(segment_id, [])
        if segment_type in {"DRAMA", "NARRATION"}:
            expected_types = DRAMA_UNIT_TYPES if segment_type == "DRAMA" else NARRATION_UNIT_TYPES
            if not records:
                issues.append(
                    v2_issue(
                        "BROADCAST_READABLE_V2_SEGMENT_MAPPING_MISSING",
                        "Segment에 대응할 Canonical Unit이 없습니다.",
                        READABLE_PATH,
                        {"segment_id": segment_id},
                    )
                )
                parsing_failed = True
                break
            for record_scene_id, unit in records:
                unit_id = required_string(unit, "unit_id")
                unit_type = required_string(unit, "type")
                special_expected[unit_type] += 1
                if record_scene_id != scene_id or unit_type not in expected_types:
                    issues.append(
                        v2_issue(
                            "BROADCAST_READABLE_V2_UNIT_SEGMENT_MISMATCH",
                            "Unit의 Scene·Layer가 Presentation Segment와 다릅니다.",
                            READABLE_PATH,
                            {
                                "segment_id": segment_id,
                                "unit_id": unit_id,
                                "scene_id": record_scene_id,
                                "unit_type": unit_type,
                            },
                        )
                    )
                    parsing_failed = True
                    break
                block = unit_blocks[unit_id]
                unit_range, cursor, unit_issues = consume_actual_block(
                    actual_markdown,
                    cursor,
                    block,
                    "BROADCAST_READABLE_V2_UNIT_ORDER_MISMATCH",
                    {"segment_id": segment_id, "unit_id": unit_id},
                )
                issues.extend(unit_issues)
                if unit_range is None or unit_issues:
                    if any(
                        actual_markdown.startswith(retrospective, cursor)
                        for retrospective in expected_retrospectives
                    ):
                        issues.append(
                            v2_issue(
                                "BROADCAST_READABLE_V2_RETROSPECTIVE_POSITION_MISMATCH",
                                "Retrospective가 Scene의 마지막 Segment보다 앞에 있습니다.",
                                READABLE_PATH,
                                {"scene_id": scene_id, "segment_id": segment_id},
                            )
                        )
                    issues.append(
                        v2_issue(
                            "BROADCAST_READABLE_V2_GLOBAL_SEGMENT_ORDER_MISMATCH",
                            "Actual Segment가 전역 Presentation 순서와 다릅니다.",
                            READABLE_PATH,
                            {"segment_id": segment_id, "global_index": global_index},
                        )
                    )
                    parsing_failed = True
                    break
                special_actual[unit_type] += 1
                content_ranges.append(unit_range)
                rendered_block_sha256 = text_sha256(block)
                container_key = ("UNIT", segment_id)
                container_orders[container_key] += 1
                global_content_order += 1
                occurrence_index = next_owned_occurrence_index(
                    owned_occurrence_counts,
                    "UNIT",
                    segment_type,
                    rendered_block_sha256,
                )
                unit_mappings.append(
                    {
                        "owner_type": "UNIT",
                        "owner_id": unit_id,
                        "container_type": segment_type,
                        "unit_id": unit_id,
                        "segment_id": segment_id,
                        "scene_id": scene_id,
                        "canonical_order": unit.get("order"),
                        "text_sha256": text_sha256(required_string(unit, "text")),
                        "rendered_block_sha256": rendered_block_sha256,
                        "container_local_order": container_orders[container_key],
                        "global_presentation_order": global_content_order,
                        "same_block_occurrence_index_within_owner_type_or_container": (
                            occurrence_index
                        ),
                        "exact_occurrence_index": occurrence_index,
                        "actual_byte_range": unit_range,
                    }
                )
            if parsing_failed:
                break
        else:
            if records:
                issues.append(
                    v2_issue(
                        "BROADCAST_READABLE_V2_UNIT_SEGMENT_MISMATCH",
                        "Panel Segment가 Screenplay Unit을 포함합니다.",
                        READABLE_PATH,
                        {"segment_id": segment_id},
                    )
                )
                parsing_failed = True
                break
            reaction_id = required_string(segment, "reaction_segment_id")
            selected_reaction = reactions.get(reaction_id)
            if selected_reaction is None:
                issues.append(
                    v2_issue(
                        "BROADCAST_READABLE_V2_SEGMENT_MAPPING_MISSING",
                        "Panel Segment의 Reaction을 찾지 못했습니다.",
                        READABLE_PATH,
                        {"segment_id": segment_id, "reaction_segment_id": reaction_id},
                    )
                )
                parsing_failed = True
                break
            panel_heading = format_profile_template(
                profile_string(render_contract, "panel_section_heading_template"),
                {"index": panel_index},
                "panel_section_heading_template",
            )
            _panel_heading_range, cursor, panel_heading_issues = consume_actual_block(
                actual_markdown,
                cursor,
                panel_heading,
                "BROADCAST_READABLE_V2_GLOBAL_SEGMENT_ORDER_MISMATCH",
                {"segment_id": segment_id, "reaction_segment_id": reaction_id},
            )
            issues.extend(panel_heading_issues)
            if panel_heading_issues:
                parsing_failed = True
                break
            for turn in mapping_items(selected_reaction.get("turns"), "turns"):
                turn_id = required_string(turn, "turn_id")
                block = panel_blocks[turn_id]
                turn_range, cursor, turn_issues = consume_actual_block(
                    actual_markdown,
                    cursor,
                    block,
                    "BROADCAST_READABLE_V2_PANEL_TURN_ORDER_MISMATCH",
                    {
                        "segment_id": segment_id,
                        "reaction_segment_id": reaction_id,
                        "turn_id": turn_id,
                    },
                )
                issues.extend(turn_issues)
                if turn_range is None or turn_issues:
                    parsing_failed = True
                    break
                content_ranges.append(turn_range)
                rendered_block_sha256 = text_sha256(block)
                container_key = ("PANEL_TURN", segment_id)
                container_orders[container_key] += 1
                global_content_order += 1
                occurrence_index = next_owned_occurrence_index(
                    owned_occurrence_counts,
                    "PANEL_TURN",
                    segment_type,
                    rendered_block_sha256,
                )
                panel_turn_mappings.append(
                    {
                        "owner_type": "PANEL_TURN",
                        "owner_id": turn_id,
                        "container_type": segment_type,
                        "reaction_segment_id": reaction_id,
                        "turn_id": turn_id,
                        "segment_id": segment_id,
                        "scene_id": scene_id,
                        "global_order": global_turn_order,
                        "spoken_line_sha256": text_sha256(required_string(turn, "spoken_line")),
                        "rendered_block_sha256": rendered_block_sha256,
                        "container_local_order": container_orders[container_key],
                        "global_presentation_order": global_content_order,
                        "same_block_occurrence_index_within_owner_type_or_container": (
                            occurrence_index
                        ),
                        "exact_occurrence_index": occurrence_index,
                        "actual_byte_range": turn_range,
                    }
                )
                global_turn_order += 1
            if parsing_failed:
                break
            panel_index += 1
        if not content_ranges:
            issues.append(
                v2_issue(
                    "BROADCAST_READABLE_V2_SEGMENT_MAPPING_MISSING",
                    "Actual Markdown에서 Segment Content 범위를 찾지 못했습니다.",
                    READABLE_PATH,
                    {"segment_id": segment_id},
                )
            )
            parsing_failed = True
            break
        segment_mappings.append(
            {
                "segment_id": segment_id,
                "type": segment_type,
                "global_presentation_index": global_index,
                "scene_id": scene_id,
                "actual_byte_range": {
                    "byte_start": content_ranges[0]["byte_start"],
                    "byte_end": content_ranges[-1]["byte_end"],
                },
            }
        )
        if global_index == last_segment_by_scene[scene_id]:
            retrospective = fragments["retrospective"]
            if isinstance(retrospective, str):
                retrospective_range, cursor, retrospective_issues = consume_actual_block(
                    actual_markdown,
                    cursor,
                    retrospective,
                    "BROADCAST_READABLE_V2_RETROSPECTIVE_POSITION_MISMATCH",
                    {"scene_id": scene_id, "segment_id": segment_id},
                )
                issues.extend(retrospective_issues)
                if retrospective_range is None or retrospective_issues:
                    parsing_failed = True
                    break
                scene_retrospective_ranges[scene_id] = retrospective_range
        previous_scene_id = scene_id

    if unsupported_types:
        issues.append(
            v2_issue(
                "BROADCAST_READABLE_UNSUPPORTED_SEGMENT_TYPE",
                "v2 Source 계약이 없는 Segment가 Presentation에 있습니다.",
                READABLE_PATH,
                {"segment_types": sorted(unsupported_types)},
            )
        )
    if not parsing_failed and cursor != len(actual_markdown):
        issues.append(
            v2_issue(
                "BROADCAST_READABLE_V2_SEGMENT_BOUNDARY_MISMATCH",
                "모든 Segment 뒤에 소비되지 않은 Actual Content가 있습니다.",
                READABLE_PATH,
                {"actual_cursor_byte": byte_offset(actual_markdown, cursor)},
            )
        )

    mapped_context_count = len(scene_context_ranges) * 2
    issues.extend(
        parsed_count_issue(
            len(scenes) * 2,
            mapped_context_count,
            "BROADCAST_READABLE_V2_CONTEXT_OCCURRENCE_MISMATCH",
            "Context Group",
        )
    )
    issues.extend(
        parsed_count_issue(
            len(expected_retrospectives),
            len(scene_retrospective_ranges),
            "BROADCAST_READABLE_V2_RETROSPECTIVE_OCCURRENCE_MISMATCH",
            "Retrospective",
        )
    )
    issues.extend(
        parsed_count_issue(
            len(expected_unit_ids),
            len(unit_mappings),
            "BROADCAST_READABLE_V2_UNIT_OCCURRENCE_MISMATCH",
            "Unit Block",
        )
    )
    issues.extend(
        parsed_count_issue(
            len(expected_panel_turn_ids),
            len(panel_turn_mappings),
            "BROADCAST_READABLE_V2_PANEL_TURN_OCCURRENCE_MISMATCH",
            "Panel Turn Block",
        )
    )

    scene_mappings: list[dict[str, object]] = []
    segment_ranges_by_scene: defaultdict[str, list[dict[str, int]]] = defaultdict(list)
    for mapping in segment_mappings:
        mapped_scene_id = mapping["scene_id"]
        byte_range = mapping["actual_byte_range"]
        if isinstance(mapped_scene_id, str) and isinstance(byte_range, dict):
            segment_ranges_by_scene[mapped_scene_id].append(byte_range)
    for scene_id, indexes in (
        (
            scene_id,
            [
                index
                for index, segment in enumerate(segments)
                if segment.get("scene_id") == scene_id
            ],
        )
        for scene_id in first_segment_by_scene
    ):
        heading_range = scene_heading_ranges.get(scene_id)
        context_ranges = scene_context_ranges.get(scene_id)
        mapped_ranges = segment_ranges_by_scene.get(scene_id, [])
        if heading_range is None or context_ranges is None or not mapped_ranges:
            continue
        retrospective_range = scene_retrospective_ranges.get(scene_id)
        retrospective = scene_fragments[scene_id]["retrospective"]
        scene_mappings.append(
            {
                "scene_id": scene_id,
                "first_global_segment_index": min(indexes),
                "last_global_segment_index": max(indexes),
                "heading_sha256": text_sha256(cast(str, scene_fragments[scene_id]["heading"])),
                "situation_context_sha256": text_sha256(
                    cast(str, scene_fragments[scene_id]["situation"])
                ),
                "sound_action_context_sha256": text_sha256(
                    cast(str, scene_fragments[scene_id]["sound"])
                ),
                "retrospective_sha256": (
                    text_sha256(retrospective) if isinstance(retrospective, str) else None
                ),
                "actual_byte_range": {
                    "byte_start": heading_range["byte_start"],
                    "byte_end": (
                        retrospective_range["byte_end"]
                        if retrospective_range is not None
                        else mapped_ranges[-1]["byte_end"]
                    ),
                },
            }
        )

    all_content_mappings: list[Mapping[str, object]] = [
        *unit_mappings,
        *panel_turn_mappings,
    ]
    issues.extend(duplicate_mapping_range_issues(all_content_mappings))
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
    retrospective_actual_count = len(scene_retrospective_ranges)
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
            "mappings_complete": len(expected_retrospectives) == retrospective_actual_count,
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
        "$schema": CURRENT_REPORT_SCHEMA_PATH,
        "schema_family": "broadcast-readable-report",
        "schema_version": CURRENT_REPORT_VERSION,
        "mapping_contract_version": MAPPING_CONTRACT_VERSION,
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
        "retrospective_meaning_coverage": conformance["retrospective_meaning_coverage"],
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
    result_issues: list[ValidationIssue] = []
    reported_mappings: list[Mapping[str, object]] = []
    for field in ("unit_mappings", "panel_turn_mappings"):
        value = report.get(field)
        if isinstance(value, list):
            reported_mappings.extend(item for item in value if isinstance(item, Mapping))
    result_issues.extend(duplicate_mapping_range_issues(reported_mappings))
    if report.get("result") == "PASS":
        result_issues.append(
            v2_issue(
                "BROADCAST_READABLE_V2_PASS_RESULT_FORBIDDEN",
                "v2 Report는 Human Editorial PASS를 선언할 수 없습니다.",
                REPORT_PATH,
                {},
            )
        )
    if (
        broadcast_readable_config.get("enabled") is not True
        or broadcast_readable_config.get("profile_id") != "BROADCAST_READABLE_SCRIPT"
        or broadcast_readable_config.get("profile_version") != "2.0.0"
    ):
        return [
            *result_issues,
            v2_issue(
                "BROADCAST_READABLE_V2_CONFIG_BINDING_INVALID",
                "v2 Config Profile 결속이 활성 2.0.0 계약과 다릅니다.",
                "00_PROJECT/broadcast_readable_config.json",
                {},
            ),
        ]
    current_expected = build_broadcast_readable_report_v2(
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
    raw_issues = current_expected["issues"]
    issues = [
        *result_issues,
        *(list(raw_issues) if isinstance(raw_issues, list) else []),
    ]
    report_version = report.get("schema_version")
    if report_version == CURRENT_REPORT_VERSION:
        issues.extend(owner_mapping_contract_issues(report, actual_markdown))
        comparable_expected = current_expected
    elif report_version == LEGACY_REPORT_VERSION:
        legacy_expected = legacy_report_2_0_from_current(current_expected)
        comparable_expected = expected_report_for_mapping_contract(
            legacy_expected,
            report,
        )
    else:
        comparable_expected = current_expected
        issues.append(
            v2_issue(
                "BROADCAST_READABLE_V2_REPORT_VERSION_UNSUPPORTED",
                "Broadcast Readable v2 Report Version이 지원 범위와 다릅니다.",
                REPORT_PATH,
                {"schema_version": report_version},
            )
        )
    if dict(report) != comparable_expected:
        issues.append(
            v2_issue(
                "BROADCAST_READABLE_V2_REPORT_STALE",
                "저장 v2 Report가 현재 입력·Actual Output Mapping과 다릅니다.",
                REPORT_PATH,
                {
                    "expected_report_sha256": document_sha256(comparable_expected),
                    "actual_report_sha256": document_sha256(report),
                },
            )
        )
    return issues
