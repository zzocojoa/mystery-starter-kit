"""설치 위치와 무관한 Repository Resource 전달 계약을 검증한다."""

import json
import os
import subprocess
import sys
import venv
from copy import deepcopy
from hashlib import sha256
from pathlib import Path
from shutil import copy2, copytree
from zipfile import ZipFile

import pytest
from runtime.support import create_runtime_repository

from VALIDATORS import pipeline
from VALIDATORS.dependency import dependency_artifacts
from VALIDATORS.exceptions import ConfigurationError
from VALIDATORS.io import load_json_object
from VALIDATORS.repository_resources import (
    REPOSITORY_SENTINELS,
    resolve_repository_resource_root,
)

ROOT = Path(__file__).resolve().parents[1]
RESOURCE_AUDIT_SCRIPT = '''
import json
import runpy
import sys
from pathlib import Path

def resource_open(event: str, args: tuple[object, ...]) -> None:
    if event != "open" or not isinstance(args[0], str):
        return
    path = Path(args[0]).resolve()
    if set(path.parts) & {"STANDARD", "CHANNELS", "AGENTS", "STORY_LIBRARY"}:
        print("RESOURCE_READ=" + json.dumps(str(path)), file=sys.stderr)

sys.addaudithook(resource_open)
sys.argv = sys.argv[1:]
runpy.run_path(sys.argv[0], run_name="__main__")
'''


def test_artifact_validators_use_only_supplied_graph(monkeypatch: pytest.MonkeyPatch) -> None:
    """두 순수 Validator는 전달받은 Graph 외의 파일을 읽지 않는다."""
    graph = load_json_object(ROOT / "STANDARD/dependency_graph.json")

    def forbidden_read(path: Path) -> dict[str, object]:
        """Validator 내부의 암묵적 파일 접근은 즉시 실패시킨다."""
        raise AssertionError(f"암묵적인 Resource 읽기: {path}")

    monkeypatch.setattr(pipeline, "load_json_object", forbidden_read)
    assert pipeline.required_channel_artifact_issues({}, {}, {}, [], graph) == []
    config: dict[str, object] = {"channel_content_version": "1.1.0"}
    artifacts: dict[str, pipeline.ArtifactContent] = {
        "shooting_script": "",
        "narration": "",
        "production_panel_reaction_script": "",
        "subtitle_script": "",
        "edit_script": "",
    }
    issues = pipeline.production_text_issues(artifacts, config, {}, graph)
    assert len(issues) == 5
    assert {issue["code"] for issue in issues} == {"PRODUCTION_ARTIFACT_EMPTY"}
    definitions = dependency_artifacts(graph)
    custom_definitions = {
        **definitions,
        "production_expert_analysis_script": {
            **definitions["production_expert_analysis_script"],
            "required_when": {"always": True},
        },
    }
    custom_graph = {**graph, "artifacts": custom_definitions}
    before = deepcopy(custom_graph)
    with pytest.raises(ConfigurationError, match="production_expert_analysis_script"):
        pipeline.production_text_issues(artifacts, config, {}, custom_graph)
    assert len(pipeline.required_channel_artifact_issues(
        {}, config, {}, ["production_expert_analysis_script"], custom_graph
    )) == 1
    assert custom_graph == before


def complete_resource_repository(tmp_path: Path) -> Path:
    """보호 파일은 바꾸지 않고 임시 Repository의 모든 Sentinel을 복제한다."""
    repository = create_runtime_repository(tmp_path)
    copy2(ROOT / "pyproject.toml", repository / "pyproject.toml")
    return repository


@pytest.mark.parametrize("sentinel", REPOSITORY_SENTINELS)
def test_explicit_root_requires_every_sentinel(tmp_path: Path, sentinel: str) -> None:
    """명시 Root가 불완전하면 정상 실행 위치로 대체하지 않는다."""
    partial = tmp_path / "partial"
    for name in REPOSITORY_SENTINELS:
        if name != sentinel:
            target = partial / name
            target.parent.mkdir(parents=True, exist_ok=True)
            copy2(ROOT / name, target)
    with pytest.raises(ConfigurationError) as captured:
        resolve_repository_resource_root(partial, ROOT / "PROJECTS/PRJ-006", ROOT)
    error = json.loads(str(captured.value))
    assert error["code"] == "REPOSITORY_RESOURCE_ROOT_NOT_FOUND"
    assert error["context"]["checked_roots"] == [
        {"root": str(partial), "missing_sentinels": [sentinel]}
    ]


def test_root_precedence_and_ancestor_discovery(tmp_path: Path) -> None:
    """명시 Root, Project 조상, 실행 위치 조상 우선순위를 고정한다."""
    other = complete_resource_repository(tmp_path)
    project = other / "PROJECTS/PRJ-006"
    assert resolve_repository_resource_root(ROOT, project, other) == ROOT
    assert resolve_repository_resource_root(None, project, ROOT) == other
    assert resolve_repository_resource_root(None, tmp_path / "standalone", ROOT / "tests") == ROOT
    assert resolve_repository_resource_root(Path(".."), tmp_path, ROOT / "tests") == ROOT


def isolated_environment() -> dict[str, str]:
    """Source Tree가 설치형 CLI Import를 가리지 못하게 환경을 격리한다."""
    return {
        **{key: value for key, value in os.environ.items()
           if key not in {"PYTHONPATH", "PYTHONHOME"}},
        "PYTHONNOUSERSITE": "1",
        "PIP_DISABLE_PIP_VERSION_CHECK": "1",
    }


def run_console(command: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
    """실제 Console Process의 종료 상태와 출력을 숨기지 않고 수집한다."""
    return subprocess.run(
        command, cwd=cwd, env=isolated_environment(), text=True, capture_output=True,
        check=False, timeout=180,
    )


def require_success(result: subprocess.CompletedProcess[str]) -> None:
    """명령 실패 시 원래 종료 코드와 전체 출력을 증거로 남긴다."""
    assert result.returncode == 0, (result.args, result.returncode, result.stdout, result.stderr)


def assert_audit_pass(result: subprocess.CompletedProcess[str]) -> None:
    """진단 결과 PASS와 Human Editorial 미완료 경계를 함께 확인한다."""
    require_success(result)
    report = json.loads(result.stdout)
    assert report["result"] == "PASS"


@pytest.fixture(scope="session")
def installed_wheel(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """현재 Source의 non-editable wheel을 독립 venv에 실제로 설치한다."""
    directory = tmp_path_factory.mktemp("installed-wheel")
    wheel_directory = directory / "dist"
    require_success(run_console(
        [sys.executable, "-m", "build", "--wheel", "--outdir", str(wheel_directory)], ROOT
    ))
    wheels = list(wheel_directory.glob("*.whl"))
    assert len(wheels) == 1
    with ZipFile(wheels[0]) as archive:
        assert not any(
            name.startswith(("STANDARD/", "CHANNELS/", "AGENTS/", "STORY_LIBRARY/"))
            for name in archive.namelist()
        )
    environment = directory / "venv"
    venv.EnvBuilder(with_pip=True).create(environment)
    require_success(run_console(
        [str(environment / "bin/python"), "-m", "pip", "install", str(wheels[0])], directory
    ))
    imported = run_console(
        [str(environment / "bin/python"), "-I", "-c",
         "import VALIDATORS.pipeline; print(VALIDATORS.pipeline.__file__)"], directory
    )
    require_success(imported)
    imported_path = Path(imported.stdout.strip())
    assert imported_path.is_relative_to(environment)
    assert "site-packages" in imported_path.parts
    assert not imported_path.is_relative_to(ROOT)
    return environment


@pytest.fixture(scope="session")
def editable_install(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """Editable 설치도 별도 venv의 실제 Console Script로 검증한다."""
    directory = tmp_path_factory.mktemp("editable-install")
    environment = directory / "venv"
    venv.EnvBuilder(with_pip=True).create(environment)
    require_success(run_console(
        [str(environment / "bin/python"), "-m", "pip", "install", "-e", str(ROOT)], directory
    ))
    imported = run_console(
        [str(environment / "bin/python"), "-I", "-c",
         "import VALIDATORS.pipeline; print(VALIDATORS.pipeline.__file__)"], directory
    )
    require_success(imported)
    assert Path(imported.stdout.strip()) == ROOT / "VALIDATORS/pipeline.py"
    return environment


@pytest.fixture
def pilot_copy(tmp_path: Path) -> Path:
    """Canonical PRJ-006은 읽기만 하고 모든 진단 출력을 외부 복사본에 한정한다."""
    return Path(copytree(ROOT / "PROJECTS/PRJ-006", tmp_path / "PRJ-006"))


@pytest.mark.parametrize("command", ["validate", "audit"])
def test_source_checkout_cli(command: str, pilot_copy: Path) -> None:
    """Source Module 실행은 외부 Pilot 복사본을 정상 진단한다."""
    assert_audit_pass(run_console(
        [sys.executable, "-m", "VALIDATORS.production_cli", command, str(pilot_copy)], ROOT
    ))


@pytest.mark.parametrize("command", ["validate", "audit"])
def test_editable_console(command: str, editable_install: Path, pilot_copy: Path) -> None:
    """Editable Console Script로도 외부 Pilot 복사본을 정상 진단한다."""
    assert_audit_pass(run_console(
        [str(editable_install / "bin/mystery-kit"), command, str(pilot_copy)], ROOT
    ))


@pytest.mark.parametrize("command", ["validate", "audit"])
@pytest.mark.parametrize("context", ["repository_cwd", "explicit_root"])
def test_wheel_console_positive(
    command: str, context: str, installed_wheel: Path, pilot_copy: Path, tmp_path: Path
) -> None:
    """설치 wheel의 Console Script가 두 정상 Root 문맥에서 통과한다."""
    before = {path.relative_to(pilot_copy): path.read_bytes()
              for path in pilot_copy.rglob("*") if path.is_file()}
    args = [str(installed_wheel / "bin/mystery-kit"), command, str(pilot_copy)]
    cwd = ROOT if context == "repository_cwd" else tmp_path
    if context == "explicit_root":
        args.extend(["--repository-root", str(ROOT)])
    assert_audit_pass(run_console(args, cwd))
    after = {path.relative_to(pilot_copy): path.read_bytes()
             for path in pilot_copy.rglob("*") if path.is_file()}
    permitted = Path("08_QA/audit_report.json")
    assert {key: value for key, value in before.items() if key != permitted} == {
        key: value for key, value in after.items() if key != permitted
    }
    state = load_json_object(pilot_copy / "00_PROJECT/project_state.json")
    assert state["state"] == "EDITORIAL_REVIEW_REQUIRED"


@pytest.mark.parametrize("command", ["validate", "audit"])
@pytest.mark.parametrize("context", ["missing_root", "invalid_explicit_root"])
def test_wheel_console_rejects_missing_resources(
    command: str, context: str, installed_wheel: Path, pilot_copy: Path, tmp_path: Path
) -> None:
    """누락 Resource는 다른 Root로 숨기지 않고 구조화 오류와 Exit 2로 거부한다."""
    args = [str(installed_wheel / "bin/mystery-kit"), command, str(pilot_copy)]
    cwd = tmp_path
    if context == "invalid_explicit_root":
        args.extend(["--repository-root", str(tmp_path)])
        cwd = ROOT
    result = run_console(args, cwd)
    assert result.returncode == 2, (result.stdout, result.stderr)
    assert result.stderr.startswith("ERROR: ")
    error = json.loads(result.stderr.removeprefix("ERROR: "))
    assert error["code"] == "REPOSITORY_RESOURCE_ROOT_NOT_FOUND"
    assert error["context"]["checked_roots"]
    assert "missing_sentinels" in result.stderr
    assert "Traceback" not in result.stderr
    assert "FileNotFoundError" not in result.stderr


@pytest.mark.parametrize("command", ["validate", "audit"])
def test_wheel_uses_one_graph_from_explicit_root(
    command: str, installed_wheel: Path, tmp_path: Path
) -> None:
    """충돌하는 Project 조상과 CWD가 있어도 단일 명시 Root의 계약만 읽는다."""
    other = complete_resource_repository(tmp_path)
    project = Path(copytree(ROOT / "PROJECTS/PRJ-006", other / "PROJECTS/PRJ-006"))
    result = run_console(
        [str(installed_wheel / "bin/python"), "-I", "-c", RESOURCE_AUDIT_SCRIPT,
         str(installed_wheel / "bin/mystery-kit"), command, str(project),
         "--repository-root", str(ROOT)], other
    )
    assert_audit_pass(result)
    reads = [Path(json.loads(line.removeprefix("RESOURCE_READ=")))
             for line in result.stderr.splitlines() if line.startswith("RESOURCE_READ=")]
    assert reads
    assert all(path.is_relative_to(ROOT) for path in reads), reads
    graph_reads = [path for path in reads if path.name == "dependency_graph.json"]
    assert graph_reads == [ROOT / "STANDARD/dependency_graph.json"]
    source_hashes = {sha256(path.read_bytes()).hexdigest() for path in graph_reads}
    expected_hash = sha256((ROOT / "STANDARD/dependency_graph.json").read_bytes()).hexdigest()
    assert source_hashes == {expected_hash}
    assert not any("site-packages" in path.parts for path in reads)


def test_wheel_installed_doctor(installed_wheel: Path, tmp_path: Path) -> None:
    """새 venv의 Doctor가 명시 Repository Root의 Runtime 계약을 진단한다."""
    result = run_console(
        [str(installed_wheel / "bin/mystery-runtime"), "--repository-root", str(ROOT), "doctor"],
        tmp_path,
    )
    require_success(result)
    assert json.loads(result.stdout)["status"] == "PASS"
