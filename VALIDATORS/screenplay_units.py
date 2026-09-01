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
    return issues
