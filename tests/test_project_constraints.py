"""Project Constraint Compiler의 Fail-closed 동작 검증."""

from copy import deepcopy
from pathlib import Path

import pytest

from VALIDATORS.exceptions import ConfigurationError
from VALIDATORS.io import load_json_object
from VALIDATORS.project_constraints import compile_project_constraints

ROOT = Path(__file__).resolve().parents[1]


def compiler_inputs() -> tuple[dict[str, object], dict[str, object], dict[str, object]]:
    """기본 Constraint와 v2 Catalog·Projection Contract를 반환한다."""
    constraints = load_json_object(
        ROOT / "TEMPLATES" / "PROJECT" / "00_PROJECT" / "project_constraints.json"
    )
    catalog = load_json_object(ROOT / "STANDARD" / "variation_catalog.json")
    projection = load_json_object(ROOT / "STANDARD" / "candidate_projection_contract.json")
    return constraints, catalog, projection


def test_unknown_must_not_use_field_fails_closed() -> None:
    """오타가 있는 must_not_use Field는 무시하지 않고 실패한다."""
    constraints, catalog, projection = compiler_inputs()
    changed = deepcopy(constraints)
    changed["must_not_use"] = [
        {"field": "incidnet_type", "operator": "NOT_IN", "values": ["FRAUD"]}
    ]

    with pytest.raises(ConfigurationError, match="PROJECT_CONSTRAINT_FIELD_UNKNOWN"):
        compile_project_constraints(changed, catalog, projection)


def test_conflicting_constraints_fail() -> None:
    """같은 유일 허용값을 필수와 금지에 동시에 둘 수 없다."""
    constraints, catalog, projection = compiler_inputs()
    changed = deepcopy(constraints)
    changed["must_use"] = [{"field": "incident_type", "operator": "IN", "values": ["FRAUD"]}]
    changed["must_not_use"] = [
        {"field": "incident_type", "operator": "NOT_IN", "values": ["FRAUD"]}
    ]

    with pytest.raises(ConfigurationError, match="PROJECT_CONSTRAINT_CONFLICT"):
        compile_project_constraints(changed, catalog, projection)


def test_operator_and_value_are_catalog_typed() -> None:
    """목록과 맞지 않는 Operator 및 Enum 외 값은 각각 실패한다."""
    constraints, catalog, projection = compiler_inputs()
    wrong_operator = deepcopy(constraints)
    wrong_operator["must_use"] = [
        {"field": "incident_type", "operator": "NOT_IN", "values": ["FRAUD"]}
    ]
    with pytest.raises(ConfigurationError, match="PROJECT_CONSTRAINT_OPERATOR_INVALID"):
        compile_project_constraints(wrong_operator, catalog, projection)

    wrong_value = deepcopy(constraints)
    wrong_value["must_use"] = [{"field": "incident_type", "operator": "IN", "values": ["FRUAD"]}]
    with pytest.raises(ConfigurationError, match="PROJECT_CONSTRAINT_VALUE_INVALID"):
        compile_project_constraints(wrong_value, catalog, projection)


def test_production_complexity_limit_can_make_constraint_unsatisfiable() -> None:
    """Production Limit보다 큰 필수 Complexity는 사전에 실패한다."""
    constraints, catalog, projection = compiler_inputs()
    changed = deepcopy(constraints)
    limits = changed["production_limits"]
    assert isinstance(limits, dict)
    limits["max_production_complexity"] = "LOW"
    changed["must_use"] = [
        {
            "field": "production_complexity",
            "operator": "IN",
            "values": ["HIGH"],
        }
    ]

    with pytest.raises(ConfigurationError, match="PROJECT_CONSTRAINT_UNSATISFIABLE"):
        compile_project_constraints(changed, catalog, projection)


def test_forbidding_every_catalog_value_fails_before_generation() -> None:
    """한 Dimension의 모든 Enum을 금지하면 Candidate 생성 전에 실패한다."""
    constraints, catalog, projection = compiler_inputs()
    changed = deepcopy(constraints)
    dimensions = catalog["dimensions"]
    assert isinstance(dimensions, dict)
    incident_types = dimensions["incident_type"]
    assert isinstance(incident_types, list)
    changed["must_not_use"] = [
        {
            "field": "incident_type",
            "operator": "NOT_IN",
            "values": incident_types,
        }
    ]

    with pytest.raises(ConfigurationError, match="PROJECT_CONSTRAINT_UNSATISFIABLE"):
        compile_project_constraints(changed, catalog, projection)


def test_duplicate_rules_are_normalized_by_intersection() -> None:
    """중복 IN Rule은 교집합 하나로 정규화한다."""
    constraints, catalog, projection = compiler_inputs()
    changed = deepcopy(constraints)
    changed["must_use"] = [
        {
            "field": "incident_type",
            "operator": "IN",
            "values": ["FRAUD", "THEFT"],
        },
        {
            "field": "incident_type",
            "operator": "IN",
            "values": ["FRAUD", "BLACKMAIL"],
        },
    ]

    compiled = compile_project_constraints(changed, catalog, projection)
    assert compiled["must_use"] == [
        {"field": "incident_type", "operator": "IN", "values": ["FRAUD"]}
    ]
