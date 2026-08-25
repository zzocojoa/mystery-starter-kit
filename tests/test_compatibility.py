"""Capability Negotiation 핵심 규칙 검증."""

from copy import deepcopy
from pathlib import Path

from VALIDATORS.compatibility import append_errors, evaluate_compatibility
from VALIDATORS.io import load_json_object
from VALIDATORS.schema_validation import collect_schema_errors

ROOT = Path(__file__).resolve().parents[1]
CONTRACT_PATH = ROOT / "STANDARD" / "compatibility_contract.json"
DEFAULTS_PATH = ROOT / "STANDARD" / "standard_defaults.json"
CHANNEL_PATH = ROOT / "CHANNELS" / "mystery_main" / "channel_dna.json"
CONTRACT_SCHEMA_PATH = ROOT / "STANDARD" / "schemas" / "compatibility_contract.schema.json"
DEFAULTS_SCHEMA_PATH = ROOT / "STANDARD" / "schemas" / "standard_defaults.schema.json"
CHANNEL_SCHEMA_PATH = ROOT / "STANDARD" / "schemas" / "channel_dna.schema.json"
STORY_SCHEMA_PATH = ROOT / "STANDARD" / "schemas" / "story_dna.schema.json"
STORY_EXAMPLE_PATH = ROOT / "EXAMPLES" / "story_dna.example.json"


def load_core_documents() -> tuple[dict[str, object], dict[str, object], dict[str, object]]:
    """테스트마다 독립적으로 수정할 핵심 문서를 읽는다."""
    return (
        load_json_object(CONTRACT_PATH),
        load_json_object(DEFAULTS_PATH),
        load_json_object(CHANNEL_PATH),
    )


def test_shipped_documents_match_their_schemas() -> None:
    """저장소 기준 문서가 선언된 Schema를 통과해야 한다."""
    contract, defaults, channel = load_core_documents()
    assert collect_schema_errors(
        contract,
        load_json_object(CONTRACT_SCHEMA_PATH),
        str(CONTRACT_PATH),
    ) == []
    assert collect_schema_errors(
        defaults,
        load_json_object(DEFAULTS_SCHEMA_PATH),
        str(DEFAULTS_PATH),
    ) == []
    assert collect_schema_errors(
        channel,
        load_json_object(CHANNEL_SCHEMA_PATH),
        str(CHANNEL_PATH),
    ) == []
    assert collect_schema_errors(
        load_json_object(STORY_EXAMPLE_PATH),
        load_json_object(STORY_SCHEMA_PATH),
        str(STORY_EXAMPLE_PATH),
    ) == []


def test_current_channel_is_compatible() -> None:
    """기준 미스터리 채널은 계약을 통과해야 한다."""
    contract, defaults, channel = load_core_documents()
    report = evaluate_compatibility(contract, defaults, channel)

    assert report["compatibility"] == "PASS"
    assert report["required_capabilities"]["GENRE_POLICY"] == "SUPPORTED"
    assert report["optional_capabilities"]["HOST_POLICY"] == "MISSING_USE_DEFAULT"
    assert report["resolved_optional_capabilities"]["HOST_POLICY"]["source"] == (
        "STANDARD_DEFAULT"
    )


def test_channel_value_is_never_overwritten_by_default() -> None:
    """명시된 Channel Capability는 같은 이름의 기본값보다 우선해야 한다."""
    contract, defaults, channel = load_core_documents()
    report = evaluate_compatibility(contract, defaults, channel)

    reaction = report["resolved_optional_capabilities"]["REACTION_POLICY"]
    channel_capabilities = channel["capabilities"]
    default_capabilities = defaults["optional_capability_defaults"]
    assert isinstance(channel_capabilities, dict)
    assert isinstance(default_capabilities, dict)
    assert reaction["source"] == "CHANNEL"
    assert reaction["value"] == channel_capabilities["REACTION_POLICY"]
    assert reaction["value"] != default_capabilities["REACTION_POLICY"]


def test_missing_required_capability_fails_before_unknowns_are_ignored() -> None:
    """필수 항목의 오타는 Unknown 무시 정책으로 숨겨지면 안 된다."""
    contract, defaults, channel = load_core_documents()
    changed_channel = deepcopy(channel)
    capabilities = changed_channel["capabilities"]
    assert isinstance(capabilities, dict)
    capabilities["GENRE_POLCIY"] = capabilities.pop("GENRE_POLICY")

    report = evaluate_compatibility(contract, defaults, changed_channel)

    assert report["compatibility"] == "FAIL"
    assert report["required_capabilities"]["GENRE_POLICY"] == "MISSING"
    assert "GENRE_POLCIY" in report["ignored_unknown_capabilities"]
    assert any(error["code"] == "MISSING_REQUIRED_CAPABILITY" for error in report["errors"])


def test_unknown_future_fields_and_capabilities_are_reported_but_ignored() -> None:
    """새 선택 기능은 기존 Standard의 성공 판정을 깨뜨리지 않아야 한다."""
    contract, defaults, channel = load_core_documents()
    changed_channel = deepcopy(channel)
    changed_channel["future_metadata"] = {"enabled": True}
    capabilities = changed_channel["capabilities"]
    assert isinstance(capabilities, dict)
    capabilities["SOUND_DESIGN_POLICY"] = "FUTURE_SHAPE_UNKNOWN_TO_V1"

    report = evaluate_compatibility(contract, defaults, changed_channel)
    schema_errors = collect_schema_errors(
        changed_channel,
        load_json_object(CHANNEL_SCHEMA_PATH),
        str(CHANNEL_PATH),
    )

    assert report["compatibility"] == "PASS"
    assert schema_errors == []
    assert report["ignored_unknown_fields"] == ["future_metadata"]
    assert report["ignored_unknown_capabilities"] == ["SOUND_DESIGN_POLICY"]


def test_content_version_does_not_affect_compatibility() -> None:
    """정책 내용 버전은 Interface 호환성 판정에 사용하지 않아야 한다."""
    contract, defaults, channel = load_core_documents()
    changed_channel = deepcopy(channel)
    changed_channel["content_version"] = "99.0.0"

    report = evaluate_compatibility(contract, defaults, changed_channel)

    assert report["compatibility"] == "PASS"
    assert report["channel"]["content_version"] == "99.0.0"


def test_unsupported_schema_major_version_fails() -> None:
    """계약 범위를 벗어난 Major Schema는 실패해야 한다."""
    contract, defaults, channel = load_core_documents()
    changed_channel = deepcopy(channel)
    changed_channel["schema_version"] = "2.0.0"

    report = evaluate_compatibility(contract, defaults, changed_channel)

    assert report["compatibility"] == "FAIL"
    assert any(error["code"] == "UNSUPPORTED_SCHEMA_VERSION" for error in report["errors"])


def test_inner_required_capability_schema_error_blocks_execution() -> None:
    """필수 Capability가 존재해도 내부 구조가 틀리면 최종 판정은 실패해야 한다."""
    contract, defaults, channel = load_core_documents()
    changed_channel = deepcopy(channel)
    capabilities = changed_channel["capabilities"]
    assert isinstance(capabilities, dict)
    capabilities["GENRE_POLICY"] = {"allowed_genres": [], "realism": "GROUNDED"}

    report = evaluate_compatibility(contract, defaults, changed_channel)
    schema_errors = collect_schema_errors(
        changed_channel,
        load_json_object(CHANNEL_SCHEMA_PATH),
        str(CHANNEL_PATH),
    )
    final_report = append_errors(report, schema_errors)

    assert final_report["compatibility"] == "FAIL"
    assert any(error["code"] == "SCHEMA_VALIDATION_ERROR" for error in final_report["errors"])
