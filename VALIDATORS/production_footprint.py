"""Scene 기반 제작 규모를 결정론적으로 계산하고 최종 Production을 검증한다."""

import re
from collections.abc import Mapping, Sequence
from urllib.parse import quote, unquote

from VALIDATORS.candidate_evaluation import document_sha256
from VALIDATORS.exceptions import ConfigurationError
from VALIDATORS.models import ValidationIssue

CHILD_ACTOR_LEVELS: tuple[str, ...] = ("NONE", "SUPPORTING", "PRIMARY")
VEHICLE_LEVELS: tuple[str, ...] = ("NONE", "STATIC", "MOVING")
SPECIAL_EFFECT_LEVELS: tuple[str, ...] = ("NONE", "LOW", "MEDIUM", "HIGH")
GRAPHIC_VIOLENCE_LEVELS: tuple[str, ...] = (
    "NONE",
    "IMPLIED",
    "NON_GRAPHIC",
    "GRAPHIC",
)
PRODUCTION_COMPLEXITY_LEVELS: tuple[str, ...] = ("LOW", "MEDIUM", "HIGH", "EXTREME")
SCENE_FIELDS: tuple[str, ...] = (
    "scene_id",
    "location_id",
    "cast_ids",
    "child_actor_use",
    "vehicle_scene",
    "special_effect_level",
    "graphic_violence",
    "production_complexity",
)
PRODUCTION_SCENE_PATTERN = re.compile(
    r"<!--\s*PRODUCTION_SCENE:(?P<scene_id>SCN-[0-9]{2,})\s+"
    r"LOCATION:(?P<location_id>[^\s]+)\s+"
    r"CAST:(?P<cast_ids>[A-Z0-9_,-]+)\s+"
    r"CHILD:(?P<child_actor_use>[A-Z_]+)\s+"
    r"VEHICLE:(?P<vehicle_scene>[A-Z_]+)\s+"
    r"SFX:(?P<special_effect_level>[A-Z_]+)\s+"
    r"VIOLENCE:(?P<graphic_violence>[A-Z_]+)\s+"
    r"COMPLEXITY:(?P<production_complexity>[A-Z_]+)\s*-->"
)
SCENE_ID_PATTERN = re.compile(r"\bSCN-[0-9]{2,}\b")


def production_footprint_enforced(project_constraints: Mapping[str, object]) -> bool:
    """Project가 최종 Production Footprint 검증을 명시적으로 활성화했는지 반환한다."""
    limits = project_constraints.get("production_limits")
    return (
        isinstance(limits, Mapping)
        and limits.get("enforce_final_footprint") is True
    )


def footprint_issue(
    code: str,
    message: str,
    artifact: str,
    context: dict[str, object],
) -> ValidationIssue:
    """Production Footprint 오류를 공통 형식으로 만든다."""
    return ValidationIssue(
        severity="ERROR",
        code=code,
        message=message,
        artifact=artifact,
        context=context,
    )


def require_records(
    document: Mapping[str, object],
    key: str,
    artifact_name: str,
) -> list[Mapping[str, object]]:
    """Artifact의 객체 배열을 엄격하게 읽는다."""
    records = document.get(key)
    if not isinstance(records, list) or not records or not all(
        isinstance(record, Mapping) for record in records
    ):
        raise ConfigurationError(
            f"PRODUCTION_FOOTPRINT_MISSING: {artifact_name}.{key} 객체 배열이 필요합니다."
        )
    return [record for record in records if isinstance(record, Mapping)]


def require_string(
    record: Mapping[str, object],
    field: str,
    scene_id: object,
) -> str:
    """Scene 제작 메타데이터 문자열을 엄격하게 읽는다."""
    value = record.get(field)
    if not isinstance(value, str) or not value:
        raise ConfigurationError(
            "PRODUCTION_FOOTPRINT_MISSING: "
            f"Scene 제작 메타데이터가 없습니다: scene_id={scene_id!r}, field={field}"
        )
    return value


def require_string_list(
    record: Mapping[str, object],
    field: str,
    scene_id: object,
) -> list[str]:
    """Scene 제작 메타데이터 문자열 배열을 엄격하게 읽는다."""
    value = record.get(field)
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise ConfigurationError(
            "PRODUCTION_FOOTPRINT_MISSING: "
            f"Scene 제작 메타데이터 배열이 없습니다: scene_id={scene_id!r}, field={field}"
        )
    return list(value)


def maximum_level(values: Sequence[str], levels: tuple[str, ...], field: str) -> str:
    """정의된 Severity 순서에서 가장 높은 값을 반환한다."""
    invalid = sorted(set(values) - set(levels))
    if invalid:
        raise ConfigurationError(
            "PRODUCTION_FOOTPRINT_MISMATCH: "
            f"알 수 없는 제작 수준입니다: field={field}, values={invalid}"
        )
    return max(values, key=levels.index)


def normalized_scene_records(
    scene_cards: Mapping[str, object],
    characters: Mapping[str, object],
    actual_timeline: Mapping[str, object],
) -> list[dict[str, object]]:
    """Scene Card 제작 메타데이터를 참조 무결성이 확인된 Record로 정규화한다."""
    scenes = require_records(scene_cards, "scenes", "scene_cards")
    character_records = require_records(characters, "characters", "characters")
    timeline_records = require_records(actual_timeline, "events", "actual_timeline")
    character_ids = {
        str(record["character_id"])
        for record in character_records
        if isinstance(record.get("character_id"), str)
    }
    timeline_locations = {
        str(record["location_id"])
        for record in timeline_records
        if isinstance(record.get("location_id"), str)
    }
    normalized: list[dict[str, object]] = []
    seen_scene_ids: set[str] = set()
    for scene in scenes:
        scene_id = require_string(scene, "scene_id", scene.get("scene_id"))
        if scene_id in seen_scene_ids:
            raise ConfigurationError(
                f"PRODUCTION_FOOTPRINT_MISMATCH: Scene ID가 중복됩니다: scene_id={scene_id}"
            )
        seen_scene_ids.add(scene_id)
        location_id = require_string(scene, "location_id", scene_id)
        cast_ids = require_string_list(scene, "cast_ids", scene_id)
        unknown_cast = sorted(set(cast_ids) - character_ids)
        if unknown_cast or location_id not in timeline_locations:
            raise ConfigurationError(
                "PRODUCTION_FOOTPRINT_MISMATCH: Scene 제작 참조가 실제 Story Artifact와 "
                f"다릅니다: scene_id={scene_id}, unknown_cast={unknown_cast}, "
                f"unknown_location={location_id not in timeline_locations}"
            )
        normalized.append(
            {
                "scene_id": scene_id,
                "location_id": location_id,
                "cast_ids": sorted(set(cast_ids)),
                "child_actor_use": require_string(scene, "child_actor_use", scene_id),
                "vehicle_scene": require_string(scene, "vehicle_scene", scene_id),
                "special_effect_level": require_string(
                    scene,
                    "special_effect_level",
                    scene_id,
                ),
                "graphic_violence": require_string(scene, "graphic_violence", scene_id),
                "production_complexity": require_string(
                    scene,
                    "production_complexity",
                    scene_id,
                ),
                "order": scene.get("order"),
            }
        )
    return sorted(
        normalized,
        key=lambda record: (
            record["order"] if isinstance(record.get("order"), int) else 0,
            str(record["scene_id"]),
        ),
    )


def major_character_ids(
    characters: Mapping[str, object],
    scene_records: Sequence[Mapping[str, object]],
) -> set[str]:
    """Scene에 실제 등장하며 MAJOR로 분류된 Character ID를 반환한다."""
    records = require_records(characters, "characters", "characters")
    role_by_id: dict[str, str] = {}
    for record in records:
        character_id = record.get("character_id")
        production_role = record.get("production_role")
        if not isinstance(character_id, str) or not isinstance(production_role, str):
            raise ConfigurationError(
                "PRODUCTION_FOOTPRINT_MISSING: Character production_role이 필요합니다: "
                f"character_id={character_id!r}"
            )
        role_by_id[character_id] = production_role
    cast_ids: set[str] = set()
    for scene in scene_records:
        raw_cast_ids = scene.get("cast_ids")
        if isinstance(raw_cast_ids, list):
            cast_ids.update(
                cast_id for cast_id in raw_cast_ids if isinstance(cast_id, str)
            )
    return {
        character_id
        for character_id in cast_ids
        if role_by_id.get(character_id) == "MAJOR"
    }


def build_production_footprint(
    project_id: str,
    scene_cards: Mapping[str, object],
    characters: Mapping[str, object],
    actual_timeline: Mapping[str, object],
) -> dict[str, object]:
    """Scene·Character·Timeline에서 CORE 소유 Production Footprint를 계산한다."""
    scene_records = normalized_scene_records(scene_cards, characters, actual_timeline)
    child_levels = [str(record["child_actor_use"]) for record in scene_records]
    vehicle_levels = [str(record["vehicle_scene"]) for record in scene_records]
    effect_levels = [str(record["special_effect_level"]) for record in scene_records]
    violence_levels = [str(record["graphic_violence"]) for record in scene_records]
    complexity_levels = [str(record["production_complexity"]) for record in scene_records]
    return {
        "$schema": "../../STANDARD/schemas/production_footprint.schema.json",
        "schema_family": "production-footprint",
        "schema_version": "1.0.0",
        "project_id": project_id,
        "status": "PLANNED",
        "actual_location_count": len(
            {str(record["location_id"]) for record in scene_records}
        ),
        "actual_major_character_count": len(
            major_character_ids(characters, scene_records)
        ),
        "actual_child_actor_use": maximum_level(
            child_levels,
            CHILD_ACTOR_LEVELS,
            "child_actor_use",
        ),
        "actual_vehicle_scene": maximum_level(
            vehicle_levels,
            VEHICLE_LEVELS,
            "vehicle_scene",
        ),
        "actual_special_effect_level": maximum_level(
            effect_levels,
            SPECIAL_EFFECT_LEVELS,
            "special_effect_level",
        ),
        "actual_graphic_violence": maximum_level(
            violence_levels,
            GRAPHIC_VIOLENCE_LEVELS,
            "graphic_violence",
        ),
        "actual_production_complexity": maximum_level(
            complexity_levels,
            PRODUCTION_COMPLEXITY_LEVELS,
            "production_complexity",
        ),
        "source_scene_ids": [str(record["scene_id"]) for record in scene_records],
        "source_artifact_hashes": {
            "scene_cards": document_sha256(scene_cards),
            "characters": document_sha256(characters),
            "actual_timeline": document_sha256(actual_timeline),
        },
    }


def approved_selection(variations: Mapping[str, object]) -> Mapping[str, object] | None:
    """승인 Candidate의 Selection을 반환한다."""
    approved_id = variations.get("approved_candidate_id")
    candidates = variations.get("candidates")
    if not isinstance(approved_id, str) or not isinstance(candidates, list):
        return None
    for candidate in candidates:
        if not isinstance(candidate, Mapping) or candidate.get("candidate_id") != approved_id:
            continue
        selection = candidate.get("selection")
        return selection if isinstance(selection, Mapping) else None
    return None


def level_exceeds(actual: object, maximum: object, levels: tuple[str, ...]) -> bool:
    """정의된 Severity에서 실제 값이 허용 최댓값을 넘는지 반환한다."""
    return (
        not isinstance(actual, str)
        or not isinstance(maximum, str)
        or actual not in levels
        or maximum not in levels
        or levels.index(actual) > levels.index(maximum)
    )


def production_limit_issues(
    footprint: Mapping[str, object],
    project_constraints: Mapping[str, object],
) -> list[ValidationIssue]:
    """CORE Footprint가 Project Production Limit 안인지 검증한다."""
    limits = project_constraints.get("production_limits")
    if not isinstance(limits, Mapping):
        return [
            footprint_issue(
                "PRODUCTION_LIMIT_EXCEEDED",
                "Project Production Limit이 없습니다.",
                "00_PROJECT/project_constraints.json",
                {},
            )
        ]
    failures: dict[str, object] = {}
    for actual_field, limit_field in (
        ("actual_location_count", "max_locations"),
        ("actual_major_character_count", "max_major_characters"),
    ):
        actual = footprint.get(actual_field)
        maximum = limits.get(limit_field)
        if (
            not isinstance(actual, int)
            or isinstance(actual, bool)
            or not isinstance(maximum, int)
            or isinstance(maximum, bool)
            or actual > maximum
        ):
            failures[actual_field] = {"actual": actual, "maximum": maximum}
    if limits.get("allow_child_actor") is not True and footprint.get(
        "actual_child_actor_use"
    ) != "NONE":
        failures["actual_child_actor_use"] = footprint.get("actual_child_actor_use")
    if limits.get("allow_moving_vehicle") is not True and footprint.get(
        "actual_vehicle_scene"
    ) == "MOVING":
        failures["actual_vehicle_scene"] = footprint.get("actual_vehicle_scene")
    for actual_field, limit_field, levels in (
        (
            "actual_special_effect_level",
            "max_special_effect_level",
            SPECIAL_EFFECT_LEVELS,
        ),
        (
            "actual_graphic_violence",
            "max_graphic_violence",
            GRAPHIC_VIOLENCE_LEVELS,
        ),
        (
            "actual_production_complexity",
            "max_production_complexity",
            PRODUCTION_COMPLEXITY_LEVELS,
        ),
    ):
        if level_exceeds(footprint.get(actual_field), limits.get(limit_field), levels):
            failures[actual_field] = {
                "actual": footprint.get(actual_field),
                "maximum": limits.get(limit_field),
            }
    return (
        [
            footprint_issue(
                "PRODUCTION_LIMIT_EXCEEDED",
                "실제 Scene 제작 규모가 Project Production Limit을 초과합니다.",
                "06_SCENE/production_footprint.json",
                {"failures": failures},
            )
        ]
        if failures
        else []
    )


def candidate_advisory_issues(
    footprint: Mapping[str, object],
    variations: Mapping[str, object],
) -> list[ValidationIssue]:
    """실제 Footprint가 승인 Candidate의 제작 Advisory를 초과하지 않는지 검증한다."""
    selection = approved_selection(variations)
    if selection is None:
        return [
            footprint_issue(
                "PRODUCTION_FOOTPRINT_MISMATCH",
                "승인 Candidate의 Production Advisory를 찾을 수 없습니다.",
                "00_PROJECT/variation_candidates.json",
                {},
            )
        ]
    failures: dict[str, object] = {}
    for actual_field, selection_field, prefix in (
        ("actual_location_count", "location_count", "LOCATIONS_"),
        ("actual_major_character_count", "major_character_count", "MAJOR_"),
    ):
        advisory = selection.get(selection_field)
        suffix = advisory.removeprefix(prefix) if isinstance(advisory, str) else ""
        maximum = int(suffix) if suffix.isdigit() else None
        actual = footprint.get(actual_field)
        if (
            maximum is None
            or not isinstance(actual, int)
            or isinstance(actual, bool)
            or actual > maximum
        ):
            failures[selection_field] = {"actual": actual, "advisory": advisory}
    for actual_field, selection_field, levels in (
        ("actual_child_actor_use", "child_actor_use", CHILD_ACTOR_LEVELS),
        ("actual_vehicle_scene", "vehicle_scene", VEHICLE_LEVELS),
        (
            "actual_special_effect_level",
            "special_effect_level",
            SPECIAL_EFFECT_LEVELS,
        ),
        (
            "actual_graphic_violence",
            "graphic_violence",
            GRAPHIC_VIOLENCE_LEVELS,
        ),
        (
            "actual_production_complexity",
            "production_complexity",
            PRODUCTION_COMPLEXITY_LEVELS,
        ),
    ):
        if level_exceeds(footprint.get(actual_field), selection.get(selection_field), levels):
            failures[selection_field] = {
                "actual": footprint.get(actual_field),
                "advisory": selection.get(selection_field),
            }
    return (
        [
            footprint_issue(
                "PRODUCTION_FOOTPRINT_MISMATCH",
                "실제 제작 규모가 승인 Candidate Advisory를 초과합니다.",
                "06_SCENE/production_footprint.json",
                {"failures": failures},
            )
        ]
        if failures
        else []
    )


def validate_production_footprint(
    project_constraints: Mapping[str, object],
    footprint: Mapping[str, object] | None,
    scene_cards: Mapping[str, object],
    characters: Mapping[str, object],
    actual_timeline: Mapping[str, object],
    variations: Mapping[str, object],
) -> list[ValidationIssue]:
    """GATE-07 Footprint 존재·최신성·합계·제한을 검증한다."""
    if not production_footprint_enforced(project_constraints):
        return []
    if footprint is None:
        return [
            footprint_issue(
                "PRODUCTION_FOOTPRINT_MISSING",
                "최종 제작 제약이 활성화된 Project에 Production Footprint가 없습니다.",
                "06_SCENE/production_footprint.json",
                {},
            )
        ]
    project_id = scene_cards.get("project_id")
    if not isinstance(project_id, str):
        return [
            footprint_issue(
                "PRODUCTION_FOOTPRINT_MISMATCH",
                "Scene Card Project ID가 없습니다.",
                "06_SCENE/scene_cards.json",
                {},
            )
        ]
    try:
        expected = build_production_footprint(
            project_id,
            scene_cards,
            characters,
            actual_timeline,
        )
    except ConfigurationError as error:
        message = str(error)
        code = message.split(":", maxsplit=1)[0]
        return [
            footprint_issue(
                code,
                message,
                "06_SCENE/production_footprint.json",
                {},
            )
        ]
    expected_hashes = expected["source_artifact_hashes"]
    if footprint.get("source_artifact_hashes") != expected_hashes:
        return [
            footprint_issue(
                "PRODUCTION_FOOTPRINT_STALE",
                "Production Footprint의 Source Artifact Hash가 현재 입력과 다릅니다.",
                "06_SCENE/production_footprint.json",
                {
                    "expected": expected_hashes,
                    "actual": footprint.get("source_artifact_hashes"),
                },
            )
        ]
    if dict(footprint) != expected:
        return [
            footprint_issue(
                "PRODUCTION_FOOTPRINT_MISMATCH",
                "저장된 Production Footprint가 CORE 재계산 결과와 다릅니다.",
                "06_SCENE/production_footprint.json",
                {},
            )
        ]
    return [
        *production_limit_issues(footprint, project_constraints),
        *candidate_advisory_issues(footprint, variations),
    ]


def production_manifest_from_scene_cards(
    project_id: str,
    footprint: Mapping[str, object],
    scene_cards: Mapping[str, object],
    characters: Mapping[str, object],
    actual_timeline: Mapping[str, object],
) -> dict[str, object]:
    """Production 인계용 Scene별 Manifest를 Footprint Source에서 만든다."""
    scenes = normalized_scene_records(scene_cards, characters, actual_timeline)
    return {
        "$schema": "../../STANDARD/schemas/production_manifest.schema.json",
        "schema_family": "production-manifest",
        "schema_version": "1.0.0",
        "project_id": project_id,
        "source_footprint_sha256": document_sha256(footprint),
        "scenes": [
            {field: record[field] for field in SCENE_FIELDS}
            for record in scenes
        ],
    }


def production_scene_marker(scene: Mapping[str, object]) -> str:
    """Shooting Script에 사용할 정규 Production Scene Marker를 반환한다."""
    cast_ids = scene.get("cast_ids")
    cast_value = (
        ",".join(sorted(str(item) for item in cast_ids))
        if isinstance(cast_ids, list) and cast_ids
        else "NONE"
    )
    location_value = quote(str(scene.get("location_id")), safe="")
    return (
        f"<!-- PRODUCTION_SCENE:{scene.get('scene_id')} "
        f"LOCATION:{location_value} CAST:{cast_value} "
        f"CHILD:{scene.get('child_actor_use')} VEHICLE:{scene.get('vehicle_scene')} "
        f"SFX:{scene.get('special_effect_level')} "
        f"VIOLENCE:{scene.get('graphic_violence')} "
        f"COMPLEXITY:{scene.get('production_complexity')} -->"
    )


def shooting_script_scene_records(script: str) -> list[dict[str, object]]:
    """Shooting Script의 정규 Production Scene Marker를 파싱한다."""
    records: list[dict[str, object]] = []
    for match in PRODUCTION_SCENE_PATTERN.finditer(script):
        values = match.groupdict()
        cast_value = values["cast_ids"]
        records.append(
            {
                "scene_id": values["scene_id"],
                "location_id": unquote(values["location_id"]),
                "cast_ids": [] if cast_value == "NONE" else sorted(set(cast_value.split(","))),
                "child_actor_use": values["child_actor_use"],
                "vehicle_scene": values["vehicle_scene"],
                "special_effect_level": values["special_effect_level"],
                "graphic_violence": values["graphic_violence"],
                "production_complexity": values["production_complexity"],
            }
        )
    return records


def validate_final_production_footprint(
    project_constraints: Mapping[str, object],
    footprint: Mapping[str, object] | None,
    production_manifest: Mapping[str, object] | None,
    scene_cards: Mapping[str, object],
    characters: Mapping[str, object],
    actual_timeline: Mapping[str, object],
    variations: Mapping[str, object],
    shooting_script: str,
) -> list[ValidationIssue]:
    """GATE-13에서 Manifest와 Shooting Script의 Scene 제작 요소를 대조한다."""
    issues = validate_production_footprint(
        project_constraints,
        footprint,
        scene_cards,
        characters,
        actual_timeline,
        variations,
    )
    if not production_footprint_enforced(project_constraints) or issues:
        return issues
    assert footprint is not None
    if production_manifest is None:
        return [
            footprint_issue(
                "PRODUCTION_FOOTPRINT_MISSING",
                "최종 Production Manifest가 없습니다.",
                "09_PRODUCTION/production_manifest.json",
                {},
            )
        ]
    expected_manifest = production_manifest_from_scene_cards(
        str(footprint.get("project_id")),
        footprint,
        scene_cards,
        characters,
        actual_timeline,
    )
    if dict(production_manifest) != expected_manifest:
        issues.append(
            footprint_issue(
                "UNDECLARED_PRODUCTION_ELEMENT",
                "Production Manifest가 승인된 Scene 제작 요소와 다릅니다.",
                "09_PRODUCTION/production_manifest.json",
                {},
            )
        )
    manifest_scenes = production_manifest.get("scenes")
    expected_scene_records = (
        [dict(record) for record in manifest_scenes if isinstance(record, Mapping)]
        if isinstance(manifest_scenes, list)
        else []
    )
    script_records = shooting_script_scene_records(shooting_script)
    duplicate_script_ids = sorted(
        {
            str(record["scene_id"])
            for record in script_records
            if sum(
                1
                for candidate in script_records
                if candidate.get("scene_id") == record.get("scene_id")
            )
            > 1
        }
    )
    unmarked_scene_ids = sorted(
        set(SCENE_ID_PATTERN.findall(shooting_script))
        - {str(record["scene_id"]) for record in script_records}
    )
    if (
        script_records != expected_scene_records
        or duplicate_script_ids
        or unmarked_scene_ids
    ):
        issues.append(
            footprint_issue(
                "UNDECLARED_PRODUCTION_ELEMENT",
                "Shooting Script의 Scene 또는 제작 요소가 Production Manifest와 다릅니다.",
                "09_PRODUCTION/shooting_script.md",
                {
                    "duplicate_scene_ids": duplicate_script_ids,
                    "unmarked_scene_ids": unmarked_scene_ids,
                },
            )
        )
    return issues
