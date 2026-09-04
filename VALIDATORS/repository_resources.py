"""설치 위치와 독립적으로 진단용 Repository Resource Root를 결정한다."""

import json
from pathlib import Path

from VALIDATORS.exceptions import ConfigurationError

REPOSITORY_SENTINELS: tuple[str, ...] = (
    "pyproject.toml",
    "STANDARD/dependency_graph.json",
    "CHANNELS/mystery_main/channel_manifest.json",
    "RUNTIME/contracts/runtime_tasks.json",
    "AGENTS/manifest.json",
    "STORY_LIBRARY/novelty_index.json",
)


def missing_repository_sentinels(repository_root: Path) -> list[str]:
    """완전한 Repository Root 판정에 필요한 누락 파일을 반환한다."""
    return [name for name in REPOSITORY_SENTINELS if not (repository_root / name).is_file()]


def resolve_repository_resource_root(
    explicit_root: Path | None,
    project_path: Path,
    working_directory: Path,
) -> Path:
    """명시 Root, Project 조상, 실행 위치 조상 순으로 완전한 Root 하나를 선택한다."""
    working_root = working_directory.resolve()
    project_root = (working_root / project_path).resolve()
    candidates = (
        [(working_root / explicit_root).resolve()]
        if explicit_root is not None
        else list(
            dict.fromkeys(
                (project_root, *project_root.parents, working_root, *working_root.parents)
            )
        )
    )
    checked_roots: list[dict[str, object]] = []
    for candidate in candidates:
        missing = missing_repository_sentinels(candidate)
        if not missing:
            return candidate
        checked_roots.append({"root": str(candidate), "missing_sentinels": missing})
    raise ConfigurationError(
        json.dumps(
            {
                "code": "REPOSITORY_RESOURCE_ROOT_NOT_FOUND",
                "message": "완전한 Repository Root를 --repository-root로 지정하세요.",
                "context": {
                    "explicit_root": str(explicit_root) if explicit_root is not None else None,
                    "project_path": str(project_root),
                    "working_directory": str(working_root),
                    "checked_roots": checked_roots,
                },
            },
            ensure_ascii=False,
        )
    )
