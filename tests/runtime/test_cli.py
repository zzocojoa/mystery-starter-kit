"""Runtime CLI Doctor, Plan, Run, Status 명령 검증."""

import json
from pathlib import Path

import pytest

from RUNTIME.cli import run_cli

from .support import create_runtime_project, create_runtime_repository


def test_cli_doctor_plan_run_and_status(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """운영자가 CLI만으로 진단·계획·실행·상태 조회를 수행할 수 있다."""
    repository_root = create_runtime_repository(tmp_path)
    project_path = create_runtime_project(repository_root, "PRJ-950")
    common = ["--repository-root", str(repository_root)]

    assert run_cli([*common, "doctor"]) == 0
    assert run_cli([*common, "plan", str(project_path), "--to", "GATE-02"]) == 0
    assert run_cli([*common, "run", str(project_path), "--to", "GATE-02"]) == 0
    assert run_cli([*common, "status", str(project_path)]) == 0

    captured = capsys.readouterr()
    documents = []
    decoder = json.JSONDecoder()
    remaining = captured.out.lstrip()
    while remaining:
        document, end = decoder.raw_decode(remaining)
        documents.append(document)
        remaining = remaining[end:].lstrip()

    assert documents[0]["status"] == "PASS"
    assert documents[1]["from_gate"] == "GATE-00"
    assert documents[2]["status"] == "COMPLETED"
    assert documents[3]["project_state"]["current_gate"] == "GATE-02"
