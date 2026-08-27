"""Presentation Contract v2와 Broadcast Master Script 검증."""

import re
from collections.abc import Mapping, Sequence
from itertools import pairwise
from typing import TypedDict, cast

from VALIDATORS.models import ValidationIssue

PRESENTATION_SCHEMA_VERSION = "2.0.0"
CANONICAL_PRESENTATION_MODES = frozenset(
    {"DRAMA", "NARRATION", "PANEL_REACTION", "AUDIENCE_PROMPT"}
)
PANEL_FUNCTIONS = frozenset(
    {
        "EMOTIONAL_REACTION",
        "ANOMALY_DETECTION",
        "HYPOTHESIS_GENERATION",
        "SUSPECT_DISCUSSION",
        "HYPOTHESIS_REVISION",
        "CONTRADICTION_DETECTION",
        "MORAL_REACTION",
        "TENSION_RELEASE",
        "EXPECTATION_BUILDING",
    }
)
REQUIRED_PANEL_FUNCTIONS = frozenset(
    {"HYPOTHESIS_GENERATION", "HYPOTHESIS_REVISION"}
)
REQUIRED_REASONING_FUNCTIONS = frozenset(
    {"ANOMALY_DETECTION", "CONTRADICTION_DETECTION"}
)
SEGMENT_MARKER = re.compile(
    r"<!-- SEGMENT:(?P<segment_id>SEG-[0-9]{3,}) "
    r"TYPE:(?P<segment_type>[A-Z_]+) "
    r"SCENE:(?P<scene_id>SCN-[0-9]{2,}) "
    r"DURATION:(?P<duration>[0-9]+(?:\.[0-9]+)?) -->"
)
FACT_TAG = re.compile(r"\[FACT:(FACT-[0-9]{2,})\]")
PANEL_HEADER = re.compile(
    r"\[(?P<reaction_id>RSEG-[0-9]{3,})\]\s*"
    r"\[(?P<panelist_id>PANEL-[0-9]{2,})\]\s*"
    r"\[(?P<function>[A-Z_]+)\]"
)
KOREAN_TIME = re.compile(r"(?P<hour>[01]?[0-9]|2[0-3])시\s*(?P<minute>[0-5]?[0-9])분")
COLON_TIME = re.compile(r"(?<![0-9])(?P<hour>[01]?[0-9]|2[0-3]):(?P<minute>[0-5][0-9])(?![0-9])")
KOREAN_MERIDIEM_TIME = re.compile(
    r"(?P<meridiem>오전|오후)\s*(?P<hour>0?[1-9]|1[0-2])시\s*"
    r"(?P<minute>[0-5]?[0-9])분"
)
RETROSPECTIVE_HINTS = (
    "전",
    "생성",
    "기록",
    "과거",
    "당시",
    "정전",
    "파일",
    "표시",
    "지연",
)


class ScriptSegment(TypedDict):
    """Machine-readable Marker에서 읽은 Script Segment."""

    segment_id: str
    segment_type: str
    scene_id: str
    duration_sec: float
    body: str


class ClockMention(TypedDict):
    """Script에서 추출한 절대시간과 주변 문맥."""

    minute_of_day: int
    context: str
    position: int


def make_presentation_issue(
    code: str,
    message: str,
    artifact: str,
    context: dict[str, object],
) -> ValidationIssue:
    """Presentation 문제를 공통 Issue 형식으로 생성한다."""
    return ValidationIssue(
        severity="ERROR",
        code=code,
        message=message,
        artifact=artifact,
        context=context,
    )


def mapping_items(document: Mapping[str, object], key: str) -> list[Mapping[str, object]]:
    """객체 배열 필드를 안전하게 읽는다."""
    value = document.get(key)
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, Mapping)]


def string_items(document: Mapping[str, object], key: str) -> list[str]:
    """문자열 배열 필드를 안전하게 읽는다."""
    value = document.get(key)
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, str)]


def scene_order_map(scene_cards: Mapping[str, object]) -> dict[str, int]:
    """Scene ID를 방송 순서에 대응한다."""
    result: dict[str, int] = {}
    for scene in mapping_items(scene_cards, "scenes"):
        scene_id = scene.get("scene_id")
        order = scene.get("order")
        if isinstance(scene_id, str) and isinstance(order, int) and not isinstance(order, bool):
            result[scene_id] = order
    return result


def canonical_mode(mode: object) -> str | None:
    """기존 REACTION Alias를 Canonical PANEL_REACTION으로 변환한다."""
    if mode == "REACTION":
        return "PANEL_REACTION"
    if isinstance(mode, str) and mode in CANONICAL_PRESENTATION_MODES:
        return mode
    return None


def presentation_segments(
    presentation_plan: Mapping[str, object],
) -> list[Mapping[str, object]]:
    """Presentation Timeline Segment 배열을 반환한다."""
    return mapping_items(presentation_plan, "segments")


def actual_panel_reaction_ratio(presentation_plan: Mapping[str, object]) -> float | None:
    """실제 Segment Duration 합에서 Panel Reaction 비율을 계산한다."""
    segments = presentation_segments(presentation_plan)
    durations: list[float] = []
    reaction_durations: list[float] = []
    for segment in segments:
        duration = segment.get("duration_sec")
        mode = canonical_mode(segment.get("segment_type"))
        if not isinstance(duration, int | float) or isinstance(duration, bool) or duration <= 0:
            return None
        if mode is None:
            return None
        durations.append(float(duration))
        if mode == "PANEL_REACTION":
            reaction_durations.append(float(duration))
    total = sum(durations)
    if not segments or total <= 0:
        return None
    return sum(reaction_durations) / total


def panel_required(channel: Mapping[str, object]) -> bool:
    """Channel이 실제 Panel Reaction을 요구하는지 판정한다."""
    capabilities = channel.get("capabilities")
    if not isinstance(capabilities, Mapping):
        return False
    reaction = capabilities.get("REACTION_POLICY")
    presentation = capabilities.get("PRESENTATION_POLICY")
    enabled = isinstance(reaction, Mapping) and reaction.get("enabled") is True
    if not isinstance(presentation, Mapping):
        return enabled
    modes = string_items(presentation, "modes")
    return enabled or any(canonical_mode(mode) == "PANEL_REACTION" for mode in modes)


def channel_ratio_range(channel: Mapping[str, object]) -> tuple[float, float] | None:
    """Channel의 Panel Reaction 목표 범위를 반환한다."""
    capabilities = channel.get("capabilities")
    if not isinstance(capabilities, Mapping):
        return None
    reaction = capabilities.get("REACTION_POLICY")
    if not isinstance(reaction, Mapping):
        return None
    target = reaction.get("target_ratio")
    if not isinstance(target, Mapping):
        return None
    minimum = target.get("min")
    maximum = target.get("max")
    if (
        not isinstance(minimum, int | float)
        or isinstance(minimum, bool)
        or not isinstance(maximum, int | float)
        or isinstance(maximum, bool)
    ):
        return None
    return float(minimum), float(maximum)


def validate_panel_cast(panel_cast: Mapping[str, object]) -> list[ValidationIssue]:
    """Panelist 수, ID, 기능과 지식 경계를 검증한다."""
    panelists = mapping_items(panel_cast, "panelists")
    issues: list[ValidationIssue] = []
    if len(panelists) < 2:
        issues.append(
            make_presentation_issue(
                "PANEL_CAST_MISSING",
                "서로 다른 기능을 가진 Panelist가 최소 2명 필요합니다.",
                "06_SCENE/panel_cast.json",
                {"minimum": 2, "actual": len(panelists)},
            )
        )
    panelist_ids = [
        panelist.get("panelist_id")
        for panelist in panelists
        if isinstance(panelist.get("panelist_id"), str)
    ]
    if len(panelist_ids) != len(panelists) or len(set(panelist_ids)) != len(panelist_ids):
        issues.append(
            make_presentation_issue(
                "PANEL_SPEAKER_INVALID",
                "Panelist ID가 누락되었거나 중복되었습니다.",
                "06_SCENE/panel_cast.json",
                {"panelist_ids": panelist_ids},
            )
        )
    personas = {
        panelist.get("persona")
        for panelist in panelists
        if isinstance(panelist.get("persona"), str)
    }
    if len(panelists) >= 2 and len(personas) < 2:
        issues.append(
            make_presentation_issue(
                "PANEL_CAST_MISSING",
                "Panel Cast는 최소 2개의 서로 다른 Persona를 가져야 합니다.",
                "06_SCENE/panel_cast.json",
                {"personas": sorted(cast(set[str], personas))},
            )
        )
    invalid_scopes = sorted(
        cast(str, panelist.get("panelist_id"))
        for panelist in panelists
        if panelist.get("knowledge_scope") != "REVEALED_INFORMATION_ONLY"
        and isinstance(panelist.get("panelist_id"), str)
    )
    if invalid_scopes:
        issues.append(
            make_presentation_issue(
                "REACTION_KNOWLEDGE_BOUNDARY_VIOLATION",
                "Panelist는 공개된 정보만 사용할 수 있습니다.",
                "06_SCENE/panel_cast.json",
                {"panelist_ids": invalid_scopes},
            )
        )
    return issues


def viewer_fact_reveal_orders(
    viewer_timeline: Mapping[str, object],
    scene_orders: Mapping[str, int],
) -> dict[str, int]:
    """Fact ID별 최초 Viewer 공개 Scene 순서를 계산한다."""
    result: dict[str, int] = {}
    for reveal in mapping_items(viewer_timeline, "reveals"):
        fact_id = reveal.get("fact_id")
        scene_id = reveal.get("scene_id")
        scene_order = reveal.get("scene_order")
        resolved_order = (
            scene_orders.get(scene_id)
            if isinstance(scene_id, str)
            else scene_order
            if isinstance(scene_order, int) and not isinstance(scene_order, bool)
            else None
        )
        if isinstance(fact_id, str) and isinstance(resolved_order, int):
            previous = result.get(fact_id)
            result[fact_id] = resolved_order if previous is None else min(previous, resolved_order)
    return result


def reaction_function_issues(
    reaction_segments: Sequence[Mapping[str, object]],
) -> list[ValidationIssue]:
    """CO_INVESTIGATOR에 필요한 가설 기능 분포를 검증한다."""
    functions = {
        function
        for segment in reaction_segments
        if isinstance((function := segment.get("function")), str)
    }
    invalid = sorted(functions - PANEL_FUNCTIONS)
    missing = sorted(REQUIRED_PANEL_FUNCTIONS - functions)
    if not functions.intersection(REQUIRED_REASONING_FUNCTIONS):
        missing.append("ANOMALY_DETECTION_OR_CONTRADICTION_DETECTION")
    issues: list[ValidationIssue] = []
    if invalid:
        issues.append(
            make_presentation_issue(
                "PANEL_REACTION_FUNCTION_MISSING",
                "허용되지 않은 Panel Reaction Function이 있습니다.",
                "06_SCENE/reaction_segments.json",
                {"invalid_functions": invalid},
            )
        )
    if missing:
        issues.append(
            make_presentation_issue(
                "PANEL_REACTION_FUNCTION_MISSING",
                "관객의 가설 생성·수정에 필요한 Panel Function이 누락되었습니다.",
                "06_SCENE/reaction_segments.json",
                {"missing_functions": missing},
            )
        )
    return issues


def reaction_reference_issues(
    reaction_segments: Sequence[Mapping[str, object]],
    panel_cast: Mapping[str, object],
    scene_cards: Mapping[str, object],
    viewer_timeline: Mapping[str, object],
    facts: Mapping[str, object],
    clue_matrix: Mapping[str, object],
) -> list[ValidationIssue]:
    """Panel 화자, 단서, Fact 공개 경계와 가설 변화를 검증한다."""
    panelist_ids = {
        panelist.get("panelist_id")
        for panelist in mapping_items(panel_cast, "panelists")
        if isinstance(panelist.get("panelist_id"), str)
    }
    panelist_functions = {
        cast(str, panelist.get("panelist_id")): set(
            string_items(panelist, "allowed_functions")
        )
        for panelist in mapping_items(panel_cast, "panelists")
        if isinstance(panelist.get("panelist_id"), str)
    }
    fact_ids = {
        fact.get("fact_id")
        for fact in mapping_items(facts, "facts")
        if isinstance(fact.get("fact_id"), str)
    }
    clues = {
        cast(str, clue.get("clue_id")): clue
        for clue in mapping_items(clue_matrix, "clues")
        if isinstance(clue.get("clue_id"), str)
    }
    orders = scene_order_map(scene_cards)
    fact_reveal_orders = viewer_fact_reveal_orders(viewer_timeline, orders)
    issues: list[ValidationIssue] = []
    for segment in reaction_segments:
        reaction_id = segment.get("reaction_segment_id")
        panelist_id = segment.get("panelist_id")
        after_scene_id = segment.get("after_scene_id")
        function = segment.get("function")
        reaction_context = {"reaction_segment_id": reaction_id}
        if panelist_id not in panelist_ids:
            issues.append(
                make_presentation_issue(
                    "PANEL_SPEAKER_INVALID",
                    "Reaction Segment의 Panelist ID가 Panel Cast에 없습니다.",
                    "06_SCENE/reaction_segments.json",
                    {**reaction_context, "panelist_id": panelist_id},
                )
            )
        elif (
            isinstance(panelist_id, str)
            and isinstance(function, str)
            and function not in panelist_functions.get(panelist_id, set())
        ):
            issues.append(
                make_presentation_issue(
                    "PANEL_SPEAKER_INVALID",
                    "Panelist에게 허용되지 않은 Reaction Function입니다.",
                    "06_SCENE/reaction_segments.json",
                    {
                        **reaction_context,
                        "panelist_id": panelist_id,
                        "function": function,
                    },
                )
            )
        scene_order = orders.get(after_scene_id) if isinstance(after_scene_id, str) else None
        evidence_ids = string_items(segment, "evidence_ids")
        broken_evidence = sorted(
            evidence_id for evidence_id in evidence_ids if evidence_id not in clues
        )
        if broken_evidence:
            issues.append(
                make_presentation_issue(
                    "REACTION_EVIDENCE_REFERENCE_BROKEN",
                    "Reaction이 존재하지 않는 Clue를 참조합니다.",
                    "06_SCENE/reaction_segments.json",
                    {**reaction_context, "evidence_ids": broken_evidence},
                )
            )
        premature_evidence = sorted(
            evidence_id
            for evidence_id in evidence_ids
            if evidence_id in clues
            and isinstance(scene_order, int)
            and isinstance(clues[evidence_id].get("introduced_scene_order"), int)
            and cast(int, clues[evidence_id].get("introduced_scene_order")) > scene_order
        )
        if premature_evidence:
            issues.append(
                make_presentation_issue(
                    "REACTION_EVIDENCE_NOT_YET_REVEALED",
                    "Panel이 아직 공개되지 않은 Clue를 사용했습니다.",
                    "06_SCENE/reaction_segments.json",
                    {**reaction_context, "evidence_ids": premature_evidence},
                )
            )
        known_fact_ids = string_items(segment, "known_fact_ids")
        unavailable_facts = sorted(
            fact_id
            for fact_id in known_fact_ids
            if fact_id not in fact_ids
            or fact_id not in fact_reveal_orders
            or not isinstance(scene_order, int)
            or fact_reveal_orders[fact_id] > scene_order
        )
        if unavailable_facts:
            issues.append(
                make_presentation_issue(
                    "REACTION_KNOWLEDGE_BOUNDARY_VIOLATION",
                    "Panel이 존재하지 않거나 아직 공개되지 않은 Fact를 사용했습니다.",
                    "06_SCENE/reaction_segments.json",
                    {**reaction_context, "fact_ids": unavailable_facts},
                )
            )
        before = segment.get("hypothesis_before")
        after = segment.get("hypothesis_after")
        if function in {"HYPOTHESIS_GENERATION", "HYPOTHESIS_REVISION"} and (
            not isinstance(before, str)
            or not before.strip()
            or not isinstance(after, str)
            or not after.strip()
            or before.strip() == after.strip()
        ):
            issues.append(
                make_presentation_issue(
                    "REACTION_HYPOTHESIS_DELTA_MISSING",
                    "가설 Function은 발화 전후 가설을 실제로 변경해야 합니다.",
                    "06_SCENE/reaction_segments.json",
                    reaction_context,
                )
            )
        spoken_line = segment.get("spoken_line")
        if isinstance(spoken_line, str) and (
            "[리액션]" in spoken_line
            or re.search(r"(고개를|표정|몸짓|침묵|눈빛)", spoken_line) is not None
        ):
            issues.append(
                make_presentation_issue(
                    "CHARACTER_REACTION_MISLABELED_AS_PANEL",
                    "극중 인물의 행동·표정을 Panel Reaction으로 계산할 수 없습니다.",
                    "06_SCENE/reaction_segments.json",
                    reaction_context,
                )
            )
    return issues


def validate_presentation_timeline(
    presentation_plan: Mapping[str, object],
    reaction_segments_document: Mapping[str, object],
    scene_cards: Mapping[str, object],
    channel: Mapping[str, object],
    production_config: Mapping[str, object],
) -> list[ValidationIssue]:
    """Presentation Segment 순서, 시간, 연결, Runtime과 비율을 검증한다."""
    segments = presentation_segments(presentation_plan)
    reactions = mapping_items(reaction_segments_document, "reaction_segments")
    issues: list[ValidationIssue] = []
    if panel_required(channel) and not reactions:
        issues.append(
            make_presentation_issue(
                "PANEL_REACTION_SEGMENT_MISSING",
                "Channel이 Panel Reaction을 요구하지만 실제 Segment가 없습니다.",
                "06_SCENE/reaction_segments.json",
                {},
            )
        )
    reaction_ids = {
        cast(str, reaction.get("reaction_segment_id"))
        for reaction in reactions
        if isinstance(reaction.get("reaction_segment_id"), str)
    }
    reactions_by_id = {
        cast(str, reaction.get("reaction_segment_id")): reaction
        for reaction in reactions
        if isinstance(reaction.get("reaction_segment_id"), str)
    }
    linked_reaction_ids = [
        cast(str, segment.get("reaction_segment_id"))
        for segment in segments
        if canonical_mode(segment.get("segment_type")) == "PANEL_REACTION"
        and isinstance(segment.get("reaction_segment_id"), str)
    ]
    if panel_required(channel) and not linked_reaction_ids:
        issues.append(
            make_presentation_issue(
                "PANEL_REACTION_SEGMENT_MISSING",
                "Presentation Timeline에 Panel Reaction Segment가 없습니다.",
                "06_SCENE/presentation_plan.json",
                {},
            )
        )
    missing_links = sorted(reaction_ids - set(linked_reaction_ids))
    unknown_links = sorted(set(linked_reaction_ids) - reaction_ids)
    duplicated_links = sorted(
        reaction_id
        for reaction_id in set(linked_reaction_ids)
        if linked_reaction_ids.count(reaction_id) > 1
    )
    if missing_links or unknown_links or duplicated_links:
        issues.append(
            make_presentation_issue(
                "PANEL_REACTION_SEGMENT_MISSING",
                "Reaction Segment와 Presentation Timeline 연결이 일대일이 아닙니다.",
                "06_SCENE/presentation_plan.json",
                {
                    "missing_reaction_ids": missing_links,
                    "unknown_reaction_ids": unknown_links,
                    "duplicated_reaction_ids": duplicated_links,
                },
            )
        )
    reaction_orders = [
        cast(int, reaction.get("order"))
        for reaction in reactions
        if isinstance(reaction.get("order"), int)
        and not isinstance(reaction.get("order"), bool)
    ]
    expected_reaction_orders = list(range(1, len(reactions) + 1))
    if sorted(reaction_orders) != expected_reaction_orders:
        issues.append(
            make_presentation_issue(
                "PRESENTATION_SEGMENT_ORDER_MISMATCH",
                "Reaction Segment order가 1부터 연속적이지 않습니다.",
                "06_SCENE/reaction_segments.json",
                {
                    "expected_orders": expected_reaction_orders,
                    "actual_orders": reaction_orders,
                },
            )
        )
    scene_ids = set(scene_order_map(scene_cards))
    unknown_scenes = sorted(
        scene_id
        for segment in segments
        if isinstance((scene_id := segment.get("scene_id")), str) and scene_id not in scene_ids
    )
    if unknown_scenes:
        issues.append(
            make_presentation_issue(
                "PRESENTATION_SEGMENT_ORDER_MISMATCH",
                "Presentation Segment가 존재하지 않는 Scene을 참조합니다.",
                "06_SCENE/presentation_plan.json",
                {"scene_ids": unknown_scenes},
            )
        )
    expected_start = 0.0
    ordered_ids: list[str] = []
    timeline_mismatches: list[dict[str, object]] = []
    for segment in segments:
        segment_id = segment.get("segment_id")
        start = segment.get("start_sec")
        duration = segment.get("duration_sec")
        if isinstance(segment_id, str):
            ordered_ids.append(segment_id)
        if (
            not isinstance(start, int | float)
            or isinstance(start, bool)
            or not isinstance(duration, int | float)
            or isinstance(duration, bool)
            or duration <= 0
        ):
            continue
        if abs(float(start) - expected_start) > 0.001:
            timeline_mismatches.append(
                {"segment_id": segment_id, "expected_start_sec": expected_start, "actual": start}
            )
        expected_start = float(start) + float(duration)
        reaction_id = segment.get("reaction_segment_id")
        if not isinstance(reaction_id, str):
            continue
        reaction = reactions_by_id.get(reaction_id)
        if reaction is None:
            continue
        reaction_start = reaction.get("start_sec")
        reaction_duration = reaction.get("duration_sec")
        if (
            not isinstance(reaction_start, int | float)
            or isinstance(reaction_start, bool)
            or not isinstance(reaction_duration, int | float)
            or isinstance(reaction_duration, bool)
            or abs(float(start) - float(reaction_start)) > 0.001
            or abs(float(duration) - float(reaction_duration)) > 0.001
        ):
            timeline_mismatches.append(
                {
                    "segment_id": segment_id,
                    "reaction_segment_id": reaction_id,
                    "reason": "REACTION_TIME",
                }
            )
        if segment.get("scene_id") != reaction.get("after_scene_id"):
            timeline_mismatches.append(
                {
                    "segment_id": segment_id,
                    "reaction_segment_id": reaction_id,
                    "reason": "REACTION_SCENE",
                }
            )
    if len(set(ordered_ids)) != len(ordered_ids) or timeline_mismatches:
        issues.append(
            make_presentation_issue(
                "PRESENTATION_SEGMENT_ORDER_MISMATCH",
                "Presentation Segment ID 또는 시간순서가 연속적이지 않습니다.",
                "06_SCENE/presentation_plan.json",
                {"timeline_mismatches": timeline_mismatches},
            )
        )
    target_minutes = production_config.get("target_runtime_minutes")
    tolerance_ratio = production_config.get("runtime_tolerance_ratio")
    if (
        isinstance(target_minutes, int | float)
        and not isinstance(target_minutes, bool)
        and isinstance(tolerance_ratio, int | float)
        and not isinstance(tolerance_ratio, bool)
        and segments
    ):
        target_seconds = float(target_minutes) * 60.0
        tolerance = target_seconds * float(tolerance_ratio)
        if abs(expected_start - target_seconds) > tolerance:
            issues.append(
                make_presentation_issue(
                    "PRESENTATION_DURATION_MISMATCH",
                    "Presentation Timeline이 목표 Runtime 허용 범위를 벗어났습니다.",
                    "06_SCENE/presentation_plan.json",
                    {
                        "actual_seconds": expected_start,
                        "target_seconds": target_seconds,
                        "tolerance_seconds": tolerance,
                    },
                )
            )
    ratio = actual_panel_reaction_ratio(presentation_plan)
    ratio_range = channel_ratio_range(channel)
    if panel_required(channel) and ratio is None:
        issues.append(
            make_presentation_issue(
                "PANEL_REACTION_RATIO_OUT_OF_RANGE",
                "실제 Segment Duration에서 Panel Reaction 비율을 계산할 수 없습니다.",
                "06_SCENE/presentation_plan.json",
                {},
            )
        )
    elif ratio is not None and ratio_range is not None:
        minimum, maximum = ratio_range
        if not minimum <= ratio <= maximum:
            issues.append(
                make_presentation_issue(
                    "PANEL_REACTION_RATIO_OUT_OF_RANGE",
                    "실제 Panel Reaction 비율이 Channel 허용 범위를 벗어났습니다.",
                    "06_SCENE/presentation_plan.json",
                    {"actual_ratio": ratio, "minimum": minimum, "maximum": maximum},
                )
            )
    return issues


def validate_presentation_design(
    panel_cast: Mapping[str, object],
    reaction_segments_document: Mapping[str, object],
    presentation_plan: Mapping[str, object],
    scene_cards: Mapping[str, object],
    viewer_timeline: Mapping[str, object],
    facts: Mapping[str, object],
    clue_matrix: Mapping[str, object],
    channel: Mapping[str, object],
    production_config: Mapping[str, object],
) -> list[ValidationIssue]:
    """GATE-07 Presentation Contract 전체를 검증한다."""
    reactions = mapping_items(reaction_segments_document, "reaction_segments")
    return [
        *validate_panel_cast(panel_cast),
        *reaction_function_issues(reactions),
        *reaction_reference_issues(
            reactions,
            panel_cast,
            scene_cards,
            viewer_timeline,
            facts,
            clue_matrix,
        ),
        *validate_presentation_timeline(
            presentation_plan,
            reaction_segments_document,
            scene_cards,
            channel,
            production_config,
        ),
    ]


def parse_script_segments(content: str) -> tuple[list[ScriptSegment], bool]:
    """Broadcast Marker와 본문을 순서대로 파싱한다."""
    segments: list[ScriptSegment] = []
    malformed = False
    for marker in SEGMENT_MARKER.finditer(content):
        segment_id = marker.group("segment_id")
        end_marker = f"<!-- END_SEGMENT:{segment_id} -->"
        end_position = content.find(end_marker, marker.end())
        if end_position < 0:
            malformed = True
            continue
        next_marker = SEGMENT_MARKER.search(content, marker.end())
        if next_marker is not None and next_marker.start() < end_position:
            malformed = True
            continue
        segments.append(
            ScriptSegment(
                segment_id=segment_id,
                segment_type=marker.group("segment_type"),
                scene_id=marker.group("scene_id"),
                duration_sec=float(marker.group("duration")),
                body=content[marker.end() : end_position].strip(),
            )
        )
    if content.count("<!-- END_SEGMENT:") != len(segments):
        malformed = True
    return segments, malformed


def script_has_complete_segment_markers(content: str) -> bool:
    """Script가 최소 한 개의 완전한 Segment Marker를 갖는지 확인한다."""
    segments, malformed = parse_script_segments(content)
    return bool(segments) and not malformed


def plan_segment_map(
    presentation_plan: Mapping[str, object],
) -> dict[str, Mapping[str, object]]:
    """Presentation Segment를 ID로 색인한다."""
    return {
        cast(str, segment.get("segment_id")): segment
        for segment in presentation_segments(presentation_plan)
        if isinstance(segment.get("segment_id"), str)
    }


def script_segment_alignment_issues(
    presentation_plan: Mapping[str, object],
    final_script: str,
) -> list[ValidationIssue]:
    """Final Script Marker의 완전성, 중복, 순서와 시간을 검사한다."""
    planned = presentation_segments(presentation_plan)
    parsed, malformed = parse_script_segments(final_script)
    planned_ids = [
        cast(str, segment.get("segment_id"))
        for segment in planned
        if isinstance(segment.get("segment_id"), str)
    ]
    parsed_ids = [segment["segment_id"] for segment in parsed]
    issues: list[ValidationIssue] = []
    if malformed or not parsed:
        issues.append(
            make_presentation_issue(
                "FINAL_SCRIPT_NOT_BROADCAST_MASTER",
                "Final Script가 완전한 Broadcast Segment Marker를 갖지 않습니다.",
                "07_SCRIPT/final_script.md",
                {"parsed_segment_count": len(parsed)},
            )
        )
    missing = sorted(set(planned_ids) - set(parsed_ids))
    if missing:
        issues.append(
            make_presentation_issue(
                "PRESENTATION_SEGMENT_MISSING_IN_FINAL_SCRIPT",
                "Presentation Plan Segment가 Final Script에 없습니다.",
                "07_SCRIPT/final_script.md",
                {"segment_ids": missing},
            )
        )
    duplicated = sorted(
        segment_id for segment_id in set(parsed_ids) if parsed_ids.count(segment_id) > 1
    )
    if duplicated:
        issues.append(
            make_presentation_issue(
                "PRESENTATION_SEGMENT_DUPLICATED",
                "Final Script에 Segment가 중복되었습니다.",
                "07_SCRIPT/final_script.md",
                {"segment_ids": duplicated},
            )
        )
    if parsed_ids != planned_ids:
        issues.append(
            make_presentation_issue(
                "PRESENTATION_SEGMENT_ORDER_MISMATCH",
                "Final Script Segment 순서가 Presentation Plan과 다릅니다.",
                "07_SCRIPT/final_script.md",
                {"expected": planned_ids, "actual": parsed_ids},
            )
        )
    planned_by_id = plan_segment_map(presentation_plan)
    duration_mismatches: list[dict[str, object]] = []
    for segment in parsed:
        plan_segment = planned_by_id.get(segment["segment_id"])
        if plan_segment is None:
            continue
        expected_duration = plan_segment.get("duration_sec")
        expected_type = canonical_mode(plan_segment.get("segment_type"))
        actual_type = canonical_mode(segment["segment_type"])
        if (
            not isinstance(expected_duration, int | float)
            or isinstance(expected_duration, bool)
            or abs(segment["duration_sec"] - float(expected_duration)) > 0.001
            or expected_type != actual_type
            or segment["scene_id"] != plan_segment.get("scene_id")
        ):
            duration_mismatches.append(
                {
                    "segment_id": segment["segment_id"],
                    "expected_duration": expected_duration,
                    "actual_duration": segment["duration_sec"],
                }
            )
    if duration_mismatches:
        issues.append(
            make_presentation_issue(
                "PRESENTATION_DURATION_MISMATCH",
                "Final Script Marker가 Presentation Plan의 유형·Scene·시간과 다릅니다.",
                "07_SCRIPT/final_script.md",
                {"segments": duration_mismatches},
            )
        )
    return issues


def layer_alignment_issues(
    presentation_plan: Mapping[str, object],
    layer_scripts: Mapping[str, str],
    final_script: str,
) -> list[ValidationIssue]:
    """세 Layer Script와 Final Script 본문이 정확히 대응하는지 검사한다."""
    parsed_final, _ = parse_script_segments(final_script)
    final_by_id = {segment["segment_id"]: segment for segment in parsed_final}
    parsed_layer_results = {
        artifact_name: parse_script_segments(content)
        for artifact_name, content in layer_scripts.items()
    }
    parsed_layers = {
        artifact_name: result[0]
        for artifact_name, result in parsed_layer_results.items()
    }
    layer_by_id = {
        artifact_name: {segment["segment_id"]: segment for segment in segments}
        for artifact_name, segments in parsed_layers.items()
    }
    mismatches: list[dict[str, object]] = []
    expected_by_layer: dict[str, list[str]] = {
        artifact_name: [] for artifact_name in layer_scripts
    }
    for plan_segment in presentation_segments(presentation_plan):
        segment_id = plan_segment.get("segment_id")
        source = plan_segment.get("source_artifact")
        if not isinstance(segment_id, str) or not isinstance(source, str):
            continue
        if source in expected_by_layer:
            expected_by_layer[source].append(segment_id)
        source_segment = layer_by_id.get(source, {}).get(segment_id)
        final_segment = final_by_id.get(segment_id)
        if source_segment is None or final_segment is None:
            mismatches.append(
                {"segment_id": segment_id, "source_artifact": source, "reason": "MISSING"}
            )
            continue
        if source_segment["body"].strip() != final_segment["body"].strip():
            mismatches.append(
                {"segment_id": segment_id, "source_artifact": source, "reason": "CONTENT"}
            )
    for artifact_name, segments in parsed_layers.items():
        actual_ids = [segment["segment_id"] for segment in segments]
        expected_ids = expected_by_layer[artifact_name]
        malformed = parsed_layer_results[artifact_name][1]
        if actual_ids != expected_ids or len(set(actual_ids)) != len(actual_ids) or malformed:
            mismatches.append(
                {
                    "source_artifact": artifact_name,
                    "reason": "LAYER_STRUCTURE",
                    "expected": expected_ids,
                    "actual": actual_ids,
                    "malformed": malformed,
                }
            )
    if not mismatches:
        return []
    return [
        make_presentation_issue(
            "FINAL_SCRIPT_NOT_BROADCAST_MASTER",
            "Final Script가 Layer Script의 Segment 본문과 일치하지 않습니다.",
            "07_SCRIPT/final_script.md",
            {"segments": mismatches},
        )
    ]


def panel_script_issues(
    reaction_segments_document: Mapping[str, object],
    panel_reaction_script: str,
) -> list[ValidationIssue]:
    """Panel Script Header가 Reaction Contract와 일치하는지 검사한다."""
    parsed_segments, malformed = parse_script_segments(panel_reaction_script)
    headers = {
        match.group("reaction_id"): {
            "panelist_id": match.group("panelist_id"),
            "function": match.group("function"),
        }
        for match in PANEL_HEADER.finditer(panel_reaction_script)
    }
    bodies_by_reaction_id = {
        match.group("reaction_id"): segment["body"]
        for segment in parsed_segments
        for match in PANEL_HEADER.finditer(segment["body"])
    }
    issues: list[ValidationIssue] = []
    if malformed or not parsed_segments:
        issues.append(
            make_presentation_issue(
                "PANEL_REACTION_SEGMENT_MISSING",
                "Panel Reaction Script에 완전한 Segment가 없습니다.",
                "07_SCRIPT/panel_reaction_script.md",
                {},
            )
        )
    mismatches: list[str] = []
    for reaction in mapping_items(reaction_segments_document, "reaction_segments"):
        reaction_id = reaction.get("reaction_segment_id")
        if not isinstance(reaction_id, str):
            continue
        header = headers.get(reaction_id)
        if (
            header is None
            or header["panelist_id"] != reaction.get("panelist_id")
            or header["function"] != reaction.get("function")
            or not isinstance(reaction.get("spoken_line"), str)
            or cast(str, reaction.get("spoken_line")).strip()
            not in bodies_by_reaction_id.get(reaction_id, "")
        ):
            mismatches.append(reaction_id)
    if mismatches:
        issues.append(
            make_presentation_issue(
                "PANEL_SPEAKER_INVALID",
                "Panel Script Header가 Reaction Segment의 화자·기능과 다릅니다.",
                "07_SCRIPT/panel_reaction_script.md",
                {"reaction_segment_ids": sorted(mismatches)},
            )
        )
    return issues


def substantive_lines(content: str) -> set[str]:
    """중복 검사에 사용할 의미 있는 일반 본문 줄을 반환한다."""
    result: set[str] = set()
    for raw_line in content.splitlines():
        line = raw_line.strip()
        if (
            len(line) < 10
            or line.startswith("<!--")
            or line.startswith("#")
            or PANEL_HEADER.fullmatch(line) is not None
        ):
            continue
        result.add(re.sub(r"\s+", " ", line))
    return result


def narration_duplication_issues(
    drama_script: str,
    narration_script: str,
    panel_reaction_script: str,
) -> list[ValidationIssue]:
    """Narration이 화면 행동 또는 Panel 발화를 그대로 반복하는지 검사한다."""
    narration_lines = substantive_lines(narration_script)
    visible_duplicates = sorted(narration_lines.intersection(substantive_lines(drama_script)))
    reaction_duplicates = sorted(
        narration_lines.intersection(substantive_lines(panel_reaction_script))
    )
    issues: list[ValidationIssue] = []
    if visible_duplicates:
        issues.append(
            make_presentation_issue(
                "NARRATION_VISIBLE_ACTION_DUPLICATION",
                "Narration이 Drama에서 이미 보이는 행동을 그대로 반복합니다.",
                "07_SCRIPT/narration_script.md",
                {"lines": visible_duplicates},
            )
        )
    if reaction_duplicates:
        issues.append(
            make_presentation_issue(
                "NARRATION_REACTION_DUPLICATION",
                "Narration이 Panel Reaction 발화를 그대로 반복합니다.",
                "07_SCRIPT/narration_script.md",
                {"lines": reaction_duplicates},
            )
        )
    return issues


def segment_fact_ids(segment: ScriptSegment, plan_segment: Mapping[str, object]) -> set[str]:
    """Plan 선언과 Script Tag에서 Segment 공개 Fact ID를 결합한다."""
    return set(string_items(plan_segment, "revealed_fact_ids")) | set(
        FACT_TAG.findall(segment["body"])
    )


def audience_belief_alignment_issues(
    presentation_plan: Mapping[str, object],
    final_script: str,
    scene_cards: Mapping[str, object],
    viewer_timeline: Mapping[str, object],
    audience_belief: Mapping[str, object],
) -> list[ValidationIssue]:
    """Script Fact 공개를 Viewer Timeline과 Audience Belief에 맞춰 검사한다."""
    orders = scene_order_map(scene_cards)
    reveal_orders = viewer_fact_reveal_orders(viewer_timeline, orders)
    belief_facts_by_order: dict[int, set[str]] = {}
    belief_mismatches: list[dict[str, object]] = []
    for belief_state in mapping_items(audience_belief, "belief_states"):
        scene_id = belief_state.get("scene_id")
        scene_order = belief_state.get("scene_order")
        resolved_order = (
            orders.get(scene_id)
            if isinstance(scene_id, str)
            else scene_order
            if isinstance(scene_order, int) and not isinstance(scene_order, bool)
            else None
        )
        if not isinstance(resolved_order, int):
            continue
        known_facts = set(string_items(belief_state, "known_fact_ids"))
        unavailable = sorted(
            fact_id
            for fact_id in known_facts
            if fact_id not in reveal_orders or reveal_orders[fact_id] > resolved_order
        )
        if unavailable:
            belief_mismatches.append(
                {
                    "scene_order": resolved_order,
                    "unavailable_fact_ids": unavailable,
                }
            )
        belief_facts_by_order[resolved_order] = known_facts
    planned_by_id = plan_segment_map(presentation_plan)
    parsed, _ = parse_script_segments(final_script)
    premature: list[dict[str, object]] = []
    for segment in parsed:
        plan_segment = planned_by_id.get(segment["segment_id"])
        if plan_segment is None:
            continue
        current_order = orders.get(segment["scene_id"])
        available_belief_orders = sorted(
            order
            for order in belief_facts_by_order
            if isinstance(current_order, int) and order <= current_order
        )
        current_belief_facts = (
            belief_facts_by_order[available_belief_orders[-1]]
            if available_belief_orders
            else set()
        )
        for fact_id in sorted(segment_fact_ids(segment, plan_segment)):
            reveal_order = reveal_orders.get(fact_id)
            if (
                reveal_order is None
                or current_order is None
                or current_order < reveal_order
                or fact_id not in current_belief_facts
            ):
                premature.append(
                    {
                        "segment_id": segment["segment_id"],
                        "fact_id": fact_id,
                        "script_scene_order": current_order,
                        "viewer_reveal_order": reveal_order,
                    }
                )
    if not premature and not belief_mismatches:
        return []
    return [
        make_presentation_issue(
            "AUDIENCE_BELIEF_SCRIPT_MISMATCH",
            "Script가 Viewer Timeline보다 먼저 Fact를 공개합니다.",
            "07_SCRIPT/final_script.md",
            {
                "premature_facts": premature,
                "belief_state_mismatches": belief_mismatches,
            },
        )
    ]


def clock_mentions(content: str) -> list[ClockMention]:
    """한국어와 콜론 형식의 절대시간을 중복 없이 추출한다."""
    matches: list[tuple[int, int, int]] = []
    for pattern in (KOREAN_MERIDIEM_TIME, KOREAN_TIME, COLON_TIME):
        for match in pattern.finditer(content):
            hour = int(match.group("hour"))
            minute = int(match.group("minute"))
            meridiem = match.groupdict().get("meridiem")
            if meridiem == "오후" and hour != 12:
                hour += 12
            if meridiem == "오전" and hour == 12:
                hour = 0
            matches.append((match.start(), match.end(), hour * 60 + minute))
    matches.sort(key=lambda item: item[0])
    accepted: list[ClockMention] = []
    last_end = -1
    for start, end, minute_of_day in matches:
        if start < last_end:
            continue
        accepted.append(
            ClockMention(
                minute_of_day=minute_of_day,
                context=content[max(0, start - 28) : min(len(content), end + 28)],
                position=start,
            )
        )
        last_end = end
    return accepted


def retrospective_time(mention: ClockMention) -> bool:
    """과거 기록을 인용하는 절대시간인지 주변 문맥으로 판정한다."""
    time_offset = min(28, mention["position"])
    prefix = mention["context"][:time_offset]
    return any(hint in prefix[-18:] for hint in RETROSPECTIVE_HINTS)


def timeline_baseline_minutes(actual_timeline: Mapping[str, object]) -> int | None:
    """Actual Timeline의 설명 시각과 상대 분에서 기준 절대시각을 계산한다."""
    baselines: list[int] = []
    for event in mapping_items(actual_timeline, "events"):
        description = event.get("description")
        start_minute = event.get("start_minute")
        if (
            not isinstance(description, str)
            or not isinstance(start_minute, int | float)
            or isinstance(start_minute, bool)
        ):
            continue
        mentions = clock_mentions(description)
        if mentions:
            baselines.append(mentions[0]["minute_of_day"] - round(float(start_minute)))
    return min(baselines) if baselines else None


def rescue_timeline_minute(actual_timeline: Mapping[str, object]) -> float | None:
    """Actual Timeline에서 구조 완료 사건의 상대 분을 찾는다."""
    for event in mapping_items(actual_timeline, "events"):
        description = event.get("description")
        start_minute = event.get("start_minute")
        if (
            isinstance(description, str)
            and "구조 완료" in description
            and isinstance(start_minute, int | float)
            and not isinstance(start_minute, bool)
        ):
            return float(start_minute)
    completion_pattern = re.compile(
        r"구조(?:한다|했다|된다|됐다|되었다|되었다고|함(?:\.|$))"
    )
    for event in mapping_items(actual_timeline, "events"):
        description = event.get("description")
        start_minute = event.get("start_minute")
        end_minute = event.get("end_minute")
        if not isinstance(description, str) or completion_pattern.search(description) is None:
            continue
        if isinstance(end_minute, int | float) and not isinstance(end_minute, bool):
            return float(end_minute)
        if isinstance(start_minute, int | float) and not isinstance(start_minute, bool):
            return float(start_minute)
    return None


def absolute_time_issues(
    final_script: str,
    actual_timeline: Mapping[str, object],
) -> list[ValidationIssue]:
    """Script 절대시간의 진행 순서와 구조 사건 정합성을 검사한다."""
    mentions = clock_mentions(final_script)
    chronological = [mention for mention in mentions if not retrospective_time(mention)]
    regressions = [
        {
            "previous_minute": previous["minute_of_day"],
            "actual_minute": current["minute_of_day"],
            "context": current["context"],
        }
        for previous, current in pairwise(chronological)
        if current["minute_of_day"] < previous["minute_of_day"]
    ]
    issues: list[ValidationIssue] = []
    if regressions:
        issues.append(
            make_presentation_issue(
                "ABSOLUTE_TIME_MONOTONICITY_ERROR",
                "Final Script의 현재 사건 절대시간이 역행합니다.",
                "07_SCRIPT/final_script.md",
                {"regressions": regressions},
            )
        )
    baseline = timeline_baseline_minutes(actual_timeline)
    rescue_minute = rescue_timeline_minute(actual_timeline)
    script_rescue_mentions = [
        mention
        for mention in mentions
        if "구조" in mention["context"] and "완료" in mention["context"]
    ]
    if baseline is not None and rescue_minute is not None and script_rescue_mentions:
        expected = (baseline + round(rescue_minute)) % (24 * 60)
        mismatches = [
            mention
            for mention in script_rescue_mentions
            if abs(mention["minute_of_day"] - expected) > 2
        ]
        if mismatches:
            issues.append(
                make_presentation_issue(
                    "SCRIPT_TIMELINE_ALIGNMENT_ERROR",
                    "Script의 구조 완료 시각이 Actual Timeline과 일치하지 않습니다.",
                    "07_SCRIPT/final_script.md",
                    {
                        "expected_minute_of_day": expected,
                        "actual_minutes": [item["minute_of_day"] for item in mismatches],
                    },
                )
            )
    return issues


def validate_script_integrity_v2(
    presentation_plan: Mapping[str, object],
    reaction_segments_document: Mapping[str, object],
    scene_cards: Mapping[str, object],
    viewer_timeline: Mapping[str, object],
    audience_belief: Mapping[str, object],
    actual_timeline: Mapping[str, object],
    drama_script: str,
    narration_script: str,
    panel_reaction_script: str,
    draft_script: str,
    final_script: str,
) -> list[ValidationIssue]:
    """Layer Script와 Broadcast Master의 구조·정보·시간 정합성을 검증한다."""
    issues: list[ValidationIssue] = []
    empty_layers = sorted(
        name
        for name, content in {
            "drama_script": drama_script,
            "narration_script": narration_script,
            "panel_reaction_script": panel_reaction_script,
        }.items()
        if not content.strip()
    )
    if empty_layers:
        issues.append(
            make_presentation_issue(
                "FINAL_SCRIPT_NOT_BROADCAST_MASTER",
                "Broadcast Master에 필요한 Layer Script가 비어 있습니다.",
                "07_SCRIPT/final_script.md",
                {"empty_layers": empty_layers},
            )
        )
    if not draft_script.strip():
        issues.append(
            make_presentation_issue(
                "FINAL_SCRIPT_NOT_BROADCAST_MASTER",
                "통합 Draft Script가 비어 있습니다.",
                "07_SCRIPT/draft_v01.md",
                {},
            )
        )
    issues.extend(script_segment_alignment_issues(presentation_plan, final_script))
    issues.extend(
        layer_alignment_issues(
            presentation_plan,
            {
                "drama_script": drama_script,
                "narration_script": narration_script,
                "panel_reaction_script": panel_reaction_script,
            },
            final_script,
        )
    )
    issues.extend(panel_script_issues(reaction_segments_document, panel_reaction_script))
    issues.extend(
        narration_duplication_issues(
            drama_script,
            narration_script,
            panel_reaction_script,
        )
    )
    issues.extend(
        audience_belief_alignment_issues(
            presentation_plan,
            final_script,
            scene_cards,
            viewer_timeline,
            audience_belief,
        )
    )
    issues.extend(absolute_time_issues(final_script, actual_timeline))
    return issues


def validate_production_presentation(
    presentation_plan: Mapping[str, object],
    reaction_segments_document: Mapping[str, object],
    production_panel_script: str,
    edit_script: str,
) -> list[ValidationIssue]:
    """Production Cue와 Edit Script가 Presentation ID를 보존하는지 검사한다."""
    issues: list[ValidationIssue] = []
    if not production_panel_script.strip():
        issues.append(
            make_presentation_issue(
                "PANEL_REACTION_SEGMENT_MISSING",
                "Production Panel Reaction Cue가 비어 있습니다.",
                "09_PRODUCTION/panel_reaction_script.md",
                {},
            )
        )
    reaction_ids = [
        cast(str, item.get("reaction_segment_id"))
        for item in mapping_items(reaction_segments_document, "reaction_segments")
        if isinstance(item.get("reaction_segment_id"), str)
    ]
    missing_reaction_cues = sorted(
        reaction_id for reaction_id in reaction_ids if reaction_id not in production_panel_script
    )
    segment_ids = [
        cast(str, item.get("segment_id"))
        for item in presentation_segments(presentation_plan)
        if isinstance(item.get("segment_id"), str)
    ]
    missing_edit_segments = sorted(
        segment_id for segment_id in segment_ids if segment_id not in edit_script
    )
    if missing_reaction_cues:
        issues.append(
            make_presentation_issue(
                "PANEL_REACTION_SEGMENT_MISSING",
                "Production Cue에서 Reaction Segment ID가 누락되었습니다.",
                "09_PRODUCTION/panel_reaction_script.md",
                {"reaction_segment_ids": missing_reaction_cues},
            )
        )
    if missing_edit_segments:
        issues.append(
            make_presentation_issue(
                "PRESENTATION_SEGMENT_MISSING_IN_FINAL_SCRIPT",
                "Edit Script에서 Presentation Segment ID가 누락되었습니다.",
                "09_PRODUCTION/edit_script.md",
                {"segment_ids": missing_edit_segments},
            )
        )
    return issues
