"""Reference Firewall 정제와 원문 충돌 검증."""

import hashlib
import re
from collections.abc import Mapping

from VALIDATORS.exceptions import ConfigurationError
from VALIDATORS.models import ValidationIssue

TOKEN_PATTERN = re.compile(r"[0-9A-Za-z가-힣]+")
NUMBER_PATTERN = re.compile(r"(?<![0-9A-Za-z가-힣_-])[0-9]+(?:[.,][0-9]+)?(?![0-9.,])")
DIALOGUE_TAG = "[DIALOGUE]"
DIALOGUE_PATTERNS = (
    re.compile(r'"([^"\n]+)"'),
    re.compile(r"“([^”\n]+)”"),
    re.compile(r"'([^'\n]+)'"),
    re.compile("\\u2018([^\\u2019\\n]+)\\u2019"),
)
REFERENCE_STORY_CATEGORIES = (
    "CHARACTERS",
    "CHARACTER_RELATIONSHIPS",
    "LOCATIONS",
    "INCIDENTS",
    "CULPRIT",
    "VICTIM",
    "MOTIVE",
    "METHOD",
    "CLUES",
    "TWISTS",
    "UNIQUE_DIALOGUE",
    "UNIQUE_NUMBERS",
    "UNIQUE_OBJECTS",
    "BEAT_SEQUENCE",
)


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


def require_record_list(
    document: Mapping[str, object],
    key: str,
    source: str,
) -> list[Mapping[str, object]]:
    """Artifact의 필수 객체 배열을 엄격하게 읽는다."""
    value = document.get(key)
    if not isinstance(value, list) or not all(isinstance(item, Mapping) for item in value):
        raise ConfigurationError(f"객체 배열이 필요합니다: source={source}, field={key}")
    return list(value)


def optional_string(document: Mapping[str, object], key: str) -> list[str]:
    """선택 문자열 필드가 존재할 때 단일 요소 배열로 반환한다."""
    value = document.get(key)
    if value is None:
        return []
    if not isinstance(value, str):
        raise ConfigurationError(f"선택 필드는 문자열이어야 합니다: field={key}")
    return [value] if value.strip() else []


def optional_string_list(document: Mapping[str, object], key: str) -> list[str]:
    """선택 문자열 배열 필드를 엄격하게 읽는다."""
    value = document.get(key)
    if value is None:
        return []
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise ConfigurationError(f"선택 필드는 문자열 배열이어야 합니다: field={key}")
    return [item for item in value if item.strip()]


def unique_strings(values: list[str]) -> list[str]:
    """빈 문자열을 제거한 고유 Story Element를 정렬한다."""
    return sorted({value.strip() for value in values if value.strip()})


def character_elements(
    characters: Mapping[str, object],
) -> tuple[list[str], dict[str, str], list[str]]:
    """Character 이름, ID-이름 사전, 명시적 Victim 이름을 추출한다."""
    records = require_record_list(characters, "characters", "characters")
    names: list[str] = []
    names_by_id: dict[str, str] = {}
    victims: list[str] = []
    for record in records:
        character_id = record.get("character_id")
        name = record.get("name")
        role = record.get("role")
        if not isinstance(character_id, str) or not isinstance(name, str):
            raise ConfigurationError(
                "Character ID와 이름 문자열이 필요합니다: source=characters"
            )
        names.append(name)
        names_by_id[character_id] = name
        if role == "VICTIM":
            victims.append(name)
    return unique_strings(names), names_by_id, unique_strings(victims)


def relationship_elements(
    relationships: Mapping[str, object],
    names_by_id: Mapping[str, str],
) -> list[str]:
    """Character Relationship을 이름과 Engine의 Canonical 문자열로 변환한다."""
    records = require_record_list(
        relationships,
        "relationships",
        "relationships",
    )
    elements: list[str] = []
    for record in records:
        source_id = record.get("from")
        target_id = record.get("to")
        engine = record.get("engine")
        if not isinstance(source_id, str) or not isinstance(target_id, str):
            raise ConfigurationError("Relationship from/to 문자열이 필요합니다.")
        if not isinstance(engine, str):
            raise ConfigurationError("Relationship engine 문자열이 필요합니다.")
        source_name = names_by_id.get(source_id, source_id)
        target_name = names_by_id.get(target_id, target_id)
        elements.append(f"{source_name} {engine} {target_name}")
    return unique_strings(elements)


def location_elements(actual_timeline: Mapping[str, object]) -> list[str]:
    """Actual Timeline의 Location ID를 추출한다."""
    records = require_record_list(actual_timeline, "events", "actual_timeline")
    locations: list[str] = []
    for record in records:
        location_id = record.get("location_id")
        if not isinstance(location_id, str):
            raise ConfigurationError("Timeline Event location_id 문자열이 필요합니다.")
        locations.append(location_id)
    return unique_strings(locations)


def clue_and_object_elements(
    clue_matrix: Mapping[str, object],
) -> tuple[list[str], list[str]]:
    """Clue 설명/Mechanism과 고유 Object를 분리해 추출한다."""
    records = require_record_list(clue_matrix, "clues", "clue_matrix")
    clue_fields = (
        "description",
        "content",
        "mechanism",
        "first_interpretation",
        "true_meaning",
    )
    object_fields = ("object", "object_name", "evidence_object")
    clues = [
        value
        for record in records
        for field in clue_fields
        for value in optional_string(record, field)
    ]
    objects = [
        value
        for record in records
        for field in object_fields
        for value in optional_string(record, field)
    ]
    return unique_strings(clues), unique_strings(objects)


def twist_elements(story_document: Mapping[str, object]) -> list[str]:
    """Story DNA의 Primary와 Secondary Twist Canonical ID를 추출한다."""
    story_dna = require_mapping(story_document, "story_dna", "story_dna")
    values = optional_string(story_dna, "primary_twist")
    values.extend(optional_string_list(story_dna, "secondary_twists"))
    return unique_strings(values)


def dialogue_elements(script: str) -> list[str]:
    """명시적 Dialogue Tag와 인용부호 안의 대사를 추출한다."""
    tagged = [
        line.strip()[len(DIALOGUE_TAG) :].strip()
        for line in script.splitlines()
        if line.strip().startswith(DIALOGUE_TAG)
        and line.strip()[len(DIALOGUE_TAG) :].strip()
    ]
    quoted = [
        match.group(1).strip()
        for pattern in DIALOGUE_PATTERNS
        for match in pattern.finditer(script)
        if match.group(1).strip()
    ]
    return unique_strings(tagged + quoted)


def number_elements(script: str) -> list[str]:
    """Final Script에 명시된 고유 숫자 문자열을 추출한다."""
    return unique_strings(NUMBER_PATTERN.findall(script))


def beat_sequence_elements(beat_sheet: Mapping[str, object]) -> list[str]:
    """Beat Sheet의 순서를 하나의 Canonical Sequence로 추출한다."""
    records = require_record_list(beat_sheet, "beats", "beat_sheet")
    beat_types: list[str] = []
    for record in records:
        beat_type = record.get("type")
        if not isinstance(beat_type, str):
            raise ConfigurationError("Beat type 문자열이 필요합니다.")
        beat_types.append(beat_type)
    return [" -> ".join(beat_types)] if beat_types else []


def build_story_element_profile(
    project_id: str,
    story_document: Mapping[str, object],
    case_input: Mapping[str, object],
    characters: Mapping[str, object],
    relationships: Mapping[str, object],
    actual_timeline: Mapping[str, object],
    clue_matrix: Mapping[str, object],
    causal_graph: Mapping[str, object],
    beat_sheet: Mapping[str, object],
    final_script: str,
) -> dict[str, object]:
    """Policy가 금지한 14개 Story Content Category를 Project에서 추출한다."""
    names, names_by_id, role_victims = character_elements(characters)
    clues, clue_objects = clue_and_object_elements(clue_matrix)
    causal_fingerprint = require_mapping(
        causal_graph,
        "fingerprint",
        "causal_graph",
    )
    incidents = [
        value
        for key in ("incident_type", "central_mystery", "final_truth", "causal_truth")
        for value in optional_string(case_input, key)
    ]
    victims = role_victims + optional_string(case_input, "victim")
    methods = optional_string(case_input, "method") + optional_string(
        causal_fingerprint,
        "mechanism",
    )
    objects = clue_objects + optional_string_list(case_input, "unique_objects")
    story_content = {
        "CHARACTERS": names,
        "CHARACTER_RELATIONSHIPS": relationship_elements(
            relationships,
            names_by_id,
        ),
        "LOCATIONS": location_elements(actual_timeline),
        "INCIDENTS": unique_strings(incidents),
        "CULPRIT": unique_strings(optional_string(case_input, "culprit")),
        "VICTIM": unique_strings(victims),
        "MOTIVE": unique_strings(optional_string(case_input, "culprit_motive")),
        "METHOD": unique_strings(methods),
        "CLUES": clues,
        "TWISTS": twist_elements(story_document),
        "UNIQUE_DIALOGUE": dialogue_elements(final_script),
        "UNIQUE_NUMBERS": number_elements(final_script),
        "UNIQUE_OBJECTS": unique_strings(objects),
        "BEAT_SEQUENCE": beat_sequence_elements(beat_sheet),
    }
    if tuple(story_content) != REFERENCE_STORY_CATEGORIES:
        raise ConfigurationError("Reference Story Category 순서가 Policy 계약과 다릅니다.")
    return {"project_id": project_id, "story_content": story_content}


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
    missing_candidate_categories = sorted(
        prohibited_categories - set(candidate_elements)
    )
    if missing_candidate_categories:
        raise ConfigurationError(
            "Candidate Story Element Profile에 Policy Category가 누락되었습니다: "
            f"categories={missing_candidate_categories}"
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
