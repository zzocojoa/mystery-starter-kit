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
    screenplay_units: Mapping[str, object],
    characters: Mapping[str, object],
    panel_cast: Mapping[str, object],
    reaction_segments: Mapping[str, object],
    presentation_plan: Mapping[str, object],
) -> dict[str, str]:
    """Readable Artifact의 모든 Canonical JSON 입력 Hash를 계산한다."""
    return {
        "screenplay_units": document_sha256(screenplay_units),
        "characters": document_sha256(characters),
        "panel_cast": document_sha256(panel_cast),
        "reaction_segments": document_sha256(reaction_segments),
        "presentation_plan": document_sha256(presentation_plan),
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


def build_broadcast_readable_report(
    screenplay_units: Mapping[str, object],
    characters: Mapping[str, object],
    panel_cast: Mapping[str, object],
    reaction_segments: Mapping[str, object],
    presentation_plan: Mapping[str, object],
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
    return {
        "$schema": "../../../STANDARD/schemas/broadcast_readable_report.schema.json",
        "schema_family": "broadcast-readable-report",
        "schema_version": "1.0.0",
        "project_id": screenplay_units.get("project_id"),
        "result": result,
        "input_artifact_hashes": readable_input_hashes(
            screenplay_units,
            characters,
            panel_cast,
            reaction_segments,
            presentation_plan,
        ),
        "output_markdown_sha256": sha256(readable_script.encode("utf-8")).hexdigest(),
        "coverage": coverage or {
            "scene_count": 0,
            "unit_count": 0,
            "character_count": 0,
            "panelist_count": 0,
            "panel_reaction_segment_count": 0,
            "panel_turn_count": 0,
            "presentation_segment_count": 0,
        },
        "issues": issues,
    }


def broadcast_readable_script_issues(
    screenplay_units: Mapping[str, object],
    characters: Mapping[str, object],
    panel_cast: Mapping[str, object],
    reaction_segments: Mapping[str, object],
    presentation_plan: Mapping[str, object],
    readable_script: str,
) -> list[ValidationIssue]:
    """GATE-08에서 Canonical Readable Artifact를 현재 입력과 대조한다."""
    report = build_broadcast_readable_report(
        screenplay_units,
        characters,
        panel_cast,
        reaction_segments,
        presentation_plan,
        readable_script,
    )
    raw_issues = report["issues"]
    return list(raw_issues) if isinstance(raw_issues, list) else []


def validate_broadcast_readable_report(
    report: Mapping[str, object],
    screenplay_units: Mapping[str, object],
    characters: Mapping[str, object],
    panel_cast: Mapping[str, object],
    reaction_segments: Mapping[str, object],
    presentation_plan: Mapping[str, object],
    readable_script: str,
) -> list[ValidationIssue]:
    """GATE-09에서 QA Report를 현재 입력과 재구성해 stale 위조를 차단한다."""
    expected = build_broadcast_readable_report(
        screenplay_units,
        characters,
        panel_cast,
        reaction_segments,
        presentation_plan,
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
