"""Screenplay Unit의 순서, 식별자와 장면 연결 의미를 검증한다."""

from collections.abc import Mapping, Sequence
from typing import cast

from VALIDATORS.models import ValidationIssue

SPEAKER_REQUIRED_TYPES = frozenset(
    {
        "DIALOGUE",
        "NARRATION",
        "INNER_MONOLOGUE",
        "HALLUCINATION",
        "MESSAGE",
        "CHAT",
        "NOTE",
        "RECORDING",
    }
)
SPEAKER_PROHIBITED_TYPES = frozenset({"ACTION", "SOUND", "SCREEN_TEXT"})


def screenplay_issue(
    code: str,
    message: str,
    context: Mapping[str, object],
) -> ValidationIssue:
    """Screenplay Unit 문제를 공통 형식으로 만든다."""
    return ValidationIssue(
        severity="ERROR",
        code=code,
        message=message,
        artifact="07_SCRIPT/screenplay_units.json",
        context=dict(context),
    )


def mapping_items(value: object) -> list[Mapping[str, object]]:
    """객체 배열만 의미 검증 대상으로 반환한다."""
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        return []
    return [cast(Mapping[str, object], item) for item in value if isinstance(item, Mapping)]


def duplicate_strings(values: Sequence[object]) -> list[str]:
    """중복 문자열을 최초 발견 순서대로 반환한다."""
    seen: set[str] = set()
    duplicated: list[str] = []
    for value in values:
        if not isinstance(value, str):
            continue
        if value in seen and value not in duplicated:
            duplicated.append(value)
        seen.add(value)
    return duplicated


def identifier_set(
    document: Mapping[str, object],
    collection_field: str,
    identifier_field: str,
) -> set[str]:
    """상위 Artifact 배열의 문자열 ID를 반환한다."""
    return {
        identifier
        for record in mapping_items(document.get(collection_field))
        if isinstance((identifier := record.get(identifier_field)), str)
    }


def reference_values(unit: Mapping[str, object], field: str) -> set[str]:
    """Unit references 객체의 문자열 ID 집합을 반환한다."""
    references = unit.get("references")
    raw_values = references.get(field) if isinstance(references, Mapping) else None
    if not isinstance(raw_values, list):
        return set()
    return {value for value in raw_values if isinstance(value, str)}


def string_values(document: Mapping[str, object], field: str) -> set[str]:
    """객체의 문자열 배열 필드를 집합으로 반환한다."""
    raw_values = document.get(field)
    if not isinstance(raw_values, list):
        return set()
    return {value for value in raw_values if isinstance(value, str)}


def contract_reference_sets(
    crime_event_contract: Mapping[str, object],
) -> dict[str, set[str]]:
    """현재 Crime Event Contract가 선언한 참조 ID 집합을 반환한다."""
    event_id = crime_event_contract.get("event_id")
    event_ids = {event_id} if isinstance(event_id, str) else set()
    harm_ids = string_values(crime_event_contract, "harm_ids")
    harm_ids.update(
        identifier_set(crime_event_contract, "harms", "harm_id")
    )
    return {
        "crime_event_ids": event_ids,
        "harm_ids": harm_ids,
        "development_function_ids": identifier_set(
            crime_event_contract,
            "development_functions",
            "development_function_id",
        ),
        "reveal_target_ids": identifier_set(
            crime_event_contract,
            "reveal_targets",
            "reveal_target_id",
        ),
    }


def validate_screenplay_unit_references(
    document: Mapping[str, object],
    facts: Mapping[str, object],
    clue_matrix: Mapping[str, object],
    crime_event_contract: Mapping[str, object],
    characters: Mapping[str, object],
    presentation_plan: Mapping[str, object],
) -> list[ValidationIssue]:
    """모든 Unit 참조를 현재 상위 Artifact와 Scene 소유권에 대해 검증한다."""
    valid_references = {
        "fact_ids": identifier_set(facts, "facts", "fact_id"),
        "clue_ids": identifier_set(clue_matrix, "clues", "clue_id"),
        **contract_reference_sets(crime_event_contract),
    }
    error_codes = {
        "fact_ids": "SCREENPLAY_FACT_REFERENCE_UNKNOWN",
        "clue_ids": "SCREENPLAY_CLUE_REFERENCE_UNKNOWN",
        "crime_event_ids": "SCREENPLAY_EVENT_REFERENCE_UNKNOWN",
        "harm_ids": "SCREENPLAY_HARM_REFERENCE_UNKNOWN",
        "development_function_ids": (
            "SCREENPLAY_DEVELOPMENT_FUNCTION_REFERENCE_UNKNOWN"
        ),
        "reveal_target_ids": "SCREENPLAY_REVEAL_TARGET_REFERENCE_UNKNOWN",
    }
    character_ids = identifier_set(characters, "characters", "character_id")
    segment_owners = {
        segment_id: segment.get("scene_id")
        for segment in mapping_items(presentation_plan.get("segments"))
        if isinstance((segment_id := segment.get("segment_id")), str)
    }
    contract_event_id = crime_event_contract.get("event_id")
    issues: list[ValidationIssue] = []
    for scene in mapping_items(document.get("scenes")):
        scene_id = scene.get("scene_id")
        local_segment_ids = string_values(scene, "segment_ids")
        for unit in mapping_items(scene.get("units")):
            unit_id = unit.get("unit_id")
            for field, valid_ids in valid_references.items():
                unknown_ids = sorted(reference_values(unit, field) - valid_ids)
                if unknown_ids:
                    issues.append(
                        screenplay_issue(
                            error_codes[field],
                            "Screenplay Unit이 현재 상위 Artifact에 없는 ID를 참조합니다.",
                            {
                                "scene_id": scene_id,
                                "unit_id": unit_id,
                                "reference_field": field,
                                "unknown_ids": unknown_ids,
                            },
                        )
                    )
            speaker_id = unit.get("speaker_id")
            if isinstance(speaker_id, str) and speaker_id not in character_ids:
                issues.append(
                    screenplay_issue(
                        "REENACTMENT_SPEAKER_UNKNOWN",
                        "Screenplay Unit speaker_id가 현재 Character에 없습니다.",
                        {
                            "scene_id": scene_id,
                            "unit_id": unit_id,
                            "speaker_id": speaker_id,
                        },
                    )
                )
            segment_id = unit.get("segment_id")
            presentation_scene_id = (
                segment_owners.get(segment_id)
                if isinstance(segment_id, str)
                else None
            )
            if (
                not isinstance(segment_id, str)
                or segment_id not in local_segment_ids
                or presentation_scene_id != scene_id
            ):
                issues.append(
                    screenplay_issue(
                        "SCREENPLAY_SEGMENT_REFERENCE_INVALID",
                        "Unit segment_id는 Presentation Plan의 동일 Scene Segment여야 합니다.",
                        {
                            "scene_id": scene_id,
                            "unit_id": unit_id,
                            "segment_id": segment_id,
                            "presentation_scene_id": presentation_scene_id,
                        },
                    )
                )
            harm_ids = reference_values(unit, "harm_ids")
            event_ids = reference_values(unit, "crime_event_ids")
            if (
                harm_ids
                and isinstance(contract_event_id, str)
                and contract_event_id not in event_ids
            ):
                issues.append(
                    screenplay_issue(
                        "SCREENPLAY_HARM_EVENT_BINDING_INVALID",
                        "Harm 참조 Unit은 같은 Crime Event 참조를 함께 가져야 합니다.",
                        {
                            "scene_id": scene_id,
                            "unit_id": unit_id,
                            "harm_ids": sorted(harm_ids),
                            "required_event_id": contract_event_id,
                        },
                    )
                )
    return issues


def integer_order_issues(
    values: Sequence[object],
    code: str,
    label: str,
    context: Mapping[str, object],
) -> list[ValidationIssue]:
    """배열 순서가 1부터 연속된 고유 정수인지 검증한다."""
    orders = [value for value in values if isinstance(value, int) and not isinstance(value, bool)]
    expected = list(range(1, len(values) + 1))
    if orders == expected:
        return []
    return [
        screenplay_issue(
            code,
            f"{label} order는 배열 순서와 일치하는 1부터의 연속 정수여야 합니다.",
            {**context, "actual_order": orders, "expected_order": expected},
        )
    ]


def validate_unit_speakers(
    scene_id: object,
    units: Sequence[Mapping[str, object]],
) -> list[ValidationIssue]:
    """Unit 유형별 speaker_id 허용 규칙을 검증한다."""
    issues: list[ValidationIssue] = []
    for unit in units:
        unit_type = unit.get("type")
        speaker_id = unit.get("speaker_id")
        context = {"scene_id": scene_id, "unit_id": unit.get("unit_id"), "type": unit_type}
        if unit_type in SPEAKER_REQUIRED_TYPES and not isinstance(speaker_id, str):
            issues.append(
                screenplay_issue(
                    "SCREENPLAY_SPEAKER_REQUIRED",
                    "발화 또는 인물 작성 Unit에는 speaker_id가 필요합니다.",
                    context,
                )
            )
        if unit_type in SPEAKER_PROHIBITED_TYPES and speaker_id is not None:
            issues.append(
                screenplay_issue(
                    "SCREENPLAY_SPEAKER_PROHIBITED",
                    "지문·음향·화면 문구 Unit에는 speaker_id를 둘 수 없습니다.",
                    context,
                )
            )
    return issues


def validate_scene_units(
    scene: Mapping[str, object],
    global_unit_ids: set[str],
) -> list[ValidationIssue]:
    """한 장면의 Unit, Segment와 Sound Cue 순서를 검증한다."""
    issues: list[ValidationIssue] = []
    scene_id = scene.get("scene_id")
    units = mapping_items(scene.get("units"))
    unit_ids = [unit.get("unit_id") for unit in units]
    local_duplicates = duplicate_strings(unit_ids)
    repeated_global_ids = sorted(
        {
            unit_id
            for unit_id in unit_ids
            if isinstance(unit_id, str) and unit_id in global_unit_ids
        }
    )
    duplicated_ids = sorted(set(local_duplicates) | set(repeated_global_ids))
    if duplicated_ids:
        issues.append(
            screenplay_issue(
                "SCREENPLAY_UNIT_ID_DUPLICATED",
                "unit_id는 문서 전체에서 고유해야 합니다.",
                {"scene_id": scene_id, "unit_ids": duplicated_ids},
            )
        )
    global_unit_ids.update(
        unit_id for unit_id in unit_ids if isinstance(unit_id, str)
    )
    issues.extend(
        integer_order_issues(
            [unit.get("order") for unit in units],
            "REENACTMENT_UNIT_ORDER_INVALID",
            "Unit",
            {"scene_id": scene_id},
        )
    )
    segment_ids_raw = scene.get("segment_ids")
    segment_ids = set(segment_ids_raw) if isinstance(segment_ids_raw, list) else set()
    invalid_segments = sorted(
        {
            segment_id
            for unit in units
            if isinstance((segment_id := unit.get("segment_id")), str)
            and segment_id not in segment_ids
        }
    )
    if invalid_segments:
        issues.append(
            screenplay_issue(
                "SCREENPLAY_SEGMENT_REFERENCE_INVALID",
                "모든 Unit segment_id는 소속 Scene의 segment_ids에 있어야 합니다.",
                {"scene_id": scene_id, "segment_ids": invalid_segments},
            )
        )
    issues.extend(validate_unit_speakers(scene_id, units))

    context = scene.get("context")
    sound_cues = mapping_items(context.get("sound_cues")) if isinstance(context, Mapping) else []
    issues.extend(
        integer_order_issues(
            [cue.get("order") for cue in sound_cues],
            "SCREENPLAY_SOUND_CUE_ORDER_INVALID",
            "Sound Cue",
            {"scene_id": scene_id},
        )
    )
    duplicate_cue_ids = duplicate_strings(
        [cue.get("sound_cue_id") for cue in sound_cues]
    )
    if duplicate_cue_ids:
        issues.append(
            screenplay_issue(
                "SCREENPLAY_SOUND_CUE_ID_DUPLICATED",
                "sound_cue_id는 Scene 안에서 고유해야 합니다.",
                {"scene_id": scene_id, "sound_cue_ids": duplicate_cue_ids},
            )
        )
    return issues


def validate_scene_links(scenes: Sequence[Mapping[str, object]]) -> list[ValidationIssue]:
    """이전 장면과 재구성 원본이 반드시 더 앞선 장면을 가리키는지 검증한다."""
    issues: list[ValidationIssue] = []
    earlier_scene_ids: list[str] = []
    for scene in scenes:
        scene_id = scene.get("scene_id")
        context = scene.get("context")
        previous_scene_id = (
            context.get("previous_scene_id") if isinstance(context, Mapping) else None
        )
        expected_previous = earlier_scene_ids[-1] if earlier_scene_ids else None
        if previous_scene_id != expected_previous:
            issues.append(
                screenplay_issue(
                    "SCREENPLAY_PREVIOUS_SCENE_REFERENCE_INVALID",
                    "previous_scene_id는 배열에서 바로 앞선 Scene을 가리켜야 합니다.",
                    {
                        "scene_id": scene_id,
                        "actual_previous_scene_id": previous_scene_id,
                        "expected_previous_scene_id": expected_previous,
                    },
                )
            )
        if scene.get("time_layer") == "RECONSTRUCTION":
            reconstruction_id = scene.get("reconstruction_of_scene_id")
            if reconstruction_id not in earlier_scene_ids:
                issues.append(
                    screenplay_issue(
                        "RECONSTRUCTION_REFERENCE_INVALID",
                        "재구성 Scene은 문서에서 더 앞선 Scene을 참조해야 합니다.",
                        {
                            "scene_id": scene_id,
                            "reconstruction_of_scene_id": reconstruction_id,
                            "earlier_scene_ids": earlier_scene_ids.copy(),
                        },
                    )
                )
        if isinstance(scene_id, str) and scene_id not in earlier_scene_ids:
            earlier_scene_ids.append(scene_id)
    return issues


def validate_reconstruction_repetition(
    scenes: Sequence[Mapping[str, object]],
) -> list[ValidationIssue]:
    """Screenplay 1.1 재구성의 의도적 반복이 원문 Unit과 정확히 결속됐는지 검증한다."""
    scene_units = {
        scene_id: mapping_items(scene.get("units"))
        for scene in scenes
        if isinstance((scene_id := scene.get("scene_id")), str)
    }
    issues: list[ValidationIssue] = []
    for scene in scenes:
        if scene.get("time_layer") != "RECONSTRUCTION":
            continue
        scene_id = scene.get("scene_id")
        source_scene_id = scene.get("reconstruction_of_scene_id")
        source_units = (
            scene_units.get(source_scene_id, [])
            if isinstance(source_scene_id, str)
            else []
        )
        repeated_units = mapping_items(scene.get("units"))
        source_by_id = {
            unit_id: unit
            for unit in source_units
            if isinstance((unit_id := unit.get("unit_id")), str)
        }
        repeated_by_id = {
            unit_id: unit
            for unit in repeated_units
            if isinstance((unit_id := unit.get("unit_id")), str)
        }
        bindings = mapping_items(scene.get("reconstruction_bindings"))
        bound_pairs = {
            (source_id, repeated_id)
            for binding in bindings
            if isinstance((source_id := binding.get("source_unit_id")), str)
            and isinstance((repeated_id := binding.get("repeated_unit_id")), str)
        }
        invalid_pairs: list[dict[str, object]] = []
        for binding in bindings:
            source_id = binding.get("source_unit_id")
            repeated_id = binding.get("repeated_unit_id")
            if not isinstance(source_id, str) or not isinstance(repeated_id, str):
                continue
            source_unit = source_by_id.get(source_id)
            repeated_unit = repeated_by_id.get(repeated_id)
            reason: str | None = None
            if source_unit is None or repeated_unit is None:
                reason = "UNIT_NOT_FOUND"
            elif any(
                source_unit.get(field) != repeated_unit.get(field)
                for field in ("type", "text", "speaker_id", "delivery")
            ):
                reason = "VISIBLE_IDENTITY_CHANGED"
            elif (
                source_unit.get("references") != repeated_unit.get("references")
                and binding.get("reference_policy") != "ALLOW_RECONTEXTUALIZATION"
            ):
                reason = "REFERENCE_CHANGE_NOT_ALLOWED"
            if reason is not None:
                invalid_pairs.append(
                    {
                        "source_unit_id": source_id,
                        "repeated_unit_id": repeated_id,
                        "reason": reason,
                    }
                )
        unbound_repeated_ids = sorted(
            repeated_id
            for repeated_id, repeated in repeated_by_id.items()
            if any(
                source.get("text") == repeated.get("text")
                and source.get("type") == repeated.get("type")
                for source in source_units
            )
            and not any(pair[1] == repeated_id for pair in bound_pairs)
        )
        if invalid_pairs or unbound_repeated_ids:
            issues.append(
                screenplay_issue(
                    "RECONSTRUCTION_REPETITION_MISMATCH",
                    "재구성 반복 Unit은 원본의 유형·text·화자·연기 지시를 보존하고 "
                    "참조 변화 정책을 명시해야 합니다.",
                    {
                        "scene_id": scene_id,
                        "source_scene_id": source_scene_id,
                        "invalid_pairs": invalid_pairs,
                        "unbound_repeated_unit_ids": unbound_repeated_ids,
                    },
                )
            )
    return issues


def validate_screenplay_units(
    document: Mapping[str, object],
) -> list[ValidationIssue]:
    """Screenplay Unit 문서의 Schema 외 의미 불변식을 검증한다."""
    scenes = mapping_items(document.get("scenes"))
    issues: list[ValidationIssue] = []
    scene_ids = [scene.get("scene_id") for scene in scenes]
    duplicated_scene_ids = duplicate_strings(scene_ids)
    if duplicated_scene_ids:
        issues.append(
            screenplay_issue(
                "SCREENPLAY_SCENE_ID_DUPLICATED",
                "scene_id는 문서 전체에서 고유해야 합니다.",
                {"scene_ids": duplicated_scene_ids},
            )
        )
    issues.extend(
        integer_order_issues(
            [scene.get("order") for scene in scenes],
            "REENACTMENT_SCENE_SEQUENCE_INVALID",
            "Scene",
            {},
        )
    )
    global_unit_ids: set[str] = set()
    for scene in scenes:
        issues.extend(validate_scene_units(scene, global_unit_ids))
    issues.extend(validate_scene_links(scenes))
    if document.get("schema_version") == "1.1.0":
        issues.extend(validate_reconstruction_repetition(scenes))
    return issues
