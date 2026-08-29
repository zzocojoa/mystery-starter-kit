"""LLM이 필요하지 않은 Runtime Task를 기존 Validator로 실행."""

from collections.abc import Mapping
from pathlib import Path

from RUNTIME.errors import RuntimeExecutionError
from RUNTIME.gate_control import validation_report_through
from VALIDATORS.candidate_evaluation import validate_candidate_evaluation
from VALIDATORS.channel_policy_v2 import (
    build_channel_policy_inputs,
    validate_channel_policy_v2,
)
from VALIDATORS.channel_registry import (
    registered_channel_relative_path,
    resolve_project_channel,
)
from VALIDATORS.channel_validation import validate_channel_consistency
from VALIDATORS.cli import evaluate_compatibility_documents
from VALIDATORS.compatibility import (
    evaluate_channel_binding,
    make_project_compatibility_report,
)
from VALIDATORS.continuity import validate_continuity
from VALIDATORS.exceptions import StoryLibraryError
from VALIDATORS.io import load_json_object
from VALIDATORS.library import novelty_history
from VALIDATORS.novelty import (
    build_story_fingerprint,
    evaluate_novelty,
    evaluate_variation_precheck,
)
from VALIDATORS.pipeline import ArtifactContent, load_existing_project_artifacts
from VALIDATORS.reference_validation import (
    build_story_element_profile,
    sanitize_reference_profile,
    validate_reference_collision,
)
from VALIDATORS.variation import (
    apply_user_case_constraints,
    approve_variation_candidate,
    generate_variation_candidates,
)


def combined_artifacts(
    project_path: Path,
    dependency_graph: Mapping[str, object],
    overlay: Mapping[str, object],
) -> dict[str, ArtifactContent]:
    """Canonical Artifact 위에 현재 Gate의 검증 전 출력을 겹친다."""
    artifacts = load_existing_project_artifacts(project_path, dependency_graph)
    for artifact_name, content in overlay.items():
        if not isinstance(content, Mapping | str):
            raise RuntimeExecutionError(
                "RUNTIME_CONFIGURATION_ERROR",
                False,
                "TASK",
                "Runtime Overlay Artifact 형식이 올바르지 않습니다.",
                None,
                artifact_name,
                {},
            )
        artifacts[artifact_name] = content
    return artifacts


def mapping_artifact(
    artifacts: Mapping[str, ArtifactContent],
    artifact_name: str,
) -> Mapping[str, object]:
    """Core Task 입력 JSON Artifact를 엄격하게 읽는다."""
    value = artifacts.get(artifact_name)
    if not isinstance(value, Mapping):
        raise RuntimeExecutionError(
            "RUNTIME_CONFIGURATION_ERROR",
            False,
            "TASK",
            "Core Task JSON Artifact가 객체가 아닙니다.",
            None,
            artifact_name,
            {},
        )
    return value


def text_artifact(
    artifacts: Mapping[str, ArtifactContent],
    artifact_name: str,
) -> str:
    """Core Task 입력 Text Artifact를 엄격하게 읽는다."""
    value = artifacts.get(artifact_name)
    if not isinstance(value, str):
        raise RuntimeExecutionError(
            "RUNTIME_CONFIGURATION_ERROR",
            False,
            "TASK",
            "Core Task Text Artifact가 문자열이 아닙니다.",
            None,
            artifact_name,
            {},
        )
    return value


def story_history(repository_root: Path) -> list[Mapping[str, object]]:
    """Abandoned를 제외한 Novelty Index 비교 기록을 읽는다."""
    index = load_json_object(repository_root / "STORY_LIBRARY" / "novelty_index.json")
    try:
        return novelty_history(index)
    except StoryLibraryError as error:
        raise RuntimeExecutionError(
            "RUNTIME_CONFIGURATION_ERROR",
            False,
            "TASK",
            "Novelty Index Entry 배열이 올바르지 않습니다.",
            None,
            None,
            {"detail": str(error)},
        ) from error


def runtime_validation_inputs(
    repository_root: Path,
) -> tuple[
    Mapping[str, object],
    Mapping[str, object],
    Mapping[str, object],
    Mapping[str, Mapping[str, object]],
    Mapping[str, object],
    Mapping[str, object],
]:
    """Gate 검증에 필요한 Channel, Schema, Policy, Threshold를 반환한다."""
    return (
        load_json_object(repository_root / "CHANNELS" / "mystery_main" / "channel_dna.json"),
        load_json_object(repository_root / "STANDARD" / "schemas" / "story_dna.schema.json"),
        load_json_object(
            repository_root / "STANDARD" / "schemas" / "story_fingerprint.schema.json"
        ),
        {
            "candidate_evaluation": load_json_object(
                repository_root
                / "STANDARD"
                / "schemas"
                / "candidate_evaluation.schema.json"
            ),
            "novelty_precheck": load_json_object(
                repository_root
                / "STANDARD"
                / "schemas"
                / "novelty_precheck.schema.json"
            ),
            "crime_psychology": load_json_object(
                repository_root / "STANDARD" / "schemas" / "crime_psychology.schema.json"
            ),
            "source_disclosure": load_json_object(
                repository_root / "STANDARD" / "schemas" / "source_disclosure.schema.json"
            ),
            "clinical_labels": load_json_object(
                repository_root / "STANDARD" / "schemas" / "clinical_labels.schema.json"
            ),
            "expert_segments": load_json_object(
                repository_root / "STANDARD" / "schemas" / "expert_segments.schema.json"
            ),
            "panel_cast": load_json_object(
                repository_root / "STANDARD" / "schemas" / "panel_cast.schema.json"
            ),
            "reaction_segments": load_json_object(
                repository_root
                / "STANDARD"
                / "schemas"
                / "reaction_segments.schema.json"
            ),
            "presentation_plan": load_json_object(
                repository_root
                / "STANDARD"
                / "schemas"
                / "presentation_plan.schema.json"
            ),
        },
        load_json_object(repository_root / "STANDARD" / "reference_policy.json"),
        load_json_object(repository_root / "STANDARD" / "novelty_thresholds.json"),
    )


def runtime_validation_inputs_for_project(
    repository_root: Path,
    production_config: Mapping[str, object],
    channel_override: Path | None,
) -> tuple[
    Mapping[str, object],
    Mapping[str, object],
    Mapping[str, object],
    Mapping[str, Mapping[str, object]],
    Mapping[str, object],
    Mapping[str, object],
]:
    """Project 핀으로 Channel을 해석해 Gate 검증 입력을 반환한다."""
    channel, _manifest, _channel_path = resolve_project_channel(
        repository_root,
        production_config,
        channel_override,
    )
    (
        _active_channel,
        story_schema,
        fingerprint_schema,
        presentation_schemas,
        reference_policy,
        novelty_thresholds,
    ) = runtime_validation_inputs(repository_root)
    return (
        channel,
        story_schema,
        fingerprint_schema,
        presentation_schemas,
        reference_policy,
        novelty_thresholds,
    )


def project_compatibility_output(
    repository_root: Path,
    artifacts: Mapping[str, ArtifactContent],
) -> dict[str, object]:
    """Project ID가 포함된 GATE-00 Compatibility Report를 생성한다."""
    manifest = mapping_artifact(artifacts, "project_manifest")
    project_id = manifest.get("project_id")
    if not isinstance(project_id, str):
        raise RuntimeExecutionError(
            "RUNTIME_CONFIGURATION_ERROR",
            False,
            "TASK",
            "Project Manifest ID가 없습니다.",
            "project.compatibility",
            "project_manifest",
            {},
        )
    production_config = mapping_artifact(artifacts, "production_config")
    contract_path = repository_root / "STANDARD" / "compatibility_contract.json"
    defaults_path = repository_root / "STANDARD" / "standard_defaults.json"
    channel, channel_manifest, channel_path = resolve_project_channel(
        repository_root,
        production_config,
        None,
    )
    report = evaluate_compatibility_documents(
        load_json_object(contract_path),
        load_json_object(defaults_path),
        channel,
        load_json_object(
            repository_root / "STANDARD" / "schemas" / "compatibility_contract.schema.json"
        ),
        load_json_object(
            repository_root / "STANDARD" / "schemas" / "standard_defaults.schema.json"
        ),
        load_json_object(repository_root / "STANDARD" / "schemas" / "channel_dna.schema.json"),
        str(contract_path),
        str(defaults_path),
        str(channel_path),
    )
    report = evaluate_channel_binding(
        report,
        production_config,
        channel_manifest,
        channel,
    )
    pinned_version = production_config.get("channel_content_version")
    if not isinstance(pinned_version, str):
        raise RuntimeExecutionError(
            "RUNTIME_CONFIGURATION_ERROR",
            False,
            "TASK",
            "production_config.channel_content_version 문자열이 필요합니다.",
            "project.compatibility",
            "production_config",
            {},
        )
    relative_path = registered_channel_relative_path(
        channel_manifest,
        pinned_version,
    )
    return dict(
        make_project_compatibility_report(
            project_id,
            report,
            relative_path,
        )
    )


def reference_profile_output(
    project_id: str,
    repository_root: Path,
    source_mode: object,
    reference_source: Path | None,
) -> dict[str, object]:
    """Reference Raw를 외부 Provider에 보내지 않고 정제 Profile만 생성한다."""
    if source_mode != "REFERENCE_INSPIRED":
        if reference_source is not None:
            raise RuntimeExecutionError(
                "DATA_POLICY_VIOLATION",
                False,
                "TASK",
                "Reference Mode가 아닌 Project에 Raw Source를 전달할 수 없습니다.",
                "reference.sanitize_profile",
                None,
                {"story_source_mode": source_mode},
            )
        return {
            "project_id": project_id,
            "mode": "NONE",
            "reference_id": None,
            "allowed_style_features": [],
            "prohibited_story_content": [],
        }
    if reference_source is None:
        raise RuntimeExecutionError(
            "RUNTIME_CONFIGURATION_ERROR",
            False,
            "TASK",
            "REFERENCE_INSPIRED Runtime에는 격리된 Reference Source가 필요합니다.",
            "reference.sanitize_profile",
            None,
            {},
        )
    sanitized = sanitize_reference_profile(
        load_json_object(reference_source),
        load_json_object(repository_root / "STANDARD" / "reference_policy.json"),
    )
    return {"project_id": project_id, "mode": "REFERENCE_INSPIRED", **sanitized}


def variation_output(
    project_id: str,
    repository_root: Path,
    production_config: Mapping[str, object],
) -> dict[str, object]:
    """결정론적 후보 다섯 개를 승인하지 않은 상태로 생성한다."""
    candidates = generate_variation_candidates(
        project_id,
        f"{project_id}:runtime-v1",
        5,
        load_json_object(repository_root / "STANDARD" / "variation_catalog.json"),
    )
    return apply_user_case_constraints(candidates, production_config)


def approved_variation_output(
    variations: Mapping[str, object],
    candidate_evaluation: Mapping[str, object],
    novelty_precheck: Mapping[str, object],
) -> dict[str, object]:
    """검증된 평가가 추천한 Candidate 하나를 승인한다."""
    issues = validate_candidate_evaluation(
        variations,
        candidate_evaluation,
        novelty_precheck,
    )
    if issues:
        first_issue = issues[0]
        raise RuntimeExecutionError(
            "GATE_REJECTED",
            False,
            "TASK",
            first_issue["message"],
            "variation.approve",
            "candidate_evaluation",
            {
                "validation_code": first_issue["code"],
                **first_issue["context"],
            },
        )
    candidate_id = candidate_evaluation.get("recommended_candidate_id")
    if not isinstance(candidate_id, str):
        raise RuntimeExecutionError(
            "GATE_REJECTED",
            False,
            "TASK",
            "Candidate 평가 추천 ID가 없습니다.",
            "variation.approve",
            "candidate_evaluation",
            {"validation_code": "CANDIDATE_EVALUATION_REQUIRED"},
        )
    approved = approve_variation_candidate(variations, candidate_id)
    approval_issues = validate_candidate_evaluation(
        approved,
        candidate_evaluation,
        novelty_precheck,
    )
    if approval_issues:
        first_issue = approval_issues[0]
        raise RuntimeExecutionError(
            "GATE_REJECTED",
            False,
            "TASK",
            first_issue["message"],
            "variation.approve",
            "candidate_evaluation",
            {
                "validation_code": first_issue["code"],
                **first_issue["context"],
            },
        )
    return approved


def evidence_outputs(
    project_id: str,
    source_mode: object,
) -> dict[str, object]:
    """Fiction은 빈 Evidence를 만들고 사실 기반 Mode는 명시적 Human 입력을 요구한다."""
    if source_mode in {"TRUE_STORY", "INSPIRED_BY_TRUE_EVENTS"}:
        raise RuntimeExecutionError(
            "HUMAN_APPROVAL_REQUIRED",
            False,
            "TASK",
            "사실 기반 Project에는 검증된 Source와 Claim-Evidence 입력이 필요합니다.",
            "reference.build_evidence",
            None,
            {"story_source_mode": source_mode},
        )
    return {
        "sources": {"project_id": project_id, "sources": []},
        "claim_evidence": {"project_id": project_id, "claims": []},
        "source_disclosure": {
            "schema_family": "source-disclosure",
            "schema_version": "1.0.0",
            "project_id": project_id,
            "internal_mode": "ORIGINAL_FICTION",
            "audience_label_text": "본 이야기는 창작입니다.",
        },
        "clinical_labels": {
            "schema_family": "clinical-labels",
            "schema_version": "1.0.0",
            "project_id": project_id,
            "labels": [],
        },
    }


def reference_report_output(
    project_id: str,
    repository_root: Path,
    artifacts: Mapping[str, ArtifactContent],
    reference_source: Path | None,
) -> dict[str, object]:
    """Reference Mode에서만 Raw를 Core 메모리에서 비교하고 원문은 보고서에 남기지 않는다."""
    story = mapping_artifact(artifacts, "story_dna")
    if story.get("story_source_mode") != "REFERENCE_INSPIRED":
        if reference_source is not None:
            raise RuntimeExecutionError(
                "DATA_POLICY_VIOLATION",
                False,
                "TASK",
                "Reference Mode가 아닌 Project에 Raw Source를 전달할 수 없습니다.",
                "reference.collision",
                None,
                {},
            )
        return {
            "project_id": project_id,
            "reference_id": None,
            "result": "PASS",
            "lexical_collision_count": 0,
            "matched_story_element_categories": [],
            "issues": [],
        }
    if reference_source is None:
        raise RuntimeExecutionError(
            "RUNTIME_CONFIGURATION_ERROR",
            False,
            "TASK",
            "Reference Collision에는 격리된 Raw Source가 필요합니다.",
            "reference.collision",
            None,
            {},
        )
    elements = build_story_element_profile(
        project_id,
        story,
        mapping_artifact(artifacts, "case_input"),
        mapping_artifact(artifacts, "characters"),
        mapping_artifact(artifacts, "relationships"),
        mapping_artifact(artifacts, "actual_timeline"),
        mapping_artifact(artifacts, "clue_matrix"),
        mapping_artifact(artifacts, "causal_graph"),
        mapping_artifact(artifacts, "beat_sheet"),
        text_artifact(artifacts, "final_script"),
    )
    return validate_reference_collision(
        text_artifact(artifacts, "final_script"),
        elements,
        load_json_object(reference_source),
        load_json_object(repository_root / "STANDARD" / "reference_policy.json"),
    )


def core_task_outputs(
    task_id: str,
    repository_root: Path,
    project_path: Path,
    overlay: Mapping[str, object],
    dependency_graph: Mapping[str, object],
    reference_source: Path | None,
    human_approved: bool,
) -> dict[str, object]:
    """Task ID에 대응하는 결정론적 Core 출력을 반환한다."""
    artifacts = combined_artifacts(project_path, dependency_graph, overlay)
    production_config = mapping_artifact(artifacts, "production_config")
    project_id = production_config.get("project_id")
    if not isinstance(project_id, str):
        raise RuntimeExecutionError(
            "RUNTIME_CONFIGURATION_ERROR",
            False,
            "TASK",
            "Production Config Project ID가 없습니다.",
            task_id,
            "production_config",
            {},
        )
    if task_id == "project.compatibility":
        return {"compatibility_report": project_compatibility_output(repository_root, artifacts)}
    if task_id == "reference.sanitize_profile":
        return {
            "reference_profile": reference_profile_output(
                project_id,
                repository_root,
                production_config.get("story_source_mode"),
                reference_source,
            )
        }
    if task_id == "variation.generate":
        return {
            "variation_candidates": variation_output(
                project_id,
                repository_root,
                production_config,
            )
        }
    if task_id == "novelty.variation_precheck":
        return {
            "novelty_precheck": evaluate_variation_precheck(
                mapping_artifact(artifacts, "variation_candidates"),
                story_history(repository_root),
                load_json_object(repository_root / "STANDARD" / "novelty_thresholds.json"),
            )
        }
    if task_id == "variation.approve":
        return {
            "variation_candidates": approved_variation_output(
                mapping_artifact(artifacts, "variation_candidates"),
                mapping_artifact(artifacts, "candidate_evaluation"),
                mapping_artifact(artifacts, "novelty_precheck"),
            )
        }
    if task_id == "reference.build_evidence":
        return evidence_outputs(project_id, production_config.get("story_source_mode"))
    if task_id == "continuity.deterministic":
        report = validate_continuity(
            production_config,
            mapping_artifact(artifacts, "characters"),
            mapping_artifact(artifacts, "facts"),
            mapping_artifact(artifacts, "knowledge_matrix"),
            mapping_artifact(artifacts, "actual_timeline"),
            mapping_artifact(artifacts, "clue_matrix"),
            mapping_artifact(artifacts, "beat_sheet"),
            mapping_artifact(artifacts, "scene_cards"),
        )
        return {"continuity_report": report}
    if task_id == "novelty.final":
        fingerprint = build_story_fingerprint(
            mapping_artifact(artifacts, "story_dna"),
            mapping_artifact(artifacts, "beat_sheet"),
            mapping_artifact(artifacts, "causal_graph"),
        )
        report = evaluate_novelty(
            fingerprint,
            story_history(repository_root),
            load_json_object(repository_root / "STANDARD" / "novelty_thresholds.json"),
        )
        return {"story_fingerprint": fingerprint, "novelty_report": report}
    if task_id == "reference.collision":
        return {
            "reference_collision_report": reference_report_output(
                project_id,
                repository_root,
                artifacts,
                reference_source,
            )
        }
    if task_id == "channel.consistency":
        channel, _manifest, _channel_path = resolve_project_channel(
            repository_root,
            production_config,
            None,
        )
        issues = validate_channel_consistency(
            channel,
            mapping_artifact(artifacts, "story_dna"),
            production_config,
            mapping_artifact(artifacts, "presentation_plan"),
        )
        issues.extend(
            validate_channel_policy_v2(
                channel,
                build_channel_policy_inputs(artifacts),
            )
        )
        return {
            "channel_consistency_report": {
                "project_id": project_id,
                "result": "FAIL" if issues else "PASS",
                "issues": issues,
            }
        }
    if task_id in {"orchestrator.validation", "production.finalize"}:
        (
            validation_channel,
            story_schema,
            fingerprint_schema,
            presentation_schemas,
            policy,
            thresholds,
        ) = runtime_validation_inputs_for_project(
            repository_root,
            production_config,
            None,
        )
        target_gate = "GATE-12" if task_id == "orchestrator.validation" else "GATE-13"
        validation_report = validation_report_through(
            target_gate,
            artifacts,
            validation_channel,
            story_schema,
            fingerprint_schema,
            presentation_schemas,
            policy,
            thresholds,
            story_history(repository_root),
            load_json_object(reference_source) if reference_source is not None else None,
        )
        return {"validation_report": validation_report}
    raise RuntimeExecutionError(
        "RUNTIME_CONFIGURATION_ERROR",
        False,
        "TASK",
        "구현되지 않은 CORE Task입니다.",
        task_id,
        None,
        {},
    )
