"""사람용 Broadcast Canonical Artifact와 QA Report의 결속을 검증한다."""

from collections.abc import Mapping
from hashlib import sha256

from RUNTIME.broadcast_readable_renderer import render_broadcast_readable_script
from RUNTIME.screenplay_renderers import mapping_items
from VALIDATORS.candidate_evaluation import document_sha256
from VALIDATORS.exceptions import ConfigurationError
from VALIDATORS.models import ValidationIssue

READABLE_ARTIFACT_PATH = "07_SCRIPT/broadcast_readable_script.md"
READABLE_REPORT_PATH = "08_QA/broadcast_readable_report.json"
PRODUCTION_READABLE_ARTIFACT_PATH = "09_PRODUCTION/broadcast_readable_script.md"
PRODUCTION_MANIFEST_PATH = "09_PRODUCTION/production_manifest.json"


def readable_issue(
    code: str,
    message: str,
    artifact: str,
    context: dict[str, object],
) -> ValidationIssue:
    """Readable 추적 체인의 오류를 표준 Issue로 만든다."""
    return ValidationIssue(
        severity="ERROR",
        code=code,
        message=message,
        artifact=artifact,
        context=context,
    )


def readable_input_hashes(
    production_config: Mapping[str, object],
    screenplay_units: Mapping[str, object],
    characters: Mapping[str, object],
    panel_cast: Mapping[str, object],
    reaction_segments: Mapping[str, object],
    presentation_plan: Mapping[str, object],
    output_profile: Mapping[str, object],
) -> dict[str, str]:
    """Readable Artifact의 모든 Canonical JSON 입력 Hash를 계산한다."""
    return {
        "production_config": document_sha256(production_config),
        "screenplay_units": document_sha256(screenplay_units),
        "characters": document_sha256(characters),
        "panel_cast": document_sha256(panel_cast),
        "reaction_segments": document_sha256(reaction_segments),
        "presentation_plan": document_sha256(presentation_plan),
        "broadcast_readable_output_profile": document_sha256(output_profile),
    }


def readable_coverage(
    screenplay_units: Mapping[str, object],
    characters: Mapping[str, object],
    panel_cast: Mapping[str, object],
    reaction_segments: Mapping[str, object],
    presentation_plan: Mapping[str, object],
) -> dict[str, int]:
    """Canonical 입력에서 사람용 View가 포함해야 할 수량을 계산한다."""
    scenes = mapping_items(screenplay_units.get("scenes"), "scenes")
    reactions = mapping_items(
        reaction_segments.get("reaction_segments"),
        "reaction_segments",
    )
    return {
        "scene_count": len(scenes),
        "unit_count": sum(
            len(mapping_items(scene.get("units"), "units")) for scene in scenes
        ),
        "character_count": len(mapping_items(characters.get("characters"), "characters")),
        "panelist_count": len(mapping_items(panel_cast.get("panelists"), "panelists")),
        "panel_reaction_segment_count": len(reactions),
        "panel_turn_count": sum(
            len(mapping_items(reaction.get("turns"), "turns"))
            for reaction in reactions
        ),
        "presentation_segment_count": len(
            mapping_items(presentation_plan.get("segments"), "segments")
        ),
    }


def readable_output_profile_binding(
    output_profile: Mapping[str, object],
    output_profile_sha256: str,
) -> dict[str, str]:
    """QA Report에 Registry로 검증한 Profile Pin과 원본 파일 Hash를 결속한다."""
    profile_id = output_profile.get("profile_id")
    profile_version = output_profile.get("profile_version")
    if not isinstance(profile_id, str) or not isinstance(profile_version, str):
        raise ConfigurationError(
            "BROADCAST_READABLE_OUTPUT_PROFILE_IDENTITY_INVALID: "
            "profile_id와 profile_version이 문자열이어야 합니다."
        )
    return {
        "profile_id": profile_id,
        "profile_version": profile_version,
        "sha256": output_profile_sha256,
    }


def readable_source_style_evidence(
    output_profile: Mapping[str, object],
    coverage: Mapping[str, int],
    readable_script: str,
    source_truth_classification: object,
) -> dict[str, object]:
    """Source-style 불변식과 Canonical 표시 수량을 검증 증거로 고정한다."""
    source_style = output_profile.get("source_style_contract")
    filter_contract = output_profile.get("filter_contract")
    if not isinstance(source_style, Mapping) or not isinstance(filter_contract, Mapping):
        raise ConfigurationError(
            "BROADCAST_READABLE_OUTPUT_PROFILE_INVALID: "
            "source_style_contract와 filter_contract가 필요합니다."
        )
    raw_markers = filter_contract.get("forbidden_internal_markers")
    raw_uncertainty = filter_contract.get(
        "original_fiction_forbidden_uncertainty_markers"
    )
    if not isinstance(raw_markers, list) or not isinstance(raw_uncertainty, list):
        raise ConfigurationError(
            "BROADCAST_READABLE_OUTPUT_PROFILE_INVALID: "
            "금지 Marker 배열이 필요합니다."
        )
    forbidden_markers = [marker for marker in raw_markers if isinstance(marker, str)]
    if source_truth_classification == "ORIGINAL_FICTION":
        forbidden_markers.extend(
            marker for marker in raw_uncertainty if isinstance(marker, str)
        )
    return {
        "ordering_source": source_style.get("ordering_source"),
        "unit_text_policy": source_style.get("unit_text_policy"),
        "character_name_source": source_style.get("character_name_source"),
        "panel_name_source": source_style.get("panel_name_source"),
        "scene_context_position": source_style.get("scene_context_position"),
        "internal_identifier_visibility": source_style.get(
            "internal_identifier_visibility"
        ),
        "scene_context_count": coverage["scene_count"],
        "canonical_unit_count": coverage["unit_count"],
        "character_row_count": coverage["character_count"],
        "panelist_row_count": coverage["panelist_count"],
        "panel_turn_count": coverage["panel_turn_count"],
        "forbidden_marker_matches": sorted(
            marker for marker in forbidden_markers if marker in readable_script
        ),
    }


def build_broadcast_readable_report(
    production_config: Mapping[str, object],
    screenplay_units: Mapping[str, object],
    characters: Mapping[str, object],
    panel_cast: Mapping[str, object],
    reaction_segments: Mapping[str, object],
    presentation_plan: Mapping[str, object],
    output_profile: Mapping[str, object],
    output_profile_sha256: str,
    readable_script: str,
) -> dict[str, object]:
    """현재 Canonical 입력과 Readable bytes에 결속된 결정론적 QA Report를 만든다."""
    issues: list[ValidationIssue] = []
    expected_script: str | None = None
    coverage: dict[str, int] | None = None
    try:
        expected_script = render_broadcast_readable_script(
            screenplay_units,
            characters,
            panel_cast,
            reaction_segments,
            presentation_plan,
            output_profile,
        )
        coverage = readable_coverage(
            screenplay_units,
            characters,
            panel_cast,
            reaction_segments,
            presentation_plan,
        )
    except ConfigurationError as error:
        issues.append(
            readable_issue(
                "BROADCAST_READABLE_RENDER_FAILED",
                "Canonical 입력에서 사람용 Broadcast를 재구성하지 못했습니다.",
                READABLE_ARTIFACT_PATH,
                {"detail": str(error)},
            )
        )
    if expected_script is not None and expected_script != readable_script:
        issues.append(
            readable_issue(
                "BROADCAST_READABLE_RENDER_MISMATCH",
                "사람용 Broadcast가 현재 Canonical JSON의 결정론적 재렌더와 다릅니다.",
                READABLE_ARTIFACT_PATH,
                {
                    "expected_sha256": sha256(expected_script.encode("utf-8")).hexdigest(),
                    "actual_sha256": sha256(readable_script.encode("utf-8")).hexdigest(),
                },
            )
        )
    result = "MISSING" if not readable_script.strip() else "FAIL" if issues else "PASS"
    effective_coverage = coverage or {
        "scene_count": 0,
        "unit_count": 0,
        "character_count": 0,
        "panelist_count": 0,
        "panel_reaction_segment_count": 0,
        "panel_turn_count": 0,
        "presentation_segment_count": 0,
    }
    source_style_evidence = readable_source_style_evidence(
        output_profile,
        effective_coverage,
        readable_script,
        screenplay_units.get("source_truth_classification"),
    )
    marker_matches = source_style_evidence["forbidden_marker_matches"]
    if isinstance(marker_matches, list) and marker_matches:
        issues.append(
            readable_issue(
                "BROADCAST_READABLE_INTERNAL_MARKER_EXPOSED",
                "사람용 Broadcast에 내부 식별자 또는 불확실성 Marker가 노출되었습니다.",
                READABLE_ARTIFACT_PATH,
                {"matches": marker_matches},
            )
        )
        result = "FAIL"
    return {
        "$schema": "../../../STANDARD/schemas/broadcast_readable_report.schema.json",
        "schema_family": "broadcast-readable-report",
        "schema_version": "1.0.0",
        "project_id": screenplay_units.get("project_id"),
        "result": result,
        "output_profile": readable_output_profile_binding(
            output_profile,
            output_profile_sha256,
        ),
        "input_artifact_hashes": readable_input_hashes(
            production_config,
            screenplay_units,
            characters,
            panel_cast,
            reaction_segments,
            presentation_plan,
            output_profile,
        ),
        "output_markdown_sha256": sha256(readable_script.encode("utf-8")).hexdigest(),
        "coverage": effective_coverage,
        "source_style_evidence": source_style_evidence,
        "issues": issues,
    }


def broadcast_readable_script_issues(
    production_config: Mapping[str, object],
    screenplay_units: Mapping[str, object],
    characters: Mapping[str, object],
    panel_cast: Mapping[str, object],
    reaction_segments: Mapping[str, object],
    presentation_plan: Mapping[str, object],
    output_profile: Mapping[str, object],
    output_profile_sha256: str,
    readable_script: str,
) -> list[ValidationIssue]:
    """GATE-08에서 Canonical Readable Artifact를 현재 입력과 대조한다."""
    report = build_broadcast_readable_report(
        production_config,
        screenplay_units,
        characters,
        panel_cast,
        reaction_segments,
        presentation_plan,
        output_profile,
        output_profile_sha256,
        readable_script,
    )
    raw_issues = report["issues"]
    return list(raw_issues) if isinstance(raw_issues, list) else []


def validate_broadcast_readable_report(
    report: Mapping[str, object],
    production_config: Mapping[str, object],
    screenplay_units: Mapping[str, object],
    characters: Mapping[str, object],
    panel_cast: Mapping[str, object],
    reaction_segments: Mapping[str, object],
    presentation_plan: Mapping[str, object],
    output_profile: Mapping[str, object],
    output_profile_sha256: str,
    readable_script: str,
) -> list[ValidationIssue]:
    """GATE-09에서 QA Report를 현재 입력과 재구성해 stale 위조를 차단한다."""
    expected = build_broadcast_readable_report(
        production_config,
        screenplay_units,
        characters,
        panel_cast,
        reaction_segments,
        presentation_plan,
        output_profile,
        output_profile_sha256,
        readable_script,
    )
    expected_issues = expected["issues"]
    issues = list(expected_issues) if isinstance(expected_issues, list) else []
    if dict(report) != expected:
        issues.append(
            readable_issue(
                "BROADCAST_READABLE_REPORT_STALE",
                "Readable QA Report가 현재 Canonical 입력·출력 Hash와 다릅니다.",
                READABLE_REPORT_PATH,
                {
                    "expected_report_sha256": document_sha256(expected),
                    "actual_report_sha256": document_sha256(report),
                },
            )
        )
    return issues


def production_broadcast_readable_copy_issues(
    readable_script: str | None,
    production_readable_script: str | None,
) -> list[ValidationIssue]:
    """GATE-13에서 Production Copy의 byte 동일성을 확인한다."""
    if (
        readable_script is not None
        and readable_script.strip()
        and production_readable_script == readable_script
    ):
        return []
    return [
        readable_issue(
            "PRODUCTION_BROADCAST_READABLE_COPY_MISMATCH",
            "Production 사람용 Broadcast가 검증된 Canonical Artifact와 다릅니다.",
            PRODUCTION_READABLE_ARTIFACT_PATH,
            {},
        )
    ]


def production_readable_deliverable_record(
    production_readable_script: str,
    source_report_sha256: str,
    profile_id: str,
    profile_version: str,
) -> dict[str, str]:
    """실제 Production Copy Byte와 Report Hash를 Manifest Record로 만든다."""
    return {
        "artifact_name": "production_broadcast_readable_script",
        "path": PRODUCTION_READABLE_ARTIFACT_PATH,
        "sha256": sha256(production_readable_script.encode("utf-8")).hexdigest(),
        "source_report_sha256": source_report_sha256,
        "profile_id": profile_id,
        "profile_version": profile_version,
    }


def production_readable_deliverable_issues(
    production_manifest: Mapping[str, object] | None,
    readable_script: str | None,
    production_readable_script: str | None,
    source_report_sha256: str,
    profile_id: str,
    profile_version: str,
) -> list[ValidationIssue]:
    """Manifest의 v2 Readable 경로·실제 Copy Hash·Report Hash를 검증한다."""
    issues = production_broadcast_readable_copy_issues(
        readable_script,
        production_readable_script,
    )
    if production_manifest is None:
        return [
            *issues,
            readable_issue(
                "PRODUCTION_READABLE_DELIVERABLE_MISSING",
                "Production Manifest에 v2 Readable Deliverable이 없습니다.",
                PRODUCTION_MANIFEST_PATH,
                {},
            ),
        ]
    deliverables = production_manifest.get("deliverables")
    matches = (
        [
            item
            for item in deliverables
            if isinstance(item, Mapping)
            and item.get("artifact_name")
            == "production_broadcast_readable_script"
        ]
        if isinstance(deliverables, list)
        else []
    )
    if production_readable_script is None or len(matches) != 1:
        issues.append(
            readable_issue(
                "PRODUCTION_READABLE_DELIVERABLE_MISSING",
                "Production Manifest의 v2 Readable Deliverable은 정확히 하나여야 합니다.",
                PRODUCTION_MANIFEST_PATH,
                {"matching_deliverable_count": len(matches)},
            )
        )
        return issues
    expected = production_readable_deliverable_record(
        production_readable_script,
        source_report_sha256,
        profile_id,
        profile_version,
    )
    actual = dict(matches[0])
    if actual != expected:
        issues.append(
            readable_issue(
                "PRODUCTION_READABLE_DELIVERABLE_STALE",
                "Production Manifest의 v2 Readable Path 또는 Hash 결속이 현재 파일과 다릅니다.",
                PRODUCTION_MANIFEST_PATH,
                {"expected": expected, "actual": actual},
            )
        )
    return issues
