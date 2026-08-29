"""Story Fingerprint, Similarity, Causal Hard Collision 판정."""

import json
from collections.abc import Mapping, Sequence
from copy import deepcopy
from difflib import SequenceMatcher
from hashlib import sha256
from typing import cast

from VALIDATORS.exceptions import ConfigurationError
from VALIDATORS.models import ValidationIssue

CAUSAL_FIELDS = ("root_cause", "mechanism", "concealment", "discovery_path", "resolution")
LIST_STORY_FIELDS = {"setting_logic", "information_mechanism"}
SEMANTIC_CAUSAL_FIELDS = (
    "normalized_roles",
    "edge_sequence",
    "character_function_chain",
    "audience_hypothesis_transitions",
)
SEMANTIC_CAUSAL_COLLISION_THRESHOLD = 0.85


def make_novelty_issue(
    code: str,
    message: str,
    context: dict[str, object],
) -> ValidationIssue:
    """Novelty 문제를 표준 형식으로 생성한다."""
    return ValidationIssue(
        severity="ERROR",
        code=code,
        message=message,
        artifact="08_QA/novelty_report.json",
        context=context,
    )


def require_mapping_value(
    document: Mapping[str, object],
    key: str,
    source: str,
) -> dict[str, object]:
    """Novelty 입력의 필수 객체를 읽는다."""
    value = document.get(key)
    if not isinstance(value, Mapping):
        raise ConfigurationError(f"필수 객체가 없습니다: source={source}, field={key}")
    return cast(dict[str, object], dict(value))


def primary_engine(value: object) -> object:
    """복합 Engine에서 비교용 Primary 값을 추출한다."""
    if isinstance(value, Mapping):
        primary = value.get("primary")
        if isinstance(primary, str):
            return primary
        source = value.get("source")
        return source if isinstance(source, str) else ""
    return value


def build_story_signature(story_document: Mapping[str, object]) -> dict[str, object]:
    """Story DNA에서 초기 Novelty Index에 저장할 비교 Signature를 만든다."""
    story_dna = require_mapping_value(story_document, "story_dna", "story_dna")
    return {
        "mystery_type": story_dna.get("mystery_type", ""),
        "architecture": story_dna.get("architecture", ""),
        "protagonist_role": story_dna.get("protagonist_role", ""),
        "primary_twist": story_dna.get("primary_twist", ""),
        "timeline_style": story_dna.get("timeline_style", ""),
        "incident_type": story_dna.get("incident_type", ""),
        "setting": story_dna.get("setting", ""),
        "culprit_structure": story_dna.get("culprit_structure", ""),
        "setting_logic": deepcopy(story_dna.get("setting_logic", [])),
        "information_mechanism": deepcopy(story_dna.get("information_mechanism", [])),
        "relationship_engine": primary_engine(story_dna.get("relationship_engine", "")),
        "pressure_engine": primary_engine(story_dna.get("pressure_engine", "")),
        "dramatic_engine": primary_engine(story_dna.get("dramatic_engine", "")),
    }


def semantic_causal_fingerprint(
    causal_graph: Mapping[str, object],
) -> dict[str, list[str]]:
    """통제된 인과 역할과 Graph Edge Type을 의미 비교용 구조로 정규화한다."""
    normalization = require_mapping_value(
        causal_graph,
        "semantic_normalization",
        "causal_graph",
    )
    normalized = {
        field: require_string_sequence(
            normalization.get(field),
            f"causal_graph.semantic_normalization.{field}",
        )
        for field in (
            "normalized_roles",
            "character_function_chain",
            "audience_hypothesis_transitions",
        )
    }
    nodes = causal_graph.get("nodes")
    edges = causal_graph.get("edges")
    if not isinstance(nodes, list) or not isinstance(edges, list):
        raise ConfigurationError("Semantic Causal Normalization에는 nodes와 edges가 필요합니다.")
    node_types = {
        node.get("node_id"): node.get("type")
        for node in nodes
        if isinstance(node, Mapping)
        and isinstance(node.get("node_id"), str)
        and isinstance(node.get("type"), str)
    }
    edge_sequence: list[str] = []
    for edge in edges:
        if not isinstance(edge, Mapping):
            raise ConfigurationError("causal_graph.edges 객체 배열이 필요합니다.")
        source_type = node_types.get(edge.get("from"))
        target_type = node_types.get(edge.get("to"))
        if not isinstance(source_type, str) or not isinstance(target_type, str):
            raise ConfigurationError(
                "Semantic Causal Edge가 존재하는 Node Type을 참조해야 합니다: "
                f"from={edge.get('from')!r}, to={edge.get('to')!r}"
            )
        edge_sequence.append(f"{source_type}>{target_type}")
    if not edge_sequence:
        raise ConfigurationError("Semantic Causal Edge Sequence는 비어 있을 수 없습니다.")
    normalized["edge_sequence"] = edge_sequence
    return normalized


def build_story_fingerprint(
    story_document: Mapping[str, object],
    beat_sheet: Mapping[str, object],
    causal_graph: Mapping[str, object],
) -> dict[str, object]:
    """Story DNA, Beat, Causal Graph를 정규화된 Fingerprint로 변환한다."""
    beats = beat_sheet.get("beats")
    if not isinstance(beats, list):
        raise ConfigurationError("beat_sheet.beats 배열이 필요합니다.")
    beat_signature = [
        beat.get("type")
        for beat in beats
        if isinstance(beat, Mapping) and isinstance(beat.get("type"), str)
    ]
    causal = require_mapping_value(causal_graph, "fingerprint", "causal_graph")
    missing_causal = [field for field in CAUSAL_FIELDS if not isinstance(causal.get(field), str)]
    if missing_causal:
        raise ConfigurationError(
            f"Causal Fingerprint 필드가 누락되었습니다: fields={missing_causal}"
        )

    return {
        "schema_family": "story-fingerprint",
        "schema_version": "1.1.0",
        "project_id": story_document.get("project_id", ""),
        "story": build_story_signature(story_document),
        "beat_signature": beat_signature,
        "causal": {field: causal[field] for field in CAUSAL_FIELDS},
        "semantic_causal": semantic_causal_fingerprint(causal_graph),
    }


def has_comparable_value(value: object) -> bool:
    """비어 있지 않은 Fingerprint Dimension만 유사도 일치 대상으로 인정한다."""
    if value is None or value == "":
        return False
    if isinstance(value, Mapping | list | tuple | set):
        return bool(value)
    return True


def require_string_sequence(value: object, source: str) -> list[str]:
    """유사도 입력을 문자열 배열로 엄격하게 읽는다."""
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise ConfigurationError(f"문자열 배열이 필요합니다: source={source}")
    return list(value)


def jaccard_similarity(candidate: object, existing: object, field: str) -> float:
    """순서와 무관한 Story Dimension 배열의 Jaccard 유사도를 계산한다."""
    candidate_values = set(
        require_string_sequence(candidate, f"candidate_fingerprint.story.{field}")
    )
    existing_values = set(
        require_string_sequence(existing, f"existing_fingerprint.story.{field}")
    )
    union = candidate_values | existing_values
    if not union:
        raise ConfigurationError(f"Jaccard 비교 배열은 비어 있을 수 없습니다: field={field}")
    return len(candidate_values & existing_values) / len(union)


def sequence_similarity(candidate: object, existing: object) -> float:
    """Beat 순서를 보존하는 Sequence 유사도를 계산한다."""
    candidate_beats = require_string_sequence(
        candidate,
        "candidate_fingerprint.beat_signature",
    )
    existing_beats = require_string_sequence(
        existing,
        "existing_fingerprint.beat_signature",
    )
    if not candidate_beats or not existing_beats:
        raise ConfigurationError("Beat Signature는 하나 이상의 Beat가 필요합니다.")
    return SequenceMatcher(
        None,
        candidate_beats,
        existing_beats,
        autojunk=False,
    ).ratio()


def causal_structure_similarity(candidate: object, existing: object) -> float:
    """Causal 다섯 Dimension의 부분 구조 일치율을 계산한다."""
    if not isinstance(candidate, Mapping) or not isinstance(existing, Mapping):
        raise ConfigurationError("Causal Fingerprint 객체가 필요합니다.")
    invalid_fields = [
        field
        for field in CAUSAL_FIELDS
        if not isinstance(candidate.get(field), str)
        or not candidate.get(field)
        or not isinstance(existing.get(field), str)
        or not existing.get(field)
    ]
    if invalid_fields:
        raise ConfigurationError(
            f"Causal 유사도 필드가 누락되었습니다: fields={invalid_fields}"
        )
    matches = sum(
        1 for field in CAUSAL_FIELDS if candidate.get(field) == existing.get(field)
    )
    return matches / len(CAUSAL_FIELDS)


def sequence_field_similarity(candidate: object, existing: object, source: str) -> float:
    """의미 인과 Chain의 순서 유사도를 계산한다."""
    candidate_values = require_string_sequence(candidate, f"candidate.{source}")
    existing_values = require_string_sequence(existing, f"existing.{source}")
    if not candidate_values or not existing_values:
        raise ConfigurationError(f"Semantic Causal 배열은 비어 있을 수 없습니다: field={source}")
    return SequenceMatcher(
        None,
        candidate_values,
        existing_values,
        autojunk=False,
    ).ratio()


def semantic_causal_similarity(candidate: object, existing: object) -> float:
    """역할·Edge·인물 기능·관객 가설 Chain의 의미 인과 유사도를 계산한다."""
    if not isinstance(candidate, Mapping) or not isinstance(existing, Mapping):
        raise ConfigurationError("Semantic Causal Fingerprint 객체가 필요합니다.")
    invalid = [
        field
        for field in SEMANTIC_CAUSAL_FIELDS
        if not isinstance(candidate.get(field), list)
        or not candidate.get(field)
        or not isinstance(existing.get(field), list)
        or not existing.get(field)
    ]
    if invalid:
        raise ConfigurationError(
            f"Semantic Causal 유사도 필드가 누락되었습니다: fields={invalid}"
        )
    role_similarity = jaccard_similarity(
        candidate["normalized_roles"],
        existing["normalized_roles"],
        "semantic_causal.normalized_roles",
    )
    edge_similarity = jaccard_similarity(
        candidate["edge_sequence"],
        existing["edge_sequence"],
        "semantic_causal.edge_sequence",
    )
    character_similarity = sequence_field_similarity(
        candidate["character_function_chain"],
        existing["character_function_chain"],
        "semantic_causal.character_function_chain",
    )
    hypothesis_similarity = sequence_field_similarity(
        candidate["audience_hypothesis_transitions"],
        existing["audience_hypothesis_transitions"],
        "semantic_causal.audience_hypothesis_transitions",
    )
    return (
        role_similarity * 0.4
        + edge_similarity * 0.25
        + character_similarity * 0.2
        + hypothesis_similarity * 0.15
    )


def fingerprint_component(
    fingerprint: Mapping[str, object],
    story: Mapping[str, object],
    field: str,
) -> object:
    """Weight 이름에 해당하는 Story 또는 구조 Fingerprint 값을 읽는다."""
    if field in {"beat_signature", "causal", "semantic_causal"}:
        return fingerprint.get(field)
    return story.get(field)


def component_similarity(
    field: str,
    candidate_value: object,
    existing_value: object,
) -> float:
    """Dimension 종류별 Exact, Jaccard, Sequence, Structural 유사도를 적용한다."""
    if field in LIST_STORY_FIELDS:
        return jaccard_similarity(candidate_value, existing_value, field)
    if field == "beat_signature":
        return sequence_similarity(candidate_value, existing_value)
    if field == "causal":
        return causal_structure_similarity(candidate_value, existing_value)
    if field == "semantic_causal":
        return semantic_causal_similarity(candidate_value, existing_value)
    if not isinstance(candidate_value, str) or not isinstance(existing_value, str):
        raise ConfigurationError(
            f"Exact 유사도 Dimension은 문자열이어야 합니다: field={field}"
        )
    return 1.0 if candidate_value == existing_value else 0.0


def similarity_components(
    candidate: Mapping[str, object],
    existing: Mapping[str, object],
    weights: Mapping[str, object],
) -> dict[str, float]:
    """비교 가능한 모든 가중 Dimension의 개별 유사도를 반환한다."""
    candidate_story = require_mapping_value(candidate, "story", "candidate_fingerprint")
    existing_story = require_mapping_value(existing, "story", "existing_fingerprint")
    numeric_weights = {
        field: float(weight)
        for field, weight in weights.items()
        if isinstance(field, str)
        and isinstance(weight, int | float)
        and not isinstance(weight, bool)
        and weight > 0
    }
    if not numeric_weights:
        raise ConfigurationError("Novelty Weight가 하나 이상 필요합니다.")

    components: dict[str, float] = {}
    for field in numeric_weights:
        candidate_value = fingerprint_component(candidate, candidate_story, field)
        existing_value = fingerprint_component(existing, existing_story, field)
        if not has_comparable_value(candidate_value) or not has_comparable_value(
            existing_value
        ):
            continue
        components[field] = component_similarity(
            field,
            candidate_value,
            existing_value,
        )
    if not components:
        raise ConfigurationError("비교 가능한 Novelty Dimension이 하나 이상 필요합니다.")
    return components


def similarity_score(
    candidate: Mapping[str, object],
    existing: Mapping[str, object],
    weights: Mapping[str, object],
) -> float:
    """Story, Beat, Causal Fingerprint의 가중 유사도를 계산한다."""
    numeric_weights = {
        field: float(weight)
        for field, weight in weights.items()
        if isinstance(field, str)
        and isinstance(weight, int | float)
        and not isinstance(weight, bool)
        and weight > 0
    }
    components = similarity_components(candidate, existing, weights)
    total_weight = sum(numeric_weights[field] for field in components)
    matched_weight = sum(
        numeric_weights[field] * similarity
        for field, similarity in components.items()
    )
    return round((matched_weight / total_weight) * 100, 2)


def causal_hard_collision(
    candidate: Mapping[str, object],
    existing: Mapping[str, object],
) -> bool:
    """다섯 Causal Dimension이 모두 같으면 Hard Collision으로 판정한다."""
    candidate_causal = require_mapping_value(candidate, "causal", "candidate_fingerprint")
    existing_causal = require_mapping_value(existing, "causal", "existing_fingerprint")
    return all(
        candidate_causal.get(field) == existing_causal.get(field)
        and isinstance(candidate_causal.get(field), str)
        and bool(candidate_causal.get(field))
        for field in CAUSAL_FIELDS
    )


def has_complete_mapping_fields(
    document: Mapping[str, object],
    key: str,
    fields: Sequence[str],
) -> bool:
    """비교 기록이 완전한 구조 Fingerprint를 가졌는지 확인한다."""
    value = document.get(key)
    return isinstance(value, Mapping) and all(
        has_comparable_value(value.get(field)) for field in fields
    )


def semantic_causal_hard_collision(
    candidate: Mapping[str, object],
    existing: Mapping[str, object],
) -> bool:
    """표면 명칭과 무관한 의미 인과 유사도가 임계값 이상인지 판정한다."""
    candidate_semantic = require_mapping_value(
        candidate,
        "semantic_causal",
        "candidate_fingerprint",
    )
    existing_semantic = require_mapping_value(
        existing,
        "semantic_causal",
        "existing_fingerprint",
    )
    return (
        semantic_causal_similarity(candidate_semantic, existing_semantic)
        >= SEMANTIC_CAUSAL_COLLISION_THRESHOLD
    )


def threshold_value(thresholds: Mapping[str, object], key: str) -> float:
    """Novelty Threshold 숫자를 읽는다."""
    similarity = require_mapping_value(thresholds, "similarity", "novelty_thresholds")
    value = similarity.get(key)
    if not isinstance(value, int | float):
        raise ConfigurationError(f"Novelty Threshold가 숫자가 아닙니다: field={key}")
    return float(value)


def history_for_other_projects(
    project_id: object,
    history: Sequence[Mapping[str, object]],
) -> list[Mapping[str, object]]:
    """현재 Project를 제외한 신규성 비교 History를 반환한다."""
    if not isinstance(project_id, str) or not project_id:
        raise ConfigurationError("신규성 비교에는 Candidate Project ID가 필요합니다.")
    own_positions = [
        index for index, record in enumerate(history) if record.get("project_id") == project_id
    ]
    historical_scope = history[: own_positions[-1]] if own_positions else history
    return [record for record in historical_scope if record.get("project_id") != project_id]


def evaluate_novelty(
    candidate: Mapping[str, object],
    history: Sequence[Mapping[str, object]],
    thresholds: Mapping[str, object],
) -> dict[str, object]:
    """최근성과 전체 유사도, Causal Hard Collision을 통합 판정한다."""
    weights = require_mapping_value(thresholds, "weights", "novelty_thresholds")
    comparisons: list[dict[str, object]] = []
    issues: list[ValidationIssue] = []
    comparable_history = history_for_other_projects(candidate.get("project_id"), history)
    history_count = len(comparable_history)
    for index, existing in enumerate(comparable_history):
        score = similarity_score(candidate, existing, weights)
        components = similarity_components(candidate, existing, weights)
        distance_from_latest = history_count - index
        threshold_key = (
            "recent_5_max"
            if distance_from_latest <= 5
            else "recent_10_max"
            if distance_from_latest <= 10
            else "overall_max"
        )
        maximum = threshold_value(thresholds, threshold_key)
        hard_collision = (
            has_complete_mapping_fields(candidate, "causal", CAUSAL_FIELDS)
            and has_complete_mapping_fields(existing, "causal", CAUSAL_FIELDS)
            and causal_hard_collision(candidate, existing)
        )
        semantic_collision = (
            has_complete_mapping_fields(
                candidate,
                "semantic_causal",
                SEMANTIC_CAUSAL_FIELDS,
            )
            and has_complete_mapping_fields(
                existing,
                "semantic_causal",
                SEMANTIC_CAUSAL_FIELDS,
            )
            and semantic_causal_hard_collision(candidate, existing)
        )
        project_id = existing.get("project_id", "")
        comparisons.append(
            {
                "project_id": project_id,
                "similarity": score,
                "components": {
                    field: round(component * 100, 2)
                    for field, component in components.items()
                },
                "threshold": maximum,
                "causal_hard_collision": hard_collision,
                "semantic_causal_collision": semantic_collision,
            }
        )
        if hard_collision:
            issues.append(
                make_novelty_issue(
                    "CAUSAL_HARD_COLLISION",
                    "기존 작품과 Causal Fingerprint 다섯 요소가 모두 같습니다.",
                    {"project_id": project_id},
                )
            )
        elif semantic_collision:
            issues.append(
                make_novelty_issue(
                    "CAUSAL_SEMANTIC_COLLISION",
                    "표면 명칭은 다르지만 기존 작품과 의미 인과 골격이 같습니다.",
                    {
                        "project_id": project_id,
                        "semantic_similarity": round(
                            semantic_causal_similarity(
                                candidate["semantic_causal"],
                                existing["semantic_causal"],
                            )
                            * 100,
                            2,
                        ),
                    },
                )
            )
        elif score > maximum:
            issues.append(
                make_novelty_issue(
                    "STORY_SIMILARITY_EXCEEDED",
                    "기존 작품과의 구조적 유사도가 허용치를 넘었습니다.",
                    {"project_id": project_id, "similarity": score, "threshold": maximum},
                )
            )

    return {
        "project_id": candidate.get("project_id", ""),
        "result": "FAIL" if issues else "PASS",
        "comparisons": comparisons,
        "hard_collisions": [
            comparison["project_id"]
            for comparison in comparisons
            if comparison["causal_hard_collision"] is True
        ],
        "semantic_hard_collisions": [
            comparison["project_id"]
            for comparison in comparisons
            if comparison["semantic_causal_collision"] is True
        ],
        "issues": issues,
    }


def variation_precheck_source_hash(
    candidates_document: Mapping[str, object],
) -> str:
    """승인 상태와 무관한 Candidate 구조 입력 Hash를 계산한다."""
    candidates = candidates_document.get("candidates")
    if not isinstance(candidates, list) or not all(
        isinstance(candidate, Mapping) for candidate in candidates
    ):
        raise ConfigurationError("variation_candidates.candidates 객체 배열이 필요합니다.")
    payload = {
        "project_id": candidates_document.get("project_id"),
        "candidates": [
            {
                "candidate_id": candidate.get("candidate_id"),
                "selection": candidate.get("selection"),
                "signature": candidate.get("signature"),
            }
            for candidate in candidates
        ]
    }
    serialized = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return sha256(serialized.encode()).hexdigest()


def evaluate_variation_precheck(
    candidates_document: Mapping[str, object],
    history: Sequence[Mapping[str, object]],
    thresholds: Mapping[str, object],
) -> dict[str, object]:
    """모든 Variation을 Story History와 비교해 평가 전 중복을 차단한다."""
    candidates = candidates_document.get("candidates")
    if not isinstance(candidates, list) or not all(
        isinstance(candidate, Mapping) for candidate in candidates
    ):
        raise ConfigurationError("variation_candidates.candidates 객체 배열이 필요합니다.")

    weights = require_mapping_value(thresholds, "weights", "novelty_thresholds")
    comparable_history = history_for_other_projects(
        candidates_document.get("project_id"),
        history,
    )
    history_count = len(comparable_history)
    candidate_results: list[dict[str, object]] = []
    issues: list[ValidationIssue] = []
    for candidate in candidates:
        candidate_id = candidate.get("candidate_id")
        selection = candidate.get("selection")
        if not isinstance(candidate_id, str) or not isinstance(selection, Mapping):
            raise ConfigurationError("Variation Candidate ID와 selection 객체가 필요합니다.")
        comparisons: list[dict[str, object]] = []
        for index, existing in enumerate(comparable_history):
            distance_from_latest = history_count - index
            threshold_key = (
                "recent_5_max"
                if distance_from_latest <= 5
                else "recent_10_max"
                if distance_from_latest <= 10
                else "overall_max"
            )
            maximum = threshold_value(thresholds, threshold_key)
            score = similarity_score({"story": dict(selection)}, existing, weights)
            components = similarity_components(
                {"story": dict(selection)},
                existing,
                weights,
            )
            comparisons.append(
                {
                    "project_id": existing.get("project_id", ""),
                    "similarity": score,
                    "components": {
                        field: round(component * 100, 2)
                        for field, component in components.items()
                    },
                    "threshold": maximum,
                    "exceeded": score > maximum,
                }
            )
        collisions = [
            comparison
            for comparison in comparisons
            if comparison["exceeded"] is True
        ]
        result = "FAIL" if collisions else "PASS"
        candidate_results.append(
            {
                "candidate_id": candidate_id,
                "result": result,
                "comparisons": comparisons,
            }
        )
    passed_count = sum(
        1 for candidate_result in candidate_results if candidate_result["result"] == "PASS"
    )
    if passed_count == 0:
        issues.append(
            make_novelty_issue(
                "ALL_VARIATION_CANDIDATES_NOVELTY_FAILED",
                "모든 Variation 후보가 Story 설계 전 신규성 기준을 통과하지 못했습니다.",
                {"candidate_count": len(candidate_results)},
            )
        )
    return {
        "schema_family": "novelty-precheck",
        "schema_version": "1.1.0",
        "project_id": candidates_document.get("project_id", ""),
        "source_hash": variation_precheck_source_hash(candidates_document),
        "result": "PASS" if passed_count > 0 else "FAIL",
        "candidate_results": candidate_results,
        "issues": issues,
    }
