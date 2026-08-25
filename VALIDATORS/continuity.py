"""Timeline, Clue, Knowledge, Runtime 연속성 검증."""

from collections.abc import Mapping
from typing import TypedDict

from VALIDATORS.exceptions import ConfigurationError
from VALIDATORS.models import ValidationIssue


class TimelineEvent(TypedDict):
    """장소 충돌 계산에 필요한 정규화 Event."""

    event_id: str
    start: float
    end: float
    location_id: str
    participant_ids: list[str]


def make_continuity_issue(
    code: str,
    message: str,
    artifact: str,
    context: dict[str, object],
) -> ValidationIssue:
    """연속성 문제를 표준 형식으로 생성한다."""
    return ValidationIssue(
        severity="ERROR",
        code=code,
        message=message,
        artifact=artifact,
        context=context,
    )


def require_records(
    document: Mapping[str, object],
    key: str,
    source: str,
) -> list[Mapping[str, object]]:
    """객체 배열을 읽고 구조 오류를 명시적으로 거부한다."""
    value = document.get(key)
    if not isinstance(value, list) or not all(isinstance(item, Mapping) for item in value):
        raise ConfigurationError(f"객체 배열이 필요합니다: source={source}, field={key}")
    return list(value)


def require_string(
    record: Mapping[str, object],
    key: str,
    source: str,
) -> str:
    """필수 문자열 필드를 읽는다."""
    value = record.get(key)
    if not isinstance(value, str) or not value:
        raise ConfigurationError(f"문자열이 필요합니다: source={source}, field={key}")
    return value


def require_number(
    record: Mapping[str, object],
    key: str,
    source: str,
) -> float:
    """필수 숫자 필드를 읽는다."""
    value = record.get(key)
    if not isinstance(value, int | float) or isinstance(value, bool):
        raise ConfigurationError(f"숫자가 필요합니다: source={source}, field={key}")
    return float(value)


def require_string_array(
    record: Mapping[str, object],
    key: str,
    source: str,
) -> list[str]:
    """필수 문자열 배열 필드를 읽는다."""
    value = record.get(key)
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise ConfigurationError(
            f"문자열 배열이 필요합니다: source={source}, field={key}"
        )
    return list(value)


def time_ranges_overlap(
    first_start: float,
    first_end: float,
    second_start: float,
    second_end: float,
) -> bool:
    """두 반개구 시간 구간의 중첩 여부를 계산한다."""
    return first_start < second_end and second_start < first_end


def validate_timeline_locations(
    actual_timeline: Mapping[str, object],
) -> list[ValidationIssue]:
    """한 인물이 같은 시간에 서로 다른 장소에 있는 모순을 찾는다."""
    events = require_records(actual_timeline, "events", "actual_timeline")
    normalized_events: list[TimelineEvent] = []
    for event in events:
        event_id = require_string(event, "event_id", "actual_timeline.events")
        start = require_number(event, "start_minute", event_id)
        end = require_number(event, "end_minute", event_id)
        if end <= start:
            raise ConfigurationError(
                f"Event 종료 시각은 시작 시각보다 커야 합니다: event_id={event_id}"
            )
        normalized_events.append(
            {
                "event_id": event_id,
                "start": start,
                "end": end,
                "location_id": require_string(event, "location_id", event_id),
                "participant_ids": require_string_array(
                    event,
                    "participant_ids",
                    event_id,
                ),
            }
        )

    issues: list[ValidationIssue] = []
    for first_index, first in enumerate(normalized_events):
        for second in normalized_events[first_index + 1 :]:
            if first["location_id"] == second["location_id"]:
                continue
            if not time_ranges_overlap(
                first["start"],
                first["end"],
                second["start"],
                second["end"],
            ):
                continue
            first_participants = set(first["participant_ids"])
            second_participants = set(second["participant_ids"])
            conflicting = sorted(first_participants & second_participants)
            if conflicting:
                issues.append(
                    make_continuity_issue(
                        "SIMULTANEOUS_LOCATION_CONFLICT",
                        "한 인물이 겹치는 시간에 서로 다른 장소에 배치되었습니다.",
                        "03_TIMELINE/actual_timeline.json",
                        {
                            "event_ids": [first["event_id"], second["event_id"]],
                            "character_ids": conflicting,
                        },
                    )
                )
    return issues


def validate_clue_integrity(
    clue_matrix: Mapping[str, object],
) -> list[ValidationIssue]:
    """Core Clue와 Red Herring의 도입·회수 순서를 검사한다."""
    clues = require_records(clue_matrix, "clues", "clue_matrix")
    issues: list[ValidationIssue] = []
    core_count = 0
    for clue in clues:
        clue_id = require_string(clue, "clue_id", "clue_matrix.clues")
        role = require_string(clue, "role", clue_id)
        introduced = require_number(clue, "introduced_scene_order", clue_id)
        resolved_value = clue.get("resolved_scene_order")
        resolved = (
            float(resolved_value)
            if isinstance(resolved_value, int | float)
            and not isinstance(resolved_value, bool)
            else None
        )
        if role == "CORE":
            core_count += 1
        if resolved is not None and resolved < introduced:
            issues.append(
                make_continuity_issue(
                    "CLUE_RESOLVED_BEFORE_INTRODUCTION",
                    "단서가 도입되기 전에 해소되었습니다.",
                    "04_MYSTERY/clue_matrix.json",
                    {"clue_id": clue_id},
                )
            )
        if role in {"CORE", "RED_HERRING"} and resolved is None:
            code = "CORE_CLUE_UNRESOLVED" if role == "CORE" else "RED_HERRING_UNRESOLVED"
            issues.append(
                make_continuity_issue(
                    code,
                    "핵심 단서 또는 Red Herring의 회수 시점이 없습니다.",
                    "04_MYSTERY/clue_matrix.json",
                    {"clue_id": clue_id, "role": role},
                )
            )
    if core_count == 0:
        issues.append(
            make_continuity_issue(
                "CORE_CLUE_MISSING",
                "미스터리 해소를 지탱할 Core Clue가 없습니다.",
                "04_MYSTERY/clue_matrix.json",
                {},
            )
        )
    return issues


def knowledge_key(character_id: str, fact_id: str) -> tuple[str, str]:
    """인물과 사실의 지식 경계 키를 만든다."""
    return (character_id, fact_id)


def build_knowledge_boundaries(
    knowledge_matrix: Mapping[str, object],
) -> dict[tuple[str, str], float]:
    """각 인물이 사실을 처음 알게 되는 Scene 순서를 계산한다."""
    events = require_records(
        knowledge_matrix,
        "knowledge_events",
        "knowledge_matrix",
    )
    boundaries: dict[tuple[str, str], float] = {}
    for event in events:
        character_id = require_string(event, "character_id", "knowledge_events")
        fact_id = require_string(event, "fact_id", "knowledge_events")
        learned_order = require_number(event, "learned_scene_order", "knowledge_events")
        key = knowledge_key(character_id, fact_id)
        previous = boundaries.get(key)
        if previous is None or learned_order < previous:
            boundaries[key] = learned_order
    return boundaries


def validate_character_knowledge(
    knowledge_matrix: Mapping[str, object],
    scene_cards: Mapping[str, object],
) -> list[ValidationIssue]:
    """인물이 알기 전 사실을 말하거나 행동에 사용하는 오류를 찾는다."""
    boundaries = build_knowledge_boundaries(knowledge_matrix)
    scenes = require_records(scene_cards, "scenes", "scene_cards")
    issues: list[ValidationIssue] = []
    for scene in scenes:
        scene_id = require_string(scene, "scene_id", "scene_cards.scenes")
        scene_order = require_number(scene, "order", scene_id)
        claims = require_records(scene, "knowledge_claims", scene_id)
        for claim in claims:
            character_id = require_string(claim, "character_id", scene_id)
            fact_id = require_string(claim, "fact_id", scene_id)
            learned_order = boundaries.get(knowledge_key(character_id, fact_id))
            if learned_order is None:
                issues.append(
                    make_continuity_issue(
                        "UNDECLARED_CHARACTER_KNOWLEDGE",
                        "인물이 사용한 사실이 Knowledge Matrix에 선언되지 않았습니다.",
                        "06_SCENE/scene_cards.json",
                        {
                            "scene_id": scene_id,
                            "character_id": character_id,
                            "fact_id": fact_id,
                        },
                    )
                )
            elif scene_order < learned_order:
                issues.append(
                    make_continuity_issue(
                        "KNOWLEDGE_BOUNDARY_VIOLATION",
                        "인물이 해당 사실을 알기 전에 사용했습니다.",
                        "06_SCENE/scene_cards.json",
                        {
                            "scene_id": scene_id,
                            "character_id": character_id,
                            "fact_id": fact_id,
                            "learned_scene_order": learned_order,
                        },
                    )
                )
    return issues


def validate_runtime(
    production_config: Mapping[str, object],
    scene_cards: Mapping[str, object],
) -> list[ValidationIssue]:
    """Scene 예상 길이 합이 목표 Runtime 허용 범위 안인지 검사한다."""
    target_minutes = require_number(
        production_config,
        "target_runtime_minutes",
        "production_config",
    )
    tolerance_ratio = require_number(
        production_config,
        "runtime_tolerance_ratio",
        "production_config",
    )
    if target_minutes <= 0 or not 0 <= tolerance_ratio < 1:
        raise ConfigurationError(
            "Runtime 목표는 양수이고 허용 비율은 0 이상 1 미만이어야 합니다."
        )
    scenes = require_records(scene_cards, "scenes", "scene_cards")
    estimated_seconds = sum(
        require_number(scene, "estimated_seconds", "scene_cards.scenes")
        for scene in scenes
    )
    target_seconds = target_minutes * 60
    minimum = target_seconds * (1 - tolerance_ratio)
    maximum = target_seconds * (1 + tolerance_ratio)
    if minimum <= estimated_seconds <= maximum:
        return []
    return [
        make_continuity_issue(
            "RUNTIME_OUT_OF_TOLERANCE",
            "Scene 예상 길이 합이 목표 Runtime 허용 범위를 벗어났습니다.",
            "06_SCENE/scene_cards.json",
            {
                "estimated_seconds": estimated_seconds,
                "minimum_seconds": minimum,
                "maximum_seconds": maximum,
            },
        )
    ]


def unique_ids(
    document: Mapping[str, object],
    records_key: str,
    id_key: str,
    source: str,
) -> set[str]:
    """Artifact의 ID 중복을 거부하고 집합을 반환한다."""
    records = require_records(document, records_key, source)
    identifiers = [require_string(record, id_key, source) for record in records]
    if len(identifiers) != len(set(identifiers)):
        raise ConfigurationError(f"중복 ID가 있습니다: source={source}, field={id_key}")
    return set(identifiers)


def validate_cross_references(
    characters: Mapping[str, object],
    facts: Mapping[str, object],
    actual_timeline: Mapping[str, object],
    knowledge_matrix: Mapping[str, object],
    clue_matrix: Mapping[str, object],
    beat_sheet: Mapping[str, object],
    scene_cards: Mapping[str, object],
) -> list[ValidationIssue]:
    """Character, Fact, Clue, Beat, Scene 간 ID 참조 무결성을 검사한다."""
    character_ids = unique_ids(characters, "characters", "character_id", "characters")
    fact_ids = unique_ids(facts, "facts", "fact_id", "facts")
    clue_ids = unique_ids(clue_matrix, "clues", "clue_id", "clue_matrix")
    beat_ids = unique_ids(beat_sheet, "beats", "beat_id", "beat_sheet")
    scene_ids = unique_ids(scene_cards, "scenes", "scene_id", "scene_cards")
    issues: list[ValidationIssue] = []

    checks: list[tuple[str, str, str, str, set[str]]] = []
    for event in require_records(actual_timeline, "events", "actual_timeline"):
        event_id = require_string(event, "event_id", "actual_timeline.events")
        for character_id in require_string_array(event, "participant_ids", event_id):
            checks.append(
                (
                    event_id,
                    "character_id",
                    character_id,
                    "actual_timeline",
                    character_ids,
                )
            )
    for event in require_records(knowledge_matrix, "knowledge_events", "knowledge_matrix"):
        checks.append(
            (
                "knowledge_events",
                "character_id",
                require_string(event, "character_id", "knowledge_events"),
                "knowledge_matrix",
                character_ids,
            )
        )
        checks.append(
            (
                "knowledge_events",
                "fact_id",
                require_string(event, "fact_id", "knowledge_events"),
                "knowledge_matrix",
                fact_ids,
            )
        )
    for clue in require_records(clue_matrix, "clues", "clue_matrix"):
        clue_id = require_string(clue, "clue_id", "clue_matrix.clues")
        for field in ("introduced_scene_id", "resolved_scene_id"):
            referenced = clue.get(field)
            if isinstance(referenced, str):
                checks.append((clue_id, field, referenced, "clue_matrix", scene_ids))
    for scene in require_records(scene_cards, "scenes", "scene_cards"):
        scene_id = require_string(scene, "scene_id", "scene_cards.scenes")
        checks.append(
            (
                scene_id,
                "beat_id",
                require_string(scene, "beat_id", scene_id),
                "scene_cards",
                beat_ids,
            )
        )
        for clue_id in require_string_array(scene, "clue_ids", scene_id):
            checks.append((scene_id, "clue_id", clue_id, "scene_cards", clue_ids))

    for owner_id, field, referenced_id, source, valid_ids in checks:
        if referenced_id not in valid_ids:
            issues.append(
                make_continuity_issue(
                    "BROKEN_ARTIFACT_REFERENCE",
                    "Artifact가 존재하지 않는 ID를 참조합니다.",
                    source,
                    {
                        "owner_id": owner_id,
                        "field": field,
                        "referenced_id": referenced_id,
                    },
                )
            )
    return issues


def validate_continuity(
    production_config: Mapping[str, object],
    characters: Mapping[str, object],
    facts: Mapping[str, object],
    knowledge_matrix: Mapping[str, object],
    actual_timeline: Mapping[str, object],
    clue_matrix: Mapping[str, object],
    beat_sheet: Mapping[str, object],
    scene_cards: Mapping[str, object],
) -> dict[str, object]:
    """모든 연속성 검사를 하나의 Gate 보고서로 통합한다."""
    issues = [
        *validate_timeline_locations(actual_timeline),
        *validate_clue_integrity(clue_matrix),
        *validate_character_knowledge(knowledge_matrix, scene_cards),
        *validate_runtime(production_config, scene_cards),
        *validate_cross_references(
            characters,
            facts,
            actual_timeline,
            knowledge_matrix,
            clue_matrix,
            beat_sheet,
            scene_cards,
        ),
    ]
    return {
        "project_id": production_config.get("project_id", ""),
        "result": "FAIL" if issues else "PASS",
        "issues": issues,
    }
