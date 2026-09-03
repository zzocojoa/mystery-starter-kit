"""Project Scaffold, Variation, Production Gate를 실행하는 통합 CLI."""

import argparse
import json
import sys
from collections.abc import Mapping, Sequence
from copy import deepcopy
from datetime import UTC, datetime
from pathlib import Path
from typing import cast
from uuid import uuid4

from RUNTIME.errors import RuntimeExecutionError
from RUNTIME.human_inputs import submit_evidence_input
from RUNTIME.models import RuntimeApproval
from RUNTIME.output_gateway import encoded_artifact
from RUNTIME.transactions import (
    acquire_project_lock,
    commit_gate_transaction,
    release_project_lock,
)
from VALIDATORS.candidate_approval import approval_input_hashes, build_candidate_approval
from VALIDATORS.candidate_eligibility import (
    build_candidate_eligibility_bound,
    validate_candidate_eligibility,
)
from VALIDATORS.candidate_evaluation import document_sha256, validate_candidate_evaluation
from VALIDATORS.change_log import append_change_log, change_log_bytes
from VALIDATORS.channel_registry import (
    registered_channel_relative_path,
    resolve_project_channel,
)
from VALIDATORS.cli import (
    evaluate_compatibility_documents,
    raise_for_configuration_schema_errors,
)
from VALIDATORS.compatibility import (
    evaluate_channel_binding,
    make_project_compatibility_report,
)
from VALIDATORS.config_admission import admit_broadcast_readable_config
from VALIDATORS.crime_event import explicit_crime_policy
from VALIDATORS.dependency import (
    artifact_hash,
    dependency_artifacts,
    invalidate_artifact_dependents,
    mark_artifact_clean,
    reconcile_project_state_artifacts,
    transitive_dependents,
)
from VALIDATORS.editorial import (
    EDITORIAL_REVIEWED_ARTIFACTS,
    approve_editorial_review,
    editorial_artifact_hashes,
    finalize_production_ready,
)
from VALIDATORS.exceptions import (
    ConfigurationError,
    GateTransactionError,
    StarterKitError,
)
from VALIDATORS.gate_transaction import (
    audit_artifact_names,
    audit_project,
    full_validation_report,
    process_conformance,
    return_task_to_owner,
    task_abort,
    task_open,
    task_status,
    task_submit,
    trace_records,
)
from VALIDATORS.io import load_json_object, write_json_object
from VALIDATORS.legacy_migration import (
    default_project_constraints,
    migrated_legacy_variations,
    migration_review_reasons,
    migration_status,
    normalized_legacy_state,
)
from VALIDATORS.library import (
    make_history_record,
    novelty_history,
    register_story_fingerprint,
)
from VALIDATORS.library_store import (
    sync_novelty_gate,
    sync_novelty_production_ready,
    sync_novelty_revision,
)
from VALIDATORS.models import ProjectCompatibilityReport, ProjectState, ValidationIssue
from VALIDATORS.novelty import evaluate_variation_precheck_bound
from VALIDATORS.pipeline import load_selected_project_artifacts
from VALIDATORS.reference_validation import sanitize_reference_profile
from VALIDATORS.scaffold import create_project_scaffold
from VALIDATORS.schema_validation import collect_schema_errors
from VALIDATORS.source_truth import require_source_truth_classification
from VALIDATORS.state_machine import GATES, advance_gate, gate_index
from VALIDATORS.variation import (
    approve_variation_candidate,
    generate_eligible_candidate_pool,
)
from VALIDATORS.variation_registry import resolve_variation_runtime

ROOT = Path.cwd().resolve()
NOVELTY_CODES = {
    "CAUSAL_HARD_COLLISION",
    "CAUSAL_SEMANTIC_COLLISION",
    "STORY_SIMILARITY_EXCEEDED",
}
REFERENCE_CODES = {
    "REFERENCE_LEXICAL_COLLISION",
    "REFERENCE_STORY_ELEMENT_COLLISION",
}


def utc_now() -> str:
    """Project 상태 기록에 사용할 UTC ISO 시각을 반환한다."""
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def build_parser() -> argparse.ArgumentParser:
    """통합 CLI 명령과 명시적 입력 인자를 구성한다."""
    parser = argparse.ArgumentParser(prog="mystery-kit")
    subparsers = parser.add_subparsers(dest="command", required=True)

    init_parser = subparsers.add_parser("init", help="표준 Project Scaffold를 생성합니다.")
    init_parser.add_argument("project_id")
    init_parser.add_argument("--projects-root", type=Path, default=ROOT / "PROJECTS")
    init_parser.add_argument("--created-at")

    compat_parser = subparsers.add_parser(
        "compat",
        help="Project와 Channel의 호환성을 판정하고 GATE-00을 실행합니다.",
    )
    compat_parser.add_argument("project_path", type=Path)
    compat_parser.add_argument(
        "--channel",
        type=Path,
        default=None,
    )

    variation_parser = subparsers.add_parser(
        "variations",
        help="구조적으로 다른 Story Variation 후보를 생성합니다.",
    )
    variation_parser.add_argument("project_path", type=Path)
    variation_parser.add_argument("--seed", required=True)
    variation_parser.add_argument("--count", required=True, type=int)

    approve_parser = subparsers.add_parser(
        "approve",
        help="Story Variation 후보 하나를 승인합니다.",
    )
    approve_parser.add_argument("project_path", type=Path)
    approve_parser.add_argument("candidate_id")
    approve_parser.add_argument("--override", action="store_true")
    approve_parser.add_argument("--actor")
    approve_parser.add_argument("--reason")

    eligibility_parser = subparsers.add_parser(
        "candidate-eligibility",
        help="Core 정책으로 Candidate 적격성을 판정합니다.",
    )
    eligibility_parser.add_argument("project_path", type=Path)

    precheck_parser = subparsers.add_parser(
        "precheck",
        help="모든 Variation을 Story History와 사전 비교합니다.",
    )
    precheck_parser.add_argument("project_path", type=Path)

    reference_parser = subparsers.add_parser(
        "reference-profile",
        help="외부 Reference를 정제된 Project Profile로 변환합니다.",
    )
    reference_parser.add_argument("project_path", type=Path)
    reference_parser.add_argument("reference_source", type=Path)

    evidence_parser = subparsers.add_parser(
        "evidence-submit",
        help="Runtime Evidence Human Input을 제출합니다.",
    )
    evidence_parser.add_argument("project_path", type=Path)
    evidence_parser.add_argument("run_id")
    evidence_parser.add_argument("input_path", type=Path)

    validate_parser = subparsers.add_parser(
        "validate",
        help="GATE-00부터 GATE-13까지 전체 Project를 검증합니다.",
    )
    validate_parser.add_argument("project_path", type=Path)
    validate_parser.add_argument(
        "--channel",
        type=Path,
        default=None,
    )
    validate_parser.add_argument("--reference-source", type=Path)

    register_parser = subparsers.add_parser(
        "register",
        help="Production Ready Story Fingerprint를 Library에 등록합니다.",
    )
    register_parser.add_argument("project_path", type=Path)
    register_parser.add_argument(
        "--library",
        type=Path,
        default=ROOT / "STORY_LIBRARY" / "published_fingerprints.json",
    )
    register_parser.add_argument(
        "--history",
        type=Path,
        default=ROOT / "STORY_LIBRARY" / "story_history.jsonl",
    )

    task_open_parser = subparsers.add_parser(
        "task-open",
        help="현재 Gate의 격리 Task Workspace를 엽니다.",
    )
    task_open_parser.add_argument("project_path", type=Path)
    task_open_parser.add_argument("gate_id")
    task_open_parser.add_argument("--reference-source", type=Path)

    task_status_parser = subparsers.add_parser(
        "task-status",
        help="현재 Gate Transaction 상태를 출력합니다.",
    )
    task_status_parser.add_argument("project_path", type=Path)

    task_submit_parser = subparsers.add_parser(
        "task-submit",
        help="현재 작성 Task를 제출하고 Gate 완료 시에만 원자 Commit합니다.",
    )
    task_submit_parser.add_argument("project_path", type=Path)
    task_submit_parser.add_argument("gate_id")
    task_submit_parser.add_argument("--reference-source", type=Path)

    task_abort_parser = subparsers.add_parser(
        "task-abort",
        help="현재 Gate Transaction을 Canonical 변경 없이 중단합니다.",
    )
    task_abort_parser.add_argument("project_path", type=Path)
    task_abort_parser.add_argument("gate_id")

    task_return_parser = subparsers.add_parser(
        "task-return",
        help="Critic Issue를 Artifact Owner Agent의 Gate로 되돌립니다.",
    )
    task_return_parser.add_argument("project_path", type=Path)
    task_return_parser.add_argument("owner_agent")
    task_return_parser.add_argument("--actor", required=True)
    task_return_parser.add_argument("--reason", required=True)

    audit_parser = subparsers.add_parser(
        "audit",
        help="Project State를 변경하지 않고 Artifact와 Process를 감사합니다.",
    )
    audit_parser.add_argument("project_path", type=Path)
    audit_parser.add_argument(
        "--channel",
        type=Path,
        default=None,
    )
    audit_parser.add_argument("--reference-source", type=Path)

    readable_config_parser = subparsers.add_parser(
        "broadcast-readable-config-set",
        help="Broadcast Readable Config를 검증된 Transaction으로 승인합니다.",
    )
    readable_config_parser.add_argument("project_path", type=Path)
    readable_config_parser.add_argument("--input", type=Path, required=True)
    readable_config_parser.add_argument("--actor", required=True)
    readable_config_parser.add_argument("--reason", required=True)

    rebuild_parser = subparsers.add_parser(
        "rebuild-state",
        help="명시적 복구 시에만 Project State를 재구성합니다.",
    )
    rebuild_parser.add_argument("project_path", type=Path)
    rebuild_parser.add_argument(
        "--channel",
        type=Path,
        default=None,
    )
    rebuild_parser.add_argument("--reference-source", type=Path)
    rebuild_parser.add_argument("--force", action="store_true")

    editorial_parser = subparsers.add_parser(
        "editorial-approve",
        help="Human Editorial Approval을 기록합니다.",
    )
    editorial_parser.add_argument("project_path", type=Path)
    editorial_parser.add_argument("--actor", required=True)
    editorial_parser.add_argument("--reason", required=True)

    finalize_parser = subparsers.add_parser(
        "production-finalize",
        help="승인 완료 Project를 Production Ready로 전이합니다.",
    )
    finalize_parser.add_argument("project_path", type=Path)

    migrate_parser = subparsers.add_parser(
        "migrate-channel-pin",
        help="Story를 수정하지 않고 Project의 Channel Content Version Pin을 이전합니다.",
    )
    migrate_parser.add_argument("project_path", type=Path)
    migrate_parser.add_argument(
        "--channel-content-version",
        required=True,
    )
    legacy_migrate_parser = subparsers.add_parser(
        "migrate-legacy-v1-1",
        help="Story와 Script를 보존하며 Legacy v1.1 Project 계약을 이전합니다.",
    )
    legacy_migrate_parser.add_argument("project_path", type=Path)

    return parser


def project_id_from_manifest(project_path: Path) -> str:
    """Project Manifest에서 Project ID를 읽는다."""
    manifest = load_json_object(project_path / "00_PROJECT" / "project_manifest.json")
    project_id = manifest.get("project_id")
    if not isinstance(project_id, str):
        raise ConfigurationError("project_manifest.project_id 문자열이 필요합니다.")
    return project_id


def repository_root_for_project(project_path: Path) -> Path:
    """Project와 같은 Tree에 속한 Repository Root를 엄격하게 찾는다."""
    resolved_project = project_path.resolve()
    if resolved_project.is_relative_to(ROOT):
        return ROOT
    for parent in resolved_project.parents:
        if (parent / "STANDARD" / "dependency_graph.json").is_file() and (
            parent / "STORY_LIBRARY" / "novelty_index.json"
        ).is_file():
            return parent
    raise ConfigurationError(
        f"Project Repository Root를 찾을 수 없습니다: project_path={project_path}"
    )


def validate_project_compatibility_configuration(
    project_path: Path,
    channel: Mapping[str, object],
) -> str:
    """Project와 Channel 식별 구성이 호환성 판정 전에 일치하는지 검증한다."""
    manifest_path = project_path / "00_PROJECT" / "project_manifest.json"
    config_path = project_path / "00_PROJECT" / "production_config.json"
    manifest = load_json_object(manifest_path)
    production_config = load_json_object(config_path)
    manifest_schema = load_json_object(
        ROOT / "STANDARD" / "schemas" / "project_manifest.schema.json"
    )
    config_schema = load_json_object(
        ROOT / "STANDARD" / "schemas" / "production_config.schema.json"
    )
    raise_for_configuration_schema_errors(
        collect_schema_errors(manifest, manifest_schema, str(manifest_path)),
        str(manifest_path),
    )
    raise_for_configuration_schema_errors(
        collect_schema_errors(production_config, config_schema, str(config_path)),
        str(config_path),
    )

    project_id = project_id_from_manifest(project_path)
    identifiers = {
        "project_manifest.project_id": project_id,
        "production_config.project_id": production_config.get("project_id"),
    }
    project_id_mismatches = sorted(
        name for name, value in identifiers.items() if value != project_id
    )
    if project_id_mismatches:
        raise ConfigurationError(
            "Project ID 구성이 일치하지 않습니다: "
            f"project_id={project_id}, fields={project_id_mismatches}"
        )

    channel_id = channel.get("channel_id")
    channel_identifiers = {
        "project_manifest.channel_id": manifest.get("channel_id"),
        "production_config.channel_id": production_config.get("channel_id"),
        "channel.channel_id": channel_id,
    }
    channel_id_mismatches = sorted(
        name for name, value in channel_identifiers.items() if value != channel_id
    )
    if not isinstance(channel_id, str) or channel_id_mismatches:
        raise ConfigurationError(
            "Channel ID 구성이 일치하지 않습니다: "
            f"channel_id={channel_id!r}, fields={channel_id_mismatches}"
        )
    return project_id


def make_compatibility_report_for_config(
    project_id: str,
    production_config: Mapping[str, object],
    channel_override: Path | None,
) -> tuple[ProjectCompatibilityReport, dict[str, object], Path]:
    """Project Pin에 맞는 Channel로 Compatibility Report를 계산한다."""
    contract_path = ROOT / "STANDARD" / "compatibility_contract.json"
    defaults_path = ROOT / "STANDARD" / "standard_defaults.json"
    channel_schema_path = ROOT / "STANDARD" / "schemas" / "channel_dna.schema.json"
    channel, channel_manifest, channel_path = resolve_project_channel(
        ROOT,
        production_config,
        channel_override,
    )
    report = evaluate_compatibility_documents(
        load_json_object(contract_path),
        load_json_object(defaults_path),
        channel,
        load_json_object(ROOT / "STANDARD" / "schemas" / "compatibility_contract.schema.json"),
        load_json_object(ROOT / "STANDARD" / "schemas" / "standard_defaults.schema.json"),
        load_json_object(channel_schema_path),
        str(contract_path),
        str(defaults_path),
        str(channel_path),
    )
    bound_report = evaluate_channel_binding(
        report,
        production_config,
        channel_manifest,
        channel,
    )
    pinned_version = production_config.get("channel_content_version")
    if not isinstance(pinned_version, str):
        raise ConfigurationError("production_config.channel_content_version 문자열이 필요합니다.")
    relative_path = registered_channel_relative_path(
        channel_manifest,
        pinned_version,
    )
    project_report = make_project_compatibility_report(
        project_id,
        bound_report,
        relative_path,
    )
    return project_report, channel, channel_path


def expand_project_state_artifacts(
    state: ProjectState,
    dependency_graph: Mapping[str, object],
) -> ProjectState:
    """현재 Dependency Graph의 신규 Artifact를 MISSING 상태로 추가한다."""
    next_state = deepcopy(state)
    for artifact_name in dependency_artifacts(dependency_graph):
        if artifact_name not in next_state["artifacts"]:
            next_state["artifacts"][artifact_name] = {
                "status": "MISSING",
                "content_hash": None,
                "invalidated_by": [],
            }
    return next_state


def invalidate_channel_pin_state(
    state: ProjectState,
    dependency_graph: Mapping[str, object],
    production_config_hash: str,
    compatibility_report_hash: str,
    updated_at: str,
) -> ProjectState:
    """Channel Pin 변경을 GATE-00부터 재검증하도록 상태에 전파한다."""
    expanded = expand_project_state_artifacts(state, dependency_graph)
    invalidated = invalidate_artifact_dependents(
        dependency_graph,
        expanded,
        "compatibility_report",
        compatibility_report_hash,
        updated_at,
    )
    invalidated = mark_artifact_clean(
        invalidated,
        "compatibility_report",
        compatibility_report_hash,
        updated_at,
    )
    invalidated = invalidate_artifact_dependents(
        dependency_graph,
        invalidated,
        "production_config",
        production_config_hash,
        updated_at,
    )
    invalidated = mark_artifact_clean(
        invalidated,
        "production_config",
        production_config_hash,
        updated_at,
    )
    next_state = deepcopy(invalidated)
    next_state["state"] = "BLOCKED"
    next_state["current_gate"] = "NONE"
    next_state["readiness"] = {
        "artifact_status": "INCOMPLETE",
        "contract_status": "UNVALIDATED",
        "process_status": "NONCONFORMANT",
        "editorial_status": "NOT_REVIEWED",
        "process_start_gate": "GATE-00",
        "process_revision": state["readiness"]["process_revision"] + 1,
    }
    next_state["updated_at"] = updated_at
    return next_state


def synchronize_compatibility_state(
    project_path: Path,
    compatibility_passed: bool,
    updated_at: str,
) -> ProjectState:
    """GATE-00 Artifact Hash와 호환성 결과를 Project State에 반영한다."""
    dependency_graph = load_json_object(ROOT / "STANDARD" / "dependency_graph.json")
    state = load_project_state(project_path)
    gate_zero_artifacts = (
        "project_manifest",
        "compatibility_report",
        "production_config",
        "project_constraints",
    )
    definitions = dependency_artifacts(dependency_graph)
    artifacts_changed = False
    next_state = state
    for artifact_name in gate_zero_artifacts:
        definition = definitions.get(artifact_name)
        if not isinstance(definition, Mapping):
            raise ConfigurationError(f"GATE-00 Artifact 정의가 없습니다: artifact={artifact_name}")
        relative_path = definition.get("path")
        if not isinstance(relative_path, str):
            raise ConfigurationError(
                f"GATE-00 Artifact path 문자열이 필요합니다: artifact={artifact_name}"
            )
        artifact_path = project_path / relative_path
        try:
            content_hash = artifact_hash(artifact_path.read_bytes())
        except OSError as error:
            raise ConfigurationError(
                f"GATE-00 Artifact를 읽지 못했습니다: path={artifact_path}, detail={error}"
            ) from error
        current_artifact = next_state["artifacts"].get(artifact_name)
        if current_artifact is None:
            raise ConfigurationError(
                f"Project State에 GATE-00 Artifact가 없습니다: artifact={artifact_name}"
            )
        if current_artifact["content_hash"] != content_hash:
            next_state = invalidate_artifact_dependents(
                dependency_graph,
                next_state,
                artifact_name,
                content_hash,
                updated_at,
            )
            artifacts_changed = True
        next_state = mark_artifact_clean(
            next_state,
            artifact_name,
            content_hash,
            updated_at,
        )

    current_gate = next_state["current_gate"]
    gate_zero_already_passed = current_gate != "NONE" and gate_index(current_gate) >= gate_index(
        "GATE-00"
    )
    if compatibility_passed and gate_zero_already_passed and not artifacts_changed:
        write_json_object(project_path / "00_PROJECT" / "project_state.json", next_state)
        return next_state

    reset_state = deepcopy(next_state)
    reset_state["state"] = "INITIALIZED"
    reset_state["current_gate"] = "NONE"
    synchronized = advance_gate(
        reset_state,
        "GATE-00",
        compatibility_passed,
        updated_at,
        GATES[gate_index("GATE-00")]["required_artifacts"],
    )
    write_json_object(project_path / "00_PROJECT" / "project_state.json", synchronized)
    return synchronized


def require_variation_prerequisites(project_path: Path, project_id: str) -> None:
    """Variation 생성 전에 Project-aware Compatibility PASS를 강제한다."""
    state = load_project_state(project_path)
    report = load_json_object(project_path / "00_PROJECT" / "compatibility_report.json")
    current_gate = state["current_gate"]
    gate_passed = current_gate != "NONE" and gate_index(current_gate) >= gate_index("GATE-00")
    if state["project_id"] != project_id:
        raise ConfigurationError(
            "Project State의 Project ID가 Manifest와 다릅니다: "
            f"manifest={project_id}, state={state['project_id']}"
        )
    if report.get("project_id") != project_id:
        raise ConfigurationError(
            "Compatibility Report의 Project ID가 Manifest와 다릅니다: "
            f"manifest={project_id}, report={report.get('project_id')!r}"
        )
    if report.get("compatibility") != "PASS" or not gate_passed:
        raise ConfigurationError(
            "Variation 생성 전에 Project Compatibility를 통과해야 합니다: "
            f"command='mystery-kit compat {project_path}', "
            f"compatibility={report.get('compatibility')!r}, current_gate={current_gate}"
        )


def load_story_history(path: Path) -> list[Mapping[str, object]]:
    """Novelty Index의 활성 Project 비교 기록을 엄격하게 읽는다."""
    try:
        return novelty_history(load_json_object(path))
    except StarterKitError as error:
        raise ConfigurationError(
            f"Novelty Index를 읽을 수 없습니다: path={path}, detail={error}"
        ) from error


def qa_issue_group(code: str) -> str | None:
    """검증 문제 Code를 개별 QA Report 종류로 분류한다."""
    if code in NOVELTY_CODES or code == "STALE_STORY_FINGERPRINT":
        return "novelty"
    if code in REFERENCE_CODES or code.startswith("REFERENCE_"):
        return "reference"
    if code.startswith("CHANNEL_"):
        return "channel"
    continuity_prefixes = (
        "SIMULTANEOUS_",
        "CLUE_",
        "CORE_",
        "RED_HERRING_",
        "KNOWLEDGE_",
        "UNDECLARED_",
        "RUNTIME_",
        "BROKEN_",
        "CAUSAL_",
        "ROOT_CAUSE_",
    )
    if code.startswith(continuity_prefixes):
        return "continuity"
    return None


def write_qa_reports(
    project_path: Path,
    project_id: str,
    issues: Sequence[ValidationIssue],
) -> None:
    """통합 문제 목록을 네 개의 전용 QA Report로 분리해 기록한다."""
    report_paths = {
        "continuity": project_path / "08_QA" / "continuity_report.json",
        "novelty": project_path / "08_QA" / "novelty_report.json",
        "reference": project_path / "08_QA" / "reference_collision_report.json",
        "channel": project_path / "08_QA" / "channel_consistency_report.json",
    }
    grouped: dict[str, list[ValidationIssue]] = {group: [] for group in report_paths}
    for issue in issues:
        group = qa_issue_group(issue["code"])
        if group is not None:
            grouped[group].append(issue)
    for group, path in report_paths.items():
        group_issues = grouped[group]
        write_json_object(
            path,
            {
                "project_id": project_id,
                "result": "FAIL" if group_issues else "PASS",
                "issues": group_issues,
            },
        )


def load_project_state(project_path: Path) -> ProjectState:
    """Project State를 Schema 검증 후 엄격한 형식으로 반환한다."""
    state_path = project_path / "00_PROJECT" / "project_state.json"
    state_document = load_json_object(state_path)
    schema = load_json_object(ROOT / "STANDARD" / "schemas" / "project_state.schema.json")
    errors = collect_schema_errors(state_document, schema, str(state_path))
    if errors:
        raise ConfigurationError(f"Project State Schema 오류입니다: errors={errors}")
    return cast(ProjectState, state_document)


def clean_existing_artifacts(
    project_path: Path,
    dependency_graph: Mapping[str, object],
    state: ProjectState,
    updated_at: str,
) -> ProjectState:
    """현재 디스크 내용의 Hash로 모든 선언 Artifact를 CLEAN 처리한다."""
    next_state = state
    for artifact_name, definition in dependency_artifacts(dependency_graph).items():
        relative_path = definition.get("path")
        if not isinstance(relative_path, str):
            raise ConfigurationError(
                f"Dependency Artifact path 문자열이 필요합니다: artifact={artifact_name}"
            )
        path = project_path / relative_path
        try:
            content = path.read_bytes()
        except OSError as error:
            raise ConfigurationError(
                f"Artifact Hash 계산에 실패했습니다: path={path}, detail={error}"
            ) from error
        next_state = mark_artifact_clean(
            next_state,
            artifact_name,
            artifact_hash(content),
            updated_at,
        )
    return next_state


def synchronize_project_state(
    project_path: Path,
    dependency_graph: Mapping[str, object],
    gate_results: Mapping[str, object],
    issues: Sequence[ValidationIssue],
    updated_at: str,
) -> ProjectState:
    """검증 결과와 Artifact Hash를 Project State Machine에 반영한다."""
    initial_state = reconcile_project_state_artifacts(
        dependency_graph,
        load_project_state(project_path),
    )
    state = clean_existing_artifacts(
        project_path,
        dependency_graph,
        initial_state,
        updated_at,
    )
    state["state"] = "INITIALIZED"
    state["current_gate"] = "NONE"
    process_start_gate = state["readiness"]["process_start_gate"]
    process_revision = state["readiness"]["process_revision"]
    state["readiness"] = {
        "artifact_status": "INCOMPLETE",
        "contract_status": "UNVALIDATED",
        "process_status": "NONCONFORMANT",
        "editorial_status": "NOT_REVIEWED",
        "process_start_gate": process_start_gate,
        "process_revision": process_revision,
    }
    for gate in GATES:
        gate_id = gate["gate_id"]
        passed = gate_results.get(gate_id) == "PASS"
        state = advance_gate(
            state,
            gate_id,
            passed,
            updated_at,
            gate["required_artifacts"],
        )
        if not passed:
            break
    state = mark_issue_artifacts_invalid(state, dependency_graph, issues)
    write_json_object(project_path / "00_PROJECT" / "project_state.json", state)
    return state


def mark_issue_artifacts_invalid(
    state: ProjectState,
    dependency_graph: Mapping[str, object],
    issues: Sequence[ValidationIssue],
) -> ProjectState:
    """검증 문제가 직접 가리킨 Artifact를 INVALID로 표시한 새 상태를 반환한다."""
    artifacts = dependency_artifacts(dependency_graph)
    path_to_name = {
        definition["path"]: artifact_name
        for artifact_name, definition in artifacts.items()
        if isinstance(definition.get("path"), str)
    }
    invalid_names = {path_to_name.get(issue["artifact"], issue["artifact"]) for issue in issues}
    next_state = deepcopy(state)
    for artifact_name in invalid_names:
        artifact_state = next_state["artifacts"].get(artifact_name)
        if artifact_state is not None:
            artifact_state["status"] = "INVALID"
            for dependent in transitive_dependents(dependency_graph, artifact_name):
                dependent_state = next_state["artifacts"][dependent]
                if dependent_state["status"] != "INVALID":
                    dependent_state["status"] = "DIRTY"
                dependent_state["invalidated_by"] = sorted(
                    set(dependent_state["invalidated_by"]) | {artifact_name}
                )
    return next_state


def record_artifact_change(
    project_path: Path,
    artifact_name: str,
    artifact_path: Path,
    updated_at: str,
) -> ProjectState:
    """Artifact 변경을 Project State와 모든 하위 의존 Artifact에 전파한다."""
    dependency_graph = load_json_object(ROOT / "STANDARD" / "dependency_graph.json")
    state = load_project_state(project_path)
    try:
        content = artifact_path.read_bytes()
    except OSError as error:
        raise ConfigurationError(
            f"변경 Artifact Hash 계산에 실패했습니다: path={artifact_path}, detail={error}"
        ) from error
    content_hash = artifact_hash(content)
    current_artifact = state["artifacts"].get(artifact_name)
    if current_artifact is None:
        raise ConfigurationError(
            f"Project State에 변경 Artifact가 없습니다: artifact={artifact_name}"
        )
    if current_artifact["content_hash"] == content_hash:
        return state
    next_state = invalidate_artifact_dependents(
        dependency_graph,
        state,
        artifact_name,
        content_hash,
        updated_at,
    )
    write_json_object(project_path / "00_PROJECT" / "project_state.json", next_state)
    return next_state


def run_init(args: argparse.Namespace) -> int:
    """Project Scaffold 생성 명령을 실행한다."""
    dependency_graph = load_json_object(ROOT / "STANDARD" / "dependency_graph.json")
    created_at = args.created_at if isinstance(args.created_at, str) else utc_now()
    project_path = create_project_scaffold(
        ROOT / "TEMPLATES" / "PROJECT",
        args.projects_root,
        dependency_graph,
        args.project_id,
        created_at,
    )
    append_change_log(
        project_path,
        "PROJECT_INITIALIZED",
        {"project_id": args.project_id},
        created_at,
    )
    print(project_path)
    return 0


def run_compat(args: argparse.Namespace) -> int:
    """Project-aware Compatibility 판정과 GATE-00 전이를 실행한다."""
    production_config = load_json_object(
        args.project_path / "00_PROJECT" / "production_config.json"
    )
    channel_override = args.channel if isinstance(args.channel, Path) else None
    channel, _manifest, _channel_path = resolve_project_channel(
        ROOT, production_config, channel_override
    )
    project_id = validate_project_compatibility_configuration(
        args.project_path,
        channel,
    )
    project_report, _channel, _resolved_path = make_compatibility_report_for_config(
        project_id,
        production_config,
        channel_override,
    )
    output_path = args.project_path / "00_PROJECT" / "compatibility_report.json"
    write_json_object(output_path, project_report)
    changed_at = utc_now()
    state = synchronize_compatibility_state(
        args.project_path,
        project_report["compatibility"] == "PASS",
        changed_at,
    )
    append_change_log(
        args.project_path,
        "PROJECT_COMPATIBILITY_EVALUATED",
        {
            "compatibility": project_report["compatibility"],
            "error_count": len(cast(list[object], project_report["errors"])),
            "current_gate": state["current_gate"],
        },
        changed_at,
    )
    print(
        json.dumps(
            {
                "project_id": project_id,
                "compatibility": project_report["compatibility"],
                "current_gate": state["current_gate"],
                "report": str(output_path),
                "error_count": len(cast(list[object], project_report["errors"])),
            },
            ensure_ascii=False,
        )
    )
    return 0 if project_report["compatibility"] == "PASS" else 1


def run_migrate_channel_pin(args: argparse.Namespace) -> int:
    """Story Artifact를 보존하며 등록된 Channel Pin으로 이전한다."""
    project_path = args.project_path.resolve()
    requested_version = args.channel_content_version
    if not isinstance(requested_version, str):
        raise ConfigurationError("--channel-content-version 문자열이 필요합니다.")
    run_id = f"MIGRATE-{uuid4()}"
    lock_path = acquire_project_lock(project_path, run_id)
    try:
        config_path = project_path / "00_PROJECT" / "production_config.json"
        report_path = project_path / "00_PROJECT" / "compatibility_report.json"
        current_config = load_json_object(config_path)
        migrated_config = deepcopy(current_config)
        migrated_config["channel_content_version"] = requested_version
        config_schema = load_json_object(
            ROOT / "STANDARD" / "schemas" / "production_config.schema.json"
        )
        raise_for_configuration_schema_errors(
            collect_schema_errors(
                migrated_config,
                config_schema,
                str(config_path),
            ),
            str(config_path),
        )
        project_id = project_id_from_manifest(project_path)
        if migrated_config.get("project_id") != project_id:
            raise ConfigurationError(
                "Project ID가 Manifest와 Production Config에서 다릅니다: "
                f"manifest={project_id}, config={migrated_config.get('project_id')!r}"
            )
        project_report, channel, _channel_path = make_compatibility_report_for_config(
            project_id,
            migrated_config,
            None,
        )
        if migrated_config.get("channel_id") != channel.get("channel_id"):
            raise ConfigurationError(
                "Channel ID가 Production Config와 등록 DNA에서 다릅니다: "
                f"config={migrated_config.get('channel_id')!r}, "
                f"channel={channel.get('channel_id')!r}"
            )
        if project_report.get("compatibility") != "PASS":
            raise ConfigurationError(
                "Channel Pin Migration Compatibility가 실패했습니다: "
                f"errors={project_report.get('errors')!r}"
            )
        dependency_graph = load_json_object(ROOT / "STANDARD" / "dependency_graph.json")
        current_state = load_project_state(project_path)
        config_bytes = encoded_artifact(migrated_config, "application/json")
        report_bytes = encoded_artifact(project_report, "application/json")
        if (
            current_config.get("channel_content_version") == requested_version
            and config_path.read_bytes() == config_bytes
            and report_path.read_bytes() == report_bytes
        ):
            next_state = current_state
            print(
                json.dumps(
                    {
                        "project_id": project_id,
                        "channel_content_version": requested_version,
                        "current_gate": next_state["current_gate"],
                        "project_state": next_state["state"],
                        "compatibility": project_report["compatibility"],
                        "changed": False,
                    },
                    ensure_ascii=False,
                )
            )
            return 0
        migrated_at = utc_now()
        next_state = invalidate_channel_pin_state(
            current_state,
            dependency_graph,
            artifact_hash(config_bytes),
            artifact_hash(report_bytes),
            migrated_at,
        )
        channel_summary = project_report["channel"]
        log_path = project_path / "00_PROJECT" / "change_log.jsonl"
        existing_log = log_path.read_bytes() if log_path.is_file() else b""
        next_log = change_log_bytes(
            existing_log,
            "CHANNEL_CONTENT_VERSION_PIN_MIGRATED",
            {
                "previous_version": current_config.get("channel_content_version"),
                "channel_content_version": requested_version,
                "relative_path": channel_summary.get("relative_path"),
                "process_revision": next_state["readiness"]["process_revision"],
            },
            migrated_at,
        )
        commit_gate_transaction(
            project_path,
            run_id,
            "CHANNEL_PIN_MIGRATION",
            project_path,
            {},
            dependency_graph,
            next_state,
            {
                "00_PROJECT/production_config.json": config_bytes,
                "00_PROJECT/compatibility_report.json": report_bytes,
                "00_PROJECT/change_log.jsonl": next_log,
            },
        )
    finally:
        release_project_lock(lock_path, run_id)
    print(
        json.dumps(
            {
                "project_id": project_id,
                "channel_content_version": requested_version,
                "current_gate": next_state["current_gate"],
                "project_state": next_state["state"],
                "compatibility": project_report["compatibility"],
            },
            ensure_ascii=False,
        )
    )
    return 0


def protected_story_script_hashes(project_path: Path) -> dict[str, str]:
    """Migration에서 변경하면 안 되는 Story·Script 파일 Hash를 반환한다."""
    paths = [project_path / "00_PROJECT" / "story_dna.json"]
    paths.extend(sorted((project_path / "07_SCRIPT").glob("*")))
    return {
        str(path.relative_to(project_path)): artifact_hash(path.read_bytes())
        for path in paths
        if path.is_file()
    }


def run_migrate_legacy_v1_1(args: argparse.Namespace) -> int:
    """Legacy v1.1 Project에 Version Pin과 Constraint를 원자적으로 추가한다."""
    project_path = args.project_path.resolve()
    run_id = f"MIGRATE-{uuid4()}"
    lock_path = acquire_project_lock(project_path, run_id)
    try:
        project_id = project_id_from_manifest(project_path)
        config_path = project_path / "00_PROJECT" / "production_config.json"
        variation_path = project_path / "00_PROJECT" / "variation_candidates.json"
        constraint_path = project_path / "00_PROJECT" / "project_constraints.json"
        current_config = load_json_object(config_path)
        if current_config.get("channel_content_version") != "1.1.0":
            raise ConfigurationError(
                "LEGACY_MIGRATION_VERSION_INVALID: Channel Content Version은 1.1.0이어야 합니다."
            )
        if (
            current_config.get("variation_engine_version") is not None
            or current_config.get("variation_catalog_version") is not None
        ):
            raise ConfigurationError(
                "LEGACY_MIGRATION_NOT_REQUIRED: Variation Version Pin이 이미 존재합니다."
            )
        migrated_config = deepcopy(current_config)
        migrated_config["variation_engine_version"] = "1.0.0"
        migrated_config["variation_catalog_version"] = "1.0.0"
        runtime = resolve_variation_runtime(ROOT, migrated_config)
        legacy_variations = load_json_object(variation_path)
        migrated_variations, signature_reproduced = migrated_legacy_variations(
            legacy_variations,
            runtime,
        )
        constraint_template = load_json_object(
            ROOT / "TEMPLATES" / "PROJECT" / "00_PROJECT" / "project_constraints.json"
        )
        migrated_constraints = (
            load_json_object(constraint_path)
            if constraint_path.is_file()
            else default_project_constraints(project_id, constraint_template)
        )
        schema_targets = (
            (
                migrated_config,
                ROOT / "STANDARD" / "schemas" / "production_config.schema.json",
                str(config_path),
            ),
            (
                migrated_constraints,
                ROOT / "STANDARD" / "schemas" / "project_constraints.schema.json",
                str(constraint_path),
            ),
            (
                migrated_variations,
                ROOT / "STANDARD" / "schemas" / "variation_candidates.schema.json",
                str(variation_path),
            ),
        )
        for document, schema_path, source in schema_targets:
            raise_for_configuration_schema_errors(
                collect_schema_errors(document, load_json_object(schema_path), source),
                source,
            )
        project_files = {
            str(path.relative_to(project_path))
            for path in project_path.rglob("*")
            if path.is_file()
        }
        review_reasons = migration_review_reasons(
            project_files,
            signature_reproduced,
        )
        review_status = migration_status(review_reasons)
        protected_hashes = protected_story_script_hashes(project_path)
        migrated_at = utc_now()
        config_bytes = encoded_artifact(migrated_config, "application/json")
        constraint_bytes = encoded_artifact(migrated_constraints, "application/json")
        variation_bytes = encoded_artifact(migrated_variations, "application/json")
        dependency_graph = load_json_object(ROOT / "STANDARD" / "dependency_graph.json")
        state = normalized_legacy_state(
            load_project_state(project_path),
            dependency_graph,
            project_id,
            migrated_at,
            {
                "production_config": config_bytes,
                "project_constraints": constraint_bytes,
                "variation_candidates": variation_bytes,
            },
        )
        log_path = project_path / "00_PROJECT" / "change_log.jsonl"
        existing_log = log_path.read_bytes() if log_path.is_file() else b""
        next_log = change_log_bytes(
            existing_log,
            "LEGACY_V1_1_MIGRATED",
            {
                "variation_engine_version": "1.0.0",
                "variation_catalog_version": "1.0.0",
                "signature_reproduced": signature_reproduced,
                "review_status": review_status,
                "review_reasons": review_reasons,
                "protected_content_hashes": protected_hashes,
                "process_revision": state["readiness"]["process_revision"],
            },
            migrated_at,
        )
        transaction_id = commit_gate_transaction(
            project_path,
            run_id,
            "LEGACY_V1_1_MIGRATION",
            project_path,
            {},
            dependency_graph,
            state,
            {
                "00_PROJECT/production_config.json": config_bytes,
                "00_PROJECT/project_constraints.json": constraint_bytes,
                "00_PROJECT/variation_candidates.json": variation_bytes,
                "00_PROJECT/change_log.jsonl": next_log,
            },
        )
        if protected_story_script_hashes(project_path) != protected_hashes:
            raise ConfigurationError(
                "LEGACY_MIGRATION_CONTENT_CHANGED: Story 또는 Script Hash가 변경되었습니다."
            )
    finally:
        release_project_lock(lock_path, run_id)
    print(
        json.dumps(
            {
                "project_id": project_id,
                "transaction_id": transaction_id,
                "variation_engine_version": "1.0.0",
                "variation_catalog_version": "1.0.0",
                "signature_reproduced": signature_reproduced,
                "story_script_hashes_unchanged": True,
                "review_status": review_status,
                "review_reasons": review_reasons,
            },
            ensure_ascii=False,
        )
    )
    return 0


def run_variations(args: argparse.Namespace) -> int:
    """Variation 후보 생성 명령을 실행한다."""
    project_id = project_id_from_manifest(args.project_path)
    require_variation_prerequisites(args.project_path, project_id)
    production_config = load_json_object(
        args.project_path / "00_PROJECT" / "production_config.json"
    )
    channel, _manifest, _channel_path = resolve_project_channel(
        ROOT,
        production_config,
        None,
    )
    truth_contract_path = args.project_path / "01_CASE" / "source_truth_contract.json"
    truth_contract = (
        load_json_object(truth_contract_path) if truth_contract_path.is_file() else None
    )
    candidates = generate_eligible_candidate_pool(
        project_id,
        args.seed,
        args.count,
        resolve_variation_runtime(ROOT, production_config),
        require_source_truth_classification(production_config),
        production_config,
        load_json_object(args.project_path / "00_PROJECT" / "project_constraints.json"),
        channel,
        load_story_history(ROOT / "STORY_LIBRARY" / "novelty_index.json"),
        load_json_object(ROOT / "STANDARD" / "novelty_thresholds.json"),
        load_json_object(ROOT / "STANDARD" / "candidate_projection_contract.json"),
        truth_contract,
        64,
    )
    output_path = args.project_path / "00_PROJECT" / "variation_candidates.json"
    write_json_object(output_path, candidates)
    changed_at = utc_now()
    record_artifact_change(
        args.project_path,
        "variation_candidates",
        output_path,
        changed_at,
    )
    append_change_log(
        args.project_path,
        "VARIATIONS_GENERATED",
        {"candidate_count": args.count},
        changed_at,
    )
    print(output_path)
    return 0


def run_validate(args: argparse.Namespace) -> int:
    """전체 Artifact를 진단하되 Project State를 재구성하지 않는다."""
    audited_at = utc_now()
    report = audit_project(
        ROOT,
        args.project_path,
        args.reference_source if isinstance(args.reference_source, Path) else None,
        args.channel if isinstance(args.channel, Path) else None,
        audited_at,
    )
    report_path = args.project_path / "08_QA" / "audit_report.json"
    write_json_object(report_path, report)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    validation = cast(Mapping[str, object], report["validation"])
    return 0 if validation["result"] == "PASS" else 1


def run_candidate_eligibility(args: argparse.Namespace) -> int:
    """현재 Channel과 Novelty 입력으로 Core 적격성을 기록한다."""
    config = load_json_object(args.project_path / "00_PROJECT" / "production_config.json")
    project_constraints = load_json_object(
        args.project_path / "00_PROJECT" / "project_constraints.json"
    )
    channel, _manifest, _path = resolve_project_channel(ROOT, config, None)
    variations = load_json_object(args.project_path / "00_PROJECT" / "variation_candidates.json")
    event_brief_path = args.project_path / "00_PROJECT" / "candidate_event_briefs.json"
    candidate_event_briefs = (
        load_json_object(event_brief_path)
        if explicit_crime_policy(channel) is not None and event_brief_path.is_file()
        else None
    )
    if explicit_crime_policy(channel) is not None and candidate_event_briefs is None:
        raise GateTransactionError(
            "CANDIDATE_EVENT_BRIEFS_REQUIRED",
            "Explicit Crime Candidate 적격성에는 Event Brief가 필요합니다.",
            {"path": str(event_brief_path)},
        )
    novelty = load_json_object(args.project_path / "08_QA" / "novelty_precheck.json")
    eligibility = build_candidate_eligibility_bound(
        config,
        project_constraints,
        channel,
        variations,
        candidate_event_briefs,
        novelty,
    )
    output_path = args.project_path / "08_QA" / "candidate_eligibility.json"
    write_json_object(output_path, eligibility)
    print(output_path)
    return 0


def run_evidence_submit(args: argparse.Namespace) -> int:
    """Project 보조 CLI에서 Runtime Evidence 입력을 제출한다."""
    result = submit_evidence_input(
        args.project_path.resolve(),
        args.run_id,
        load_json_object(args.input_path.resolve()),
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


def canonical_file_hashes(paths: Sequence[Path]) -> dict[Path, str]:
    """승인 검증과 Commit 사이 Drift를 막을 Canonical 파일 Hash를 계산한다."""
    try:
        return {path: artifact_hash(path.read_bytes()) for path in paths}
    except OSError as error:
        raise GateTransactionError(
            "CANDIDATE_APPROVAL_INPUT_MISSING",
            "Candidate 승인 입력 파일을 읽을 수 없습니다.",
            {"detail": str(error)},
        ) from error


def run_approve(args: argparse.Namespace) -> int:
    """최신 Novelty와 평가 근거를 통과한 Variation 후보를 승인한다."""
    production_config = load_json_object(
        args.project_path / "00_PROJECT" / "production_config.json"
    )
    channel, _manifest, channel_path = resolve_project_channel(
        ROOT,
        production_config,
        None,
    )
    path = args.project_path / "00_PROJECT" / "variation_candidates.json"
    document = load_json_object(path)
    event_brief_path = args.project_path / "00_PROJECT" / "candidate_event_briefs.json"
    candidate_event_briefs = (
        load_json_object(event_brief_path)
        if explicit_crime_policy(channel) is not None and event_brief_path.is_file()
        else None
    )
    if explicit_crime_policy(channel) is not None and candidate_event_briefs is None:
        raise GateTransactionError(
            "CANDIDATE_EVENT_BRIEFS_REQUIRED",
            "Explicit Crime Candidate 승인에는 Event Brief가 필요합니다.",
            {"path": str(event_brief_path)},
        )
    evaluation_path = args.project_path / "00_PROJECT" / "candidate_evaluation.json"
    evaluation = load_json_object(evaluation_path)
    evaluations = evaluation.get("evaluations")
    if not isinstance(evaluations, list) or not evaluations:
        raise GateTransactionError(
            "CANDIDATE_EVALUATION_REQUIRED",
            "Variation 승인 전에 Candidate 평가가 필요합니다.",
            {"path": str(evaluation_path)},
        )
    evaluation_schema = load_json_object(
        ROOT / "STANDARD" / "schemas" / "candidate_evaluation.schema.json"
    )
    schema_errors = collect_schema_errors(
        evaluation,
        evaluation_schema,
        str(evaluation_path),
    )
    if schema_errors:
        raise GateTransactionError(
            "CANDIDATE_EVALUATION_INVALID",
            "Candidate 평가가 Schema를 통과하지 못했습니다.",
            {"issues": schema_errors},
        )
    novelty_path = args.project_path / "08_QA" / "novelty_precheck.json"
    novelty_precheck = load_json_object(novelty_path)
    eligibility_path = args.project_path / "08_QA" / "candidate_eligibility.json"
    candidate_eligibility = load_json_object(eligibility_path)
    state_path = args.project_path / "00_PROJECT" / "project_state.json"
    log_path = args.project_path / "00_PROJECT" / "change_log.jsonl"
    current_state = load_project_state(args.project_path)
    approval_documents: dict[Path, Mapping[str, object]] = {
        args.project_path / "00_PROJECT" / "production_config.json": production_config,
        channel_path: channel,
        path: document,
        evaluation_path: evaluation,
        novelty_path: novelty_precheck,
        eligibility_path: candidate_eligibility,
        state_path: current_state,
    }
    if candidate_event_briefs is not None:
        approval_documents[event_brief_path] = candidate_event_briefs
    approval_source_paths = (*approval_documents, log_path)
    approval_document_hashes = {
        source_path: document_sha256(source_document)
        for source_path, source_document in approval_documents.items()
    }
    approval_source_hashes = canonical_file_hashes(approval_source_paths)
    eligibility_schema_errors = collect_schema_errors(
        candidate_eligibility,
        load_json_object(ROOT / "STANDARD" / "schemas" / "candidate_eligibility.schema.json"),
        str(eligibility_path),
    )
    if eligibility_schema_errors:
        raise GateTransactionError(
            "CANDIDATE_ELIGIBILITY_INVALID",
            "Candidate 적격성 문서가 Schema를 통과하지 못했습니다.",
            {"issues": eligibility_schema_errors},
        )
    novelty_schema_errors = collect_schema_errors(
        novelty_precheck,
        load_json_object(ROOT / "STANDARD" / "schemas" / "novelty_precheck.schema.json"),
        str(novelty_path),
    )
    if novelty_schema_errors:
        raise GateTransactionError(
            "CANDIDATE_NOVELTY_PRECHECK_REQUIRED",
            "Variation 승인 전에 전체 Candidate Novelty Precheck가 필요합니다.",
            {"issues": novelty_schema_errors},
        )
    eligibility_issues = validate_candidate_eligibility(
        production_config,
        load_json_object(args.project_path / "00_PROJECT" / "project_constraints.json"),
        channel,
        document,
        candidate_event_briefs,
        novelty_precheck,
        candidate_eligibility,
    )
    if eligibility_issues:
        issue = eligibility_issues[0]
        raise GateTransactionError(
            issue["code"],
            issue["message"],
            issue["context"],
        )
    evaluation_issues = validate_candidate_evaluation(
        document,
        candidate_event_briefs,
        evaluation,
        novelty_precheck,
        candidate_eligibility,
    )
    if evaluation_issues:
        issue = evaluation_issues[0]
        raise GateTransactionError(
            issue["code"],
            issue["message"],
            issue["context"],
        )
    recommended = evaluation.get("recommended_candidate_id")
    if not isinstance(recommended, str):
        raise GateTransactionError(
            "CANDIDATE_EVALUATION_REQUIRED",
            "추천 Candidate ID가 필요합니다.",
            {},
        )
    eligible_ids = candidate_eligibility.get("eligible_candidate_ids")
    if not isinstance(eligible_ids, list) or args.candidate_id not in eligible_ids:
        raise GateTransactionError(
            "CANDIDATE_APPROVAL_INELIGIBLE",
            "Core 적격성 판정을 통과하지 못한 후보는 승인할 수 없습니다.",
            {"candidate_id": args.candidate_id},
        )
    is_override = args.candidate_id != recommended
    approval_policy = production_config.get("approval_policy")
    if approval_policy not in {"AUTO_CONTINUE", "HUMAN_REVIEW"}:
        raise GateTransactionError(
            "CANDIDATE_APPROVAL_POLICY_INVALID",
            "Candidate Approval Policy가 올바르지 않습니다.",
            {"approval_policy": approval_policy},
        )
    if is_override and (
        args.override is not True
        or not isinstance(args.actor, str)
        or not args.actor
        or not isinstance(args.reason, str)
        or not args.reason
    ):
        raise GateTransactionError(
            "CANDIDATE_HUMAN_OVERRIDE_REQUIRED",
            "비추천 후보 승인에는 --override --actor --reason이 모두 필요합니다.",
            {"candidate_id": args.candidate_id, "recommended_candidate_id": recommended},
        )
    if not is_override and args.override:
        raise GateTransactionError(
            "CANDIDATE_OVERRIDE_NOT_REQUIRED",
            "추천 후보에는 Human Override를 사용할 수 없습니다.",
            {"candidate_id": args.candidate_id},
        )
    human_confirmation = approval_policy == "HUMAN_REVIEW" and not is_override
    if human_confirmation and (
        not isinstance(args.actor, str)
        or not args.actor
        or not isinstance(args.reason, str)
        or not args.reason
    ):
        raise GateTransactionError(
            "CANDIDATE_HUMAN_CONFIRMATION_REQUIRED",
            "HUMAN_REVIEW 추천 후보 승인에는 --actor와 --reason이 필요합니다.",
            {"candidate_id": args.candidate_id},
        )
    changed_at = utc_now()
    human_decision = is_override or human_confirmation
    run_id = f"CLI-APPROVE-{uuid4().hex[:12].upper()}"
    runtime_approval = (
        RuntimeApproval(
            schema_family="runtime-approval",
            schema_version="1.0.0",
            approval_id=f"APR-{uuid4().hex[:12].upper()}",
            run_id=run_id,
            task_id="variation.approve",
            decision="APPROVED",
            actor=str(args.actor),
            reason=str(args.reason),
            bound_input_hashes=approval_input_hashes(
                production_config,
                document,
                candidate_event_briefs,
                novelty_precheck,
                candidate_eligibility,
                evaluation,
            ),
            created_at=changed_at,
        )
        if human_decision
        else None
    )
    approved = approve_variation_candidate(document, args.candidate_id)
    approval = build_candidate_approval(
        project_id_from_manifest(args.project_path),
        args.candidate_id,
        recommended,
        args.actor if human_decision else "SYSTEM",
        args.reason if human_decision else "적격 후보 중 최고 Soft 평가 점수를 자동 승인했습니다.",
        changed_at,
        production_config,
        document,
        candidate_event_briefs,
        novelty_precheck,
        candidate_eligibility,
        evaluation,
        str(approval_policy),
        runtime_approval,
    )
    approval_schema_errors = collect_schema_errors(
        approval,
        load_json_object(ROOT / "STANDARD" / "schemas" / "candidate_approval.schema.json"),
        "candidate_approval",
    )
    if approval_schema_errors:
        raise GateTransactionError(
            "CANDIDATE_APPROVAL_INVALID",
            "Candidate 승인 기록이 Schema를 통과하지 못했습니다.",
            {"issues": approval_schema_errors},
        )
    dependency_graph = load_json_object(ROOT / "STANDARD" / "dependency_graph.json")
    approved_bytes = encoded_artifact(approved, "application/json")
    approval_bytes = encoded_artifact(approval, "application/json")
    next_state = invalidate_artifact_dependents(
        dependency_graph,
        current_state,
        "variation_candidates",
        artifact_hash(approved_bytes),
        changed_at,
    )
    next_state = invalidate_artifact_dependents(
        dependency_graph,
        next_state,
        "candidate_approval",
        artifact_hash(approval_bytes),
        changed_at,
    )
    next_state = mark_artifact_clean(
        next_state,
        "variation_candidates",
        artifact_hash(approved_bytes),
        changed_at,
    )
    next_state = mark_artifact_clean(
        next_state,
        "candidate_approval",
        artifact_hash(approval_bytes),
        changed_at,
    )
    existing_log = log_path.read_bytes() if log_path.is_file() else b""
    next_log = change_log_bytes(
        existing_log,
        "VARIATION_APPROVED",
        {
            "candidate_id": args.candidate_id,
            "approval_type": approval["approval_type"],
        },
        changed_at,
    )
    lock_path = acquire_project_lock(args.project_path, run_id)
    try:
        current_document_hashes = {
            source_path: document_sha256(load_json_object(source_path))
            for source_path in approval_documents
        }
        if (
            canonical_file_hashes(approval_source_paths) != approval_source_hashes
            or current_document_hashes != approval_document_hashes
        ):
            raise GateTransactionError(
                "CANDIDATE_APPROVAL_INPUT_CHANGED",
                "Candidate 승인 검증 후 입력이 변경되어 Commit을 중단했습니다.",
                {},
            )
        commit_gate_transaction(
            args.project_path,
            run_id,
            "CANDIDATE_APPROVAL",
            args.project_path,
            {
                "variation_candidates": approved,
                "candidate_approval": approval,
            },
            dependency_graph,
            next_state,
            {"00_PROJECT/change_log.jsonl": next_log},
        )
    finally:
        release_project_lock(lock_path, run_id)
    print(path)
    return 0


def run_reference_profile(args: argparse.Namespace) -> int:
    """외부 Reference에서 원문을 제외한 Project Profile만 기록한다."""
    project_id = project_id_from_manifest(args.project_path)
    reference_material = load_json_object(args.reference_source)
    policy = load_json_object(ROOT / "STANDARD" / "reference_policy.json")
    sanitized = sanitize_reference_profile(reference_material, policy)
    profile = {
        "project_id": project_id,
        "mode": "REFERENCE_INSPIRED",
        **sanitized,
    }
    path = args.project_path / "00_PROJECT" / "reference_profile.json"
    write_json_object(path, profile)
    changed_at = utc_now()
    record_artifact_change(
        args.project_path,
        "reference_profile",
        path,
        changed_at,
    )
    append_change_log(
        args.project_path,
        "REFERENCE_PROFILE_SANITIZED",
        {"reference_id": sanitized["reference_id"]},
        changed_at,
    )
    print(path)
    return 0


def run_precheck(args: argparse.Namespace) -> int:
    """전체 Variation의 Story History Novelty Precheck를 실행한다."""
    candidates = load_json_object(args.project_path / "00_PROJECT" / "variation_candidates.json")
    report = evaluate_variation_precheck_bound(
        candidates,
        (
            load_json_object(
                args.project_path / "00_PROJECT" / "candidate_event_briefs.json"
            )
            if (args.project_path / "00_PROJECT" / "candidate_event_briefs.json").is_file()
            else None
        ),
        load_story_history(ROOT / "STORY_LIBRARY" / "novelty_index.json"),
        load_json_object(ROOT / "STANDARD" / "novelty_thresholds.json"),
    )
    path = args.project_path / "08_QA" / "novelty_precheck.json"
    write_json_object(path, report)
    changed_at = utc_now()
    record_artifact_change(
        args.project_path,
        "novelty_precheck",
        path,
        changed_at,
    )
    append_change_log(
        args.project_path,
        "VARIATION_NOVELTY_PRECHECKED",
        {"result": report["result"]},
        changed_at,
    )
    print(path)
    return 0 if report["result"] == "PASS" else 1


def append_history_record(path: Path, record: Mapping[str, object]) -> None:
    """Story Library 감사 이력을 JSONL로 추가한다."""
    try:
        with path.open("a", encoding="utf-8") as output_file:
            output_file.write(json.dumps(dict(record), ensure_ascii=False) + "\n")
    except OSError as error:
        raise ConfigurationError(
            f"Story Library 이력 기록에 실패했습니다: path={path}, detail={error}"
        ) from error


def run_register(args: argparse.Namespace) -> int:
    """Production Ready Fingerprint를 Story Library에 등록한다."""
    audit = audit_project(ROOT, args.project_path, None, None, utc_now())
    if audit["production_ready"] is not True:
        raise GateTransactionError(
            "PRODUCTION_READY_AUDIT_FAILED",
            "현재 Canonical Artifact와 Process가 Production Ready 감사를 통과하지 못했습니다.",
            {"audit": audit},
        )
    state = load_project_state(args.project_path)
    fingerprint = load_json_object(args.project_path / "00_PROJECT" / "story_fingerprint.json")
    library = load_json_object(args.library)
    next_library = register_story_fingerprint(library, fingerprint, state)
    registered_at = utc_now()
    write_json_object(args.library, next_library)
    append_history_record(
        args.history,
        make_history_record(fingerprint, registered_at),
    )
    append_change_log(
        args.project_path,
        "STORY_LIBRARY_REGISTERED",
        {"library": str(args.library)},
        registered_at,
    )
    print(args.library)
    return 0


def run_task_open(args: argparse.Namespace) -> int:
    """현재 Gate의 Codex Task Workspace를 연다."""
    gate_index(args.gate_id)
    record = task_open(
        ROOT,
        args.project_path,
        args.gate_id,
        utc_now(),
        args.reference_source if isinstance(args.reference_source, Path) else None,
    )
    print(json.dumps(record, ensure_ascii=False, indent=2))
    return 0


def run_task_status(args: argparse.Namespace) -> int:
    """현재 또는 최근 Codex Gate Task 상태를 출력한다."""
    status = task_status(ROOT, args.project_path)
    print(json.dumps(status, ensure_ascii=False, indent=2))
    return 0


def run_task_submit(args: argparse.Namespace) -> int:
    """Gate Workspace를 검증하고 원자 Commit한다."""
    gate_index(args.gate_id)
    submitted_at = utc_now()
    result = task_submit(
        ROOT,
        args.project_path,
        args.gate_id,
        submitted_at,
        args.reference_source if isinstance(args.reference_source, Path) else None,
    )
    if result.get("status") != "COMMITTED":
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    sync_novelty_gate(
        repository_root_for_project(args.project_path),
        args.project_path,
        args.gate_id,
        submitted_at,
    )
    append_change_log(
        args.project_path,
        "CODEX_GATE_TRANSACTION_COMMITTED",
        {
            "gate_id": args.gate_id,
            "transaction_id": result["transaction_id"],
            "runtime_transaction_id": result["runtime_transaction_id"],
            "commit_sha": result["commit_sha"],
        },
        submitted_at,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


def run_task_abort(args: argparse.Namespace) -> int:
    """현재 Gate Workspace를 Canonical 변경 없이 중단한다."""
    gate_index(args.gate_id)
    record = task_abort(ROOT, args.project_path, args.gate_id, utc_now())
    print(json.dumps(record, ensure_ascii=False, indent=2))
    return 0


def run_task_return(args: argparse.Namespace) -> int:
    """Critic Issue를 Owner Agent의 재작업 Gate로 반환한다."""
    returned_at = utc_now()
    result = return_task_to_owner(
        ROOT,
        args.project_path,
        args.owner_agent,
        args.actor,
        args.reason,
        returned_at,
    )
    target_gate = result.get("target_gate")
    if isinstance(target_gate, str) and gate_index(target_gate) <= gate_index("GATE-10"):
        sync_novelty_revision(
            repository_root_for_project(args.project_path),
            args.project_path,
            returned_at,
        )
    append_change_log(
        args.project_path,
        "TASK_RETURNED_TO_OWNER",
        {
            "owner_agent": result["owner_agent"],
            "actor": result["actor"],
            "reason": result["reason"],
            "target_gate": result["target_gate"],
            "process_revision": result["process_revision"],
            "aborted_transaction_id": result["aborted_transaction_id"],
        },
        returned_at,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


def run_audit(args: argparse.Namespace) -> int:
    """Project State를 바꾸지 않는 전체 Artifact와 Process 감사를 실행한다."""
    report = audit_project(
        ROOT,
        args.project_path,
        args.reference_source if isinstance(args.reference_source, Path) else None,
        args.channel if isinstance(args.channel, Path) else None,
        utc_now(),
    )
    write_json_object(args.project_path / "08_QA" / "audit_report.json", report)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["result"] == "PASS" else 1


def run_broadcast_readable_config_set(args: argparse.Namespace) -> int:
    """Broadcast Readable Config Admission Transaction을 실행한다."""
    result = admit_broadcast_readable_config(
        args.project_path,
        args.input,
        args.actor,
        args.reason,
        utc_now(),
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


def run_rebuild_state(args: argparse.Namespace) -> int:
    """명시적 Force가 있을 때만 현재 Artifact에서 Project State를 복구한다."""
    if args.force is not True:
        raise ConfigurationError(
            "rebuild-state는 명시적 Human Confirmation인 --force가 필요합니다."
        )
    dependency_graph = load_json_object(ROOT / "STANDARD" / "dependency_graph.json")
    report = full_validation_report(
        ROOT,
        args.project_path,
        args.reference_source if isinstance(args.reference_source, Path) else None,
        args.channel if isinstance(args.channel, Path) else None,
    )
    rebuilt_at = utc_now()
    write_qa_reports(args.project_path, report["project_id"], report["issues"])
    write_json_object(
        args.project_path / "08_QA" / "validation_report.json",
        report,
    )
    state = synchronize_project_state(
        args.project_path,
        dependency_graph,
        report["gate_results"],
        report["issues"],
        rebuilt_at,
    )
    conformant, _missing = process_conformance(
        trace_records(ROOT, args.project_path),
        state["readiness"]["process_start_gate"],
        "GATE-13",
        state["readiness"]["process_revision"],
    )
    state["readiness"]["process_status"] = (
        "PROCESS_CONFORMANT"
        if conformant and state["current_gate"] == "GATE-13"
        else "NONCONFORMANT"
    )
    write_json_object(
        args.project_path / "00_PROJECT" / "project_state.json",
        state,
    )
    append_change_log(
        args.project_path,
        "PROJECT_STATE_REBUILT",
        {
            "result": report["result"],
            "current_gate": state["current_gate"],
            "process_conformant": state["readiness"]["process_status"] == "PROCESS_CONFORMANT",
        },
        rebuilt_at,
    )
    print(json.dumps(state, ensure_ascii=False, indent=2))
    return 0 if report["result"] == "PASS" else 1


def run_editorial_approve(args: argparse.Namespace) -> int:
    """Human Editorial Approval을 Actor와 Reason과 함께 기록한다."""
    run_id = f"EDITORIAL-{uuid4().hex[:16].upper()}"
    lock_path = acquire_project_lock(args.project_path, run_id)
    try:
        audit = audit_project(ROOT, args.project_path, None, None, utc_now())
        if audit["result"] != "PASS":
            raise GateTransactionError(
                "EDITORIAL_APPROVAL_AUDIT_FAILED",
                "Editorial 승인 전 Canonical Artifact와 Process 감사를 통과해야 합니다.",
                {"audit": audit},
            )
        state = load_project_state(args.project_path)
        review = load_json_object(args.project_path / "08_QA" / "editorial_review.json")
        dependency_graph = load_json_object(ROOT / "STANDARD" / "dependency_graph.json")
        auditable_artifacts = set(audit_artifact_names(ROOT, args.project_path, dependency_graph))
        reviewed_artifacts = load_selected_project_artifacts(
            args.project_path,
            dependency_graph,
            [
                artifact_name
                for artifact_name in EDITORIAL_REVIEWED_ARTIFACTS
                if artifact_name in auditable_artifacts
            ],
        )
        approved_at = utc_now()
        approved = approve_editorial_review(
            state,
            review,
            editorial_artifact_hashes(reviewed_artifacts),
            reviewed_artifacts,
            args.actor,
            args.reason,
            approved_at,
        )
        write_json_object(
            args.project_path / "00_PROJECT" / "project_state.json",
            approved,
        )
        append_change_log(
            args.project_path,
            "EDITORIAL_APPROVED",
            {"actor": args.actor, "reason": args.reason},
            approved_at,
        )
    finally:
        release_project_lock(lock_path, run_id)
    print(json.dumps(approved, ensure_ascii=False, indent=2))
    return 0


def run_production_finalize(args: argparse.Namespace) -> int:
    """모든 독립 준비 조건이 충족된 Project를 Production Ready로 전이한다."""
    run_id = f"FINALIZE-{uuid4().hex[:16].upper()}"
    lock_path = acquire_project_lock(args.project_path, run_id)
    try:
        finalized_at = utc_now()
        state = load_project_state(args.project_path)
        trace_conformant, missing_traces = process_conformance(
            trace_records(ROOT, args.project_path),
            state["readiness"]["process_start_gate"],
            "GATE-13",
            state["readiness"]["process_revision"],
        )
        if state["readiness"]["process_status"] != "PROCESS_CONFORMANT" or not trace_conformant:
            raise GateTransactionError(
                "PROCESS_TRACE_MISSING",
                "Production Ready 전이에 필요한 Process Trace가 완전하지 않습니다.",
                {
                    "process_start_gate": state["readiness"]["process_start_gate"],
                    "current_gate": state["current_gate"],
                    "missing_gate_traces": missing_traces,
                },
            )
        audit = audit_project(ROOT, args.project_path, None, None, finalized_at)
        if audit["result"] != "PASS":
            raise GateTransactionError(
                "PRODUCTION_READY_AUDIT_FAILED",
                "Production Ready 전 Canonical Artifact와 Process 감사를 통과해야 합니다.",
                {"audit": audit},
            )
        finalized = finalize_production_ready(
            state,
            load_json_object(args.project_path / "08_QA" / "editorial_review.json"),
            finalized_at,
        )
        write_json_object(
            args.project_path / "00_PROJECT" / "project_state.json",
            finalized,
        )
        append_change_log(
            args.project_path,
            "PRODUCTION_READY_FINALIZED",
            {"current_gate": finalized["current_gate"]},
            finalized_at,
        )
        sync_novelty_production_ready(
            repository_root_for_project(args.project_path),
            args.project_path,
            finalized_at,
        )
    finally:
        release_project_lock(lock_path, run_id)
    print(json.dumps(finalized, ensure_ascii=False, indent=2))
    return 0


def run_cli(argv: Sequence[str]) -> int:
    """테스트 가능한 인자 배열로 통합 CLI를 실행한다."""
    parser = build_parser()
    args = parser.parse_args(list(argv))
    try:
        if args.command == "init":
            return run_init(args)
        if args.command == "compat":
            return run_compat(args)
        if args.command == "variations":
            return run_variations(args)
        if args.command == "validate":
            return run_validate(args)
        if args.command == "approve":
            return run_approve(args)
        if args.command == "candidate-eligibility":
            return run_candidate_eligibility(args)
        if args.command == "reference-profile":
            return run_reference_profile(args)
        if args.command == "evidence-submit":
            return run_evidence_submit(args)
        if args.command == "precheck":
            return run_precheck(args)
        if args.command == "register":
            return run_register(args)
        if args.command == "task-open":
            return run_task_open(args)
        if args.command == "task-status":
            return run_task_status(args)
        if args.command == "task-submit":
            return run_task_submit(args)
        if args.command == "task-abort":
            return run_task_abort(args)
        if args.command == "task-return":
            return run_task_return(args)
        if args.command == "audit":
            return run_audit(args)
        if args.command == "broadcast-readable-config-set":
            return run_broadcast_readable_config_set(args)
        if args.command == "rebuild-state":
            return run_rebuild_state(args)
        if args.command == "editorial-approve":
            return run_editorial_approve(args)
        if args.command == "production-finalize":
            return run_production_finalize(args)
        if args.command == "migrate-channel-pin":
            return run_migrate_channel_pin(args)
        if args.command == "migrate-legacy-v1-1":
            return run_migrate_legacy_v1_1(args)
        raise ConfigurationError(f"알 수 없는 명령입니다: command={args.command}")
    except StarterKitError as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 2
    except RuntimeExecutionError as error:
        print(
            f"ERROR: {error.code}: {error}; context={error.safe_context}",
            file=sys.stderr,
        )
        return 2


def main() -> None:
    """Shell Entry Point로 CLI를 실행한다."""
    raise SystemExit(run_cli(sys.argv[1:]))


if __name__ == "__main__":
    main()
