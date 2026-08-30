"""Capability Negotiation 핵심 규칙 검증."""

from copy import deepcopy
from pathlib import Path

from VALIDATORS.channel_validation import validate_reaction_ratio
from VALIDATORS.compatibility import (
    append_errors,
    channel_dna_sha256,
    evaluate_channel_binding,
    evaluate_compatibility,
    parse_semantic_version,
)
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
CHANNEL_MANIFEST_PATH = ROOT / "CHANNELS" / "mystery_main" / "channel_manifest.json"
CHANNEL_MANIFEST_SCHEMA_PATH = (
    ROOT / "STANDARD" / "schemas" / "channel_manifest.schema.json"
)


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
    assert collect_schema_errors(
        load_json_object(CHANNEL_MANIFEST_PATH),
        load_json_object(CHANNEL_MANIFEST_SCHEMA_PATH),
        str(CHANNEL_MANIFEST_PATH),
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


def test_v1_1_contract_keeps_five_required_and_adds_v2_optional_capabilities() -> None:
    """v2 지원은 Required Interface를 넓히지 않고 Optional로만 확장한다."""
    contract, _defaults, _channel = load_core_documents()
    interface = contract["channel_dna_interface"]
    assert isinstance(interface, dict)
    required = interface["required_capabilities"]
    optional = interface["optional_capabilities"]
    assert isinstance(required, list)
    assert isinstance(optional, list)

    assert contract["contract_version"] == "1.1.0"
    assert len(required) == 5
    assert {
        "CRIME_PSYCHOLOGY_POLICY",
        "TRUST_AND_SAFETY_BETRAYAL_POLICY",
        "COERCIVE_CONTROL_POLICY",
        "VICTIM_CENTERED_POLICY",
        "EXPERT_ANALYSIS_POLICY",
        "RISK_SIGNAL_AND_PUBLIC_VALUE_POLICY",
        "SOURCE_DISCLOSURE_POLICY",
        "CLINICAL_LABEL_POLICY",
        "EPISODE_THEME_POLICY",
    }.issubset(set(optional))


def test_v2_optional_capability_shapes_are_explicit() -> None:
    """신규 Capability는 빈 객체나 무제한 추가 속성으로 통과하지 않아야 한다."""
    schema = load_json_object(CHANNEL_SCHEMA_PATH)
    definitions = schema["$defs"]
    assert isinstance(definitions, dict)
    definition_names = (
        "crimePsychologyPolicy",
        "trustAndSafetyBetrayalPolicy",
        "coerciveControlPolicy",
        "victimCenteredPolicy",
        "expertAnalysisPolicy",
        "riskSignalAndPublicValuePolicy",
        "sourceDisclosurePolicy",
        "clinicalLabelPolicy",
        "episodeThemePolicy",
    )

    for name in definition_names:
        definition = definitions[name]
        assert isinstance(definition, dict)
        assert definition["additionalProperties"] is False
        assert definition["required"]
        assert definition["properties"]


def test_v2_optional_defaults_match_explicit_channel_shapes() -> None:
    """신규 Optional Default는 동일 Capability의 Channel Schema를 통과해야 한다."""
    _contract, defaults, channel = load_core_documents()
    changed_channel = deepcopy(channel)
    capabilities = changed_channel["capabilities"]
    optional_defaults = defaults["optional_capability_defaults"]
    assert isinstance(capabilities, dict)
    assert isinstance(optional_defaults, dict)
    for capability_name in (
        "CRIME_PSYCHOLOGY_POLICY",
        "TRUST_AND_SAFETY_BETRAYAL_POLICY",
        "COERCIVE_CONTROL_POLICY",
        "VICTIM_CENTERED_POLICY",
        "EXPERT_ANALYSIS_POLICY",
        "RISK_SIGNAL_AND_PUBLIC_VALUE_POLICY",
        "SOURCE_DISCLOSURE_POLICY",
        "CLINICAL_LABEL_POLICY",
        "EPISODE_THEME_POLICY",
    ):
        capabilities[capability_name] = deepcopy(optional_defaults[capability_name])

    assert collect_schema_errors(
        changed_channel,
        load_json_object(CHANNEL_SCHEMA_PATH),
        "channel_with_v2_defaults",
    ) == []


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
    schema_errors = collect_schema_errors(
        changed_channel,
        load_json_object(CHANNEL_SCHEMA_PATH),
        str(CHANNEL_PATH),
    )

    assert report["compatibility"] == "FAIL"
    assert schema_errors == []
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


def test_project_channel_binding_records_version_and_hash() -> None:
    """Project 핀과 Manifest가 일치하면 DNA Hash를 포함해 통과해야 한다."""
    contract, defaults, channel = load_core_documents()
    report = evaluate_channel_binding(
        evaluate_compatibility(contract, defaults, channel),
        {
            "channel_id": "MYSTERY_MAIN",
            "channel_content_version": "2.0.0",
        },
        load_json_object(CHANNEL_MANIFEST_PATH),
        channel,
    )

    assert report["compatibility"] == "PASS"
    assert report["channel"] == {
        "channel_id": "MYSTERY_MAIN",
        "schema_family": "channel-dna",
        "schema_version": "1.0.0",
        "content_version": "2.0.0",
        "channel_dna_sha256": channel_dna_sha256(channel),
    }


def test_unregistered_content_version_fails_binding() -> None:
    """Manifest에 없는 Project 핀은 명시적 오류로 실패해야 한다."""
    contract, defaults, channel = load_core_documents()
    changed_channel = deepcopy(channel)
    changed_channel["content_version"] = "9.9.9"
    report = evaluate_channel_binding(
        evaluate_compatibility(contract, defaults, changed_channel),
        {
            "channel_id": "MYSTERY_MAIN",
            "channel_content_version": "9.9.9",
        },
        load_json_object(CHANNEL_MANIFEST_PATH),
        changed_channel,
    )

    assert report["compatibility"] == "FAIL"
    assert [error["code"] for error in report["errors"]] == [
        "CHANNEL_CONTENT_VERSION_NOT_FOUND"
    ]


def test_content_version_mismatch_fails_binding() -> None:
    """Project 핀과 읽은 DNA 버전이 다르면 실패해야 한다."""
    contract, defaults, channel = load_core_documents()
    report = evaluate_channel_binding(
        evaluate_compatibility(contract, defaults, channel),
        {
            "channel_id": "MYSTERY_MAIN",
            "channel_content_version": "1.1.0",
        },
        load_json_object(CHANNEL_MANIFEST_PATH),
        channel,
    )

    codes = {error["code"] for error in report["errors"]}
    assert "CHANNEL_CONTENT_VERSION_MISMATCH" in codes
    assert "CHANNEL_DNA_HASH_MISMATCH" in codes


def test_channel_hash_mismatch_fails_binding() -> None:
    """Manifest Hash와 실제 DNA가 다르면 실패해야 한다."""
    contract, defaults, channel = load_core_documents()
    manifest = deepcopy(load_json_object(CHANNEL_MANIFEST_PATH))
    entries = manifest["available_versions"]
    assert isinstance(entries, list)
    entry = next(
        item
        for item in entries
        if isinstance(item, dict) and item.get("content_version") == "2.0.0"
    )
    entry["channel_dna_sha256"] = "0" * 64
    report = evaluate_channel_binding(
        evaluate_compatibility(contract, defaults, channel),
        {
            "channel_id": "MYSTERY_MAIN",
            "channel_content_version": "2.0.0",
        },
        manifest,
        channel,
    )

    assert any(
        error["code"] == "CHANNEL_DNA_HASH_MISMATCH"
        for error in report["errors"]
    )


def test_semantic_versions_are_compared_numerically() -> None:
    """Content Version 순서는 문자열 사전식이 아니라 SemVer 숫자로 비교한다."""
    assert parse_semantic_version("10.0.0") > parse_semantic_version("2.0.0")


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


def test_contract_is_the_only_owner_of_required_capability_names() -> None:
    """Channel Schema는 Capability Shape만 소유하고 Required 목록은 소유하지 않아야 한다."""
    channel_schema = load_json_object(CHANNEL_SCHEMA_PATH)
    properties = channel_schema["properties"]
    assert isinstance(properties, dict)
    capabilities = properties["capabilities"]
    assert isinstance(capabilities, dict)
    assert "required" not in capabilities


def test_reaction_ratio_minimum_cannot_exceed_maximum() -> None:
    """JSON Schema로 표현하기 어려운 비율 관계는 의미 검증에서 실패해야 한다."""
    _, _, channel = load_core_documents()
    changed_channel = deepcopy(channel)
    capabilities = changed_channel["capabilities"]
    assert isinstance(capabilities, dict)
    reaction = capabilities["REACTION_POLICY"]
    assert isinstance(reaction, dict)
    reaction["target_ratio"] = {"min": 0.8, "max": 0.2}

    errors = validate_reaction_ratio(changed_channel)

    assert [error["code"] for error in errors] == ["INVALID_REACTION_RATIO"]
