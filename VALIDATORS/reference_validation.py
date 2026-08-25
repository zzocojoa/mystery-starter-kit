"""Reference Firewall 정제와 원문 충돌 검증."""

import hashlib
import re
from collections.abc import Mapping

from VALIDATORS.exceptions import ConfigurationError
from VALIDATORS.models import ValidationIssue

TOKEN_PATTERN = re.compile(r"[0-9A-Za-z가-힣]+")


def make_reference_issue(
    code: str,
    message: str,
    context: dict[str, object],
) -> ValidationIssue:
    """Reference 충돌 문제를 표준 형식으로 생성한다."""
    return ValidationIssue(
        severity="ERROR",
        code=code,
        message=message,
        artifact="08_QA/reference_collision_report.json",
        context=context,
    )


def require_string_list(
    document: Mapping[str, object],
    key: str,
    source: str,
) -> list[str]:
    """필수 문자열 배열을 읽고 잘못된 입력을 명시적으로 거부한다."""
    value = document.get(key)
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise ConfigurationError(
            f"문자열 배열이 필요합니다: source={source}, field={key}"
        )
    return list(value)


def require_mapping(
    document: Mapping[str, object],
    key: str,
    source: str,
) -> Mapping[str, object]:
    """필수 객체를 읽고 잘못된 입력을 명시적으로 거부한다."""
    value = document.get(key)
    if not isinstance(value, Mapping):
        raise ConfigurationError(f"객체가 필요합니다: source={source}, field={key}")
    return value


def sanitize_reference_profile(
    reference_material: Mapping[str, object],
    reference_policy: Mapping[str, object],
) -> dict[str, object]:
    """원문의 Story Content를 버리고 허용된 Style Feature 이름만 보존한다."""
    reference_id = reference_material.get("reference_id")
    if not isinstance(reference_id, str) or not reference_id:
        raise ConfigurationError("reference_material.reference_id 문자열이 필요합니다.")

    allowed_by_policy = set(
        require_string_list(reference_policy, "allowed_style_features", "reference_policy")
    )
    prohibited_by_policy = require_string_list(
        reference_policy,
        "prohibited_story_content",
        "reference_policy",
    )
    selected_features = require_string_list(
        reference_material,
        "selected_style_features",
        "reference_material",
    )
    unsupported = sorted(set(selected_features) - allowed_by_policy)
    if unsupported:
        raise ConfigurationError(
            f"정책이 허용하지 않은 Style Feature입니다: features={unsupported}"
        )

    return {
        "reference_id": reference_id,
        "allowed_style_features": sorted(set(selected_features)),
        "prohibited_story_content": prohibited_by_policy,
        "separation_attestation": True,
    }


def tokenize(text: str) -> list[str]:
    """문장을 대소문자 독립 단어 토큰으로 정규화한다."""
    return [token.casefold() for token in TOKEN_PATTERN.findall(text)]


def phrase_hash(tokens: tuple[str, ...]) -> str:
    """충돌 문구를 노출하지 않는 식별 해시를 만든다."""
    phrase = " ".join(tokens)
    return hashlib.sha256(phrase.encode("utf-8")).hexdigest()


def ngram_hashes(text: str, size: int) -> set[str]:
    """지정 길이의 모든 연속 문구를 비가역 해시 집합으로 만든다."""
    if size < 1:
        raise ConfigurationError(f"N-gram 크기는 1 이상이어야 합니다: size={size}")
    tokens = tokenize(text)
    return {
        phrase_hash(tuple(tokens[index : index + size]))
        for index in range(len(tokens) - size + 1)
    }


def normalized_story_elements(value: object, source: str) -> dict[str, set[str]]:
    """Story Element 객체를 비교 가능한 문자열 집합으로 변환한다."""
    if not isinstance(value, Mapping):
        raise ConfigurationError(f"Story Element 객체가 필요합니다: source={source}")

    normalized: dict[str, set[str]] = {}
    for category, elements in value.items():
        if not isinstance(category, str) or not isinstance(elements, list):
            raise ConfigurationError(
                f"Story Element 배열 형식이 아닙니다: source={source}, category={category}"
            )
        if not all(isinstance(element, str) for element in elements):
            raise ConfigurationError(
                f"Story Element는 문자열이어야 합니다: source={source}, category={category}"
            )
        normalized[category] = {
            " ".join(tokenize(element)) for element in elements if tokenize(element)
        }
    return normalized


def threshold_integer(
    collision_thresholds: Mapping[str, object],
    key: str,
) -> int:
    """Reference 충돌 임계값을 양의 정수로 읽는다."""
    value = collision_thresholds.get(key)
    if not isinstance(value, int) or isinstance(value, bool) or value < 1:
        raise ConfigurationError(f"양의 정수 임계값이 필요합니다: field={key}")
    return value


def validate_reference_collision(
    candidate_script: str,
    candidate_story_elements: Mapping[str, object],
    reference_material: Mapping[str, object],
    reference_policy: Mapping[str, object],
) -> dict[str, object]:
    """문구와 금지 Story Element 재사용을 원문 비노출 방식으로 검사한다."""
    raw_text = reference_material.get("raw_text")
    reference_id = reference_material.get("reference_id")
    if not isinstance(raw_text, str):
        raise ConfigurationError("reference_material.raw_text 문자열이 필요합니다.")
    if not isinstance(reference_id, str) or not reference_id:
        raise ConfigurationError("reference_material.reference_id 문자열이 필요합니다.")

    thresholds = require_mapping(
        reference_policy,
        "collision_thresholds",
        "reference_policy",
    )
    phrase_size = threshold_integer(thresholds, "lexical_phrase_words")
    element_threshold = threshold_integer(thresholds, "story_element_match_count")
    candidate_phrases = ngram_hashes(candidate_script, phrase_size)
    reference_phrases = ngram_hashes(raw_text, phrase_size)
    phrase_collisions = sorted(candidate_phrases & reference_phrases)

    reference_elements = normalized_story_elements(
        reference_material.get("story_content"),
        "reference_material.story_content",
    )
    candidate_elements = normalized_story_elements(
        candidate_story_elements.get("story_content"),
        "candidate_story_elements.story_content",
    )
    prohibited_categories = set(
        require_string_list(
            reference_policy,
            "prohibited_story_content",
            "reference_policy",
        )
    )
    matched_categories = sorted(
        category
        for category in prohibited_categories
        if reference_elements.get(category, set())
        & candidate_elements.get(category, set())
    )

    issues: list[ValidationIssue] = []
    if phrase_collisions:
        issues.append(
            make_reference_issue(
                "REFERENCE_LEXICAL_COLLISION",
                "Reference 원문과 허용 길이 이상의 동일 문구가 발견되었습니다.",
                {
                    "reference_id": reference_id,
                    "phrase_words": phrase_size,
                    "collision_count": len(phrase_collisions),
                    "collision_hashes": phrase_collisions,
                },
            )
        )
    if len(matched_categories) >= element_threshold:
        issues.append(
            make_reference_issue(
                "REFERENCE_STORY_ELEMENT_COLLISION",
                "Reference의 금지 Story Element가 임계값 이상 재사용되었습니다.",
                {
                    "reference_id": reference_id,
                    "matched_categories": matched_categories,
                    "match_count": len(matched_categories),
                    "threshold": element_threshold,
                },
            )
        )

    return {
        "project_id": candidate_story_elements.get("project_id", ""),
        "reference_id": reference_id,
        "result": "FAIL" if issues else "PASS",
        "lexical_collision_count": len(phrase_collisions),
        "matched_story_element_categories": matched_categories,
        "issues": issues,
    }
