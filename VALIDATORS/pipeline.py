"""v1.3 전체 Project Artifact를 검증하는 Production Gate 파이프라인."""

from collections.abc import Mapping, Sequence
from copy import deepcopy
from pathlib import Path
from typing import cast

from VALIDATORS.causal_validation import validate_causal_graph
from VALIDATORS.channel_validation import validate_channel_consistency
from VALIDATORS.continuity import validate_continuity
from VALIDATORS.dependency import dependency_artifacts
from VALIDATORS.editorial import validate_editorial_review
from VALIDATORS.exceptions import ConfigurationError, InputFileReadError
from VALIDATORS.fact_validation import validate_fact_integrity
from VALIDATORS.io import load_json_object
from VALIDATORS.models import GateStatus, ProductionValidationReport, ValidationIssue
from VALIDATORS.novelty import (
    build_story_fingerprint,
    evaluate_novelty,
    variation_precheck_source_hash,
)
from VALIDATORS.presentation_validation import (
    validate_presentation_design,
    validate_production_presentation,
    validate_script_integrity_v2,
)
from VALIDATORS.reference_validation import (
    build_story_element_profile,
    validate_reference_collision,
)
from VALIDATORS.schema_validation import collect_schema_errors
from VALIDATORS.story_validation import (
    validate_reference_profile_alignment,
    validate_story_dna_semantics,
    validate_user_case_constraints,
)

ArtifactContent = Mapping[str, object] | str


def make_pipeline_issue(
    code: str,
    message: str,
    artifact: str,
    context: dict[str, object],
) -> ValidationIssue:
    """Production Pipeline 문제를 공통 형식으로 생성한다."""
    return ValidationIssue(
        severity="ERROR",
        code=code,
        message=message,
        artifact=artifact,
        context=context,
    )


def read_text(path: Path) -> str:
    """UTF-8 텍스트 Artifact를 읽고 구체적 오류를 발생시킨다."""
    try:
        return path.read_text(encoding="utf-8")
    except OSError as error:
        raise InputFileReadError(
            f"텍스트 Artifact를 읽지 못했습니다: path={path}, detail={error}"
        ) from error


def load_project_artifacts(
    project_path: Path,
    dependency_graph: Mapping[str, object],
) -> dict[str, ArtifactContent]:
    """Dependency Graph에 선언된 모든 Project Artifact를 디스크에서 읽는다."""
    artifacts: dict[str, ArtifactContent] = {}
    for artifact_name, definition in dependency_artifacts(dependency_graph).items():
        relative_path = definition.get("path")
        if not isinstance(relative_path, str):
            raise ConfigurationError(
                f"Artifact path 문자열이 필요합니다: artifact={artifact_name}"
            )
        artifact_path = project_path / relative_path
        if artifact_path.suffix == ".json":
            artifacts[artifact_name] = load_json_object(artifact_path)
        else:
            artifacts[artifact_name] = read_text(artifact_path)
    return artifacts


def artifact_document(
    artifacts: Mapping[str, ArtifactContent],
    artifact_name: str,
) -> Mapping[str, object]:
    """JSON Artifact를 객체로 읽고 형식이 다르면 실패한다."""
    value = artifacts.get(artifact_name)
    if not isinstance(value, Mapping):
        raise ConfigurationError(f"JSON Artifact 객체가 필요합니다: artifact={artifact_name}")
    return value


def artifact_text(
    artifacts: Mapping[str, ArtifactContent],
    artifact_name: str,
) -> str:
    """Text Artifact를 문자열로 읽고 형식이 다르면 실패한다."""
    value = artifacts.get(artifact_name)
    if not isinstance(value, str):
        raise ConfigurationError(f"Text Artifact가 필요합니다: artifact={artifact_name}")
    return value


def schema_issues(
    document: Mapping[str, object],
    schema: Mapping[str, object],
    artifact: str,
) -> list[ValidationIssue]:
    """JSON Schema 오류를 Production Gate 공통 문제 형식으로 변환한다."""
    return [
        make_pipeline_issue(
            "ARTIFACT_SCHEMA_VIOLATION",
            error["message"],
            artifact,
            error["context"],
        )
        for error in collect_schema_errors(document, schema, artifact)
    ]


def nonempty_list_issues(
    document: Mapping[str, object],
    key: str,
    artifact: str,
) -> list[ValidationIssue]:
    """핵심 Artifact 배열이 비어 있지 않은지 검사한다."""
    value = document.get(key)
    if isinstance(value, list) and value:
        return []
    return [
        make_pipeline_issue(
            "REQUIRED_ARTIFACT_CONTENT_MISSING",
            "Production Gate에 필요한 배열 내용이 비어 있습니다.",
            artifact,
            {"field": key},
        )
    ]


def nonempty_string_issues(
    document: Mapping[str, object],
    keys: Sequence[str],
    artifact: str,
) -> list[ValidationIssue]:
    """핵심 Artifact 문자열 필드가 채워졌는지 검사한다."""
    missing = [
        key
        for key in keys
        if not isinstance(document.get(key), str) or not str(document.get(key)).strip()
    ]
    if not missing:
        return []
    return [
        make_pipeline_issue(
            "REQUIRED_ARTIFACT_CONTENT_MISSING",
            "Production Gate에 필요한 문자열 내용이 비어 있습니다.",
            artifact,
            {"fields": missing},
        )
    ]


def validate_compatibility_gate(
    compatibility_report: Mapping[str, object],
) -> list[ValidationIssue]:
    """Compatibility가 PASS인지 검사한다."""
    if compatibility_report.get("compatibility") == "PASS":
        return []
    return [
        make_pipeline_issue(
            "COMPATIBILITY_NOT_PASSED",
            "Channel Compatibility가 PASS가 아닙니다.",
            "00_PROJECT/compatibility_report.json",
            {"compatibility": compatibility_report.get("compatibility")},
        )
    ]


def validate_project_ids(
    artifacts: Mapping[str, ArtifactContent],
    project_id: str,
) -> list[ValidationIssue]:
    """모든 JSON Artifact가 동일한 Project ID를 사용하는지 검사한다."""
    mismatches = sorted(
        artifact_name
        for artifact_name, content in artifacts.items()
        if isinstance(content, Mapping) and content.get("project_id") != project_id
    )
    if not mismatches:
        return []
    return [
        make_pipeline_issue(
            "PROJECT_ID_MISMATCH",
            "JSON Artifact의 Project ID가 Production Config와 다릅니다.",
            "00_PROJECT/production_config.json",
            {"project_id": project_id, "artifacts": mismatches},
        )
    ]


def validate_project_configuration(
    manifest: Mapping[str, object],
    production_config: Mapping[str, object],
    story_document: Mapping[str, object],
    channel: Mapping[str, object],
) -> list[ValidationIssue]:
    """Manifest, Config, Story, Channel의 공통 식별 설정을 교차 검사한다."""
    comparisons = {
        "standard_version": (
            manifest.get("standard_version"),
            production_config.get("standard_version"),
        ),
        "channel_id": (
            manifest.get("channel_id"),
            production_config.get("channel_id"),
            channel.get("channel_id"),
        ),
        "story_source_mode": (
            manifest.get("story_source_mode"),
            production_config.get("story_source_mode"),
            story_document.get("story_source_mode"),
        ),
    }
    mismatches = sorted(
        field
        for field, values in comparisons.items()
        if not all(isinstance(value, str) for value in values)
        or any(value != values[0] for value in values[1:])
    )
    if not mismatches:
        return []
    return [
        make_pipeline_issue(
            "PROJECT_CONFIGURATION_MISMATCH",
            "Project Manifest, Production Config, Story 또는 Channel 설정이 다릅니다.",
            "00_PROJECT/project_manifest.json",
            {"fields": mismatches},
        )
    ]


def validate_variation_gate(
    candidates_document: Mapping[str, object],
    channel: Mapping[str, object],
) -> list[ValidationIssue]:
    """최소 후보 수와 승인 후보의 존재를 검사한다."""
    candidates = candidates_document.get("candidates")
    approved_id = candidates_document.get("approved_candidate_id")
    capabilities = channel.get("capabilities")
    if not isinstance(capabilities, Mapping):
        raise ConfigurationError("channel.capabilities 객체가 필요합니다.")
    variation_policy = capabilities.get("STORY_VARIATION_POLICY")
    if not isinstance(variation_policy, Mapping):
        raise ConfigurationError("STORY_VARIATION_POLICY 객체가 필요합니다.")
    minimum = variation_policy.get("minimum_candidates")
    if not isinstance(minimum, int) or isinstance(minimum, bool):
        raise ConfigurationError("minimum_candidates 정수가 필요합니다.")

    issues: list[ValidationIssue] = []
    if not isinstance(candidates, list) or len(candidates) < minimum:
        issues.append(
            make_pipeline_issue(
                "VARIATION_CANDIDATES_INSUFFICIENT",
                "Channel이 요구하는 최소 Variation 후보 수를 충족하지 못했습니다.",
                "00_PROJECT/variation_candidates.json",
                {
                    "minimum": minimum,
                    "actual": len(candidates) if isinstance(candidates, list) else 0,
                },
            )
        )
        return issues

    candidate_ids = {
        candidate.get("candidate_id")
        for candidate in candidates
        if isinstance(candidate, Mapping)
    }
    if not isinstance(approved_id, str) or approved_id not in candidate_ids:
        issues.append(
            make_pipeline_issue(
                "VARIATION_APPROVAL_MISSING",
                "승인된 Variation 후보 ID가 후보군에 없습니다.",
                "00_PROJECT/variation_candidates.json",
                {"approved_candidate_id": approved_id},
            )
        )
    return issues


def validate_variation_precheck(
    candidates_document: Mapping[str, object],
    precheck_document: Mapping[str, object],
) -> list[ValidationIssue]:
    """Novelty Precheck가 현재 승인 후보를 PASS했는지 검사한다."""
    expected_hash = variation_precheck_source_hash(candidates_document)
    issues_value = precheck_document.get("issues")
    if not isinstance(issues_value, list):
        raise ConfigurationError("novelty_precheck.issues 배열이 필요합니다.")
    issues = list(cast(list[ValidationIssue], issues_value))
    if precheck_document.get("source_hash") != expected_hash:
        issues.append(
            make_pipeline_issue(
                "STALE_VARIATION_NOVELTY_PRECHECK",
                "Novelty Precheck가 현재 승인 후보에서 생성되지 않았습니다.",
                "08_QA/novelty_precheck.json",
                {},
            )
        )
    if (
        precheck_document.get("approved_candidate_id")
        != candidates_document.get("approved_candidate_id")
        or precheck_document.get("result") != "PASS"
    ):
        issues.append(
            make_pipeline_issue(
                "VARIATION_NOVELTY_PRECHECK_NOT_PASSED",
                "현재 승인 Variation이 Novelty Precheck를 통과하지 못했습니다.",
                "08_QA/novelty_precheck.json",
                {
                    "approved_candidate_id": candidates_document.get(
                        "approved_candidate_id"
                    )
                },
            )
        )
    return issues


def story_dimension_value(story_dna: Mapping[str, object], dimension: str) -> object:
    """복합 Engine을 포함한 Story DNA Dimension 값을 후보 비교 형식으로 읽는다."""
    value = story_dna.get(dimension)
    if not isinstance(value, Mapping):
        return value
    if dimension == "pressure_engine":
        return value.get("source")
    return value.get("primary")


def validate_variation_alignment(
    candidates_document: Mapping[str, object],
    story_document: Mapping[str, object],
) -> list[ValidationIssue]:
    """승인 후보와 Story DNA 차이는 Dimension별 사유가 있을 때만 허용한다."""
    approved_id = candidates_document.get("approved_candidate_id")
    candidates = candidates_document.get("candidates")
    story_dna = story_document.get("story_dna")
    if not isinstance(approved_id, str) or not isinstance(candidates, list):
        return []
    if not isinstance(story_dna, Mapping):
        return []
    approved = next(
        (
            candidate
            for candidate in candidates
            if isinstance(candidate, Mapping)
            and candidate.get("candidate_id") == approved_id
        ),
        None,
    )
    if not isinstance(approved, Mapping):
        return []
    selection = approved.get("selection")
    if not isinstance(selection, Mapping):
        raise ConfigurationError("승인 Variation의 selection 객체가 필요합니다.")
    overrides = story_document.get("variation_overrides")
    override_dimensions = set(overrides) if isinstance(overrides, Mapping) else set()
    override_reason = story_document.get("override_reason")
    mismatches = sorted(
        dimension
        for dimension, selected_value in selection.items()
        if isinstance(dimension, str)
        and story_dimension_value(story_dna, dimension) != selected_value
        and dimension not in override_dimensions
    )
    if not mismatches:
        return []
    reason_present = isinstance(override_reason, str) and bool(override_reason.strip())
    return [
        make_pipeline_issue(
            "UNDECLARED_VARIATION_OVERRIDE",
            "승인 Variation과 다른 Story DNA Dimension에는 명시적 Override가 필요합니다.",
            "00_PROJECT/story_dna.json",
            {"dimensions": mismatches, "override_reason_present": reason_present},
        )
    ]


def normalize_fingerprint(document: Mapping[str, object]) -> dict[str, object]:
    """비교에 영향을 주지 않는 Schema 링크를 제외한 Fingerprint를 복사한다."""
    normalized = deepcopy(dict(document))
    normalized.pop("$schema", None)
    return normalized


def validate_fingerprint_current(
    story_document: Mapping[str, object],
    beat_sheet: Mapping[str, object],
    causal_graph: Mapping[str, object],
    stored_fingerprint: Mapping[str, object],
) -> list[ValidationIssue]:
    """저장된 Fingerprint가 현재 Story·Beat·Causal Graph에서 다시 계산되는지 검사한다."""
    current = build_story_fingerprint(story_document, beat_sheet, causal_graph)
    if normalize_fingerprint(current) == normalize_fingerprint(stored_fingerprint):
        return []
    return [
        make_pipeline_issue(
            "STALE_STORY_FINGERPRINT",
            "Story Fingerprint가 현재 상위 Artifact와 일치하지 않습니다.",
            "00_PROJECT/story_fingerprint.json",
            {},
        )
    ]


def validate_reference_gate(
    story_document: Mapping[str, object],
    final_script: str,
    story_elements: Mapping[str, object],
    reference_material: Mapping[str, object] | None,
    reference_policy: Mapping[str, object],
) -> list[ValidationIssue]:
    """Source Mode에 따라 Reference Collision Gate를 실행하거나 엄격히 생략한다."""
    source_mode = story_document.get("story_source_mode")
    if source_mode != "REFERENCE_INSPIRED":
        if reference_material is not None:
            raise ConfigurationError(
                "REFERENCE_INSPIRED가 아닌 Project에는 Reference 원문을 전달할 수 없습니다."
            )
        return []
    if reference_material is None:
        raise ConfigurationError(
            "REFERENCE_INSPIRED Project 검증에는 격리된 Reference 원문이 필요합니다."
        )
    report = validate_reference_collision(
        final_script,
        story_elements,
        reference_material,
        reference_policy,
    )
    issues = report.get("issues")
    if not isinstance(issues, list):
        raise ConfigurationError("Reference Collision Report issues 배열이 필요합니다.")
    return list(issues)


def production_text_issues(
    artifacts: Mapping[str, ArtifactContent],
) -> list[ValidationIssue]:
    """다섯 가지 Production 인계 문서가 실제 내용을 갖는지 검사한다."""
    issues: list[ValidationIssue] = []
    for artifact_name in (
        "shooting_script",
        "narration",
        "production_panel_reaction_script",
        "subtitle_script",
        "edit_script",
    ):
        content = artifact_text(artifacts, artifact_name)
        if not content.strip():
            issues.append(
                make_pipeline_issue(
                    "PRODUCTION_ARTIFACT_EMPTY",
                    "Production 인계 문서가 비어 있습니다.",
                    artifact_name,
                    {},
                )
            )
    return issues


def gate_status(issues: Sequence[ValidationIssue]) -> GateStatus:
    """Gate 문제 목록을 PASS 또는 FAIL로 변환한다."""
    return "FAIL" if issues else "PASS"


def run_production_validation(
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
    """Compatibility부터 Production 인계까지 14개 Gate를 모두 판정한다."""
    project_manifest = artifact_document(artifacts, "project_manifest")
    compatibility = artifact_document(artifacts, "compatibility_report")
    production_config = artifact_document(artifacts, "production_config")
    reference_profile = artifact_document(artifacts, "reference_profile")
    variation_candidates = artifact_document(artifacts, "variation_candidates")
    novelty_precheck = artifact_document(artifacts, "novelty_precheck")
    story_document = artifact_document(artifacts, "story_dna")
    fingerprint = artifact_document(artifacts, "story_fingerprint")
    case_input = artifact_document(artifacts, "case_input")
    facts = artifact_document(artifacts, "facts")
    sources = artifact_document(artifacts, "sources")
    claim_evidence = artifact_document(artifacts, "claim_evidence")
    characters = artifact_document(artifacts, "characters")
    relationships = artifact_document(artifacts, "relationships")
    knowledge_matrix = artifact_document(artifacts, "knowledge_matrix")
    actual_timeline = artifact_document(artifacts, "actual_timeline")
    viewer_timeline = artifact_document(artifacts, "viewer_timeline")
    audience_belief = artifact_document(artifacts, "audience_belief")
    clue_matrix = artifact_document(artifacts, "clue_matrix")
    hypothesis_ledger = artifact_document(artifacts, "hypothesis_ledger")
    causal_graph = artifact_document(artifacts, "causal_graph")
    beat_sheet = artifact_document(artifacts, "beat_sheet")
    retention_plan = artifact_document(artifacts, "retention_plan")
    scene_cards = artifact_document(artifacts, "scene_cards")
    panel_cast = artifact_document(artifacts, "panel_cast")
    reaction_segments = artifact_document(artifacts, "reaction_segments")
    presentation_plan = artifact_document(artifacts, "presentation_plan")
    drama_script = artifact_text(artifacts, "drama_script")
    narration_script = artifact_text(artifacts, "narration_script")
    panel_reaction_script = artifact_text(artifacts, "panel_reaction_script")
    draft_script = artifact_text(artifacts, "draft_script")
    final_script = artifact_text(artifacts, "final_script")
    editorial_review = artifact_document(artifacts, "editorial_review")
    project_id = production_config.get("project_id")
    if not isinstance(project_id, str):
        raise ConfigurationError("production_config.project_id 문자열이 필요합니다.")

    gate_00 = [
        *validate_compatibility_gate(compatibility),
        *validate_project_ids(artifacts, project_id),
        *validate_project_configuration(
            project_manifest,
            production_config,
            story_document,
            channel,
        ),
    ]
    gate_01 = [
        *validate_variation_gate(variation_candidates, channel),
        *validate_variation_precheck(variation_candidates, novelty_precheck),
    ]
    gate_02 = [
        *schema_issues(story_document, story_schema, "00_PROJECT/story_dna.json"),
        *validate_story_dna_semantics(story_document, reference_policy),
        *validate_user_case_constraints(production_config, story_document),
        *validate_reference_profile_alignment(story_document, reference_profile),
        *validate_variation_alignment(variation_candidates, story_document),
    ]
    gate_03 = [
        *nonempty_string_issues(
            case_input,
            ("central_mystery", "final_truth", "causal_truth"),
            "01_CASE/case_input.json",
        ),
        *nonempty_list_issues(facts, "facts", "01_CASE/facts.json"),
    ]
    if story_document.get("story_source_mode") in {
        "TRUE_STORY",
        "INSPIRED_BY_TRUE_EVENTS",
    }:
        gate_03.extend(nonempty_list_issues(sources, "sources", "01_CASE/sources.json"))
        gate_03.extend(
            nonempty_list_issues(
                claim_evidence,
                "claims",
                "01_CASE/claim_evidence.json",
            )
        )
        gate_03.extend(
            validate_fact_integrity(
                story_document.get("story_source_mode"),
                facts,
                sources,
                claim_evidence,
            )
        )
    gate_04 = [
        *nonempty_list_issues(characters, "characters", "02_CHARACTER/characters.json"),
        *nonempty_list_issues(
            relationships,
            "relationships",
            "02_CHARACTER/relationships.json",
        ),
        *nonempty_list_issues(
            knowledge_matrix,
            "knowledge_events",
            "02_CHARACTER/knowledge_matrix.json",
        ),
    ]
    gate_05 = [
        *nonempty_list_issues(
            actual_timeline,
            "events",
            "03_TIMELINE/actual_timeline.json",
        ),
        *nonempty_list_issues(
            viewer_timeline,
            "reveals",
            "03_TIMELINE/viewer_timeline.json",
        ),
        *nonempty_list_issues(
            audience_belief,
            "belief_states",
            "03_TIMELINE/audience_belief_timeline.json",
        ),
        *nonempty_list_issues(clue_matrix, "clues", "04_MYSTERY/clue_matrix.json"),
        *nonempty_list_issues(
            hypothesis_ledger,
            "hypotheses",
            "04_MYSTERY/hypothesis_ledger.json",
        ),
        *nonempty_list_issues(causal_graph, "nodes", "04_MYSTERY/causal_graph.json"),
        *nonempty_list_issues(causal_graph, "edges", "04_MYSTERY/causal_graph.json"),
        *validate_causal_graph(causal_graph),
    ]
    gate_06 = [
        *nonempty_list_issues(beat_sheet, "beats", "05_STORY/beat_sheet.json"),
        *nonempty_list_issues(
            retention_plan,
            "checkpoints",
            "05_STORY/retention_plan.json",
        ),
    ]
    gate_07 = [
        *nonempty_list_issues(scene_cards, "scenes", "06_SCENE/scene_cards.json"),
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
            presentation_plan,
            presentation_schemas["presentation_plan"],
            "06_SCENE/presentation_plan.json",
        ),
        *validate_presentation_design(
            panel_cast,
            reaction_segments,
            presentation_plan,
            scene_cards,
            viewer_timeline,
            facts,
            clue_matrix,
            channel,
            production_config,
        ),
    ]
    gate_08 = validate_script_integrity_v2(
        presentation_plan,
        reaction_segments,
        scene_cards,
        viewer_timeline,
        audience_belief,
        actual_timeline,
        drama_script,
        narration_script,
        panel_reaction_script,
        draft_script,
        final_script,
    )
    continuity_report = validate_continuity(
        production_config,
        characters,
        facts,
        knowledge_matrix,
        actual_timeline,
        clue_matrix,
        beat_sheet,
        scene_cards,
    )
    continuity_issues = continuity_report.get("issues")
    if not isinstance(continuity_issues, list):
        raise ConfigurationError("Continuity Report issues 배열이 필요합니다.")
    gate_09 = list(continuity_issues)
    novelty_report = evaluate_novelty(fingerprint, story_history, novelty_thresholds)
    novelty_issues = novelty_report.get("issues")
    if not isinstance(novelty_issues, list):
        raise ConfigurationError("Novelty Report issues 배열이 필요합니다.")
    gate_10 = [
        *schema_issues(
            fingerprint,
            fingerprint_schema,
            "00_PROJECT/story_fingerprint.json",
        ),
        *validate_fingerprint_current(
            story_document,
            beat_sheet,
            causal_graph,
            fingerprint,
        ),
        *list(novelty_issues),
    ]
    elements = build_story_element_profile(
        project_id,
        story_document,
        case_input,
        characters,
        relationships,
        actual_timeline,
        clue_matrix,
        causal_graph,
        beat_sheet,
        final_script,
    )
    gate_11 = validate_reference_gate(
        story_document,
        final_script,
        elements,
        reference_material,
        reference_policy,
    )
    gate_12 = validate_channel_consistency(
        channel,
        story_document,
        production_config,
        presentation_plan,
    )
    gate_13 = [
        *production_text_issues(artifacts),
        *validate_production_presentation(
            presentation_plan,
            reaction_segments,
            artifact_text(artifacts, "production_panel_reaction_script"),
            artifact_text(artifacts, "edit_script"),
        ),
        *validate_editorial_review(editorial_review, project_id),
    ]
    gate_groups = (
        gate_00,
        gate_01,
        gate_02,
        gate_03,
        gate_04,
        gate_05,
        gate_06,
        gate_07,
        gate_08,
        gate_09,
        gate_10,
        gate_11,
        gate_12,
        gate_13,
    )
    gate_results: dict[str, GateStatus] = {}
    blocked = False
    for index, issues in enumerate(gate_groups):
        gate_id = f"GATE-{index:02d}"
        if blocked:
            gate_results[gate_id] = "NOT_RUN"
            continue
        status = gate_status(issues)
        gate_results[gate_id] = status
        blocked = status == "FAIL"
    all_issues = [issue for issues in gate_groups for issue in issues]
    return ProductionValidationReport(
        schema_family="validation-report",
        schema_version="1.0.0",
        project_id=project_id,
        result="FAIL" if all_issues else "PASS",
        gate_results=gate_results,
        issues=all_issues,
    )
