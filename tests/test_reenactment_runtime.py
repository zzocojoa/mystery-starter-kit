"""방송과 독립된 재연극 계획·측정 Runtime 계약 테스트."""

from collections.abc import Mapping, Sequence
from copy import deepcopy

from test_reenactment_export import (
    canonical_derived_outputs,
    clue_matrix,
    crime_event_contract,
    facts_document,
    profile_sha256,
    rendered_markdown,
)
from test_screenplay_renderers import (
    characters_document,
    output_profile,
    presentation_plan,
    reaction_segments,
    relationships_document,
    screenplay_document,
)

from VALIDATORS.reenactment_export import build_reenactment_export_report
from VALIDATORS.reenactment_runtime import (
    reenactment_runtime_evidence,
    reenactment_runtime_evidence_issues,
    reenactment_runtime_status,
)


def runtime_config() -> dict[str, object]:
    """100초 재연극 계획에 맞춘 독립 Runtime Config를 만든다."""
    return {
        "project_id": "PRJ-005",
        "script_source_mode": "SCREENPLAY_UNITS",
        "source_truth_classification": "ORIGINAL_FICTION",
        "reenactment_output_profile_id": "REENACTMENT_CHARACTER_SCRIPT",
        "reenactment_output_profile_version": "1.0.0",
        "target_runtime_minutes": 25,
        "runtime_tolerance_ratio": 0.1,
        "target_reenactment_minutes": 100 / 60,
        "reenactment_runtime_tolerance_ratio": 0.1,
    }


def configured_report(config: dict[str, object]) -> dict[str, object]:
    """독립 Runtime 설정과 현재 Renderer 출력에서 Report를 만든다."""
    screenplay = screenplay_document()
    characters = characters_document()
    relationships = relationships_document()
    profile = output_profile()
    markdown = rendered_markdown(screenplay, characters, relationships, profile)
    return build_reenactment_export_report(
        config,
        screenplay,
        facts_document(),
        characters,
        relationships,
        crime_event_contract(),
        clue_matrix(),
        profile,
        profile_sha256(),
        presentation_plan(),
        reaction_segments(),
        canonical_derived_outputs(markdown),
    )


def issue_codes(issues: Sequence[Mapping[str, object]]) -> set[str]:
    """검증 Issue code 집합을 반환한다."""
    return {
        str(issue["code"])
        for issue in issues
        if isinstance(issue.get("code"), str)
    }


def test_absent_legacy_runtime_fields_remain_valid() -> None:
    """선택 필드가 없는 기존 Config는 재연극 Runtime을 강제하지 않는다."""
    config = runtime_config()
    del config["target_reenactment_minutes"]
    del config["reenactment_runtime_tolerance_ratio"]

    status, issues = reenactment_runtime_status(
        config,
        screenplay_document(),
        presentation_plan(),
        output_profile(),
    )

    assert issues == []
    assert status["status"] == "NOT_CONFIGURED"
    assert status["target_minutes"] is None


def test_valid_target_and_profile_segment_partition_pass() -> None:
    """Profile 포함 Drama·Narration만 합산하고 Panel Segment는 제외한다."""
    report = configured_report(runtime_config())
    status = report["runtime_status"]
    assert isinstance(status, dict)

    assert report["result"] == "NEEDS_REVIEW"
    assert report["issues"] == []
    assert status["status"] == "ESTIMATED"
    assert status["included_segment_ids"] == ["SEG-001", "SEG-002", "SEG-004"]
    assert status["excluded_segment_ids"] == ["SEG-003"]
    assert status["planned_duration_sec"] == 100.0
    assert status["estimated_minutes"] == 1.666667


def test_reenactment_target_above_broadcast_fails() -> None:
    """재연극 목표가 방송 총 목표보다 크면 별도 설정 오류로 실패한다."""
    config = runtime_config()
    config["target_reenactment_minutes"] = 26

    report = configured_report(config)
    issues = report["issues"]
    assert isinstance(issues, list)

    assert report["result"] == "FAIL"
    assert "REENACTMENT_RUNTIME_TARGET_EXCEEDS_BROADCAST" in issue_codes(issues)


def test_excluded_unit_type_removes_its_segment_duration() -> None:
    """Profile에서 제외된 유형만 있는 Segment는 계획시간에 포함하지 않는다."""
    profile = deepcopy(output_profile())
    filter_contract = profile["filter_contract"]
    assert isinstance(filter_contract, dict)
    included_types = filter_contract["included_unit_types"]
    assert isinstance(included_types, list)
    included_types.remove("NARRATION")
    filter_contract["excluded_unit_types"] = ["NARRATION"]

    status, issues = reenactment_runtime_status(
        runtime_config(),
        screenplay_document(),
        presentation_plan(),
        profile,
    )

    included_segment_ids = status["included_segment_ids"]
    excluded_segment_ids = status["excluded_segment_ids"]
    assert isinstance(included_segment_ids, list)
    assert isinstance(excluded_segment_ids, list)
    assert "SEG-002" not in included_segment_ids
    assert "SEG-002" in excluded_segment_ids
    assert status["planned_duration_sec"] == 85.0
    assert "REENACTMENT_RUNTIME_MISMATCH" in issue_codes(issues)


def test_runtime_tolerance_boundary_is_inclusive() -> None:
    """허용범위 경계는 통과하고 경계를 넘는 순간 실패한다."""
    plan_at_boundary = deepcopy(presentation_plan())
    segments = plan_at_boundary["segments"]
    assert isinstance(segments, list)
    final_segment = segments[-1]
    assert isinstance(final_segment, dict)
    final_segment["duration_sec"] = 50

    _status, boundary_issues = reenactment_runtime_status(
        runtime_config(),
        screenplay_document(),
        plan_at_boundary,
        output_profile(),
    )
    assert "REENACTMENT_RUNTIME_MISMATCH" not in issue_codes(boundary_issues)

    final_segment["duration_sec"] = 50.01
    _status, outside_issues = reenactment_runtime_status(
        runtime_config(),
        screenplay_document(),
        plan_at_boundary,
        output_profile(),
    )
    assert "REENACTMENT_RUNTIME_MISMATCH" in issue_codes(outside_issues)


def test_measurement_is_stale_after_unit_bound_report_changes() -> None:
    """Unit 입력 Hash가 바뀐 Report에는 이전 측정 근거를 재사용할 수 없다."""
    config = runtime_config()
    report = configured_report(config)
    evidence = reenactment_runtime_evidence(report, "TABLE_READ", None, 100.0)
    review: dict[str, object] = {"reenactment_runtime_evidence": evidence}

    assert reenactment_runtime_evidence_issues(config, report, review) == []

    changed_report = deepcopy(report)
    input_hashes = changed_report["input_artifact_hashes"]
    assert isinstance(input_hashes, dict)
    input_hashes["screenplay_units"] = "0" * 64

    assert "REENACTMENT_RUNTIME_MEASUREMENT_STALE" in issue_codes(
        reenactment_runtime_evidence_issues(config, changed_report, review)
    )


def test_estimate_cannot_claim_measured_duration() -> None:
    """WORD_COUNT_ESTIMATE에 실측값을 섞으면 측정 증거가 아니다."""
    config = runtime_config()
    report = configured_report(config)
    invalid = reenactment_runtime_evidence(
        report,
        "WORD_COUNT_ESTIMATE",
        100.0,
        100.0,
    )

    assert "REENACTMENT_RUNTIME_EVIDENCE_INVALID" in issue_codes(
        reenactment_runtime_evidence_issues(
            config,
            report,
            {"reenactment_runtime_evidence": invalid},
        )
    )


def test_valid_word_count_estimate_uses_only_estimated_duration() -> None:
    """단어 수 예상은 양의 예상값만 가지고 실측값은 비워야 한다."""
    config = runtime_config()
    report = configured_report(config)
    evidence = reenactment_runtime_evidence(
        report,
        "WORD_COUNT_ESTIMATE",
        100.0,
        None,
    )

    assert reenactment_runtime_evidence_issues(
        config,
        report,
        {"reenactment_runtime_evidence": evidence},
    ) == []


def test_valid_recorded_audio_uses_only_measured_duration() -> None:
    """녹음 실측은 양의 실측값만 가지고 예상값은 비워야 한다."""
    config = runtime_config()
    report = configured_report(config)
    evidence = reenactment_runtime_evidence(
        report,
        "RECORDED_AUDIO",
        None,
        100.0,
    )

    assert reenactment_runtime_evidence_issues(
        config,
        report,
        {"reenactment_runtime_evidence": evidence},
    ) == []


def test_table_read_cannot_carry_active_estimate() -> None:
    """Table Read 실측에 활성 예상값을 함께 두면 배타성 위반이다."""
    config = runtime_config()
    report = configured_report(config)
    evidence = reenactment_runtime_evidence(report, "TABLE_READ", 100.0, 100.0)

    assert "REENACTMENT_RUNTIME_EVIDENCE_INVALID" in issue_codes(
        reenactment_runtime_evidence_issues(
            config,
            report,
            {"reenactment_runtime_evidence": evidence},
        )
    )


def test_recorded_audio_cannot_carry_active_estimate() -> None:
    """녹음 실측에 활성 예상값을 함께 두면 배타성 위반이다."""
    config = runtime_config()
    report = configured_report(config)
    evidence = reenactment_runtime_evidence(
        report,
        "RECORDED_AUDIO",
        100.0,
        100.0,
    )

    assert "REENACTMENT_RUNTIME_EVIDENCE_INVALID" in issue_codes(
        reenactment_runtime_evidence_issues(
            config,
            report,
            {"reenactment_runtime_evidence": evidence},
        )
    )
