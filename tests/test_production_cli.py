"""통합 CLI의 실제 디렉터리 E2E 검증."""

from pathlib import Path

from project_factory import make_complete_project_artifacts

from VALIDATORS.io import load_json_object, write_json_object
from VALIDATORS.pipeline import ArtifactContent
from VALIDATORS.production_cli import ROOT, run_cli
from VALIDATORS.schema_validation import collect_schema_errors


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


def test_readme_golden_path_reaches_production_ready(tmp_path: Path) -> None:
    """README 명령 순서 전체가 실제 디스크에서 Production Ready에 도달해야 한다."""
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
    approve_code = run_cli(["approve", str(project_path), "VAR-01"])
    precheck_code = run_cli(["precheck", str(project_path)])
    artifacts = make_complete_project_artifacts()
    for generated_artifact in (
        "compatibility_report",
        "variation_candidates",
        "novelty_precheck",
    ):
        del artifacts[generated_artifact]
    write_complete_artifacts(project_path, artifacts)

    validate_code = run_cli(["validate", str(project_path)])
    state = load_json_object(project_path / "00_PROJECT" / "project_state.json")
    report = load_json_object(project_path / "08_QA" / "validation_report.json")
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
    assert register_code == 0
    assert report["result"] == "PASS"
    assert state["state"] == "PRODUCTION_READY"
    assert state["current_gate"] == "GATE-13"
    fingerprints = library["fingerprints"]
    assert isinstance(fingerprints, list)
    assert len(fingerprints) == 1
    assert history_path.read_text(encoding="utf-8").strip()


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


def test_failed_validation_marks_problem_artifact_invalid(tmp_path: Path) -> None:
    """Gate 실패 원인이 된 Artifact는 Project State에서 INVALID로 표시되어야 한다."""
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
    presentation["reaction_ratio"] = 0.9
    write_complete_artifacts(project_path, artifacts)

    result = run_cli(["validate", str(project_path)])
    state = load_json_object(project_path / "00_PROJECT" / "project_state.json")
    states = state["artifacts"]
    assert isinstance(states, dict)

    assert result == 1
    assert state["state"] == "BLOCKED"
    assert state["current_gate"] == "GATE-11"
    assert states["presentation_plan"]["status"] == "INVALID"
    assert states["edit_script"]["status"] == "DIRTY"


def test_variation_approval_and_precheck_commands_form_gate_one(tmp_path: Path) -> None:
    """후보 생성·승인·History Precheck 명령이 GATE-01 Artifact를 완성해야 한다."""
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
    assert run_cli(["approve", str(project_path), "VAR-01"]) == 0
    assert run_cli(["precheck", str(project_path)]) == 0
    report = load_json_object(project_path / "08_QA" / "novelty_precheck.json")

    assert report["result"] == "PASS"
    assert report["approved_candidate_id"] == "VAR-01"
    assert compatibility["project_id"] == "PRJ-004"
    assert compatibility["compatibility"] == "PASS"
    assert state["current_gate"] == "GATE-00"


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
    report = load_json_object(
        project_path / "00_PROJECT" / "compatibility_report.json"
    )
    state = load_json_object(project_path / "00_PROJECT" / "project_state.json")

    assert compat_code == 1
    assert variation_code == 2
    assert report["project_id"] == "PRJ-006"
    assert report["compatibility"] == "FAIL"
    assert state["state"] == "BLOCKED"
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
