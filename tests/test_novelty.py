"""Story/Causal Fingerprint 신규성 검증."""

from copy import deepcopy
from pathlib import Path

import pytest

from VALIDATORS.exceptions import ConfigurationError
from VALIDATORS.io import load_json_object
from VALIDATORS.novelty import (
    build_story_fingerprint,
    evaluate_novelty,
    evaluate_variation_precheck,
    similarity_components,
    similarity_score,
)
from VALIDATORS.schema_validation import collect_schema_errors
from VALIDATORS.variation import (
    approve_variation_candidate,
    generate_variation_candidates,
)

ROOT = Path(__file__).resolve().parents[1]
STORY_PATH = ROOT / "EXAMPLES" / "story_dna.example.json"
THRESHOLDS_PATH = ROOT / "STANDARD" / "novelty_thresholds.json"
THRESHOLDS_SCHEMA_PATH = (
    ROOT / "STANDARD" / "schemas" / "novelty_thresholds.schema.json"
)
FINGERPRINT_SCHEMA_PATH = ROOT / "STANDARD" / "schemas" / "story_fingerprint.schema.json"
PRECHECK_SCHEMA_PATH = ROOT / "STANDARD" / "schemas" / "novelty_precheck.schema.json"


def make_fingerprint() -> dict[str, object]:
    """테스트용 완전한 Fingerprint를 생성한다."""
    story = load_json_object(STORY_PATH)
    beat_sheet: dict[str, object] = {
        "project_id": "PRJ-001",
        "beats": [
            {"beat_id": "BEAT-01", "type": "HOOK"},
            {"beat_id": "BEAT-02", "type": "FALSE_SOLUTION"},
            {"beat_id": "BEAT-03", "type": "REVEAL"},
        ],
    }
    causal_graph: dict[str, object] = {
        "project_id": "PRJ-001",
        "nodes": [
            {"node_id": "CAUSE-01", "type": "ROOT_CAUSE"},
            {"node_id": "MECH-01", "type": "MECHANISM"},
            {"node_id": "DISC-01", "type": "DISCOVERY"},
            {"node_id": "RES-01", "type": "RESOLUTION"},
        ],
        "edges": [
            {"from": "CAUSE-01", "to": "MECH-01"},
            {"from": "MECH-01", "to": "DISC-01"},
            {"from": "DISC-01", "to": "RES-01"},
        ],
        "fingerprint": {
            "root_cause": "SYSTEMIC_NEGLECT",
            "mechanism": "AUTOMATION_CASCADE",
            "concealment": "LOG_ROTATION",
            "discovery_path": "TIME_GAP_ANALYSIS",
            "resolution": "PUBLIC_DISCLOSURE",
        },
        "semantic_normalization": {
            "normalized_roles": ["ISOLATED_SITE", "INTERNAL_ENTRAPMENT"],
            "character_function_chain": ["MISREAD", "DISCOVERY", "RESCUE"],
            "audience_hypothesis_transitions": [
                "APPARENT_DEPARTURE",
                "TIMESTAMP_DOUBT",
                "INTERNAL_ENTRAPMENT",
            ],
        },
    }
    return build_story_fingerprint(story, beat_sheet, causal_graph)


def test_story_fingerprint_passes_schema() -> None:
    """Story, Beat, Causal 요소로 만든 Fingerprint는 표준 Schema를 통과해야 한다."""
    fingerprint = make_fingerprint()
    schema = load_json_object(FINGERPRINT_SCHEMA_PATH)

    assert collect_schema_errors(fingerprint, schema, "generated_fingerprint") == []


def test_novelty_thresholds_pass_schema() -> None:
    """최근·전체 유사도와 Weight 기준은 자체 Schema를 통과해야 한다."""
    thresholds = load_json_object(THRESHOLDS_PATH)
    schema = load_json_object(THRESHOLDS_SCHEMA_PATH)

    assert collect_schema_errors(thresholds, schema, "novelty_thresholds") == []


def test_causal_fingerprint_exact_match_is_hard_collision() -> None:
    """Causal 다섯 요소가 모두 같으면 유사도와 무관하게 차단해야 한다."""
    fingerprint = make_fingerprint()
    existing = deepcopy(fingerprint)
    existing["project_id"] = "PRJ-099"
    thresholds = load_json_object(THRESHOLDS_PATH)

    report = evaluate_novelty(fingerprint, [existing], thresholds)

    assert report["result"] == "FAIL"
    issues = report["issues"]
    assert isinstance(issues, list)
    assert [issue["code"] for issue in issues] == ["CAUSAL_HARD_COLLISION"]


def test_semantic_causal_reskin_is_hard_collision() -> None:
    """인과 문구를 바꿔도 역할과 가설 전이 골격이 같으면 차단해야 한다."""
    fingerprint = make_fingerprint()
    existing = deepcopy(fingerprint)
    existing["project_id"] = "PRJ-099"
    causal = existing["causal"]
    assert isinstance(causal, dict)
    causal.update(
        {
            "root_cause": "DIFFERENT_CAUSE_NAME",
            "mechanism": "DIFFERENT_MECHANISM_NAME",
            "concealment": "DIFFERENT_CONCEALMENT_NAME",
            "discovery_path": "DIFFERENT_DISCOVERY_NAME",
            "resolution": "DIFFERENT_RESOLUTION_NAME",
        }
    )
    thresholds = load_json_object(THRESHOLDS_PATH)

    report = evaluate_novelty(fingerprint, [existing], thresholds)

    assert report["result"] == "FAIL"
    issues = report["issues"]
    assert isinstance(issues, list)
    assert [issue["code"] for issue in issues] == ["CAUSAL_SEMANTIC_COLLISION"]
    assert report["semantic_hard_collisions"] == ["PRJ-099"]


def test_registered_project_does_not_collide_with_itself() -> None:
    """등록 후 재검증할 때 동일 Project History는 신규성 비교에서 제외해야 한다."""
    fingerprint = make_fingerprint()
    thresholds = load_json_object(THRESHOLDS_PATH)

    report = evaluate_novelty(fingerprint, [deepcopy(fingerprint)], thresholds)

    assert report["result"] == "PASS"
    assert report["comparisons"] == []
    assert report["issues"] == []


def test_novelty_requires_candidate_project_id() -> None:
    """자기 비교 제외가 모호해지지 않도록 Candidate Project ID를 필수로 요구한다."""
    fingerprint = make_fingerprint()
    del fingerprint["project_id"]
    thresholds = load_json_object(THRESHOLDS_PATH)

    with pytest.raises(ConfigurationError, match="Candidate Project ID"):
        evaluate_novelty(fingerprint, [], thresholds)


def test_distinct_story_and_causal_fingerprint_passes() -> None:
    """구조와 인과가 충분히 다른 후보는 신규성 Gate를 통과해야 한다."""
    fingerprint = make_fingerprint()
    existing = deepcopy(fingerprint)
    existing["project_id"] = "PRJ-099"
    story = existing["story"]
    causal = existing["causal"]
    assert isinstance(story, dict)
    assert isinstance(causal, dict)
    story.update(
        {
            "mystery_type": "WHO",
            "architecture": "ARCH-01_LINEAR_REVEAL",
            "protagonist_role": "REPORTER",
            "primary_twist": "TW-03_FALSE_VICTIM",
            "timeline_style": "REAL_TIME",
            "culprit_structure": "DUAL",
            "setting_logic": ["OPEN_CITY"],
            "information_mechanism": ["INTERVIEW"],
            "relationship_engine": "RIVALRY",
            "pressure_engine": "COUNTDOWN",
            "dramatic_engine": "MORAL_DILEMMA",
        }
    )
    causal.update(
        {
            "root_cause": "GREED",
            "mechanism": "PHYSICAL_SWAP",
            "concealment": "FALSE_WITNESS",
            "discovery_path": "OBJECT_TRACE",
            "resolution": "ARREST",
        }
    )
    semantic = existing["semantic_causal"]
    assert isinstance(semantic, dict)
    semantic.update(
        {
            "normalized_roles": ["OPEN_CITY", "PLANNED_CRIME"],
            "edge_sequence": ["ROOT_CAUSE>RESOLUTION"],
            "character_function_chain": ["INVESTIGATION", "ARREST"],
            "audience_hypothesis_transitions": ["SUSPECT_A", "CULPRIT_B"],
        }
    )
    thresholds = load_json_object(THRESHOLDS_PATH)

    report = evaluate_novelty(fingerprint, [existing], thresholds)

    assert report["result"] == "PASS"
    assert report["issues"] == []


def test_similarity_uses_jaccard_beat_sequence_and_causal_structure() -> None:
    """List, Beat, Causal Dimension은 각 구조에 맞는 부분 유사도를 사용해야 한다."""
    candidate = make_fingerprint()
    existing = deepcopy(candidate)
    existing_story = existing.get("story")
    existing_causal = existing.get("causal")
    assert isinstance(existing_story, dict)
    assert isinstance(existing_causal, dict)
    existing_story["setting_logic"] = ["MACHINE_LOG", "OTHER"]
    existing["beat_signature"] = ["HOOK", "DISCOVERY", "REVEAL"]
    existing_causal["resolution"] = "ARREST"
    thresholds = load_json_object(THRESHOLDS_PATH)
    weights = thresholds.get("weights")
    assert isinstance(weights, dict)

    components = similarity_components(candidate, existing, weights)
    score = similarity_score(candidate, existing, weights)

    assert components["setting_logic"] == pytest.approx(0.25)
    assert components["beat_signature"] == pytest.approx(2 / 3)
    assert components["causal"] == pytest.approx(0.8)
    assert 0 < score < 100


def test_approved_variation_precheck_passes_schema_without_history() -> None:
    """History가 비어 있으면 승인 후보 Precheck는 PASS하고 Schema를 통과해야 한다."""
    catalog = load_json_object(ROOT / "STANDARD" / "variation_catalog.json")
    candidates = generate_variation_candidates("PRJ-002", "seed", 5, catalog)
    approved = approve_variation_candidate(candidates, "VAR-01")
    thresholds = load_json_object(THRESHOLDS_PATH)

    report = evaluate_variation_precheck(approved, [], thresholds)
    schema = load_json_object(PRECHECK_SCHEMA_PATH)

    assert report["result"] == "PASS"
    assert collect_schema_errors(report, schema, "novelty_precheck") == []


def test_colliding_candidate_fails_while_other_candidates_remain_eligible() -> None:
    """충돌 후보는 FAIL이지만 다른 PASS 후보는 평가 대상으로 남는다."""
    catalog = load_json_object(ROOT / "STANDARD" / "variation_catalog.json")
    candidates = generate_variation_candidates("PRJ-002", "seed", 5, catalog)
    approved = approve_variation_candidate(candidates, "VAR-01")
    records = approved["candidates"]
    assert isinstance(records, list)
    first = records[0]
    assert isinstance(first, dict)
    selection = first["selection"]
    assert isinstance(selection, dict)
    history = [{"project_id": "PRJ-001", "story": deepcopy(selection)}]
    thresholds = load_json_object(THRESHOLDS_PATH)

    report = evaluate_variation_precheck(approved, history, thresholds)

    assert report["result"] == "PASS"
    results = report["candidate_results"]
    assert isinstance(results, list)
    first_result = results[0]
    assert isinstance(first_result, dict)
    assert first_result["candidate_id"] == "VAR-01"
    assert first_result["result"] == "FAIL"
    assert any(
        isinstance(result, dict) and result.get("result") == "PASS"
        for result in results[1:]
    )


def test_approved_variation_precheck_ignores_same_project_history() -> None:
    """등록된 동일 Project를 다시 사전검사해도 자기 자신과 충돌하지 않아야 한다."""
    catalog = load_json_object(ROOT / "STANDARD" / "variation_catalog.json")
    candidates = generate_variation_candidates("PRJ-002", "seed", 5, catalog)
    approved = approve_variation_candidate(candidates, "VAR-01")
    records = approved["candidates"]
    assert isinstance(records, list)
    first = records[0]
    assert isinstance(first, dict)
    selection = first["selection"]
    assert isinstance(selection, dict)
    history = [{"project_id": "PRJ-002", "story": deepcopy(selection)}]
    thresholds = load_json_object(THRESHOLDS_PATH)

    report = evaluate_variation_precheck(approved, history, thresholds)

    assert report["result"] == "PASS"
    assert report["issues"] == []
