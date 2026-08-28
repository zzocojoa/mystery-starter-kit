"""Novelty Index와 Published Library의 파일 저장 경계."""

from pathlib import Path

from VALIDATORS.io import load_json_object, write_json_object
from VALIDATORS.library import mark_novelty_production_ready, update_novelty_for_gate


def novelty_index_path(repository_root: Path) -> Path:
    """Repository Novelty Index의 절대 경로를 반환한다."""
    return repository_root / "STORY_LIBRARY" / "novelty_index.json"


def sync_novelty_gate(
    repository_root: Path,
    project_path: Path,
    gate_id: str,
    updated_at: str,
) -> None:
    """Gate Commit 후 Novelty Lifecycle을 Repository Index에 기록한다."""
    if gate_id not in {"GATE-02", "GATE-10", "GATE-13"}:
        return
    path = novelty_index_path(repository_root)
    story_document = load_json_object(project_path / "00_PROJECT" / "story_dna.json")
    fingerprint = (
        load_json_object(project_path / "00_PROJECT" / "story_fingerprint.json")
        if gate_id in {"GATE-10", "GATE-13"}
        else None
    )
    next_index = update_novelty_for_gate(
        load_json_object(path),
        gate_id,
        story_document,
        fingerprint,
        updated_at,
    )
    write_json_object(path, next_index)


def sync_novelty_production_ready(
    repository_root: Path,
    project_path: Path,
    updated_at: str,
) -> None:
    """Production Finalize 후 Novelty Lifecycle을 PRODUCTION_READY로 확정한다."""
    path = novelty_index_path(repository_root)
    fingerprint = load_json_object(
        project_path / "00_PROJECT" / "story_fingerprint.json"
    )
    next_index = mark_novelty_production_ready(
        load_json_object(path),
        fingerprint,
        updated_at,
    )
    write_json_object(path, next_index)


def sync_novelty_revision(
    repository_root: Path,
    project_path: Path,
    updated_at: str,
) -> None:
    """Story 재작업을 시작한 Project를 DRAFT Novelty 상태로 되돌린다."""
    path = novelty_index_path(repository_root)
    next_index = update_novelty_for_gate(
        load_json_object(path),
        "GATE-10",
        load_json_object(project_path / "00_PROJECT" / "story_dna.json"),
        load_json_object(project_path / "00_PROJECT" / "story_fingerprint.json"),
        updated_at,
    )
    write_json_object(path, next_index)
