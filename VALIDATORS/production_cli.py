"""Project Scaffold, Variation, Production Gate를 실행하는 통합 CLI."""

import argparse
import json
import sys
from collections.abc import Mapping, Sequence
from copy import deepcopy
from datetime import UTC, datetime
from pathlib import Path
from typing import cast

from VALIDATORS.cli import (
    evaluate_compatibility_documents,
    raise_for_configuration_schema_errors,
)
from VALIDATORS.compatibility import make_project_compatibility_report
from VALIDATORS.dependency import (
    artifact_hash,
    dependency_artifacts,
    invalidate_artifact_dependents,
    mark_artifact_clean,
    transitive_dependents,
)
from VALIDATORS.exceptions import ConfigurationError, StarterKitError
from VALIDATORS.io import load_json_object, write_json_object
from VALIDATORS.library import make_history_record, register_story_fingerprint
from VALIDATORS.models import ProjectState, ValidationIssue
from VALIDATORS.novelty import evaluate_variation_precheck
from VALIDATORS.pipeline import load_project_artifacts, run_production_validation
from VALIDATORS.reference_validation import sanitize_reference_profile
from VALIDATORS.scaffold import create_project_scaffold
from VALIDATORS.schema_validation import collect_schema_errors
from VALIDATORS.state_machine import GATES, advance_gate, gate_index
from VALIDATORS.variation import approve_variation_candidate, generate_variation_candidates

ROOT = Path.cwd().resolve()
NOVELTY_CODES = {"CAUSAL_HARD_COLLISION", "STORY_SIMILARITY_EXCEEDED"}
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
        default=ROOT / "CHANNELS" / "mystery_main" / "channel_dna.json",
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

    precheck_parser = subparsers.add_parser(
        "precheck",
        help="승인 Variation을 Story History와 사전 비교합니다.",
    )
    precheck_parser.add_argument("project_path", type=Path)

    reference_parser = subparsers.add_parser(
        "reference-profile",
        help="외부 Reference를 정제된 Project Profile로 변환합니다.",
    )
    reference_parser.add_argument("project_path", type=Path)
    reference_parser.add_argument("reference_source", type=Path)

    validate_parser = subparsers.add_parser(
        "validate",
        help="GATE-00부터 GATE-13까지 전체 Project를 검증합니다.",
    )
    validate_parser.add_argument("project_path", type=Path)
    validate_parser.add_argument(
        "--channel",
        type=Path,
        default=ROOT / "CHANNELS" / "mystery_main" / "channel_dna.json",
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
        default=ROOT / "STORY_LIBRARY" / "story_fingerprints.json",
    )
    register_parser.add_argument(
        "--history",
        type=Path,
        default=ROOT / "STORY_LIBRARY" / "story_history.jsonl",
    )
    return parser


def project_id_from_manifest(project_path: Path) -> str:
    """Project Manifest에서 Project ID를 읽는다."""
    manifest = load_json_object(project_path / "00_PROJECT" / "project_manifest.json")
    project_id = manifest.get("project_id")
    if not isinstance(project_id, str):
        raise ConfigurationError("project_manifest.project_id 문자열이 필요합니다.")
    return project_id


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
    )
    definitions = dependency_artifacts(dependency_graph)
    artifacts_changed = False
    next_state = state
    for artifact_name in gate_zero_artifacts:
        definition = definitions.get(artifact_name)
        if not isinstance(definition, Mapping):
            raise ConfigurationError(
                f"GATE-00 Artifact 정의가 없습니다: artifact={artifact_name}"
            )
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
    gate_zero_already_passed = (
        current_gate != "NONE"
        and gate_index(current_gate) >= gate_index("GATE-00")
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
    )
    write_json_object(project_path / "00_PROJECT" / "project_state.json", synchronized)
    return synchronized


def require_variation_prerequisites(project_path: Path, project_id: str) -> None:
    """Variation 생성 전에 Project-aware Compatibility PASS를 강제한다."""
    state = load_project_state(project_path)
    report = load_json_object(
        project_path / "00_PROJECT" / "compatibility_report.json"
    )
    current_gate = state["current_gate"]
    gate_passed = (
        current_gate != "NONE"
        and gate_index(current_gate) >= gate_index("GATE-00")
    )
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
    """Story Library의 Fingerprint 배열을 엄격하게 읽는다."""
    library = load_json_object(path)
    fingerprints = library.get("fingerprints")
    if not isinstance(fingerprints, list) or not all(
        isinstance(fingerprint, Mapping) for fingerprint in fingerprints
    ):
        raise ConfigurationError(
            f"Story Library fingerprints 객체 배열이 필요합니다: path={path}"
        )
    return list(fingerprints)


def append_change_log(
    project_path: Path,
    event: str,
    detail: Mapping[str, object],
    occurred_at: str,
) -> None:
    """Project 변경 이력을 JSONL에 추가한다."""
    record = {
        "occurred_at": occurred_at,
        "event": event,
        "detail": dict(detail),
    }
    log_path = project_path / "00_PROJECT" / "change_log.jsonl"
    try:
        with log_path.open("a", encoding="utf-8") as output_file:
            output_file.write(json.dumps(record, ensure_ascii=False) + "\n")
    except OSError as error:
        raise ConfigurationError(
            f"Project Change Log 기록에 실패했습니다: path={log_path}, detail={error}"
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
    initial_state = load_project_state(project_path)
    state = clean_existing_artifacts(
        project_path,
        dependency_graph,
        initial_state,
        updated_at,
    )
    state["state"] = "INITIALIZED"
    state["current_gate"] = "NONE"
    for gate in GATES:
        gate_id = gate["gate_id"]
        passed = gate_results.get(gate_id) == "PASS"
        state = advance_gate(state, gate_id, passed, updated_at)
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
    invalid_names = {
        path_to_name.get(issue["artifact"], issue["artifact"])
        for issue in issues
    }
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
    contract_path = ROOT / "STANDARD" / "compatibility_contract.json"
    defaults_path = ROOT / "STANDARD" / "standard_defaults.json"
    contract_schema_path = (
        ROOT / "STANDARD" / "schemas" / "compatibility_contract.schema.json"
    )
    defaults_schema_path = (
        ROOT / "STANDARD" / "schemas" / "standard_defaults.schema.json"
    )
    channel_schema_path = ROOT / "STANDARD" / "schemas" / "channel_dna.schema.json"
    channel = load_json_object(args.channel)
    project_id = validate_project_compatibility_configuration(args.project_path, channel)
    report = evaluate_compatibility_documents(
        load_json_object(contract_path),
        load_json_object(defaults_path),
        channel,
        load_json_object(contract_schema_path),
        load_json_object(defaults_schema_path),
        load_json_object(channel_schema_path),
        str(contract_path),
        str(defaults_path),
        str(args.channel),
    )
    project_report = make_project_compatibility_report(project_id, report)
    output_path = args.project_path / "00_PROJECT" / "compatibility_report.json"
    write_json_object(output_path, project_report)
    changed_at = utc_now()
    state = synchronize_compatibility_state(
        args.project_path,
        report["compatibility"] == "PASS",
        changed_at,
    )
    append_change_log(
        args.project_path,
        "PROJECT_COMPATIBILITY_EVALUATED",
        {
            "compatibility": report["compatibility"],
            "error_count": len(report["errors"]),
            "current_gate": state["current_gate"],
        },
        changed_at,
    )
    print(
        json.dumps(
            {
                "project_id": project_id,
                "compatibility": report["compatibility"],
                "current_gate": state["current_gate"],
                "report": str(output_path),
                "error_count": len(report["errors"]),
            },
            ensure_ascii=False,
        )
    )
    return 0 if report["compatibility"] == "PASS" else 1


def run_variations(args: argparse.Namespace) -> int:
    """Variation 후보 생성 명령을 실행한다."""
    project_id = project_id_from_manifest(args.project_path)
    require_variation_prerequisites(args.project_path, project_id)
    catalog = load_json_object(ROOT / "STANDARD" / "variation_catalog.json")
    candidates = generate_variation_candidates(
        project_id,
        args.seed,
        args.count,
        catalog,
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
    """전체 Production Gate 검증과 상태 동기화를 실행한다."""
    dependency_graph = load_json_object(ROOT / "STANDARD" / "dependency_graph.json")
    artifacts = load_project_artifacts(args.project_path, dependency_graph)
    reference_material = (
        load_json_object(args.reference_source)
        if isinstance(args.reference_source, Path)
        else None
    )
    report = run_production_validation(
        artifacts,
        load_json_object(args.channel),
        load_json_object(ROOT / "STANDARD" / "schemas" / "story_dna.schema.json"),
        load_json_object(
            ROOT / "STANDARD" / "schemas" / "story_fingerprint.schema.json"
        ),
        load_json_object(ROOT / "STANDARD" / "reference_policy.json"),
        load_json_object(ROOT / "STANDARD" / "novelty_thresholds.json"),
        load_story_history(ROOT / "STORY_LIBRARY" / "story_fingerprints.json"),
        reference_material,
    )
    project_id = report["project_id"]
    write_qa_reports(args.project_path, project_id, report["issues"])
    report_path = args.project_path / "08_QA" / "validation_report.json"
    write_json_object(report_path, report)
    state = synchronize_project_state(
        args.project_path,
        dependency_graph,
        report["gate_results"],
        report["issues"],
        utc_now(),
    )
    append_change_log(
        args.project_path,
        "PRODUCTION_VALIDATED",
        {"result": report["result"], "state": state["state"]},
        utc_now(),
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["result"] == "PASS" else 1


def run_approve(args: argparse.Namespace) -> int:
    """Variation 후보 승인 명령을 실행한다."""
    path = args.project_path / "00_PROJECT" / "variation_candidates.json"
    document = load_json_object(path)
    approved = approve_variation_candidate(document, args.candidate_id)
    write_json_object(path, approved)
    changed_at = utc_now()
    record_artifact_change(
        args.project_path,
        "variation_candidates",
        path,
        changed_at,
    )
    append_change_log(
        args.project_path,
        "VARIATION_APPROVED",
        {"candidate_id": args.candidate_id},
        changed_at,
    )
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
    """승인 Variation의 Story History Novelty Precheck를 실행한다."""
    candidates = load_json_object(
        args.project_path / "00_PROJECT" / "variation_candidates.json"
    )
    report = evaluate_variation_precheck(
        candidates,
        load_story_history(ROOT / "STORY_LIBRARY" / "story_fingerprints.json"),
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
    state = load_project_state(args.project_path)
    fingerprint = load_json_object(
        args.project_path / "00_PROJECT" / "story_fingerprint.json"
    )
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
        if args.command == "reference-profile":
            return run_reference_profile(args)
        if args.command == "precheck":
            return run_precheck(args)
        if args.command == "register":
            return run_register(args)
        raise ConfigurationError(f"알 수 없는 명령입니다: command={args.command}")
    except StarterKitError as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 2


def main() -> None:
    """Shell Entry Point로 CLI를 실행한다."""
    raise SystemExit(run_cli(sys.argv[1:]))


if __name__ == "__main__":
    main()
