"""최종 방송 대본과 Production Package의 Editorial Review 계약."""

import json
import re
from collections.abc import Mapping, Sequence
from copy import deepcopy
from hashlib import sha256
from math import isfinite
from typing import cast

from VALIDATORS.crime_event import explicit_crime_policy, required_semantic_subjects
from VALIDATORS.exceptions import ConfigurationError, StateTransitionError
from VALIDATORS.models import ProjectState, ValidationIssue
from VALIDATORS.presentation_validation import parse_script_segments, presentation_segments
from VALIDATORS.scene_realization import capability_policy, realization_policy

EDITORIAL_CHECKS = (
    "broadcast_format",
    "absolute_time",
    "dialogue_naturalness",
    "panel_reaction_function",
    "audience_belief",
    "shootability",
    "victim_dignity",
)
EDITORIAL_REVIEWED_ARTIFACTS = (
    "broadcast_readable_config",
    "psychological_arc",
    "character_state_transitions",
    "crime_event_contract",
    "scene_cards",
    "final_script",
    "screenplay_units",
    "broadcast_readable_script",
    "broadcast_readable_report",
    "reenactment_character_script",
    "reenactment_export_report",
    "script_realization_report",
    "actual_timeline",
    "viewer_timeline",
    "audience_belief",
    "panel_cast",
    "reaction_segments",
    "expert_segments",
    "presentation_plan",
    "panel_reaction_script",
    "expert_analysis_script",
    "production_footprint",
    "shooting_script",
    "production_manifest",
    "narration",
    "production_panel_reaction_script",
    "production_expert_analysis_script",
    "subtitle_script",
    "edit_script",
    "production_reenactment_character_script",
    "production_broadcast_readable_script",
)
PANEL_DIALOGUE_LINE = re.compile(
    r"^\[(?P<panelist_id>PANEL-[0-9]{2,})(?:\s*·[^\]]+)?\]\s*"
    r"[“\"]?(?P<speech>.*?)[”\"]?\s*$"
)
SPOKEN_WORD = re.compile(r"[0-9A-Za-z가-힣]+(?:['\u2019][0-9A-Za-z가-힣]+)?")
EVIDENCE_SELECTOR_FIELDS = {
    "SEGMENT_ID": "segment_id",
    "REACTION_SEGMENT_ID": "reaction_segment_id",
    "SCENE_ID": "scene_id",
    "PSYCHOLOGICAL_STAGE_ID": "stage_id",
    "EVENT_ID": "event_id",
    "FACT_ID": "fact_id",
    "CLUE_ID": "clue_id",
    "REVEAL_TARGET_ID": "reveal_target_id",
    "UNIT_ID": "unit_id",
}


def make_editorial_issue(
    code: str,
    message: str,
    context: dict[str, object],
) -> ValidationIssue:
    """Editorial Review 문제를 공통 Issue 형식으로 생성한다."""
    return ValidationIssue(
        severity="ERROR",
        code=code,
        message=message,
        artifact="08_QA/editorial_review.json",
        context=context,
    )


def encoded_review_artifact(content: object) -> bytes:
    """Review 입력 Hash에 사용할 형식 독립 Canonical Byte를 반환한다."""
    if isinstance(content, Mapping):
        return json.dumps(
            dict(content),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    if isinstance(content, str):
        return content.encode("utf-8")
    raise TypeError(
        "Editorial Review 입력은 JSON 객체 또는 문자열이어야 합니다: "
        f"actual_type={type(content).__name__}"
    )


def editorial_artifact_hashes(
    artifacts: Mapping[str, object],
) -> dict[str, str]:
    """Editorial Critic이 실제로 검토해야 하는 입력 Hash를 계산한다."""
    hashes: dict[str, str] = {}
    for artifact_name in EDITORIAL_REVIEWED_ARTIFACTS:
        if artifact_name not in artifacts:
            continue
        hashes[artifact_name] = sha256(
            encoded_review_artifact(artifacts[artifact_name])
        ).hexdigest()
    readable_report = artifacts.get("broadcast_readable_report")
    if isinstance(readable_report, Mapping) and readable_report.get("schema_version") in {
        "2.0.0",
        "2.1.0",
    }:
        profile_binding = readable_report.get("output_profile_binding")
        profile_hash = (
            profile_binding.get("file_sha256") if isinstance(profile_binding, Mapping) else None
        )
        if isinstance(profile_hash, str):
            hashes["broadcast_readable_output_profile"] = profile_hash
    return hashes


def json_selector_matches(
    value: object,
    field: str,
    selector_id: str,
) -> list[Mapping[str, object]]:
    """JSON Tree에서 지정 ID를 소유한 객체를 찾는다."""
    if isinstance(value, Mapping):
        if value.get(field) == selector_id:
            return [value]
        return [
            match
            for child in value.values()
            for match in json_selector_matches(child, field, selector_id)
        ]
    if isinstance(value, list):
        return [
            match for child in value for match in json_selector_matches(child, field, selector_id)
        ]
    return []


def resolve_editorial_excerpt(
    artifact_name: str,
    artifact: object,
    selector_type: str,
    selector_id: str,
) -> object | None:
    """Editorial Evidence Selector를 실제 Artifact 일부로 해석한다."""
    if selector_type == "DOCUMENT":
        return artifact if selector_id == artifact_name else None
    field = EVIDENCE_SELECTOR_FIELDS.get(selector_type)
    if field is None:
        return None
    if isinstance(artifact, str):
        if selector_type != "SEGMENT_ID":
            return None
        segments, malformed = parse_script_segments(artifact)
        if malformed:
            return None
        script_matches = [segment for segment in segments if segment["segment_id"] == selector_id]
        return script_matches[0] if len(script_matches) == 1 else None
    if isinstance(artifact, Mapping):
        json_matches = json_selector_matches(artifact, field, selector_id)
        return json_matches[0] if len(json_matches) == 1 else None
    return None


def editorial_excerpt_hash(excerpt: object) -> str:
    """Editorial Evidence Excerpt의 Canonical SHA-256을 계산한다."""
    return sha256(encoded_review_artifact(excerpt)).hexdigest()


def make_editorial_evidence(
    artifacts: Mapping[str, object],
    artifact_name: str,
    selector_type: str,
    selector_id: str,
) -> dict[str, str]:
    """실제로 해석 가능한 Editorial Evidence Reference를 생성한다."""
    artifact = artifacts.get(artifact_name)
    if artifact is None:
        raise ConfigurationError(
            f"Editorial Evidence Artifact가 없습니다: artifact={artifact_name}"
        )
    excerpt = resolve_editorial_excerpt(
        artifact_name,
        artifact,
        selector_type,
        selector_id,
    )
    if excerpt is None:
        raise ConfigurationError(
            "Editorial Evidence Selector를 해석할 수 없습니다: "
            f"artifact={artifact_name}, selector_type={selector_type}, "
            f"selector_id={selector_id}"
        )
    return {
        "artifact": artifact_name,
        "selector_type": selector_type,
        "selector_id": selector_id,
        "excerpt_hash": editorial_excerpt_hash(excerpt),
    }


def editorial_evidence_issues(
    evidence: Sequence[object],
    artifacts: Mapping[str, object],
    check_name: str,
) -> list[ValidationIssue]:
    """Editorial Evidence의 Artifact, Selector, Excerpt Hash를 검증한다."""
    issues: list[ValidationIssue] = []
    for index, raw_reference in enumerate(evidence):
        context = {"check": check_name, "evidence_index": index}
        if not isinstance(raw_reference, Mapping):
            issues.append(
                make_editorial_issue(
                    "EDITORIAL_EVIDENCE_SELECTOR_NOT_FOUND",
                    "Editorial Evidence가 구조화된 Selector Reference가 아닙니다.",
                    context,
                )
            )
            continue
        artifact_name = raw_reference.get("artifact")
        selector_type = raw_reference.get("selector_type")
        selector_id = raw_reference.get("selector_id")
        excerpt_hash = raw_reference.get("excerpt_hash")
        if not isinstance(artifact_name, str) or artifact_name not in artifacts:
            issues.append(
                make_editorial_issue(
                    "EDITORIAL_EVIDENCE_ARTIFACT_UNKNOWN",
                    "Editorial Evidence가 검토 대상이 아닌 Artifact를 참조합니다.",
                    {**context, "artifact": artifact_name},
                )
            )
            continue
        if not isinstance(selector_type, str) or not isinstance(selector_id, str):
            issues.append(
                make_editorial_issue(
                    "EDITORIAL_EVIDENCE_SELECTOR_NOT_FOUND",
                    "Editorial Evidence Selector 형식이 완전하지 않습니다.",
                    context,
                )
            )
            continue
        excerpt = resolve_editorial_excerpt(
            artifact_name,
            artifacts[artifact_name],
            selector_type,
            selector_id,
        )
        if excerpt is None:
            issues.append(
                make_editorial_issue(
                    "EDITORIAL_EVIDENCE_SELECTOR_NOT_FOUND",
                    "Editorial Evidence Selector가 Artifact에서 해석되지 않습니다.",
                    {
                        **context,
                        "artifact": artifact_name,
                        "selector_type": selector_type,
                        "selector_id": selector_id,
                    },
                )
            )
            continue
        expected_hash = editorial_excerpt_hash(excerpt)
        if excerpt_hash != expected_hash:
            issues.append(
                make_editorial_issue(
                    "EDITORIAL_EVIDENCE_HASH_MISMATCH",
                    "Editorial Evidence Excerpt Hash가 현재 Artifact와 다릅니다.",
                    {
                        **context,
                        "artifact": artifact_name,
                        "selector_id": selector_id,
                        "expected": expected_hash,
                        "actual": excerpt_hash,
                    },
                )
            )
    return issues


def panel_spoken_metrics(panel_reaction_script: str) -> dict[str, dict[str, object]]:
    """Panel Segment별 방송 발화 단어 수와 실제 화자 집합을 계산한다."""
    metrics: dict[str, dict[str, object]] = {}
    parsed_segments, malformed = parse_script_segments(panel_reaction_script)
    if malformed:
        return metrics
    for segment in parsed_segments:
        speaker_ids: set[str] = set()
        spoken_words = 0
        for raw_line in segment["body"].splitlines():
            match = PANEL_DIALOGUE_LINE.fullmatch(raw_line.strip())
            if match is None:
                continue
            speaker_ids.add(match.group("panelist_id"))
            spoken_words += len(SPOKEN_WORD.findall(match.group("speech")))
        metrics[segment["segment_id"]] = {
            "speaker_ids": sorted(speaker_ids),
            "spoken_word_count": spoken_words,
        }
    return metrics


def mapping_records(document: Mapping[str, object], key: str) -> list[Mapping[str, object]]:
    """Editorial Review의 객체 배열을 안전하게 읽는다."""
    value = document.get(key)
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, Mapping)]


def string_values(value: object) -> list[str]:
    """문자열 배열 값만 반환한다."""
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, str)]


def numeric_value(value: object) -> float | None:
    """Boolean을 제외한 유한한 0 이상 시간값을 실수로 정규화한다."""
    if (
        not isinstance(value, int | float)
        or isinstance(value, bool)
        or not isfinite(value)
        or value < 0
    ):
        return None
    return float(value)


def positive_numeric_value(value: object) -> float | None:
    """Boolean과 비유한 값과 0을 제외한 양의 시간값을 반환한다."""
    normalized = numeric_value(value)
    return normalized if normalized is not None and normalized > 0 else None


def runtime_evidence_issues(
    review: Mapping[str, object],
    presentation_plan: Mapping[str, object],
    panel_reaction_script: str,
) -> list[ValidationIssue]:
    """계획시간을 발화 예상시간과 비발화 편집 요소로 완전히 설명하는지 검사한다."""
    evidence = review.get("runtime_evidence")
    if not isinstance(evidence, Mapping):
        return [
            make_editorial_issue(
                "EDITORIAL_RUNTIME_EVIDENCE_INVALID",
                "Editorial Review에 Runtime 측정 근거가 필요합니다.",
                {},
            )
        ]
    method = evidence.get("method")
    reading_rate = numeric_value(evidence.get("reading_rate_wpm"))
    raw_segments = mapping_records(evidence, "panel_segments")
    invalid_method_fields: list[dict[str, object]] = []
    if method == "WORD_COUNT_ESTIMATE":
        if (
            positive_numeric_value(evidence.get("estimated_panel_spoken_duration_sec")) is None
            or evidence.get("measured_panel_duration_sec") is not None
        ):
            invalid_method_fields.append({"scope": "aggregate"})
        invalid_method_fields.extend(
            {"scope": "segment", "segment_id": segment.get("segment_id")}
            for segment in raw_segments
            if positive_numeric_value(segment.get("estimated_spoken_duration_sec")) is None
            or segment.get("measured_duration_sec") is not None
        )
    elif method in {"TABLE_READ", "RECORDED_AUDIO"}:
        if (
            evidence.get("estimated_panel_spoken_duration_sec") is not None
            or positive_numeric_value(evidence.get("measured_panel_duration_sec")) is None
        ):
            invalid_method_fields.append({"scope": "aggregate"})
        invalid_method_fields.extend(
            {"scope": "segment", "segment_id": segment.get("segment_id")}
            for segment in raw_segments
            if segment.get("estimated_spoken_duration_sec") is not None
            or positive_numeric_value(segment.get("measured_duration_sec")) is None
        )
    evidence_by_id = {
        cast(str, item.get("segment_id")): item
        for item in raw_segments
        if isinstance(item.get("segment_id"), str)
    }
    planned_panel_segments = [
        segment
        for segment in presentation_segments(presentation_plan)
        if segment.get("segment_type") == "PANEL_REACTION"
    ]
    planned_ids = {
        cast(str, segment.get("segment_id"))
        for segment in planned_panel_segments
        if isinstance(segment.get("segment_id"), str)
    }
    missing_ids = sorted(planned_ids - set(evidence_by_id))
    unexpected_ids = sorted(set(evidence_by_id) - planned_ids)
    issues: list[ValidationIssue] = []
    if invalid_method_fields:
        issues.append(
            make_editorial_issue(
                "EDITORIAL_RUNTIME_METHOD_FIELDS_INVALID",
                "Runtime 방법별 추정값과 실측값은 서로 배타적이어야 합니다.",
                {"method": method, "invalid_fields": invalid_method_fields},
            )
        )
    if missing_ids or unexpected_ids:
        issues.append(
            make_editorial_issue(
                "EDITORIAL_PANEL_SEGMENT_COVERAGE_MISMATCH",
                "Runtime 근거가 모든 Panel Segment와 정확히 대응해야 합니다.",
                {"missing_segment_ids": missing_ids, "unexpected_segment_ids": unexpected_ids},
            )
        )
    spoken_metrics = panel_spoken_metrics(panel_reaction_script)
    planned_panel_duration = 0.0
    estimated_panel_spoken_duration = 0.0
    measured_panel_duration = 0.0
    measured_values_present = True
    for plan_segment in planned_panel_segments:
        segment_id = plan_segment.get("segment_id")
        if not isinstance(segment_id, str):
            continue
        record = evidence_by_id.get(segment_id)
        if record is None:
            continue
        planned_duration = numeric_value(plan_segment.get("duration_sec"))
        recorded_planned_duration = numeric_value(record.get("planned_duration_sec"))
        estimated_duration = numeric_value(record.get("estimated_spoken_duration_sec"))
        measured_duration = numeric_value(record.get("measured_duration_sec"))
        raw_word_count = record.get("spoken_word_count")
        raw_speaker_ids = record.get("speaker_ids")
        speaker_ids = (
            sorted(item for item in raw_speaker_ids if isinstance(item, str))
            if isinstance(raw_speaker_ids, list)
            else []
        )
        actual_metrics = spoken_metrics.get(segment_id, {})
        actual_word_count = actual_metrics.get("spoken_word_count")
        actual_speaker_ids = actual_metrics.get("speaker_ids")
        if raw_word_count != actual_word_count:
            issues.append(
                make_editorial_issue(
                    "EDITORIAL_PANEL_WORD_COUNT_MISMATCH",
                    "Runtime 근거의 발화 단어 수가 Panel Script와 다릅니다.",
                    {
                        "segment_id": segment_id,
                        "expected": actual_word_count,
                        "actual": raw_word_count,
                    },
                )
            )
        if speaker_ids != actual_speaker_ids:
            issues.append(
                make_editorial_issue(
                    "EDITORIAL_PANEL_SPEAKER_MISMATCH",
                    "Runtime 근거의 화자 목록이 Panel Script와 다릅니다.",
                    {
                        "segment_id": segment_id,
                        "expected": actual_speaker_ids,
                        "actual": speaker_ids,
                    },
                )
            )
        if (
            method == "WORD_COUNT_ESTIMATE"
            and reading_rate is not None
            and isinstance(actual_word_count, int)
            and estimated_duration is not None
        ):
            expected_estimate = round(actual_word_count * 60.0 / reading_rate, 2)
            if abs(expected_estimate - estimated_duration) > 0.01:
                issues.append(
                    make_editorial_issue(
                        "EDITORIAL_PANEL_ESTIMATE_MISMATCH",
                        "단어 수 기반 예상시간 계산이 발화 속도와 일치하지 않습니다.",
                        {
                            "segment_id": segment_id,
                            "expected": expected_estimate,
                            "actual": estimated_duration,
                        },
                    )
                )
        if (
            planned_duration is None
            or recorded_planned_duration is None
            or abs(planned_duration - recorded_planned_duration) > 0.01
        ):
            issues.append(
                make_editorial_issue(
                    "EDITORIAL_PANEL_PLANNED_DURATION_MISMATCH",
                    "Runtime 근거의 계획시간이 Presentation Plan과 다릅니다.",
                    {
                        "segment_id": segment_id,
                        "expected": planned_duration,
                        "actual": recorded_planned_duration,
                    },
                )
            )
            continue
        non_speech_duration = sum(
            duration
            for item in mapping_records(record, "non_speech_elements")
            if (duration := numeric_value(item.get("duration_sec"))) is not None
        )
        spoken_duration = (
            measured_duration if method in {"TABLE_READ", "RECORDED_AUDIO"} else estimated_duration
        )
        timing_gap = (
            None
            if spoken_duration is None
            else abs(spoken_duration + non_speech_duration - planned_duration)
        )
        if timing_gap is None or timing_gap > 0.25:
            issues.append(
                make_editorial_issue(
                    "EDITORIAL_PANEL_TIMING_GAP",
                    "Panel Segment의 발화와 비발화 요소가 계획시간을 채우지 못합니다.",
                    {
                        "segment_id": segment_id,
                        "planned_duration_sec": planned_duration,
                        "spoken_duration_sec": spoken_duration,
                        "non_speech_duration_sec": non_speech_duration,
                    },
                )
            )
        planned_panel_duration += planned_duration
        estimated_panel_spoken_duration += estimated_duration or 0.0
        if measured_duration is None:
            measured_values_present = False
        else:
            measured_panel_duration += measured_duration
    planned_total = sum(
        duration
        for segment in presentation_segments(presentation_plan)
        if (duration := numeric_value(segment.get("duration_sec"))) is not None
    )
    aggregate_values = {
        "planned_runtime_sec": (planned_total, numeric_value(evidence.get("planned_runtime_sec"))),
        "planned_panel_duration_sec": (
            planned_panel_duration,
            numeric_value(evidence.get("planned_panel_duration_sec")),
        ),
    }
    if method == "WORD_COUNT_ESTIMATE":
        aggregate_values["estimated_panel_spoken_duration_sec"] = (
            round(estimated_panel_spoken_duration, 2),
            numeric_value(evidence.get("estimated_panel_spoken_duration_sec")),
        )
    aggregate_mismatches = {
        field: {"expected": expected, "actual": actual}
        for field, (expected, actual) in aggregate_values.items()
        if actual is None or abs(expected - actual) > 0.01
    }
    if method in {"TABLE_READ", "RECORDED_AUDIO"}:
        reported_measured = numeric_value(evidence.get("measured_panel_duration_sec"))
        if (
            not measured_values_present
            or reported_measured is None
            or abs(measured_panel_duration - reported_measured) > 0.01
        ):
            aggregate_mismatches["measured_panel_duration_sec"] = {
                "expected": measured_panel_duration,
                "actual": reported_measured,
            }
    if aggregate_mismatches:
        issues.append(
            make_editorial_issue(
                "EDITORIAL_RUNTIME_AGGREGATE_MISMATCH",
                "Runtime 근거의 합계가 Segment별 값과 다릅니다.",
                {"mismatches": aggregate_mismatches},
            )
        )
    return issues


def explicit_crime_runtime_evidence_issues(
    channel: Mapping[str, object],
    review: Mapping[str, object],
) -> list[ValidationIssue]:
    """사건 중심 Channel의 한국어 발화·행동·비발화 시간 근거를 검사한다."""
    if explicit_crime_policy(channel) is None:
        return []
    evidence = review.get("runtime_evidence")
    if not isinstance(evidence, Mapping):
        return [
            make_editorial_issue(
                "CRIME_RUNTIME_EVIDENCE_MISSING",
                "사건 중심 Editorial Review에는 Runtime Evidence가 필요합니다.",
                {},
            )
        ]
    reaction_policy = capability_policy(channel, "REACTION_POLICY") or {}
    minimum_density = numeric_value(reaction_policy.get("minimum_spoken_density"))
    minimum_density = minimum_density if minimum_density is not None else 0.4
    maximum_non_speech = numeric_value(reaction_policy.get("maximum_non_speech_ratio"))
    maximum_non_speech = maximum_non_speech if maximum_non_speech is not None else 0.6
    assumptions = evidence.get("estimation_assumptions")
    issues: list[ValidationIssue] = []
    if (
        evidence.get("language_unit") != "KOREAN_EOJEOL"
        or not isinstance(assumptions, list)
        or not assumptions
        or not all(isinstance(item, str) and item.strip() for item in assumptions)
    ):
        issues.append(
            make_editorial_issue(
                "CRIME_RUNTIME_ESTIMATION_BASIS_INVALID",
                "한국어 어절 기준과 명시적인 시간 추정 가정이 필요합니다.",
                {},
            )
        )
    for record in mapping_records(evidence, "panel_segments"):
        segment_id = record.get("segment_id")
        planned_duration = numeric_value(record.get("planned_duration_sec"))
        method = evidence.get("method")
        spoken_duration = numeric_value(
            record.get("measured_duration_sec")
            if method in {"TABLE_READ", "RECORDED_AUDIO"}
            else record.get("estimated_spoken_duration_sec")
        )
        action_total = 0.0
        non_speaking_total = 0.0
        invalid_elements: list[int] = []
        unsupported_elements: list[int] = []
        for index, element in enumerate(mapping_records(record, "non_speech_elements")):
            duration = numeric_value(element.get("duration_sec"))
            time_class = element.get("time_class")
            support_status = element.get("support_status")
            source_reference = element.get("source_reference")
            if (
                duration is None
                or time_class not in {"ACTION", "NON_SPEAKING"}
                or support_status not in {"SUPPORTED", "UNSUPPORTED"}
                or not isinstance(source_reference, str)
                or not source_reference.strip()
            ):
                invalid_elements.append(index)
                continue
            if time_class == "ACTION":
                action_total += duration
            else:
                non_speaking_total += duration
            if support_status == "UNSUPPORTED":
                unsupported_elements.append(index)
        declared_action = numeric_value(record.get("action_duration_sec"))
        declared_non_speaking = numeric_value(record.get("non_speaking_duration_sec"))
        if (
            invalid_elements
            or declared_action is None
            or declared_non_speaking is None
            or abs(declared_action - action_total) > 0.01
            or abs(declared_non_speaking - non_speaking_total) > 0.01
        ):
            issues.append(
                make_editorial_issue(
                    "CRIME_RUNTIME_CLASSIFICATION_INVALID",
                    "행동 시간과 비발화 시간은 근거 요소의 분류별 합계와 일치해야 합니다.",
                    {
                        "segment_id": segment_id,
                        "invalid_element_indexes": invalid_elements,
                        "expected_action_duration_sec": action_total,
                        "expected_non_speaking_duration_sec": non_speaking_total,
                    },
                )
            )
        if unsupported_elements:
            issues.append(
                make_editorial_issue(
                    "CRIME_RUNTIME_SOURCE_UNSUPPORTED",
                    "Graphic·행동·비발화 시간은 실제 Script 또는 편집 근거로 뒷받침되어야 합니다.",
                    {
                        "segment_id": segment_id,
                        "unsupported_element_indexes": unsupported_elements,
                    },
                )
            )
        if planned_duration is not None and planned_duration > 0 and spoken_duration is not None:
            spoken_density = spoken_duration / planned_duration
            if spoken_density < minimum_density:
                issues.append(
                    make_editorial_issue(
                        "PANEL_SPOKEN_DENSITY_LOW",
                        "Panel 실측 또는 예상 발화 밀도가 Channel 기준보다 낮습니다.",
                        {
                            "segment_id": segment_id,
                            "spoken_density": spoken_density,
                            "minimum": minimum_density,
                        },
                    )
                )
        if planned_duration is not None and planned_duration > 0:
            non_speech_ratio = non_speaking_total / planned_duration
            if non_speech_ratio > maximum_non_speech:
                issues.append(
                    make_editorial_issue(
                        "PANEL_NON_SPEECH_RATIO_HIGH",
                        "Panel의 Graphic·침묵·Hold 비율이 Channel 상한을 초과했습니다.",
                        {
                            "segment_id": segment_id,
                            "non_speech_ratio": non_speech_ratio,
                            "maximum": maximum_non_speech,
                        },
                    )
                )
            filler_duration = sum(
                duration
                for element in mapping_records(record, "non_speech_elements")
                if element.get("element_type") in {"GRAPHIC", "REACTION_HOLD", "REPLAY"}
                and (duration := numeric_value(element.get("duration_sec"))) is not None
            )
            if filler_duration / planned_duration > maximum_non_speech:
                issues.append(
                    make_editorial_issue(
                        "PANEL_FILLER_TIME_EXCESSIVE",
                        "Graphic·Hold·Replay로 Panel 시간을 인위적으로 채울 수 없습니다.",
                        {
                            "segment_id": segment_id,
                            "filler_ratio": filler_duration / planned_duration,
                            "maximum": maximum_non_speech,
                        },
                    )
                )
    return issues


def validate_editorial_crime_assessments(
    channel: Mapping[str, object],
    review: Mapping[str, object],
    contract: Mapping[str, object],
    reviewed_artifacts: Mapping[str, object],
) -> list[ValidationIssue]:
    """CORE 근거를 실제 의미 충족으로 승격하는 Editorial 평가를 검사한다."""
    if explicit_crime_policy(channel) is None:
        return []
    expected = required_semantic_subjects(channel, contract)
    assessments = mapping_records(review, "semantic_assessments")
    observed = [(str(item.get("category")), str(item.get("subject_id"))) for item in assessments]
    missing = sorted(expected - set(observed))
    duplicates = sorted({subject for subject in observed if observed.count(subject) > 1})
    issues: list[ValidationIssue] = []
    if missing or duplicates or len(observed) != len(expected):
        issues.append(
            make_editorial_issue(
                "CRIME_SEMANTIC_ASSESSMENT_COVERAGE_INVALID",
                "사건·Narration·Panel·Reveal·단서 의미 평가는 대상별로 정확히 하나 필요합니다.",
                {"missing": missing, "duplicates": duplicates, "observed": observed},
            )
        )
    for assessment in assessments:
        subject = (str(assessment.get("category")), str(assessment.get("subject_id")))
        evidence = assessment.get("evidence")
        notes = assessment.get("notes")
        is_disclosure_scan = subject[0] == "PREMATURE_DISCLOSURE_SCAN"
        acceptable_statuses = (
            {"NOT_DISCLOSED", "INTENTIONAL_PREREVEAL"} if is_disclosure_scan else {"EVIDENCED"}
        )
        if (
            subject not in expected
            or assessment.get("status") not in acceptable_statuses
            or not isinstance(evidence, list)
            or not evidence
            or not isinstance(notes, str)
            or not notes.strip()
        ):
            issues.append(
                make_editorial_issue(
                    (
                        "PREMATURE_DISCLOSURE_SCAN_FAILED"
                        if is_disclosure_scan
                        else "CRIME_SEMANTIC_ASSESSMENT_NOT_EVIDENCED"
                    ),
                    "각 의미 평가는 허용된 판정과 실제 발췌 근거가 필요합니다.",
                    {"subject": subject, "status": assessment.get("status")},
                )
            )
            continue
        issues.extend(editorial_evidence_issues(evidence, reviewed_artifacts, ":".join(subject)))
        if is_disclosure_scan and assessment.get("status") == "INTENTIONAL_PREREVEAL":
            presentation = reviewed_artifacts.get("presentation_plan")
            viewer = reviewed_artifacts.get("viewer_timeline")
            evidence_segment_ids = {
                str(item.get("selector_id"))
                for item in evidence
                if isinstance(item, Mapping)
                and item.get("artifact") == "final_script"
                and item.get("selector_type") == "SEGMENT_ID"
            }
            planned_segment_ids = {
                str(segment.get("segment_id"))
                for segment in (
                    presentation_segments(presentation) if isinstance(presentation, Mapping) else []
                )
                if subject[1] in set(string_values(segment.get("intentional_prereveal_ids")))
            }
            viewer_recorded = any(
                reveal.get("reveal_target_id") == subject[1]
                and reveal.get("intentional_prereveal") is True
                for reveal in (
                    mapping_records(viewer, "reveals") if isinstance(viewer, Mapping) else []
                )
            )
            if not evidence_segment_ids.intersection(planned_segment_ids) or not viewer_recorded:
                issues.append(
                    make_editorial_issue(
                        "PREMATURE_DISCLOSURE_SCAN_FAILED",
                        "Intentional Prereveal은 Presentation과 Viewer Timeline에 "
                        "모두 계획돼야 합니다.",
                        {"reveal_target_id": subject[1]},
                    )
                )
    return issues


def validate_editorial_review(
    review: Mapping[str, object],
    project_id: str,
    expected_artifact_hashes: Mapping[str, str],
    reviewed_artifacts: Mapping[str, object],
) -> list[ValidationIssue]:
    """완료된 Editorial Review의 판정과 Issue 정합성을 검사한다."""
    issues: list[ValidationIssue] = []
    if review.get("project_id") != project_id:
        issues.append(
            make_editorial_issue(
                "EDITORIAL_PROJECT_ID_MISMATCH",
                "Editorial Review의 Project ID가 현재 Project와 다릅니다.",
                {"expected": project_id, "actual": review.get("project_id")},
            )
        )
    checks = review.get("checks")
    failed_checks = (
        list(EDITORIAL_CHECKS)
        if not isinstance(checks, Mapping)
        else [
            name
            for name in EDITORIAL_CHECKS
            if not isinstance(checks.get(name), Mapping)
            or cast(Mapping[str, object], checks.get(name)).get("result") != "PASS"
        ]
    )
    raw_issues = review.get("issues")
    issue_count = len(raw_issues) if isinstance(raw_issues, list) else 1
    evidence_missing: list[str] = []
    if isinstance(checks, Mapping):
        for name in EDITORIAL_CHECKS:
            check = checks.get(name)
            if not isinstance(check, Mapping):
                evidence_missing.append(name)
                continue
            raw_evidence = check.get("evidence")
            notes = check.get("notes")
            if (
                not isinstance(raw_evidence, list)
                or not raw_evidence
                or not isinstance(notes, str)
                or not notes.strip()
            ):
                evidence_missing.append(name)
                continue
            issues.extend(editorial_evidence_issues(raw_evidence, reviewed_artifacts, name))
    if evidence_missing:
        issues.append(
            make_editorial_issue(
                "EDITORIAL_CHECK_EVIDENCE_MISSING",
                "PASS Editorial Check에는 장면·Segment 근거와 검토 Notes가 필요합니다.",
                {"checks": evidence_missing},
            )
        )
    raw_hashes = review.get("artifact_hashes")
    actual_hashes = (
        {str(key): str(value) for key, value in raw_hashes.items()}
        if isinstance(raw_hashes, Mapping)
        else {}
    )
    missing_hashes = sorted(set(expected_artifact_hashes) - set(actual_hashes))
    unexpected_hashes = sorted(set(actual_hashes) - set(expected_artifact_hashes))
    mismatched_hashes = sorted(
        artifact_name
        for artifact_name, expected_hash in expected_artifact_hashes.items()
        if actual_hashes.get(artifact_name) != expected_hash
    )
    if missing_hashes or unexpected_hashes or mismatched_hashes:
        issues.append(
            make_editorial_issue(
                "EDITORIAL_ARTIFACT_HASH_MISMATCH",
                "Editorial Review가 현재 검토 대상 Artifact Hash와 결합되지 않았습니다.",
                {
                    "missing_artifacts": missing_hashes,
                    "unexpected_artifacts": unexpected_hashes,
                    "mismatched_artifacts": mismatched_hashes,
                },
            )
        )
    if review.get("result") != "PASS" or failed_checks or issue_count:
        issues.append(
            make_editorial_issue(
                "EDITORIAL_REVIEW_REQUIRED",
                "Editorial Review의 모든 항목이 PASS이고 Issue가 없어야 합니다.",
                {
                    "result": review.get("result"),
                    "failed_checks": failed_checks,
                    "issue_count": issue_count,
                },
            )
        )
    return issues


def validate_editorial_realization_evidence(
    channel: Mapping[str, object],
    review: Mapping[str, object],
    psychological_arc: Mapping[str, object],
) -> list[ValidationIssue]:
    """2.1 Editorial Review가 모든 심리 Stage의 독립 근거를 인용하는지 검사한다."""
    if realization_policy(channel) is None:
        return []
    expected_stage_ids = {
        cast(str, stage.get("stage_id"))
        for stage in mapping_records(psychological_arc, "stages")
        if isinstance(stage.get("stage_id"), str)
    }
    checks = review.get("checks")
    observed_stage_ids: set[str] = set()
    if isinstance(checks, Mapping):
        for check in checks.values():
            if not isinstance(check, Mapping):
                continue
            raw_evidence = check.get("evidence")
            if not isinstance(raw_evidence, list):
                continue
            observed_stage_ids.update(
                cast(str, reference.get("selector_id"))
                for reference in raw_evidence
                if isinstance(reference, Mapping)
                and reference.get("artifact") == "script_realization_report"
                and reference.get("selector_type") == "PSYCHOLOGICAL_STAGE_ID"
                and isinstance(reference.get("selector_id"), str)
            )
    missing_stage_ids = sorted(expected_stage_ids - observed_stage_ids)
    unexpected_stage_ids = sorted(observed_stage_ids - expected_stage_ids)
    if expected_stage_ids and not missing_stage_ids and not unexpected_stage_ids:
        return []
    return [
        make_editorial_issue(
            "EDITORIAL_REALIZATION_EVIDENCE_MISSING",
            "Editorial Review가 모든 심리 Stage의 Script 실현 근거를 인용해야 합니다.",
            {
                "missing_stage_ids": missing_stage_ids,
                "unexpected_stage_ids": unexpected_stage_ids,
            },
        )
    ]


def approve_editorial_review(
    state: ProjectState,
    review: Mapping[str, object],
    expected_artifact_hashes: Mapping[str, str],
    reviewed_artifacts: Mapping[str, object],
    actor: str,
    reason: str,
    updated_at: str,
) -> ProjectState:
    """완료된 Review와 준비 조건을 확인한 뒤 Editorial 승인 상태를 반환한다."""
    if not actor.strip() or not reason.strip():
        raise StateTransitionError("Editorial 승인에는 actor와 reason이 필요합니다.")
    if state["state"] != "EDITORIAL_REVIEW_REQUIRED":
        raise StateTransitionError(
            f"Editorial Review Required 상태에서만 승인할 수 있습니다: state={state['state']}"
        )
    readiness = state["readiness"]
    readiness_values: Mapping[str, object] = readiness
    required = {
        "artifact_status": "ARTIFACT_COMPLETE",
        "contract_status": "CONTRACT_VALIDATED",
        "process_status": "PROCESS_CONFORMANT",
    }
    mismatches = {
        field: {"expected": expected, "actual": readiness_values[field]}
        for field, expected in required.items()
        if readiness_values[field] != expected
    }
    if mismatches:
        raise StateTransitionError(
            f"Editorial 승인 전 준비 상태가 완전하지 않습니다: mismatches={mismatches}"
        )
    issues = validate_editorial_review(
        review,
        state["project_id"],
        expected_artifact_hashes,
        reviewed_artifacts,
    )
    if issues:
        raise StateTransitionError(
            f"Editorial Review Issue를 먼저 해결해야 합니다: issues={issues}"
        )
    next_state = deepcopy(state)
    next_state["state"] = "EDITORIAL_APPROVED"
    next_state["readiness"]["editorial_status"] = "EDITORIAL_APPROVED"
    next_state["updated_at"] = updated_at
    return next_state


def finalize_production_ready(
    state: ProjectState,
    review: Mapping[str, object],
    updated_at: str,
) -> ProjectState:
    """네 준비 조건이 모두 충족된 Project만 Production Ready로 전이한다."""
    if state["state"] != "EDITORIAL_APPROVED":
        raise StateTransitionError(
            "Editorial Approved 상태에서만 Production Ready로 전이할 수 있습니다: "
            f"state={state['state']}"
        )
    readiness = state["readiness"]
    readiness_values: Mapping[str, object] = readiness
    expected = {
        "artifact_status": "ARTIFACT_COMPLETE",
        "contract_status": "CONTRACT_VALIDATED",
        "process_status": "PROCESS_CONFORMANT",
        "editorial_status": "EDITORIAL_APPROVED",
    }
    mismatches = {
        field: {"expected": value, "actual": readiness_values[field]}
        for field, value in expected.items()
        if readiness_values[field] != value
    }
    if mismatches:
        raise StateTransitionError(
            f"Production Ready 조건이 충족되지 않았습니다: mismatches={mismatches}"
        )
    runtime_evidence = review.get("runtime_evidence")
    method = runtime_evidence.get("method") if isinstance(runtime_evidence, Mapping) else None
    segments = (
        mapping_records(runtime_evidence, "panel_segments")
        if isinstance(runtime_evidence, Mapping)
        else []
    )
    measured_total = (
        numeric_value(runtime_evidence.get("measured_panel_duration_sec"))
        if isinstance(runtime_evidence, Mapping)
        else None
    )
    missing_measured_segments = [
        segment.get("segment_id")
        for segment in segments
        if numeric_value(segment.get("measured_duration_sec")) is None
    ]
    if (
        method not in {"TABLE_READ", "RECORDED_AUDIO"}
        or measured_total is None
        or not segments
        or missing_measured_segments
    ):
        raise StateTransitionError(
            "Production Ready에는 TABLE_READ 또는 RECORDED_AUDIO 실측이 필요합니다: "
            f"method={method!r}, measured_total={measured_total!r}, "
            f"missing_segments={missing_measured_segments}"
        )
    reenactment_evidence = review.get("reenactment_runtime_evidence")
    if isinstance(reenactment_evidence, Mapping):
        reenactment_method = reenactment_evidence.get("method")
        reenactment_measured = numeric_value(reenactment_evidence.get("measured_duration_sec"))
        if (
            reenactment_method not in {"TABLE_READ", "RECORDED_AUDIO"}
            or reenactment_measured is None
        ):
            raise StateTransitionError(
                "Production Ready의 재연극 Runtime에는 TABLE_READ 또는 "
                "RECORDED_AUDIO 실측이 필요합니다: "
                f"method={reenactment_method!r}, measured={reenactment_measured!r}"
            )
    next_state = deepcopy(state)
    next_state["state"] = "PRODUCTION_READY"
    next_state["updated_at"] = updated_at
    return next_state
