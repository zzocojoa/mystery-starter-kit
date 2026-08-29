"""Production Pipeline 테스트용 완전한 Project Artifact Factory."""

from copy import deepcopy
from pathlib import Path

from RUNTIME.providers.fake import (
    fake_broadcast_master,
    fake_candidate_evaluation,
    fake_edit_script,
    fake_editorial_review,
    fake_panel_cast,
    fake_presentation_plan,
    fake_reaction_segments,
    fake_script_layers,
)
from VALIDATORS.compatibility import channel_dna_sha256
from VALIDATORS.io import load_json_object
from VALIDATORS.novelty import build_story_fingerprint, evaluate_variation_precheck
from VALIDATORS.pipeline import ArtifactContent
from VALIDATORS.variation import (
    approve_variation_candidate,
    generate_variation_candidates,
)

ROOT = Path(__file__).resolve().parents[1]


def make_complete_project_artifacts() -> dict[str, ArtifactContent]:
    """GATE-00부터 GATE-13까지 통과하는 독립 Project를 만든다."""
    project_id = "PRJ-002"
    channel = load_json_object(ROOT / "CHANNELS" / "mystery_main" / "channel_dna.json")
    story_document = deepcopy(
        load_json_object(ROOT / "EXAMPLES" / "story_dna.example.json")
    )
    catalog = load_json_object(ROOT / "STANDARD" / "variation_catalog.json")
    variations = generate_variation_candidates(project_id, "공장 교대 중 사라진 작업자", 5, catalog)
    variations = approve_variation_candidate(variations, "VAR-01")
    candidates = variations["candidates"]
    story_dna = story_document["story_dna"]
    assert isinstance(candidates, list)
    assert isinstance(story_dna, dict)
    first_candidate = candidates[0]
    assert isinstance(first_candidate, dict)
    selection = first_candidate["selection"]
    assert isinstance(selection, dict)
    direct_dimensions = (
        "mystery_type",
        "architecture",
        "protagonist_role",
        "perspective",
        "timeline_style",
        "incident_type",
        "setting",
        "culprit_structure",
        "primary_twist",
    )
    for dimension in direct_dimensions:
        story_dna[dimension] = selection[dimension]
    relationship_engine = story_dna["relationship_engine"]
    pressure_engine = story_dna["pressure_engine"]
    dramatic_engine = story_dna["dramatic_engine"]
    assert isinstance(relationship_engine, dict)
    assert isinstance(pressure_engine, dict)
    assert isinstance(dramatic_engine, dict)
    relationship_engine["primary"] = selection["relationship_engine"]
    pressure_engine["source"] = selection["pressure_engine"]
    dramatic_engine["primary"] = selection["dramatic_engine"]
    thresholds = load_json_object(ROOT / "STANDARD" / "novelty_thresholds.json")
    novelty_precheck = evaluate_variation_precheck(variations, [], thresholds)

    production_config: dict[str, object] = {
        "project_id": project_id,
        "standard_version": "1.3.3",
        "channel_id": "MYSTERY_MAIN",
        "channel_content_version": "1.1.0",
        "approval_policy": "AUTO_CONTINUE",
        "story_source_mode": "ORIGINAL",
        "genre": "MYSTERY",
        "tones": ["GROUNDED", "SUSPENSEFUL"],
        "target_runtime_minutes": 2,
        "runtime_tolerance_ratio": 0.1,
    }
    case_input: dict[str, object] = {
        "project_id": project_id,
        "title_working": "교대 기록의 7분",
        "source_type": "FICTION",
        "central_mystery": "작업자는 언제 통제 구역을 벗어났는가?",
        "final_truth": "작업자는 정지한 이송 설비의 점검 공간에 갇혔다.",
        "causal_truth": "센서 차단과 교대 기록 오류가 구조 지연을 만들었다.",
        "culprit": None,
        "culprit_motive": None,
        "restrictions": [],
    }
    facts: dict[str, object] = {
        "project_id": project_id,
        "facts": [
            {"fact_id": "FACT-01", "statement": "기계 로그에 7분 공백이 있다."},
            {"fact_id": "FACT-02", "statement": "안전 센서는 점검 모드였다."},
        ],
    }
    characters: dict[str, object] = {
        "project_id": project_id,
        "characters": [
            {"character_id": "CHAR-01", "name": "지안", "role": "SUSPECT"},
            {"character_id": "CHAR-02", "name": "태호", "role": "MISSING_COWORKER"},
        ],
    }
    relationships: dict[str, object] = {
        "project_id": project_id,
        "relationships": [
            {
                "relationship_id": "REL-01",
                "from": "CHAR-01",
                "to": "CHAR-02",
                "engine": "TRUST_TO_RESPONSIBILITY",
            }
        ],
    }
    knowledge_matrix: dict[str, object] = {
        "project_id": project_id,
        "knowledge_events": [
            {
                "character_id": "CHAR-01",
                "fact_id": "FACT-01",
                "learned_scene_order": 1,
            },
            {
                "character_id": "CHAR-01",
                "fact_id": "FACT-02",
                "learned_scene_order": 2,
            },
        ],
    }
    actual_timeline: dict[str, object] = {
        "project_id": project_id,
        "events": [
            {
                "event_id": "EVT-01",
                "start_minute": 0,
                "end_minute": 7,
                "location_id": "CONTROL_ROOM",
                "participant_ids": ["CHAR-01"],
            },
            {
                "event_id": "EVT-02",
                "start_minute": 7,
                "end_minute": 15,
                "location_id": "CONVEYOR_SHAFT",
                "participant_ids": ["CHAR-02"],
            },
        ],
    }
    clue_matrix: dict[str, object] = {
        "project_id": project_id,
        "clues": [
            {
                "clue_id": "CLUE-01",
                "role": "CORE",
                "introduced_scene_order": 1,
                "introduced_scene_id": "SCN-01",
                "resolved_scene_order": 2,
                "resolved_scene_id": "SCN-02",
            },
            {
                "clue_id": "CLUE-02",
                "role": "RED_HERRING",
                "introduced_scene_order": 1,
                "introduced_scene_id": "SCN-01",
                "resolved_scene_order": 2,
                "resolved_scene_id": "SCN-02",
            },
        ],
    }
    causal_graph: dict[str, object] = {
        "project_id": project_id,
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
            "root_cause": "SENSOR_BYPASS",
            "mechanism": "CONVEYOR_LOCK",
            "concealment": "SHIFT_LOG_GAP",
            "discovery_path": "MACHINE_LOG_RECONSTRUCTION",
            "resolution": "MANUAL_RESCUE",
        },
        "semantic_normalization": {
            "normalized_roles": [
                "INDUSTRIAL_SITE",
                "INTERNAL_ENTRAPMENT",
                "MACHINE_LOG_DISCOVERY",
            ],
            "character_function_chain": [
                "INITIAL_MISREAD",
                "EVIDENCE_REINTERPRETATION",
                "MANUAL_RESCUE",
            ],
            "audience_hypothesis_transitions": [
                "APPARENT_DEPARTURE",
                "SYSTEM_FAILURE",
                "INTERNAL_ENTRAPMENT",
            ],
        },
    }
    beat_sheet: dict[str, object] = {
        "project_id": project_id,
        "architecture": story_dna["architecture"],
        "beats": [
            {"beat_id": "BEAT-01", "type": "HOOK"},
            {"beat_id": "BEAT-02", "type": "REVEAL"},
        ],
    }
    scene_cards: dict[str, object] = {
        "project_id": project_id,
        "scenes": [
            {
                "scene_id": "SCN-01",
                "order": 1,
                "beat_id": "BEAT-01",
                "estimated_seconds": 60,
                "clue_ids": ["CLUE-01", "CLUE-02"],
                "knowledge_claims": [
                    {"character_id": "CHAR-01", "fact_id": "FACT-01"}
                ],
            },
            {
                "scene_id": "SCN-02",
                "order": 2,
                "beat_id": "BEAT-02",
                "estimated_seconds": 60,
                "clue_ids": ["CLUE-01", "CLUE-02"],
                "knowledge_claims": [
                    {"character_id": "CHAR-01", "fact_id": "FACT-02"}
                ],
            },
        ],
    }
    fingerprint = build_story_fingerprint(story_document, beat_sheet, causal_graph)
    total_seconds = 120
    layer_scripts = fake_script_layers(total_seconds)
    broadcast_master = fake_broadcast_master(total_seconds)
    artifacts: dict[str, ArtifactContent] = {
        "project_manifest": {
            "project_id": project_id,
            "standard_version": "1.3.3",
            "channel_id": "MYSTERY_MAIN",
            "story_source_mode": "ORIGINAL",
        },
        "compatibility_report": {
            "project_id": project_id,
            "channel": {
                "channel_id": "MYSTERY_MAIN",
                "schema_family": "channel-dna",
                "schema_version": "1.0.0",
                "content_version": "1.1.0",
                "channel_dna_sha256": channel_dna_sha256(channel),
            },
            "compatibility": "PASS",
            "errors": [],
        },
        "production_config": production_config,
        "reference_profile": {
            "project_id": project_id,
            "mode": "NONE",
            "reference_id": None,
            "allowed_style_features": [],
            "prohibited_story_content": [],
        },
        "variation_candidates": variations,
        "candidate_evaluation": fake_candidate_evaluation(project_id, variations),
        "novelty_precheck": novelty_precheck,
        "story_dna": story_document,
        "story_fingerprint": fingerprint,
        "case_input": case_input,
        "facts": facts,
        "sources": {"project_id": project_id, "sources": []},
        "claim_evidence": {"project_id": project_id, "claims": []},
        "characters": characters,
        "relationships": relationships,
        "knowledge_matrix": knowledge_matrix,
        "actual_timeline": actual_timeline,
        "viewer_timeline": {
            "project_id": project_id,
            "reveals": [
                {
                    "reveal_id": "REV-01",
                    "scene_id": "SCN-01",
                    "fact_id": "FACT-01",
                },
                {
                    "reveal_id": "REV-02",
                    "scene_id": "SCN-02",
                    "fact_id": "FACT-02",
                },
            ],
        },
        "audience_belief": {
            "project_id": project_id,
            "belief_states": [
                {
                    "scene_id": "SCN-01",
                    "belief": "작업자가 기록 공백을 이용해 이탈했다.",
                    "confidence": 0.65,
                    "known_fact_ids": ["FACT-01"],
                    "active_hypothesis_ids": ["HYP-01"],
                },
                {
                    "scene_id": "SCN-02",
                    "belief": "센서 차단이 작업자의 위치를 숨겼다.",
                    "confidence": 0.9,
                    "known_fact_ids": ["FACT-01", "FACT-02"],
                    "active_hypothesis_ids": [],
                },
            ],
        },
        "clue_matrix": clue_matrix,
        "hypothesis_ledger": {
            "project_id": project_id,
            "hypotheses": [{"hypothesis_id": "HYP-01", "status": "REJECTED"}],
        },
        "causal_graph": causal_graph,
        "beat_sheet": beat_sheet,
        "retention_plan": {
            "project_id": project_id,
            "checkpoints": [{"scene_id": "SCN-01", "function": "QUESTION"}],
        },
        "scene_cards": scene_cards,
        "panel_cast": fake_panel_cast(project_id),
        "reaction_segments": fake_reaction_segments(project_id, total_seconds),
        "presentation_plan": fake_presentation_plan(project_id, total_seconds),
        **layer_scripts,
        "draft_script": broadcast_master,
        "final_script": broadcast_master,
        "shooting_script": "SCN-01 통제실 와이드. SCN-02 이송 설비 클로즈업.",
        "narration": "실종은 연쇄된 안전 실패였다.",
        "production_panel_reaction_script": (
            "RSEG-001 논리 패널 Cue\n"
            "RSEG-002 반론 패널 Cue\n"
            "RSEG-003 논리 패널 Cue"
        ),
        "subtitle_script": "00:00 지안은 7분의 공백을 발견한다.",
        "edit_script": fake_edit_script(project_id, total_seconds),
    }
    artifacts["editorial_review"] = fake_editorial_review(project_id, artifacts)
    return artifacts
