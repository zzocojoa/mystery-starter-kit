"""Capability 기반 장면·Layer 실현 계약을 검증한다."""

import json
import re
from collections.abc import Mapping, Sequence
from hashlib import sha256
from typing import TypedDict, cast

from VALIDATORS.compatibility import parse_semantic_version
from VALIDATORS.exceptions import ConfigurationError
from VALIDATORS.models import ValidationIssue
from VALIDATORS.presentation_validation import (
    PANEL_HEADER,
    PANEL_SPOKEN_LINE,
    canonical_mode,
    parse_script_segments,
    presentation_segments,
)

REALIZATION_MINIMUM_VERSION = (2, 1, 0)
REQUIRED_STAGE_TYPES = (
    "TRUST_FORMATION",
    "EARLY_WARNING",
    "RATIONALIZATION",
    "BOUNDARY_EROSION",
    "CONTROL_OR_DEPENDENCY",
    "PSYCHOLOGICAL_CONSEQUENCE",
    "HARM_OR_CRIME",
    "RECOGNITION_AND_RESISTANCE",
    "AGENCY_RECOVERY",
)
REQUIRED_PANEL_FUNCTIONS = frozenset(
    {
        "EMOTIONAL_REACTION",
        "RISK_SIGNAL_RECOGNITION",
        "VICTIM_CONTEXTUALIZATION",
        "BELIEF_CORRECTION",
    }
)
HYPOTHESIS_FUNCTIONS = frozenset(
    {
        "ANOMALY_DETECTION",
        "HYPOTHESIS_GENERATION",
        "SUSPECT_DISCUSSION",
        "HYPOTHESIS_REVISION",
        "CONTRADICTION_DETECTION",
    }
)
SUBJECTIVE_NARRATION_FUNCTIONS = frozenset(
    {
        "SUBJECTIVE_EXPERIENCE",
        "EMOTIONAL_CONTINUITY",
        "MEMORY",
        "MISUNDERSTANDING",
        "SELF_DOUBT",
        "FEAR",
        "TIME_COMPRESSION",
        "RETROSPECTIVE_REFLECTION",
    }
)
ANALYSIS_NARRATION_FUNCTIONS = frozenset(
    {
        "CLUE_EXPLANATION",
        "EVIDENCE_WEIGHTING",
        "SOLUTION_EXPOSITION",
        "ANSWER_DIRECTIVE",
        "UNPLANNED_PREMATURE_REVEAL",
    }
)
STAGE_TAG = re.compile(r"\[PSY_STAGE:(PSTAGE-[0-9]{3,})\]")
TRACE_TAG = re.compile(r"\[PSY_TRACE:([A-Z][A-Z0-9_]*-[0-9]{2,})\]")
SPOKEN_TOKEN = re.compile(r"[0-9A-Za-z가-힣]+(?:['\u2019][0-9A-Za-z가-힣]+)?")
OBJECT_PUZZLE_VALUES = frozenset(
    {
        "OBJECT_LOCATION",
        "OBJECT_WHEREABOUTS",
        "WHERE_IS_OBJECT",
        "WHERE",
        "WHOSE",
    }
)


class RealizationInputs(TypedDict):
    """2.1 장면 실현 Validator가 소비하는 Artifact 묶음."""

    production_config: Mapping[str, object]
    story_dna: Mapping[str, object]
    case_input: Mapping[str, object]
    crime_psychology: Mapping[str, object]
    psychological_arc: Mapping[str, object]
    scene_cards: Mapping[str, object]
    presentation_plan: Mapping[str, object]
    reaction_segments: Mapping[str, object]
    final_script: str
    panel_reaction_script: str
    script_realization_report: Mapping[str, object]
    channel_consistency_report: Mapping[str, object]


def mapping_artifact(
    artifacts: Mapping[str, object],
    artifact_name: str,
) -> Mapping[str, object]:
    """Artifact 색인에서 JSON 객체를 읽는다."""
    value = artifacts.get(artifact_name)
    return value if isinstance(value, Mapping) else {}


def text_artifact(artifacts: Mapping[str, object], artifact_name: str) -> str:
    """Artifact 색인에서 텍스트를 읽는다."""
    value = artifacts.get(artifact_name)
    return value if isinstance(value, str) else ""


def build_realization_inputs(artifacts: Mapping[str, object]) -> RealizationInputs:
    """Project Artifact 색인에서 2.1 장면 실현 입력을 구성한다."""
    return RealizationInputs(
        production_config=mapping_artifact(artifacts, "production_config"),
        story_dna=mapping_artifact(artifacts, "story_dna"),
        case_input=mapping_artifact(artifacts, "case_input"),
        crime_psychology=mapping_artifact(artifacts, "crime_psychology"),
        psychological_arc=mapping_artifact(artifacts, "psychological_arc"),
        scene_cards=mapping_artifact(artifacts, "scene_cards"),
        presentation_plan=mapping_artifact(artifacts, "presentation_plan"),
        reaction_segments=mapping_artifact(artifacts, "reaction_segments"),
        final_script=text_artifact(artifacts, "final_script"),
        panel_reaction_script=text_artifact(artifacts, "panel_reaction_script"),
        script_realization_report=mapping_artifact(
            artifacts,
            "script_realization_report",
        ),
        channel_consistency_report=mapping_artifact(
            artifacts,
            "channel_consistency_report",
        ),
    )


def make_realization_issue(
    code: str,
    message: str,
    artifact: str,
    context: dict[str, object],
) -> ValidationIssue:
    """장면 실현 문제를 공통 Issue 형식으로 만든다."""
    return ValidationIssue(
        severity="ERROR",
        code=code,
        message=message,
        artifact=artifact,
        context=context,
    )


def mapping_items(document: Mapping[str, object], field: str) -> list[Mapping[str, object]]:
    """객체 배열 필드를 안전하게 읽는다."""
    value = document.get(field)
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, Mapping)]


def string_items(document: Mapping[str, object], field: str) -> list[str]:
    """문자열 배열 필드를 안전하게 읽는다."""
    value = document.get(field)
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, str)]


def number_value(value: object) -> float | None:
    """Boolean을 제외한 숫자를 실수로 읽는다."""
    if not isinstance(value, int | float) or isinstance(value, bool):
        return None
    return float(value)


def realization_policy(channel: Mapping[str, object]) -> Mapping[str, object] | None:
    """2.1 이상 Channel의 활성 SCENE_REALIZATION_POLICY를 반환한다."""
    version = channel.get("content_version")
    if not isinstance(version, str):
        return None
    if parse_semantic_version(version) < REALIZATION_MINIMUM_VERSION:
        return None
    capabilities = channel.get("capabilities")
    if not isinstance(capabilities, Mapping):
        return None
    policy = capabilities.get("SCENE_REALIZATION_POLICY")
    if not isinstance(policy, Mapping) or policy.get("enabled") is not True:
        return None
    return policy


def capability_policy(
    channel: Mapping[str, object],
    capability_id: str,
) -> Mapping[str, object] | None:
    """활성화된 Channel Capability 정책 객체를 반환한다."""
    capabilities = channel.get("capabilities")
    policy = capabilities.get(capability_id) if isinstance(capabilities, Mapping) else None
    if not isinstance(policy, Mapping) or policy.get("enabled") is not True:
        return None
    return policy


def story_payload(story_document: Mapping[str, object]) -> Mapping[str, object]:
    """Story DNA Wrapper와 직접 Payload를 모두 지원한다."""
    payload = story_document.get("story_dna")
    return payload if isinstance(payload, Mapping) else story_document


def validate_primary_story_engine(
    channel: Mapping[str, object],
    story_document: Mapping[str, object],
    case_input: Mapping[str, object],
) -> list[ValidationIssue]:
    """범죄 심리 진행이 2.1의 Primary Story Engine인지 검증한다."""
    if realization_policy(channel) is None:
        return []
    story = story_payload(story_document)
    primary_engine = story.get("primary_story_engine")
    question_mode = case_input.get("primary_question_mode")
    central_question_type = story.get("central_question_type")
    issues: list[ValidationIssue] = []
    if primary_engine != "CRIME_PSYCHOLOGICAL_ESCALATION":
        issues.append(
            make_realization_issue(
                "PRIMARY_STORY_ENGINE_MISSING",
                "Channel 2.1은 범죄 심리 진행을 Primary Story Engine으로 요구합니다.",
                "00_PROJECT/story_dna.json",
                {"actual": primary_engine},
            )
        )
    if (
        primary_engine in OBJECT_PUZZLE_VALUES
        or question_mode in OBJECT_PUZZLE_VALUES
        or central_question_type in OBJECT_PUZZLE_VALUES
    ):
        issues.append(
            make_realization_issue(
                "OBJECT_PUZZLE_DOMINANCE",
                "사물 또는 위치 찾기만으로 Primary Story Engine을 구성할 수 없습니다.",
                "00_PROJECT/story_dna.json",
                {
                    "primary_story_engine": primary_engine,
                    "primary_question_mode": question_mode,
                    "central_question_type": central_question_type,
                },
            )
        )
    if story.get("mystery_priority") != "SECONDARY":
        issues.append(
            make_realization_issue(
                "MYSTERY_ENGINE_PRIORITY_INVALID",
                "Channel 2.1에서 Mystery Engine의 우선순위는 SECONDARY여야 합니다.",
                "00_PROJECT/story_dna.json",
                {"actual": story.get("mystery_priority")},
            )
        )
    return issues


def required_stage_types(policy: Mapping[str, object]) -> tuple[str, ...]:
    """정책의 순서화된 필수 심리 Stage를 반환한다."""
    values = string_items(policy, "required_stages")
    return tuple(values) if values else REQUIRED_STAGE_TYPES


def stage_records(
    psychological_arc: Mapping[str, object],
) -> list[Mapping[str, object]]:
    """Psychological Arc Stage 배열을 반환한다."""
    return mapping_items(psychological_arc, "stages")


def stage_by_id(
    psychological_arc: Mapping[str, object],
) -> dict[str, Mapping[str, object]]:
    """Psychological Arc Stage를 ID로 색인한다."""
    return {
        cast(str, stage.get("stage_id")): stage
        for stage in stage_records(psychological_arc)
        if isinstance(stage.get("stage_id"), str)
    }


def validate_psychological_arc(
    channel: Mapping[str, object],
    psychological_arc: Mapping[str, object],
) -> list[ValidationIssue]:
    """GATE-06의 순서화된 심리 진행과 상태 변화를 검증한다."""
    if not psychological_arc:
        return []
    policy = realization_policy(channel)
    if policy is None:
        return []
    stages = stage_records(psychological_arc)
    expected_types = required_stage_types(policy)
    actual_types = tuple(
        cast(str, stage.get("stage_type"))
        for stage in stages
        if isinstance(stage.get("stage_type"), str)
    )
    issues: list[ValidationIssue] = []
    if actual_types != expected_types:
        issues.append(
            make_realization_issue(
                "PSYCHOLOGICAL_STAGE_SEQUENCE_INVALID",
                "Psychological Arc가 필수 Stage 순서를 정확히 보존하지 않습니다.",
                "05_STORY/psychological_arc.json",
                {"expected": list(expected_types), "actual": list(actual_types)},
            )
        )
    stage_ids = [
        cast(str, stage.get("stage_id"))
        for stage in stages
        if isinstance(stage.get("stage_id"), str)
    ]
    if len(stage_ids) != len(stages) or len(stage_ids) != len(set(stage_ids)):
        issues.append(
            make_realization_issue(
                "PSYCHOLOGICAL_STAGE_ID_INVALID",
                "Psychological Arc Stage ID가 누락되거나 중복되었습니다.",
                "05_STORY/psychological_arc.json",
                {"stage_ids": stage_ids},
            )
        )
    invalid_states: list[object] = []
    for stage in stages:
        before = stage.get("state_before")
        after = stage.get("state_after")
        required_fields = (
            stage.get("actor_id"),
            stage.get("subject_id"),
            before,
            after,
            stage.get("experience_goal"),
        )
        if (
            not all(isinstance(value, str) and value.strip() for value in required_fields)
            or before == after
            or stage.get("required_drama_evidence") is not True
        ):
            invalid_states.append(stage.get("stage_id"))
    if invalid_states:
        issues.append(
            make_realization_issue(
                "PSYCHOLOGICAL_STATE_DELTA_MISSING",
                "각 Psychological Stage에는 인물 관점의 실제 상태 변화와 Drama 근거가 필요합니다.",
                "05_STORY/psychological_arc.json",
                {"stage_ids": invalid_states},
            )
        )
    return issues


def scene_realizations(
    scene_cards: Mapping[str, object],
) -> list[tuple[Mapping[str, object], Mapping[str, object]]]:
    """Scene과 그 안의 Psychological Realization을 평탄화한다."""
    return [
        (scene, realization)
        for scene in mapping_items(scene_cards, "scenes")
        for realization in mapping_items(scene, "psychological_realization")
    ]


def presentation_stage_links(
    presentation_plan: Mapping[str, object],
) -> dict[str, list[Mapping[str, object]]]:
    """Presentation Segment를 Psychological Stage ID로 색인한다."""
    result: dict[str, list[Mapping[str, object]]] = {}
    for segment in presentation_segments(presentation_plan):
        for stage_id in string_items(segment, "psychological_stage_ids"):
            result.setdefault(stage_id, []).append(segment)
    return result


def ratio_threshold(policy: Mapping[str, object], field: str) -> float:
    """정책 비율 임곗값을 엄격하게 읽는다."""
    value = number_value(policy.get(field))
    if value is None:
        raise ConfigurationError(f"SCENE_REALIZATION_POLICY.{field} 숫자가 필요합니다.")
    return value


def psychology_drama_ratios(
    psychological_arc: Mapping[str, object],
    presentation_plan: Mapping[str, object],
) -> tuple[float, float]:
    """전체 및 Harm 이전 Drama에서 심리 진행 Segment 비율을 계산한다."""
    segments = presentation_segments(presentation_plan)
    harm_stage_ids = {
        stage_id
        for stage_id, stage in stage_by_id(psychological_arc).items()
        if stage.get("stage_type") == "HARM_OR_CRIME"
    }
    drama = [
        segment for segment in segments if canonical_mode(segment.get("segment_type")) == "DRAMA"
    ]
    total_duration = sum(number_value(segment.get("duration_sec")) or 0.0 for segment in drama)
    psychology_duration = sum(
        number_value(segment.get("duration_sec")) or 0.0
        for segment in drama
        if string_items(segment, "psychological_stage_ids")
    )
    harm_positions = [
        index
        for index, segment in enumerate(segments)
        if harm_stage_ids.intersection(string_items(segment, "psychological_stage_ids"))
    ]
    harm_index = harm_positions[0] if harm_positions else len(segments)
    pre_harm_drama = [
        segment
        for index, segment in enumerate(segments)
        if index < harm_index and canonical_mode(segment.get("segment_type")) == "DRAMA"
    ]
    pre_harm_duration = sum(
        number_value(segment.get("duration_sec")) or 0.0 for segment in pre_harm_drama
    )
    pre_harm_psychology_duration = sum(
        number_value(segment.get("duration_sec")) or 0.0
        for segment in pre_harm_drama
        if string_items(segment, "psychological_stage_ids")
    )
    return (
        psychology_duration / total_duration if total_duration > 0 else 0.0,
        (pre_harm_psychology_duration / pre_harm_duration if pre_harm_duration > 0 else 0.0),
    )


def validate_scene_coverage(
    channel: Mapping[str, object],
    psychological_arc: Mapping[str, object],
    scene_cards: Mapping[str, object],
    presentation_plan: Mapping[str, object],
) -> list[ValidationIssue]:
    """GATE-07의 Stage별 Drama Scene과 Presentation 연결을 검증한다."""
    policy = realization_policy(channel)
    if policy is None:
        return []
    stages = stage_by_id(psychological_arc)
    required_types = set(required_stage_types(policy))
    critical_types = set(string_items(policy, "critical_stages"))
    realizations = scene_realizations(scene_cards)
    links = presentation_stage_links(presentation_plan)
    issues: list[ValidationIssue] = []
    invalid_entries: list[object] = []
    satisfaction_issues: list[object] = []
    covered_types: set[str] = set()
    covered_scene_ids: set[str] = set()
    counts_by_scene: dict[str, int] = {}
    for scene, realization in realizations:
        stage_id = realization.get("stage_id")
        scene_id = scene.get("scene_id")
        stage = stages.get(stage_id) if isinstance(stage_id, str) else None
        stage_type = realization.get("stage_type")
        mode = realization.get("satisfaction_mode")
        matching_links = links.get(stage_id, []) if isinstance(stage_id, str) else []
        drama_links = [
            segment
            for segment in matching_links
            if canonical_mode(segment.get("segment_type")) == "DRAMA"
            and segment.get("scene_id") == scene_id
        ]
        trace_ids = string_items(realization, "trace_ids")
        state_matches = (
            stage is not None
            and realization.get("actor_id") == stage.get("actor_id")
            and realization.get("subject_id") == stage.get("subject_id")
            and realization.get("state_before") == stage.get("state_before")
            and realization.get("state_after") == stage.get("state_after")
        )
        evidence = realization.get("on_screen_evidence")
        if (
            stage is None
            or stage_type != stage.get("stage_type")
            or not trace_ids
            or not state_matches
            or not isinstance(evidence, str)
            or not evidence.strip()
        ):
            invalid_entries.append(stage_id)
            continue
        if mode in {"NARRATION_ONLY", "PANEL_ONLY"} or not drama_links:
            satisfaction_issues.append(stage_id)
            continue
        expected_mode = "DRAMA_REQUIRED" if stage_type in critical_types else "DRAMA"
        if mode != expected_mode:
            invalid_entries.append(stage_id)
            continue
        covered_types.add(cast(str, stage_type))
        if isinstance(scene_id, str):
            covered_scene_ids.add(scene_id)
            counts_by_scene[scene_id] = counts_by_scene.get(scene_id, 0) + 1
    if invalid_entries:
        issues.append(
            make_realization_issue(
                "SCENE_REALIZATION_INVALID",
                "Scene의 심리 Stage 실현이 Arc 상태와 Trace 계약에 결속되지 않았습니다.",
                "06_SCENE/scene_cards.json",
                {"stage_ids": invalid_entries},
            )
        )
    if satisfaction_issues:
        issues.append(
            make_realization_issue(
                "DRAMA_REALIZATION_REQUIRED",
                "Narration 또는 Panel만으로 Psychological Stage를 충족할 수 없습니다.",
                "06_SCENE/scene_cards.json",
                {"stage_ids": satisfaction_issues},
            )
        )
    missing_types = sorted(required_types - covered_types)
    missing_critical = sorted(critical_types - covered_types)
    if missing_types:
        issues.append(
            make_realization_issue(
                "PSYCHOLOGICAL_STAGE_SCENE_MISSING",
                "필수 Psychological Stage가 Drama Scene으로 실현되지 않았습니다.",
                "06_SCENE/scene_cards.json",
                {"stage_types": missing_types},
            )
        )
    if missing_critical:
        issues.append(
            make_realization_issue(
                "CRITICAL_STAGE_UNREALIZED",
                "Critical Psychological Stage는 반드시 Drama로 실현해야 합니다.",
                "06_SCENE/scene_cards.json",
                {"stage_types": missing_critical},
            )
        )
    minimum_scenes = int(number_value(policy.get("minimum_distinct_drama_scenes")) or 0)
    if len(covered_scene_ids) < minimum_scenes:
        issues.append(
            make_realization_issue(
                "PSYCHOLOGICAL_SCENE_DIVERSITY_LOW",
                "심리 진행을 서로 다른 Drama Scene에 충분히 분산하지 않았습니다.",
                "06_SCENE/scene_cards.json",
                {"minimum": minimum_scenes, "actual": len(covered_scene_ids)},
            )
        )
    maximum_per_scene = int(number_value(policy.get("maximum_stages_per_scene")) or 0)
    overloaded = sorted(
        scene_id
        for scene_id, count in counts_by_scene.items()
        if maximum_per_scene > 0 and count > maximum_per_scene
    )
    if overloaded:
        issues.append(
            make_realization_issue(
                "PSYCHOLOGICAL_STAGE_COMPRESSION_EXCESSIVE",
                "한 Scene에 허용된 Psychological Stage 수를 초과했습니다.",
                "06_SCENE/scene_cards.json",
                {"scene_ids": overloaded, "maximum": maximum_per_scene},
            )
        )
    drama_ratio, pre_harm_ratio = psychology_drama_ratios(
        psychological_arc,
        presentation_plan,
    )
    if drama_ratio < ratio_threshold(policy, "minimum_psychology_drama_ratio"):
        issues.append(
            make_realization_issue(
                "PSYCHOLOGICAL_DRAMA_RATIO_LOW",
                "전체 Drama에서 심리 진행을 실현한 비율이 기준보다 낮습니다.",
                "06_SCENE/presentation_plan.json",
                {"actual": drama_ratio},
            )
        )
    if pre_harm_ratio < ratio_threshold(policy, "minimum_pre_harm_drama_ratio"):
        issues.append(
            make_realization_issue(
                "PRE_HARM_DRAMA_RATIO_LOW",
                "Harm 이전 Drama에서 Trust와 Control 진행 비율이 기준보다 낮습니다.",
                "06_SCENE/presentation_plan.json",
                {"actual": pre_harm_ratio},
            )
        )
    return issues


def canonical_json_hash(value: object) -> str:
    """JSON 값의 정규 SHA-256을 계산한다."""
    encoded = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return sha256(encoded).hexdigest()


def script_stage_bindings(
    presentation_plan: Mapping[str, object],
    final_script: str,
) -> dict[str, list[dict[str, object]]]:
    """Final Script의 Drama Segment와 Stage Tag를 결합한다."""
    planned = {
        cast(str, segment.get("segment_id")): segment
        for segment in presentation_segments(presentation_plan)
        if isinstance(segment.get("segment_id"), str)
    }
    parsed, malformed = parse_script_segments(final_script)
    if malformed:
        return {}
    result: dict[str, list[dict[str, object]]] = {}
    for segment in parsed:
        plan_segment = planned.get(segment["segment_id"])
        if plan_segment is None:
            continue
        declared_ids = set(string_items(plan_segment, "psychological_stage_ids"))
        tagged_ids = set(STAGE_TAG.findall(segment["body"]))
        trace_ids = set(TRACE_TAG.findall(segment["body"]))
        for stage_id in sorted(declared_ids & tagged_ids):
            result.setdefault(stage_id, []).append(
                {
                    "segment_id": segment["segment_id"],
                    "scene_id": segment["scene_id"],
                    "segment_type": segment["segment_type"],
                    "trace_ids": sorted(trace_ids),
                    "excerpt_hash": canonical_json_hash(segment),
                }
            )
    return result


def validate_script_realization(
    channel: Mapping[str, object],
    psychological_arc: Mapping[str, object],
    scene_cards: Mapping[str, object],
    presentation_plan: Mapping[str, object],
    final_script: str,
) -> list[ValidationIssue]:
    """GATE-08의 실제 Final Script Drama 실현을 검증한다."""
    policy = realization_policy(channel)
    if policy is None:
        return []
    stages = stage_by_id(psychological_arc)
    bindings = script_stage_bindings(presentation_plan, final_script)
    required_ids = set(stages)
    realized_ids = set(bindings)
    issues: list[ValidationIssue] = []
    missing_ids = sorted(required_ids - realized_ids)
    if missing_ids:
        issues.append(
            make_realization_issue(
                "SCRIPT_STAGE_REALIZATION_MISSING",
                "Psychological Stage가 실제 Final Script Drama Segment에 없습니다.",
                "07_SCRIPT/final_script.md",
                {"stage_ids": missing_ids},
            )
        )
    wrong_modes = sorted(
        stage_id
        for stage_id, records in bindings.items()
        if any(record.get("segment_type") != "DRAMA" for record in records)
    )
    if wrong_modes:
        issues.append(
            make_realization_issue(
                "DRAMA_REALIZATION_REQUIRED",
                "Psychological Stage Script 근거는 Drama Segment여야 합니다.",
                "07_SCRIPT/final_script.md",
                {"stage_ids": wrong_modes},
            )
        )
    expected_traces: dict[str, set[str]] = {}
    for _scene, realization in scene_realizations(scene_cards):
        stage_id = realization.get("stage_id")
        if isinstance(stage_id, str):
            expected_traces.setdefault(stage_id, set()).update(
                string_items(realization, "trace_ids")
            )
    missing_traces = {
        stage_id: sorted(
            expected_traces.get(stage_id, set())
            - {
                trace_id
                for binding in bindings.get(stage_id, [])
                for trace_id in cast(list[str], binding.get("trace_ids", []))
            }
        )
        for stage_id in required_ids
    }
    unresolved_traces = {
        stage_id: trace_ids for stage_id, trace_ids in missing_traces.items() if trace_ids
    }
    if unresolved_traces:
        issues.append(
            make_realization_issue(
                "CRIME_PSYCHOLOGY_TRACE_UNREALIZED",
                "Crime Psychology Trace가 실제 Final Script Segment에 실현되지 않았습니다.",
                "07_SCRIPT/final_script.md",
                {"missing_trace_ids": unresolved_traces},
            )
        )
    return issues


def build_script_realization_report(
    project_id: str,
    channel: Mapping[str, object],
    psychological_arc: Mapping[str, object],
    scene_cards: Mapping[str, object],
    presentation_plan: Mapping[str, object],
    final_script: str,
) -> dict[str, object]:
    """Continuity Critic CORE Task가 생성할 Script 실현 보고서를 만든다."""
    policy = realization_policy(channel)
    if policy is None:
        return {
            "schema_family": "script-realization-report",
            "schema_version": "1.0.0",
            "project_id": project_id,
            "applicable": False,
            "minimum_realization_score": 0,
            "realization_score": 100,
            "stage_results": [],
            "result": "PASS",
            "issues": [],
        }
    stages = stage_by_id(psychological_arc)
    bindings = script_stage_bindings(presentation_plan, final_script)
    stage_results: list[dict[str, object]] = []
    for stage_id, stage in stages.items():
        records = bindings.get(stage_id, [])
        first = records[0] if records else {}
        state_delta_observed = stage.get("state_before") != stage.get("state_after")
        stage_results.append(
            {
                "stage_id": stage_id,
                "stage_type": stage.get("stage_type"),
                "status": "PASS" if records and state_delta_observed else "FAIL",
                "satisfaction_mode": "DRAMA" if records else "UNREALIZED",
                "scene_id": first.get("scene_id"),
                "segment_id": first.get("segment_id"),
                "selector_type": "SEGMENT_ID",
                "excerpt_hash": first.get("excerpt_hash"),
                "state_delta_observed": state_delta_observed,
            }
        )
    realized_count = sum(result["status"] == "PASS" for result in stage_results)
    score = round(100.0 * realized_count / len(stage_results), 2) if stage_results else 0.0
    minimum_score = number_value(policy.get("minimum_realization_score")) or 0.0
    report_issues = [
        *validate_psychological_arc(channel, psychological_arc),
        *validate_scene_coverage(
            channel,
            psychological_arc,
            scene_cards,
            presentation_plan,
        ),
        *validate_script_realization(
            channel,
            psychological_arc,
            scene_cards,
            presentation_plan,
            final_script,
        ),
    ]
    if score < minimum_score:
        report_issues.append(
            make_realization_issue(
                "SCRIPT_REALIZATION_SCORE_LOW",
                "Script Realization Score가 Channel 기준보다 낮습니다.",
                "08_QA/script_realization_report.json",
                {"minimum": minimum_score, "actual": score},
            )
        )
    return {
        "schema_family": "script-realization-report",
        "schema_version": "1.0.0",
        "project_id": project_id,
        "applicable": True,
        "minimum_realization_score": minimum_score,
        "realization_score": score,
        "input_hashes": {
            "psychological_arc": canonical_json_hash(psychological_arc),
            "scene_cards": canonical_json_hash(scene_cards),
            "presentation_plan": canonical_json_hash(presentation_plan),
            "final_script": sha256(final_script.encode("utf-8")).hexdigest(),
        },
        "stage_results": stage_results,
        "result": "FAIL" if report_issues else "PASS",
        "issues": report_issues,
    }


def validate_script_realization_report(
    channel: Mapping[str, object],
    psychological_arc: Mapping[str, object],
    scene_cards: Mapping[str, object],
    presentation_plan: Mapping[str, object],
    final_script: str,
    report: Mapping[str, object],
) -> list[ValidationIssue]:
    """CORE가 Report의 Selector, Excerpt Hash와 점수를 재계산한다."""
    if realization_policy(channel) is None:
        return []
    project_id = psychological_arc.get("project_id")
    expected = build_script_realization_report(
        project_id if isinstance(project_id, str) else "PRJ-000",
        channel,
        psychological_arc,
        scene_cards,
        presentation_plan,
        final_script,
    )
    fields = (
        "schema_family",
        "schema_version",
        "project_id",
        "applicable",
        "minimum_realization_score",
        "realization_score",
        "input_hashes",
        "stage_results",
        "result",
        "issues",
    )
    mismatches = {
        field: {"expected": expected.get(field), "actual": report.get(field)}
        for field in fields
        if report.get(field) != expected.get(field)
    }
    issues: list[ValidationIssue] = []
    if mismatches:
        issues.append(
            make_realization_issue(
                "SCRIPT_REALIZATION_REPORT_STALE",
                "Script Realization Report가 현재 Final Script 근거와 일치하지 않습니다.",
                "08_QA/script_realization_report.json",
                {"mismatches": mismatches},
            )
        )
    score = number_value(report.get("realization_score"))
    minimum_score = ratio_threshold(realization_policy(channel) or {}, "minimum_realization_score")
    if score is None or score < minimum_score:
        issues.append(
            make_realization_issue(
                "SCRIPT_REALIZATION_SCORE_LOW",
                "Script Realization Score가 Channel 기준보다 낮습니다.",
                "08_QA/script_realization_report.json",
                {"minimum": minimum_score, "actual": score},
            )
        )
    return issues


def narration_references(segment: Mapping[str, object]) -> set[str]:
    """Narration Segment가 언급하는 Fact와 Clue ID를 결합한다."""
    return set(string_items(segment, "referenced_fact_ids")) | set(
        string_items(segment, "referenced_clue_ids")
    )


def validate_narration_realization(
    channel: Mapping[str, object],
    presentation_plan: Mapping[str, object],
) -> list[ValidationIssue]:
    """Narration의 주관성, 분석 지배, 선행 공개와 중복을 검증한다."""
    if (
        capability_policy(channel, "NARRATION_POLICY") is None
        or capability_policy(channel, "EXPLICIT_CRIME_EVENT_POLICY") is None
    ):
        return []
    segments = presentation_segments(presentation_plan)
    narration = [
        segment
        for segment in segments
        if canonical_mode(segment.get("segment_type")) == "NARRATION"
    ]
    total_duration = sum(number_value(item.get("duration_sec")) or 0.0 for item in narration)
    subjective_duration = sum(
        number_value(item.get("duration_sec")) or 0.0
        for item in narration
        if item.get("narration_function") in SUBJECTIVE_NARRATION_FUNCTIONS
    )
    analysis_duration = sum(
        number_value(item.get("duration_sec")) or 0.0
        for item in narration
        if item.get("narration_function") in ANALYSIS_NARRATION_FUNCTIONS
    )
    issues: list[ValidationIssue] = []
    subjective_ratio = subjective_duration / total_duration if total_duration > 0 else 0.0
    analysis_ratio = analysis_duration / total_duration if total_duration > 0 else 1.0
    invalid_segments = [
        segment.get("segment_id")
        for segment in narration
        if segment.get("narration_function") not in SUBJECTIVE_NARRATION_FUNCTIONS
        or not isinstance(segment.get("narrator_character_id"), str)
    ]
    if not narration or invalid_segments or subjective_ratio < 1.0:
        issues.append(
            make_realization_issue(
                "SUBJECTIVE_NARRATION_MISSING",
                "Narration은 허용된 주관적 기능과 내부 인물 Anchor를 가져야 합니다.",
                "06_SCENE/presentation_plan.json",
                {
                    "subjective_duration_ratio": subjective_ratio,
                    "invalid_segment_ids": invalid_segments,
                },
            )
        )
    if analysis_ratio > 0.15:
        issues.append(
            make_realization_issue(
                "NARRATION_ANALYSIS_DOMINANCE",
                "Narration의 분석·증거 설명 비율은 0.15를 초과할 수 없습니다.",
                "06_SCENE/presentation_plan.json",
                {"analysis_exposition_ratio": analysis_ratio},
            )
        )
    revealed: set[str] = set()
    premature: list[dict[str, object]] = []
    duplicated = 0
    referenced = 0
    for index, segment in enumerate(segments):
        mode = canonical_mode(segment.get("segment_type"))
        if mode == "NARRATION":
            references = narration_references(segment)
            referenced += len(references)
            unavailable = sorted(references - revealed)
            if unavailable:
                premature.append(
                    {"segment_id": segment.get("segment_id"), "reference_ids": unavailable}
                )
            adjacent_ids: set[str] = set()
            for adjacent_index in (index - 1, index + 1):
                if not 0 <= adjacent_index < len(segments):
                    continue
                adjacent = segments[adjacent_index]
                if canonical_mode(adjacent.get("segment_type")) not in {
                    "DRAMA",
                    "PANEL_REACTION",
                }:
                    continue
                adjacent_ids.update(string_items(adjacent, "revealed_fact_ids"))
                adjacent_ids.update(string_items(adjacent, "revealed_clue_ids"))
                adjacent_ids.update(narration_references(adjacent))
            duplicated += len(references & adjacent_ids)
        revealed.update(string_items(segment, "revealed_fact_ids"))
        revealed.update(string_items(segment, "revealed_clue_ids"))
    if premature:
        issues.append(
            make_realization_issue(
                "NARRATION_PREMATURE_REVEAL",
                "Narration이 아직 Drama에서 공개되지 않은 Fact 또는 Clue를 언급했습니다.",
                "06_SCENE/presentation_plan.json",
                {"segments": premature},
            )
        )
    duplication_ratio = duplicated / referenced if referenced > 0 else 0.0
    if duplication_ratio > 0.20:
        issues.append(
            make_realization_issue(
                "NARRATION_PANEL_DUPLICATION",
                "Narration이 인접 Drama 또는 Panel의 정보 설명을 반복했습니다.",
                "06_SCENE/presentation_plan.json",
                {"duplication_ratio": duplication_ratio},
            )
        )
    return issues


def repeated_mechanical_cycle(presentation_plan: Mapping[str, object]) -> bool:
    """DRAMA→NARRATION→PANEL 순환이 세 번 연속 반복되는지 판정한다."""
    modes = [
        canonical_mode(segment.get("segment_type"))
        for segment in presentation_segments(presentation_plan)
    ]
    pattern = ["DRAMA", "NARRATION", "PANEL_REACTION"] * 3
    return any(modes[index : index + len(pattern)] == pattern for index in range(len(modes)))


def panel_spoken_density(
    reaction: Mapping[str, object],
    panel_reaction_script: str,
) -> float:
    """실제 Panel Script 발화량을 Segment Duration 대비 비율로 계산한다."""
    reaction_id = reaction.get("reaction_segment_id")
    duration = number_value(reaction.get("duration_sec"))
    if not isinstance(reaction_id, str) or duration is None or duration <= 0:
        return 0.0
    sections: dict[str, list[str]] = {}
    headers = list(PANEL_HEADER.finditer(panel_reaction_script))
    for index, header in enumerate(headers):
        section_end = (
            headers[index + 1].start() if index + 1 < len(headers) else len(panel_reaction_script)
        )
        sections.setdefault(header.group("reaction_id"), []).append(
            panel_reaction_script[header.end() : section_end]
        )
    words = sum(
        len(SPOKEN_TOKEN.findall(match.group("spoken_line")))
        for section in sections.get(reaction_id, [])
        for match in PANEL_SPOKEN_LINE.finditer(section)
    )
    spoken_seconds = words / 2.5
    return min(1.0, spoken_seconds / duration)


def valid_exchange_turns(turns: Sequence[Mapping[str, object]]) -> int:
    """앞선 발화에 실제로 응답하는 Turn 수를 계산한다."""
    speakers_by_turn: dict[str, str] = {}
    exchanges = 0
    for turn in turns:
        turn_id = turn.get("turn_id")
        panelist_id = turn.get("panelist_id")
        responds_to = turn.get("responds_to_turn_id")
        if (
            isinstance(responds_to, str)
            and isinstance(panelist_id, str)
            and responds_to in speakers_by_turn
            and speakers_by_turn[responds_to] != panelist_id
        ):
            exchanges += 1
        if isinstance(turn_id, str) and isinstance(panelist_id, str):
            speakers_by_turn[turn_id] = panelist_id
    return exchanges


def validate_panel_design_realization(
    channel: Mapping[str, object],
    reaction_segments: Mapping[str, object],
    presentation_plan: Mapping[str, object],
) -> list[ValidationIssue]:
    """Panel의 정서 기능과 실제 대화 교환 설계를 검증한다."""
    policy = capability_policy(channel, "REACTION_POLICY")
    if policy is None or number_value(policy.get("minimum_exchange_segment_ratio")) is None:
        return []
    reactions = mapping_items(reaction_segments, "reaction_segments")
    turns = [turn for reaction in reactions for turn in mapping_items(reaction, "turns")]
    functions = {function for turn in turns if isinstance((function := turn.get("function")), str)}
    issues: list[ValidationIssue] = []
    required_functions = set(string_items(policy, "required_functions"))
    required_any = set(string_items(policy, "required_function_any_of"))
    missing_functions = sorted(required_functions - functions)
    any_function_missing = bool(required_any) and not functions.intersection(required_any)
    if missing_functions or any_function_missing:
        issues.append(
            make_realization_issue(
                "PANEL_CRIME_PURSUIT_FUNCTION_MISSING",
                "Panel은 필수 감정 반응과 사건·용의자 추적 기능을 수행해야 합니다.",
                "06_SCENE/reaction_segments.json",
                {
                    "missing_functions": missing_functions,
                    "required_any_of_satisfied": not any_function_missing,
                },
            )
        )
    exchange_segments = sum(
        valid_exchange_turns(mapping_items(reaction, "turns")) > 0 for reaction in reactions
    )
    exchange_ratio = exchange_segments / len(reactions) if reactions else 0.0
    minimum_exchange_ratio = number_value(policy.get("minimum_exchange_segment_ratio"))
    minimum_exchange_ratio = minimum_exchange_ratio if minimum_exchange_ratio is not None else 0.5
    if exchange_ratio < minimum_exchange_ratio:
        issues.append(
            make_realization_issue(
                "PANEL_EXCHANGE_RATIO_LOW",
                "Panel Segment의 실제 상호 응답 비율이 Channel 기준보다 낮습니다.",
                "06_SCENE/reaction_segments.json",
                {
                    "exchange_segment_ratio": exchange_ratio,
                    "minimum": minimum_exchange_ratio,
                },
            )
        )
    if repeated_mechanical_cycle(presentation_plan):
        issues.append(
            make_realization_issue(
                "PRESENTATION_MECHANICAL_CYCLE_REPETITION",
                "DRAMA→NARRATION→PANEL 고정 순환을 세 번 이상 반복할 수 없습니다.",
                "06_SCENE/presentation_plan.json",
                {},
            )
        )
    return issues


def validate_panel_script_density(
    channel: Mapping[str, object],
    reaction_segments: Mapping[str, object],
    panel_reaction_script: str,
) -> list[ValidationIssue]:
    """Panel Script의 실제 발화 밀도와 비발화 비율을 검증한다."""
    policy = capability_policy(channel, "REACTION_POLICY")
    if policy is None or number_value(policy.get("minimum_spoken_density")) is None:
        return []
    reactions = mapping_items(reaction_segments, "reaction_segments")
    minimum_density = number_value(policy.get("minimum_spoken_density"))
    minimum_density = minimum_density if minimum_density is not None else 0.4
    low_density = [
        reaction.get("reaction_segment_id")
        for reaction in reactions
        if panel_spoken_density(reaction, panel_reaction_script) < minimum_density
    ]
    if not low_density:
        return []
    return [
        make_realization_issue(
            "PANEL_SPOKEN_DENSITY_LOW",
            "Panel Segment의 실제 발화 밀도가 Channel 기준보다 낮습니다.",
            "07_SCRIPT/panel_reaction_script.md",
            {"reaction_segment_ids": low_density, "minimum": minimum_density},
        )
    ]


def validate_panel_realization(
    channel: Mapping[str, object],
    reaction_segments: Mapping[str, object],
    presentation_plan: Mapping[str, object],
    panel_reaction_script: str,
) -> list[ValidationIssue]:
    """Panel 설계와 Script 발화 밀도를 함께 검증한다."""
    return [
        *validate_panel_design_realization(
            channel,
            reaction_segments,
            presentation_plan,
        ),
        *validate_panel_script_density(
            channel,
            reaction_segments,
            panel_reaction_script,
        ),
    ]


def channel_realization_evidence(
    report: Mapping[str, object],
) -> list[dict[str, object]]:
    """Script Report Stage 결과를 Channel QA 증거로 투영한다."""
    return [
        {
            "stage_id": result.get("stage_id"),
            "scene_id": result.get("scene_id"),
            "segment_id": result.get("segment_id"),
            "excerpt_hash": result.get("excerpt_hash"),
        }
        for result in mapping_items(report, "stage_results")
        if result.get("status") == "PASS"
    ]


def validate_channel_realization_evidence(
    channel: Mapping[str, object],
    psychological_arc: Mapping[str, object],
    script_realization_report: Mapping[str, object],
    channel_consistency_report: Mapping[str, object],
) -> list[ValidationIssue]:
    """GATE-12 Channel QA가 실제 Scene Evidence를 포함하는지 검증한다."""
    if realization_policy(channel) is None:
        return []
    expected = channel_realization_evidence(script_realization_report)
    actual = channel_consistency_report.get("scene_realization_evidence")
    required_count = len(stage_records(psychological_arc))
    if actual == expected and len(expected) == required_count:
        return []
    return [
        make_realization_issue(
            "CHANNEL_REALIZATION_EVIDENCE_MISSING",
            "Channel Consistency Report에 Stage별 Scene·Segment Hash 근거가 없습니다.",
            "08_QA/channel_consistency_report.json",
            {"expected": expected, "actual": actual},
        )
    ]


def validate_realization_bundle(
    channel: Mapping[str, object],
    inputs: RealizationInputs,
    include_report: bool,
    include_channel_evidence: bool,
) -> list[ValidationIssue]:
    """선택한 Gate 수준까지 2.1 장면 실현 계약을 검증한다."""
    if realization_policy(channel) is None:
        return []
    issues = [
        *validate_primary_story_engine(channel, inputs["story_dna"], inputs["case_input"]),
        *validate_psychological_arc(channel, inputs["psychological_arc"]),
        *validate_scene_coverage(
            channel,
            inputs["psychological_arc"],
            inputs["scene_cards"],
            inputs["presentation_plan"],
        ),
        *validate_script_realization(
            channel,
            inputs["psychological_arc"],
            inputs["scene_cards"],
            inputs["presentation_plan"],
            inputs["final_script"],
        ),
        *validate_narration_realization(channel, inputs["presentation_plan"]),
        *validate_panel_realization(
            channel,
            inputs["reaction_segments"],
            inputs["presentation_plan"],
            inputs["panel_reaction_script"],
        ),
    ]
    if include_report:
        issues.extend(
            validate_script_realization_report(
                channel,
                inputs["psychological_arc"],
                inputs["scene_cards"],
                inputs["presentation_plan"],
                inputs["final_script"],
                inputs["script_realization_report"],
            )
        )
    if include_channel_evidence:
        issues.extend(
            validate_channel_realization_evidence(
                channel,
                inputs["psychological_arc"],
                inputs["script_realization_report"],
                inputs["channel_consistency_report"],
            )
        )
    return issues
