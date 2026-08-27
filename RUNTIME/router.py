"""Capability, Data Policy, Context, Budget 순서의 Provider Router."""

from collections.abc import Mapping
from typing import cast

from RUNTIME.contracts import configuration_error, require_mapping, require_string_list
from RUNTIME.errors import RuntimeExecutionError
from RUNTIME.models import DataClass, LLMProvider, SelectedRoute


def provider_allowed_classes(
    registry_document: Mapping[str, object],
    provider_id: str,
) -> set[str]:
    """Provider Registry의 Data Egress Allowlist를 반환한다."""
    providers = require_mapping(registry_document, "providers", "provider_registry")
    definition = providers.get(provider_id)
    if not isinstance(definition, Mapping):
        raise configuration_error(
            "Model Route가 알 수 없는 Provider를 참조합니다.",
            {"provider_id": provider_id},
        )
    policy = require_mapping(definition, "data_policy", provider_id)
    return set(require_string_list(policy, "allowed_classes", provider_id))


def route_candidates(
    model_profile: str,
    providers: Mapping[str, LLMProvider],
    registry_document: Mapping[str, object],
    model_routes: Mapping[str, object],
    data_classes: set[DataClass],
    input_tokens: int,
    output_tokens: int,
) -> list[SelectedRoute]:
    """정책과 Capability를 모두 만족하는 Route를 우선순위대로 반환한다."""
    if "REFERENCE_RAW" in data_classes:
        raise RuntimeExecutionError(
            "DATA_POLICY_VIOLATION",
            False,
            "TASK",
            "Reference Raw는 Provider에 전송할 수 없습니다.",
            None,
            None,
            {"data_classes": sorted(data_classes)},
        )
    profiles = require_mapping(model_routes, "profiles", "model_routes")
    profile = profiles.get(model_profile)
    if not isinstance(profile, Mapping):
        raise configuration_error(
            "알 수 없는 Model Profile입니다.",
            {"model_profile": model_profile},
        )
    required = set(require_string_list(profile, "required_capabilities", model_profile))
    routes = profile.get("routes")
    if not isinstance(routes, list) or not all(isinstance(route, Mapping) for route in routes):
        raise configuration_error(
            "Model Profile Route 배열이 올바르지 않습니다.",
            {"model_profile": model_profile},
        )
    selected: list[SelectedRoute] = []
    rejection_context: list[dict[str, object]] = []
    for route in routes:
        provider_id = route.get("provider_id")
        model_ref = route.get("model_ref")
        if not isinstance(provider_id, str) or not isinstance(model_ref, str):
            raise configuration_error(
                "Model Route 식별자가 올바르지 않습니다.",
                {"model_profile": model_profile},
            )
        provider = providers.get(provider_id)
        if provider is None:
            rejection_context.append({"provider_id": provider_id, "reason": "NOT_AVAILABLE"})
            continue
        allowed_classes = provider_allowed_classes(registry_document, provider_id)
        if not set(data_classes) <= allowed_classes:
            rejection_context.append({"provider_id": provider_id, "reason": "DATA_POLICY"})
            continue
        capabilities = set(provider.descriptor.capabilities)
        if not required <= capabilities:
            rejection_context.append({"provider_id": provider_id, "reason": "CAPABILITY"})
            continue
        if (
            provider.descriptor.max_context_tokens is not None
            and input_tokens > provider.descriptor.max_context_tokens
        ):
            rejection_context.append({"provider_id": provider_id, "reason": "CONTEXT_LIMIT"})
            continue
        if (
            provider.descriptor.max_output_tokens is not None
            and output_tokens > provider.descriptor.max_output_tokens
        ):
            rejection_context.append({"provider_id": provider_id, "reason": "OUTPUT_LIMIT"})
            continue
        selected.append(
            SelectedRoute(
                provider_id=provider_id,
                model_ref=model_ref,
                provider=provider,
            )
        )
    if not selected:
        raise RuntimeExecutionError(
            "PROVIDER_NOT_AVAILABLE",
            False,
            "TASK",
            "Task 조건을 만족하는 Provider Route가 없습니다.",
            None,
            None,
            {"model_profile": model_profile, "rejections": rejection_context},
        )
    return selected


def budget_values(model_routes: Mapping[str, object], budget_profile: str) -> tuple[int, int, int]:
    """입력·출력 Token과 최대 시도 Budget을 반환한다."""
    budgets = require_mapping(model_routes, "budget_profiles", "model_routes")
    budget = budgets.get(budget_profile)
    if not isinstance(budget, Mapping):
        raise configuration_error(
            "알 수 없는 Budget Profile입니다.",
            {"budget_profile": budget_profile},
        )
    values = (
        budget.get("max_input_tokens"),
        budget.get("max_output_tokens"),
        budget.get("max_attempts"),
    )
    if not all(isinstance(value, int) and not isinstance(value, bool) for value in values):
        raise configuration_error(
            "Budget Profile 값이 정수가 아닙니다.",
            {"budget_profile": budget_profile},
        )
    return cast(tuple[int, int, int], values)


def retry_values(model_routes: Mapping[str, object], retry_policy: str) -> tuple[int, int, int]:
    """Transport, Format, Semantic 최대 시도 횟수를 반환한다."""
    policies = require_mapping(model_routes, "retry_policies", "model_routes")
    policy = policies.get(retry_policy)
    if not isinstance(policy, Mapping):
        raise configuration_error(
            "알 수 없는 Retry Policy입니다.",
            {"retry_policy": retry_policy},
        )
    values = (
        policy.get("transport_attempts"),
        policy.get("format_attempts"),
        policy.get("semantic_attempts"),
    )
    if not all(isinstance(value, int) and not isinstance(value, bool) for value in values):
        raise configuration_error(
            "Retry Policy 값이 정수가 아닙니다.",
            {"retry_policy": retry_policy},
        )
    return cast(tuple[int, int, int], values)
