"""검증된 Screenplay Unit에서 방송·재연 문서를 결정론적으로 파생한다."""

import re
import unicodedata
from collections.abc import Mapping, Sequence
from pathlib import PurePath

from VALIDATORS.exceptions import ConfigurationError

DRAMA_UNIT_TYPES = frozenset(
    {
        "ACTION",
        "SOUND",
        "DIALOGUE",
        "INNER_MONOLOGUE",
        "HALLUCINATION",
        "MESSAGE",
        "CHAT",
        "NOTE",
        "RECORDING",
        "SCREEN_TEXT",
    }
)
NARRATION_UNIT_TYPES = frozenset({"NARRATION"})
UNIT_LAYER_BY_TYPE = {
    **{unit_type: "DRAMA" for unit_type in DRAMA_UNIT_TYPES},
    **{unit_type: "NARRATION" for unit_type in NARRATION_UNIT_TYPES},
}
CHARACTER_AUTHORED_TYPES = frozenset(
    {
        "NARRATION",
        "INNER_MONOLOGUE",
        "HALLUCINATION",
        "MESSAGE",
        "CHAT",
        "NOTE",
        "RECORDING",
    }
)
TRACE_REFERENCE_FIELDS = (
    "fact_ids",
    "clue_ids",
    "crime_event_ids",
    "harm_ids",
    "development_function_ids",
    "reveal_target_ids",
)
TRACE_FIELD_LABELS = {
    "fact_ids": "FACT",
    "clue_ids": "CLUE",
    "crime_event_ids": "EVENT",
    "harm_ids": "HARM",
    "development_function_ids": "DEV",
    "reveal_target_ids": "REVEAL",
}
CONTEXT_LABELS = {
    "location_description": "장소",
    "time_description": "시간",
    "previous_scene_id": "이전 장면",
    "background_music_description": "배경 음악",
    "sound_cues": "환경 음향",
    "opening_character_state": "시작 인물 상태",
    "opening_emotional_state": "시작 감정 상태",
    "action_summary": "행동 개요",
    "audience_information_gain": "관객 정보 획득",
    "retrospective_meaning": "사후적 의미",
}
SEGMENT_START = re.compile(
    r"<!-- SEGMENT:(?P<segment_id>SEG-[A-Z0-9_-]+) "
    r"TYPE:(?P<segment_type>[A-Z_]+) "
    r"SCENE:(?P<scene_id>SCN-[A-Z0-9_-]+) "
    r"DURATION:(?P<duration>[0-9]+(?:\.[0-9]+)?) -->"
)


def normalize_line_endings(value: str) -> str:
    """입력 의미를 바꾸지 않고 줄바꿈만 LF로 정규화한다."""
    return value.replace("\r\n", "\n").replace("\r", "\n")


def fail(code: str, message: str) -> ConfigurationError:
    """결정론적 Renderer 구성 오류를 코드와 함께 만든다."""
    return ConfigurationError(f"{code}: {message}")


def mapping_items(value: object, field: str) -> list[Mapping[str, object]]:
    """객체 배열 필드를 엄격하게 읽는다."""
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        raise fail("SCREENPLAY_RENDER_INPUT_INVALID", f"{field}는 객체 배열이어야 합니다.")
    if not all(isinstance(item, Mapping) for item in value):
        raise fail(
            "SCREENPLAY_RENDER_INPUT_INVALID",
            f"{field}의 모든 항목은 객체여야 합니다.",
        )
    return [item for item in value if isinstance(item, Mapping)]


def required_mapping(document: Mapping[str, object], field: str) -> Mapping[str, object]:
    """필수 객체 필드를 엄격하게 읽는다."""
    value = document.get(field)
    if not isinstance(value, Mapping):
        raise fail("SCREENPLAY_RENDER_INPUT_INVALID", f"{field}는 객체여야 합니다.")
    return value


def required_string(document: Mapping[str, object], field: str) -> str:
    """필수 비어 있지 않은 문자열 필드를 엄격하게 읽는다."""
    value = document.get(field)
    if not isinstance(value, str) or not value.strip():
        raise fail(
            "SCREENPLAY_RENDER_INPUT_INVALID",
            f"{field}는 비어 있지 않은 문자열이어야 합니다.",
        )
    return value


def required_number(document: Mapping[str, object], field: str) -> float:
    """필수 양의 숫자 필드를 엄격하게 읽는다."""
    value = document.get(field)
    if not isinstance(value, int | float) or isinstance(value, bool) or value <= 0:
        raise fail("SCREENPLAY_RENDER_INPUT_INVALID", f"{field}는 양수여야 합니다.")
    return float(value)


def string_items(document: Mapping[str, object], field: str) -> list[str]:
    """문자열 배열 필드를 엄격하게 읽는다."""
    values = document.get(field)
    if not isinstance(values, Sequence) or isinstance(values, (str, bytes)):
        raise fail("SCREENPLAY_RENDER_INPUT_INVALID", f"{field}는 문자열 배열이어야 합니다.")
    if not all(isinstance(value, str) for value in values):
        raise fail(
            "SCREENPLAY_RENDER_INPUT_INVALID",
            f"{field}의 모든 항목은 문자열이어야 합니다.",
        )
    return [value for value in values if isinstance(value, str)]


def sorted_scenes(screenplay_units: Mapping[str, object]) -> list[Mapping[str, object]]:
    """Screenplay Scene을 선언된 연속 순서대로 반환한다."""
    scenes = mapping_items(screenplay_units.get("scenes"), "scenes")
    expected = list(range(1, len(scenes) + 1))
    orders = [scene.get("order") for scene in scenes]
    if orders != expected:
        raise fail(
            "REENACTMENT_SCENE_SEQUENCE_INVALID",
            f"Scene order가 배열 순서와 다릅니다: actual={orders}, expected={expected}",
        )
    return scenes


def ordered_scene_units(scene: Mapping[str, object]) -> list[Mapping[str, object]]:
    """한 Scene의 Unit을 선언된 연속 순서대로 반환한다."""
    units = mapping_items(scene.get("units"), "units")
    expected = list(range(1, len(units) + 1))
    orders = [unit.get("order") for unit in units]
    if orders != expected:
        raise fail(
            "REENACTMENT_UNIT_ORDER_INVALID",
            f"Unit order가 배열 순서와 다릅니다: actual={orders}, expected={expected}",
        )
    return units


def presentation_segments(
    presentation_plan: Mapping[str, object],
) -> list[Mapping[str, object]]:
    """방송 시작 시각과 배열 순서가 일치하는 Segment를 반환한다."""
    segments = mapping_items(presentation_plan.get("segments"), "segments")
    starts: list[float] = []
    for segment in segments:
        value = segment.get("start_sec")
        if not isinstance(value, int | float) or isinstance(value, bool) or value < 0:
            raise fail(
                "PRESENTATION_SEGMENT_INVALID",
                "Segment start_sec는 0 이상의 숫자여야 합니다.",
            )
        starts.append(float(value))
    if starts != sorted(starts):
        raise fail(
            "PRESENTATION_SEGMENT_INVALID",
            f"Segment 배열이 start_sec 순서가 아닙니다: {starts}",
        )
    return segments


def unit_records_by_segment(
    screenplay_units: Mapping[str, object],
) -> dict[str, list[tuple[str, Mapping[str, object]]]]:
    """Scene 순서를 보존해 Unit을 Segment별로 묶는다."""
    records: dict[str, list[tuple[str, Mapping[str, object]]]] = {}
    seen_unit_ids: set[str] = set()
    for scene in sorted_scenes(screenplay_units):
        scene_id = required_string(scene, "scene_id")
        for unit in ordered_scene_units(scene):
            unit_id = required_string(unit, "unit_id")
            if unit_id in seen_unit_ids:
                raise fail(
                    "SCREENPLAY_UNIT_ID_DUPLICATED",
                    f"unit_id가 중복되었습니다: {unit_id}",
                )
            seen_unit_ids.add(unit_id)
            segment_id = required_string(unit, "segment_id")
            records.setdefault(segment_id, []).append((scene_id, unit))
    return records


def unit_trace_marker(unit: Mapping[str, object]) -> str:
    """Unit 참조에서만 방송 내부 추적 Marker를 만든다."""
    unit_id = required_string(unit, "unit_id")
    references = required_mapping(unit, "references")
    fields = [f"UNIT:{unit_id}"]
    for key in TRACE_REFERENCE_FIELDS:
        values = sorted(string_items(references, key))
        if values:
            fields.append(f"{TRACE_FIELD_LABELS[key]}:{','.join(values)}")
    return f"<!-- {' '.join(fields)} -->"


def crime_trace_marker(
    units: Sequence[Mapping[str, object]],
    crime_event_contract: Mapping[str, object],
) -> str | None:
    """Segment에 실제 배치된 Unit 참조의 합집합으로 범죄 추적 Block을 만든다."""
    values_by_key: dict[str, set[str]] = {
        "crime_event_ids": set(),
        "harm_ids": set(),
        "development_function_ids": set(),
    }
    for unit in units:
        references = required_mapping(unit, "references")
        for key in values_by_key:
            values_by_key[key].update(string_items(references, key))
    if not any(values_by_key.values()):
        return None
    lines = ["<!-- CRIME_TRACE"]
    event_ids = sorted(values_by_key["crime_event_ids"])
    if event_ids:
        lines.append(f"EVENT={','.join(event_ids)}")
    contract_event_id = crime_event_contract.get("event_id")
    action_type = crime_event_contract.get("core_action_type")
    if (
        isinstance(contract_event_id, str)
        and contract_event_id in values_by_key["crime_event_ids"]
        and isinstance(action_type, str)
    ):
        lines.append(f"ACTION={action_type}")
    harm_ids = sorted(values_by_key["harm_ids"])
    if harm_ids:
        lines.append(f"HARM={','.join(harm_ids)}")
    function_ids = sorted(values_by_key["development_function_ids"])
    if function_ids:
        lines.append(f"DEV={','.join(function_ids)}")
    lines.append("-->")
    return "\n".join(lines)


def broadcast_unit_text(unit: Mapping[str, object]) -> str:
    """Unit text를 교정하지 않고 방송 Layer의 가시 블록으로 감싼다."""
    unit_type = required_string(unit, "type")
    text = normalize_line_endings(required_string(unit, "text"))
    if unit_type == "ACTION":
        return f"[지문] {text}"
    if unit_type == "SOUND":
        return f"[음향] {text}"
    if unit_type == "SCREEN_TEXT":
        return f"[화면 문구] {text}"
    speaker_id = required_string(unit, "speaker_id")
    if unit_type == "DIALOGUE":
        return f"{speaker_id}: {text}"
    return f"[{unit_type}] {speaker_id}: {text}"


def render_segment(
    segment: Mapping[str, object],
    records: Sequence[tuple[str, Mapping[str, object]]],
    crime_event_contract: Mapping[str, object],
) -> str:
    """한 Presentation Segment를 표준 Marker와 Unit 본문으로 렌더링한다."""
    segment_id = required_string(segment, "segment_id")
    segment_type = required_string(segment, "segment_type")
    scene_id = required_string(segment, "scene_id")
    duration_text = f"{required_number(segment, 'duration_sec'):g}"
    mismatched_scenes = sorted({record[0] for record in records if record[0] != scene_id})
    if mismatched_scenes:
        raise fail(
            "SCREENPLAY_SEGMENT_SCENE_MISMATCH",
            f"{segment_id} Unit의 Scene이 Presentation과 다릅니다: {mismatched_scenes}",
        )
    units = [record[1] for record in records]
    trace = crime_trace_marker(units, crime_event_contract)
    blocks: list[str] = []
    if trace is not None:
        blocks.append(trace)
    blocks.extend(
        f"{unit_trace_marker(unit)}\n{broadcast_unit_text(unit)}" for unit in units
    )
    body = "\n".join(blocks)
    return (
        f"<!-- SEGMENT:{segment_id} TYPE:{segment_type} "
        f"SCENE:{scene_id} DURATION:{duration_text} -->\n"
        f"{body}\n"
        f"<!-- END_SEGMENT:{segment_id} -->"
    )


def render_unit_layer(
    screenplay_units: Mapping[str, object],
    presentation_plan: Mapping[str, object],
    crime_event_contract: Mapping[str, object],
    segment_type: str,
    included_types: frozenset[str],
) -> str:
    """지정 방송 계층의 Segment를 Unit 원문으로 렌더링한다."""
    records_by_segment = unit_records_by_segment(screenplay_units)
    planned = [
        segment
        for segment in presentation_segments(presentation_plan)
        if segment.get("segment_type") == segment_type
    ]
    planned_ids = {required_string(segment, "segment_id") for segment in planned}
    rendered: list[str] = []
    for segment in planned:
        segment_id = required_string(segment, "segment_id")
        records = records_by_segment.get(segment_id, [])
        if not records:
            raise fail(
                "PRESENTATION_SEGMENT_CONTENT_MISSING",
                f"{segment_id}에 렌더링할 Unit이 없습니다.",
            )
        invalid_types = sorted(
            {
                required_string(unit, "type")
                for _scene_id, unit in records
                if unit.get("type") not in included_types
            }
        )
        if invalid_types:
            raise fail(
                "SCREENPLAY_UNIT_LAYER_MISMATCH",
                f"{segment_id}에 {segment_type} 계층이 아닌 Unit이 있습니다: {invalid_types}",
            )
        rendered.append(render_segment(segment, records, crime_event_contract))
    unplanned_ids = sorted(
        segment_id
        for segment_id, records in records_by_segment.items()
        if any(unit.get("type") in included_types for _scene_id, unit in records)
        and segment_id not in planned_ids
    )
    if unplanned_ids:
        raise fail(
            "SCREENPLAY_SEGMENT_REFERENCE_INVALID",
            f"Unit이 참조한 {segment_type} Segment가 Presentation에 없습니다: {unplanned_ids}",
        )
    if not rendered:
        raise fail(
            "PRESENTATION_SEGMENT_CONTENT_MISSING",
            f"{segment_type} Segment가 없습니다.",
        )
    return "\n\n".join(rendered) + "\n"


def render_drama_layer(
    screenplay_units: Mapping[str, object],
    presentation_plan: Mapping[str, object],
    crime_event_contract: Mapping[str, object],
) -> str:
    """Screenplay Unit의 Drama 유형만 방송 Drama Layer로 렌더링한다."""
    return render_unit_layer(
        screenplay_units,
        presentation_plan,
        crime_event_contract,
        "DRAMA",
        DRAMA_UNIT_TYPES,
    )


def render_narration_layer(
    screenplay_units: Mapping[str, object],
    presentation_plan: Mapping[str, object],
    crime_event_contract: Mapping[str, object],
) -> str:
    """Screenplay Unit의 Narration만 방송 Narration Layer로 렌더링한다."""
    return render_unit_layer(
        screenplay_units,
        presentation_plan,
        crime_event_contract,
        "NARRATION",
        NARRATION_UNIT_TYPES,
    )


def reaction_by_id(
    reaction_segments: Mapping[str, object],
) -> dict[str, Mapping[str, object]]:
    """Reaction Contract Segment를 고유 ID로 색인한다."""
    reactions = mapping_items(reaction_segments.get("reaction_segments"), "reaction_segments")
    result: dict[str, Mapping[str, object]] = {}
    for reaction in reactions:
        reaction_id = required_string(reaction, "reaction_segment_id")
        if reaction_id in result:
            raise fail("PANEL_REACTION_ID_DUPLICATED", f"중복 Reaction ID: {reaction_id}")
        result[reaction_id] = reaction
    return result


def render_panel_layer(
    reaction_segments: Mapping[str, object],
    presentation_plan: Mapping[str, object],
) -> str:
    """기존 Reaction Contract를 방송 Panel Layer로 렌더링한다."""
    reactions = reaction_by_id(reaction_segments)
    rendered: list[str] = []
    used_reaction_ids: set[str] = set()
    for segment in presentation_segments(presentation_plan):
        if segment.get("segment_type") != "PANEL_REACTION":
            continue
        segment_id = required_string(segment, "segment_id")
        reaction_id = required_string(segment, "reaction_segment_id")
        reaction = reactions.get(reaction_id)
        if reaction is None:
            raise fail(
                "PANEL_REACTION_SEGMENT_MISSING",
                f"{segment_id}가 참조한 Reaction이 없습니다: {reaction_id}",
            )
        turns = mapping_items(reaction.get("turns"), "turns")
        if not turns:
            raise fail("PANEL_REACTION_SEGMENT_MISSING", f"{reaction_id}에 Turn이 없습니다.")
        first_panelist = required_string(turns[0], "panelist_id")
        function = required_string(reaction, "segment_function")
        body = [f"[{reaction_id}] [{first_panelist}] [{function}]"]
        body.extend(
            f"[{required_string(turn, 'panelist_id')}] “"
            f"{normalize_line_endings(required_string(turn, 'spoken_line'))}”"
            for turn in turns
        )
        rendered.append(render_plain_segment(segment, "\n".join(body)))
        used_reaction_ids.add(reaction_id)
    unused = sorted(set(reactions) - used_reaction_ids)
    if unused:
        raise fail(
            "PANEL_REACTION_SEGMENT_UNPLANNED",
            f"Presentation에 배치되지 않은 Reaction이 있습니다: {unused}",
        )
    if not rendered:
        raise fail("PANEL_REACTION_SEGMENT_MISSING", "Panel Reaction Segment가 없습니다.")
    return "\n\n".join(rendered) + "\n"


def render_plain_segment(segment: Mapping[str, object], body: str) -> str:
    """비-Unit 계층 본문을 표준 Segment Marker로 감싼다."""
    segment_id = required_string(segment, "segment_id")
    segment_type = required_string(segment, "segment_type")
    scene_id = required_string(segment, "scene_id")
    duration_text = f"{required_number(segment, 'duration_sec'):g}"
    normalized_body = normalize_line_endings(body)
    if not normalized_body.strip():
        raise fail("PRESENTATION_SEGMENT_CONTENT_MISSING", f"{segment_id} 본문이 비었습니다.")
    return (
        f"<!-- SEGMENT:{segment_id} TYPE:{segment_type} "
        f"SCENE:{scene_id} DURATION:{duration_text} -->\n"
        f"{normalized_body}\n"
        f"<!-- END_SEGMENT:{segment_id} -->"
    )


def extract_layer_segments(content: str) -> dict[str, str]:
    """한 Layer에서 완전한 Segment Block을 손실 없이 추출한다."""
    normalized = normalize_line_endings(content)
    result: dict[str, str] = {}
    for marker in SEGMENT_START.finditer(normalized):
        segment_id = marker.group("segment_id")
        end_marker = f"<!-- END_SEGMENT:{segment_id} -->"
        end_position = normalized.find(end_marker, marker.end())
        if end_position < 0:
            raise fail(
                "BROADCAST_LAYER_SEGMENT_INVALID",
                f"{segment_id} 종료 Marker가 없습니다.",
            )
        next_marker = SEGMENT_START.search(normalized, marker.end())
        if next_marker is not None and next_marker.start() < end_position:
            raise fail(
                "BROADCAST_LAYER_SEGMENT_INVALID",
                f"{segment_id} 안에 다른 Segment가 중첩되었습니다.",
            )
        if segment_id in result:
            raise fail(
                "BROADCAST_LAYER_SEGMENT_DUPLICATED",
                f"Layer에 {segment_id}가 중복되었습니다.",
            )
        result[segment_id] = normalized[marker.start() : end_position + len(end_marker)]
    if normalized.count("<!-- END_SEGMENT:") != len(result):
        raise fail("BROADCAST_LAYER_SEGMENT_INVALID", "짝이 없는 Segment Marker가 있습니다.")
    return result


def render_broadcast_master(
    presentation_plan: Mapping[str, object],
    layers: Mapping[str, str],
) -> str:
    """Layer Segment를 Presentation 순서 그대로 하나의 Broadcast Master로 결합한다."""
    indexed_layers = {
        artifact_name: extract_layer_segments(content)
        for artifact_name, content in layers.items()
    }
    rendered: list[str] = []
    used: set[tuple[str, str]] = set()
    for segment in presentation_segments(presentation_plan):
        segment_id = required_string(segment, "segment_id")
        source_artifact = required_string(segment, "source_artifact")
        source_segments = indexed_layers.get(source_artifact)
        if source_segments is None or segment_id not in source_segments:
            raise fail(
                "BROADCAST_MASTER_SEGMENT_MISSING",
                f"{source_artifact}에 {segment_id}가 없습니다.",
            )
        rendered.append(source_segments[segment_id])
        used.add((source_artifact, segment_id))
    unused = sorted(
        (artifact_name, segment_id)
        for artifact_name, segments in indexed_layers.items()
        for segment_id in segments
        if (artifact_name, segment_id) not in used
    )
    if unused:
        raise fail(
            "BROADCAST_MASTER_SEGMENT_UNPLANNED",
            f"Presentation에 없는 Layer Segment가 있습니다: {unused}",
        )
    return "\n\n".join(rendered) + "\n"


def markdown_cell(value: str) -> str:
    """Canonical 인물 Metadata만 Markdown 표 셀에 안전하게 넣는다."""
    return normalize_line_endings(value).replace("|", "\\|").replace("\n", "<br>")


def characters_by_id(
    characters: Mapping[str, object],
) -> dict[str, Mapping[str, object]]:
    """Canonical Characters를 고유 ID로 색인한다."""
    result: dict[str, Mapping[str, object]] = {}
    for character in mapping_items(characters.get("characters"), "characters"):
        character_id = required_string(character, "character_id")
        if character_id in result:
            raise fail("REENACTMENT_CAST_REQUIRED", f"중복 Character ID: {character_id}")
        required_string(character, "name")
        required_string(character, "role")
        result[character_id] = character
    if not result:
        raise fail("REENACTMENT_CAST_REQUIRED", "Canonical Character가 없습니다.")
    return result


def cast_order(
    screenplay_units: Mapping[str, object],
    character_map: Mapping[str, Mapping[str, object]],
) -> list[str]:
    """첫 발화 순서 뒤 Character ID 순서로 Cast를 정렬한다."""
    first_appearance: list[str] = []
    for scene in sorted_scenes(screenplay_units):
        for unit in ordered_scene_units(scene):
            speaker_id = unit.get("speaker_id")
            if isinstance(speaker_id, str) and speaker_id not in first_appearance:
                if speaker_id not in character_map:
                    raise fail(
                        "REENACTMENT_SPEAKER_UNKNOWN",
                        f"Canonical Characters에 없는 speaker_id입니다: {speaker_id}",
                    )
                first_appearance.append(speaker_id)
    remaining = sorted(set(character_map) - set(first_appearance))
    return [*first_appearance, *remaining]


def relationship_texts(
    relationships: Mapping[str, object],
    character_map: Mapping[str, Mapping[str, object]],
) -> dict[str, str]:
    """표시 요약 또는 이름 기반 Legacy 대체 문구를 인물별로 만든다."""
    values: dict[str, list[str]] = {character_id: [] for character_id in character_map}
    records = mapping_items(relationships.get("relationships"), "relationships")
    for relationship in sorted(records, key=lambda item: required_string(item, "relationship_id")):
        from_id = required_string(relationship, "from")
        to_id = required_string(relationship, "to")
        required_string(relationship, "engine")
        if from_id not in character_map or to_id not in character_map:
            raise fail(
                "REENACTMENT_CAST_REQUIRED",
                f"Relationship가 알 수 없는 인물을 참조합니다: {from_id}, {to_id}",
            )
        from_name = required_string(character_map[from_id], "name")
        to_name = required_string(character_map[to_id], "name")
        display_summary = relationship.get("display_summary")
        if relationships.get("schema_version") == "1.1.0":
            display_summary = required_string(relationship, "display_summary")
        if isinstance(display_summary, str) and display_summary.strip():
            summary = normalize_line_endings(display_summary)
            values[from_id].append(f"{to_name}: {summary}")
            values[to_id].append(f"{from_name}: {summary}")
        else:
            values[from_id].append(f"{to_name}와 연결된 기존 관계")
            values[to_id].append(f"{from_name}와 연결된 기존 관계")
    return {
        character_id: "; ".join(entries) if entries else "—"
        for character_id, entries in values.items()
    }


def render_context_value(field: str, value: object) -> str:
    """Profile이 요청한 Scene Context 값을 결정론적 Markdown 문구로 만든다."""
    if field == "sound_cues":
        cues = mapping_items(value, "sound_cues")
        if not cues:
            return "—"
        descriptions: list[str] = []
        expected_order = 1
        for cue in cues:
            if cue.get("order") != expected_order:
                raise fail(
                    "SCREENPLAY_SOUND_CUE_ORDER_INVALID",
                    "Sound Cue 순서가 배열 순서와 다릅니다.",
                )
            descriptions.append(required_string(cue, "description"))
            expected_order += 1
        return " / ".join(descriptions)
    if value is None:
        return "—"
    if not isinstance(value, str) or not value.strip():
        raise fail("REENACTMENT_CONTEXT_MISSING", f"{field} Context가 비었습니다.")
    return normalize_line_endings(value).replace("\n", "<br>")


def reenactment_unit_text(
    unit: Mapping[str, object],
    character_map: Mapping[str, Mapping[str, object]],
    profile: Mapping[str, object],
) -> str:
    """Output Profile Template로 한 Unit을 내부 Marker 없이 렌더링한다."""
    unit_type = required_string(unit, "type")
    text = normalize_line_endings(required_string(unit, "text"))
    render_contract = required_mapping(profile, "render_contract")
    if unit_type == "ACTION":
        return required_string(render_contract, "direction_template").format(text=text)
    if unit_type == "SOUND":
        return required_string(render_contract, "sound_template").format(text=text)
    labels = required_mapping(render_contract, "special_unit_labels")
    if unit_type == "SCREEN_TEXT":
        label = required_string(labels, unit_type)
        return f"[{label}] {text}"
    speaker_id = required_string(unit, "speaker_id")
    character = character_map.get(speaker_id)
    if character is None:
        raise fail(
            "REENACTMENT_SPEAKER_UNKNOWN",
            f"Canonical Characters에 없는 speaker_id입니다: {speaker_id}",
        )
    speaker_name = required_string(character, "name")
    if unit_type == "DIALOGUE":
        return required_string(render_contract, "speaker_template").format(
            speaker_name=speaker_name,
            text=text,
        )
    if unit_type in CHARACTER_AUTHORED_TYPES:
        label = required_string(labels, unit_type)
        return required_string(render_contract, "character_authored_template").format(
            label=label,
            speaker_name=speaker_name,
            text=text,
        )
    raise fail("REENACTMENT_UNIT_TYPE_UNSUPPORTED", f"지원하지 않는 Unit 유형: {unit_type}")


def render_reenactment_character_script(
    screenplay_units: Mapping[str, object],
    characters: Mapping[str, object],
    relationships: Mapping[str, object],
    output_profile: Mapping[str, object],
) -> str:
    """Screenplay Unit과 Canonical Cast에서 재연용 인물별 대사 문서를 만든다."""
    title = normalize_line_endings(required_string(screenplay_units, "title"))
    project_id = required_string(screenplay_units, "project_id")
    truth_classification = required_string(screenplay_units, "source_truth_classification")
    profile_id = required_string(output_profile, "profile_id")
    profile_version = required_string(output_profile, "profile_version")
    filter_contract = required_mapping(output_profile, "filter_contract")
    included_layers = set(string_items(filter_contract, "included_layers"))
    excluded_layers = set(string_items(filter_contract, "excluded_layers"))
    included_types = set(string_items(filter_contract, "included_unit_types"))
    excluded_types = set(string_items(filter_contract, "excluded_unit_types"))
    if (
        included_layers.intersection(excluded_layers)
        or included_types.intersection(excluded_types)
    ):
        raise fail(
            "REENACTMENT_OUTPUT_PROFILE_INVALID",
            "Output Profile의 포함·제외 Layer 또는 Unit 유형이 겹칩니다.",
        )
    character_map = characters_by_id(characters)
    ordered_character_ids = cast_order(screenplay_units, character_map)
    relations = relationship_texts(relationships, character_map)
    document_contract = required_mapping(output_profile, "document_contract")
    headings = string_items(document_contract, "required_headings")
    if len(headings) != 3:
        raise fail("REENACTMENT_OUTPUT_PROFILE_INVALID", "필수 Heading은 세 개여야 합니다.")
    cast_contract = required_mapping(document_contract, "cast_table")
    columns = string_items(cast_contract, "columns")
    if len(columns) != 3:
        raise fail("REENACTMENT_OUTPUT_PROFILE_INVALID", "Cast 표 열은 세 개여야 합니다.")
    lines = [
        f"# {title} — 인물별 대사 스크립트",
        "",
        f"## {headings[0]}",
        "",
        f"- 작품명: {title}",
        f"- 프로젝트: {project_id}",
        "- 작성일: 편집 검토 시 기록",
        f"- 작품 구분: {truth_classification}",
        f"- 출력 프로필: {profile_id} {profile_version}",
        "",
        "### 구성 원칙",
        "",
        "- 지문·음향·인물 발화와 화면 문구를 Scene 순서대로 수록합니다.",
        "- 패널 반응·전문가 분석·시청자 유도와 내부 추적 표시는 수록하지 않습니다.",
        "- 발화와 지문은 Canonical Screenplay Unit 원문을 교정 없이 보존합니다.",
        "",
        f"## {headings[1]}",
        "",
        f"| {columns[0]} | {columns[1]} | {columns[2]} |",
        "|---|---|---|",
    ]
    for character_id in ordered_character_ids:
        character = character_map[character_id]
        lines.append(
            "| "
            + " | ".join(
                (
                    markdown_cell(required_string(character, "name")),
                    markdown_cell(required_string(character, "role")),
                    markdown_cell(relations[character_id]),
                )
            )
            + " |"
        )
    lines.extend(("", f"## {headings[2]}", ""))
    scene_heading_template = required_string(document_contract, "scene_heading_template")
    context_fields = string_items(document_contract, "scene_context_fields")
    for scene in sorted_scenes(screenplay_units):
        scene_order = scene.get("order")
        if not isinstance(scene_order, int) or isinstance(scene_order, bool):
            raise fail("REENACTMENT_SCENE_SEQUENCE_INVALID", "Scene order가 정수가 아닙니다.")
        scene_title = normalize_line_endings(required_string(scene, "title"))
        lines.append(scene_heading_template.format(order=scene_order, title=scene_title))
        lines.append("")
        context = required_mapping(scene, "context")
        for field in context_fields:
            label = CONTEXT_LABELS.get(field)
            if label is None:
                raise fail(
                    "REENACTMENT_OUTPUT_PROFILE_INVALID",
                    f"지원하지 않는 Context 필드: {field}",
                )
            lines.append(f"- {label}: {render_context_value(field, context.get(field))}")
        lines.append("")
        rendered_count = 0
        for unit in ordered_scene_units(scene):
            unit_type = required_string(unit, "type")
            unit_layer = UNIT_LAYER_BY_TYPE.get(unit_type)
            if unit_layer is None:
                raise fail(
                    "REENACTMENT_UNIT_TYPE_UNSUPPORTED",
                    f"Profile Layer를 해석할 수 없는 Unit 유형: {unit_type}",
                )
            if unit_layer not in included_layers or unit_layer in excluded_layers:
                continue
            if unit_type in excluded_types:
                continue
            if unit_type not in included_types:
                raise fail(
                    "REENACTMENT_UNIT_TYPE_UNSUPPORTED",
                    f"Profile에 포함 여부가 선언되지 않은 Unit 유형: {unit_type}",
                )
            lines.append(reenactment_unit_text(unit, character_map, output_profile))
            lines.append("")
            rendered_count += 1
        if rendered_count == 0:
            raise fail(
                "REENACTMENT_CONTEXT_MISSING",
                f"Scene {scene_order}에 재연용 Unit이 없습니다.",
            )
    if not lines or lines[-1] != "":
        raise fail(
            "SCREENPLAY_RENDER_INPUT_INVALID",
            "Renderer 소유의 마지막 Unit 구분자가 없습니다.",
        )
    return "\n".join(lines[:-1]) + "\n"


def package_production_reenactment_script(reenactment_script: str) -> str:
    """검증된 재연 Script를 Production Canonical Artifact에 바이트 그대로 전달한다."""
    if not reenactment_script or not reenactment_script.endswith("\n"):
        raise fail(
            "REENACTMENT_PACKAGE_INPUT_INVALID",
            "Canonical 재연 Script는 비어 있지 않고 LF로 끝나야 합니다.",
        )
    if "\r" in reenactment_script:
        raise fail(
            "REENACTMENT_PACKAGE_INPUT_INVALID",
            "Canonical 재연 Script에는 CR 줄바꿈이 없어야 합니다.",
        )
    return reenactment_script


def reenactment_export_filename(title: str) -> str:
    """작품명을 안전한 명시적 외부 Export 파일명으로 변환한다."""
    normalized = unicodedata.normalize("NFKC", normalize_line_endings(title)).strip()
    safe_title = re.sub(r"[\\/:*?\"<>|\x00-\x1f\x7f]", "_", normalized)
    safe_title = re.sub(r"\s+", " ", safe_title).strip(" .")
    if not safe_title or safe_title in {".", ".."}:
        raise fail("REENACTMENT_EXPORT_FILENAME_INVALID", "안전한 작품명이 필요합니다.")
    filename = f"{safe_title}_인물별_대사_스크립트.md"
    if PurePath(filename).name != filename:
        raise fail("REENACTMENT_EXPORT_FILENAME_INVALID", "Export 파일명이 안전하지 않습니다.")
    return filename
