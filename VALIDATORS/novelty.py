"""Story Fingerprint, Similarity, Causal Hard Collision 판정."""

import json
from collections.abc import Mapping, Sequence
from copy import deepcopy
from hashlib import sha256
from typing import cast

from VALIDATORS.exceptions import ConfigurationError
from VALIDATORS.models import ValidationIssue

CAUSAL_FIELDS = ("root_cause", "mechanism", "concealment", "discovery_path", "resolution")


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


def build_story_fingerprint(
    story_document: Mapping[str, object],
    beat_sheet: Mapping[str, object],
    causal_graph: Mapping[str, object],
) -> dict[str, object]:
    """Story DNA, Beat, Causal Graph를 정규화된 Fingerprint로 변환한다."""
    story_dna = require_mapping_value(story_document, "story_dna", "story_dna")
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

    fingerprint_story = {
        "mystery_type": story_dna.get("mystery_type", ""),
        "architecture": story_dna.get("architecture", ""),
        "protagonist_role": story_dna.get("protagonist_role", ""),
        "primary_twist": story_dna.get("primary_twist", ""),
        "timeline_style": story_dna.get("timeline_style", ""),
        "culprit_structure": story_dna.get("culprit_structure", ""),
        "setting_logic": deepcopy(story_dna.get("setting_logic", [])),
        "information_mechanism": deepcopy(story_dna.get("information_mechanism", [])),
        "relationship_engine": primary_engine(story_dna.get("relationship_engine", "")),
        "pressure_engine": primary_engine(story_dna.get("pressure_engine", "")),
        "dramatic_engine": primary_engine(story_dna.get("dramatic_engine", "")),
    }
    return {
        "schema_family": "story-fingerprint",
        "schema_version": "1.0.0",
        "project_id": story_document.get("project_id", ""),
        "story": fingerprint_story,
        "beat_signature": beat_signature,
        "causal": {field: causal[field] for field in CAUSAL_FIELDS},
    }


def normalized_value(value: object) -> object:
    """Fingerprint의 배열 값을 순서 독립 비교 형식으로 변환한다."""
    if isinstance(value, list):
        return tuple(sorted(str(item) for item in value))
    return value


def has_comparable_value(value: object) -> bool:
    """비어 있지 않은 Fingerprint Dimension만 유사도 일치 대상으로 인정한다."""
    return value not in (None, "", [], ())


def similarity_score(
    candidate: Mapping[str, object],
    existing: Mapping[str, object],
    weights: Mapping[str, object],
) -> float:
    """Story Fingerprint의 가중 일치율을 0부터 100 사이로 계산한다."""
    candidate_story = require_mapping_value(candidate, "story", "candidate_fingerprint")
    existing_story = require_mapping_value(existing, "story", "existing_fingerprint")
    numeric_weights = {
        field: float(weight)
        for field, weight in weights.items()
        if isinstance(weight, int | float) and weight > 0
    }
    if not numeric_weights:
        raise ConfigurationError("Novelty Weight가 하나 이상 필요합니다.")
    total_weight = sum(numeric_weights.values())
    matched_weight = sum(
        weight
        for field, weight in numeric_weights.items()
        if has_comparable_value(normalized_value(candidate_story.get(field)))
        and has_comparable_value(normalized_value(existing_story.get(field)))
        and normalized_value(candidate_story.get(field))
        == normalized_value(existing_story.get(field))
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


def threshold_value(thresholds: Mapping[str, object], key: str) -> float:
    """Novelty Threshold 숫자를 읽는다."""
    similarity = require_mapping_value(thresholds, "similarity", "novelty_thresholds")
    value = similarity.get(key)
    if not isinstance(value, int | float):
        raise ConfigurationError(f"Novelty Threshold가 숫자가 아닙니다: field={key}")
    return float(value)


def evaluate_novelty(
    candidate: Mapping[str, object],
    history: Sequence[Mapping[str, object]],
    thresholds: Mapping[str, object],
) -> dict[str, object]:
    """최근성과 전체 유사도, Causal Hard Collision을 통합 판정한다."""
    weights = require_mapping_value(thresholds, "weights", "novelty_thresholds")
    comparisons: list[dict[str, object]] = []
    issues: list[ValidationIssue] = []
    history_count = len(history)
    for index, existing in enumerate(history):
        score = similarity_score(candidate, existing, weights)
        distance_from_latest = history_count - index
        threshold_key = (
            "recent_5_max"
            if distance_from_latest <= 5
            else "recent_10_max"
            if distance_from_latest <= 10
            else "overall_max"
        )
        maximum = threshold_value(thresholds, threshold_key)
        hard_collision = causal_hard_collision(candidate, existing)
        project_id = existing.get("project_id", "")
        comparisons.append(
            {
                "project_id": project_id,
                "similarity": score,
                "threshold": maximum,
                "causal_hard_collision": hard_collision,
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
        "issues": issues,
    }


def variation_precheck_source_hash(
    candidates_document: Mapping[str, object],
) -> str:
    """후보 선택과 승인 ID만 포함한 Novelty Precheck 입력 Hash를 계산한다."""
    candidates = candidates_document.get("candidates")
    if not isinstance(candidates, list) or not all(
        isinstance(candidate, Mapping) for candidate in candidates
    ):
        raise ConfigurationError("variation_candidates.candidates 객체 배열이 필요합니다.")
    payload = {
        "project_id": candidates_document.get("project_id"),
        "approved_candidate_id": candidates_document.get("approved_candidate_id"),
        "candidates": [
            {
                "candidate_id": candidate.get("candidate_id"),
                "selection": candidate.get("selection"),
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
    """승인 Variation을 Story History와 비교해 Story 설계 전 중복을 차단한다."""
    candidates = candidates_document.get("candidates")
    approved_id = candidates_document.get("approved_candidate_id")
    if not isinstance(candidates, list) or not all(
        isinstance(candidate, Mapping) for candidate in candidates
    ):
        raise ConfigurationError("variation_candidates.candidates 객체 배열이 필요합니다.")
    if not isinstance(approved_id, str):
        raise ConfigurationError("Novelty Precheck 전에 Variation 승인이 필요합니다.")

    weights = require_mapping_value(thresholds, "weights", "novelty_thresholds")
    history_count = len(history)
    candidate_results: list[dict[str, object]] = []
    issues: list[ValidationIssue] = []
    for candidate in candidates:
        candidate_id = candidate.get("candidate_id")
        selection = candidate.get("selection")
        if not isinstance(candidate_id, str) or not isinstance(selection, Mapping):
            raise ConfigurationError("Variation Candidate ID와 selection 객체가 필요합니다.")
        comparisons: list[dict[str, object]] = []
        for index, existing in enumerate(history):
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
            comparisons.append(
                {
                    "project_id": existing.get("project_id", ""),
                    "similarity": score,
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
        if candidate_id == approved_id and collisions:
            issues.append(
                make_novelty_issue(
                    "APPROVED_VARIATION_SIMILARITY_EXCEEDED",
                    "승인 Variation이 Story 설계 전 유사도 기준을 넘었습니다.",
                    {
                        "candidate_id": candidate_id,
                        "collision_count": len(collisions),
                    },
                )
            )

    approved_result = next(
        (
            result
            for result in candidate_results
            if result["candidate_id"] == approved_id
        ),
        None,
    )
    if approved_result is None:
        raise ConfigurationError(
            f"승인 Variation이 후보 결과에 없습니다: candidate_id={approved_id}"
        )
    return {
        "project_id": candidates_document.get("project_id", ""),
        "source_hash": variation_precheck_source_hash(candidates_document),
        "approved_candidate_id": approved_id,
        "result": approved_result["result"],
        "candidate_results": candidate_results,
        "issues": issues,
    }
