"""Causal Graph 인과 무결성 검증."""

from copy import deepcopy
from pathlib import Path

from VALIDATORS.causal_validation import validate_causal_graph
from VALIDATORS.io import load_json_object
from VALIDATORS.schema_validation import collect_schema_errors

ROOT = Path(__file__).resolve().parents[1]


def make_valid_graph() -> dict[str, object]:
    """원인에서 해결까지 이어지는 최소 DAG를 만든다."""
    return {
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
        "semantic_normalization": {
            "normalized_roles": ["INTERNAL_ENTRAPMENT", "MANUAL_RESCUE"],
            "character_function_chain": ["MISREAD", "DISCOVERY", "RESCUE"],
            "audience_hypothesis_transitions": [
                "APPARENT_DEPARTURE",
                "INTERNAL_ENTRAPMENT",
            ],
        },
    }


def test_valid_causal_dag_passes() -> None:
    """Root Cause부터 Resolution까지 연결된 DAG는 통과해야 한다."""
    graph = make_valid_graph()
    graph["fingerprint"] = {
        "root_cause": "SYSTEM_FAILURE",
        "mechanism": "LOCK_SEQUENCE",
        "concealment": "LOG_GAP",
        "discovery_path": "TIME_RECONSTRUCTION",
        "resolution": "MANUAL_RELEASE",
    }
    schema = load_json_object(ROOT / "STANDARD" / "schemas" / "causal_graph.schema.json")

    assert collect_schema_errors(graph, schema, "causal_graph") == []
    assert validate_causal_graph(graph) == []


def test_cycle_and_broken_edge_are_detected() -> None:
    """순환과 존재하지 않는 Node 참조를 함께 보고해야 한다."""
    graph = deepcopy(make_valid_graph())
    edges = graph["edges"]
    assert isinstance(edges, list)
    edges.extend(
        [
            {"from": "RES-01", "to": "CAUSE-01"},
            {"from": "MISSING", "to": "RES-01"},
        ]
    )

    issues = validate_causal_graph(graph)
    codes = {issue["code"] for issue in issues}

    assert "CAUSAL_CYCLE" in codes
    assert "BROKEN_CAUSAL_EDGE" in codes


def test_disconnected_resolution_fails() -> None:
    """Resolution Node가 있어도 Root Cause 경로와 끊겼으면 실패해야 한다."""
    graph = deepcopy(make_valid_graph())
    edges = graph["edges"]
    assert isinstance(edges, list)
    edges.pop()

    issues = validate_causal_graph(graph)

    assert [issue["code"] for issue in issues] == ["CAUSAL_PATH_INCOMPLETE"]
