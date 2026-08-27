"""Presentation Contract v1의 명시적 State Migration 검증."""

from pathlib import Path
from typing import cast

from VALIDATORS.io import load_json_object, write_json_object
from VALIDATORS.models import ProjectState
from VALIDATORS.presentation_migration import (
    mark_presentation_migration_required,
    presentation_migration_required,
)
from VALIDATORS.scaffold import create_project_scaffold

ROOT = Path(__file__).resolve().parents[1]


def test_explicit_presentation_migration_preserves_existing_script(tmp_path: Path) -> None:
    """명시적 Migration은 기존 Script를 보존하고 재생성 상태만 표시한다."""
    graph = load_json_object(ROOT / "STANDARD" / "dependency_graph.json")
    project_path = create_project_scaffold(
        ROOT / "TEMPLATES" / "PROJECT",
        tmp_path,
        graph,
        "PRJ-970",
        "2026-08-28T00:00:00Z",
    )
    legacy_script = "# 기존 최종 대본\n\nSCN-08 정정된 사건"
    script_path = project_path / "07_SCRIPT" / "final_script.md"
    script_path.write_text(legacy_script, encoding="utf-8")
    write_json_object(
        project_path / "06_SCENE" / "presentation_plan.json",
        {
            "project_id": "PRJ-970",
            "modes": ["DRAMA", "NARRATION", "REACTION"],
            "reaction_ratio": 0.2,
            "scene_presentations": [{"scene_id": "SCN-08", "mode": "DRAMA"}],
        },
    )
    (project_path / "06_SCENE" / "panel_cast.json").unlink()
    state = load_json_object(project_path / "00_PROJECT" / "project_state.json")

    migrated = mark_presentation_migration_required(
        project_path,
        graph,
        cast(ProjectState, state),
        "2026-08-28T00:01:00Z",
    )

    assert presentation_migration_required(project_path) is True
    assert migrated["state"] == "PRESENTATION_MIGRATION_REQUIRED"
    assert migrated["current_gate"] == "NONE"
    assert migrated["artifacts"]["panel_cast"]["status"] == "MISSING"
    assert migrated["artifacts"]["presentation_plan"]["status"] == "INVALID"
    assert migrated["artifacts"]["final_script"]["status"] == "INVALID"
    assert script_path.read_text(encoding="utf-8") == legacy_script
