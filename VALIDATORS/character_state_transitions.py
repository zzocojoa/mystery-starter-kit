"""명시적 범죄용 유연한 Character State Transition을 검증한다."""

from collections.abc import Mapping, Sequence

from VALIDATORS.models import ValidationIssue
from VALIDATORS.output_profiles import script_source_mode
from VALIDATORS.requirements import enabled_capability


def transition_policy_applies(
    production_config: Mapping[str, object],
    channel: Mapping[str, object],
) -> bool:
    """새 Script mode와 Explicit Crime Capability가 함께 활성인지 반환한다."""
    return (
        script_source_mode(production_config) == "SCREENPLAY_UNITS"
        and enabled_capability(channel, "EXPLICIT_CRIME_EVENT_POLICY")
    )


def transition_issue(
    code: str,
    message: str,
    context: Mapping[str, object],
) -> ValidationIssue:
    """Character State Transition 문제를 공통 형식으로 만든다."""
    return ValidationIssue(
        severity="ERROR",
        code=code,
        message=message,
        artifact="05_STORY/character_state_transitions.json",
        context=dict(context),
    )


def mapping_records(document: Mapping[str, object], field: str) -> list[Mapping[str, object]]:
    """객체 배열을 의미 검증용으로 반환한다."""
    value = document.get(field)
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        return []
    return [item for item in value if isinstance(item, Mapping)]


def identifier_set(
    document: Mapping[str, object],
    collection_field: str,
    identifier_field: str,
) -> set[str]:
    """Artifact 배열의 문자열 ID를 집합으로 만든다."""
    return {
        identifier
        for record in mapping_records(document, collection_field)
        if isinstance((identifier := record.get(identifier_field)), str)
    }


def trigger_ids(transition: Mapping[str, object], field: str) -> set[str]:
    """Transition trigger 배열의 문자열 ID를 반환한다."""
    triggers = transition.get("triggers")
    values = triggers.get(field) if isinstance(triggers, Mapping) else None
    if not isinstance(values, list):
        return set()
    return {value for value in values if isinstance(value, str)}


def transition_order_issues(
    transitions: Sequence[Mapping[str, object]],
) -> list[ValidationIssue]:
    """Transition ID와 order의 전역 결정성을 검증한다."""
    transition_ids = [record.get("transition_id") for record in transitions]
    orders = [record.get("order") for record in transitions]
    valid_ids = [value for value in transition_ids if isinstance(value, str)]
    valid_orders = [
        value
        for value in orders
        if isinstance(value, int) and not isinstance(value, bool)
    ]
    issues: list[ValidationIssue] = []
    if len(valid_ids) != len(transitions) or len(valid_ids) != len(set(valid_ids)):
        issues.append(
            transition_issue(
                "CHARACTER_STATE_TRANSITION_ID_INVALID",
                "transition_id는 문서 전체에서 고유해야 합니다.",
                {"transition_ids": valid_ids},
            )
        )
    expected_orders = list(range(1, len(transitions) + 1))
    if valid_orders != expected_orders:
        issues.append(
            transition_issue(
                "CHARACTER_STATE_TRANSITION_ORDER_INVALID",
                "Transition order는 배열과 일치하는 1부터의 연속 정수여야 합니다.",
                {"actual_order": valid_orders, "expected_order": expected_orders},
            )
        )
    return issues


def transition_reference_issues(
    transition: Mapping[str, object],
    valid_ids: Mapping[str, set[str]],
) -> list[ValidationIssue]:
    """인물, Scope와 Trigger가 실제 상위 Artifact를 참조하는지 검증한다."""
    transition_id = transition.get("transition_id")
    invalid: dict[str, list[str]] = {}
    character_id = transition.get("character_id")
    if not isinstance(character_id, str) or character_id not in valid_ids["character_ids"]:
        invalid["character_ids"] = [str(character_id)]
    scope_type = transition.get("scope_type")
    scope_id = transition.get("scope_id")
    scope_key = "beat_ids" if scope_type == "BEAT" else "scene_ids"
    if not isinstance(scope_id, str) or scope_id not in valid_ids[scope_key]:
        invalid[scope_key] = [str(scope_id)]
    trigger_fields = {
        "fact_ids": "fact_ids",
        "clue_ids": "clue_ids",
        "crime_event_ids": "crime_event_ids",
    }
    for trigger_field, valid_key in trigger_fields.items():
        unknown = sorted(trigger_ids(transition, trigger_field) - valid_ids[valid_key])
        if unknown:
            invalid[trigger_field] = unknown
    if not invalid:
        return []
    return [
        transition_issue(
            "CHARACTER_STATE_REFERENCE_INVALID",
            "Character State Transition이 존재하지 않는 인물·Scope·Trigger를 참조합니다.",
            {"transition_id": transition_id, "invalid_references": invalid},
        )
    ]


def state_delta_issues(
    transitions: Sequence[Mapping[str, object]],
) -> list[ValidationIssue]:
    """각 상태 변화와 동일 인물의 연속 상태를 검증한다."""
    issues: list[ValidationIssue] = []
    previous_state_by_character: dict[str, object] = {}
    for transition in transitions:
        transition_id = transition.get("transition_id")
        character_id = transition.get("character_id")
        before = transition.get("state_before")
        after = transition.get("state_after")
        if before == after:
            issues.append(
                transition_issue(
                    "CHARACTER_STATE_DELTA_MISSING",
                    "state_before와 state_after는 실제 변화를 나타내야 합니다.",
                    {"transition_id": transition_id},
                )
            )
        if isinstance(character_id, str):
            previous_after = previous_state_by_character.get(character_id)
            if previous_after is not None and previous_after != before:
                issues.append(
                    transition_issue(
                        "CHARACTER_STATE_CHAIN_BROKEN",
                        "동일 인물의 다음 state_before는 이전 state_after와 이어져야 합니다.",
                        {
                            "transition_id": transition_id,
                            "character_id": character_id,
                            "expected_state_before": previous_after,
                            "actual_state_before": before,
                        },
                    )
                )
            previous_state_by_character[character_id] = after
    return issues


def validate_character_state_transitions(
    production_config: Mapping[str, object],
    channel: Mapping[str, object],
    document: Mapping[str, object],
    characters: Mapping[str, object],
    facts: Mapping[str, object],
    clue_matrix: Mapping[str, object],
    crime_event_contract: Mapping[str, object],
    beat_sheet: Mapping[str, object],
    scene_cards: Mapping[str, object],
) -> list[ValidationIssue]:
    """적용 가능한 Project의 유연한 상태 변화와 상위 참조를 검증한다."""
    if not transition_policy_applies(production_config, channel):
        return []
    transitions = mapping_records(document, "transitions")
    event_id = crime_event_contract.get("event_id")
    valid_ids = {
        "character_ids": identifier_set(characters, "characters", "character_id"),
        "fact_ids": identifier_set(facts, "facts", "fact_id"),
        "clue_ids": identifier_set(clue_matrix, "clues", "clue_id"),
        "crime_event_ids": {event_id} if isinstance(event_id, str) else set(),
        "beat_ids": identifier_set(beat_sheet, "beats", "beat_id"),
        "scene_ids": identifier_set(scene_cards, "scenes", "scene_id"),
    }
    issues = [*transition_order_issues(transitions), *state_delta_issues(transitions)]
    for transition in transitions:
        issues.extend(transition_reference_issues(transition, valid_ids))
    return issues
