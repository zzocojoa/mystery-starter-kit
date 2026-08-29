"""Runtime Engine Golden Path, 실패 원자성, Retry, 승인·재개 검증."""

import asyncio
import json
from collections.abc import Awaitable, Callable
from hashlib import sha256
from pathlib import Path

import pytest

from RUNTIME.approvals import approval_is_current
from RUNTIME.cli import approval_document
from RUNTIME.engine import execute_run, resume_run
from RUNTIME.errors import RuntimeExecutionError
from RUNTIME.models import LLMRequest, LLMResponse, ProviderDescriptor, TokenUsage
from RUNTIME.providers.fake import agent_result_document
from RUNTIME.providers.in_process import InProcessProviderAdapter
from VALIDATORS.io import load_json_object, write_json_object

from .support import create_runtime_project, create_runtime_repository


async def close_nothing() -> None:
    """Test Adapter의 비어 있는 명시적 종료 Handler."""
    return None


def fake_adapter(
    handler: Callable[[LLMRequest], Awaitable[LLMResponse]],
) -> InProcessProviderAdapter:
    """Model Route의 fake ID를 사용하는 Test In-process Adapter를 만든다."""
    return InProcessProviderAdapter(
        ProviderDescriptor(
            interface_version="1.0.0",
            provider_id="fake",
            adapter_id="runtime-test",
            adapter_version="1.0.0",
            capabilities=("TEXT_GENERATION", "JSON_OBJECT", "JSON_SCHEMA_OUTPUT"),
            max_context_tokens=128000,
            max_output_tokens=32000,
        ),
        handler,
        close_nothing,
    )


def response_with_result(request: LLMRequest, result: dict[str, object]) -> LLMResponse:
    """동적 Request Identity를 보존한 Provider 완료 응답을 만든다."""
    return LLMResponse(
        request_id=request.request_id,
        provider_request_id=f"TEST-{request.request_id}",
        status="COMPLETED",
        finish_reason="STOP",
        text=None,
        structured_output=result,
        tool_calls=(),
        usage=TokenUsage(input_tokens=10, output_tokens=10, cached_tokens=0),
        model_resolved="runtime-test-v1",
        warnings=(),
    )


def latest_run(project_path: Path) -> dict[str, object]:
    """Test Project의 유일하거나 최신 Runtime Run 문서를 반환한다."""
    run_paths = sorted((project_path / ".runtime" / "runs").glob("*/run.json"))
    assert run_paths
    return load_json_object(run_paths[-1])


def test_fake_provider_runs_gate_zero_through_thirteen(tmp_path: Path) -> None:
    """외부 API 없이 새 Project가 전체 Gate와 감사 기록을 완성한다."""
    repository_root = create_runtime_repository(tmp_path)
    project_path = create_runtime_project(repository_root, "PRJ-940")

    run = asyncio.run(
        execute_run(
            repository_root,
            project_path,
            "GATE-00",
            "GATE-13",
            "default",
            None,
            None,
        )
    )

    state = load_json_object(project_path / "00_PROJECT" / "project_state.json")
    report = load_json_object(project_path / "08_QA" / "validation_report.json")
    novelty_index = load_json_object(
        repository_root / "STORY_LIBRARY" / "novelty_index.json"
    )
    gate_results = report.get("gate_results")
    assert isinstance(gate_results, dict)
    story_path = project_path / "00_PROJECT" / "story_dna.json"
    provenance = load_json_object(project_path / ".runtime" / "provenance" / "story_dna.json")
    events_path = project_path / ".runtime" / "runs" / run["run_id"] / "events.jsonl"
    events = [json.loads(line) for line in events_path.read_text(encoding="utf-8").splitlines()]

    assert run["status"] == "COMPLETED"
    assert state["state"] == "EDITORIAL_REVIEW_REQUIRED"
    assert state["current_gate"] == "GATE-13"
    assert state["readiness"] == {
        "artifact_status": "ARTIFACT_COMPLETE",
        "contract_status": "CONTRACT_VALIDATED",
        "process_status": "PROCESS_CONFORMANT",
        "editorial_status": "EDITORIAL_REVIEW_REQUIRED",
        "process_start_gate": "GATE-00",
        "process_revision": 1,
    }
    assert report["result"] == "PASS"
    assert set(gate_results.values()) == {"PASS"}
    assert provenance["content_hash"] == sha256(story_path.read_bytes()).hexdigest()
    assert provenance["prompt_hash"]
    assert provenance["schema_hash"]
    usage = provenance["usage"]
    assert isinstance(usage, dict)
    assert isinstance(usage["input_tokens"], int)
    assert isinstance(usage["output_tokens"], int)
    assert usage["input_tokens"] > 0
    assert usage["output_tokens"] > 0
    assert usage["cached_tokens"] == 0
    assert any(event["event_type"] == "RUN_COMPLETED" for event in events)
    assert len(list((project_path / ".runtime" / "transactions").glob("*/transaction.json"))) == 14
    trace_lines = (
        project_path / "00_PROJECT" / "process_trace.jsonl"
    ).read_text(encoding="utf-8").splitlines()
    assert len(trace_lines) == 23
    novelty_entries = novelty_index["entries"]
    assert isinstance(novelty_entries, list)
    runtime_entry = next(
        entry
        for entry in novelty_entries
        if isinstance(entry, dict) and entry.get("project_id") == "PRJ-940"
    )
    assert runtime_entry["status"] == "EDITORIAL_PENDING"
    assert isinstance(runtime_entry["fingerprint"], dict)


def test_unauthorized_provider_output_never_changes_canonical_artifact(tmp_path: Path) -> None:
    """Task writes 밖의 출력은 Gateway에서 거부하고 Canonical 파일을 유지한다."""
    repository_root = create_runtime_repository(tmp_path)
    project_path = create_runtime_project(repository_root, "PRJ-941")
    asyncio.run(
        execute_run(
            repository_root,
            project_path,
            "GATE-00",
            "GATE-01",
            "default",
            None,
            None,
        )
    )
    story_path = project_path / "00_PROJECT" / "story_dna.json"
    before = story_path.read_bytes()

    async def unauthorized_handler(request: LLMRequest) -> LLMResponse:
        result = agent_result_document(request)
        artifacts = result["artifacts"]
        assert isinstance(artifacts, list)
        artifacts.append(
            {
                "artifact_name": "final_script",
                "media_type": "text/markdown",
                "content": "권한 밖 출력",
            }
        )
        return response_with_result(request, result)

    with pytest.raises(RuntimeExecutionError) as error_info:
        asyncio.run(
            execute_run(
                repository_root,
                project_path,
                "GATE-02",
                "GATE-02",
                "default",
                None,
                {"fake": fake_adapter(unauthorized_handler)},
            )
        )

    state = load_json_object(project_path / "00_PROJECT" / "project_state.json")
    assert error_info.value.code == "UNAUTHORIZED_ARTIFACT"
    assert story_path.read_bytes() == before
    assert state["current_gate"] == "GATE-01"


def test_retry_exhaustion_marks_project_blocked_without_artifact_commit(tmp_path: Path) -> None:
    """Provider 재시도 소진은 마지막 Gate를 유지하고 Project를 BLOCKED 처리한다."""
    repository_root = create_runtime_repository(tmp_path)
    project_path = create_runtime_project(repository_root, "PRJ-944")
    asyncio.run(
        execute_run(
            repository_root,
            project_path,
            "GATE-00",
            "GATE-01",
            "default",
            None,
            None,
        )
    )
    story_path = project_path / "00_PROJECT" / "story_dna.json"
    before = story_path.read_bytes()
    attempts: list[int] = []

    async def timeout_handler(request: LLMRequest) -> LLMResponse:
        attempts.append(int(request.metadata["attempt"]))
        raise RuntimeExecutionError(
            "PROVIDER_TIMEOUT",
            True,
            "PROVIDER",
            "의도한 Provider Timeout",
            request.metadata["task_id"],
            None,
            {"request_id": request.request_id},
        )

    with pytest.raises(RuntimeExecutionError) as error_info:
        asyncio.run(
            execute_run(
                repository_root,
                project_path,
                "GATE-02",
                "GATE-02",
                "default",
                None,
                {"fake": fake_adapter(timeout_handler)},
            )
        )

    state = load_json_object(project_path / "00_PROJECT" / "project_state.json")
    run_documents = [
        load_json_object(path)
        for path in (project_path / ".runtime" / "runs").glob("*/run.json")
    ]
    failed_runs = [document for document in run_documents if document["status"] == "FAILED"]
    assert len(failed_runs) == 1
    failed = failed_runs[0]
    tasks = failed["tasks"]
    assert isinstance(tasks, dict)
    story_task = tasks["story.design_dna"]
    assert isinstance(story_task, dict)
    assert error_info.value.code == "PROVIDER_TIMEOUT"
    assert attempts == [1, 2, 3]
    assert story_task["attempt"] == 3
    assert state["state"] == "BLOCKED"
    assert state["current_gate"] == "GATE-01"
    assert story_path.read_bytes() == before


def test_reference_run_egresses_only_sanitized_profile(tmp_path: Path) -> None:
    """Reference 원문은 Runtime Provider 기록에 남지 않고 정제 Profile만 전달된다."""
    repository_root = create_runtime_repository(tmp_path)
    project_path = create_runtime_project(repository_root, "PRJ-945")
    raw_secret = "닫힌 통제실에서 여섯 번째 경보가 울리자 민서는 서버 전원을 내렸다"
    reference_source = tmp_path / "reference-source.json"
    write_json_object(
        reference_source,
        {
            "reference_id": "REF-945",
            "selected_style_features": ["PACING", "SUSPENSE_HANDLING"],
            "raw_text": raw_secret,
            "story_content": {
                "CHARACTERS": ["민서"],
                "LOCATIONS": ["닫힌 통제실"],
                "INCIDENTS": ["여섯 번째 경보"],
                "UNIQUE_OBJECTS": ["서버 전원"],
            },
        },
    )
    reference_profile = {
        "reference_id": "REF-945",
        "allowed_style_features": ["PACING", "SUSPENSE_HANDLING"],
        "prohibited_story_content": [
            "CHARACTERS",
            "CHARACTER_RELATIONSHIPS",
            "LOCATIONS",
            "INCIDENTS",
            "CULPRIT",
            "VICTIM",
            "MOTIVE",
            "METHOD",
            "CLUES",
            "TWISTS",
            "UNIQUE_DIALOGUE",
            "UNIQUE_NUMBERS",
            "UNIQUE_OBJECTS",
            "BEAT_SEQUENCE",
        ],
        "separation_attestation": True,
    }
    for relative_path in (
        "00_PROJECT/project_manifest.json",
        "00_PROJECT/production_config.json",
        "00_PROJECT/story_dna.json",
    ):
        path = project_path / relative_path
        document = load_json_object(path)
        document["story_source_mode"] = "REFERENCE_INSPIRED"
        if path.name == "story_dna.json":
            document["reference_profile"] = reference_profile
        write_json_object(path, document)

    run = asyncio.run(
        execute_run(
            repository_root,
            project_path,
            "GATE-00",
            "GATE-11",
            "default",
            reference_source,
            None,
        )
    )

    sanitized = load_json_object(project_path / "00_PROJECT" / "reference_profile.json")
    runtime_text = "\n".join(
        path.read_text(encoding="utf-8")
        for path in (project_path / ".runtime").rglob("*")
        if path.is_file()
    )
    assert run["status"] == "COMPLETED"
    assert sanitized["mode"] == "REFERENCE_INSPIRED"
    assert "raw_text" not in sanitized
    assert "story_content" not in sanitized
    assert raw_secret not in runtime_text


def test_format_error_retries_with_monotonic_attempt_number(tmp_path: Path) -> None:
    """파싱 오류만 제한 재시도하고 두 번째 정상 출력은 Gate에 Commit한다."""
    repository_root = create_runtime_repository(tmp_path)
    project_path = create_runtime_project(repository_root, "PRJ-942")
    asyncio.run(
        execute_run(
            repository_root,
            project_path,
            "GATE-00",
            "GATE-01",
            "default",
            None,
            None,
        )
    )
    attempts: list[int] = []

    async def repair_handler(request: LLMRequest) -> LLMResponse:
        attempt = int(request.metadata["attempt"])
        attempts.append(attempt)
        if attempt == 1:
            return LLMResponse(
                request_id=request.request_id,
                provider_request_id="INVALID-FIRST",
                status="COMPLETED",
                finish_reason="STOP",
                text="not-json",
                structured_output=None,
                tool_calls=(),
                usage=TokenUsage(input_tokens=1, output_tokens=1, cached_tokens=0),
                model_resolved="runtime-test-v1",
                warnings=(),
            )
        return response_with_result(request, agent_result_document(request))

    run = asyncio.run(
        execute_run(
            repository_root,
            project_path,
            "GATE-02",
            "GATE-02",
            "default",
            None,
            {"fake": fake_adapter(repair_handler)},
        )
    )

    assert attempts == [1, 2]
    assert run["tasks"]["story.design_dna"]["attempt"] == 2
    assert (
        load_json_object(project_path / "00_PROJECT" / "project_state.json")["current_gate"]
        == "GATE-02"
    )


def test_human_approval_is_hash_bound_and_run_resumes(tmp_path: Path) -> None:
    """Human Review Run은 현재 입력 승인 전 대기하고 승인 후 같은 Run으로 재개한다."""
    repository_root = create_runtime_repository(tmp_path)
    project_path = create_runtime_project(repository_root, "PRJ-943")
    config_path = project_path / "00_PROJECT" / "production_config.json"
    config = load_json_object(config_path)
    config["approval_policy"] = "HUMAN_REVIEW"
    write_json_object(config_path, config)

    with pytest.raises(RuntimeExecutionError) as error_info:
        asyncio.run(
            execute_run(
                repository_root,
                project_path,
                "GATE-00",
                "GATE-01",
                "default",
                None,
                None,
            )
        )

    waiting = latest_run(project_path)
    run_id = waiting["run_id"]
    assert isinstance(run_id, str)
    task_state = waiting["tasks"]
    assert isinstance(task_state, dict)
    variation_state = task_state["variation.generate"]
    assert isinstance(variation_state, dict)
    input_hashes = variation_state["input_hashes"]
    assert isinstance(input_hashes, dict)
    assert error_info.value.code == "HUMAN_APPROVAL_REQUIRED"
    assert waiting["status"] == "WAITING_HUMAN"

    approval_document(
        repository_root,
        run_id,
        "variation.generate",
        "runtime-reviewer",
        "후보 VAR-01의 구조적 차이를 검토함",
    )
    assert approval_is_current(
        project_path,
        run_id,
        "variation.generate",
        input_hashes,
    )
    changed_hashes = {**input_hashes, "production_config": "changed"}
    assert not approval_is_current(
        project_path,
        run_id,
        "variation.generate",
        changed_hashes,
    )

    completed = asyncio.run(resume_run(repository_root, run_id, None))

    assert completed["status"] == "COMPLETED"
    assert completed["run_id"] == run_id
    assert (
        load_json_object(project_path / "00_PROJECT" / "project_state.json")["current_gate"]
        == "GATE-01"
    )
