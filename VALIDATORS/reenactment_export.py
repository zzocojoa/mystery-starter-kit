"""재연극 Markdown의 Unit 결속, 의미 Coverage와 Report 신선도를 검증한다."""

import re
from collections import Counter
from collections.abc import Mapping, Sequence
from hashlib import sha256
from typing import NotRequired, TypedDict, cast

from RUNTIME.screenplay_renderers import (
    UNIT_LAYER_BY_TYPE,
    characters_by_id,
    markdown_cell,
    reenactment_unit_text,
    render_broadcast_master,
    render_context_value,
    render_drama_layer,
    render_narration_layer,
    render_panel_layer,
    render_reenactment_character_script,
)
from VALIDATORS.candidate_evaluation import document_sha256
from VALIDATORS.crime_event import CRIME_TRACE_BLOCK, segment_trace_blocks
from VALIDATORS.exceptions import ConfigurationError
from VALIDATORS.models import Severity, ValidationIssue
from VALIDATORS.presentation_validation import parse_script_segments
from VALIDATORS.reenactment_runtime import reenactment_runtime_status
from VALIDATORS.screenplay_units import (
    validate_screenplay_unit_references,
    validate_screenplay_units,
)

REPORT_ARTIFACT = "08_QA/reenactment_export_report.json"
EXPORT_ARTIFACT = "07_SCRIPT/reenactment_character_script.md"
SPECIAL_UNIT_TYPES = frozenset(
    {
        "NARRATION",
        "INNER_MONOLOGUE",
        "HALLUCINATION",
        "MESSAGE",
        "CHAT",
        "NOTE",
        "RECORDING",
        "SCREEN_TEXT",
    }
)
PANEL_MARKER = re.compile(r"\[(?:PANEL|EXPERT|AUDIENCE)-[A-Z0-9_-]+\]")
UNIT_TRACE_MARKER = re.compile(
    r"<!-- UNIT:(?P<unit_id>UNIT-[A-Z0-9_-]+)(?: (?P<fields>.*?))? -->"
)
UNIT_TRACE_FIELD = re.compile(
    r"(?P<label>FACT|CLUE|EVENT|HARM|DEV|REVEAL):(?P<values>[^ ]+)"
)
REFERENCE_TRACE_LABELS = {
    "fact_ids": "FACT",
    "clue_ids": "CLUE",
    "crime_event_ids": "EVENT",
    "harm_ids": "HARM",
    "development_function_ids": "DEV",
    "reveal_target_ids": "REVEAL",
}


class ScreenplayDerivedOutputs(TypedDict):
    """현재 Screenplay 입력에서 파생된 모든 가시 Script Artifact."""

    drama_script: str
    narration_script: str
    panel_reaction_script: str
    draft_script: str
    final_script: str
    reenactment_character_script: str
    expert_analysis_script: NotRequired[str]


def export_issue(
    severity: Severity,
    code: str,
    message: str,
    artifact: str,
    context: Mapping[str, object],
) -> ValidationIssue:
    """재연극 Export 문제를 공통 Issue 형식으로 만든다."""
    return ValidationIssue(
        severity=severity,
        code=code,
        message=message,
        artifact=artifact,
        context=dict(context),
    )


def records(value: object) -> list[Mapping[str, object]]:
    """객체 배열에서 의미 검증 가능한 항목만 반환한다."""
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        return []
    return [item for item in value if isinstance(item, Mapping)]


def strings(value: object) -> list[str]:
    """문자열 배열에서 문자열 항목만 반환한다."""
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        return []
    return [item for item in value if isinstance(item, str)]


def ordered_unique(values: Sequence[str]) -> list[str]:
    """최초 등장 순서로 문자열 중복을 제거한다."""
    result: list[str] = []
    for value in values:
        if value not in result:
            result.append(value)
    return result


def duplicate_values(values: Sequence[str]) -> list[str]:
    """두 번 이상 나타난 문자열을 최초 등장 순서로 반환한다."""
    counts = Counter(values)
    return ordered_unique([value for value in values if counts[value] > 1])


def screenplay_scenes(screenplay_units: Mapping[str, object]) -> list[Mapping[str, object]]:
    """Screenplay Scene 배열을 입력 순서로 반환한다."""
    return records(screenplay_units.get("scenes"))


def scene_units(scene: Mapping[str, object]) -> list[Mapping[str, object]]:
    """한 Scene의 Unit 배열을 입력 순서로 반환한다."""
    return records(scene.get("units"))


def included_unit_types(output_profile: Mapping[str, object]) -> list[str]:
    """Output Profile이 포함하는 Unit 유형을 선언 순서로 반환한다."""
    filter_contract = output_profile.get("filter_contract")
    if not isinstance(filter_contract, Mapping):
        return []
    return strings(filter_contract.get("included_unit_types"))


def excluded_unit_types(output_profile: Mapping[str, object]) -> list[str]:
    """Output Profile이 제외하는 Unit 유형을 선언 순서로 반환한다."""
    filter_contract = output_profile.get("filter_contract")
    if not isinstance(filter_contract, Mapping):
        return []
    return strings(filter_contract.get("excluded_unit_types"))


def included_units(
    screenplay_units: Mapping[str, object],
    output_profile: Mapping[str, object],
) -> list[Mapping[str, object]]:
    """Profile이 포함한 Layer와 Unit 유형을 Scene·Unit 순서로 반환한다."""
    filter_contract = output_profile.get("filter_contract")
    included_layers = (
        set(strings(filter_contract.get("included_layers")))
        if isinstance(filter_contract, Mapping)
        else set()
    )
    excluded_layers = (
        set(strings(filter_contract.get("excluded_layers")))
        if isinstance(filter_contract, Mapping)
        else set()
    )
    included = set(included_unit_types(output_profile))
    excluded = set(excluded_unit_types(output_profile))
    return [
        unit
        for scene in screenplay_scenes(screenplay_units)
        for unit in scene_units(scene)
        if unit.get("type") in included
        and unit.get("type") not in excluded
        and UNIT_LAYER_BY_TYPE.get(cast(str, unit.get("type"))) in included_layers
        and UNIT_LAYER_BY_TYPE.get(cast(str, unit.get("type"))) not in excluded_layers
    ]


def input_artifact_hashes(
    production_config: Mapping[str, object],
    screenplay_units: Mapping[str, object],
    facts: Mapping[str, object],
    characters: Mapping[str, object],
    relationships: Mapping[str, object],
    crime_event_contract: Mapping[str, object],
    clue_matrix: Mapping[str, object],
    output_profile: Mapping[str, object],
    presentation_plan: Mapping[str, object],
    reaction_segments: Mapping[str, object],
) -> dict[str, str]:
    """Report 신선도를 결속할 Canonical JSON 입력 Hash를 만든다."""
    return {
        "production_config": document_sha256(production_config),
        "screenplay_units": document_sha256(screenplay_units),
        "facts": document_sha256(facts),
        "characters": document_sha256(characters),
        "relationships": document_sha256(relationships),
        "crime_event_contract": document_sha256(crime_event_contract),
        "clue_matrix": document_sha256(clue_matrix),
        "reenactment_output_profile": document_sha256(output_profile),
        "presentation_plan": document_sha256(presentation_plan),
        "reaction_segments": document_sha256(reaction_segments),
    }


def output_artifact_hashes(outputs: ScreenplayDerivedOutputs) -> dict[str, str]:
    """모든 결정론적 Layer·Master·Export의 실제 Byte Hash를 만든다."""
    return {
        "drama_script": sha256(outputs["drama_script"].encode("utf-8")).hexdigest(),
        "narration_script": sha256(
            outputs["narration_script"].encode("utf-8")
        ).hexdigest(),
        "panel_reaction_script": sha256(
            outputs["panel_reaction_script"].encode("utf-8")
        ).hexdigest(),
        "draft_script": sha256(outputs["draft_script"].encode("utf-8")).hexdigest(),
        "final_script": sha256(outputs["final_script"].encode("utf-8")).hexdigest(),
        "reenactment_character_script": sha256(
            outputs["reenactment_character_script"].encode("utf-8")
        ).hexdigest(),
    }


def coverage(
    expected_ids: Sequence[str],
    rendered_occurrences: Sequence[str],
) -> dict[str, object]:
    """예상·렌더 ID의 누락과 중복을 공통 Coverage 형식으로 만든다."""
    expected = ordered_unique(list(expected_ids))
    rendered = ordered_unique(list(rendered_occurrences))
    return {
        "expected_ids": expected,
        "rendered_ids": rendered,
        "missing_ids": [item for item in expected if item not in rendered],
        "duplicate_ids": duplicate_values(list(rendered_occurrences)),
    }


def character_map_or_empty(
    characters: Mapping[str, object],
) -> tuple[dict[str, Mapping[str, object]], list[ValidationIssue]]:
    """Canonical Cast를 해석하고 구성 오류를 Report Issue로 변환한다."""
    try:
        return characters_by_id(characters), []
    except ConfigurationError as error:
        return {}, [
            export_issue(
                "ERROR",
                "REENACTMENT_CAST_REQUIRED",
                "Canonical Characters에서 재연극 Cast를 만들 수 없습니다.",
                EXPORT_ARTIFACT,
                {"detail": str(error)},
            )
        ]


def rendered_unit_evidence(
    expected_units: Sequence[Mapping[str, object]],
    character_map: Mapping[str, Mapping[str, object]],
    output_profile: Mapping[str, object],
    markdown: str,
) -> tuple[dict[str, object], list[str], list[ValidationIssue]]:
    """가시 Unit Block을 원본 Unit ID와 순서에 결정론적으로 대응한다."""
    issues: list[ValidationIssue] = []
    expected_ids: list[str] = []
    blocks_by_value: dict[str, list[str]] = {}
    types_by_id: dict[str, str] = {}
    for unit in expected_units:
        unit_id = unit.get("unit_id")
        unit_type = unit.get("type")
        if not isinstance(unit_id, str) or not isinstance(unit_type, str):
            continue
        expected_ids.append(unit_id)
        types_by_id[unit_id] = unit_type
        try:
            block = reenactment_unit_text(unit, character_map, output_profile)
        except ConfigurationError as error:
            code = str(error).split(":", maxsplit=1)[0]
            issues.append(
                export_issue(
                    "ERROR",
                    code,
                    "Unit을 Output Profile에 따라 렌더링할 수 없습니다.",
                    EXPORT_ARTIFACT,
                    {"unit_id": unit_id, "detail": str(error)},
                )
            )
            continue
        blocks_by_value.setdefault(block, []).append(unit_id)

    positioned_ids: list[tuple[int, str]] = []
    rendered_occurrences: list[str] = []
    duplicate_ids: list[str] = []
    for block, unit_ids in blocks_by_value.items():
        positions: list[int] = []
        cursor = 0
        while True:
            position = markdown.find(block, cursor)
            if position < 0:
                break
            positions.append(position)
            cursor = position + len(block)
        for unit_id, position in zip(unit_ids, positions, strict=False):
            rendered_occurrences.append(unit_id)
            positioned_ids.append((position, unit_id))
        if len(positions) > len(unit_ids):
            duplicate_ids.append(unit_ids[0])

    rendered_order = [unit_id for _position, unit_id in sorted(positioned_ids)]
    rendered_ids = ordered_unique(rendered_occurrences)
    missing_ids = [unit_id for unit_id in expected_ids if unit_id not in rendered_ids]
    expected_present_order = [unit_id for unit_id in expected_ids if unit_id in rendered_ids]
    if rendered_order != expected_present_order:
        issues.append(
            export_issue(
                "ERROR",
                "REENACTMENT_UNIT_ORDER_INVALID",
                "재연극 Markdown의 Unit 순서가 Screenplay Unit 순서와 다릅니다.",
                EXPORT_ARTIFACT,
                {
                    "expected_order": expected_present_order,
                    "rendered_order": rendered_order,
                },
            )
        )
    lost_special_ids = [
        unit_id for unit_id in missing_ids if types_by_id.get(unit_id) in SPECIAL_UNIT_TYPES
    ]
    if lost_special_ids:
        issues.append(
            export_issue(
                "ERROR",
                "SPECIAL_UNIT_TYPE_LOST",
                "재연극 Markdown에서 특수 Unit 유형이 유실되었습니다.",
                EXPORT_ARTIFACT,
                {"unit_ids": lost_special_ids},
            )
        )
    unit_coverage: dict[str, object] = {
        "expected_ids": expected_ids,
        "rendered_ids": rendered_ids,
        "missing_ids": missing_ids,
        "duplicate_ids": ordered_unique(duplicate_ids),
        "rendered_order": rendered_order,
    }
    return unit_coverage, rendered_order, issues


def scene_coverage_evidence(
    screenplay_units: Mapping[str, object],
    output_profile: Mapping[str, object],
    markdown: str,
) -> tuple[dict[str, object], list[ValidationIssue]]:
    """Scene Heading의 coverage, 중복과 순서를 검증한다."""
    document_contract = output_profile.get("document_contract")
    heading_template = (
        document_contract.get("scene_heading_template")
        if isinstance(document_contract, Mapping)
        else None
    )
    expected_ids: list[str] = []
    positions: list[tuple[int, str]] = []
    rendered_occurrences: list[str] = []
    if not isinstance(heading_template, str):
        return coverage([], []), [
            export_issue(
                "ERROR",
                "REENACTMENT_OUTPUT_PROFILE_INVALID",
                "Scene Heading Template가 없습니다.",
                EXPORT_ARTIFACT,
                {},
            )
        ]
    for scene in screenplay_scenes(screenplay_units):
        scene_id = scene.get("scene_id")
        order = scene.get("order")
        title = scene.get("title")
        if (
            not isinstance(scene_id, str)
            or not isinstance(order, int)
            or not isinstance(title, str)
        ):
            continue
        expected_ids.append(scene_id)
        heading = heading_template.format(order=order, title=title)
        count = markdown.count(heading)
        rendered_occurrences.extend([scene_id] * count)
        position = markdown.find(heading)
        if position >= 0:
            positions.append((position, scene_id))
    evidence = coverage(expected_ids, rendered_occurrences)
    issues: list[ValidationIssue] = []
    rendered_order = [scene_id for _position, scene_id in sorted(positions)]
    expected_present = [scene_id for scene_id in expected_ids if scene_id in rendered_order]
    if rendered_order != expected_present or evidence["missing_ids"] or evidence["duplicate_ids"]:
        issues.append(
            export_issue(
                "ERROR",
                "REENACTMENT_SCENE_SEQUENCE_INVALID",
                "재연극 Markdown의 Scene Heading coverage 또는 순서가 올바르지 않습니다.",
                EXPORT_ARTIFACT,
                {"rendered_order": rendered_order, **evidence},
            )
        )
    return evidence, issues


def cast_and_speaker_evidence(
    expected_units: Sequence[Mapping[str, object]],
    character_map: Mapping[str, Mapping[str, object]],
    output_profile: Mapping[str, object],
    markdown: str,
) -> tuple[dict[str, object], list[ValidationIssue]]:
    """Cast 표와 Unit speaker_id의 Canonical Character 결속을 검증한다."""
    speaker_ids = ordered_unique(
        [
            speaker_id
            for unit in expected_units
            if isinstance((speaker_id := unit.get("speaker_id")), str)
        ]
    )
    unknown = [speaker_id for speaker_id in speaker_ids if speaker_id not in character_map]
    resolved = [speaker_id for speaker_id in speaker_ids if speaker_id in character_map]
    issues: list[ValidationIssue] = []
    if unknown:
        issues.append(
            export_issue(
                "ERROR",
                "REENACTMENT_SPEAKER_UNKNOWN",
                "Unit speaker_id가 Canonical Characters에 없습니다.",
                EXPORT_ARTIFACT,
                {"speaker_ids": unknown},
            )
        )
    document_contract = output_profile.get("document_contract")
    headings = (
        strings(document_contract.get("required_headings"))
        if isinstance(document_contract, Mapping)
        else []
    )
    cast_heading = f"## {headings[1]}" if len(headings) == 3 else ""
    scene_heading = f"## {headings[2]}" if len(headings) == 3 else ""
    cast_start = markdown.find(cast_heading) if cast_heading else -1
    cast_end = markdown.find(scene_heading) if scene_heading else -1
    cast_section = (
        markdown[cast_start:cast_end]
        if cast_start >= 0 and cast_end > cast_start
        else ""
    )
    missing_cast_ids = [
        character_id
        for character_id, character in character_map.items()
        if not isinstance(character.get("name"), str)
        or cast_section.count(f"| {markdown_cell(cast(str, character['name']))} |") != 1
    ]
    if not cast_section or missing_cast_ids:
        issues.append(
            export_issue(
                "ERROR",
                "REENACTMENT_CAST_REQUIRED",
                "Canonical Character를 한 번씩 표시한 Cast 표가 필요합니다.",
                EXPORT_ARTIFACT,
                {"missing_character_ids": missing_cast_ids},
            )
        )
    return {
        "resolved_character_ids": resolved,
        "unknown_speaker_ids": unknown,
    }, issues


def document_structure_issues(
    output_profile: Mapping[str, object],
    markdown: str,
) -> list[ValidationIssue]:
    """Profile 필수 Heading이 정확히 한 번 선언 순서로 나타나는지 검증한다."""
    document_contract = output_profile.get("document_contract")
    headings = (
        strings(document_contract.get("required_headings"))
        if isinstance(document_contract, Mapping)
        else []
    )
    markers = [f"## {heading}" for heading in headings]
    positions = [markdown.find(marker) for marker in markers]
    invalid = (
        not markers
        or any(position < 0 for position in positions)
        or positions != sorted(positions)
        or any(markdown.count(marker) != 1 for marker in markers)
    )
    if not invalid:
        return []
    return [
        export_issue(
            "ERROR",
            "REENACTMENT_REQUIRED_HEADING_MISMATCH",
            "재연극 문서의 필수 Heading이 Output Profile 선언과 다릅니다.",
            EXPORT_ARTIFACT,
            {"required_headings": headings, "positions": positions},
        )
    ]


def context_issues(
    screenplay_units: Mapping[str, object],
    output_profile: Mapping[str, object],
    markdown: str,
) -> list[ValidationIssue]:
    """Profile이 요구한 상세 Scene Context가 각 Heading 아래에 있는지 검증한다."""
    document_contract = output_profile.get("document_contract")
    fields = (
        strings(document_contract.get("scene_context_fields"))
        if isinstance(document_contract, Mapping)
        else []
    )
    missing: list[dict[str, object]] = []
    for scene in screenplay_scenes(screenplay_units):
        scene_id = scene.get("scene_id")
        context = scene.get("context")
        if not isinstance(context, Mapping):
            missing.append({"scene_id": scene_id, "field": "context"})
            continue
        for field in fields:
            try:
                value = render_context_value(field, context.get(field))
            except ConfigurationError:
                missing.append({"scene_id": scene_id, "field": field})
                continue
            if value not in markdown:
                missing.append({"scene_id": scene_id, "field": field})
    if not missing:
        return []
    return [
        export_issue(
            "ERROR",
            "REENACTMENT_CONTEXT_MISSING",
            "Output Profile이 요구한 Scene Context가 누락되었습니다.",
            EXPORT_ARTIFACT,
            {"missing": missing},
        )
    ]


def forbidden_content_issues(
    screenplay_units: Mapping[str, object],
    output_profile: Mapping[str, object],
    markdown: str,
) -> list[ValidationIssue]:
    """Panel·내부 Marker와 Original Fiction 불명확 표기를 차단한다."""
    filter_contract = output_profile.get("filter_contract")
    excluded_layers = (
        strings(filter_contract.get("excluded_layers"))
        if isinstance(filter_contract, Mapping)
        else []
    )
    forbidden_markers = (
        strings(filter_contract.get("forbidden_internal_markers"))
        if isinstance(filter_contract, Mapping)
        else []
    )
    uncertainty_markers = (
        strings(filter_contract.get("original_fiction_forbidden_uncertainty_markers"))
        if isinstance(filter_contract, Mapping)
        else []
    )
    issues: list[ValidationIssue] = []
    leaked_layers = [layer for layer in excluded_layers if layer in markdown]
    if leaked_layers or PANEL_MARKER.search(markdown) is not None:
        issues.append(
            export_issue(
                "ERROR",
                "PANEL_CONTENT_IN_REENACTMENT_EXPORT",
                "재연극 Export에 제외된 방송 Layer 내용이 포함되었습니다.",
                EXPORT_ARTIFACT,
                {"layer_markers": leaked_layers},
            )
        )
    leaked_markers = [marker for marker in forbidden_markers if marker in markdown]
    if leaked_markers:
        issues.append(
            export_issue(
                "ERROR",
                "INTERNAL_MARKER_LEAKED",
                "재연극 Export에 내부 추적 Marker가 노출되었습니다.",
                EXPORT_ARTIFACT,
                {"markers": leaked_markers},
            )
        )
    if screenplay_units.get("source_truth_classification") == "ORIGINAL_FICTION":
        unclear = [marker for marker in uncertainty_markers if marker in markdown]
        if "- 작품 구분: ORIGINAL_FICTION" not in markdown or unclear:
            issues.append(
                export_issue(
                    "ERROR",
                    "ORIGINAL_FICTION_UNCLEAR_MARKER",
                    "Original Fiction 표시는 명확해야 하며 화자 불명확 Marker가 없어야 합니다.",
                    EXPORT_ARTIFACT,
                    {"uncertainty_markers": unclear},
                )
            )
    return issues


def unit_reference_ids(
    expected_units: Sequence[Mapping[str, object]],
    field: str,
) -> list[str]:
    """실제 포함 Unit의 구조화 Reference ID를 Unit 순서로 반환한다."""
    values: list[str] = []
    for unit in expected_units:
        references = unit.get("references")
        if isinstance(references, Mapping):
            values.extend(strings(references.get(field)))
    return values


def harm_coverage_evidence(
    expected_units: Sequence[Mapping[str, object]],
    crime_event_contract: Mapping[str, object],
) -> tuple[dict[str, object], list[ValidationIssue]]:
    """Contract의 모든 Harm이 가시 Unit Reference로 실현됐는지 검증한다."""
    expected_ids = strings(crime_event_contract.get("harm_ids"))
    rendered_occurrences = unit_reference_ids(expected_units, "harm_ids")
    rendered_ids = ordered_unique(rendered_occurrences)
    evidence: dict[str, object] = {
        "expected_ids": ordered_unique(expected_ids),
        "rendered_ids": rendered_ids,
        "missing_ids": [harm_id for harm_id in expected_ids if harm_id not in rendered_ids],
        "duplicate_ids": duplicate_values(expected_ids),
    }
    event_id = crime_event_contract.get("event_id")
    invalid_units: list[str] = []
    for unit in expected_units:
        references = unit.get("references")
        if not isinstance(references, Mapping):
            continue
        event_ids = strings(references.get("crime_event_ids"))
        harm_ids = strings(references.get("harm_ids"))
        valid_binding = (
            (not event_ids and not harm_ids)
            or (
                isinstance(event_id, str)
                and event_id in event_ids
                and bool(harm_ids)
                and set(harm_ids).issubset(set(expected_ids))
            )
        )
        if not valid_binding and isinstance(unit.get("unit_id"), str):
            invalid_units.append(cast(str, unit["unit_id"]))
    if not evidence["missing_ids"] and not invalid_units:
        return evidence, []
    return evidence, [
        export_issue(
            "ERROR",
            "HARM_REALIZATION_MISSING",
            "Crime Event와 모든 Harm은 같은 가시 Unit Reference에 결속돼야 합니다.",
            EXPORT_ARTIFACT,
            {"missing_harm_ids": evidence["missing_ids"], "invalid_unit_ids": invalid_units},
        )
    ]


def clue_reveal_evidence(
    screenplay_units: Mapping[str, object],
    expected_units: Sequence[Mapping[str, object]],
    clue_matrix: Mapping[str, object],
) -> tuple[dict[str, object], list[ValidationIssue]]:
    """Seeded Clue가 선행·Reveal Scene과 회고적 의미에 결속됐는지 검증한다."""
    clues = records(clue_matrix.get("clues"))
    expected_ids = [
        cast(str, clue["clue_id"])
        for clue in clues
        if isinstance(clue.get("clue_id"), str)
    ]
    rendered_ids = ordered_unique(unit_reference_ids(expected_units, "clue_ids"))
    evidence: dict[str, object] = {
        "expected_ids": ordered_unique(expected_ids),
        "rendered_ids": rendered_ids,
        "missing_ids": [clue_id for clue_id in expected_ids if clue_id not in rendered_ids],
        "duplicate_ids": duplicate_values(expected_ids),
    }
    scene_map = {
        scene_id: scene
        for scene in screenplay_scenes(screenplay_units)
        if isinstance((scene_id := scene.get("scene_id")), str)
    }
    clue_scene_ids: dict[str, list[str]] = {}
    for scene_id, scene in scene_map.items():
        for unit in scene_units(scene):
            references = unit.get("references")
            if not isinstance(references, Mapping):
                continue
            for clue_id in strings(references.get("clue_ids")):
                clue_scene_ids.setdefault(clue_id, []).append(scene_id)
    issues: list[ValidationIssue] = []
    for clue in clues:
        if clue.get("reveal_mode") != "SEEDED_REINTERPRETATION":
            continue
        raw_clue_id = clue.get("clue_id")
        first_scene_id = clue.get("first_seen_scene_id")
        reveal_scene_id = clue.get("reveal_scene_id")
        referenced_scenes = (
            clue_scene_ids.get(raw_clue_id, []) if isinstance(raw_clue_id, str) else []
        )
        if first_scene_id not in referenced_scenes or reveal_scene_id not in referenced_scenes:
            issues.append(
                export_issue(
                    "ERROR",
                    "REVEAL_WITHOUT_PRIOR_SEED",
                    "Seeded Clue는 선행 Scene과 Reveal Scene의 가시 Unit에 모두 필요합니다.",
                    EXPORT_ARTIFACT,
                    {
                        "clue_id": raw_clue_id,
                        "first_seen_scene_id": first_scene_id,
                        "reveal_scene_id": reveal_scene_id,
                        "referenced_scene_ids": ordered_unique(referenced_scenes),
                    },
                )
            )
        reveal_scene = scene_map.get(reveal_scene_id) if isinstance(reveal_scene_id, str) else None
        context = reveal_scene.get("context") if isinstance(reveal_scene, Mapping) else None
        retrospective = (
            context.get("retrospective_meaning") if isinstance(context, Mapping) else None
        )
        if not isinstance(retrospective, str) or not retrospective.strip():
            issues.append(
                export_issue(
                    "ERROR",
                    "RETROSPECTIVE_MEANING_MISSING",
                    "Clue Reveal Scene에는 첫 의미를 바꾸는 회고적 의미가 필요합니다.",
                    EXPORT_ARTIFACT,
                    {"clue_id": raw_clue_id, "reveal_scene_id": reveal_scene_id},
                )
            )
    return evidence, issues


def reconstruction_evidence(
    screenplay_units: Mapping[str, object],
) -> tuple[list[dict[str, object]], list[ValidationIssue]]:
    """Reconstruction Scene 원본과 exact repetition 결속 상태를 만든다."""
    screenplay_issues = validate_screenplay_units(screenplay_units)
    relevant = [
        issue
        for issue in screenplay_issues
        if issue["code"]
        in {"RECONSTRUCTION_REFERENCE_INVALID", "RECONSTRUCTION_REPETITION_MISMATCH"}
    ]
    evidence: list[dict[str, object]] = []
    for scene in screenplay_scenes(screenplay_units):
        if scene.get("time_layer") != "RECONSTRUCTION":
            continue
        scene_id = scene.get("scene_id")
        source_id = scene.get("reconstruction_of_scene_id")
        invalid = any(issue["context"].get("scene_id") == scene_id for issue in relevant)
        if isinstance(scene_id, str) and isinstance(source_id, str):
            evidence.append(
                {
                    "scene_id": scene_id,
                    "reconstruction_of_scene_id": source_id,
                    "status": "INVALID" if invalid else "VALID",
                }
            )
    return evidence, relevant


def type_coverage_evidence(
    expected_units: Sequence[Mapping[str, object]],
    output_profile: Mapping[str, object],
) -> dict[str, object]:
    """Profile 포함·제외 유형과 실제 원본 Unit 유형을 기록한다."""
    return {
        "included_unit_types": included_unit_types(output_profile),
        "excluded_unit_types": excluded_unit_types(output_profile),
        "rendered_unit_types": ordered_unique(
            [
                cast(str, unit["type"])
                for unit in expected_units
                if isinstance(unit.get("type"), str)
            ]
        ),
    }


def expected_unit_trace_fields(unit: Mapping[str, object]) -> dict[str, set[str]]:
    """한 Unit의 구조화 Reference를 방송 Trace field 집합으로 변환한다."""
    references = unit.get("references")
    if not isinstance(references, Mapping):
        return {}
    return {
        label: set(strings(references.get(field)))
        for field, label in REFERENCE_TRACE_LABELS.items()
        if strings(references.get(field))
    }


def parsed_unit_traces(body: str) -> list[tuple[str, dict[str, set[str]]]]:
    """방송 Segment의 CORE Unit Trace Marker를 순서대로 읽는다."""
    result: list[tuple[str, dict[str, set[str]]]] = []
    for marker in UNIT_TRACE_MARKER.finditer(body):
        raw_fields = marker.group("fields") or ""
        fields = {
            match.group("label"): {
                value for value in match.group("values").split(",") if value
            }
            for match in UNIT_TRACE_FIELD.finditer(raw_fields)
        }
        result.append((marker.group("unit_id"), fields))
    return result


def expected_crime_trace_fields(
    units: Sequence[Mapping[str, object]],
    crime_event_contract: Mapping[str, object],
) -> list[dict[str, set[str]]]:
    """Segment Unit References에서 기대하는 CRIME_TRACE Block 하나를 계산한다."""
    event_ids: set[str] = set()
    harm_ids: set[str] = set()
    function_ids: set[str] = set()
    for unit in units:
        references = unit.get("references")
        if not isinstance(references, Mapping):
            continue
        event_ids.update(strings(references.get("crime_event_ids")))
        harm_ids.update(strings(references.get("harm_ids")))
        function_ids.update(strings(references.get("development_function_ids")))
    if not event_ids and not harm_ids and not function_ids:
        return []
    fields: dict[str, set[str]] = {}
    if event_ids:
        fields["EVENT"] = event_ids
    contract_event_id = crime_event_contract.get("event_id")
    action_type = crime_event_contract.get("core_action_type")
    if (
        isinstance(contract_event_id, str)
        and contract_event_id in event_ids
        and isinstance(action_type, str)
    ):
        fields["ACTION"] = {action_type}
    if harm_ids:
        fields["HARM"] = harm_ids
    if function_ids:
        fields["DEV"] = function_ids
    return [fields]


def broadcast_trace_issues(
    screenplay_units: Mapping[str, object],
    presentation_plan: Mapping[str, object],
    crime_event_contract: Mapping[str, object],
    broadcast_master: str,
) -> list[ValidationIssue]:
    """Broadcast Segment의 Unit·Crime Trace를 실제 가시 Unit References와 비교한다."""
    parsed_segments, malformed = parse_script_segments(broadcast_master)
    planned_segments = records(presentation_plan.get("segments"))
    planned_ids = [
        cast(str, segment["segment_id"])
        for segment in planned_segments
        if isinstance(segment.get("segment_id"), str)
    ]
    parsed_ids = [segment["segment_id"] for segment in parsed_segments]
    issues: list[ValidationIssue] = []
    if malformed or parsed_ids != planned_ids or len(set(parsed_ids)) != len(parsed_ids):
        issues.append(
            export_issue(
                "ERROR",
                "REENACTMENT_UNIT_ORDER_INVALID",
                "Broadcast Master Segment가 Presentation 순서·coverage와 다릅니다.",
                "07_SCRIPT/final_script.md",
                {"planned_segment_ids": planned_ids, "actual_segment_ids": parsed_ids},
            )
        )
    units_by_segment: dict[str, list[Mapping[str, object]]] = {}
    for scene in screenplay_scenes(screenplay_units):
        for unit in scene_units(scene):
            segment_id = unit.get("segment_id")
            if isinstance(segment_id, str):
                units_by_segment.setdefault(segment_id, []).append(unit)
    mismatches: list[dict[str, object]] = []
    for segment in parsed_segments:
        segment_id = segment["segment_id"]
        expected_units = units_by_segment.get(segment_id, [])
        actual_unit_traces = parsed_unit_traces(segment["body"])
        expected_unit_traces = [
            (cast(str, unit["unit_id"]), expected_unit_trace_fields(unit))
            for unit in expected_units
            if isinstance(unit.get("unit_id"), str)
        ]
        expected_crime = expected_crime_trace_fields(expected_units, crime_event_contract)
        actual_crime = segment_trace_blocks(segment)
        visible_body = CRIME_TRACE_BLOCK.sub("", segment["body"])
        visible_body = UNIT_TRACE_MARKER.sub("", visible_body).strip()
        reasons: list[str] = []
        if actual_unit_traces != expected_unit_traces:
            reasons.append("UNIT_TRACE")
        if actual_crime != expected_crime:
            reasons.append("CRIME_TRACE")
        if (actual_unit_traces or actual_crime) and not visible_body:
            reasons.append("TRACE_WITHOUT_VISIBLE_CONTENT")
        if reasons:
            mismatches.append(
                {
                    "segment_id": segment_id,
                    "reasons": reasons,
                    "expected_unit_ids": [item[0] for item in expected_unit_traces],
                    "actual_unit_ids": [item[0] for item in actual_unit_traces],
                    "expected_crime_trace": [
                        {key: sorted(values) for key, values in fields.items()}
                        for fields in expected_crime
                    ],
                    "actual_crime_trace": [
                        {key: sorted(values) for key, values in fields.items()}
                        for fields in actual_crime
                    ],
                }
            )
    unrendered_ids = sorted(set(units_by_segment) - set(parsed_ids))
    if unrendered_ids:
        mismatches.append(
            {
                "reasons": ["UNIT_SEGMENT_MISSING"],
                "segment_ids": unrendered_ids,
            }
        )
    if mismatches:
        issues.append(
            export_issue(
                "ERROR",
                "UNIT_RENDER_MISMATCH",
                "Broadcast 내부 Trace가 실제로 렌더링한 Unit References와 다릅니다.",
                "07_SCRIPT/final_script.md",
                {"segments": mismatches},
            )
        )
    return issues


def render_mismatch_issue(
    code: str,
    artifact: str,
    expected: str,
    actual: str,
) -> ValidationIssue:
    """결정론적 기대 bytes와 실제 bytes 차이를 Hash 근거로 만든다."""
    return export_issue(
        "ERROR",
        code,
        "가시 Script가 현재 입력의 결정론적 Renderer 출력과 다릅니다.",
        artifact,
        {
            "affected_artifact": artifact,
            "expected_sha256": sha256(expected.encode("utf-8")).hexdigest(),
            "actual_sha256": sha256(actual.encode("utf-8")).hexdigest(),
        },
    )


def screenplay_derived_output_issues(
    screenplay_units: Mapping[str, object],
    presentation_plan: Mapping[str, object],
    reaction_segments: Mapping[str, object],
    crime_event_contract: Mapping[str, object],
    characters: Mapping[str, object],
    relationships: Mapping[str, object],
    output_profile: Mapping[str, object],
    outputs: ScreenplayDerivedOutputs,
) -> list[ValidationIssue]:
    """모든 Layer·Master·Export를 현재 원본 입력에서 다시 렌더링해 비교한다."""
    try:
        expected_drama = render_drama_layer(
            screenplay_units,
            presentation_plan,
            crime_event_contract,
        )
        expected_narration = render_narration_layer(
            screenplay_units,
            presentation_plan,
            crime_event_contract,
        )
        expected_panel = render_panel_layer(reaction_segments, presentation_plan)
        expected_layers = {
            "drama_script": expected_drama,
            "narration_script": expected_narration,
            "panel_reaction_script": expected_panel,
        }
        if "expert_analysis_script" in outputs:
            expected_layers["expert_analysis_script"] = outputs["expert_analysis_script"]
        expected_master = render_broadcast_master(presentation_plan, expected_layers)
        expected_reenactment = render_reenactment_character_script(
            screenplay_units,
            characters,
            relationships,
            output_profile,
        )
    except ConfigurationError as error:
        code = str(error).split(":", maxsplit=1)[0]
        return [
            export_issue(
                "ERROR",
                code,
                "현재 입력으로 모든 파생 Script를 결정론적으로 렌더링할 수 없습니다.",
                "07_SCRIPT/screenplay_units.json",
                {"detail": str(error)},
            )
        ]
    comparisons = (
        (
            "DRAMA_LAYER_RENDER_MISMATCH",
            "07_SCRIPT/drama_script.md",
            expected_drama,
            outputs["drama_script"],
        ),
        (
            "NARRATION_LAYER_RENDER_MISMATCH",
            "07_SCRIPT/narration_script.md",
            expected_narration,
            outputs["narration_script"],
        ),
        (
            "PANEL_LAYER_RENDER_MISMATCH",
            "07_SCRIPT/panel_reaction_script.md",
            expected_panel,
            outputs["panel_reaction_script"],
        ),
        (
            "BROADCAST_MASTER_RENDER_MISMATCH",
            "07_SCRIPT/draft_v01.md",
            expected_master,
            outputs["draft_script"],
        ),
        (
            "BROADCAST_MASTER_RENDER_MISMATCH",
            "07_SCRIPT/final_script.md",
            expected_master,
            outputs["final_script"],
        ),
        (
            "UNIT_RENDER_MISMATCH",
            EXPORT_ARTIFACT,
            expected_reenactment,
            outputs["reenactment_character_script"],
        ),
    )
    return [
        render_mismatch_issue(code, artifact, expected, actual)
        for code, artifact, expected, actual in comparisons
        if expected.encode("utf-8") != actual.encode("utf-8")
    ]


def deduplicate_issues(issues: Sequence[ValidationIssue]) -> list[ValidationIssue]:
    """동일 코드·Artifact·Context의 Issue를 최초 순서로 하나만 보존한다."""
    result: list[ValidationIssue] = []
    seen: set[str] = set()
    for issue in issues:
        key = document_sha256(cast(Mapping[str, object], issue))
        if key not in seen:
            seen.add(key)
            result.append(issue)
    return result


def build_reenactment_export_report(
    production_config: Mapping[str, object],
    screenplay_units: Mapping[str, object],
    facts: Mapping[str, object],
    characters: Mapping[str, object],
    relationships: Mapping[str, object],
    crime_event_contract: Mapping[str, object],
    clue_matrix: Mapping[str, object],
    output_profile: Mapping[str, object],
    output_profile_sha256: str,
    presentation_plan: Mapping[str, object],
    reaction_segments: Mapping[str, object],
    outputs: ScreenplayDerivedOutputs,
) -> dict[str, object]:
    """현재 입력·출력에서 재현 가능한 Reenactment Export Report를 만든다."""
    reenactment_markdown = outputs["reenactment_character_script"]
    broadcast_master = outputs["final_script"]
    character_map, cast_input_issues = character_map_or_empty(characters)
    expected_units = included_units(screenplay_units, output_profile)
    unit_evidence, _rendered_order, unit_issues = rendered_unit_evidence(
        expected_units,
        character_map,
        output_profile,
        reenactment_markdown,
    )
    scene_evidence, scene_issues = scene_coverage_evidence(
        screenplay_units,
        output_profile,
        reenactment_markdown,
    )
    speaker_evidence, speaker_issues = cast_and_speaker_evidence(
        expected_units,
        character_map,
        output_profile,
        reenactment_markdown,
    )
    harm_evidence, harm_issues = harm_coverage_evidence(
        expected_units,
        crime_event_contract,
    )
    clue_evidence, clue_issues = clue_reveal_evidence(
        screenplay_units,
        expected_units,
        clue_matrix,
    )
    reconstruction, reconstruction_issues = reconstruction_evidence(screenplay_units)
    runtime_evidence, runtime_issues = reenactment_runtime_status(
        production_config,
        screenplay_units,
        presentation_plan,
        output_profile,
    )
    issues = deduplicate_issues(
        [
            *cast_input_issues,
            *unit_issues,
            *scene_issues,
            *speaker_issues,
            *document_structure_issues(output_profile, reenactment_markdown),
            *context_issues(screenplay_units, output_profile, reenactment_markdown),
            *forbidden_content_issues(
                screenplay_units,
                output_profile,
                reenactment_markdown,
            ),
            *harm_issues,
            *clue_issues,
            *reconstruction_issues,
            *validate_screenplay_unit_references(
                screenplay_units,
                facts,
                clue_matrix,
                crime_event_contract,
                characters,
                presentation_plan,
            ),
            *runtime_issues,
            *broadcast_trace_issues(
                screenplay_units,
                presentation_plan,
                crime_event_contract,
                broadcast_master,
            ),
            *screenplay_derived_output_issues(
                screenplay_units,
                presentation_plan,
                reaction_segments,
                crime_event_contract,
                characters,
                relationships,
                output_profile,
                outputs,
            ),
        ]
    )
    result = (
        "MISSING"
        if not reenactment_markdown.strip()
        else "FAIL"
        if any(issue["severity"] == "ERROR" for issue in issues)
        else "NEEDS_REVIEW"
    )
    return {
        "$schema": "../../../STANDARD/schemas/reenactment_export_report.schema.json",
        "schema_family": "reenactment-export-report",
        "schema_version": "1.1.0",
        "project_id": screenplay_units.get("project_id"),
        "result": result,
        "input_artifact_hashes": input_artifact_hashes(
            production_config,
            screenplay_units,
            facts,
            characters,
            relationships,
            crime_event_contract,
            clue_matrix,
            output_profile,
            presentation_plan,
            reaction_segments,
        ),
        "output_profile": {
            "profile_id": output_profile.get("profile_id"),
            "profile_version": output_profile.get("profile_version"),
            "sha256": output_profile_sha256,
        },
        "output_markdown_sha256": sha256(reenactment_markdown.encode("utf-8")).hexdigest(),
        "output_artifact_hashes": output_artifact_hashes(outputs),
        "scene_coverage": scene_evidence,
        "unit_coverage": unit_evidence,
        "speaker_resolution": speaker_evidence,
        "type_coverage": type_coverage_evidence(expected_units, output_profile),
        "harm_coverage": harm_evidence,
        "clue_reveal_coverage": clue_evidence,
        "reconstruction_references": reconstruction,
        "runtime_status": runtime_evidence,
        "issues": issues,
    }


def validate_reenactment_export_report(
    report: Mapping[str, object],
    production_config: Mapping[str, object],
    screenplay_units: Mapping[str, object],
    facts: Mapping[str, object],
    characters: Mapping[str, object],
    relationships: Mapping[str, object],
    crime_event_contract: Mapping[str, object],
    clue_matrix: Mapping[str, object],
    output_profile: Mapping[str, object],
    output_profile_sha256: str,
    presentation_plan: Mapping[str, object],
    reaction_segments: Mapping[str, object],
    outputs: ScreenplayDerivedOutputs,
) -> list[ValidationIssue]:
    """Report를 현재 입출력에서 재구성해 Metadata-only spoof와 stale evidence를 차단한다."""
    expected = build_reenactment_export_report(
        production_config,
        screenplay_units,
        facts,
        characters,
        relationships,
        crime_event_contract,
        clue_matrix,
        output_profile,
        output_profile_sha256,
        presentation_plan,
        reaction_segments,
        outputs,
    )
    raw_issues = expected.get("issues")
    issues = [
        cast(ValidationIssue, dict(issue))
        for issue in records(raw_issues)
    ]
    if dict(report) != expected:
        issues.append(
            export_issue(
                "ERROR",
                "REENACTMENT_EXPORT_REPORT_STALE",
                "Export Report가 현재 입출력에서 결정론적으로 재구성한 Report와 다릅니다.",
                REPORT_ARTIFACT,
                {
                    "expected_report_sha256": document_sha256(expected),
                    "actual_report_sha256": document_sha256(report),
                },
            )
        )
    return deduplicate_issues(issues)
