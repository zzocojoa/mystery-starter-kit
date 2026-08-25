"""Channel DNA 의미 규칙과 Story 일관성 검증."""

from collections.abc import Mapping

from VALIDATORS.compatibility import make_error, mapping_or_empty
from VALIDATORS.models import CompatibilityError, ValidationIssue


def validate_reaction_ratio(channel: Mapping[str, object]) -> list[CompatibilityError]:
    """Reaction 비율의 최소값이 최대값을 넘지 않는지 검사한다."""
    capabilities = mapping_or_empty(channel, "capabilities")
    reaction = capabilities.get("REACTION_POLICY")
    if not isinstance(reaction, Mapping):
        return []

    target_ratio = reaction.get("target_ratio")
    if not isinstance(target_ratio, Mapping):
        return []

    minimum = target_ratio.get("min")
    maximum = target_ratio.get("max")
    if not isinstance(minimum, int | float) or not isinstance(maximum, int | float):
        return []
    if minimum <= maximum:
        return []

    return [
        make_error(
            "INVALID_REACTION_RATIO",
            "Reaction 목표 비율의 min은 max보다 클 수 없습니다.",
            {"min": minimum, "max": maximum},
        )
    ]


def make_channel_issue(
    code: str,
    message: str,
    artifact: str,
    context: dict[str, object],
) -> ValidationIssue:
    """Channel Consistency 문제를 표준 형식으로 생성한다."""
    return ValidationIssue(
        severity="ERROR",
        code=code,
        message=message,
        artifact=artifact,
        context=context,
    )


def validate_channel_consistency(
    channel: Mapping[str, object],
    story_document: Mapping[str, object],
    production_config: Mapping[str, object],
    presentation_plan: Mapping[str, object],
) -> list[ValidationIssue]:
    """Story와 Presentation이 Channel의 장르·톤·표현 제약을 지키는지 검사한다."""
    capabilities = mapping_or_empty(channel, "capabilities")
    genre_policy = capabilities.get("GENRE_POLICY")
    tone_policy = capabilities.get("TONE_POLICY")
    presentation_policy = capabilities.get("PRESENTATION_POLICY")
    reaction_policy = capabilities.get("REACTION_POLICY")
    story_dna = story_document.get("story_dna")
    issues: list[ValidationIssue] = []

    if isinstance(genre_policy, Mapping) and isinstance(story_dna, Mapping):
        allowed_genres = genre_policy.get("allowed_genres")
        genre = production_config.get("genre")
        if (
            isinstance(allowed_genres, list)
            and isinstance(genre, str)
            and genre not in allowed_genres
        ):
            issues.append(
                make_channel_issue(
                    "CHANNEL_GENRE_VIOLATION",
                    "프로젝트 장르가 Channel의 허용 장르에 없습니다.",
                    "00_PROJECT/production_config.json",
                    {"genre": genre, "allowed_genres": allowed_genres},
                )
            )

    if isinstance(tone_policy, Mapping):
        prohibited_tones = tone_policy.get("prohibited_tones")
        selected_tones = production_config.get("tones")
        if isinstance(prohibited_tones, list) and isinstance(selected_tones, list):
            collisions = sorted(
                tone
                for tone in selected_tones
                if isinstance(tone, str) and tone in prohibited_tones
            )
            if collisions:
                issues.append(
                    make_channel_issue(
                        "CHANNEL_TONE_VIOLATION",
                        "프로젝트 톤이 Channel의 금지 톤과 충돌합니다.",
                        "00_PROJECT/production_config.json",
                        {"prohibited_tones": collisions},
                    )
                )

    if isinstance(presentation_policy, Mapping):
        required_modes = presentation_policy.get("modes")
        selected_modes = presentation_plan.get("modes")
        if isinstance(required_modes, list) and isinstance(selected_modes, list):
            missing_modes = sorted(
                mode
                for mode in required_modes
                if isinstance(mode, str) and mode not in selected_modes
            )
            if missing_modes:
                issues.append(
                    make_channel_issue(
                        "CHANNEL_PRESENTATION_VIOLATION",
                        "Channel의 핵심 Presentation Mode가 누락되었습니다.",
                        "06_SCENE/presentation_plan.json",
                        {"missing_modes": missing_modes},
                    )
                )

    if isinstance(reaction_policy, Mapping):
        target_ratio = reaction_policy.get("target_ratio")
        selected_ratio = presentation_plan.get("reaction_ratio")
        if isinstance(target_ratio, Mapping) and isinstance(selected_ratio, int | float):
            minimum = target_ratio.get("min")
            maximum = target_ratio.get("max")
            if (
                isinstance(minimum, int | float)
                and isinstance(maximum, int | float)
                and not minimum <= selected_ratio <= maximum
            ):
                issues.append(
                    make_channel_issue(
                        "CHANNEL_REACTION_RATIO_VIOLATION",
                        "Reaction 비율이 Channel의 허용 범위를 벗어났습니다.",
                        "06_SCENE/presentation_plan.json",
                        {
                            "reaction_ratio": selected_ratio,
                            "minimum": minimum,
                            "maximum": maximum,
                        },
                    )
                )

    return issues
