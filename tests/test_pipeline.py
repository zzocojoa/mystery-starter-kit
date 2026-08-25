"""Compatibility부터 Production Ready까지의 전체 E2E Gate 검증."""

from copy import deepcopy
from pathlib import Path

from project_factory import make_complete_project_artifacts

from VALIDATORS.io import load_json_object
from VALIDATORS.models import ProductionValidationReport
from VALIDATORS.pipeline import run_production_validation
from VALIDATORS.schema_validation import collect_schema_errors

ROOT = Path(__file__).resolve().parents[1]


def run_complete_validation() -> ProductionValidationReport:
    """완전한 독립 Project를 기준 설정으로 검증한다."""
    return run_production_validation(
        make_complete_project_artifacts(),
        load_json_object(ROOT / "CHANNELS" / "mystery_main" / "channel_dna.json"),
        load_json_object(ROOT / "STANDARD" / "schemas" / "story_dna.schema.json"),
        load_json_object(
            ROOT / "STANDARD" / "schemas" / "story_fingerprint.schema.json"
        ),
        load_json_object(ROOT / "STANDARD" / "reference_policy.json"),
        load_json_object(ROOT / "STANDARD" / "novelty_thresholds.json"),
        [],
        None,
    )


def test_complete_project_passes_all_fourteen_gates() -> None:
    """완전한 신규 Project는 GATE-00부터 GATE-13까지 모두 통과해야 한다."""
    report = run_complete_validation()
    report_schema = load_json_object(
        ROOT / "STANDARD" / "schemas" / "validation_report.schema.json"
    )

    assert report["result"] == "PASS"
    assert report["issues"] == []
    gate_results = report["gate_results"]
    assert len(gate_results) == 14
    assert set(gate_results.values()) == {"PASS"}
    assert collect_schema_errors(report, report_schema, "generated_report") == []


def test_causal_break_blocks_full_pipeline() -> None:
    """Causal Graph 경로가 끊기면 전체 Project는 Production Ready가 될 수 없다."""
    artifacts = deepcopy(make_complete_project_artifacts())
    causal_graph = artifacts["causal_graph"]
    assert isinstance(causal_graph, dict)
    edges = causal_graph["edges"]
    assert isinstance(edges, list)
    edges.pop()

    report = run_production_validation(
        artifacts,
        load_json_object(ROOT / "CHANNELS" / "mystery_main" / "channel_dna.json"),
        load_json_object(ROOT / "STANDARD" / "schemas" / "story_dna.schema.json"),
        load_json_object(
            ROOT / "STANDARD" / "schemas" / "story_fingerprint.schema.json"
        ),
        load_json_object(ROOT / "STANDARD" / "reference_policy.json"),
        load_json_object(ROOT / "STANDARD" / "novelty_thresholds.json"),
        [],
        None,
    )

    assert report["result"] == "FAIL"
    assert report["gate_results"]["GATE-05"] == "FAIL"
    assert report["gate_results"]["GATE-10"] == "NOT_RUN"


def test_undeclared_variation_override_blocks_story_gate() -> None:
    """승인 후보와 다른 Story DNA Dimension을 사유 없이 바꾸면 차단해야 한다."""
    artifacts = deepcopy(make_complete_project_artifacts())
    story = artifacts["story_dna"]
    assert isinstance(story, dict)
    story_dna = story["story_dna"]
    assert isinstance(story_dna, dict)
    story_dna["timeline_style"] = "REAL_TIME"

    report = run_production_validation(
        artifacts,
        load_json_object(ROOT / "CHANNELS" / "mystery_main" / "channel_dna.json"),
        load_json_object(ROOT / "STANDARD" / "schemas" / "story_dna.schema.json"),
        load_json_object(
            ROOT / "STANDARD" / "schemas" / "story_fingerprint.schema.json"
        ),
        load_json_object(ROOT / "STANDARD" / "reference_policy.json"),
        load_json_object(ROOT / "STANDARD" / "novelty_thresholds.json"),
        [],
        None,
    )

    assert report["gate_results"]["GATE-02"] == "FAIL"
    codes = {issue["code"] for issue in report["issues"]}
    assert "UNDECLARED_VARIATION_OVERRIDE" in codes


def test_cross_project_artifact_is_rejected() -> None:
    """다른 Project ID의 Artifact가 섞이면 첫 Gate에서 차단해야 한다."""
    artifacts = make_complete_project_artifacts()
    facts = artifacts["facts"]
    assert isinstance(facts, dict)
    facts["project_id"] = "PRJ-999"

    report = run_production_validation(
        artifacts,
        load_json_object(ROOT / "CHANNELS" / "mystery_main" / "channel_dna.json"),
        load_json_object(ROOT / "STANDARD" / "schemas" / "story_dna.schema.json"),
        load_json_object(
            ROOT / "STANDARD" / "schemas" / "story_fingerprint.schema.json"
        ),
        load_json_object(ROOT / "STANDARD" / "reference_policy.json"),
        load_json_object(ROOT / "STANDARD" / "novelty_thresholds.json"),
        [],
        None,
    )

    assert report["gate_results"]["GATE-00"] == "FAIL"
    codes = {issue["code"] for issue in report["issues"]}
    assert "PROJECT_ID_MISMATCH" in codes
