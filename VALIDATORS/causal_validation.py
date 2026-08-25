"""Causal Graph의 참조, 순환, 해결 경로 검증."""

from collections.abc import Mapping

from VALIDATORS.continuity import require_records, require_string
from VALIDATORS.exceptions import ConfigurationError
from VALIDATORS.models import ValidationIssue


def make_causal_issue(
    code: str,
    message: str,
    context: dict[str, object],
) -> ValidationIssue:
    """Causal Graph 문제를 표준 형식으로 생성한다."""
    return ValidationIssue(
        severity="ERROR",
        code=code,
        message=message,
        artifact="04_MYSTERY/causal_graph.json",
        context=context,
    )


def build_node_types(
    causal_graph: Mapping[str, object],
) -> dict[str, str]:
    """중복 없는 Node ID와 Type 사전을 만든다."""
    nodes = require_records(causal_graph, "nodes", "causal_graph")
    node_types: dict[str, str] = {}
    for node in nodes:
        node_id = require_string(node, "node_id", "causal_graph.nodes")
        node_type = require_string(node, "type", node_id)
        if node_id in node_types:
            raise ConfigurationError(f"Causal Node ID가 중복됩니다: node_id={node_id}")
        node_types[node_id] = node_type
    return node_types


def build_edges(
    causal_graph: Mapping[str, object],
) -> list[tuple[str, str]]:
    """Causal Edge의 출발·도착 ID를 추출한다."""
    edges = require_records(causal_graph, "edges", "causal_graph")
    return [
        (
            require_string(edge, "from", "causal_graph.edges"),
            require_string(edge, "to", "causal_graph.edges"),
        )
        for edge in edges
    ]


def adjacency_map(
    node_ids: set[str],
    edges: list[tuple[str, str]],
) -> dict[str, list[str]]:
    """유효 Node만 포함하는 인접 목록을 만든다."""
    adjacency: dict[str, list[str]] = {node_id: [] for node_id in node_ids}
    for source, target in edges:
        if source in node_ids and target in node_ids:
            adjacency[source].append(target)
    return adjacency


def graph_has_cycle(adjacency: Mapping[str, list[str]]) -> bool:
    """삼색 DFS로 방향 그래프의 순환 여부를 판정한다."""
    state = {node_id: 0 for node_id in adjacency}

    def visit(node_id: str) -> bool:
        state[node_id] = 1
        for neighbor in adjacency[node_id]:
            if state[neighbor] == 1:
                return True
            if state[neighbor] == 0 and visit(neighbor):
                return True
        state[node_id] = 2
        return False

    return any(state[node_id] == 0 and visit(node_id) for node_id in adjacency)


def path_exists(
    adjacency: Mapping[str, list[str]],
    sources: set[str],
    targets: set[str],
) -> bool:
    """원인 Node 중 하나에서 해결 Node까지 도달 가능한지 검사한다."""
    pending = list(sources)
    visited: set[str] = set()
    while pending:
        node_id = pending.pop()
        if node_id in targets:
            return True
        if node_id in visited:
            continue
        visited.add(node_id)
        pending.extend(adjacency[node_id])
    return False


def validate_causal_graph(
    causal_graph: Mapping[str, object],
) -> list[ValidationIssue]:
    """Causal Graph가 유효한 비순환 원인→해결 구조인지 검사한다."""
    node_types = build_node_types(causal_graph)
    edges = build_edges(causal_graph)
    node_ids = set(node_types)
    issues: list[ValidationIssue] = []
    broken_edges = [
        {"from": source, "to": target}
        for source, target in edges
        if source not in node_ids or target not in node_ids
    ]
    if broken_edges:
        issues.append(
            make_causal_issue(
                "BROKEN_CAUSAL_EDGE",
                "Causal Edge가 존재하지 않는 Node를 참조합니다.",
                {"edges": broken_edges},
            )
        )

    adjacency = adjacency_map(node_ids, edges)
    if graph_has_cycle(adjacency):
        issues.append(
            make_causal_issue(
                "CAUSAL_CYCLE",
                "Causal Graph에 원인과 결과를 뒤집는 순환이 있습니다.",
                {},
            )
        )

    root_nodes = {
        node_id for node_id, node_type in node_types.items() if node_type == "ROOT_CAUSE"
    }
    resolution_nodes = {
        node_id for node_id, node_type in node_types.items() if node_type == "RESOLUTION"
    }
    if not root_nodes:
        issues.append(
            make_causal_issue(
                "ROOT_CAUSE_MISSING",
                "Causal Graph에 ROOT_CAUSE Node가 없습니다.",
                {},
            )
        )
    if not resolution_nodes:
        issues.append(
            make_causal_issue(
                "CAUSAL_RESOLUTION_MISSING",
                "Causal Graph에 RESOLUTION Node가 없습니다.",
                {},
            )
        )
    if root_nodes and resolution_nodes and not path_exists(
        adjacency,
        root_nodes,
        resolution_nodes,
    ):
        issues.append(
            make_causal_issue(
                "CAUSAL_PATH_INCOMPLETE",
                "ROOT_CAUSE에서 RESOLUTION까지 이어지는 인과 경로가 없습니다.",
                {
                    "root_nodes": sorted(root_nodes),
                    "resolution_nodes": sorted(resolution_nodes),
                },
            )
        )
    return issues
