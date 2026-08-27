"""Staging Overlay에서 기존 결정론적 Validator를 Gate별로 실행."""

from collections.abc import Mapping, Sequence

from VALIDATORS.causal_validation import validate_causal_graph
from VALIDATORS.channel_validation import validate_channel_consistency
from VALIDATORS.continuity import validate_continuity
from VALIDATORS.fact_validation import validate_fact_integrity
from VALIDATORS.models import GateStatus, ProductionValidationReport, ValidationIssue
from VALIDATORS.novelty import evaluate_novelty
from VALIDATORS.pipeline import (
    ArtifactContent,
    artifact_document,
    artifact_text,
    nonempty_list_issues,
    nonempty_string_issues,
    production_text_issues,
    schema_issues,
    validate_compatibility_gate,
    validate_fingerprint_current,
    validate_project_configuration,
    validate_project_ids,
    validate_reference_gate,
    validate_variation_alignment,
    validate_variation_gate,
    validate_variation_precheck,
)
from VALIDATORS.presentation_validation import (
    validate_presentation_design,
    validate_production_presentation,
    validate_script_integrity_v2,
)
from VALIDATORS.reference_validation import build_story_element_profile
from VALIDATORS.state_machine import gate_index
from VALIDATORS.story_validation import (
    validate_reference_profile_alignment,
    validate_story_dna_semantics,
    validate_user_case_constraints,
)


def script_nonempty_issues(artifacts: Mapping[str, ArtifactContent]) -> list[ValidationIssue]:
    """Draft와 Final Script가 비어 있는지 검사한다."""
    issues: list[ValidationIssue] = []
    for artifact_name, artifact_path, code in (
        ("draft_script", "07_SCRIPT/draft_v01.md", "DRAFT_SCRIPT_EMPTY"),
        ("final_script", "07_SCRIPT/final_script.md", "FINAL_SCRIPT_EMPTY"),
    ):
        if artifact_text(artifacts, artifact_name).strip():
            continue
        issues.append(
            ValidationIssue(
                severity="ERROR",
                code=code,
                message="Script Artifact가 비어 있습니다.",
                artifact=artifact_path,
                context={},
            )
        )
    return issues


def validate_gate(
    gate_id: str,
    artifacts: Mapping[str, ArtifactContent],
    channel: Mapping[str, object],
    story_schema: Mapping[str, object],
    fingerprint_schema: Mapping[str, object],
    presentation_schemas: Mapping[str, Mapping[str, object]],
    reference_policy: Mapping[str, object],
    novelty_thresholds: Mapping[str, object],
    story_history: Sequence[Mapping[str, object]],
    reference_material: Mapping[str, object] | None,
) -> list[ValidationIssue]:
    """요청 Gate까지만 필요한 기존 Validator를 실행한다."""
    manifest = artifact_document(artifacts, "project_manifest")
    compatibility = artifact_document(artifacts, "compatibility_report")
    production_config = artifact_document(artifacts, "production_config")
    reference_profile = artifact_document(artifacts, "reference_profile")
    variations = artifact_document(artifacts, "variation_candidates")
    precheck = artifact_document(artifacts, "novelty_precheck")
    story = artifact_document(artifacts, "story_dna")
    project_id = production_config.get("project_id")
    if not isinstance(project_id, str):
        return [
            ValidationIssue(
                severity="ERROR",
                code="PROJECT_ID_MISSING",
                message="Production Config Project ID가 없습니다.",
                artifact="00_PROJECT/production_config.json",
                context={},
            )
        ]
    if gate_id == "GATE-00":
        return [
            *validate_compatibility_gate(compatibility),
            *validate_project_ids(artifacts, project_id),
            *validate_project_configuration(manifest, production_config, story, channel),
        ]
    if gate_id == "GATE-01":
        return [
            *validate_variation_gate(variations, channel),
            *validate_variation_precheck(variations, precheck),
        ]
    if gate_id == "GATE-02":
        return [
            *schema_issues(story, story_schema, "00_PROJECT/story_dna.json"),
            *validate_story_dna_semantics(story, reference_policy),
            *validate_user_case_constraints(production_config, story),
            *validate_reference_profile_alignment(story, reference_profile),
            *validate_variation_alignment(variations, story),
        ]
    case_input = artifact_document(artifacts, "case_input")
    facts = artifact_document(artifacts, "facts")
    sources = artifact_document(artifacts, "sources")
    claims = artifact_document(artifacts, "claim_evidence")
    if gate_id == "GATE-03":
        issues = [
            *nonempty_string_issues(
                case_input,
                ("central_mystery", "final_truth", "causal_truth"),
                "01_CASE/case_input.json",
            ),
            *nonempty_list_issues(facts, "facts", "01_CASE/facts.json"),
        ]
        if story.get("story_source_mode") in {"TRUE_STORY", "INSPIRED_BY_TRUE_EVENTS"}:
            issues.extend(nonempty_list_issues(sources, "sources", "01_CASE/sources.json"))
            issues.extend(nonempty_list_issues(claims, "claims", "01_CASE/claim_evidence.json"))
            issues.extend(
                validate_fact_integrity(story.get("story_source_mode"), facts, sources, claims)
            )
        return issues
    characters = artifact_document(artifacts, "characters")
    relationships = artifact_document(artifacts, "relationships")
    knowledge = artifact_document(artifacts, "knowledge_matrix")
    if gate_id == "GATE-04":
        return [
            *nonempty_list_issues(characters, "characters", "02_CHARACTER/characters.json"),
            *nonempty_list_issues(
                relationships, "relationships", "02_CHARACTER/relationships.json"
            ),
            *nonempty_list_issues(
                knowledge, "knowledge_events", "02_CHARACTER/knowledge_matrix.json"
            ),
        ]
    actual = artifact_document(artifacts, "actual_timeline")
    viewer = artifact_document(artifacts, "viewer_timeline")
    audience = artifact_document(artifacts, "audience_belief")
    clues = artifact_document(artifacts, "clue_matrix")
    hypotheses = artifact_document(artifacts, "hypothesis_ledger")
    causal = artifact_document(artifacts, "causal_graph")
    if gate_id == "GATE-05":
        return [
            *nonempty_list_issues(actual, "events", "03_TIMELINE/actual_timeline.json"),
            *nonempty_list_issues(viewer, "reveals", "03_TIMELINE/viewer_timeline.json"),
            *nonempty_list_issues(
                audience, "belief_states", "03_TIMELINE/audience_belief_timeline.json"
            ),
            *nonempty_list_issues(clues, "clues", "04_MYSTERY/clue_matrix.json"),
            *nonempty_list_issues(hypotheses, "hypotheses", "04_MYSTERY/hypothesis_ledger.json"),
            *nonempty_list_issues(causal, "nodes", "04_MYSTERY/causal_graph.json"),
            *nonempty_list_issues(causal, "edges", "04_MYSTERY/causal_graph.json"),
            *validate_causal_graph(causal),
        ]
    beats = artifact_document(artifacts, "beat_sheet")
    retention = artifact_document(artifacts, "retention_plan")
    if gate_id == "GATE-06":
        return [
            *nonempty_list_issues(beats, "beats", "05_STORY/beat_sheet.json"),
            *nonempty_list_issues(retention, "checkpoints", "05_STORY/retention_plan.json"),
        ]
    scenes = artifact_document(artifacts, "scene_cards")
    panel_cast = artifact_document(artifacts, "panel_cast")
    reaction_segments = artifact_document(artifacts, "reaction_segments")
    presentation = artifact_document(artifacts, "presentation_plan")
    if gate_id == "GATE-07":
        return [
            *nonempty_list_issues(scenes, "scenes", "06_SCENE/scene_cards.json"),
            *schema_issues(
                panel_cast,
                presentation_schemas["panel_cast"],
                "06_SCENE/panel_cast.json",
            ),
            *schema_issues(
                reaction_segments,
                presentation_schemas["reaction_segments"],
                "06_SCENE/reaction_segments.json",
            ),
            *schema_issues(
                presentation,
                presentation_schemas["presentation_plan"],
                "06_SCENE/presentation_plan.json",
            ),
            *validate_presentation_design(
                panel_cast,
                reaction_segments,
                presentation,
                scenes,
                viewer,
                facts,
                clues,
                channel,
                production_config,
            ),
        ]
    if gate_id == "GATE-08":
        return validate_script_integrity_v2(
            presentation,
            reaction_segments,
            scenes,
            viewer,
            audience,
            actual,
            artifact_text(artifacts, "drama_script"),
            artifact_text(artifacts, "narration_script"),
            artifact_text(artifacts, "panel_reaction_script"),
            artifact_text(artifacts, "draft_script"),
            artifact_text(artifacts, "final_script"),
        )
    if gate_id == "GATE-09":
        report = validate_continuity(
            production_config,
            characters,
            facts,
            knowledge,
            actual,
            clues,
            beats,
            scenes,
        )
        report_issues = report.get("issues")
        return list(report_issues) if isinstance(report_issues, list) else []
    fingerprint = artifact_document(artifacts, "story_fingerprint")
    if gate_id == "GATE-10":
        novelty_report = evaluate_novelty(fingerprint, story_history, novelty_thresholds)
        novelty_issues = novelty_report.get("issues")
        return [
            *schema_issues(fingerprint, fingerprint_schema, "00_PROJECT/story_fingerprint.json"),
            *validate_fingerprint_current(story, beats, causal, fingerprint),
            *(list(novelty_issues) if isinstance(novelty_issues, list) else []),
        ]
    final_script = artifact_text(artifacts, "final_script")
    if gate_id == "GATE-11":
        elements = build_story_element_profile(
            project_id,
            story,
            case_input,
            characters,
            relationships,
            actual,
            clues,
            causal,
            beats,
            final_script,
        )
        return validate_reference_gate(
            story,
            final_script,
            elements,
            reference_material,
            reference_policy,
        )
    if gate_id == "GATE-12":
        return validate_channel_consistency(channel, story, production_config, presentation)
    if gate_id == "GATE-13":
        return [
            *production_text_issues(artifacts),
            *validate_production_presentation(
                presentation,
                reaction_segments,
                artifact_text(artifacts, "production_panel_reaction_script"),
                artifact_text(artifacts, "edit_script"),
            ),
        ]
    raise ValueError(f"알 수 없는 Gate입니다: {gate_id}")


def validation_report_through(
    target_gate: str,
    artifacts: Mapping[str, ArtifactContent],
    channel: Mapping[str, object],
    story_schema: Mapping[str, object],
    fingerprint_schema: Mapping[str, object],
    presentation_schemas: Mapping[str, Mapping[str, object]],
    reference_policy: Mapping[str, object],
    novelty_thresholds: Mapping[str, object],
    story_history: Sequence[Mapping[str, object]],
    reference_material: Mapping[str, object] | None,
) -> ProductionValidationReport:
    """GATE-00부터 목표 Gate까지 순차 결과와 모든 Issue를 만든다."""
    target_index = gate_index(target_gate)
    gate_results: dict[str, GateStatus] = {}
    issues: list[ValidationIssue] = []
    blocked = False
    for index in range(14):
        gate_id = f"GATE-{index:02d}"
        if index > target_index or blocked:
            gate_results[gate_id] = "NOT_RUN"
            continue
        gate_issues = validate_gate(
            gate_id,
            artifacts,
            channel,
            story_schema,
            fingerprint_schema,
            presentation_schemas,
            reference_policy,
            novelty_thresholds,
            story_history,
            reference_material,
        )
        status: GateStatus = "FAIL" if gate_issues else "PASS"
        gate_results[gate_id] = status
        issues.extend(gate_issues)
        blocked = status == "FAIL"
    production_config = artifact_document(artifacts, "production_config")
    project_id = production_config.get("project_id")
    return ProductionValidationReport(
        schema_family="validation-report",
        schema_version="1.0.0",
        project_id=project_id if isinstance(project_id, str) else "",
        result="FAIL" if issues else "PASS",
        gate_results=gate_results,
        issues=issues,
    )
