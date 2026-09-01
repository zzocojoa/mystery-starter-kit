"""Editorial Review v1.2의 Selector 감사 증거와 Runtime 근거 검증."""

from copy import deepcopy
from pathlib import Path
from typing import cast

import pytest
from project_factory import make_complete_project_artifacts

from VALIDATORS.dependency import build_initial_project_state
from VALIDATORS.editorial import (
    editorial_artifact_hashes,
    finalize_production_ready,
    runtime_evidence_issues,
    validate_editorial_review,
)
from VALIDATORS.exceptions import StateTransitionError
from VALIDATORS.io import load_json_object
from VALIDATORS.models import ValidationIssue
from VALIDATORS.pipeline import ArtifactContent
from VALIDATORS.schema_validation import collect_schema_errors

ROOT = Path(__file__).resolve().parents[1]


def editorial_review(artifacts: dict[str, ArtifactContent]) -> dict[str, object]:
    """완전한 Project에서 수정 가능한 Editorial Review를 읽는다."""
    review = artifacts["editorial_review"]
    assert isinstance(review, dict)
    return cast(dict[str, object], review)


def editorial_issues(artifacts: dict[str, ArtifactContent]) -> list[ValidationIssue]:
    """Review Hash와 Panel Runtime 근거를 함께 검증한다."""
    review = editorial_review(artifacts)
    presentation_plan = artifacts["presentation_plan"]
    panel_reaction_script = artifacts["panel_reaction_script"]
    assert isinstance(presentation_plan, dict)
    assert isinstance(panel_reaction_script, str)
    return [
        *validate_editorial_review(
            review,
            "PRJ-002",
            editorial_artifact_hashes(artifacts),
            artifacts,
        ),
        *runtime_evidence_issues(
            review,
            presentation_plan,
            panel_reaction_script,
        ),
    ]


def first_runtime_segment(review: dict[str, object]) -> dict[str, object]:
    """첫 Panel Runtime 근거를 수정 가능한 객체로 반환한다."""
    runtime_evidence = review["runtime_evidence"]
    assert isinstance(runtime_evidence, dict)
    panel_segments = runtime_evidence["panel_segments"]
    assert isinstance(panel_segments, list)
    first_segment = panel_segments[0]
    assert isinstance(first_segment, dict)
    return cast(dict[str, object], first_segment)


def test_editorial_review_v12_requires_resolvable_evidence() -> None:
    """완료 Review는 검토자·시각·Hash·근거·Runtime 추정을 모두 보존한다."""
    artifacts = make_complete_project_artifacts()
    review = editorial_review(artifacts)
    schema = load_json_object(ROOT / "STANDARD" / "schemas" / "editorial_review.schema.json")

    assert review["schema_version"] == "1.2.0"
    assert collect_schema_errors(review, schema, "editorial_review") == []
    assert editorial_issues(artifacts) == []


def test_editorial_review_rejects_missing_check_evidence() -> None:
    """PASS Check가 장면·Segment 근거를 비우면 Gate-13을 통과하지 못한다."""
    artifacts = deepcopy(make_complete_project_artifacts())
    review = editorial_review(artifacts)
    checks = review["checks"]
    assert isinstance(checks, dict)
    dialogue_check = checks["dialogue_naturalness"]
    assert isinstance(dialogue_check, dict)
    dialogue_check["evidence"] = []

    codes = {issue["code"] for issue in editorial_issues(artifacts)}

    assert "EDITORIAL_CHECK_EVIDENCE_MISSING" in codes


def test_editorial_review_rejects_stale_artifact_hash() -> None:
    """검토 뒤 입력 Artifact가 바뀌면 기존 Review를 재사용할 수 없다."""
    artifacts = deepcopy(make_complete_project_artifacts())
    review = editorial_review(artifacts)
    hashes = review["artifact_hashes"]
    assert isinstance(hashes, dict)
    hashes["final_script"] = "0" * 64

    codes = {issue["code"] for issue in editorial_issues(artifacts)}

    assert "EDITORIAL_ARTIFACT_HASH_MISMATCH" in codes


def test_editorial_review_rejects_unverified_spoken_word_count() -> None:
    """Panel 발화 단어 수가 Script와 다르면 예상시간 근거를 거부한다."""
    artifacts = deepcopy(make_complete_project_artifacts())
    review = editorial_review(artifacts)
    first_segment = first_runtime_segment(review)
    word_count = first_segment["spoken_word_count"]
    assert isinstance(word_count, int)
    first_segment["spoken_word_count"] = word_count + 1

    codes = {issue["code"] for issue in editorial_issues(artifacts)}

    assert "EDITORIAL_PANEL_WORD_COUNT_MISMATCH" in codes


def test_editorial_review_rejects_unfilled_panel_runtime() -> None:
    """발화와 비발화 요소의 합이 계획시간보다 짧으면 방송 비율 근거가 아니다."""
    artifacts = deepcopy(make_complete_project_artifacts())
    review = editorial_review(artifacts)
    first_segment = first_runtime_segment(review)
    non_speech_elements = first_segment["non_speech_elements"]
    assert isinstance(non_speech_elements, list)
    first_element = non_speech_elements[0]
    assert isinstance(first_element, dict)
    duration = first_element["duration_sec"]
    assert isinstance(duration, int | float)
    first_element["duration_sec"] = float(duration) - 1.0

    codes = {issue["code"] for issue in editorial_issues(artifacts)}

    assert "EDITORIAL_PANEL_TIMING_GAP" in codes


def test_editorial_review_rejects_nonfinite_runtime_value() -> None:
    """NaN처럼 합계를 우회하는 비유한 Runtime 값은 검증 근거로 사용하지 않는다."""
    artifacts = deepcopy(make_complete_project_artifacts())
    review = editorial_review(artifacts)
    runtime_evidence = review["runtime_evidence"]
    assert isinstance(runtime_evidence, dict)
    runtime_evidence["planned_runtime_sec"] = float("nan")

    codes = {issue["code"] for issue in editorial_issues(artifacts)}

    assert "EDITORIAL_RUNTIME_AGGREGATE_MISMATCH" in codes


def test_editorial_review_rejects_unknown_selector_and_excerpt_drift() -> None:
    """Evidence Selector가 없거나 Excerpt가 바뀌면 감사 근거를 거부해야 한다."""
    artifacts = deepcopy(make_complete_project_artifacts())
    review = editorial_review(artifacts)
    checks = review["checks"]
    assert isinstance(checks, dict)
    check = checks["broadcast_format"]
    assert isinstance(check, dict)
    evidence = check["evidence"]
    assert isinstance(evidence, list)
    reference = evidence[0]
    assert isinstance(reference, dict)
    reference["selector_id"] = "SEG-999"

    selector_codes = {issue["code"] for issue in editorial_issues(artifacts)}
    assert "EDITORIAL_EVIDENCE_SELECTOR_NOT_FOUND" in selector_codes

    reference["selector_id"] = "SEG-001"
    reference["excerpt_hash"] = "0" * 64
    hash_codes = {issue["code"] for issue in editorial_issues(artifacts)}
    assert "EDITORIAL_EVIDENCE_HASH_MISMATCH" in hash_codes


def test_production_finalize_requires_measured_runtime_method() -> None:
    """Word Count 예상만으로는 Production Ready를 확정할 수 없다."""
    graph = load_json_object(ROOT / "STANDARD" / "dependency_graph.json")
    state = build_initial_project_state(graph, "PRJ-002", "2026-08-28T00:00:00Z")
    state["state"] = "EDITORIAL_APPROVED"
    state["current_gate"] = "GATE-13"
    state["readiness"].update(
        {
            "artifact_status": "ARTIFACT_COMPLETE",
            "contract_status": "CONTRACT_VALIDATED",
            "process_status": "PROCESS_CONFORMANT",
            "editorial_status": "EDITORIAL_APPROVED",
        }
    )
    artifacts = make_complete_project_artifacts()
    review = editorial_review(artifacts)
    runtime_evidence = review["runtime_evidence"]
    assert isinstance(runtime_evidence, dict)
    runtime_evidence["method"] = "WORD_COUNT_ESTIMATE"
    runtime_evidence["measured_panel_duration_sec"] = None

    with pytest.raises(StateTransitionError, match="TABLE_READ"):
        finalize_production_ready(
            state,
            review,
            "2026-08-28T01:00:00Z",
        )


def test_production_finalize_rejects_reenactment_estimate_as_measurement() -> None:
    """재연극 단어 수 예상은 Production Ready 실측 근거가 아니다."""
    graph = load_json_object(ROOT / "STANDARD" / "dependency_graph.json")
    state = build_initial_project_state(graph, "PRJ-002", "2026-08-28T00:00:00Z")
    state["state"] = "EDITORIAL_APPROVED"
    state["current_gate"] = "GATE-13"
    state["readiness"].update(
        {
            "artifact_status": "ARTIFACT_COMPLETE",
            "contract_status": "CONTRACT_VALIDATED",
            "process_status": "PROCESS_CONFORMANT",
            "editorial_status": "EDITORIAL_APPROVED",
        }
    )
    review = editorial_review(make_complete_project_artifacts())
    review["reenactment_runtime_evidence"] = {
        "method": "WORD_COUNT_ESTIMATE",
        "measured_duration_sec": None,
    }

    with pytest.raises(StateTransitionError, match="재연극 Runtime"):
        finalize_production_ready(
            state,
            review,
            "2026-08-28T01:00:00Z",
        )
