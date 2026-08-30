"""Channel DNA 2.1 Version, Variation과 Candidate Potential 계약 검증."""

from hashlib import sha256
from pathlib import Path

from VALIDATORS.candidate_evaluation import (
    REALIZATION_SCORE_FIELDS,
    REALIZATION_WEIGHTS,
    validate_weighted_scores,
)
from VALIDATORS.io import load_json_object
from VALIDATORS.schema_validation import collect_schema_errors
from VALIDATORS.variation_engines.v2_1_0 import (
    PSYCHOLOGICAL_DIMENSION_ORDER,
    SECONDARY_MYSTERY_DIMENSION,
    generate_candidates,
    ordered_dimensions,
)
from VALIDATORS.variation_registry import resolve_variation_runtime_for_channel

ROOT = Path(__file__).resolve().parents[1]
CHANNEL_PATH = (
    ROOT / "CHANNELS" / "mystery_main" / "versions" / "2.1.0" / "channel_dna.json"
)


def test_v21_is_registered_but_active_channel_remains_v20() -> None:
    """2.1 Snapshot은 선택 가능하지만 Active Alias를 바꾸지 않는다."""
    manifest = load_json_object(ROOT / "CHANNELS/mystery_main/channel_manifest.json")
    active = load_json_object(ROOT / "CHANNELS/mystery_main/channel_dna.json")
    entries = manifest["available_versions"]
    assert isinstance(entries, list)
    v21 = next(
        entry
        for entry in entries
        if isinstance(entry, dict) and entry.get("content_version") == "2.1.0"
    )

    assert manifest["active_content_version"] == "2.0.0"
    assert active["content_version"] == "2.0.0"
    assert v21["channel_dna_sha256"] == sha256(CHANNEL_PATH.read_bytes()).hexdigest()


def test_v21_channel_and_new_artifact_schemas_are_valid() -> None:
    """2.1 Channel, Arc와 Script Report Schema가 자체 계약을 통과한다."""
    channel = load_json_object(CHANNEL_PATH)
    channel_schema = load_json_object(ROOT / "STANDARD/schemas/channel_dna.schema.json")
    arc_schema = load_json_object(ROOT / "STANDARD/schemas/psychological_arc.schema.json")
    report_schema = load_json_object(
        ROOT / "STANDARD/schemas/script_realization_report.schema.json"
    )

    assert collect_schema_errors(channel, channel_schema, str(CHANNEL_PATH)) == []
    assert arc_schema["$defs"]
    assert report_schema["$defs"]


def test_compatibility_keeps_five_required_capabilities() -> None:
    """SCENE_REALIZATION_POLICY는 Required Interface 수를 늘리지 않는다."""
    contract = load_json_object(ROOT / "STANDARD/compatibility_contract.json")
    interface = contract["channel_dna_interface"]
    assert isinstance(interface, dict)
    required = interface["required_capabilities"]
    optional = interface["optional_capabilities"]

    assert contract["contract_version"] == "1.2.0"
    assert isinstance(required, list) and len(required) == 5
    assert isinstance(optional, list) and "SCENE_REALIZATION_POLICY" in optional


def test_v21_variation_runtime_resolves_exact_versions_and_hashes() -> None:
    """2.1 Channel은 2.1 Engine과 Catalog에 정확히 결속된다."""
    channel = load_json_object(CHANNEL_PATH)
    runtime = resolve_variation_runtime_for_channel(
        ROOT,
        {
            "channel_content_version": "2.1.0",
            "variation_engine_version": "2.1.0",
            "variation_catalog_version": "2.1.0",
        },
        channel,
    )

    assert runtime["engine_version"] == "2.1.0"
    assert runtime["catalog_version"] == "2.1.0"
    assert runtime["entrypoint_name"].startswith("VALIDATORS.variation_engines.v2_1_0")


def test_v21_generates_psychological_architecture_before_secondary_mystery() -> None:
    """생성 순서는 심리 구조가 먼저이고 Mystery가 마지막이다."""
    channel = load_json_object(CHANNEL_PATH)
    runtime = resolve_variation_runtime_for_channel(
        ROOT,
        {
            "channel_content_version": "2.1.0",
            "variation_engine_version": "2.1.0",
            "variation_catalog_version": "2.1.0",
        },
        channel,
    )
    dimensions = runtime["catalog"]["dimensions"]
    assert isinstance(dimensions, dict)
    ordered = ordered_dimensions(dimensions)
    document = generate_candidates(
        "PRJ-901",
        "psychological-first",
        5,
        runtime,
        "ORIGINAL_FICTION",
    )
    candidates = document["candidates"]

    assert tuple(name for name, _choices in ordered[:9]) == PSYCHOLOGICAL_DIMENSION_ORDER
    assert ordered[-1][0] == SECONDARY_MYSTERY_DIMENSION
    assert isinstance(candidates, list)
    assert all(
        isinstance(candidate, dict)
        and "primary_psychological_architecture" in candidate["selection"]
        and "secondary_mystery_engine" in candidate["selection"]
        for candidate in candidates
    )


def candidate_record() -> dict[str, object]:
    """2.1 Candidate Potential 평가 한 건을 만든다."""
    scores = {field: 80 for field in REALIZATION_SCORE_FIELDS}
    return {
        "candidate_id": "VAR-01",
        "dimension_evidence": {
            field: [f"{field}의 장면화 가능 근거"] for field in REALIZATION_SCORE_FIELDS
        },
        **scores,
        "total_score": 80,
        "decision": "RECOMMENDED",
        "decision_reason": "가장 높은 잠재력",
    }


def test_v21_candidate_potential_uses_fixed_weights() -> None:
    """Potential 가중치는 Final Script 실현 점수와 분리된 고정 계약이다."""
    evaluation = {"weights": dict(REALIZATION_WEIGHTS)}
    record = candidate_record()

    assert validate_weighted_scores(
        {"variation_engine_version": "2.1.0"},
        evaluation,
        [record],
    ) == []

    changed = {"weights": {**REALIZATION_WEIGHTS, "production_score": 10}}
    codes = {
        issue["code"]
        for issue in validate_weighted_scores(
            {"variation_engine_version": "2.1.0"},
            changed,
            [record],
        )
    }
    assert "CANDIDATE_REALIZATION_WEIGHTS_INVALID" in codes


def test_v21_candidate_potential_uses_schema_v13() -> None:
    """1.3 Evaluation Schema는 Potential Dimension만 허용하고 1.2와 섞지 않는다."""
    records: list[dict[str, object]] = []
    for index in range(1, 4):
        record = candidate_record()
        record["candidate_id"] = f"VAR-{index:02d}"
        record["decision"] = "RECOMMENDED" if index == 1 else "REJECTED"
        records.append(record)
    document: dict[str, object] = {
        "schema_family": "candidate-evaluation",
        "schema_version": "1.3.0",
        "project_id": "PRJ-901",
        "weights": dict(REALIZATION_WEIGHTS),
        "input_hashes": {
            "variation_candidates": "0" * 64,
            "novelty_precheck": "1" * 64,
            "candidate_eligibility": "2" * 64,
        },
        "novelty_report_hash": "1" * 64,
        "recommended_candidate_id": "VAR-01",
        "evaluations": records,
    }
    schema = load_json_object(
        ROOT / "STANDARD" / "schemas" / "candidate_evaluation.schema.json"
    )

    assert collect_schema_errors(document, schema, "candidate_evaluation") == []
    document["schema_version"] = "1.2.0"
    assert collect_schema_errors(document, schema, "candidate_evaluation")
