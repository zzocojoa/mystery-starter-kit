"""README의 Codex 후보 선택 Golden Path 회귀 검증."""

from pathlib import Path

from RUNTIME.providers.fake import fake_candidate_evaluation
from VALIDATORS.io import load_json_object, write_json_object
from VALIDATORS.production_cli import run_cli

ROOT = Path(__file__).resolve().parents[1]


def test_readme_candidate_command_order_executes(tmp_path: Path) -> None:
    """문서화된 compat→variation→precheck→eligibility→evaluation→approve가 실행된다."""
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    commands = (
        "mystery-kit compat",
        "mystery-kit variations",
        "mystery-kit precheck",
        "mystery-kit candidate-eligibility",
        "candidate_evaluation.json",
        "mystery-kit approve",
    )
    command_section = readme.index("결정론적 제작 보조 명령")
    positions = [readme.index(command, command_section) for command in commands]
    assert positions == sorted(positions)

    projects_root = tmp_path / "projects"
    assert run_cli(
        [
            "init",
            "PRJ-990",
            "--projects-root",
            str(projects_root),
            "--created-at",
            "2026-08-25T00:00:00Z",
        ]
    ) == 0
    project_path = projects_root / "PRJ-990"
    assert run_cli(["compat", str(project_path)]) == 0
    assert run_cli(
        ["variations", str(project_path), "--seed", "README smoke", "--count", "5"]
    ) == 0
    assert run_cli(["precheck", str(project_path)]) == 0
    assert run_cli(["candidate-eligibility", str(project_path)]) == 0
    variations = load_json_object(project_path / "00_PROJECT/variation_candidates.json")
    novelty = load_json_object(project_path / "08_QA/novelty_precheck.json")
    eligibility = load_json_object(project_path / "08_QA/candidate_eligibility.json")
    evaluation = fake_candidate_evaluation(
        "PRJ-990", variations, novelty, eligibility
    )
    write_json_object(
        project_path / "00_PROJECT/candidate_evaluation.json",
        evaluation,
    )
    recommended = evaluation["recommended_candidate_id"]
    assert isinstance(recommended, str)
    assert run_cli(["approve", str(project_path), recommended]) == 0
    approval = load_json_object(project_path / "00_PROJECT/candidate_approval.json")
    assert approval["approval_type"] == "AUTO_POLICY"
