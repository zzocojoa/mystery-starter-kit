"""통합 CLI의 실제 디렉터리 E2E 검증."""

import os
from collections.abc import Mapping
from pathlib import Path

import pytest
from project_factory import make_complete_project_artifacts, write_candidate_event_briefs

from RUNTIME.providers.fake import fake_candidate_evaluation
from VALIDATORS.candidate_approval import validate_candidate_approval
from VALIDATORS.candidate_eligibility import (
    build_candidate_eligibility,
    build_candidate_eligibility_bound,
    validate_candidate_eligibility,
)
from VALIDATORS.candidate_evaluation import validate_candidate_evaluation
from VALIDATORS.channel_registry import resolve_project_channel
from VALIDATORS.io import load_json_object, write_json_object
from VALIDATORS.pipeline import ArtifactContent, validate_variation_precheck
from VALIDATORS.production_cli import ROOT, run_cli
from VALIDATORS.schema_validation import collect_schema_errors


def write_candidate_evaluation(project_path: Path) -> str:
    """현재 Variation과 Novelty Precheck에서 평가 Artifact를 작성한다."""
    variations = load_json_object(
        project_path / "00_PROJECT" / "variation_candidates.json"
    )
    precheck = load_json_object(project_path / "08_QA" / "novelty_precheck.json")
    project_id = variations.get("project_id")
    assert isinstance(project_id, str)
    config = load_json_object(project_path / "00_PROJECT" / "production_config.json")
    constraints = load_json_object(
        project_path / "00_PROJECT" / "project_constraints.json"
    )
    channel, _manifest, _path = resolve_project_channel(ROOT, config, None)
    brief_path = project_path / "00_PROJECT" / "candidate_event_briefs.json"
    briefs = load_json_object(brief_path) if brief_path.is_file() else None
    eligibility = (
        build_candidate_eligibility_bound(
            config,
            constraints,
            channel,
            variations,
            briefs,
            precheck,
        )
        if briefs is not None
        else build_candidate_eligibility(
            config,
            constraints,
            channel,
            variations,
            precheck,
        )
    )
    write_json_object(project_path / "08_QA" / "candidate_eligibility.json", eligibility)
    evaluation = fake_candidate_evaluation(
        project_id, variations, briefs, precheck, eligibility
    )
    write_json_object(
        project_path / "00_PROJECT" / "candidate_evaluation.json",
        evaluation,
    )
    recommended = evaluation["recommended_candidate_id"]
    assert isinstance(recommended, str)
    return recommended


def prepare_candidate_approval_project(
    tmp_path: Path,
    project_id: str,
) -> tuple[Path, str]:
    """CLI Candidate 승인 직전 상태의 격리 Project를 만든다."""
    projects_root = tmp_path / project_id
    assert run_cli(
        [
            "init",
            project_id,
            "--projects-root",
            str(projects_root),
            "--created-at",
            "2026-08-25T00:00:00Z",
        ]
    ) == 0
    project_path = projects_root / project_id
    assert run_cli(["compat", str(project_path)]) == 0
    assert run_cli(
        [
            "variations",
            str(project_path),
            "--seed",
            "Candidate 승인 원자성 검증",
            "--count",
            "5",
        ]
    ) == 0
    write_candidate_event_briefs(project_path)
    assert run_cli(["precheck", str(project_path)]) == 0
    return project_path, write_candidate_evaluation(project_path)


def write_complete_artifacts(
    project_path: Path,
    artifacts: dict[str, ArtifactContent],
) -> None:
    """Dependency Graph 경로에 완전한 테스트 Artifact를 기록한다."""
    graph = load_json_object(ROOT / "STANDARD" / "dependency_graph.json")
    definitions = graph["artifacts"]
    assert isinstance(definitions, dict)
    for artifact_name, content in artifacts.items():
        definition = definitions.get(artifact_name)
        if not isinstance(definition, dict):
            continue
        relative_path = definition["path"]
        assert isinstance(relative_path, str)
        path = project_path / relative_path
        if isinstance(content, str):
            path.write_text(content, encoding="utf-8")
        else:
            write_json_object(path, content)


def configure_legacy_v1_project(project_path: Path) -> None:
    """활성 v2 Scaffold를 기존 1.1 회귀 검증용 Pin과 제약으로 고정한다."""
    config_path = project_path / "00_PROJECT" / "production_config.json"
    constraints_path = project_path / "00_PROJECT" / "project_constraints.json"
    config = load_json_object(config_path)
    config.update(
        {
            "channel_content_version": "1.1.0",
            "variation_engine_version": "1.0.0",
            "variation_catalog_version": "1.0.0",
            "genre": "MYSTERY",
        }
    )
    constraints = load_json_object(constraints_path)
    production_limits = constraints["production_limits"]
    assert isinstance(production_limits, dict)
    production_limits.update(
        {
            "max_production_complexity": "EXTREME",
            "max_special_effect_level": "HIGH",
            "allow_child_actor": True,
            "allow_moving_vehicle": True,
            "max_graphic_violence": "GRAPHIC",
            "enforce_final_footprint": False,
        }
    )
    write_json_object(config_path, config)
    write_json_object(constraints_path, constraints)


def test_validate_audits_without_reconstructing_state(tmp_path: Path) -> None:
    """전체 Artifact PASS도 Validate 단독으로 State나 Library를 승인하지 않는다."""
    projects_root = tmp_path / "projects"
    init_code = run_cli(
        [
            "init",
            "PRJ-002",
            "--projects-root",
            str(projects_root),
            "--created-at",
            "2026-08-25T00:00:00Z",
        ]
    )
    project_path = projects_root / "PRJ-002"
    configure_legacy_v1_project(project_path)
    compat_code = run_cli(["compat", str(project_path)])
    variation_code = run_cli(
        [
            "variations",
            str(project_path),
            "--seed",
            "공장 교대 중 사라진 작업자",
            "--count",
            "5",
        ]
    )
    precheck_code = run_cli(["precheck", str(project_path)])
    recommended = write_candidate_evaluation(project_path)
    approve_code = run_cli(["approve", str(project_path), recommended])
    artifacts = make_complete_project_artifacts()
    for generated_artifact in (
        "compatibility_report",
        "variation_candidates",
        "candidate_eligibility",
        "candidate_evaluation",
        "candidate_approval",
        "novelty_precheck",
    ):
        del artifacts[generated_artifact]
    write_complete_artifacts(project_path, artifacts)
    refreshed_recommendation = write_candidate_evaluation(project_path)
    assert run_cli(["approve", str(project_path), refreshed_recommendation]) == 0
    state_path = project_path / "00_PROJECT" / "project_state.json"
    state_before = state_path.read_bytes()

    validate_code = run_cli(["validate", str(project_path)])
    state = load_json_object(state_path)
    report = load_json_object(project_path / "08_QA" / "audit_report.json")
    library_path = tmp_path / "story_fingerprints.json"
    history_path = tmp_path / "story_history.jsonl"
    write_json_object(
        library_path,
        {
            "schema_family": "story-library",
            "schema_version": "1.0.0",
            "fingerprints": [],
        },
    )
    register_code = run_cli(
        [
            "register",
            str(project_path),
            "--library",
            str(library_path),
            "--history",
            str(history_path),
        ]
    )
    library = load_json_object(library_path)

    assert init_code == 0
    assert compat_code == 0
    assert variation_code == 0
    assert approve_code == 0
    assert precheck_code == 0
    assert validate_code == 0
    assert register_code == 2
    validation = report["validation"]
    process_issues = report["process_issues"]
    assert isinstance(validation, Mapping)
    assert isinstance(process_issues, list)
    assert process_issues
    process_issue = process_issues[0]
    assert isinstance(process_issue, Mapping)
    assert validation["result"] == "PASS"
    assert report["result"] == "FAIL"
    assert process_issue["code"] == "PROCESS_TRACE_MISSING"
    assert state_path.read_bytes() == state_before
    assert state["state"] != "PRODUCTION_READY"
    fingerprints = library["fingerprints"]
    assert isinstance(fingerprints, list)
    assert fingerprints == []
    assert not history_path.exists()


def test_reference_profile_command_never_copies_raw_story_content(tmp_path: Path) -> None:
    """Reference 정제 명령은 외부 원문과 Story Content를 Project에 복사하지 않아야 한다."""
    projects_root = tmp_path / "projects"
    assert run_cli(
        [
            "init",
            "PRJ-003",
            "--projects-root",
            str(projects_root),
            "--created-at",
            "2026-08-25T00:00:00Z",
        ]
    ) == 0
    source_path = tmp_path / "reference-source.json"
    write_json_object(
        source_path,
        {
            "reference_id": "REF-003",
            "selected_style_features": ["PACING", "SUSPENSE_HANDLING"],
            "raw_text": "외부 원문의 고유 문장",
            "story_content": {"CHARACTERS": ["고유 인물"]},
        },
    )
    project_path = projects_root / "PRJ-003"

    result = run_cli(
        ["reference-profile", str(project_path), str(source_path)]
    )
    profile = load_json_object(project_path / "00_PROJECT" / "reference_profile.json")

    assert result == 0
    assert profile["mode"] == "REFERENCE_INSPIRED"
    assert "raw_text" not in profile
    assert "story_content" not in profile
    assert "고유 인물" not in str(profile)
    schema = load_json_object(ROOT / "STANDARD" / "schemas" / "reference_profile.schema.json")
    assert collect_schema_errors(profile, schema, "sanitized_profile") == []


def test_failed_validation_preserves_project_state(tmp_path: Path) -> None:
    """진단 실패는 문제를 보고하되 Project State를 재구성하지 않는다."""
    projects_root = tmp_path / "projects"
    assert run_cli(
        [
            "init",
            "PRJ-002",
            "--projects-root",
            str(projects_root),
            "--created-at",
            "2026-08-25T00:00:00Z",
        ]
    ) == 0
    project_path = projects_root / "PRJ-002"
    artifacts = make_complete_project_artifacts()
    presentation = artifacts["presentation_plan"]
    assert isinstance(presentation, dict)
    segments = presentation["segments"]
    assert isinstance(segments, list)
    first_segment = segments[0]
    assert isinstance(first_segment, dict)
    first_segment["duration_sec"] = 1
    write_complete_artifacts(project_path, artifacts)
    state_path = project_path / "00_PROJECT" / "project_state.json"
    state_before = state_path.read_bytes()

    result = run_cli(["validate", str(project_path)])
    report = load_json_object(project_path / "08_QA" / "audit_report.json")
    validation = report["validation"]
    assert isinstance(validation, dict)
    issues = validation["issues"]
    assert isinstance(issues, list)

    assert result == 1
    assert state_path.read_bytes() == state_before
    assert any(
        isinstance(issue, dict)
        and issue.get("code") == "PRESENTATION_SEGMENT_ORDER_MISMATCH"
        for issue in issues
    )


def test_validate_never_migrates_missing_presentation_artifacts(tmp_path: Path) -> None:
    """Validate는 누락 파일을 복구하거나 기존 Script와 State를 변경하지 않는다."""
    projects_root = tmp_path / "projects"
    assert run_cli(
        [
            "init",
            "PRJ-005",
            "--projects-root",
            str(projects_root),
            "--created-at",
            "2026-08-25T00:00:00Z",
        ]
    ) == 0
    project_path = projects_root / "PRJ-005"
    artifacts = make_complete_project_artifacts()
    manifest = artifacts["project_manifest"]
    production = artifacts["production_config"]
    assert isinstance(manifest, dict)
    assert isinstance(production, dict)
    manifest["project_id"] = "PRJ-005"
    production["project_id"] = "PRJ-005"
    write_complete_artifacts(project_path, artifacts)
    state_path = project_path / "00_PROJECT" / "project_state.json"
    prior_state = load_json_object(state_path)
    prior_state["state"] = "PRODUCTION_READY"
    prior_state["current_gate"] = "GATE-13"
    write_json_object(state_path, prior_state)
    legacy_script = "# 기존 최종 대본\n\nSCN-08 정정된 사건"
    legacy_plan = {
        "project_id": "PRJ-005",
        "modes": ["DRAMA", "NARRATION", "REACTION"],
        "reaction_ratio": 0.2,
        "scene_presentations": [{"scene_id": "SCN-08", "mode": "DRAMA"}],
    }
    write_json_object(project_path / "06_SCENE" / "presentation_plan.json", legacy_plan)
    (project_path / "07_SCRIPT" / "final_script.md").write_text(
        legacy_script,
        encoding="utf-8",
    )
    (project_path / "06_SCENE" / "panel_cast.json").unlink()
    state_before = state_path.read_bytes()

    result = run_cli(["validate", str(project_path)])
    preserved_script = (project_path / "07_SCRIPT" / "final_script.md").read_text(
        encoding="utf-8"
    )

    assert result == 2
    assert state_path.read_bytes() == state_before
    assert not (project_path / "06_SCENE" / "panel_cast.json").exists()
    assert preserved_script == legacy_script


def test_rebuild_state_requires_explicit_force(tmp_path: Path) -> None:
    """Project State 복구는 명시적 Force 없이 실행되지 않는다."""
    projects_root = tmp_path / "projects"
    assert run_cli(
        [
            "init",
            "PRJ-006",
            "--projects-root",
            str(projects_root),
            "--created-at",
            "2026-08-25T00:00:00Z",
        ]
    ) == 0
    project_path = projects_root / "PRJ-006"
    state_path = project_path / "00_PROJECT" / "project_state.json"
    state_before = state_path.read_bytes()

    result = run_cli(["rebuild-state", str(project_path)])

    assert result == 2
    assert state_path.read_bytes() == state_before


def test_variation_precheck_evaluation_and_approval_form_gate_one(
    tmp_path: Path,
) -> None:
    """후보·Precheck·평가·승인 순서가 GATE-01 계약을 만족한다."""
    projects_root = tmp_path / "projects"
    assert run_cli(
        [
            "init",
            "PRJ-004",
            "--projects-root",
            str(projects_root),
            "--created-at",
            "2026-08-25T00:00:00Z",
        ]
    ) == 0
    project_path = projects_root / "PRJ-004"
    assert run_cli(["compat", str(project_path)]) == 0
    compatibility = load_json_object(
        project_path / "00_PROJECT" / "compatibility_report.json"
    )
    state = load_json_object(project_path / "00_PROJECT" / "project_state.json")

    assert run_cli(
        [
            "variations",
            str(project_path),
            "--seed",
            "야간 창고의 사라진 기록",
            "--count",
            "5",
        ]
    ) == 0
    write_candidate_event_briefs(project_path)
    assert run_cli(["precheck", str(project_path)]) == 0
    recommended = write_candidate_evaluation(project_path)
    assert run_cli(["approve", str(project_path), recommended]) == 0
    report = load_json_object(project_path / "08_QA" / "novelty_precheck.json")
    candidates = load_json_object(
        project_path / "00_PROJECT" / "variation_candidates.json"
    )

    assert report["result"] == "PASS"
    assert "approved_candidate_id" not in report
    assert candidates["approved_candidate_id"] == recommended
    assert compatibility["project_id"] == "PRJ-004"
    assert compatibility["compatibility"] == "PASS"
    assert state["current_gate"] == "GATE-00"


def test_approve_before_candidate_evaluation_fails(tmp_path: Path) -> None:
    """Candidate Evaluation이 없으면 approve는 명시적으로 실패한다."""
    projects_root = tmp_path / "projects"
    assert run_cli(
        [
            "init",
            "PRJ-008",
            "--projects-root",
            str(projects_root),
            "--created-at",
            "2026-08-25T00:00:00Z",
        ]
    ) == 0
    project_path = projects_root / "PRJ-008"
    assert run_cli(["compat", str(project_path)]) == 0
    assert run_cli(
        [
            "variations",
            str(project_path),
            "--seed",
            "평가 전 승인 차단",
            "--count",
            "5",
        ]
    ) == 0

    assert run_cli(["approve", str(project_path), "VAR-01"]) == 2


def test_approve_recalculates_tampered_eligibility(tmp_path: Path) -> None:
    """저장된 적격성 결과를 변조해도 CLI Core 재계산에서 차단한다."""
    project_path, recommended = prepare_candidate_approval_project(tmp_path, "PRJ-920")
    path = project_path / "08_QA" / "candidate_eligibility.json"
    eligibility = load_json_object(path)
    eligibility["eligible_candidate_ids"] = []
    write_json_object(path, eligibility)

    assert run_cli(["approve", str(project_path), recommended]) == 2
    candidates = load_json_object(
        project_path / "00_PROJECT" / "variation_candidates.json"
    )
    assert candidates["approved_candidate_id"] is None


def test_approve_rejects_stale_candidate_evaluation(tmp_path: Path) -> None:
    """평가 뒤 Candidate 입력이 바뀌면 저장된 평가를 승인하지 않는다."""
    project_path, recommended = prepare_candidate_approval_project(tmp_path, "PRJ-921")
    path = project_path / "00_PROJECT" / "candidate_evaluation.json"
    evaluation = load_json_object(path)
    input_hashes = evaluation["input_hashes"]
    assert isinstance(input_hashes, dict)
    input_hashes["variation_candidates"] = "0" * 64
    write_json_object(path, evaluation)

    assert run_cli(["approve", str(project_path), recommended]) == 2


def test_brief_mutation_invalidates_precheck_evaluation_and_approval(
    tmp_path: Path,
) -> None:
    """승인 뒤 사건 Brief 변경은 모든 후속 Hash 결속을 무효화한다."""
    project_path, recommended = prepare_candidate_approval_project(tmp_path, "PRJ-927")
    assert run_cli(["approve", str(project_path), recommended]) == 0
    config = load_json_object(project_path / "00_PROJECT/production_config.json")
    constraints = load_json_object(project_path / "00_PROJECT/project_constraints.json")
    variations = load_json_object(project_path / "00_PROJECT/variation_candidates.json")
    briefs = load_json_object(project_path / "00_PROJECT/candidate_event_briefs.json")
    precheck = load_json_object(project_path / "08_QA/novelty_precheck.json")
    eligibility = load_json_object(project_path / "08_QA/candidate_eligibility.json")
    evaluation = load_json_object(project_path / "00_PROJECT/candidate_evaluation.json")
    approval = load_json_object(project_path / "00_PROJECT/candidate_approval.json")
    channel, _manifest, _path = resolve_project_channel(ROOT, config, None)
    raw_briefs = briefs["briefs"]
    assert isinstance(raw_briefs, list)
    first_brief = raw_briefs[0]
    assert isinstance(first_brief, dict)
    first_brief["motive_summary"] = "승인 뒤 바뀐 보복 동기와 책임 경로"

    assert {
        issue["code"]
        for issue in validate_variation_precheck(variations, briefs, precheck)
    } == {"STALE_CANDIDATE_EVENT_BRIEF_NOVELTY_PRECHECK"}
    assert validate_candidate_eligibility(
        config,
        constraints,
        channel,
        variations,
        briefs,
        precheck,
        eligibility,
    )[0]["code"] == "CANDIDATE_ELIGIBILITY_MISMATCH"
    assert "CANDIDATE_EVALUATION_STALE" in {
        issue["code"]
        for issue in validate_candidate_evaluation(
            variations,
            briefs,
            evaluation,
            precheck,
            eligibility,
        )
    }
    approval_issues = validate_candidate_approval(
        config,
        variations,
        briefs,
        precheck,
        eligibility,
        evaluation,
        approval,
    )
    assert approval_issues[0]["code"] == "CANDIDATE_APPROVAL_INVALID"
    problems = approval_issues[0]["context"]["problems"]
    assert isinstance(problems, list)
    assert "APPROVAL_STALE" in problems


def test_nonrecommended_candidate_requires_explicit_override(tmp_path: Path) -> None:
    """추천 외 적격 후보는 Override Actor와 Reason 없이 승인할 수 없다."""
    project_path, recommended = prepare_candidate_approval_project(tmp_path, "PRJ-922")
    eligibility = load_json_object(
        project_path / "08_QA" / "candidate_eligibility.json"
    )
    eligible = eligibility["eligible_candidate_ids"]
    assert isinstance(eligible, list)
    selected = next(
        candidate_id
        for candidate_id in eligible
        if isinstance(candidate_id, str) and candidate_id != recommended
    )

    assert run_cli(["approve", str(project_path), selected]) == 2


@pytest.mark.parametrize(
    "target_name",
    [
        "variation_candidates.json",
        "candidate_approval.json",
        "project_state.json",
        "change_log.jsonl",
    ],
)
def test_candidate_approval_rolls_back_each_canonical_write(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    target_name: str,
) -> None:
    """승인 Transaction 어느 Canonical 교체가 실패해도 기존 파일을 복원한다."""
    project_id = {
        "variation_candidates.json": "PRJ-923",
        "candidate_approval.json": "PRJ-924",
        "project_state.json": "PRJ-925",
        "change_log.jsonl": "PRJ-926",
    }[target_name]
    project_path, recommended = prepare_candidate_approval_project(tmp_path, project_id)
    canonical_paths = [
        project_path / "00_PROJECT" / name
        for name in (
            "variation_candidates.json",
            "candidate_approval.json",
            "project_state.json",
            "change_log.jsonl",
        )
    ]
    before = {path: path.read_bytes() for path in canonical_paths}
    original_replace = os.replace
    injected = False

    def fail_target_once(
        source: str | bytes | os.PathLike[str] | os.PathLike[bytes],
        destination: str | bytes | os.PathLike[str] | os.PathLike[bytes],
    ) -> None:
        """지정 Canonical Target의 첫 교체만 실패시킨다."""
        nonlocal injected
        destination_path = Path(os.fsdecode(destination))
        if not injected and destination_path.name == target_name:
            injected = True
            raise OSError(f"injected approval failure: {target_name}")
        original_replace(source, destination)

    monkeypatch.setattr("RUNTIME.transactions.os.replace", fail_target_once)

    assert run_cli(["approve", str(project_path), recommended]) == 2
    assert injected
    assert {path: path.read_bytes() for path in canonical_paths} == before


def test_migrate_channel_pin_preserves_story_artifacts(tmp_path: Path) -> None:
    """Channel Pin Migration은 Story를 쓰지 않고 구성·보고·상태만 갱신한다."""
    projects_root = tmp_path / "projects"
    assert run_cli(
        [
            "init",
            "PRJ-009",
            "--projects-root",
            str(projects_root),
            "--created-at",
            "2026-08-25T00:00:00Z",
        ]
    ) == 0
    project_path = projects_root / "PRJ-009"
    excluded = {
        "00_PROJECT/production_config.json",
        "00_PROJECT/compatibility_report.json",
        "00_PROJECT/project_state.json",
        "00_PROJECT/change_log.jsonl",
    }
    preserved_before = {
        path.relative_to(project_path).as_posix(): path.read_bytes()
        for path in project_path.rglob("*")
            if path.is_file()
            and ".runtime" not in path.relative_to(project_path).parts
            and path.relative_to(project_path).as_posix() not in excluded
    }

    result = run_cli(
        [
            "migrate-channel-pin",
            str(project_path),
            "--channel-content-version",
            "1.1.0",
        ]
    )
    config = load_json_object(
        project_path / "00_PROJECT" / "production_config.json"
    )
    report = load_json_object(
        project_path / "00_PROJECT" / "compatibility_report.json"
    )
    state = load_json_object(project_path / "00_PROJECT" / "project_state.json")
    preserved_after = {
        path.relative_to(project_path).as_posix(): path.read_bytes()
        for path in project_path.rglob("*")
            if path.is_file()
            and ".runtime" not in path.relative_to(project_path).parts
            and path.relative_to(project_path).as_posix() not in excluded
    }

    assert result == 0
    assert config["channel_content_version"] == "1.1.0"
    assert report["compatibility"] == "PASS"
    channel_summary = report["channel"]
    assert isinstance(channel_summary, dict)
    assert channel_summary["relative_path"] == "versions/1.1.0/channel_dna.json"
    assert state["state"] == "BLOCKED"
    assert state["current_gate"] == "NONE"
    readiness = state["readiness"]
    assert isinstance(readiness, dict)
    assert readiness["process_revision"] == 2
    assert readiness["process_start_gate"] == "GATE-00"
    assert preserved_after == preserved_before
    canonical_paths = [
        project_path / "00_PROJECT" / name
        for name in (
            "production_config.json",
            "compatibility_report.json",
            "project_state.json",
            "change_log.jsonl",
        )
    ]
    first_migration = {path: path.read_bytes() for path in canonical_paths}
    assert run_cli(
        [
            "migrate-channel-pin",
            str(project_path),
            "--channel-content-version",
            "1.1.0",
        ]
    ) == 0
    assert {path: path.read_bytes() for path in canonical_paths} == first_migration


@pytest.mark.parametrize("failure_stage", [1, 2, 3, 4])
def test_migrate_channel_pin_rolls_back_each_write_stage(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    failure_stage: int,
) -> None:
    """Migration의 네 Canonical 교체 단계 중 어디서 실패해도 전부 복구한다."""
    projects_root = tmp_path / f"projects-{failure_stage}"
    assert run_cli(
        [
            "init",
            f"PRJ-91{failure_stage}",
            "--projects-root",
            str(projects_root),
            "--created-at",
            "2026-08-25T00:00:00Z",
        ]
    ) == 0
    project_path = projects_root / f"PRJ-91{failure_stage}"
    canonical_paths = [
        project_path / "00_PROJECT" / name
        for name in (
            "production_config.json",
            "compatibility_report.json",
            "project_state.json",
            "change_log.jsonl",
        )
    ]
    before = {path: path.read_bytes() for path in canonical_paths}
    original_replace = os.replace
    calls = 0

    def fail_once(
        source: str | bytes | os.PathLike[str] | os.PathLike[bytes],
        destination: str | bytes | os.PathLike[str] | os.PathLike[bytes],
    ) -> None:
        """지정된 Canonical 교체 단계에서 한 번만 실패한다."""
        nonlocal calls
        calls += 1
        if calls == failure_stage:
            raise OSError("injected migration write failure")
        original_replace(source, destination)

    monkeypatch.setattr("RUNTIME.transactions.os.replace", fail_once)
    assert run_cli(
        [
            "migrate-channel-pin",
            str(project_path),
            "--channel-content-version",
            "1.1.0",
        ]
    ) == 2
    assert {path: path.read_bytes() for path in canonical_paths} == before


def test_migrate_channel_pin_rejects_unregistered_version(tmp_path: Path) -> None:
    """등록되지 않은 Channel Pin Migration은 아무 파일도 바꾸지 않는다."""
    projects_root = tmp_path / "projects"
    assert run_cli(
        [
            "init",
            "PRJ-010",
            "--projects-root",
            str(projects_root),
            "--created-at",
            "2026-08-25T00:00:00Z",
        ]
    ) == 0
    project_path = projects_root / "PRJ-010"
    before = {
        path.relative_to(project_path).as_posix(): path.read_bytes()
        for path in project_path.rglob("*")
        if path.is_file()
    }

    result = run_cli(
        [
            "migrate-channel-pin",
            str(project_path),
            "--channel-content-version",
            "9.9.9",
        ]
    )
    after = {
        path.relative_to(project_path).as_posix(): path.read_bytes()
        for path in project_path.rglob("*")
        if path.is_file()
    }

    assert result == 2
    assert after == before


def test_variations_require_project_compatibility_gate(tmp_path: Path) -> None:
    """Compatibility를 실행하지 않은 Project는 Variation을 생성할 수 없어야 한다."""
    projects_root = tmp_path / "projects"
    assert run_cli(
        [
            "init",
            "PRJ-005",
            "--projects-root",
            str(projects_root),
            "--created-at",
            "2026-08-25T00:00:00Z",
        ]
    ) == 0
    project_path = projects_root / "PRJ-005"

    result = run_cli(
        [
            "variations",
            str(project_path),
            "--seed",
            "호환성 없는 후보 생성",
            "--count",
            "5",
        ]
    )

    assert result == 2
    candidates = load_json_object(
        project_path / "00_PROJECT" / "variation_candidates.json"
    )
    assert candidates["candidate_count"] == 0


def test_failed_project_compatibility_blocks_variations(tmp_path: Path) -> None:
    """필수 Capability가 없는 Channel은 GATE-00과 Variation을 차단해야 한다."""
    projects_root = tmp_path / "projects"
    assert run_cli(
        [
            "init",
            "PRJ-006",
            "--projects-root",
            str(projects_root),
            "--created-at",
            "2026-08-25T00:00:00Z",
        ]
    ) == 0
    project_path = projects_root / "PRJ-006"
    channel = load_json_object(ROOT / "CHANNELS" / "mystery_main" / "channel_dna.json")
    capabilities = channel.get("capabilities")
    assert isinstance(capabilities, dict)
    del capabilities["GENRE_POLICY"]
    channel_path = tmp_path / "incompatible_channel.json"
    write_json_object(channel_path, channel)

    compat_code = run_cli(
        ["compat", str(project_path), "--channel", str(channel_path)]
    )
    variation_code = run_cli(
        [
            "variations",
            str(project_path),
            "--seed",
            "호환되지 않는 채널",
            "--count",
            "5",
        ]
    )
    state = load_json_object(project_path / "00_PROJECT" / "project_state.json")

    assert compat_code == 2
    assert variation_code == 2
    assert state["state"] == "INITIALIZED"
    assert state["current_gate"] == "NONE"


def test_user_case_locked_values_flow_into_cli_variations(tmp_path: Path) -> None:
    """CLI Variation은 Production Config의 USER_CASE LOCKED 값을 보존해야 한다."""
    projects_root = tmp_path / "projects"
    assert run_cli(
        [
            "init",
            "PRJ-007",
            "--projects-root",
            str(projects_root),
            "--created-at",
            "2026-08-25T00:00:00Z",
        ]
    ) == 0
    project_path = projects_root / "PRJ-007"
    manifest_path = project_path / "00_PROJECT" / "project_manifest.json"
    config_path = project_path / "00_PROJECT" / "production_config.json"
    story_path = project_path / "00_PROJECT" / "story_dna.json"
    manifest = load_json_object(manifest_path)
    production_config = load_json_object(config_path)
    story_document = load_json_object(story_path)
    manifest["story_source_mode"] = "USER_CASE"
    production_config["story_source_mode"] = "USER_CASE"
    production_config["channel_content_version"] = "2.0.0"
    production_config["variation_engine_version"] = "2.0.0"
    production_config["variation_catalog_version"] = "2.0.0"
    production_config["genre"] = "CRIME_PSYCHOLOGICAL_THRILLER"
    production_config["user_case_constraints"] = [
        {"field": "protagonist_role", "value": "REPORTER", "status": "LOCKED"},
        {"field": "incident_type", "value": "DISAPPEARANCE", "status": "LOCKED"},
        {"field": "setting", "value": "FACTORY", "status": "FLEXIBLE"},
        {"field": "primary_twist", "value": None, "status": "UNKNOWN"},
    ]
    story_document["story_source_mode"] = "USER_CASE"
    write_json_object(manifest_path, manifest)
    write_json_object(config_path, production_config)
    write_json_object(story_path, story_document)

    assert run_cli(["compat", str(project_path)]) == 0
    assert run_cli(
        [
            "variations",
            str(project_path),
            "--seed",
            "사용자가 정한 실종 사건",
            "--count",
            "5",
        ]
    ) == 0
    candidates = load_json_object(
        project_path / "00_PROJECT" / "variation_candidates.json"
    )
    records = candidates.get("candidates")
    assert isinstance(records, list)

    assert all(
        isinstance(record, dict)
        and isinstance(record.get("selection"), dict)
        and record["selection"]["protagonist_role"] == "REPORTER"
        and record["selection"]["incident_type"] == "DISAPPEARANCE"
        for record in records
    )
