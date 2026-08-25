"""Production Agent 계약과 Example Isolation 검증."""

from pathlib import Path

from VALIDATORS.agent_validation import (
    build_production_context_paths,
    validate_agent_manifest,
)
from VALIDATORS.io import load_json_object
from VALIDATORS.schema_validation import collect_schema_errors

ROOT = Path(__file__).resolve().parents[1]
MANIFEST_PATH = ROOT / "AGENTS" / "manifest.json"
MANIFEST_SCHEMA_PATH = ROOT / "STANDARD" / "schemas" / "agent_manifest.schema.json"
GRAPH_PATH = ROOT / "STANDARD" / "dependency_graph.json"


def test_agent_manifest_has_all_ten_schema_valid_agents() -> None:
    """필수 10개 Agent는 Schema와 의미 계약을 모두 통과해야 한다."""
    manifest = load_json_object(MANIFEST_PATH)
    schema = load_json_object(MANIFEST_SCHEMA_PATH)
    graph = load_json_object(GRAPH_PATH)

    assert collect_schema_errors(manifest, schema, str(MANIFEST_PATH)) == []
    validate_agent_manifest(manifest, graph, ROOT / "AGENTS")
    agents = manifest["agents"]
    assert isinstance(agents, dict)
    assert len(agents) == 10
    covered_gates = {
        gate
        for agent in agents.values()
        if isinstance(agent, dict)
        for gate in agent["gates"]
    }
    assert covered_gates == {f"GATE-{index:02d}" for index in range(14)}


def test_production_context_excludes_all_example_paths(tmp_path: Path) -> None:
    """Context Builder는 물리적으로 존재하는 EXAMPLES 파일도 반환하지 않아야 한다."""
    manifest = load_json_object(MANIFEST_PATH)
    graph = load_json_object(GRAPH_PATH)

    context_paths = build_production_context_paths(
        manifest,
        graph,
        "script_writer",
        ROOT,
        tmp_path / "PRJ-999",
    )

    assert context_paths
    assert all("EXAMPLES" not in path.parts for path in context_paths)
    assert ROOT / "EXAMPLES" / "story_dna.example.json" not in context_paths

    novelty_paths = build_production_context_paths(
        manifest,
        graph,
        "novelty_auditor",
        ROOT,
        tmp_path / "PRJ-999",
    )
    assert ROOT / "STORY_LIBRARY" / "story_fingerprints.json" in novelty_paths
