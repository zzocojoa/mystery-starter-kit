"""Runtime Engine Golden Path, 실패 원자성, Retry, 승인·재개 검증."""

import asyncio
import json
from collections.abc import Awaitable, Callable
from copy import deepcopy
from hashlib import sha256
from pathlib import Path

import pytest

from RUNTIME.approvals import approval_is_current
from RUNTIME.cli import approval_document
from RUNTIME.engine import execute_run, resume_run
from RUNTIME.errors import RuntimeExecutionError
from RUNTIME.human_inputs import current_evidence_input, submit_evidence_input
from RUNTIME.models import LLMRequest, LLMResponse, ProviderDescriptor, TokenUsage
from RUNTIME.providers.fake import agent_result_document
from RUNTIME.providers.in_process import InProcessProviderAdapter
from VALIDATORS.exceptions import ConfigurationError
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


def evidence_input_document(
    project_id: str,
    source_truth: str,
    input_hashes: dict[str, str],
) -> dict[str, object]:
    """원문을 포함하지 않는 Test Human Evidence 입력을 만든다."""
    return {
        "schema_family": "evidence-input",
        "schema_version": "1.0.0",
        "project_id": project_id,
        "task_id": "reference.intake_evidence",
        "source_truth_classification": source_truth,
        "sources": [
            {
                "source_id": "SRC-01",
                "url": "https://example.com/case-940",
                "title": "공식 사건 요약",
                "publisher": "Example Court",
                "published_at": "2026-08-20",
                "source_type": "COURT_RECORD",
                "retrieved_at": "2026-08-30T00:00:00Z",
                "evidence_locator": "case-summary:paragraphs-1-2",
                "source_snapshot_sha256": "a" * 64,
                "verification_actor": "evidence-editor",
                "verification_status": "VERIFIED",
            }
        ],
        "claims": [
            {
                "fact_id": "FACT-01",
                "claim": "피고인이 피해자를 폭행했다.",
                "classification": "FACT",
                "evidence_source_ids": ["SRC-01"],
                "basis_fact_ids": [],
                "evidence_scope": "공식 판결 요약의 폭행 사실 부분",
                "confidence": "HIGH",
                "presented_as_fact": True,
            },
            {
                "fact_id": "FACT-02",
                "claim": "피해자는 치료가 필요한 상해를 입었다.",
                "classification": "FACT",
                "evidence_source_ids": ["SRC-01"],
                "basis_fact_ids": [],
                "evidence_scope": "공식 판결 요약의 피해 결과 부분",
                "confidence": "HIGH",
                "presented_as_fact": True,
            },
        ],
        "source_subjects": [
            {
                "source_subject_id": "SUBJECT-01",
                "pseudonym": "지안",
                "source_role": "OFFENDER",
                "related_fact_ids": ["FACT-01"],
                "identity_disclosure_level": "PSEUDONYMIZED",
            },
            {
                "source_subject_id": "SUBJECT-02",
                "pseudonym": "태호",
                "source_role": "VICTIM",
                "related_fact_ids": ["FACT-02"],
                "identity_disclosure_level": "PSEUDONYMIZED",
            },
        ],
        "verified_events": [
            {
                "verified_event_id": "VEVT-01",
                "statement": "피고인이 피해자를 폭행했다.",
                "sequence": 1,
                "setting": "WORKPLACE",
                "participant_source_subject_ids": ["SUBJECT-01", "SUBJECT-02"],
                "source_claim_ids": ["FACT-01"],
            },
            {
                "verified_event_id": "VEVT-02",
                "statement": "피해자는 치료가 필요한 상해를 입었다.",
                "sequence": 2,
                "setting": "WORKPLACE",
                "participant_source_subject_ids": ["SUBJECT-02"],
                "source_claim_ids": ["FACT-02"],
            },
        ],
        "source_truth_contract": {
            "locked_dimensions": [
                "incident_type",
                "setting",
                "subject_roles",
                "relationships",
                "events",
                "responsible_agent_structure",
            ],
            "verified_relationships": [
                {
                    "from_source_subject_id": "SUBJECT-01",
                    "to_source_subject_id": "SUBJECT-02",
                    "relationship_type": "WORKPLACE_ACQUAINTANCE",
                    "source_claim_ids": ["FACT-01"],
                }
            ],
            "verified_incident_type": "ASSAULT",
            "verified_setting": "WORKPLACE",
            "verified_responsible_agent_structure": "SINGLE_AGENT",
            "verified_legal_outcome": None,
            "flexible_dimensions": [],
            "unknown_dimensions": ["legal_outcome"],
            "source_claim_ids": ["FACT-01", "FACT-02"],
        },
        "source_disclosure": {
            "schema_family": "source-disclosure",
            "schema_version": "1.0.0",
            "project_id": project_id,
            "internal_mode": source_truth,
            "audience_label_text": (
                "실제 사건을 바탕으로 재구성했습니다."
                if source_truth == "VERIFIED_TRUE_CASE"
                else "실제 사건에서 모티프를 얻어 각색했습니다."
            ),
        },
        "clinical_labels": {
            "schema_family": "clinical-labels",
            "schema_version": "1.0.0",
            "project_id": project_id,
            "labels": [],
        },
        "actor": "evidence-editor",
        "reason": "출처와 Claim 범위를 검증함",
        "submitted_at": "2026-08-30T00:00:00Z",
        "bound_input_hashes": input_hashes,
    }


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
    novelty_index = load_json_object(repository_root / "STORY_LIBRARY" / "novelty_index.json")
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
        (project_path / "00_PROJECT" / "process_trace.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()
    )
    assert len(trace_lines) == 31
    novelty_entries = novelty_index["entries"]
    assert isinstance(novelty_entries, list)
    runtime_entry = next(
        entry
        for entry in novelty_entries
        if isinstance(entry, dict) and entry.get("project_id") == "PRJ-940"
    )
    assert runtime_entry["status"] == "EDITORIAL_PENDING"
    assert isinstance(runtime_entry["fingerprint"], dict)
    for relative_path in (
        "01_CASE/crime_event_contract.json",
        "01_CASE/source_disclosure.json",
    ):
        assert (project_path / relative_path).is_file()
    for relative_path in (
        "01_CASE/clinical_labels.json",
        "06_SCENE/expert_segments.json",
        "07_SCRIPT/expert_analysis_script.md",
        "09_PRODUCTION/expert_analysis_script.md",
    ):
        assert not (project_path / relative_path).exists()


def test_true_story_evidence_submission_resumes_same_run_through_gate_five(
    tmp_path: Path,
) -> None:
    """사실 기반 Run은 Evidence 검증 후 같은 Run에서 GATE-05까지 Truth를 유지한다."""
    repository_root = create_runtime_repository(tmp_path)
    project_path = create_runtime_project(repository_root, "PRJ-938")
    config_path = project_path / "00_PROJECT" / "production_config.json"
    config = load_json_object(config_path)
    config["story_source_mode"] = "TRUE_STORY"
    config["source_truth_classification"] = "VERIFIED_TRUE_CASE"
    write_json_object(config_path, config)
    manifest_path = project_path / "00_PROJECT" / "project_manifest.json"
    manifest = load_json_object(manifest_path)
    manifest["story_source_mode"] = "TRUE_STORY"
    write_json_object(manifest_path, manifest)

    with pytest.raises(RuntimeExecutionError) as error_info:
        asyncio.run(
            execute_run(
                repository_root,
                project_path,
                "GATE-00",
                "GATE-05",
                "default",
                None,
                None,
            )
        )

    waiting = latest_run(project_path)
    run_id = waiting["run_id"]
    assert isinstance(run_id, str)
    waiting_tasks = waiting["tasks"]
    assert isinstance(waiting_tasks, dict)
    task_state = waiting_tasks["reference.intake_evidence"]
    assert isinstance(task_state, dict)
    input_hashes = task_state["input_hashes"]
    assert isinstance(input_hashes, dict)
    assert error_info.value.code == "HUMAN_INPUT_REQUIRED", error_info.value.as_dict()
    assert waiting["status"] == "WAITING_HUMAN"
    assert waiting["current_task_id"] == "reference.intake_evidence"
    assert waiting_tasks["variation.evaluate"]["attempt"] == 0
    assert waiting_tasks["story.design_dna"]["attempt"] == 0
    assert waiting_tasks["story.define_case"]["attempt"] == 0

    wrong_truth = evidence_input_document(
        "PRJ-938",
        "INSPIRED_BY_TRUE_EVENTS",
        input_hashes,
    )
    with pytest.raises(RuntimeExecutionError) as truth_error:
        submit_evidence_input(project_path, run_id, wrong_truth)
    assert truth_error.value.code == "HUMAN_INPUT_SOURCE_TRUTH_MISMATCH"

    raw_document = evidence_input_document(
        "PRJ-938",
        "VERIFIED_TRUE_CASE",
        input_hashes,
    )
    raw_sources = raw_document["sources"]
    assert isinstance(raw_sources, list)
    source = raw_sources[0]
    assert isinstance(source, dict)
    source["raw_text"] = "저장하면 안 되는 기사 전문"
    with pytest.raises(RuntimeExecutionError) as raw_error:
        submit_evidence_input(project_path, run_id, raw_document)
    assert raw_error.value.code == "HUMAN_INPUT_INVALID"

    pending_document = evidence_input_document(
        "PRJ-938",
        "VERIFIED_TRUE_CASE",
        input_hashes,
    )
    pending_sources = pending_document["sources"]
    assert isinstance(pending_sources, list)
    pending_source = pending_sources[0]
    assert isinstance(pending_source, dict)
    pending_source["verification_status"] = "PENDING"
    with pytest.raises(RuntimeExecutionError) as pending_error:
        submit_evidence_input(project_path, run_id, pending_document)
    assert pending_error.value.code == "HUMAN_INPUT_INVALID"

    inferred_contract_document = evidence_input_document(
        "PRJ-938",
        "VERIFIED_TRUE_CASE",
        input_hashes,
    )
    inferred_claims = inferred_contract_document["claims"]
    assert isinstance(inferred_claims, list)
    inferred_claim = inferred_claims[0]
    assert isinstance(inferred_claim, dict)
    inferred_claim["classification"] = "INFERENCE"
    inferred_claim["evidence_source_ids"] = []
    inferred_claim["basis_fact_ids"] = ["FACT-02"]
    inferred_claim["presented_as_fact"] = False
    with pytest.raises(RuntimeExecutionError) as inferred_contract_error:
        submit_evidence_input(project_path, run_id, inferred_contract_document)
    assert inferred_contract_error.value.code == "HUMAN_INPUT_INVALID"

    document = evidence_input_document(
        "PRJ-938",
        "VERIFIED_TRUE_CASE",
        input_hashes,
    )
    accepted = submit_evidence_input(project_path, run_id, document)
    assert accepted["status"] == "ACCEPTED"
    assert submit_evidence_input(project_path, run_id, document)["status"] == "NO_OP"
    conflicting = deepcopy(document)
    conflicting["actor"] = "different-reviewer"
    with pytest.raises(RuntimeExecutionError) as conflict_error:
        submit_evidence_input(project_path, run_id, conflicting)
    assert conflict_error.value.code == "HUMAN_INPUT_CONFLICT"
    assert (
        current_evidence_input(
            project_path,
            run_id,
            "PRJ-938",
            "VERIFIED_TRUE_CASE",
            {**input_hashes, "production_config": "0" * 64},
        )
        is None
    )

    completed = asyncio.run(resume_run(repository_root, run_id, None))

    assert completed["status"] == "COMPLETED"
    assert completed["run_id"] == run_id
    state = load_json_object(project_path / "00_PROJECT" / "project_state.json")
    assert state["current_gate"] == "GATE-05"
    for relative_path in (
        "01_CASE/sources.json",
        "01_CASE/source_subjects.json",
        "01_CASE/claim_evidence.json",
        "01_CASE/source_case_brief.json",
        "01_CASE/verified_fact_ledger.json",
        "01_CASE/verified_event_ledger.json",
        "01_CASE/source_truth_contract.json",
        "01_CASE/source_disclosure.json",
        "01_CASE/clinical_labels.json",
        "02_CHARACTER/characters.json",
        "02_CHARACTER/relationships.json",
        "03_TIMELINE/actual_timeline.json",
        "04_MYSTERY/causal_graph.json",
    ):
        assert (project_path / relative_path).is_file()
    transaction_paths = sorted(
        (project_path / ".runtime" / "transactions").glob("*/transaction.json")
    )
    gate_one = next(
        transaction
        for path in transaction_paths
        if (transaction := load_json_object(path)).get("gate_id") == "GATE-01"
    )
    targets = gate_one["targets"]
    assert isinstance(targets, list)
    target_names = {
        Path(str(target["target_path"])).name for target in targets if isinstance(target, dict)
    }
    assert {
        "sources.json",
        "source_subjects.json",
        "claim_evidence.json",
        "source_case_brief.json",
        "verified_fact_ledger.json",
        "verified_event_ledger.json",
        "source_truth_contract.json",
        "source_disclosure.json",
        "clinical_labels.json",
        "project_state.json",
        "change_log.jsonl",
    } <= target_names
    ledger = load_json_object(project_path / "01_CASE" / "verified_fact_ledger.json")
    story_facts = load_json_object(project_path / "01_CASE" / "facts.json")
    ledger_facts = ledger["facts"]
    generated_facts = story_facts["facts"]
    assert isinstance(ledger_facts, list)
    assert isinstance(generated_facts, list)
    assert ledger_facts
    assert all(
        isinstance(fact, dict) and fact.get("classification") == "FACT" for fact in ledger_facts
    )
    assert all(fact in generated_facts for fact in ledger_facts)


def test_source_truth_bundle_tamper_fails_before_llm_context(tmp_path: Path) -> None:
    """Evidence Bundle 변조는 Story LLM이 한 번도 호출되기 전에 차단된다."""
    repository_root = create_runtime_repository(tmp_path)
    project_path = create_runtime_project(repository_root, "PRJ-937")
    config_path = project_path / "00_PROJECT" / "production_config.json"
    config = load_json_object(config_path)
    config["story_source_mode"] = "TRUE_STORY"
    config["source_truth_classification"] = "VERIFIED_TRUE_CASE"
    write_json_object(config_path, config)
    manifest_path = project_path / "00_PROJECT" / "project_manifest.json"
    manifest = load_json_object(manifest_path)
    manifest["story_source_mode"] = "TRUE_STORY"
    write_json_object(manifest_path, manifest)

    with pytest.raises(RuntimeExecutionError) as waiting_error:
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
    assert waiting_error.value.code == "HUMAN_INPUT_REQUIRED"
    waiting = latest_run(project_path)
    run_id = waiting["run_id"]
    tasks = waiting["tasks"]
    assert isinstance(run_id, str)
    assert isinstance(tasks, dict)
    evidence_task = tasks["reference.intake_evidence"]
    assert isinstance(evidence_task, dict)
    input_hashes = evidence_task["input_hashes"]
    assert isinstance(input_hashes, dict)
    submit_evidence_input(
        project_path,
        run_id,
        evidence_input_document(
            "PRJ-937",
            "VERIFIED_TRUE_CASE",
            input_hashes,
        ),
    )
    completed = asyncio.run(resume_run(repository_root, run_id, None))
    assert completed["status"] == "COMPLETED"

    claims_path = project_path / "01_CASE" / "claim_evidence.json"
    claims = load_json_object(claims_path)
    claim_records = claims["claims"]
    assert isinstance(claim_records, list)
    claim = claim_records[0]
    assert isinstance(claim, dict)
    claim["evidence_scope"] = "변조된 범위"
    write_json_object(claims_path, claims)
    state_path = project_path / "00_PROJECT" / "project_state.json"
    state = load_json_object(state_path)
    artifact_states = state["artifacts"]
    assert isinstance(artifact_states, dict)
    claim_state = artifact_states["claim_evidence"]
    assert isinstance(claim_state, dict)
    claim_state["content_hash"] = sha256(claims_path.read_bytes()).hexdigest()
    write_json_object(state_path, state)

    call_count = 0

    async def counting_handler(request: LLMRequest) -> LLMResponse:
        """Story LLM 호출 횟수를 기록한다."""
        nonlocal call_count
        call_count += 1
        return response_with_result(request, agent_result_document(request))

    with pytest.raises(RuntimeExecutionError) as bundle_error:
        asyncio.run(
            execute_run(
                repository_root,
                project_path,
                "GATE-02",
                "GATE-02",
                "default",
                None,
                {"fake": fake_adapter(counting_handler)},
            )
        )
    assert bundle_error.value.code == "SOURCE_TRUTH_BOUND_ARTIFACT_HASH_MISMATCH"
    assert call_count == 0


def test_channel_tamper_fails_before_any_llm_call(tmp_path: Path) -> None:
    """GATE-00 뒤 Channel DNA 변조는 다음 실행의 첫 LLM 호출 전에 차단한다."""
    repository_root = create_runtime_repository(tmp_path)
    project_path = create_runtime_project(repository_root, "PRJ-939")
    asyncio.run(
        execute_run(
            repository_root,
            project_path,
            "GATE-00",
            "GATE-00",
            "default",
            None,
            None,
        )
    )
    channel_path = repository_root / "CHANNELS/mystery_main/versions/1.1.0/channel_dna.json"
    channel = load_json_object(channel_path)
    identity = channel["identity"]
    assert isinstance(identity, dict)
    identity["statement"] = "변조된 채널 정체성"
    write_json_object(channel_path, channel)
    call_count = 0

    async def counting_handler(request: LLMRequest) -> LLMResponse:
        """호출 여부만 세고 호출되면 명시적으로 실패한다."""
        nonlocal call_count
        call_count += 1
        raise AssertionError(f"LLM 호출 금지: {request.metadata.get('task_id')}")

    with pytest.raises(ConfigurationError, match="CHANNEL_DNA_HASH_MISMATCH"):
        asyncio.run(
            execute_run(
                repository_root,
                project_path,
                "GATE-01",
                "GATE-01",
                "default",
                None,
                {"fake": fake_adapter(counting_handler)},
            )
        )
    assert call_count == 0


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
        load_json_object(path) for path in (project_path / ".runtime" / "runs").glob("*/run.json")
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
    variation_state = task_state["variation.approve"]
    assert isinstance(variation_state, dict)
    input_hashes = variation_state["input_hashes"]
    assert isinstance(input_hashes, dict)
    assert error_info.value.code == "HUMAN_APPROVAL_REQUIRED"
    assert waiting["status"] == "WAITING_HUMAN"

    runtime_approval = approval_document(
        repository_root,
        run_id,
        "variation.approve",
        "runtime-reviewer",
        "후보 VAR-01의 구조적 차이를 검토함",
    )
    assert approval_is_current(
        project_path,
        run_id,
        "variation.approve",
        input_hashes,
    )
    changed_hashes = {**input_hashes, "production_config": "changed"}
    assert not approval_is_current(
        project_path,
        run_id,
        "variation.approve",
        changed_hashes,
    )

    completed = asyncio.run(resume_run(repository_root, run_id, None))

    assert completed["status"] == "COMPLETED"
    assert completed["run_id"] == run_id
    assert (
        load_json_object(project_path / "00_PROJECT" / "project_state.json")["current_gate"]
        == "GATE-01"
    )
    candidate_approval = load_json_object(project_path / "00_PROJECT" / "candidate_approval.json")
    assert candidate_approval["approval_type"] == "HUMAN_CONFIRMATION"
    assert candidate_approval["approval_id"] == runtime_approval["approval_id"]
    assert candidate_approval["actor"] == "runtime-reviewer"
    assert candidate_approval["reason"] == "후보 VAR-01의 구조적 차이를 검토함"
    assert candidate_approval["created_at"] == runtime_approval["created_at"]
    assert candidate_approval["approved_at"] == runtime_approval["created_at"]
    assert candidate_approval["bound_input_hashes"] == input_hashes
    assert candidate_approval["run_id"] == run_id
    assert candidate_approval["task_id"] == "variation.approve"
    assert "1970-01-01T00:00:00Z" not in json.dumps(candidate_approval)
