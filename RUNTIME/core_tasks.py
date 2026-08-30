"""LLM이 필요하지 않은 Runtime Task를 기존 Validator로 실행."""

from collections.abc import Mapping
from pathlib import Path

from RUNTIME.errors import RuntimeExecutionError
from RUNTIME.event_store import load_run, utc_now
from RUNTIME.gate_control import validation_report_through
from RUNTIME.human_inputs import current_evidence_input, evidence_artifact_outputs
from RUNTIME.models import RuntimeApproval
from VALIDATORS.candidate_approval import build_candidate_approval
from VALIDATORS.candidate_eligibility import build_candidate_eligibility
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
from VALIDATORS.source_truth import require_source_truth_classification
from VALIDATORS.variation import (
    apply_user_case_constraints,
    approve_variation_candidate,
    generate_variation_candidates_for_project,
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
            "candidate_eligibility": load_json_object(
                repository_root
                / "STANDARD"
                / "schemas"
                / "candidate_eligibility.schema.json"
            ),
            "candidate_approval": load_json_object(
                repository_root
                / "STANDARD"
                / "schemas"
                / "candidate_approval.schema.json"
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
    project_constraints: Mapping[str, object],
    source_case_brief: Mapping[str, object] | None,
) -> dict[str, object]:
    """결정론적 후보 다섯 개를 승인하지 않은 상태로 생성한다."""
    channel, _manifest, _channel_path = resolve_project_channel(
        repository_root,
        production_config,
        None,
    )
    brief = source_case_brief.get("brief") if source_case_brief is not None else None
    seed = brief if isinstance(brief, str) else f"{project_id}:runtime-v1"
    candidates = generate_variation_candidates_for_project(
        project_id,
        seed,
        5,
        load_json_object(repository_root / "STANDARD" / "variation_catalog.json"),
        require_source_truth_classification(production_config),
        production_config,
        project_constraints,
        channel,
    )
    return apply_user_case_constraints(candidates, production_config)


def approved_variation_output(
    variations: Mapping[str, object],
    candidate_evaluation: Mapping[str, object],
    novelty_precheck: Mapping[str, object],
    candidate_eligibility: Mapping[str, object],
) -> tuple[dict[str, object], str]:
    """검증된 평가가 추천한 Candidate 하나를 승인한다."""
    issues = validate_candidate_evaluation(
        variations,
        candidate_evaluation,
        novelty_precheck,
        candidate_eligibility,
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
    return approved, candidate_id


def evidence_outputs(
    project_id: str,
    source_truth: object,
    project_path: Path,
    run_id: str,
    input_hashes: Mapping[str, str],
) -> dict[str, object]:
    """Fiction은 빈 Evidence를 만들고 사실 기반 분류는 검증된 Human 입력을 읽는다."""
    if source_truth in {"VERIFIED_TRUE_CASE", "INSPIRED_BY_TRUE_EVENTS"}:
        human_input = current_evidence_input(
            project_path,
            run_id,
            project_id,
            str(source_truth),
            input_hashes,
        )
        if human_input is None:
            raise RuntimeExecutionError(
                "HUMAN_INPUT_REQUIRED",
                False,
                "TASK",
                "사실 기반 Project에는 현재 Input Hash로 검증된 Evidence 입력이 필요합니다.",
                "reference.intake_evidence",
                None,
                {
                    "source_truth_classification": source_truth,
                    "input_hashes": dict(input_hashes),
                },
            )
        return evidence_artifact_outputs(project_id, human_input)
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


def resolved_clinical_labels_output(
    clinical_labels: Mapping[str, object],
    characters: Mapping[str, object],
) -> dict[str, object]:
    """Evidence Subject ID를 생성된 Character ID에 결정론적으로 연결한다."""
    raw_labels = clinical_labels.get("labels")
    raw_characters = characters.get("characters")
    if not isinstance(raw_labels, list) or not isinstance(raw_characters, list):
        raise RuntimeExecutionError(
            "RUNTIME_CONFIGURATION_ERROR", False, "TASK",
            "Clinical Label 또는 Character 배열이 없습니다.",
            "reference.resolve_clinical_subjects", "clinical_labels", {},
        )
    character_ids = [
        character.get("character_id")
        for character in raw_characters
        if isinstance(character, Mapping) and isinstance(character.get("character_id"), str)
    ]
    labels: list[dict[str, object]] = []
    for raw_label in raw_labels:
        if not isinstance(raw_label, Mapping):
            raise RuntimeExecutionError(
                "RUNTIME_CONFIGURATION_ERROR", False, "TASK",
                "Clinical Label 객체가 손상되었습니다.",
                "reference.resolve_clinical_subjects", "clinical_labels", {},
            )
        label = dict(raw_label)
        source_subject = label.pop("source_subject_id", None)
        if source_subject is not None:
            suffix = str(source_subject).removeprefix("SUBJECT-")
            index = int(suffix) - 1 if suffix.isdigit() else -1
            if index < 0 or index >= len(character_ids):
                raise RuntimeExecutionError(
                    "HUMAN_INPUT_INVALID", False, "TASK",
                    "Evidence Subject를 생성된 Character에 연결할 수 없습니다.",
                    "reference.resolve_clinical_subjects", "clinical_labels",
                    {"source_subject_id": source_subject},
                )
            label["subject_id"] = character_ids[index]
        labels.append(label)
    return {**dict(clinical_labels), "labels": labels}


def core_task_outputs(
    task_id: str,
    repository_root: Path,
    project_path: Path,
    overlay: Mapping[str, object],
    dependency_graph: Mapping[str, object],
    reference_source: Path | None,
    runtime_approval: RuntimeApproval | None,
    run_id: str,
    input_hashes: Mapping[str, str],
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
        source_case_brief = artifacts.get("source_case_brief")
        return {
            "variation_candidates": variation_output(
                project_id,
                repository_root,
                production_config,
                mapping_artifact(artifacts, "project_constraints"),
                source_case_brief if isinstance(source_case_brief, Mapping) else None,
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
    if task_id == "variation.eligibility":
        channel, _manifest, _channel_path = resolve_project_channel(
            repository_root,
            production_config,
            None,
        )
        return {
            "candidate_eligibility": build_candidate_eligibility(
                production_config,
                mapping_artifact(artifacts, "project_constraints"),
                channel,
                mapping_artifact(artifacts, "variation_candidates"),
                mapping_artifact(artifacts, "novelty_precheck"),
            )
        }
    if task_id == "variation.approve":
        variations = mapping_artifact(artifacts, "variation_candidates")
        evaluation = mapping_artifact(artifacts, "candidate_evaluation")
        novelty = mapping_artifact(artifacts, "novelty_precheck")
        eligibility = mapping_artifact(artifacts, "candidate_eligibility")
        approved, _candidate_id = approved_variation_output(
            variations,
            evaluation,
            novelty,
            eligibility,
        )
        return {
            "variation_candidates": approved,
        }
    if task_id == "variation.record_approval":
        variations = mapping_artifact(artifacts, "variation_candidates")
        evaluation = mapping_artifact(artifacts, "candidate_evaluation")
        novelty = mapping_artifact(artifacts, "novelty_precheck")
        selected_candidate_id = variations.get("approved_candidate_id")
        recommended = evaluation.get("recommended_candidate_id")
        if not isinstance(selected_candidate_id, str) or not isinstance(recommended, str):
            raise RuntimeExecutionError(
                "GATE_REJECTED",
                False,
                "TASK",
                "승인 또는 추천 Candidate ID가 없습니다.",
                task_id,
                "candidate_approval",
                {},
            )
        approval_policy = production_config.get("approval_policy")
        if not isinstance(approval_policy, str):
            raise RuntimeExecutionError(
                "RUNTIME_CONFIGURATION_ERROR",
                False,
                "TASK",
                "Candidate Approval Policy가 없습니다.",
                task_id,
                "production_config",
                {},
            )
        actor = "SYSTEM"
        reason = "적격 후보 중 최고 Soft 평가 점수를 자동 승인했습니다."
        approved_at = utc_now()
        if runtime_approval is not None:
            actor = runtime_approval["actor"]
            reason = runtime_approval["reason"]
            approved_at = runtime_approval["created_at"]
        return {
            "candidate_approval": build_candidate_approval(
                project_id,
                selected_candidate_id,
                recommended,
                actor,
                reason,
                approved_at,
                production_config,
                variations,
                novelty,
                mapping_artifact(artifacts, "candidate_eligibility"),
                evaluation,
                approval_policy,
                runtime_approval,
            ),
        }
    if task_id in {
        "reference.intake_evidence",
        "reference.initialize_fiction_evidence",
        "reference.build_source_disclosure",
        "reference.build_clinical_labels",
    }:
        run = load_run(project_path, run_id)
        evidence_state = run["tasks"].get("reference.intake_evidence")
        evidence_hashes = (
            evidence_state["input_hashes"]
            if evidence_state is not None and evidence_state["input_hashes"]
            else input_hashes
        )
        bundle = evidence_outputs(
            project_id,
            production_config.get("source_truth_classification"),
            project_path,
            run_id,
            evidence_hashes,
        )
        selected_outputs = {
            "reference.intake_evidence": (
                "sources", "claim_evidence", "source_case_brief",
                "verified_fact_ledger", "source_disclosure", "clinical_labels",
            ),
            "reference.initialize_fiction_evidence": ("sources", "claim_evidence"),
            "reference.build_source_disclosure": ("source_disclosure",),
            "reference.build_clinical_labels": ("clinical_labels",),
        }
        return {name: bundle[name] for name in selected_outputs[task_id]}
    if task_id == "reference.resolve_clinical_subjects":
        return {
            "clinical_labels": resolved_clinical_labels_output(
                mapping_artifact(artifacts, "clinical_labels"),
                mapping_artifact(artifacts, "characters"),
            )
        }
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
