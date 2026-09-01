"""v1.3 전체 Project Artifact를 검증하는 Production Gate 파이프라인."""

from collections.abc import Mapping, Sequence
from copy import deepcopy
from pathlib import Path
from typing import cast

from VALIDATORS.candidate_approval import validate_candidate_approval
from VALIDATORS.candidate_eligibility import validate_candidate_eligibility
from VALIDATORS.candidate_evaluation import validate_candidate_evaluation
from VALIDATORS.candidate_event_briefs import (
    approved_event_brief,
    validate_candidate_event_briefs,
    validate_candidate_event_case_projection,
)
from VALIDATORS.candidate_projection import (
    validate_approved_candidate_projection,
    validate_final_story_constraints,
    validate_projection_contract_coverage,
)
from VALIDATORS.causal_validation import validate_causal_graph
from VALIDATORS.channel_policy_v2 import (
    build_channel_policy_inputs,
    validate_channel_policy_v2,
)
from VALIDATORS.channel_validation import validate_channel_consistency
from VALIDATORS.compatibility import channel_dna_sha256, parse_semantic_version
from VALIDATORS.continuity import validate_continuity
from VALIDATORS.crime_event import (
    validate_channel_crime_evidence,
    validate_crime_event_contract,
    validate_crime_event_traceability,
    validate_crime_role_bindings,
    validate_crime_script_realization_report,
    validate_scene_crime_realization,
    validate_script_crime_realization,
    validate_truth_basis,
)
from VALIDATORS.dependency import (
    artifact_required_for_project,
    dependency_artifacts,
)
from VALIDATORS.editorial import (
    editorial_artifact_hashes,
    explicit_crime_runtime_evidence_issues,
    runtime_evidence_issues,
    validate_editorial_crime_assessments,
    validate_editorial_realization_evidence,
    validate_editorial_review,
)
from VALIDATORS.exceptions import (
    ConfigurationError,
    InputFileReadError,
    InvalidSemanticVersionError,
)
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
from VALIDATORS.production_footprint import (
    validate_final_production_footprint,
    validate_production_footprint,
)
from VALIDATORS.project_constraints import project_constraint_compiler_issues
from VALIDATORS.reference_validation import (
    build_story_element_profile,
    validate_reference_collision,
)
from VALIDATORS.scene_realization import (
    validate_channel_realization_evidence,
    validate_narration_realization,
    validate_panel_design_realization,
    validate_panel_script_density,
    validate_primary_story_engine,
    validate_psychological_arc,
    validate_scene_coverage,
    validate_script_realization,
    validate_script_realization_report,
)
from VALIDATORS.schema_validation import collect_schema_errors
from VALIDATORS.source_truth import (
    source_truth_configuration_issues,
    source_truth_requires_evidence,
)
from VALIDATORS.source_truth_contract import (
    validate_source_subject_mapping,
    validate_source_truth_contract_integrity,
    validate_truth_characters,
    validate_truth_dimensions,
    validate_truth_events,
)
from VALIDATORS.story_validation import (
    validate_reference_profile_alignment,
    validate_story_dna_semantics,
    validate_user_case_constraints,
)
from VALIDATORS.variation_registry import variation_runtime_binding_issues

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
    channel: Mapping[str, object],
) -> dict[str, ArtifactContent]:
    """Project Pin에서 필수인 모든 Artifact와 기존 선택 Artifact를 읽는다."""
    production_config = load_json_object(project_path / "00_PROJECT" / "production_config.json")
    definitions = dependency_artifacts(dependency_graph)
    existing_artifacts = load_existing_project_artifacts(project_path, dependency_graph)
    artifact_names = [
        artifact_name
        for artifact_name, definition in definitions.items()
        if artifact_required_for_project(
            definition,
            channel,
            production_config,
            existing_artifacts,
        )
        or (
            isinstance(definition.get("path"), str)
            and (project_path / cast(str, definition["path"])).is_file()
        )
    ]
    return load_selected_project_artifacts(
        project_path,
        dependency_graph,
        artifact_names,
    )


def load_selected_project_artifacts(
    project_path: Path,
    dependency_graph: Mapping[str, object],
    artifact_names: Sequence[str],
) -> dict[str, ArtifactContent]:
    """지정된 Project Artifact만 디스크에서 엄격하게 읽는다."""
    definitions = dependency_artifacts(dependency_graph)
    artifacts: dict[str, ArtifactContent] = {}
    for artifact_name in artifact_names:
        definition = definitions.get(artifact_name)
        if definition is None:
            raise ConfigurationError(
                f"Dependency Graph Artifact 정의가 없습니다: artifact={artifact_name}"
            )
        relative_path = definition.get("path")
        if not isinstance(relative_path, str):
            raise ConfigurationError(f"Artifact path 문자열이 필요합니다: artifact={artifact_name}")
        artifact_path = project_path / relative_path
        if artifact_path.suffix == ".json":
            artifacts[artifact_name] = load_json_object(artifact_path)
        else:
            artifacts[artifact_name] = read_text(artifact_path)
    return artifacts


def load_existing_project_artifacts(
    project_path: Path,
    dependency_graph: Mapping[str, object],
) -> dict[str, ArtifactContent]:
    """아직 생성되지 않은 미래 Artifact를 제외하고 현재 파일만 읽는다."""
    definitions = dependency_artifacts(dependency_graph)
    existing_names = [
        artifact_name
        for artifact_name, definition in definitions.items()
        if isinstance(definition.get("path"), str)
        and (project_path / cast(str, definition["path"])).is_file()
    ]
    return load_selected_project_artifacts(
        project_path,
        dependency_graph,
        existing_names,
    )


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


def optional_artifact_text(
    artifacts: Mapping[str, ArtifactContent],
    artifact_name: str,
) -> str:
    """이전 1.1 Project에서 없을 수 있는 v2 Text Artifact를 읽는다."""
    value = artifacts.get(artifact_name)
    if value is None:
        return ""
    if not isinstance(value, str):
        raise ConfigurationError(f"Text Artifact가 필요합니다: artifact={artifact_name}")
    return value


def optional_artifact_document(
    artifacts: Mapping[str, ArtifactContent],
    artifact_name: str,
) -> Mapping[str, object]:
    """현재 Project에서 선택 JSON Artifact가 없으면 빈 객체를 반환한다."""
    value = artifacts.get(artifact_name)
    if value is None:
        return {}
    if not isinstance(value, Mapping):
        raise ConfigurationError(f"JSON Artifact 객체가 필요합니다: artifact={artifact_name}")
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


def optional_schema_issues(
    artifacts: Mapping[str, ArtifactContent],
    artifact_name: str,
    schema: Mapping[str, object],
    artifact_path: str,
) -> list[ValidationIssue]:
    """선택 v2 Artifact가 존재할 때만 Schema를 검증한다."""
    if artifact_name not in artifacts:
        return []
    return schema_issues(
        artifact_document(artifacts, artifact_name),
        schema,
        artifact_path,
    )


def required_channel_artifact_issues(
    artifacts: Mapping[str, ArtifactContent],
    production_config: Mapping[str, object],
    channel: Mapping[str, object],
    artifact_names: Sequence[str],
) -> list[ValidationIssue]:
    """공통 Artifact Requirement Predicate로 누락을 보고한다."""
    graph = load_json_object(
        Path(__file__).resolve().parents[1] / "STANDARD" / "dependency_graph.json"
    )
    definitions = dependency_artifacts(graph)
    return [
        make_pipeline_issue(
            "REQUIRED_CHANNEL_ARTIFACT_MISSING",
            "Channel Content Version이 요구하는 First-class Artifact가 없습니다.",
            artifact_name,
            {"artifact_name": artifact_name},
        )
        for artifact_name in artifact_names
        if artifact_name not in artifacts
        and artifact_required_for_project(
            definitions[artifact_name], channel, production_config, artifacts
        )
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


def validate_compatibility_binding_current(
    compatibility_report: Mapping[str, object],
    production_config: Mapping[str, object],
    channel: Mapping[str, object],
) -> list[ValidationIssue]:
    """저장된 Compatibility Report가 현재 Project 핀과 DNA를 가리키는지 검사한다."""
    summary = compatibility_report.get("channel")
    summary_mapping = summary if isinstance(summary, Mapping) else {}
    expected_version = production_config.get("channel_content_version")
    report_version = summary_mapping.get("content_version")
    actual_version = channel.get("content_version")
    versions_match = False
    if all(isinstance(value, str) for value in (expected_version, report_version, actual_version)):
        try:
            versions_match = (
                parse_semantic_version(str(expected_version))
                == parse_semantic_version(str(report_version))
                == parse_semantic_version(str(actual_version))
            )
        except InvalidSemanticVersionError:
            versions_match = False
    issues: list[ValidationIssue] = []
    if not versions_match:
        issues.append(
            make_pipeline_issue(
                "CHANNEL_CONTENT_VERSION_MISMATCH",
                "Compatibility Report, Project 핀, 실제 Channel DNA 버전이 다릅니다.",
                "00_PROJECT/compatibility_report.json",
                {
                    "project": expected_version,
                    "report": report_version,
                    "channel": actual_version,
                },
            )
        )
    expected_hash = summary_mapping.get("channel_dna_sha256")
    actual_hash = channel_dna_sha256(channel)
    if expected_hash != actual_hash:
        issues.append(
            make_pipeline_issue(
                "CHANNEL_DNA_HASH_MISMATCH",
                "Compatibility Report의 SHA-256과 현재 Channel DNA가 다릅니다.",
                "00_PROJECT/compatibility_report.json",
                {"expected": expected_hash, "actual": actual_hash},
            )
        )
    return issues


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
        "channel_content_version": (
            production_config.get("channel_content_version"),
            channel.get("content_version"),
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


def validate_project_setup(
    manifest: Mapping[str, object],
    production_config: Mapping[str, object],
    channel: Mapping[str, object],
) -> list[ValidationIssue]:
    """Story 생성 전 Manifest, Config, Channel의 식별 설정을 교차 검사한다."""
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
        "channel_content_version": (
            production_config.get("channel_content_version"),
            channel.get("content_version"),
        ),
        "story_source_mode": (
            manifest.get("story_source_mode"),
            production_config.get("story_source_mode"),
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
            "Project Manifest, Production Config 또는 Channel 설정이 다릅니다.",
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
        candidate.get("candidate_id") for candidate in candidates if isinstance(candidate, Mapping)
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
    """Novelty Precheck가 전체 후보와 현재 승인 후보를 PASS했는지 검사한다."""
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
    approved_id = candidates_document.get("approved_candidate_id")
    raw_results = precheck_document.get("candidate_results")
    approved_result = None
    if isinstance(raw_results, list):
        approved_result = next(
            (
                result.get("result")
                for result in raw_results
                if isinstance(result, Mapping) and result.get("candidate_id") == approved_id
            ),
            None,
        )
    if precheck_document.get("result") != "PASS" or approved_result != "PASS":
        issues.append(
            make_pipeline_issue(
                "VARIATION_NOVELTY_PRECHECK_NOT_PASSED",
                "현재 승인 Variation이 Novelty Precheck를 통과하지 못했습니다.",
                "08_QA/novelty_precheck.json",
                {
                    "approved_candidate_id": approved_id,
                    "approved_candidate_result": approved_result,
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
            if isinstance(candidate, Mapping) and candidate.get("candidate_id") == approved_id
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
    story_dimensions = {
        "mystery_type",
        "architecture",
        "protagonist_role",
        "perspective",
        "timeline_style",
        "incident_type",
        "setting",
        "culprit_structure",
        "primary_twist",
        "relationship_engine",
        "pressure_engine",
        "dramatic_engine",
    }
    mismatches = sorted(
        dimension
        for dimension, selected_value in selection.items()
        if isinstance(dimension, str)
        and dimension in story_dimensions
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
    production_config: Mapping[str, object],
    channel: Mapping[str, object],
) -> list[ValidationIssue]:
    """Project Version에서 필수인 Production 인계 문서 내용을 검사한다."""
    artifact_names = [
        "shooting_script",
        "narration",
        "production_panel_reaction_script",
        "subtitle_script",
        "edit_script",
    ]
    graph = load_json_object(
        Path(__file__).resolve().parents[1] / "STANDARD" / "dependency_graph.json"
    )
    definition = dependency_artifacts(graph)["production_expert_analysis_script"]
    if (
        artifact_required_for_project(definition, channel, production_config, artifacts)
        or "production_expert_analysis_script" in artifacts
    ):
        artifact_names.append("production_expert_analysis_script")
    issues: list[ValidationIssue] = []
    for artifact_name in artifact_names:
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
    project_constraints = artifact_document(artifacts, "project_constraints")
    reference_profile = artifact_document(artifacts, "reference_profile")
    variation_candidates = artifact_document(artifacts, "variation_candidates")
    candidate_event_briefs = optional_artifact_document(
        artifacts,
        "candidate_event_briefs",
    )
    candidate_event_brief_schema = presentation_schemas.get("candidate_event_briefs")
    candidate_eligibility = artifact_document(artifacts, "candidate_eligibility")
    candidate_evaluation = artifact_document(artifacts, "candidate_evaluation")
    candidate_approval = artifact_document(artifacts, "candidate_approval")
    novelty_precheck = artifact_document(artifacts, "novelty_precheck")
    story_document = artifact_document(artifacts, "story_dna")
    fingerprint = artifact_document(artifacts, "story_fingerprint")
    case_input = artifact_document(artifacts, "case_input")
    facts = artifact_document(artifacts, "facts")
    crime_event_contract = optional_artifact_document(
        artifacts,
        "crime_event_contract",
    )
    sources = artifact_document(artifacts, "sources")
    claim_evidence = artifact_document(artifacts, "claim_evidence")
    verified_fact_ledger = optional_artifact_document(artifacts, "verified_fact_ledger")
    source_subjects = optional_artifact_document(artifacts, "source_subjects")
    verified_event_ledger = optional_artifact_document(artifacts, "verified_event_ledger")
    source_truth_contract = optional_artifact_document(artifacts, "source_truth_contract")
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
    psychological_arc = optional_artifact_document(artifacts, "psychological_arc")
    scene_cards = artifact_document(artifacts, "scene_cards")
    production_footprint = optional_artifact_document(artifacts, "production_footprint")
    panel_cast = artifact_document(artifacts, "panel_cast")
    reaction_segments = artifact_document(artifacts, "reaction_segments")
    presentation_plan = artifact_document(artifacts, "presentation_plan")
    drama_script = artifact_text(artifacts, "drama_script")
    narration_script = artifact_text(artifacts, "narration_script")
    panel_reaction_script = artifact_text(artifacts, "panel_reaction_script")
    expert_analysis_script = optional_artifact_text(
        artifacts,
        "expert_analysis_script",
    )
    draft_script = artifact_text(artifacts, "draft_script")
    final_script = artifact_text(artifacts, "final_script")
    script_realization_report = optional_artifact_document(
        artifacts,
        "script_realization_report",
    )
    channel_consistency_report = optional_artifact_document(
        artifacts,
        "channel_consistency_report",
    )
    editorial_review = artifact_document(artifacts, "editorial_review")
    production_manifest = optional_artifact_document(artifacts, "production_manifest")
    project_id = production_config.get("project_id")
    if not isinstance(project_id, str):
        raise ConfigurationError("production_config.project_id 문자열이 필요합니다.")
    source_truth_bundle_issues = (
        validate_source_truth_contract_integrity(
            source_truth_contract,
            sources,
            claim_evidence,
            verified_fact_ledger,
            source_subjects,
            verified_event_ledger,
        )
        if source_truth_requires_evidence(production_config.get("source_truth_classification"))
        else []
    )
    gate_00 = [
        *validate_compatibility_gate(compatibility),
        *validate_compatibility_binding_current(
            compatibility,
            production_config,
            channel,
        ),
        *validate_project_ids(artifacts, project_id),
        *validate_project_configuration(
            project_manifest,
            production_config,
            story_document,
            channel,
        ),
        *source_truth_configuration_issues(production_config),
        *validate_projection_contract_coverage(
            presentation_schemas["variation_catalog"],
            presentation_schemas["candidate_projection_contract"],
        ),
        *project_constraint_compiler_issues(
            project_constraints,
            presentation_schemas["variation_catalog"],
            presentation_schemas["candidate_projection_contract"],
        ),
    ]
    gate_01 = [
        *validate_variation_gate(variation_candidates, channel),
        *required_channel_artifact_issues(
            artifacts,
            production_config,
            channel,
            ("candidate_event_briefs",),
        ),
        *(
            optional_schema_issues(
                artifacts,
                "candidate_event_briefs",
                candidate_event_brief_schema,
                "00_PROJECT/candidate_event_briefs.json",
            )
            if candidate_event_brief_schema is not None
            else []
        ),
        *(
            validate_candidate_event_briefs(
                variation_candidates,
                candidate_event_briefs,
            )
            if "candidate_event_briefs" in artifacts
            else []
        ),
        *schema_issues(
            candidate_eligibility,
            presentation_schemas["candidate_eligibility"],
            "08_QA/candidate_eligibility.json",
        ),
        *schema_issues(
            candidate_evaluation,
            presentation_schemas["candidate_evaluation"],
            "00_PROJECT/candidate_evaluation.json",
        ),
        *schema_issues(
            candidate_approval,
            presentation_schemas["candidate_approval"],
            "00_PROJECT/candidate_approval.json",
        ),
        *schema_issues(
            novelty_precheck,
            presentation_schemas["novelty_precheck"],
            "08_QA/novelty_precheck.json",
        ),
        *validate_candidate_evaluation(
            variation_candidates,
            candidate_evaluation,
            novelty_precheck,
            candidate_eligibility,
        ),
        *validate_candidate_eligibility(
            production_config,
            project_constraints,
            channel,
            variation_candidates,
            novelty_precheck,
            candidate_eligibility,
        ),
        *validate_candidate_approval(
            production_config,
            variation_candidates,
            novelty_precheck,
            candidate_eligibility,
            candidate_evaluation,
            candidate_approval,
        ),
        *validate_variation_precheck(variation_candidates, novelty_precheck),
        *variation_runtime_binding_issues(
            production_config,
            variation_candidates,
            presentation_schemas["variation_runtime"],
        ),
    ]
    if source_truth_requires_evidence(production_config.get("source_truth_classification")):
        gate_01.extend(source_truth_bundle_issues)
    gate_02 = [
        *schema_issues(story_document, story_schema, "00_PROJECT/story_dna.json"),
        *validate_story_dna_semantics(story_document, reference_policy),
        *validate_user_case_constraints(production_config, story_document),
        *validate_reference_profile_alignment(story_document, reference_profile),
        *validate_variation_alignment(variation_candidates, story_document),
        *validate_primary_story_engine(channel, story_document, case_input),
        *validate_approved_candidate_projection(
            production_config,
            variation_candidates,
            presentation_schemas["candidate_projection_contract"],
            {"story_dna": story_document},
            channel,
        ),
    ]
    if source_truth_requires_evidence(production_config.get("source_truth_classification")):
        gate_02.extend(
            validate_truth_dimensions(
                source_truth_contract,
                story_document,
                None,
                None,
            )
        )
    gate_03 = [
        *nonempty_string_issues(
            case_input,
            ("central_mystery", "final_truth", "causal_truth"),
            "01_CASE/case_input.json",
        ),
        *nonempty_list_issues(facts, "facts", "01_CASE/facts.json"),
        *validate_candidate_event_case_projection(
            variation_candidates,
            candidate_event_briefs,
            case_input,
            facts,
        ),
        *(
            validate_truth_basis(
                production_config,
                approved_brief,
                facts,
            )
            if (
                approved_brief := approved_event_brief(
                    variation_candidates,
                    candidate_event_briefs,
                )
            )
            is not None
            else []
        ),
        *required_channel_artifact_issues(
            artifacts,
            production_config,
            channel,
            ("crime_psychology", "source_disclosure", "clinical_labels"),
        ),
        *optional_schema_issues(
            artifacts,
            "crime_psychology",
            presentation_schemas["crime_psychology"],
            "01_CASE/crime_psychology.json",
        ),
        *optional_schema_issues(
            artifacts,
            "source_disclosure",
            presentation_schemas["source_disclosure"],
            "01_CASE/source_disclosure.json",
        ),
        *optional_schema_issues(
            artifacts,
            "clinical_labels",
            presentation_schemas["clinical_labels"],
            "01_CASE/clinical_labels.json",
        ),
    ]
    if source_truth_requires_evidence(production_config.get("source_truth_classification")):
        gate_03.extend(source_truth_bundle_issues)
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
                production_config.get("source_truth_classification"),
                facts,
                sources,
                claim_evidence,
                verified_fact_ledger,
            )
        )
        gate_03.extend(
            validate_truth_dimensions(
                source_truth_contract,
                story_document,
                case_input,
                optional_artifact_document(artifacts, "crime_psychology"),
            )
        )
    gate_03.extend(
        validate_approved_candidate_projection(
            production_config,
            variation_candidates,
            presentation_schemas["candidate_projection_contract"],
            {
                "story_dna": story_document,
                "case_input": case_input,
                **(
                    {"crime_event_contract": artifacts["crime_event_contract"]}
                    if "crime_event_contract" in artifacts
                    else {}
                ),
                **(
                    {"crime_psychology": artifacts["crime_psychology"]}
                    if "crime_psychology" in artifacts
                    else {}
                ),
            },
            channel,
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
        *required_channel_artifact_issues(
            artifacts,
            production_config,
            channel,
            ("crime_event_contract",),
        ),
        *optional_schema_issues(
            artifacts,
            "crime_event_contract",
            presentation_schemas["crime_event_contract"],
            "01_CASE/crime_event_contract.json",
        ),
        *validate_crime_event_contract(
            channel,
            production_config,
            variation_candidates,
            crime_event_contract,
            facts,
            candidate_event_briefs,
        ),
        *validate_crime_role_bindings(crime_event_contract, characters),
    ]
    if source_truth_requires_evidence(production_config.get("source_truth_classification")):
        gate_04.extend(source_truth_bundle_issues)
        gate_04.extend(
            validate_source_subject_mapping(
                source_subjects,
                characters,
                optional_artifact_document(artifacts, "clinical_labels"),
            )
        )
        gate_04.extend(
            validate_truth_characters(
                source_truth_contract,
                source_subjects,
                characters,
                relationships,
            )
        )
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
        *validate_crime_event_traceability(
            crime_event_contract,
            characters,
            case_input,
            facts,
            actual_timeline,
            causal_graph,
            viewer_timeline,
        ),
        *validate_approved_candidate_projection(
            production_config,
            variation_candidates,
            presentation_schemas["candidate_projection_contract"],
            {
                "story_dna": story_document,
                "case_input": case_input,
                "clue_matrix": clue_matrix,
                **(
                    {"crime_psychology": artifacts["crime_psychology"]}
                    if "crime_psychology" in artifacts
                    else {}
                ),
            },
            channel,
        ),
    ]
    if source_truth_requires_evidence(production_config.get("source_truth_classification")):
        gate_05.extend(source_truth_bundle_issues)
        gate_05.extend(
            validate_truth_events(
                source_truth_contract,
                verified_event_ledger,
                characters,
                actual_timeline,
                causal_graph,
            )
        )
    gate_06 = [
        *nonempty_list_issues(beat_sheet, "beats", "05_STORY/beat_sheet.json"),
        *nonempty_list_issues(
            retention_plan,
            "checkpoints",
            "05_STORY/retention_plan.json",
        ),
        *required_channel_artifact_issues(
            artifacts,
            production_config,
            channel,
            ("psychological_arc",),
        ),
        *optional_schema_issues(
            artifacts,
            "psychological_arc",
            presentation_schemas["psychological_arc"],
            "05_STORY/psychological_arc.json",
        ),
        *validate_psychological_arc(channel, psychological_arc),
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
        *required_channel_artifact_issues(
            artifacts,
            production_config,
            channel,
            ("expert_segments",),
        ),
        *optional_schema_issues(
            artifacts,
            "expert_segments",
            presentation_schemas["expert_segments"],
            "06_SCENE/expert_segments.json",
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
        *validate_scene_coverage(
            channel,
            psychological_arc,
            scene_cards,
            presentation_plan,
        ),
        *validate_narration_realization(channel, presentation_plan),
        *validate_panel_design_realization(
            channel,
            reaction_segments,
            presentation_plan,
        ),
        *validate_production_footprint(
            project_constraints,
            production_footprint,
            scene_cards,
            characters,
            actual_timeline,
            variation_candidates,
        ),
        *validate_scene_crime_realization(
            channel,
            crime_event_contract,
            scene_cards,
            presentation_plan,
        ),
    ]
    gate_08 = [
        *required_channel_artifact_issues(
            artifacts,
            production_config,
            channel,
            ("expert_analysis_script",),
        ),
        *validate_script_integrity_v2(
            presentation_plan,
            reaction_segments,
            scene_cards,
            viewer_timeline,
            audience_belief,
            actual_timeline,
            drama_script,
            narration_script,
            panel_reaction_script,
            expert_analysis_script,
            draft_script,
            final_script,
        ),
        *validate_script_realization(
            channel,
            psychological_arc,
            scene_cards,
            presentation_plan,
            final_script,
        ),
        *validate_script_crime_realization(
            channel,
            crime_event_contract,
            scene_cards,
            presentation_plan,
            reaction_segments,
            viewer_timeline,
            final_script,
        ),
        *validate_panel_script_density(
            channel,
            reaction_segments,
            panel_reaction_script,
        ),
    ]
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
    gate_09 = [
        *list(continuity_issues),
        *required_channel_artifact_issues(
            artifacts,
            production_config,
            channel,
            ("script_realization_report",),
        ),
        *optional_schema_issues(
            artifacts,
            "script_realization_report",
            presentation_schemas["script_realization_report"],
            "08_QA/script_realization_report.json",
        ),
        *validate_script_realization_report(
            channel,
            psychological_arc,
            scene_cards,
            presentation_plan,
            final_script,
            script_realization_report,
        ),
        *validate_crime_script_realization_report(
            channel,
            project_id,
            crime_event_contract,
            scene_cards,
            presentation_plan,
            reaction_segments,
            viewer_timeline,
            final_script,
            script_realization_report,
        ),
    ]
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
    gate_12.extend(
        validate_channel_policy_v2(
            channel,
            build_channel_policy_inputs(artifacts),
        )
    )
    gate_12.extend(
        validate_panel_design_realization(
            channel,
            reaction_segments,
            presentation_plan,
        )
    )
    gate_12.extend(
        validate_panel_script_density(
            channel,
            reaction_segments,
            panel_reaction_script,
        )
    )
    gate_12.extend(
        validate_channel_realization_evidence(
            channel,
            psychological_arc,
            script_realization_report,
            channel_consistency_report,
        )
    )
    gate_12.extend(
        validate_channel_crime_evidence(
            channel,
            script_realization_report,
            channel_consistency_report,
        )
    )
    gate_12.extend(
        validate_approved_candidate_projection(
            production_config,
            variation_candidates,
            presentation_schemas["candidate_projection_contract"],
            artifacts,
            channel,
        )
    )
    gate_12.extend(
        validate_final_story_constraints(
            project_constraints,
            variation_candidates,
            presentation_schemas["candidate_projection_contract"],
            artifacts,
        )
    )
    gate_13 = [
        *required_channel_artifact_issues(
            artifacts,
            production_config,
            channel,
            ("production_expert_analysis_script",),
        ),
        *production_text_issues(artifacts, production_config, channel),
        *validate_production_presentation(
            presentation_plan,
            reaction_segments,
            artifact_text(artifacts, "production_panel_reaction_script"),
            artifact_text(artifacts, "edit_script"),
        ),
        *validate_editorial_review(
            editorial_review,
            project_id,
            editorial_artifact_hashes(artifacts),
            artifacts,
        ),
        *validate_editorial_realization_evidence(
            channel,
            editorial_review,
            psychological_arc,
        ),
        *validate_editorial_crime_assessments(
            channel,
            editorial_review,
            crime_event_contract,
            artifacts,
        ),
        *runtime_evidence_issues(
            editorial_review,
            presentation_plan,
            panel_reaction_script,
        ),
        *explicit_crime_runtime_evidence_issues(channel, editorial_review),
        *validate_final_production_footprint(
            project_constraints,
            production_footprint,
            production_manifest,
            scene_cards,
            characters,
            actual_timeline,
            variation_candidates,
            artifact_text(artifacts, "shooting_script"),
        ),
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
