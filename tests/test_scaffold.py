"""표준 Project Scaffold 생성 검증."""

from pathlib import Path

import pytest

from VALIDATORS.dependency import dependency_artifacts
from VALIDATORS.exceptions import InvalidProjectIdError, ProjectAlreadyExistsError
from VALIDATORS.io import load_json_object
from VALIDATORS.scaffold import create_project_scaffold
from VALIDATORS.schema_validation import collect_schema_errors

ROOT = Path(__file__).resolve().parents[1]
TEMPLATE_ROOT = ROOT / "TEMPLATES" / "PROJECT"
GRAPH_PATH = ROOT / "STANDARD" / "dependency_graph.json"
STATE_SCHEMA_PATH = ROOT / "STANDARD" / "schemas" / "project_state.schema.json"


def test_every_dependency_artifact_has_a_template_file() -> None:
    """Dependency Graph의 모든 경로는 Project Template에 실제 파일로 존재해야 한다."""
    graph = load_json_object(GRAPH_PATH)

    missing = [
        artifact_name
        for artifact_name, definition in dependency_artifacts(graph).items()
        if isinstance((relative_path := definition.get("path")), str)
        and not (TEMPLATE_ROOT / relative_path).is_file()
    ]

    assert missing == []


def test_project_scaffold_creates_all_production_directories(tmp_path: Path) -> None:
    """신규 프로젝트는 00부터 09까지 전체 표준 구조를 가져야 한다."""
    graph = load_json_object(GRAPH_PATH)

    project_path = create_project_scaffold(
        TEMPLATE_ROOT,
        tmp_path,
        graph,
        "PRJ-101",
        "2026-08-25T00:00:00Z",
    )

    expected_directories = {
        "00_PROJECT",
        "01_CASE",
        "02_CHARACTER",
        "03_TIMELINE",
        "04_MYSTERY",
        "05_STORY",
        "06_SCENE",
        "07_SCRIPT",
        "08_QA",
        "09_PRODUCTION",
    }
    assert {path.name for path in project_path.iterdir() if path.is_dir()} == expected_directories
    assert "PRJ-101" in (project_path / "00_PROJECT" / "production_config.json").read_text(
        encoding="utf-8"
    )

    state_path = project_path / "00_PROJECT" / "project_state.json"
    state = load_json_object(state_path)
    state_schema = load_json_object(STATE_SCHEMA_PATH)
    assert collect_schema_errors(state, state_schema, str(state_path)) == []
    artifacts = state["artifacts"]
    assert isinstance(artifacts, dict)
    assert artifacts["story_dna"]["status"] == "DIRTY"


def test_project_scaffold_never_overwrites_existing_project(tmp_path: Path) -> None:
    """동일 ID Project가 존재하면 덮어쓰지 않고 명시적으로 실패해야 한다."""
    graph = load_json_object(GRAPH_PATH)
    create_project_scaffold(
        TEMPLATE_ROOT,
        tmp_path,
        graph,
        "PRJ-102",
        "2026-08-25T00:00:00Z",
    )

    with pytest.raises(ProjectAlreadyExistsError):
        create_project_scaffold(
            TEMPLATE_ROOT,
            tmp_path,
            graph,
            "PRJ-102",
            "2026-08-25T00:00:01Z",
        )


def test_project_scaffold_rejects_invalid_project_id(tmp_path: Path) -> None:
    """추적할 수 없는 Project ID는 생성 전에 거부해야 한다."""
    graph = load_json_object(GRAPH_PATH)

    with pytest.raises(InvalidProjectIdError):
        create_project_scaffold(
            TEMPLATE_ROOT,
            tmp_path,
            graph,
            "project-one",
            "2026-08-25T00:00:00Z",
        )
