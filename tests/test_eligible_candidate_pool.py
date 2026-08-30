"""Novelty와 CORE Eligibility를 포함한 Candidate Pool 재생성 검증."""

from collections.abc import Mapping
from pathlib import Path

import pytest

from VALIDATORS.exceptions import ConfigurationError
from VALIDATORS.io import load_json_object
from VALIDATORS.variation import generate_eligible_candidate_pool
from VALIDATORS.variation_registry import resolve_variation_runtime

ROOT = Path(__file__).resolve().parents[1]


def candidate_results(
    candidates: Mapping[str, object],
    result: str,
) -> dict[str, object]:
    """모든 Candidate에 같은 판정을 부여한 Test Report를 만든다."""
    records = candidates.get("candidates")
    assert isinstance(records, list)
    return {
        "candidate_results": [
            {"candidate_id": record["candidate_id"], "result": result, "issues": []}
            for record in records
            if isinstance(record, Mapping)
        ]
    }


def legacy_pool_inputs() -> tuple[
    dict[str, object],
    dict[str, object],
    dict[str, object],
    dict[str, object],
]:
    """v1.1 Pool 생성에 필요한 고정 입력을 반환한다."""
    config: dict[str, object] = {
        "project_id": "PRJ-991",
        "channel_content_version": "1.1.0",
        "variation_engine_version": "1.0.0",
        "variation_catalog_version": "1.0.0",
        "story_source_mode": "ORIGINAL",
        "source_truth_classification": "ORIGINAL_FICTION",
        "genre": "MYSTERY",
    }
    constraints = load_json_object(
        ROOT / "TEMPLATES" / "PROJECT" / "00_PROJECT" / "project_constraints.json"
    )
    constraints["project_id"] = "PRJ-991"
    channel = load_json_object(ROOT / "CHANNELS" / "mystery_main" / "channel_dna.json")
    projection = load_json_object(ROOT / "STANDARD" / "candidate_projection_contract.json")
    return config, constraints, channel, projection


def test_novelty_failed_first_batch_retries_until_pool_is_eligible(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """첫 Batch 전체 Novelty 실패 뒤 다음 Batch의 적격 후보를 채택한다."""
    config, constraints, channel, projection = legacy_pool_inputs()
    novelty_call_count = 0

    def novelty_report(
        candidates: Mapping[str, object],
        history: object,
        thresholds: Mapping[str, object],
    ) -> dict[str, object]:
        """첫 호출만 전체 실패시키는 Novelty Test Double이다."""
        del history, thresholds
        nonlocal novelty_call_count
        novelty_call_count += 1
        return candidate_results(
            candidates,
            "FAIL" if novelty_call_count == 1 else "PASS",
        )

    def eligibility_report(
        production_config: Mapping[str, object],
        project_constraints: Mapping[str, object],
        channel_document: Mapping[str, object],
        candidates: Mapping[str, object],
        novelty: Mapping[str, object],
    ) -> dict[str, object]:
        """Novelty 결과와 별개로 CORE 적격성을 통과시키는 Test Double이다."""
        del production_config, project_constraints, channel_document, novelty
        return candidate_results(candidates, "PASS")

    monkeypatch.setattr("VALIDATORS.variation.evaluate_variation_precheck", novelty_report)
    monkeypatch.setattr("VALIDATORS.variation.build_candidate_eligibility", eligibility_report)

    result = generate_eligible_candidate_pool(
        "PRJ-991",
        "retry-seed",
        5,
        resolve_variation_runtime(ROOT, config),
        "ORIGINAL_FICTION",
        config,
        constraints,
        channel,
        [],
        {},
        projection,
        None,
        3,
    )

    traces = result["batch_trace"]
    candidates = result["candidates"]
    assert isinstance(traces, list)
    assert isinstance(candidates, list)
    assert len(traces) == 2
    assert traces[0]["accepted_count"] == 0
    assert traces[1]["accepted_count"] == 5
    assert [candidate["candidate_id"] for candidate in candidates] == [
        "VAR-01",
        "VAR-02",
        "VAR-03",
        "VAR-04",
        "VAR-05",
    ]
    assert all(candidate["origin_batch_id"] == "BATCH-02" for candidate in candidates)
    assert [candidate["batch_candidate_id"] for candidate in candidates] == [
        "BVAR-01",
        "BVAR-02",
        "BVAR-03",
        "BVAR-04",
        "BVAR-05",
    ]


def test_eligible_pool_exhaustion_fails_explicitly(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """최대 Batch까지 적격 후보가 없으면 명시적 오류로 종료한다."""
    config, constraints, channel, projection = legacy_pool_inputs()

    def failed_report(
        candidates: Mapping[str, object],
        history: object,
        thresholds: Mapping[str, object],
    ) -> dict[str, object]:
        """모든 후보의 Novelty를 실패시키는 Test Double이다."""
        del history, thresholds
        return candidate_results(candidates, "FAIL")

    monkeypatch.setattr("VALIDATORS.variation.evaluate_variation_precheck", failed_report)

    with pytest.raises(ConfigurationError, match="ELIGIBLE_CANDIDATE_POOL_EXHAUSTED"):
        generate_eligible_candidate_pool(
            "PRJ-991",
            "exhaustion-seed",
            5,
            resolve_variation_runtime(ROOT, config),
            "ORIGINAL_FICTION",
            config,
            constraints,
            channel,
            [],
            {},
            projection,
            None,
            2,
        )


def test_partial_pool_retry_preserves_a_complete_batch_trace(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """두 번째 Batch에서 Pool이 채워져도 나머지 후보의 판정 Trace를 남긴다."""
    config, constraints, channel, projection = legacy_pool_inputs()
    novelty_call_count = 0

    def novelty_report(
        candidates: Mapping[str, object],
        history: object,
        thresholds: Mapping[str, object],
    ) -> dict[str, object]:
        """첫 Batch에서 네 개만 Novelty를 통과시킨다."""
        del history, thresholds
        nonlocal novelty_call_count
        novelty_call_count += 1
        records = candidates.get("candidates")
        assert isinstance(records, list)
        return {
            "candidate_results": [
                {
                    "candidate_id": record["candidate_id"],
                    "result": (
                        "FAIL" if novelty_call_count == 1 and index == len(records) - 1 else "PASS"
                    ),
                    "issues": [],
                }
                for index, record in enumerate(records)
                if isinstance(record, Mapping)
            ]
        }

    def eligibility_report(
        production_config: Mapping[str, object],
        project_constraints: Mapping[str, object],
        channel_document: Mapping[str, object],
        candidates: Mapping[str, object],
        novelty: Mapping[str, object],
    ) -> dict[str, object]:
        """CORE Eligibility는 모든 Candidate를 통과시킨다."""
        del production_config, project_constraints, channel_document, novelty
        return candidate_results(candidates, "PASS")

    monkeypatch.setattr("VALIDATORS.variation.evaluate_variation_precheck", novelty_report)
    monkeypatch.setattr("VALIDATORS.variation.build_candidate_eligibility", eligibility_report)
    monkeypatch.setattr("VALIDATORS.variation.selection_similarity", lambda left, right: 0.0)

    result = generate_eligible_candidate_pool(
        "PRJ-991",
        "partial-retry-seed",
        5,
        resolve_variation_runtime(ROOT, config),
        "ORIGINAL_FICTION",
        config,
        constraints,
        channel,
        [],
        {},
        projection,
        None,
        3,
    )

    traces = result["batch_trace"]
    assert isinstance(traces, list)
    second_trace = traces[1]
    assert isinstance(second_trace, Mapping)
    rejections = second_trace["rejections"]
    assert isinstance(rejections, list)
    assert second_trace["generated_count"] == second_trace["accepted_count"] + len(rejections)
    assert (
        sum(
            "ELIGIBLE_POOL_TARGET_REACHED" in rejection["codes"]
            for rejection in rejections
            if isinstance(rejection, Mapping)
        )
        == 4
    )
