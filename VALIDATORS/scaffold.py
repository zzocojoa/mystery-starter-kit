"""표준 Project Scaffold 생성 경계."""

import re
import shutil
from collections.abc import Mapping
from copy import deepcopy
from pathlib import Path

from VALIDATORS.dependency import (
    artifact_hash,
    build_initial_project_state,
    dependency_artifacts,
)
from VALIDATORS.exceptions import (
    InputFileNotFoundError,
    InvalidProjectIdError,
    ProjectAlreadyExistsError,
    ProjectScaffoldError,
)
from VALIDATORS.io import write_json_object
from VALIDATORS.models import ProjectState

PROJECT_ID_PATTERN = re.compile(r"^PRJ-[0-9]{3,}$")


def replace_project_id(path: Path, project_id: str) -> None:
    """새로 복사된 텍스트 파일의 Project ID 자리표시자를 치환한다."""
    try:
        content = path.read_text(encoding="utf-8")
        path.write_text(content.replace("PRJ-000", project_id), encoding="utf-8")
    except UnicodeDecodeError as error:
        raise ProjectScaffoldError(
            f"Project Template은 UTF-8 텍스트여야 합니다: path={path}"
        ) from error
    except OSError as error:
        raise ProjectScaffoldError(
            f"Project Template 치환에 실패했습니다: path={path}, detail={error}"
        ) from error


def mark_existing_template_artifacts(
    project_path: Path,
    graph: Mapping[str, object],
    project_state: ProjectState,
) -> ProjectState:
    """Template에 존재하는 Artifact를 DIRTY로 표시한 새 상태를 반환한다."""
    next_state = deepcopy(project_state)
    artifacts = next_state["artifacts"]

    for artifact_name, definition in dependency_artifacts(graph).items():
        relative_path = definition.get("path")
        if not isinstance(relative_path, str):
            raise ProjectScaffoldError(
                f"Dependency Artifact path가 올바르지 않습니다: artifact={artifact_name}"
            )
        artifact_path = project_path / relative_path
        if not artifact_path.is_file():
            continue
        artifact_state = artifacts.get(artifact_name)
        if artifact_state is None:
            raise ProjectScaffoldError(
                f"Project State Artifact 형식이 올바르지 않습니다: artifact={artifact_name}"
            )
        artifact_state["status"] = "DIRTY"
        artifact_state["content_hash"] = artifact_hash(artifact_path.read_bytes())
    return next_state


def create_project_scaffold(
    template_root: Path,
    projects_root: Path,
    dependency_graph: Mapping[str, object],
    project_id: str,
    created_at: str,
) -> Path:
    """표준 Template을 복사해 추적 가능한 신규 프로젝트를 생성한다."""
    if PROJECT_ID_PATTERN.fullmatch(project_id) is None:
        raise InvalidProjectIdError(
            f"Project ID는 PRJ-### 형식이어야 합니다: project_id={project_id!r}"
        )
    if not template_root.is_dir():
        raise InputFileNotFoundError(
            f"Project Template 디렉터리를 찾을 수 없습니다: path={template_root}"
        )

    project_path = projects_root / project_id
    if project_path.exists():
        raise ProjectAlreadyExistsError(
            f"동일한 Project가 이미 존재합니다: path={project_path}"
        )

    try:
        shutil.copytree(template_root, project_path)
    except OSError as error:
        raise ProjectScaffoldError(
            f"Project Scaffold 복사에 실패했습니다: source={template_root}, "
            f"destination={project_path}, detail={error}"
        ) from error

    for template_file in sorted(path for path in project_path.rglob("*") if path.is_file()):
        replace_project_id(template_file, project_id)

    initial_state = build_initial_project_state(dependency_graph, project_id, created_at)
    dirty_state = mark_existing_template_artifacts(
        project_path,
        dependency_graph,
        initial_state,
    )
    write_json_object(project_path / "00_PROJECT" / "project_state.json", dirty_state)
    return project_path
