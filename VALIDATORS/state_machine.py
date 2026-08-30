"""GATE-00부터 GATE-13까지의 Project 상태 전이."""

from collections.abc import Mapping, Sequence
from copy import deepcopy
from typing import TypedDict

from VALIDATORS.dependency import artifact_required_for_project, dependency_artifacts
from VALIDATORS.exceptions import StateTransitionError
from VALIDATORS.models import ProjectState, ProjectStatus


class GateDefinition(TypedDict):
    """Gate 통과에 필요한 Artifact와 도착 상태."""

    gate_id: str
    required_artifacts: tuple[str, ...]
    target_state: ProjectStatus


GATES: tuple[GateDefinition, ...] = (
    {
        "gate_id": "GATE-00",
        "required_artifacts": (
            "project_manifest",
            "compatibility_report",
            "production_config",
            "project_constraints",
        ),
        "target_state": "COMPATIBILITY_VALIDATED",
    },
    {
        "gate_id": "GATE-01",
        "required_artifacts": (
            "variation_candidates",
            "candidate_evaluation",
            "novelty_precheck",
            "candidate_eligibility",
            "candidate_approval",
            "source_case_brief",
            "verified_fact_ledger",
        ),
        "target_state": "VARIATION_APPROVED",
    },
    {
        "gate_id": "GATE-02",
        "required_artifacts": ("story_dna",),
        "target_state": "STORY_DESIGNED",
    },
    {
        "gate_id": "GATE-03",
        "required_artifacts": (
            "case_input",
            "facts",
            "crime_psychology",
            "sources",
            "claim_evidence",
            "source_disclosure",
            "clinical_labels",
        ),
        "target_state": "CASE_DEFINED",
    },
    {
        "gate_id": "GATE-04",
        "required_artifacts": ("characters", "relationships", "knowledge_matrix"),
        "target_state": "CHARACTERS_DESIGNED",
    },
    {
        "gate_id": "GATE-05",
        "required_artifacts": (
            "actual_timeline",
            "viewer_timeline",
            "audience_belief",
            "clue_matrix",
            "hypothesis_ledger",
            "causal_graph",
        ),
        "target_state": "MYSTERY_DESIGNED",
    },
    {
        "gate_id": "GATE-06",
        "required_artifacts": ("beat_sheet", "retention_plan"),
        "target_state": "STORY_STRUCTURED",
    },
    {
        "gate_id": "GATE-07",
        "required_artifacts": (
            "scene_cards",
            "panel_cast",
            "reaction_segments",
            "expert_segments",
            "presentation_plan",
        ),
        "target_state": "SCENES_DESIGNED",
    },
    {
        "gate_id": "GATE-08",
        "required_artifacts": (
            "drama_script",
            "narration_script",
            "panel_reaction_script",
            "expert_analysis_script",
            "draft_script",
            "final_script",
        ),
        "target_state": "SCRIPT_WRITTEN",
    },
    {
        "gate_id": "GATE-09",
        "required_artifacts": ("continuity_report",),
        "target_state": "SCRIPT_WRITTEN",
    },
    {
        "gate_id": "GATE-10",
        "required_artifacts": ("story_fingerprint", "novelty_report"),
        "target_state": "SCRIPT_WRITTEN",
    },
    {
        "gate_id": "GATE-11",
        "required_artifacts": ("reference_collision_report",),
        "target_state": "SCRIPT_WRITTEN",
    },
    {
        "gate_id": "GATE-12",
        "required_artifacts": ("channel_consistency_report", "validation_report"),
        "target_state": "QA_PASSED",
    },
    {
        "gate_id": "GATE-13",
        "required_artifacts": (
            "shooting_script",
            "narration",
            "production_panel_reaction_script",
            "production_expert_analysis_script",
            "subtitle_script",
            "edit_script",
            "editorial_review",
        ),
        "target_state": "EDITORIAL_REVIEW_REQUIRED",
    },
)


def gate_index(gate_id: str) -> int:
    """Gate ID의 실행 순서를 반환한다."""
    for index, definition in enumerate(GATES):
        if definition["gate_id"] == gate_id:
            return index
    raise StateTransitionError(f"알 수 없는 Gate입니다: gate_id={gate_id}")


def expected_gate(state: ProjectState) -> GateDefinition:
    """현재 상태에서 실행해야 할 다음 Gate를 계산한다."""
    current_gate = state["current_gate"]
    if current_gate == "NONE":
        return GATES[0]
    next_index = gate_index(current_gate) + 1
    if next_index >= len(GATES):
        raise StateTransitionError("모든 Gate가 이미 통과되었습니다.")
    return GATES[next_index]


def missing_clean_artifacts(
    state: ProjectState,
    required_artifacts: Sequence[str],
) -> list[str]:
    """Gate에 필요하지만 CLEAN이 아닌 Artifact 이름을 반환한다."""
    missing: list[str] = []
    for artifact_name in required_artifacts:
        artifact_state = state["artifacts"].get(artifact_name)
        if artifact_state is None or artifact_state["status"] != "CLEAN":
            missing.append(artifact_name)
    return missing


def gate_required_artifacts_for_project(
    gate_id: str,
    dependency_graph: Mapping[str, object],
    channel: Mapping[str, object],
    production_config: Mapping[str, object],
    artifacts: Mapping[str, object],
) -> tuple[str, ...]:
    """Gate 기본 목록에서 현재 Project에 실제로 필요한 Artifact만 반환한다."""
    gate = GATES[gate_index(gate_id)]
    definitions = dependency_artifacts(dependency_graph)
    return tuple(
        artifact_name
        for artifact_name in gate["required_artifacts"]
        if artifact_required_for_project(
            definitions[artifact_name],
            channel,
            production_config,
            artifacts,
        )
    )


def advance_gate(
    state: ProjectState,
    gate_id: str,
    passed: bool,
    updated_at: str,
    required_artifacts: Sequence[str],
) -> ProjectState:
    """정해진 순서와 CLEAN 조건을 만족할 때만 Project 상태를 전이한다."""
    gate = expected_gate(state)
    if gate["gate_id"] != gate_id:
        raise StateTransitionError(
            f"Gate 순서가 올바르지 않습니다: expected={gate['gate_id']}, actual={gate_id}"
        )
    next_state = deepcopy(state)
    next_state["updated_at"] = updated_at
    if not passed:
        next_state["state"] = "BLOCKED"
        return next_state

    missing = missing_clean_artifacts(state, required_artifacts)
    if missing:
        raise StateTransitionError(
            f"Gate 필수 Artifact가 CLEAN이 아닙니다: gate={gate_id}, artifacts={missing}"
        )
    next_state["current_gate"] = gate_id
    next_state["state"] = gate["target_state"]
    if gate_id == "GATE-13":
        next_state["readiness"]["artifact_status"] = "ARTIFACT_COMPLETE"
        next_state["readiness"]["contract_status"] = "CONTRACT_VALIDATED"
        next_state["readiness"]["editorial_status"] = "EDITORIAL_REVIEW_REQUIRED"
    return next_state
