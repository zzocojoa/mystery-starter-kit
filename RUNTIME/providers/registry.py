"""Built-in, Entry Point, Sidecar Provider를 구성하는 Registry."""

import os
from collections.abc import Mapping
from importlib.metadata import entry_points
from typing import Protocol, cast

from RUNTIME.contracts import configuration_error, require_mapping
from RUNTIME.models import LLMProvider
from RUNTIME.providers.fake import FakeProvider
from RUNTIME.providers.sidecar import create_sidecar_provider


class ProviderFactory(Protocol):
    """외부 Entry Point Provider Factory 계약."""

    def __call__(self, provider_id: str, credential: str | None) -> LLMProvider:
        """환경 참조에서 읽은 Credential로 Adapter를 만든다."""


def provider_credential(definition: Mapping[str, object], provider_id: str) -> str | None:
    """Registry가 지정한 환경 변수에서만 Credential을 읽는다."""
    credential_env = definition.get("credential_env")
    if credential_env is None:
        return None
    if not isinstance(credential_env, str) or not credential_env:
        raise configuration_error(
            "Provider Credential 환경 변수 이름이 올바르지 않습니다.",
            {"provider_id": provider_id},
        )
    credential = os.environ.get(credential_env)
    if credential is None:
        raise configuration_error(
            "Provider Credential 환경 변수가 설정되지 않았습니다.",
            {"provider_id": provider_id, "credential_env": credential_env},
        )
    return credential


def load_entry_point_factory(entry_point_name: str) -> ProviderFactory:
    """등록된 mystery_runtime.providers Entry Point Factory를 읽는다."""
    matches = [
        entry_point
        for entry_point in entry_points(group="mystery_runtime.providers")
        if entry_point.name == entry_point_name
    ]
    if len(matches) != 1:
        raise configuration_error(
            "Provider Entry Point를 정확히 하나 찾을 수 없습니다.",
            {"entry_point": entry_point_name, "match_count": len(matches)},
        )
    loaded = matches[0].load()
    if not callable(loaded):
        raise configuration_error(
            "Provider Entry Point가 Callable이 아닙니다.",
            {"entry_point": entry_point_name},
        )
    return cast(ProviderFactory, loaded)


async def build_provider_registry(
    registry_document: Mapping[str, object],
) -> dict[str, LLMProvider]:
    """활성 Provider 정의를 Adapter 인스턴스로 변환한다."""
    definitions = require_mapping(registry_document, "providers", "provider_registry")
    providers: dict[str, LLMProvider] = {}
    for provider_id, raw_definition in definitions.items():
        if not isinstance(raw_definition, Mapping):
            raise configuration_error(
                "Provider Registry 정의가 객체가 아닙니다.",
                {"provider_id": provider_id},
            )
        if raw_definition.get("enabled") is not True:
            continue
        adapter_type = raw_definition.get("adapter_type")
        entry_point_name = raw_definition.get("adapter_entry_point")
        if not isinstance(entry_point_name, str):
            raise configuration_error(
                "Provider Adapter Entry Point가 문자열이 아닙니다.",
                {"provider_id": provider_id},
            )
        credential = provider_credential(raw_definition, provider_id)
        if adapter_type == "IN_PROCESS_PLUGIN":
            if entry_point_name == "builtin:fake":
                provider: LLMProvider = FakeProvider({})
            else:
                provider = load_entry_point_factory(entry_point_name)(provider_id, credential)
        elif adapter_type == "SIDECAR_HTTP":
            endpoint = raw_definition.get("endpoint")
            if not isinstance(endpoint, str) or not endpoint:
                raise configuration_error(
                    "Sidecar Provider Endpoint가 없습니다.",
                    {"provider_id": provider_id},
                )
            provider = await create_sidecar_provider(endpoint, credential, 30.0, 3)
        else:
            raise configuration_error(
                "알 수 없는 Provider Adapter Type입니다.",
                {"provider_id": provider_id, "adapter_type": adapter_type},
            )
        if provider.descriptor.provider_id != provider_id:
            raise configuration_error(
                "Provider Descriptor ID가 Registry Key와 다릅니다.",
                {
                    "provider_id": provider_id,
                    "descriptor_provider_id": provider.descriptor.provider_id,
                },
            )
        providers[provider_id] = provider
    if not providers:
        raise configuration_error("활성 Provider가 하나 이상 필요합니다.", {})
    return providers


async def close_providers(providers: Mapping[str, LLMProvider]) -> None:
    """등록된 Provider 연결을 모두 명시적으로 정리한다."""
    for provider in providers.values():
        await provider.close()
