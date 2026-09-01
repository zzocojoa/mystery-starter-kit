"""Versioned Clue Matrix의 Seed, Reveal과 회고적 재해석을 검증한다."""

from collections.abc import Mapping, Sequence

from VALIDATORS.models import ValidationIssue


def clue_issue(
    code: str,
    message: str,
    context: Mapping[str, object],
) -> ValidationIssue:
    """Clue Recontextualization 문제를 공통 형식으로 만든다."""
    return ValidationIssue(
        severity="ERROR",
        code=code,
        message=message,
        artifact="04_MYSTERY/clue_matrix.json",
        context=dict(context),
    )


def mapping_records(document: Mapping[str, object], field: str) -> list[Mapping[str, object]]:
    """객체 배열 필드를 의미 검증용으로 반환한다."""
    value = document.get(field)
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        return []
    return [item for item in value if isinstance(item, Mapping)]


def scene_order_index(scene_cards: Mapping[str, object]) -> dict[str, int]:
    """Scene ID를 명시된 순서로 색인한다."""
    return {
        scene_id: order
        for scene in mapping_records(scene_cards, "scenes")
        if isinstance((scene_id := scene.get("scene_id")), str)
        and isinstance((order := scene.get("order")), int)
        and not isinstance(order, bool)
    }


def normalized_meaning(value: object) -> str:
    """표면·실제 의미 비교용 공백 정규화 문자열을 반환한다."""
    if not isinstance(value, str):
        return ""
    return " ".join(value.split()).casefold()


def string_list(value: object) -> list[str]:
    """문자열 배열만 복사해 반환한다."""
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, str)]


def clue_scene_reference_issues(
    clue: Mapping[str, object],
    scene_orders: Mapping[str, int],
) -> list[ValidationIssue]:
    """Clue의 Scene ID와 명시 order 결속을 검증한다."""
    clue_id = clue.get("clue_id")
    issues: list[ValidationIssue] = []
    pairs = (
        ("introduced_scene_id", "introduced_scene_order"),
        ("resolved_scene_id", "resolved_scene_order"),
    )
    for scene_field, order_field in pairs:
        scene_id = clue.get(scene_field)
        declared_order = clue.get(order_field)
        if scene_id is None:
            continue
        actual_order = scene_orders.get(scene_id) if isinstance(scene_id, str) else None
        if actual_order is None or declared_order != actual_order:
            issues.append(
                clue_issue(
                    "CLUE_SCENE_REFERENCE_INVALID",
                    "Clue Scene ID는 존재해야 하며 선언된 Scene order와 일치해야 합니다.",
                    {
                        "clue_id": clue_id,
                        "scene_field": scene_field,
                        "scene_id": scene_id,
                        "declared_order": declared_order,
                        "actual_order": actual_order,
                    },
                )
            )
    return issues


def seeded_reinterpretation_issues(
    clue: Mapping[str, object],
    scene_orders: Mapping[str, int],
) -> list[ValidationIssue]:
    """Seeded Reveal의 선행 Seed, 의미 변화와 재맥락 Scene 순서를 검증한다."""
    clue_id = clue.get("clue_id")
    first_scene_id = clue.get("first_seen_scene_id")
    reveal_scene_id = clue.get("reveal_scene_id")
    first_order = scene_orders.get(first_scene_id) if isinstance(first_scene_id, str) else None
    reveal_order = scene_orders.get(reveal_scene_id) if isinstance(reveal_scene_id, str) else None
    issues: list[ValidationIssue] = []
    if (
        first_order is None
        or reveal_order is None
        or first_order >= reveal_order
        or clue.get("introduced_scene_id") != first_scene_id
    ):
        issues.append(
            clue_issue(
                "REVEAL_WITHOUT_PRIOR_SEED",
                "재해석 Reveal은 더 앞선 Seed Scene에 동일 Clue를 먼저 배치해야 합니다.",
                {
                    "clue_id": clue_id,
                    "first_seen_scene_id": first_scene_id,
                    "first_seen_order": first_order,
                    "reveal_scene_id": reveal_scene_id,
                    "reveal_order": reveal_order,
                },
            )
        )
    if normalized_meaning(clue.get("surface_meaning")) == normalized_meaning(
        clue.get("actual_meaning")
    ):
        issues.append(
            clue_issue(
                "CLUE_MEANING_NOT_RECONTEXTUALIZED",
                "재해석 Clue의 surface_meaning과 actual_meaning은 달라야 합니다.",
                {"clue_id": clue_id},
            )
        )
    recontextualized_ids = string_list(clue.get("recontextualized_scene_ids"))
    recontextualized_orders = [
        scene_orders.get(scene_id) for scene_id in recontextualized_ids
    ]
    valid_recontextualized_orders = [
        order for order in recontextualized_orders if order is not None
    ]
    valid_range = (
        first_order is not None
        and reveal_order is not None
        and first_scene_id in recontextualized_ids
        and len(valid_recontextualized_orders) == len(recontextualized_orders)
        and all(
            first_order <= order < reveal_order
            for order in valid_recontextualized_orders
        )
        and valid_recontextualized_orders == sorted(valid_recontextualized_orders)
    )
    if not valid_range:
        issues.append(
            clue_issue(
                "CLUE_RECONTEXTUALIZATION_SCENE_INVALID",
                "재맥락 Scene은 Seed부터 Reveal 전까지의 실제 Scene 순서로 나열해야 합니다.",
                {
                    "clue_id": clue_id,
                    "recontextualized_scene_ids": recontextualized_ids,
                    "scene_orders": recontextualized_orders,
                },
            )
        )
    if clue.get("resolved_scene_id") != reveal_scene_id:
        issues.append(
            clue_issue(
                "CLUE_REVEAL_BINDING_MISMATCH",
                "resolved_scene_id는 재해석 reveal_scene_id와 일치해야 합니다.",
                {
                    "clue_id": clue_id,
                    "resolved_scene_id": clue.get("resolved_scene_id"),
                    "reveal_scene_id": reveal_scene_id,
                },
            )
        )
    return issues


def validate_clue_recontextualization(
    clue_matrix: Mapping[str, object],
    scene_cards: Mapping[str, object],
) -> list[ValidationIssue]:
    """Clue Matrix 1.1의 명시적 Reveal mode와 Scene 결속을 검증한다."""
    if clue_matrix.get("schema_version") != "1.1.0":
        return []
    scene_orders = scene_order_index(scene_cards)
    issues: list[ValidationIssue] = []
    for clue in mapping_records(clue_matrix, "clues"):
        issues.extend(clue_scene_reference_issues(clue, scene_orders))
        reveal_mode = clue.get("reveal_mode")
        reveal_scene_id = clue.get("reveal_scene_id")
        if reveal_mode == "SEEDED_REINTERPRETATION":
            issues.extend(seeded_reinterpretation_issues(clue, scene_orders))
        elif reveal_mode == "INTENTIONAL_NON_MYSTERY_DISCLOSURE" and (
            not isinstance(reveal_scene_id, str) or reveal_scene_id not in scene_orders
        ):
            issues.append(
                clue_issue(
                    "CLUE_SCENE_REFERENCE_INVALID",
                    "의도적 비미스터리 공개도 실제 Reveal Scene을 참조해야 합니다.",
                    {"clue_id": clue.get("clue_id"), "scene_id": reveal_scene_id},
                )
            )
    return issues
