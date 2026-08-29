"""Runtime 계약, 최소 Context, Data Firewall, Tool 경계 검증."""

import ast
import asyncio
import os
import subprocess
import sys
from pathlib import Path
from typing import cast

import pytest

from RUNTIME.context import build_minimal_context
from RUNTIME.contracts import (
    load_model_routes,
    load_provider_registry,
    validate_runtime_contracts,
)
from RUNTIME.errors import RuntimeExecutionError
from RUNTIME.models import RuntimeTask
from RUNTIME.providers.fake import FakeProvider
from RUNTIME.router import route_candidates
from RUNTIME.tools.broker import invoke_tool, tool_definitions
from VALIDATORS.io import load_json_object

from .support import ROOT, create_runtime_project, create_runtime_repository


def run_import_probe(source: str) -> subprocess.CompletedProcess[str]:
    """새 Python Process에서 Import 순서 독립성을 검사한다."""
    environment: dict[str, str] = dict(os.environ)
    environment["PYTHONPATH"] = str(ROOT)
    return subprocess.run(
        [sys.executable, "-c", source],
        cwd=ROOT,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )


def test_gate_transaction_import_does_not_require_engine_preload() -> None:
    """Gate Transaction은 Runtime Engine 선행 Import 없이 로드되어야 한다."""
    result = run_import_probe(
        "from VALIDATORS.gate_transaction import audit_project; "
        "print(audit_project.__name__)"
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "audit_project"


def test_runtime_package_keeps_public_callable_exports() -> None:
    """Runtime Package 공개 함수는 지연 Import 이후에도 호출 가능해야 한다."""
    result = run_import_probe(
        "from RUNTIME import build_execution_plan, execute_run, resume_run; "
        "print(all(callable(value) for value in "
        "(build_execution_plan, execute_run, resume_run)))"
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "True"


def test_runtime_contracts_cross_validate_all_authorities() -> None:
    """Task는 Agent 권한·Artifact Owner·Gate·Schema 계약을 모두 통과해야 한다."""
    result = validate_runtime_contracts(ROOT)

    assert result["result"] == "PASS"
    assert result["runtime_version"] == "1.0.0"
    assert result["task_count"] == 26


def test_runtime_has_no_provider_sdk_imports() -> None:
    """Provider 독립 Core와 Adapter 패키지는 특정 Vendor SDK를 직접 Import하지 않는다."""
    forbidden_roots = {"anthropic", "boto3", "cohere", "google", "openai", "vertexai"}
    violations: list[str] = []
    source_roots = (ROOT / "RUNTIME", ROOT / "RUNTIME_ADAPTERS")
    for source_root in source_roots:
        for source_path in sorted(source_root.rglob("*.py")):
            tree = ast.parse(source_path.read_text(encoding="utf-8"), filename=str(source_path))
            for node in ast.walk(tree):
                imported: list[str] = []
                if isinstance(node, ast.Import):
                    imported = [alias.name for alias in node.names]
                elif isinstance(node, ast.ImportFrom) and node.module is not None:
                    imported = [node.module]
                for module_name in imported:
                    if module_name.split(".", maxsplit=1)[0] in forbidden_roots:
                        violations.append(f"{source_path}:{module_name}")

    assert violations == []


def test_default_distribution_routes_only_to_fake_provider() -> None:
    """기본 배포는 외부 Credential이나 Vendor Route 없이 FakeProvider만 사용한다."""
    registry = load_provider_registry(ROOT)
    providers = registry.get("providers")
    assert isinstance(providers, dict)
    assert set(providers) == {"fake"}

    model_routes = load_model_routes(ROOT)
    profiles = model_routes.get("profiles")
    assert isinstance(profiles, dict)
    route_provider_ids: set[str] = set()
    for profile in profiles.values():
        assert isinstance(profile, dict)
        routes = profile.get("routes")
        assert isinstance(routes, list)
        for route in routes:
            assert isinstance(route, dict)
            provider_id = route.get("provider_id")
            assert isinstance(provider_id, str)
            route_provider_ids.add(provider_id)

    assert route_provider_ids == {"fake"}


def test_context_builder_rejects_example_resources(tmp_path: Path) -> None:
    """물리적으로 존재하는 EXAMPLES 파일도 Production Context로 읽지 않는다."""
    repository_root = create_runtime_repository(tmp_path)
    project_path = create_runtime_project(repository_root, "PRJ-920")
    dependency_graph = load_json_object(ROOT / "STANDARD" / "dependency_graph.json")
    task = cast(
        RuntimeTask,
        {
            "agent_id": "story_architect",
            "executor": "LLM",
            "target_gate": "GATE-02",
            "reads": [],
            "writes": ["story_dna"],
            "depends_on_tasks": [],
            "condition": "ALWAYS",
            "model_profile": "STRUCTURED_CREATIVE",
            "output_contract": "STORY_DNA_BUNDLE",
            "commit_policy": "ATOMIC_ON_PASS",
            "retry_policy": "CREATIVE_STRUCTURED",
            "budget_profile": "MEDIUM",
            "standard_resources": ["EXAMPLES/story_dna.example.json"],
            "allowed_tools": [],
            "required_data_classes": ["INTERNAL"],
            "approval_required": False,
        },
    )

    with pytest.raises(RuntimeExecutionError, match="EXAMPLES") as error_info:
        build_minimal_context(
            repository_root,
            project_path,
            "story.design_dna",
            task,
            dependency_graph,
            {},
        )

    assert error_info.value.code == "DATA_POLICY_VIOLATION"


def test_router_blocks_raw_reference_before_route_selection() -> None:
    """Reference Raw는 Provider Capability와 무관하게 Egress 전에 거부한다."""
    provider = FakeProvider({})

    with pytest.raises(RuntimeExecutionError) as error_info:
        route_candidates(
            "STRUCTURED_CREATIVE",
            {"fake": provider},
            load_provider_registry(ROOT),
            load_model_routes(ROOT),
            {"REFERENCE_RAW"},
            10,
            10,
        )

    assert error_info.value.code == "DATA_POLICY_VIOLATION"


def test_tool_broker_rejects_forbidden_and_missing_tools() -> None:
    """임의 Shell·파일·Network 도구와 미등록 Allowlist 도구를 실행하지 않는다."""
    with pytest.raises(RuntimeExecutionError) as forbidden_error:
        tool_definitions({}, ["arbitrary_shell"])
    with pytest.raises(RuntimeExecutionError) as missing_error:
        tool_definitions({}, ["source.search"])
    with pytest.raises(RuntimeExecutionError) as invocation_error:
        asyncio.run(
            invoke_tool(
                {},
                [],
                "unrestricted_http",
                {},
                {"task_id": "story.design_dna"},
            )
        )

    assert forbidden_error.value.code == "TOOL_NOT_ALLOWED"
    assert missing_error.value.code == "TOOL_NOT_ALLOWED"
    assert invocation_error.value.code == "TOOL_NOT_ALLOWED"
