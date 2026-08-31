"""Channel DNA 2.1 사건 중심 계약과 Version Pin 검증."""

from pathlib import Path

from VALIDATORS.candidate_evaluation import (
    EVENT_SCORE_FIELDS,
    EVENT_WEIGHTS,
    validate_weighted_scores,
)
from VALIDATORS.compatibility import channel_dna_sha256
from VALIDATORS.io import load_json_object
from VALIDATORS.schema_validation import collect_schema_errors
from VALIDATORS.variation_engines.v2_1_0 import EVENT_DIMENSION_ORDER, generate_candidates
from VALIDATORS.variation_registry import resolve_variation_runtime_for_channel

ROOT = Path(__file__).resolve().parents[1]
CHANNEL_PATH = ROOT / "CHANNELS/mystery_main/versions/2.1.0/channel_dna.json"
EXACT_STATEMENT = (
    "살인·납치·감금·폭행·스토킹·주거침입·교제폭력·가정폭력 등 구체적인 대인범죄 사건을 "
    "피해자·목격자·연루자의 시점으로 재연하고, 주관적 내레이션과 외부 패널의 감정 반응·용의자 "
    "추적을 교차시켜 후반에 범인, 범행 동기, 범행 방식과 피해 결과를 공개하는 범죄사건 재연·추적 "
    "예능 채널이다."
)


def runtime() -> tuple[dict[str, object], object]:
    """2.1 Channel과 검증된 Variation Runtime을 반환한다."""
    channel = load_json_object(CHANNEL_PATH)
    resolved = resolve_variation_runtime_for_channel(
        ROOT,
        {
            "channel_content_version": "2.1.0",
            "variation_engine_version": "2.1.0",
            "variation_catalog_version": "2.1.0",
        },
        channel,
    )
    return channel, resolved


def test_support_commit_registers_v21_without_activation() -> None:
    """지원 Commit에서는 Active 2.0 Pin과 기존 Snapshot을 유지한다."""
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
    assert v21["channel_dna_sha256"] == channel_dna_sha256(
        load_json_object(CHANNEL_PATH)
    )


def test_v21_preserves_exact_identity_and_disables_rigid_psychology() -> None:
    """2.1은 구체 대인범죄 정의를 보존하고 심리 9단계를 활성화하지 않는다."""
    channel, _runtime = runtime()
    schema = load_json_object(ROOT / "STANDARD/schemas/channel_dna.schema.json")
    capabilities = channel["capabilities"]
    assert isinstance(capabilities, dict)
    assert collect_schema_errors(channel, schema, str(CHANNEL_PATH)) == []
    assert channel["identity"]["statement"] == EXACT_STATEMENT  # type: ignore[index]
    assert capabilities["EXPLICIT_CRIME_EVENT_POLICY"]["enabled"] is True  # type: ignore[index]
    assert "SCENE_REALIZATION_POLICY" not in capabilities
    assert capabilities["EXPLICIT_CRIME_EVENT_POLICY"]["require_survival"] is False  # type: ignore[index]


def test_v21_generates_event_before_story_dimensions() -> None:
    """후보는 여덟 핵심 범죄 중 하나와 실제 행위·피해를 먼저 생성한다."""
    channel, resolved = runtime()
    catalog = resolved["catalog"]  # type: ignore[index]
    dimensions = catalog["dimensions"]
    assert isinstance(dimensions, dict)
    assert tuple(dimensions)[:9] == EVENT_DIMENSION_ORDER
    document = generate_candidates(
        "PRJ-901",
        "explicit-crime-event-first",
        8,
        resolved,  # type: ignore[arg-type]
        "ORIGINAL_FICTION",
    )
    candidates = document["candidates"]
    assert isinstance(candidates, list)
    core_crimes = set(
        channel["capabilities"]["EXPLICIT_CRIME_EVENT_POLICY"]["core_crimes"]  # type: ignore[index]
    )
    assert {
        candidate["crime_event"]["primary_crime"]
        for candidate in candidates
        if isinstance(candidate, dict)
    }.issubset(core_crimes)
    assert all(
        isinstance(candidate, dict)
        and candidate["crime_event"]["core_action_type"]
        and candidate["crime_event"]["harm_classifications"]
        for candidate in candidates
    )


def candidate_record() -> dict[str, object]:
    """사건 중심 Candidate 평가 한 건을 만든다."""
    scores = {field: 80 for field in EVENT_SCORE_FIELDS}
    return {
        "candidate_id": "VAR-01",
        "dimension_evidence": {field: [f"{field}의 사건 근거"] for field in EVENT_SCORE_FIELDS},
        **scores,
        "total_score": 80,
        "decision": "RECOMMENDED",
        "decision_reason": "가장 높은 사건 잠재력",
    }


def test_v21_candidate_evaluation_uses_event_weights() -> None:
    """1.3 평가는 사건 중심 다섯 Dimension과 고정 가중치를 사용한다."""
    record = candidate_record()
    assert (
        validate_weighted_scores(
            {"variation_engine_version": "2.1.0"},
            {"weights": dict(EVENT_WEIGHTS)},
            [record],
        )
        == []
    )
    changed = {"weights": {**EVENT_WEIGHTS, "production_score": 20}}
    codes = {
        issue["code"]
        for issue in validate_weighted_scores(
            {"variation_engine_version": "2.1.0"},
            changed,
            [record],
        )
    }
    assert "CANDIDATE_EVENT_WEIGHTS_INVALID" in codes


def test_new_capability_is_optional_but_required_by_v21_engine() -> None:
    """Legacy Interface는 유지하되 2.1 Engine은 새 Capability 없이는 실패한다."""
    contract = load_json_object(ROOT / "STANDARD/compatibility_contract.json")
    optional = contract["channel_dna_interface"]["optional_capabilities"]
    assert "EXPLICIT_CRIME_EVENT_POLICY" in optional
    channel, _resolved = runtime()
    broken = {**channel, "capabilities": dict(channel["capabilities"])}
    broken["capabilities"].pop("EXPLICIT_CRIME_EVENT_POLICY")  # type: ignore[union-attr]
    try:
        resolve_variation_runtime_for_channel(
            ROOT,
            {
                "channel_content_version": "2.1.0",
                "variation_engine_version": "2.1.0",
                "variation_catalog_version": "2.1.0",
            },
            broken,
        )
    except Exception as error:
        assert "VARIATION_REQUIRED_CAPABILITY_MISSING" in str(error)
    else:
        raise AssertionError("새 Capability가 없는 2.1 Runtime은 실패해야 합니다.")
