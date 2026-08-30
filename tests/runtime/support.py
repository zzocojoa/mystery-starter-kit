"""Runtime 테스트용 격리 Repository와 Project 생성 도우미."""

import shutil
from pathlib import Path

from VALIDATORS.io import load_json_object
from VALIDATORS.scaffold import create_project_scaffold

ROOT = Path(__file__).resolve().parents[2]


def create_runtime_repository(tmp_path: Path) -> Path:
    """운영 계약은 복제하고 PROJECTS만 격리한 Repository를 만든다."""
    repository_root = tmp_path / "repository"
    repository_root.mkdir()
    for directory_name in ("AGENTS", "CHANNELS", "RUNTIME", "STANDARD", "STORY_LIBRARY"):
        shutil.copytree(
            ROOT / directory_name,
            repository_root / directory_name,
            ignore=shutil.ignore_patterns("__pycache__"),
        )
    shutil.copytree(
        ROOT / "VALIDATORS" / "variation_engines",
        repository_root / "VALIDATORS" / "variation_engines",
        ignore=shutil.ignore_patterns("__pycache__"),
    )
    (repository_root / "PROJECTS").mkdir()
    return repository_root


def create_runtime_project(repository_root: Path, project_id: str) -> Path:
    """격리 Repository에 표준 Project Scaffold를 생성한다."""
    dependency_graph = load_json_object(ROOT / "STANDARD" / "dependency_graph.json")
    return create_project_scaffold(
        ROOT / "TEMPLATES" / "PROJECT",
        repository_root / "PROJECTS",
        dependency_graph,
        project_id,
        "2026-08-27T00:00:00Z",
    )
