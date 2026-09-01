"""Provider API 없이 전체 Runtime을 검증하는 결정론적 FakeProvider."""

import json
from collections.abc import Mapping
from copy import deepcopy
from hashlib import sha256
from typing import TypeAlias, cast

from RUNTIME.errors import RuntimeExecutionError
from RUNTIME.models import (
    LLMRequest,
    LLMResponse,
    ProviderDescriptor,
    TokenUsage,
)
from VALIDATORS.candidate_evaluation import (
    EVENT_SCORE_FIELDS,
    EVENT_WEIGHTS,
    SCORE_FIELDS,
    candidate_evaluation_input_hashes,
)
from VALIDATORS.candidate_event_briefs import canonical_json_hash
from VALIDATORS.crime_functions import DEFAULT_DEVELOPMENT_FUNCTIONS, development_families
from VALIDATORS.editorial import (
    editorial_artifact_hashes,
    make_editorial_evidence,
    panel_spoken_metrics,
)
from VALIDATORS.presentation_validation import presentation_segments
from VALIDATORS.production_footprint import (
    production_footprint_enforced,
    production_scene_marker,
)
from VALIDATORS.reenactment_runtime import reenactment_runtime_evidence

PresentationDefinition: TypeAlias = tuple[
    str,
    str,
    str,
    float,
    str | None,
    str,
    list[str],
]


def mapping_values(value: object) -> list[Mapping[str, object]]:
    """객체 배열 값만 반환한다."""
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, Mapping)]


def string_values(value: object) -> list[str]:
    """문자열 배열 값만 반환한다."""
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, str)]


def panel_fixture_line(core: str, focus: str, segment_duration_sec: float) -> str:
    """발화 밀도 계약을 만족하는 사건 추적용 Panel 발화를 만든다."""
    if segment_duration_sec < 30.0:
        return core
    return (
        f"{core} 지금 확인된 {focus}만 기준으로 보면 한 장면의 인상만으로 "
        "책임을 단정할 수 없습니다. 피해자가 처한 위험과 선택의 제약을 먼저 살피고, "
        "공개된 기록과 행동이 서로 맞는지 확인해야 합니다. 다른 패널의 해석과 "
        "충돌하는 지점도 짚어야 하고, 새 단서가 나오면 기존 가설을 고쳐야 합니다. "
        "그래야 감정 반응과 용의자 추적이 함께 진행되고, 아직 공개되지 않은 범인과 "
        "동기와 방식과 피해 결과를 앞당겨 말하지 않을 수 있습니다."
    )


def panel_script_line(
    panelist_id: str,
    core: str,
    focus: str,
    segment_duration_sec: float,
) -> str:
    """Panel Script의 실제 화자 발화 한 줄을 만든다."""
    spoken_line = panel_fixture_line(core, focus, segment_duration_sec)
    return f"[{panelist_id}] “{spoken_line}”"


def approved_selection(metadata: Mapping[str, str]) -> dict[str, str]:
    """Runtime이 전달한 승인 Variation을 Fake Fixture 입력으로 읽는다."""
    raw_selection = metadata.get("approved_selection")
    if not isinstance(raw_selection, str):
        raise RuntimeExecutionError(
            "RUNTIME_CONFIGURATION_ERROR",
            False,
            "TASK",
            "FakeProvider에 승인 Variation이 전달되지 않았습니다.",
            metadata.get("task_id"),
            "variation_candidates",
            {},
        )
    parsed: object = json.loads(raw_selection)
    if not isinstance(parsed, Mapping) or not all(
        isinstance(key, str) and isinstance(value, str) for key, value in parsed.items()
    ):
        raise RuntimeExecutionError(
            "RUNTIME_CONFIGURATION_ERROR",
            False,
            "TASK",
            "FakeProvider 승인 Variation 형식이 올바르지 않습니다.",
            metadata.get("task_id"),
            "variation_candidates",
            {},
        )
    return {str(key): cast(str, value) for key, value in parsed.items()}


def target_runtime_seconds(metadata: Mapping[str, str]) -> int:
    """Runtime Metadata에서 목표 영상 길이를 초 단위로 읽는다."""
    raw_minutes = metadata.get("target_runtime_minutes")
    if not isinstance(raw_minutes, str) or not raw_minutes.isdigit():
        raise RuntimeExecutionError(
            "RUNTIME_CONFIGURATION_ERROR",
            False,
            "TASK",
            "FakeProvider에 목표 Runtime이 전달되지 않았습니다.",
            metadata.get("task_id"),
            "production_config",
            {"target_runtime_minutes": raw_minutes},
        )
    minutes = int(raw_minutes)
    if minutes < 1:
        raise RuntimeExecutionError(
            "RUNTIME_CONFIGURATION_ERROR",
            False,
            "TASK",
            "FakeProvider 목표 Runtime은 1분 이상이어야 합니다.",
            metadata.get("task_id"),
            "production_config",
            {"target_runtime_minutes": minutes},
        )
    return minutes * 60


def broadcast_marker(
    segment_id: str,
    segment_type: str,
    scene_id: str,
    duration_sec: float,
    body: str,
) -> str:
    """Fake Broadcast Segment를 표준 Marker 형식으로 만든다."""
    duration_text = f"{duration_sec:g}"
    return (
        f"<!-- SEGMENT:{segment_id} TYPE:{segment_type} "
        f"SCENE:{scene_id} DURATION:{duration_text} -->\n"
        f"{body}\n"
        f"<!-- END_SEGMENT:{segment_id} -->"
    )


def fake_presentation_plan(project_id: str, total_seconds: int) -> dict[str, object]:
    """Panel 비율이 정확히 20%인 결정론적 Presentation Plan을 만든다."""
    reaction_duration = float(total_seconds) / 15.0
    main_duration = float(total_seconds) * 4.0 / 15.0
    definitions: tuple[PresentationDefinition, ...] = (
        ("SEG-001", "DRAMA", "SCN-01", main_duration, None, "drama_script", ["FACT-01"]),
        (
            "SEG-002",
            "PANEL_REACTION",
            "SCN-01",
            reaction_duration,
            "RSEG-001",
            "panel_reaction_script",
            [],
        ),
        (
            "SEG-003",
            "NARRATION",
            "SCN-01",
            main_duration,
            None,
            "narration_script",
            [],
        ),
        (
            "SEG-004",
            "PANEL_REACTION",
            "SCN-01",
            reaction_duration,
            "RSEG-002",
            "panel_reaction_script",
            [],
        ),
        ("SEG-005", "DRAMA", "SCN-02", main_duration, None, "drama_script", ["FACT-02"]),
        (
            "SEG-006",
            "PANEL_REACTION",
            "SCN-02",
            reaction_duration,
            "RSEG-003",
            "panel_reaction_script",
            [],
        ),
    )
    start_sec = 0.0
    segments: list[dict[str, object]] = []
    for (
        segment_id,
        segment_type,
        scene_id,
        duration_sec,
        reaction_segment_id,
        source_artifact,
        fact_ids,
    ) in definitions:
        segment: dict[str, object] = {
            "segment_id": segment_id,
            "segment_type": segment_type,
            "scene_id": scene_id,
            "start_sec": start_sec,
            "duration_sec": duration_sec,
            "source_artifact": source_artifact,
            "revealed_fact_ids": fact_ids,
            "revealed_clue_ids": [],
        }
        if reaction_segment_id is not None:
            segment["reaction_segment_id"] = reaction_segment_id
        segments.append(segment)
        start_sec += duration_sec
    return {
        "schema_family": "presentation-plan",
        "schema_version": "2.0.0",
        "project_id": project_id,
        "modes": ["DRAMA", "NARRATION", "PANEL_REACTION"],
        "segments": segments,
    }


def fake_crime_presentation_plan(
    project_id: str,
    total_seconds: int,
    crime_event: Mapping[str, object],
) -> dict[str, object]:
    """사건 Reveal·주관적 Narration Metadata를 Presentation에 결속한다."""
    plan = fake_presentation_plan(project_id, total_seconds)
    raw_segments = plan.get("segments")
    if not isinstance(raw_segments, list):
        raise RuntimeExecutionError(
            "RUNTIME_CONFIGURATION_ERROR",
            False,
            "TASK",
            "Fake 사건 Presentation Segment가 없습니다.",
            "scene.design",
            "presentation_plan",
            {},
        )
    reveal_targets = crime_event.get("reveal_targets")
    reveal_records = reveal_targets if isinstance(reveal_targets, list) else []
    target_ids = [
        str(item["reveal_target_id"])
        for item in reveal_records
        if isinstance(item, Mapping) and isinstance(item.get("reveal_target_id"), str)
    ]
    development_functions = crime_event.get("development_functions")
    function_records = development_functions if isinstance(development_functions, list) else []
    function_ids = [
        str(item["development_function_id"])
        for item in function_records
        if isinstance(item, Mapping)
        and isinstance(item.get("development_function_id"), str)
        and item.get("required") is True
    ]
    for raw_segment in raw_segments:
        if not isinstance(raw_segment, dict):
            continue
        raw_segment["referenced_reveal_target_ids"] = []
        raw_segment["revealed_reveal_target_ids"] = []
        raw_segment["intentional_prereveal_ids"] = []
        if raw_segment.get("segment_type") == "NARRATION":
            raw_segment["narrator_character_id"] = "CHAR-02"
            raw_segment["narration_function"] = "EMOTIONAL_CONTINUITY"
        if raw_segment.get("segment_id") == "SEG-005":
            raw_segment["revealed_reveal_target_ids"] = target_ids[:2]
            raw_segment["crime_development_function_ids"] = function_ids
        if raw_segment.get("segment_id") == "SEG-006":
            raw_segment["revealed_reveal_target_ids"] = target_ids[2:]
    plan["schema_version"] = "2.1.0"
    return plan


def fake_context_presentation_plan(
    request: LLMRequest,
    project_id: str,
    total_seconds: int,
) -> dict[str, object]:
    """현재 Task에 사건 계약이 있으면 사건 Metadata가 포함된 Plan을 만든다."""
    crime_event = context_artifact(request, "crime_event_contract")
    if crime_event is None:
        return fake_presentation_plan(project_id, total_seconds)
    return fake_crime_presentation_plan(project_id, total_seconds, crime_event)


def fake_panel_cast(project_id: str) -> dict[str, object]:
    """서로 다른 추리 기능을 가진 세 Panelist Fixture를 만든다."""
    return {
        "schema_family": "panel-cast",
        "schema_version": "2.0.0",
        "project_id": project_id,
        "panelists": [
            {
                "panelist_id": "PANEL-01",
                "display_name": "논리 패널",
                "persona": "LOGIC_ANALYST",
                "voice_style": "차분하고 근거 중심",
                "allowed_functions": [
                    "ANOMALY_DETECTION",
                    "HYPOTHESIS_GENERATION",
                    "HYPOTHESIS_REVISION",
                ],
                "knowledge_scope": "REVEALED_INFORMATION_ONLY",
            },
            {
                "panelist_id": "PANEL-02",
                "display_name": "감정 패널",
                "persona": "EMOTIONAL_PROXY",
                "voice_style": "인물의 감정 변화를 세심하게 읽음",
                "allowed_functions": ["EMOTIONAL_REACTION", "TENSION_RELEASE"],
                "knowledge_scope": "REVEALED_INFORMATION_ONLY",
            },
            {
                "panelist_id": "PANEL-03",
                "display_name": "반론 패널",
                "persona": "SKEPTIC",
                "voice_style": "주요 가설에 근거 있는 반론을 제시함",
                "allowed_functions": [
                    "CONTRADICTION_DETECTION",
                    "HYPOTHESIS_REVISION",
                ],
                "knowledge_scope": "REVEALED_INFORMATION_ONLY",
            },
        ],
    }


def fake_reaction_segments(project_id: str, total_seconds: int) -> dict[str, object]:
    """가설 생성·이상 탐지·수정을 포함한 Reaction Fixture를 만든다."""
    reaction_duration = float(total_seconds) / 15.0
    main_duration = float(total_seconds) * 4.0 / 15.0
    return {
        "schema_family": "reaction-segments",
        "schema_version": "2.1.0",
        "project_id": project_id,
        "reaction_segments": [
            {
                "reaction_segment_id": "RSEG-001",
                "after_scene_id": "SCN-01",
                "order": 1,
                "start_sec": main_duration,
                "duration_sec": reaction_duration,
                "segment_function": "HYPOTHESIS_GENERATION",
                "hypothesis_before": "작업자가 자발적으로 이탈했다.",
                "hypothesis_after": "기계 기록이 실제 동선과 다를 수 있다.",
                "tone": "SUSPICIOUS",
                "turns": [
                    {
                        "turn_id": "TURN-001-01",
                        "panelist_id": "PANEL-01",
                        "function": "HYPOTHESIS_GENERATION",
                        "spoken_line": panel_fixture_line(
                            "7분의 공백이 이탈의 증거인지부터 확인해야 합니다.",
                            "기계 로그의 시간 공백",
                            reaction_duration,
                        ),
                        "evidence_ids": ["CLUE-01"],
                        "known_fact_ids": ["FACT-01"],
                        "tone": "SUSPICIOUS",
                    },
                    {
                        "turn_id": "TURN-001-02",
                        "panelist_id": "PANEL-03",
                        "function": "CONTRADICTION_DETECTION",
                        "responds_to_turn_id": "TURN-001-01",
                        "spoken_line": panel_fixture_line(
                            "공백을 사람의 선택으로만 보기엔 빠른 것 같아요.",
                            "자발적 이탈이라는 첫 가설",
                            reaction_duration,
                        ),
                        "evidence_ids": ["CLUE-01"],
                        "known_fact_ids": ["FACT-01"],
                        "tone": "CHALLENGING",
                    },
                ],
            },
            {
                "reaction_segment_id": "RSEG-002",
                "after_scene_id": "SCN-01",
                "order": 2,
                "start_sec": main_duration * 2.0 + reaction_duration,
                "duration_sec": reaction_duration,
                "segment_function": "CONTRADICTION_DETECTION",
                "hypothesis_before": "공백 동안 작업자가 이동했다.",
                "hypothesis_after": "센서 공백과 작업자 이동은 별개일 수 있다.",
                "tone": "ANALYTICAL",
                "turns": [
                    {
                        "turn_id": "TURN-002-01",
                        "panelist_id": "PANEL-03",
                        "function": "CONTRADICTION_DETECTION",
                        "spoken_line": panel_fixture_line(
                            "이동 기록이 아니라 센서 자체가 멈춘 것일 수도 있죠.",
                            "센서 작동 상태",
                            reaction_duration,
                        ),
                        "evidence_ids": ["CLUE-01"],
                        "known_fact_ids": ["FACT-01"],
                        "tone": "ANALYTICAL",
                    },
                    {
                        "turn_id": "TURN-002-02",
                        "panelist_id": "PANEL-02",
                        "function": "EMOTIONAL_REACTION",
                        "responds_to_turn_id": "TURN-002-01",
                        "spoken_line": panel_fixture_line(
                            "그렇다면 공백 안에 남은 사람을 먼저 찾아야 해요.",
                            "피해자의 안전과 위치",
                            reaction_duration,
                        ),
                        "evidence_ids": ["CLUE-01"],
                        "known_fact_ids": ["FACT-01"],
                        "tone": "CONCERNED",
                    },
                ],
            },
            {
                "reaction_segment_id": "RSEG-003",
                "after_scene_id": "SCN-02",
                "order": 3,
                "start_sec": main_duration * 3.0 + reaction_duration * 2.0,
                "duration_sec": reaction_duration,
                "segment_function": "HYPOTHESIS_REVISION",
                "hypothesis_before": "작업자가 기록 공백을 이용해 이탈했다.",
                "hypothesis_after": "센서 차단이 작업자의 위치를 숨겼다.",
                "tone": "RECONSIDERING",
                "turns": [
                    {
                        "turn_id": "TURN-003-01",
                        "panelist_id": "PANEL-01",
                        "function": "HYPOTHESIS_REVISION",
                        "spoken_line": panel_fixture_line(
                            "안전 센서가 점검 모드였다면 공백은 이탈 증거가 아닙니다.",
                            "점검 모드 기록",
                            reaction_duration,
                        ),
                        "evidence_ids": ["CLUE-01", "CLUE-02"],
                        "known_fact_ids": ["FACT-01", "FACT-02"],
                        "tone": "RECONSIDERING",
                    },
                    {
                        "turn_id": "TURN-003-02",
                        "panelist_id": "PANEL-02",
                        "function": "TENSION_RELEASE",
                        "responds_to_turn_id": "TURN-003-01",
                        "spoken_line": panel_fixture_line(
                            "이제야 사람을 잘못 탓하던 시간을 되돌릴 수 있겠네요.",
                            "수정된 가설과 피해자 맥락",
                            reaction_duration,
                        ),
                        "evidence_ids": ["CLUE-01", "CLUE-02"],
                        "known_fact_ids": ["FACT-01", "FACT-02"],
                        "tone": "RELIEVED",
                    },
                ],
            },
        ],
    }


def fake_script_layers(
    total_seconds: int,
    audience_label_text: str | None,
) -> dict[str, str]:
    """Presentation Plan과 정확히 일치하는 세 Script Layer를 만든다."""
    reaction_duration = float(total_seconds) / 15.0
    main_duration = float(total_seconds) * 4.0 / 15.0
    return {
        "drama_script": "\n\n".join(
            (
                broadcast_marker(
                    "SEG-001",
                    "DRAMA",
                    "SCN-01",
                    main_duration,
                    "\n".join(
                        value
                        for value in (
                            audience_label_text,
                            "[FACT:FACT-01] 지안은 기계 로그에서 7분의 공백을 발견한다.",
                        )
                        if value is not None
                    ),
                ),
                broadcast_marker(
                    "SEG-005",
                    "DRAMA",
                    "SCN-02",
                    main_duration,
                    "[FACT:FACT-02] 점검 모드였던 안전 센서가 화면에 표시된다.",
                ),
            )
        ),
        "narration_script": broadcast_marker(
            "SEG-003",
            "NARRATION",
            "SCN-01",
            main_duration,
            "지안은 기록의 공백을 사람의 선택으로 해석하고 있었다.",
        ),
        "panel_reaction_script": "\n\n".join(
            (
                broadcast_marker(
                    "SEG-002",
                    "PANEL_REACTION",
                    "SCN-01",
                    reaction_duration,
                    "[RSEG-001] [PANEL-01] [HYPOTHESIS_GENERATION]\n"
                    + panel_script_line(
                        "PANEL-01",
                        "7분의 공백이 이탈의 증거인지부터 확인해야 합니다.",
                        "기계 로그의 시간 공백",
                        reaction_duration,
                    )
                    + "\n"
                    + panel_script_line(
                        "PANEL-03",
                        "공백을 사람의 선택으로만 보기엔 빠른 것 같아요.",
                        "자발적 이탈이라는 첫 가설",
                        reaction_duration,
                    ),
                ),
                broadcast_marker(
                    "SEG-004",
                    "PANEL_REACTION",
                    "SCN-01",
                    reaction_duration,
                    "[RSEG-002] [PANEL-03] [CONTRADICTION_DETECTION]\n"
                    + panel_script_line(
                        "PANEL-03",
                        "이동 기록이 아니라 센서 자체가 멈춘 것일 수도 있죠.",
                        "센서 작동 상태",
                        reaction_duration,
                    )
                    + "\n"
                    + panel_script_line(
                        "PANEL-02",
                        "그렇다면 공백 안에 남은 사람을 먼저 찾아야 해요.",
                        "피해자의 안전과 위치",
                        reaction_duration,
                    ),
                ),
                broadcast_marker(
                    "SEG-006",
                    "PANEL_REACTION",
                    "SCN-02",
                    reaction_duration,
                    "[RSEG-003] [PANEL-01] [HYPOTHESIS_REVISION]\n"
                    + panel_script_line(
                        "PANEL-01",
                        "안전 센서가 점검 모드였다면 공백은 이탈 증거가 아닙니다.",
                        "점검 모드 기록",
                        reaction_duration,
                    )
                    + "\n"
                    + panel_script_line(
                        "PANEL-02",
                        "이제야 사람을 잘못 탓하던 시간을 되돌릴 수 있겠네요.",
                        "수정된 가설과 피해자 맥락",
                        reaction_duration,
                    ),
                ),
            )
        ),
    }


def fake_broadcast_master(
    total_seconds: int,
    audience_label_text: str | None,
) -> str:
    """세 Layer Segment를 방송 시간순으로 통합한다."""
    layers = fake_script_layers(total_seconds, audience_label_text)
    layer_segments: dict[str, str] = {}
    for content in layers.values():
        for segment_id in ("SEG-001", "SEG-002", "SEG-003", "SEG-004", "SEG-005", "SEG-006"):
            start = content.find(f"<!-- SEGMENT:{segment_id} ")
            if start < 0:
                continue
            end_marker = f"<!-- END_SEGMENT:{segment_id} -->"
            end = content.find(end_marker, start)
            if end >= 0:
                layer_segments[segment_id] = content[start : end + len(end_marker)]
    return "\n\n".join(layer_segments[f"SEG-{index:03d}"] for index in range(1, 7))


def fake_crime_script_layers(
    total_seconds: int,
    audience_label_text: str | None,
    crime_event: Mapping[str, object],
) -> dict[str, str]:
    """범죄 행동·피해·서사 기능의 비가시 추적 정보를 Drama에 삽입한다."""
    layers = fake_script_layers(total_seconds, audience_label_text)
    event_id = crime_event.get("event_id")
    action_type = crime_event.get("core_action_type")
    harm_ids = crime_event.get("harm_ids")
    harm_id = harm_ids[0] if isinstance(harm_ids, list) and harm_ids else None
    method_summary = crime_event.get("non_actionable_method_summary")
    immediate_harm = crime_event.get("immediate_harm")
    lasting_harm = crime_event.get("lasting_harm")
    development_functions = crime_event.get("development_functions")
    function_ids = [
        str(item["development_function_id"])
        for item in mapping_values(development_functions)
        if isinstance(item.get("development_function_id"), str) and item.get("required") is True
    ]
    if not all(
        isinstance(value, str)
        for value in (
            event_id,
            action_type,
            harm_id,
            method_summary,
            immediate_harm,
            lasting_harm,
        )
    ):
        raise RuntimeExecutionError(
            "RUNTIME_CONFIGURATION_ERROR",
            False,
            "TASK",
            "Fake 사건 Script에 사건·행동·피해 ID가 없습니다.",
            "script.write_layers",
            "crime_event_contract",
            {},
        )
    marker = (
        "<!-- CRIME_TRACE\n"
        f"EVENT={event_id}\n"
        f"ACTION={action_type}\n"
        f"HARM={harm_id}\n"
        f"DEV={','.join(function_ids)}\n"
        "-->\n"
    )
    realization = (
        f"사건 기록은 {method_summary}을 보여 준다. "
        f"그 결과 {immediate_harm}이 발생했고, {lasting_harm}으로 이어졌다.\n"
    )
    layers["drama_script"] = layers["drama_script"].replace(
        "[FACT:FACT-02]",
        marker + realization + "[FACT:FACT-02]",
        1,
    )
    return layers


def fake_crime_broadcast_master(
    total_seconds: int,
    audience_label_text: str | None,
    crime_event: Mapping[str, object],
) -> str:
    """사건 Marker가 포함된 세 Layer를 방송 순서로 통합한다."""
    layers = fake_crime_script_layers(total_seconds, audience_label_text, crime_event)
    layer_segments: dict[str, str] = {}
    for content in layers.values():
        for index in range(1, 7):
            segment_id = f"SEG-{index:03d}"
            start = content.find(f"<!-- SEGMENT:{segment_id} ")
            if start < 0:
                continue
            end_marker = f"<!-- END_SEGMENT:{segment_id} -->"
            end = content.find(end_marker, start)
            if end >= 0:
                layer_segments[segment_id] = content[start : end + len(end_marker)]
    return "\n\n".join(layer_segments[f"SEG-{index:03d}"] for index in range(1, 7))


def fake_edit_script(project_id: str, total_seconds: int) -> str:
    """Presentation Plan과 일치하는 Edit Timecode 표를 만든다."""
    plan = fake_presentation_plan(project_id, total_seconds)
    raw_segments = plan.get("segments")
    if not isinstance(raw_segments, list):
        raise RuntimeExecutionError(
            "RUNTIME_CONFIGURATION_ERROR",
            False,
            "TASK",
            "Fake Presentation Plan Segment가 배열이 아닙니다.",
            "production.package",
            "presentation_plan",
            {},
        )
    lines = ["| Segment | Timecode |", "|---|---:|"]
    for raw_segment in raw_segments:
        if not isinstance(raw_segment, Mapping):
            raise RuntimeExecutionError(
                "RUNTIME_CONFIGURATION_ERROR",
                False,
                "TASK",
                "Fake Presentation Segment가 객체가 아닙니다.",
                "production.package",
                "presentation_plan",
                {},
            )
        segment_id = raw_segment.get("segment_id")
        start_sec = raw_segment.get("start_sec")
        duration_sec = raw_segment.get("duration_sec")
        if (
            not isinstance(segment_id, str)
            or not isinstance(start_sec, int | float)
            or isinstance(start_sec, bool)
            or not isinstance(duration_sec, int | float)
            or isinstance(duration_sec, bool)
        ):
            raise RuntimeExecutionError(
                "RUNTIME_CONFIGURATION_ERROR",
                False,
                "TASK",
                "Fake Presentation Segment Timecode가 올바르지 않습니다.",
                "production.package",
                "presentation_plan",
                {"segment_id": segment_id},
            )
        start = round(float(start_sec))
        end = round(float(start_sec) + float(duration_sec))
        lines.append(
            f"| {segment_id} | {start // 60:02d}:{start % 60:02d}-{end // 60:02d}:{end % 60:02d} |"
        )
    return "\n".join(lines)


def fake_runtime_evidence(
    presentation_plan: Mapping[str, object],
    panel_reaction_script: str,
) -> dict[str, object]:
    """발화 예상시간과 편집 요소가 계획시간을 채우는 Runtime Fixture를 만든다."""
    reading_rate_wpm = 150.0
    spoken_metrics = panel_spoken_metrics(panel_reaction_script)
    panel_segments: list[dict[str, object]] = []
    planned_panel_duration = 0.0
    estimated_panel_spoken_duration = 0.0
    planned_runtime = 0.0
    for segment in presentation_segments(presentation_plan):
        duration = segment.get("duration_sec")
        if not isinstance(duration, int | float) or isinstance(duration, bool):
            raise RuntimeExecutionError(
                "RUNTIME_CONFIGURATION_ERROR",
                False,
                "TASK",
                "Fake Runtime Evidence의 Segment 시간이 올바르지 않습니다.",
                "editorial.review",
                "presentation_plan",
                {"segment_id": segment.get("segment_id")},
            )
        planned_runtime += float(duration)
        if segment.get("segment_type") != "PANEL_REACTION":
            continue
        segment_id = segment.get("segment_id")
        reaction_segment_id = segment.get("reaction_segment_id")
        if not isinstance(segment_id, str) or not isinstance(reaction_segment_id, str):
            raise RuntimeExecutionError(
                "RUNTIME_CONFIGURATION_ERROR",
                False,
                "TASK",
                "Fake Runtime Evidence의 Panel Segment ID가 없습니다.",
                "editorial.review",
                "presentation_plan",
                {"segment_id": segment_id},
            )
        metrics = spoken_metrics.get(segment_id)
        if metrics is None:
            raise RuntimeExecutionError(
                "RUNTIME_CONFIGURATION_ERROR",
                False,
                "TASK",
                "Fake Panel Script의 발화 지표가 없습니다.",
                "editorial.review",
                "panel_reaction_script",
                {"segment_id": segment_id},
            )
        word_count = metrics.get("spoken_word_count")
        speaker_ids = metrics.get("speaker_ids")
        if not isinstance(word_count, int) or not isinstance(speaker_ids, list):
            raise RuntimeExecutionError(
                "RUNTIME_CONFIGURATION_ERROR",
                False,
                "TASK",
                "Fake Panel Script의 발화 지표 형식이 올바르지 않습니다.",
                "editorial.review",
                "panel_reaction_script",
                {"segment_id": segment_id},
            )
        estimated_duration = round(word_count * 60.0 / reading_rate_wpm, 2)
        non_speech_duration = round(float(duration) - estimated_duration, 2)
        if non_speech_duration <= 0:
            raise RuntimeExecutionError(
                "RUNTIME_CONFIGURATION_ERROR",
                False,
                "TASK",
                "Fake Panel 발화가 계획시간을 초과합니다.",
                "editorial.review",
                "panel_reaction_script",
                {"segment_id": segment_id},
            )
        panel_segments.append(
            {
                "segment_id": segment_id,
                "reaction_segment_id": reaction_segment_id,
                "planned_duration_sec": float(duration),
                "spoken_word_count": word_count,
                "estimated_spoken_duration_sec": estimated_duration,
                "measured_duration_sec": estimated_duration,
                "action_duration_sec": 0.0,
                "non_speaking_duration_sec": non_speech_duration,
                "speaker_ids": speaker_ids,
                "non_speech_elements": [
                    {
                        "element_type": "GRAPHIC",
                        "duration_sec": non_speech_duration,
                        "time_class": "NON_SPEAKING",
                        "support_status": "SUPPORTED",
                        "source_reference": f"presentation_plan:{segment_id}",
                        "notes": "결정론적 Fixture의 근거 요약 Graphic",
                    }
                ],
            }
        )
        planned_panel_duration += float(duration)
        estimated_panel_spoken_duration += estimated_duration
    return {
        "language_unit": "KOREAN_EOJEOL",
        "estimation_assumptions": [
            "Panel Script의 한글·영문·숫자 토큰을 한국어 어절 단위로 센다.",
            "발화 외 Graphic 시간은 Presentation Segment 근거로 분리한다.",
        ],
        "method": "TABLE_READ",
        "reading_rate_wpm": reading_rate_wpm,
        "planned_runtime_sec": planned_runtime,
        "planned_panel_duration_sec": planned_panel_duration,
        "estimated_panel_spoken_duration_sec": round(
            estimated_panel_spoken_duration,
            2,
        ),
        "measured_panel_duration_sec": round(
            estimated_panel_spoken_duration,
            2,
        ),
        "panel_segments": panel_segments,
    }


def fake_editorial_review(
    project_id: str,
    artifacts: Mapping[str, object],
) -> dict[str, object]:
    """입력 Hash·근거·Runtime 추정을 포함한 Editorial Review Fixture를 만든다."""
    presentation_plan = artifacts.get("presentation_plan")
    panel_reaction_script = artifacts.get("panel_reaction_script")
    if not isinstance(presentation_plan, Mapping) or not isinstance(panel_reaction_script, str):
        raise RuntimeExecutionError(
            "RUNTIME_CONFIGURATION_ERROR",
            False,
            "TASK",
            "Editorial Review Fixture 입력이 누락되었습니다.",
            "editorial.review",
            None,
            {},
        )
    review: dict[str, object] = {
        "schema_family": "editorial-review",
        "schema_version": "1.2.0",
        "project_id": project_id,
        "reviewer": {
            "reviewer_id": "agent:continuity_critic",
            "role": "CONTINUITY_CRITIC",
        },
        "reviewed_at": "2026-08-28T00:00:00Z",
        "artifact_hashes": editorial_artifact_hashes(artifacts),
        "runtime_evidence": fake_runtime_evidence(
            presentation_plan,
            panel_reaction_script,
        ),
        "result": "PASS",
        "checks": {
            "broadcast_format": {
                "result": "PASS",
                "evidence": [
                    make_editorial_evidence(
                        artifacts,
                        "final_script",
                        "SEGMENT_ID",
                        "SEG-001",
                    )
                ],
                "notes": "모든 방송 Segment Marker와 Layer 순서를 확인함",
            },
            "absolute_time": {
                "result": "PASS",
                "evidence": [
                    make_editorial_evidence(
                        artifacts,
                        "actual_timeline",
                        "DOCUMENT",
                        "actual_timeline",
                    )
                ],
                "notes": "대본의 시간 언급과 실제 사건 순서를 대조함",
            },
            "dialogue_naturalness": {
                "result": "PASS",
                "evidence": [
                    make_editorial_evidence(
                        artifacts,
                        "panel_reaction_script",
                        "SEGMENT_ID",
                        "SEG-002",
                    )
                ],
                "notes": "Panel 발화가 기능과 화자 Persona에 맞는지 검토함",
            },
            "panel_reaction_function": {
                "result": "PASS",
                "evidence": [
                    make_editorial_evidence(
                        artifacts,
                        "reaction_segments",
                        "REACTION_SEGMENT_ID",
                        "RSEG-001",
                    )
                ],
                "notes": "가설 생성·반론·수정 기능과 방송 Cue를 대조함",
            },
            "audience_belief": {
                "result": "PASS",
                "evidence": [
                    make_editorial_evidence(
                        artifacts,
                        "audience_belief",
                        "DOCUMENT",
                        "audience_belief",
                    )
                ],
                "notes": "관객이 공개 전 사실을 알지 못하도록 Reveal 순서를 확인함",
            },
            "shootability": {
                "result": "PASS",
                "evidence": [
                    make_editorial_evidence(
                        artifacts,
                        "shooting_script",
                        "DOCUMENT",
                        "shooting_script",
                    )
                ],
                "notes": "장면과 Production Cue가 촬영 가능한 단위인지 확인함",
            },
            "victim_dignity": {
                "result": "PASS",
                "evidence": [
                    make_editorial_evidence(
                        artifacts,
                        "final_script",
                        "SEGMENT_ID",
                        "SEG-005",
                    )
                ],
                "notes": "피해 인물을 선정적으로 대상화하는 표현이 없음을 확인함",
            },
        },
        "issues": [],
    }
    production_config = artifacts.get("production_config")
    reenactment_report = artifacts.get("reenactment_export_report")
    if (
        isinstance(production_config, Mapping)
        and production_config.get("target_reenactment_minutes") is not None
        and isinstance(reenactment_report, Mapping)
    ):
        runtime_status = reenactment_report.get("runtime_status")
        planned_duration = (
            runtime_status.get("planned_duration_sec")
            if isinstance(runtime_status, Mapping)
            else None
        )
        if isinstance(planned_duration, int | float) and not isinstance(
            planned_duration,
            bool,
        ):
            review["reenactment_runtime_evidence"] = reenactment_runtime_evidence(
                reenactment_report,
                "TABLE_READ",
                float(planned_duration),
                float(planned_duration),
            )
    crime_event = artifacts.get("crime_event_contract")
    if isinstance(crime_event, Mapping):
        reveal_targets = crime_event.get("reveal_targets")
        target_records = [item for item in reveal_targets or [] if isinstance(item, Mapping)]
        semantic_assessments: list[dict[str, object]] = [
            {
                "assessment_id": "ASSESS-01",
                "category": "CRIME_EVENT_REALIZATION",
                "subject_id": str(crime_event.get("event_id")),
                "status": "EVIDENCED",
                "evidence": [
                    make_editorial_evidence(
                        artifacts,
                        "final_script",
                        "SEGMENT_ID",
                        "SEG-005",
                    )
                ],
                "notes": "행동과 피해 인과가 실제 Drama 발췌에서 확인됨",
            },
            {
                "assessment_id": "ASSESS-02",
                "category": "NARRATION_FUNCTION",
                "subject_id": "NARRATION",
                "status": "EVIDENCED",
                "evidence": [
                    make_editorial_evidence(
                        artifacts,
                        "final_script",
                        "SEGMENT_ID",
                        "SEG-003",
                    )
                ],
                "notes": "내레이션이 내부 인물의 주관적 해석을 전달함",
            },
            {
                "assessment_id": "ASSESS-03",
                "category": "PANEL_FUNCTION",
                "subject_id": "PANEL_REACTION",
                "status": "EVIDENCED",
                "evidence": [
                    make_editorial_evidence(
                        artifacts,
                        "final_script",
                        "SEGMENT_ID",
                        "SEG-002",
                    )
                ],
                "notes": "패널의 감정 반응과 용의자 추적 기능이 방송 발췌에 나타남",
            },
            {
                "assessment_id": "ASSESS-04",
                "category": "CLUE_AND_EVIDENCE_COHERENCE",
                "subject_id": "FINAL_REVEAL_EVIDENCE",
                "status": "EVIDENCED",
                "evidence": [
                    make_editorial_evidence(
                        artifacts,
                        "final_script",
                        "SEGMENT_ID",
                        "SEG-005",
                    )
                ],
                "notes": "후반 공개가 앞선 단서와 모순되지 않음",
            },
        ]
        development_functions = mapping_values(crime_event.get("development_functions"))
        semantic_subjects = [
            (
                "DEVELOPMENT_FUNCTION",
                str(item.get("development_function_id")),
                "필수 범죄 전개 기능이 실제 Drama 발췌에서 확인됨",
            )
            for item in development_functions
            if isinstance(item.get("development_function_id"), str)
        ]
        core_action_type = crime_event.get("core_action_type")
        if isinstance(core_action_type, str):
            semantic_subjects.append(
                (
                    "CRIME_ACTION",
                    core_action_type,
                    "범죄 행동이 실제 Drama 발췌에서 확인됨",
                )
            )
        semantic_subjects.extend(
            (
                "HARM_RESULT",
                harm_id,
                "범죄 피해 결과가 실제 Drama 발췌에서 확인됨",
            )
            for harm_id in string_values(crime_event.get("harm_ids"))
        )
        for category, subject_id, notes in semantic_subjects:
            semantic_assessments.append(
                {
                    "assessment_id": f"ASSESS-{len(semantic_assessments) + 1:02d}",
                    "category": category,
                    "subject_id": subject_id,
                    "status": "EVIDENCED",
                    "evidence": [
                        make_editorial_evidence(
                            artifacts,
                            "final_script",
                            "SEGMENT_ID",
                            "SEG-005",
                        )
                    ],
                    "notes": notes,
                }
            )
        for target in target_records:
            target_id = target.get("reveal_target_id")
            semantic_assessments.append(
                {
                    "assessment_id": f"ASSESS-{len(semantic_assessments) + 1:02d}",
                    "category": "REVEAL_TIMING",
                    "subject_id": str(target_id),
                    "status": "EVIDENCED",
                    "evidence": [
                        make_editorial_evidence(
                            artifacts,
                            "final_script",
                            "SEGMENT_ID",
                            "SEG-005" if len(semantic_assessments) < 13 else "SEG-006",
                        )
                    ],
                    "notes": "계획된 후반 Segment에서 공개됨",
                }
            )
        for target in target_records:
            target_id = target.get("reveal_target_id")
            semantic_assessments.append(
                {
                    "assessment_id": f"ASSESS-{len(semantic_assessments) + 1:02d}",
                    "category": "PREMATURE_DISCLOSURE_SCAN",
                    "subject_id": str(target_id),
                    "status": "NOT_DISCLOSED",
                    "evidence": [
                        make_editorial_evidence(
                            artifacts,
                            "final_script",
                            "SEGMENT_ID",
                            "SEG-003",
                        )
                    ],
                    "notes": (
                        "예정 공개 전 DRAMA·NARRATION·PANEL·NEWS·DOCUMENT·INTERVIEW "
                        "Layer에서 정답 누설이 없음을 검토함"
                    ),
                }
            )
        review["semantic_assessments"] = semantic_assessments
    return review


def story_document(
    project_id: str,
    source_mode: str,
    selection: Mapping[str, str],
    reference_profile: Mapping[str, object] | None,
) -> dict[str, object]:
    """승인 Variation을 그대로 구체화한 Story DNA Fixture를 만든다."""
    embedded_profile: dict[str, object] = {}
    if source_mode == "REFERENCE_INSPIRED":
        if reference_profile is None:
            raise RuntimeExecutionError(
                "RUNTIME_CONFIGURATION_ERROR",
                False,
                "TASK",
                "Reference Story Fixture에 정제 Profile이 없습니다.",
                "story.design_dna",
                "reference_profile",
                {},
            )
        embedded_profile = {
            "reference_profile": {
                key: value
                for key, value in reference_profile.items()
                if key not in {"project_id", "mode", "$schema"}
            }
        }
    raw_responsible_structure = selection.get("responsible_agent_structure")
    responsible_structure = (
        raw_responsible_structure if isinstance(raw_responsible_structure, str) else ""
    )
    derived_culprit_structure = {
        "SINGLE_AGENT": "SINGLE",
        "DUAL_AGENTS": "DUAL",
        "COMPLICIT_GROUP": "MULTIPLE",
    }.get(responsible_structure, "SINGLE")
    return {
        "$schema": "../../../STANDARD/schemas/story_dna.schema.json",
        "schema_family": "story-dna",
        "schema_version": "1.3.0",
        "project_id": project_id,
        "story_source_mode": source_mode,
        **embedded_profile,
        "story_dna": {
            "mystery_type": selection["mystery_type"],
            "architecture": selection["architecture"],
            "protagonist_role": selection["protagonist_role"],
            "perspective": selection["perspective"],
            "narrator_reliability": "RELIABLE",
            "timeline_style": selection["timeline_style"],
            "incident_type": selection.get("incident_type", selection.get("primary_crime")),
            "setting": selection["setting"],
            "setting_logic": ["ACCESS_LOG", "MACHINE_LOG", "SHIFT_CHANGE"],
            "culprit_structure": selection.get(
                "culprit_structure",
                derived_culprit_structure,
            ),
            "causal_truth": (
                "가해자의 의도적 범죄 행위가 피해와 은폐를 낳았고 기록이 책임을 드러냈다."
            ),
            "primary_twist": selection["primary_twist"],
            "secondary_twists": ["TW-10_CAUSALITY"],
            "information_mechanism": [selection.get("information_mechanism", "MACHINE_LOG")],
            "clue_mechanism": [selection.get("clue_mechanism", "TIMESTAMP")],
            "motive_class": selection.get("motive_category", "UNKNOWN"),
            "emotional_engine": "GUILT",
            "relationship_engine": {
                "primary": selection["relationship_engine"],
                "secondary": ["WORKPLACE_SOLIDARITY"],
                "protagonist_counterpart_role": "MISSING_COWORKER",
            },
            "pressure_engine": {
                "source": selection["pressure_engine"],
                "escalation": "COUNTDOWN",
                "stakes": ["LIFE", "EMPLOYMENT", "PUBLIC_SAFETY"],
            },
            "dramatic_engine": {
                "primary": selection["dramatic_engine"],
                "secondary": ["SYSTEM_MISTRUST"],
                "audience_emotion_curve": ["UNEASE", "SUSPICION", "URGENCY", "RELIEF", "GRIEF"],
            },
            "thematic_question": "개인의 실수와 시스템의 책임은 어디에서 갈리는가?",
            "audience_experience": {
                "initial_belief": "누군가 실종을 은폐했다.",
                "midpoint_shift": "주인공의 기억과 기계 기록이 서로 충돌한다.",
                "final_reframe": "흩어진 기록은 사고가 아니라 의도적 범죄와 책임 주체를 가리켰다.",
            },
            "reveal_mode": selection.get("reveal_mode", "TIMELINE_RECONSTRUCTION"),
            "ending_type": "BITTERSWEET",
            **(
                {"episode_theme": selection["episode_theme"]}
                if "episode_theme" in selection
                else {}
            ),
        },
    }


def context_artifacts(request: LLMRequest) -> dict[str, object]:
    """컴파일된 비신뢰 Context의 Artifact Content를 이름으로 색인한다."""
    start_marker = '<CONTEXT_DATA instructional="false">\n'
    end_marker = "\n</CONTEXT_DATA>"
    user_messages = [message.content for message in request.messages if message.role == "user"]
    context_messages = [
        message for message in user_messages if start_marker in message and end_marker in message
    ]
    if len(context_messages) != 1:
        raise RuntimeExecutionError(
            "RUNTIME_CONFIGURATION_ERROR",
            False,
            "TASK",
            "FakeProvider는 단일 User Prompt를 요구합니다.",
            request.metadata.get("task_id"),
            None,
            {
                "user_message_count": len(user_messages),
                "context_message_count": len(context_messages),
            },
        )
    content = context_messages[0]
    start = content.find(start_marker)
    end = content.find(end_marker, start + len(start_marker))
    if start < 0 or end < 0:
        raise RuntimeExecutionError(
            "RUNTIME_CONFIGURATION_ERROR",
            False,
            "TASK",
            "FakeProvider Prompt에 Context Data 구간이 없습니다.",
            request.metadata.get("task_id"),
            None,
            {},
        )
    parsed: object = json.loads(content[start + len(start_marker) : end])
    if not isinstance(parsed, list):
        raise RuntimeExecutionError(
            "RUNTIME_CONFIGURATION_ERROR",
            False,
            "TASK",
            "FakeProvider Context Data가 배열이 아닙니다.",
            request.metadata.get("task_id"),
            None,
            {},
        )
    artifacts: dict[str, object] = {}
    for item in parsed:
        if not isinstance(item, Mapping):
            continue
        artifact_name = item.get("artifact_name")
        artifact = item.get("content")
        if not isinstance(artifact_name, str) or not isinstance(artifact, Mapping | str):
            raise RuntimeExecutionError(
                "RUNTIME_CONFIGURATION_ERROR",
                False,
                "TASK",
                "FakeProvider Context Artifact 형식이 올바르지 않습니다.",
                request.metadata.get("task_id"),
                artifact_name if isinstance(artifact_name, str) else None,
                {},
            )
        artifacts[artifact_name] = dict(artifact) if isinstance(artifact, Mapping) else artifact
    return artifacts


def context_artifact(request: LLMRequest, artifact_name: str) -> Mapping[str, object] | None:
    """컴파일된 비신뢰 Context에서 지정 JSON Artifact를 읽는다."""
    artifact = context_artifacts(request).get(artifact_name)
    if artifact is None:
        return None
    if not isinstance(artifact, Mapping):
        raise RuntimeExecutionError(
            "RUNTIME_CONFIGURATION_ERROR",
            False,
            "TASK",
            "FakeProvider Context Artifact가 JSON 객체가 아닙니다.",
            request.metadata.get("task_id"),
            artifact_name,
            {},
        )
    return artifact


def screenplay_units_mode(request: LLMRequest) -> bool:
    """현재 Fake Task가 새 구조화 Script 경로인지 반환한다."""
    production_config = context_artifact(request, "production_config")
    return (
        production_config is not None
        and production_config.get("script_source_mode") == "SCREENPLAY_UNITS"
    )


def fake_clue_matrix(
    request: LLMRequest,
    project_id: str,
    selection: Mapping[str, str],
) -> dict[str, object]:
    """Script mode에 맞는 Legacy 또는 명시적 Reveal Clue Fixture를 만든다."""
    common: dict[str, object] = {
        "project_id": project_id,
        **(
            {
                "final_proof_mechanism": selection["final_proof_mechanism"],
                "technical_dependency_level": selection["technical_dependency_level"],
            }
            if "final_proof_mechanism" in selection
            and "technical_dependency_level" in selection
            else {}
        ),
    }
    base_clues: list[dict[str, object]] = [
        {
            "clue_id": "CLUE-01",
            "role": "CORE",
            "evidence_class": "RELATIONAL",
            "independent_ground_id": "GROUND-01",
            "supports_final_reveal": True,
            "introduced_scene_order": 1,
            "introduced_scene_id": "SCN-01",
            "resolved_scene_order": 2,
            "resolved_scene_id": "SCN-02",
        },
        {
            "clue_id": "CLUE-02",
            "role": "CORE",
            "evidence_class": "BEHAVIORAL",
            "independent_ground_id": "GROUND-02",
            "supports_final_reveal": True,
            "introduced_scene_order": 1,
            "introduced_scene_id": "SCN-01",
            "resolved_scene_order": 2,
            "resolved_scene_id": "SCN-02",
        },
    ]
    if not screenplay_units_mode(request):
        return {**common, "clues": base_clues}
    versioned_clues = [
        {
            **base_clues[0],
            "reveal_mode": "SEEDED_REINTERPRETATION",
            "surface_meaning": "기록 공백은 피해자의 자발적 이탈처럼 보인다.",
            "actual_meaning": "기록 공백은 가해자가 사건을 숨기려 만든 흔적이다.",
            "first_seen_scene_id": "SCN-01",
            "reveal_scene_id": "SCN-02",
            "recontextualized_scene_ids": ["SCN-01"],
        },
        {
            **base_clues[1],
            "reveal_mode": "INTENTIONAL_NON_MYSTERY_DISCLOSURE",
            "reveal_scene_id": "SCN-02",
        },
    ]
    return {
        "$schema": "../../../STANDARD/schemas/clue_matrix.schema.json",
        "schema_family": "clue-matrix",
        "schema_version": "1.1.0",
        **common,
        "clues": versioned_clues,
    }


def first_identifier(
    document: Mapping[str, object],
    collection_field: str,
    identifier_field: str,
    task_id: str,
    artifact_name: str,
) -> str:
    """Fixture 입력 배열의 첫 Canonical ID를 엄격하게 읽는다."""
    for record in mapping_values(document.get(collection_field)):
        identifier = record.get(identifier_field)
        if isinstance(identifier, str):
            return identifier
    raise RuntimeExecutionError(
        "RUNTIME_CONFIGURATION_ERROR",
        False,
        "TASK",
        "FakeProvider Fixture 입력에 Canonical ID가 없습니다.",
        task_id,
        artifact_name,
        {
            "collection_field": collection_field,
            "identifier_field": identifier_field,
        },
    )


def fake_character_state_transitions(
    request: LLMRequest,
    project_id: str,
) -> dict[str, object]:
    """Beat와 사건·단서에 결속된 Character State Transition을 만든다."""
    characters = context_artifact(request, "characters")
    facts = context_artifact(request, "facts")
    clues = context_artifact(request, "clue_matrix")
    crime_event = context_artifact(request, "crime_event_contract")
    if characters is None or facts is None or clues is None or crime_event is None:
        raise RuntimeExecutionError(
            "RUNTIME_CONFIGURATION_ERROR",
            False,
            "TASK",
            "State Transition Fixture 입력이 누락되었습니다.",
            "story.design_state_transitions",
            "character_state_transitions",
            {},
        )
    character_id = first_identifier(
        characters,
        "characters",
        "character_id",
        "story.design_state_transitions",
        "characters",
    )
    fact_id = first_identifier(
        facts,
        "facts",
        "fact_id",
        "story.design_state_transitions",
        "facts",
    )
    clue_id = first_identifier(
        clues,
        "clues",
        "clue_id",
        "story.design_state_transitions",
        "clue_matrix",
    )
    event_id = crime_event.get("event_id")
    if not isinstance(event_id, str):
        raise RuntimeExecutionError(
            "RUNTIME_CONFIGURATION_ERROR",
            False,
            "TASK",
            "State Transition Fixture에 Crime Event ID가 없습니다.",
            "story.design_state_transitions",
            "crime_event_contract",
            {},
        )
    return {
        "$schema": "../../../STANDARD/schemas/character_state_transitions.schema.json",
        "schema_family": "character-state-transitions",
        "schema_version": "1.0.0",
        "project_id": project_id,
        "narrative_path": "SURVIVOR_RECOVERY",
        "transitions": [
            {
                "transition_id": "CSTATE-001",
                "order": 1,
                "character_id": character_id,
                "scope_type": "BEAT",
                "scope_id": "BEAT-01",
                "state_before": "기록 공백을 피해자의 선택으로 오해한다.",
                "state_after": "기록 공백이 의도적으로 만들어졌다고 의심한다.",
                "triggers": {
                    "fact_ids": [fact_id],
                    "clue_ids": [],
                    "crime_event_ids": [],
                },
                "change_category": "BELIEF",
            },
            {
                "transition_id": "CSTATE-002",
                "order": 2,
                "character_id": character_id,
                "scope_type": "BEAT",
                "scope_id": "BEAT-02",
                "state_before": "기록 공백이 의도적으로 만들어졌다고 의심한다.",
                "state_after": "사건 기록을 보존하고 책임을 드러내기로 선택한다.",
                "triggers": {
                    "fact_ids": [],
                    "clue_ids": [clue_id],
                    "crime_event_ids": [event_id],
                },
                "change_category": "CHOICE",
                "recovery_function": "AGENCY_RECOVERY",
            },
        ],
    }


def screenplay_references(
    fact_ids: list[str],
    clue_ids: list[str],
    crime_event_ids: list[str],
    harm_ids: list[str],
    development_function_ids: list[str],
    reveal_target_ids: list[str],
) -> dict[str, object]:
    """Screenplay Unit의 여섯 Reference 배열을 빠짐없이 만든다."""
    return {
        "fact_ids": fact_ids,
        "clue_ids": clue_ids,
        "crime_event_ids": crime_event_ids,
        "harm_ids": harm_ids,
        "development_function_ids": development_function_ids,
        "reveal_target_ids": reveal_target_ids,
    }


def screenplay_character_ids(characters: Mapping[str, object]) -> list[str]:
    """Canonical Character ID를 문서 순서로 반환한다."""
    return [
        str(record["character_id"])
        for record in mapping_values(characters.get("characters"))
        if isinstance(record.get("character_id"), str)
    ]


def fake_screenplay_units(
    request: LLMRequest,
    project_id: str,
    source_truth: str,
) -> dict[str, object]:
    """Approved 구조 입력만 사용해 검증 가능한 Screenplay Unit Fixture를 만든다."""
    characters = context_artifact(request, "characters")
    viewer_timeline = context_artifact(request, "viewer_timeline")
    clues = context_artifact(request, "clue_matrix")
    crime_event = context_artifact(request, "crime_event_contract")
    scene_cards = context_artifact(request, "scene_cards")
    if characters is None or viewer_timeline is None or clues is None or crime_event is None:
        raise RuntimeExecutionError(
            "RUNTIME_CONFIGURATION_ERROR",
            False,
            "TASK",
            "Screenplay Unit Fixture 입력이 누락되었습니다.",
            "script.compose_screenplay_units",
            "screenplay_units",
            {},
        )
    character_ids = screenplay_character_ids(characters)
    fact_ids = [
        str(record["fact_id"])
        for record in mapping_values(viewer_timeline.get("reveals"))
        if isinstance(record.get("fact_id"), str)
    ]
    clue_ids = [
        str(record["clue_id"])
        for record in mapping_values(clues.get("clues"))
        if isinstance(record.get("clue_id"), str)
    ]
    event_id = crime_event.get("event_id")
    harm_ids = string_values(crime_event.get("harm_ids"))
    development_ids = [
        str(record["development_function_id"])
        for record in mapping_values(crime_event.get("development_functions"))
        if isinstance(record.get("development_function_id"), str)
        and record.get("required") is True
    ]
    reveal_ids = [
        str(record["reveal_target_id"])
        for record in mapping_values(crime_event.get("reveal_targets"))
        if isinstance(record.get("reveal_target_id"), str)
    ]
    method = crime_event.get("non_actionable_method_summary")
    immediate_harm = crime_event.get("immediate_harm")
    lasting_harm = crime_event.get("lasting_harm")
    if (
        not character_ids
        or len(fact_ids) < 2
        or len(clue_ids) < 2
        or not isinstance(event_id, str)
        or not harm_ids
        or not development_ids
        or not all(isinstance(value, str) for value in (method, immediate_harm, lasting_harm))
    ):
        raise RuntimeExecutionError(
            "RUNTIME_CONFIGURATION_ERROR",
            False,
            "TASK",
            "Screenplay Unit Fixture의 인물·Fact·Clue·사건 입력이 불완전합니다.",
            "script.compose_screenplay_units",
            "screenplay_units",
            {
                "character_count": len(character_ids),
                "fact_count": len(fact_ids),
                "clue_count": len(clue_ids),
            },
        )
    primary_speaker = character_ids[0]
    secondary_speaker = character_ids[min(1, len(character_ids) - 1)]
    audience_labels = {
        "ORIGINAL_FICTION": "본 이야기는 창작입니다.",
        "VERIFIED_TRUE_CASE": "실제 사건을 바탕으로 재구성했습니다.",
        "INSPIRED_BY_TRUE_EVENTS": "실제 사건에서 모티프를 얻어 각색했습니다.",
    }
    audience_label = audience_labels.get(source_truth)
    if audience_label is None:
        raise RuntimeExecutionError(
            "RUNTIME_CONFIGURATION_ERROR",
            False,
            "TASK",
            "Screenplay Unit Fixture의 Source Truth 분류를 지원하지 않습니다.",
            "script.compose_screenplay_units",
            "production_config",
            {"source_truth_classification": source_truth},
        )
    empty_refs = screenplay_references([], [], [], [], [], [])
    crime_refs = screenplay_references(
        [fact_ids[1]],
        clue_ids,
        [event_id],
        harm_ids,
        development_ids,
        reveal_ids,
    )
    title = "교대 기록의 7분"
    if scene_cards is not None:
        raw_scenes = scene_cards.get("scenes")
        if not isinstance(raw_scenes, list) or len(raw_scenes) < 2:
            raise RuntimeExecutionError(
                "RUNTIME_CONFIGURATION_ERROR",
                False,
                "TASK",
                "Screenplay Unit Fixture에는 두 Scene Card가 필요합니다.",
                "script.compose_screenplay_units",
                "scene_cards",
                {},
            )
    return {
        "$schema": "../../../STANDARD/schemas/screenplay_units.schema.json",
        "schema_family": "screenplay-units",
        "schema_version": "1.0.0",
        "project_id": project_id,
        "title": title,
        "source_truth_classification": source_truth,
        "scenes": [
            {
                "scene_id": "SCN-01",
                "order": 1,
                "title": "기록의 공백",
                "time_layer": "COLD_OPEN",
                "location_id": "LOC-01",
                "segment_ids": ["SEG-001", "SEG-003"],
                "context": {
                    "location_description": "교대 기록을 확인하는 폐쇄된 통제실",
                    "time_description": "사건 당일 밤, 교대 직전",
                    "previous_scene_id": None,
                    "background_music_description": "낮게 이어지는 금속성 리듬",
                    "sound_cues": [
                        {
                            "sound_cue_id": "SOUND-001",
                            "order": 1,
                            "description": "기록 단말의 경고음이 한 번 울린다.",
                        }
                    ],
                    "opening_character_state": "기록 공백을 단순한 이탈로 받아들인다.",
                    "opening_emotional_state": "확신과 불안이 섞인 경계 상태",
                    "action_summary": "기록 공백과 현장 흔적을 처음 대조한다.",
                    "audience_information_gain": "공백 기록이 사건의 첫 단서임을 알게 된다.",
                },
                "units": [
                    {
                        "unit_id": "UNIT-001",
                        "order": 1,
                        "type": "SCREEN_TEXT",
                        "text": audience_label,
                        "segment_id": "SEG-001",
                        "references": deepcopy(empty_refs),
                    },
                    {
                        "unit_id": "UNIT-002",
                        "order": 2,
                        "type": "ACTION",
                        "text": "지안은 교대 기록의 7분 공백과 멈춘 표시등을 함께 확인한다.",
                        "segment_id": "SEG-001",
                        "references": screenplay_references(
                            [fact_ids[0]],
                            [clue_ids[0]],
                            [],
                            [],
                            [],
                            [],
                        ),
                    },
                    {
                        "unit_id": "UNIT-003",
                        "order": 3,
                        "type": "DIALOGUE",
                        "text": (
                            "이 공백은 누군가 떠났다는 기록이 아니라, "
                            "누군가 숨긴 기록일 수 있어."
                        ),
                        "segment_id": "SEG-001",
                        "speaker_id": primary_speaker,
                        "delivery": {"instruction": "확신을 누르고 낮게 말한다.", "pace": "SLOW"},
                        "references": deepcopy(empty_refs),
                    },
                    {
                        "unit_id": "UNIT-004",
                        "order": 4,
                        "type": "NARRATION",
                        "text": "그는 기록이 가리키는 빈 시간을 피해자의 선택으로 오해하고 있었다.",
                        "segment_id": "SEG-003",
                        "speaker_id": primary_speaker,
                        "delivery": {"instruction": "회고하듯 차분하게 읽는다.", "pace": "NORMAL"},
                        "references": deepcopy(empty_refs),
                    },
                ],
            },
            {
                "scene_id": "SCN-02",
                "order": 2,
                "title": "공백의 실제 의미",
                "time_layer": "PRESENT",
                "location_id": "LOC-02",
                "segment_ids": ["SEG-005"],
                "context": {
                    "location_description": "현장 기록과 피해 흔적이 보존된 조사 공간",
                    "time_description": "다음 날 새벽, 기록 대조 직후",
                    "previous_scene_id": "SCN-01",
                    "background_music_description": "리듬이 멈추고 낮은 현악음이 남는다.",
                    "sound_cues": [
                        {
                            "sound_cue_id": "SOUND-002",
                            "order": 1,
                            "description": "보존된 기록 파일이 열리는 소리",
                        }
                    ],
                    "opening_character_state": "기록 공백의 조작 가능성을 추적한다.",
                    "opening_emotional_state": "두려움보다 책임 확인이 앞선다.",
                    "action_summary": "범죄 행위와 피해 결과를 기록으로 확정한다.",
                    "audience_information_gain": "가해 행위와 피해 인과, 책임 주체가 드러난다.",
                    "retrospective_meaning": (
                        "첫 장면의 공백은 이탈이 아니라 범죄 은폐의 흔적이었다."
                    ),
                },
                "units": [
                    {
                        "unit_id": "UNIT-005",
                        "order": 1,
                        "type": "ACTION",
                        "text": (
                            f"사건 기록은 {method}을 보여 준다. "
                            f"그 결과 {immediate_harm}이 발생했고, "
                            f"{lasting_harm}으로 이어졌다."
                        ),
                        "segment_id": "SEG-005",
                        "references": crime_refs,
                    },
                    {
                        "unit_id": "UNIT-006",
                        "order": 2,
                        "type": "DIALOGUE",
                        "text": "이제 공백이 아니라, 누가 무엇을 선택했는지 기록하겠습니다.",
                        "segment_id": "SEG-005",
                        "speaker_id": secondary_speaker,
                        "delivery": {
                            "instruction": "또렷하고 흔들림 없이 말한다.",
                            "volume": "NORMAL",
                        },
                        "references": deepcopy(empty_refs),
                    },
                ],
            },
        ],
    }


def source_disclosure_label(request: LLMRequest) -> str:
    """Source Disclosure Artifact의 검증 대상 Audience Label을 읽는다."""
    disclosure = context_artifact(request, "source_disclosure")
    label_text = disclosure.get("audience_label_text") if disclosure is not None else None
    if not isinstance(label_text, str) or not label_text:
        raise RuntimeExecutionError(
            "RUNTIME_CONFIGURATION_ERROR",
            False,
            "TASK",
            "FakeProvider Script 생성에는 Audience Source Label이 필요합니다.",
            request.metadata.get("task_id"),
            "source_disclosure",
            {},
        )
    return label_text


def fake_production_footprint_enabled(request: LLMRequest) -> bool:
    """Project Constraint가 활성화한 제작 메타데이터 Fixture 여부를 반환한다."""
    project_constraints = context_artifact(request, "project_constraints")
    production_footprint = context_artifact(request, "production_footprint")
    return production_footprint is not None or (
        project_constraints is not None and production_footprint_enforced(project_constraints)
    )


def fake_scene_production_metadata(request: LLMRequest) -> list[dict[str, object]]:
    """현재 Character와 Timeline에서 두 Scene의 최소 제작 메타데이터를 만든다."""
    characters = context_artifact(request, "characters")
    actual_timeline = context_artifact(request, "actual_timeline")
    raw_characters = characters.get("characters") if characters is not None else None
    raw_events = actual_timeline.get("events") if actual_timeline is not None else None
    character_records = raw_characters if isinstance(raw_characters, list) else []
    event_records = raw_events if isinstance(raw_events, list) else []
    character_ids = [
        str(record["character_id"])
        for record in character_records
        if isinstance(record, Mapping) and isinstance(record.get("character_id"), str)
    ]
    location_ids = [
        str(record["location_id"])
        for record in event_records
        if isinstance(record, Mapping) and isinstance(record.get("location_id"), str)
    ]
    if not character_ids or not location_ids:
        raise RuntimeExecutionError(
            "RUNTIME_CONFIGURATION_ERROR",
            False,
            "TASK",
            "Production Footprint Fixture에는 Character와 Timeline Location이 필요합니다.",
            "scene.design",
            "scene_cards",
            {
                "character_count": len(character_ids),
                "location_count": len(location_ids),
            },
        )
    scene_locations = [location_ids[0], location_ids[min(1, len(location_ids) - 1)]]
    cast_ids = sorted(set(character_ids[:2]))
    return [
        {
            "location_id": location_id,
            "cast_ids": cast_ids,
            "child_actor_use": "NONE",
            "vehicle_scene": "NONE",
            "special_effect_level": "NONE",
            "graphic_violence": "NONE",
            "production_complexity": "LOW",
        }
        for location_id in scene_locations
    ]


def role_slots(prefix: str, count: int) -> list[str]:
    """요청 수만큼 Canonical Crime Role Slot을 만든다."""
    return [f"{prefix}-{index:02d}" for index in range(1, count + 1)]


def approved_brief_from_request(request: LLMRequest) -> Mapping[str, object] | None:
    """현재 승인 Candidate의 Event Brief를 Context에서 찾는다."""
    variations = context_artifact(request, "variation_candidates")
    briefs_document = context_artifact(request, "candidate_event_briefs")
    approved_id = variations.get("approved_candidate_id") if variations is not None else None
    raw_briefs = briefs_document.get("briefs") if briefs_document is not None else None
    if not isinstance(raw_briefs, list):
        return None
    return next(
        (
            brief
            for brief in raw_briefs
            if isinstance(brief, Mapping) and brief.get("candidate_id") == approved_id
        ),
        None,
    )


def planned_character_bindings(brief: Mapping[str, object]) -> dict[str, str]:
    """Role Slot마다 안정적인 Character ID를 배정한다."""
    offender_slots = brief.get("offender_role_slots")
    victim_slots = brief.get("victim_role_slots")
    protagonist_slot = brief.get("protagonist_role_slot")
    participant_slots = [
        slot
        for slot in [
            *(offender_slots if isinstance(offender_slots, list) else []),
            *(victim_slots if isinstance(victim_slots, list) else []),
        ]
        if isinstance(slot, str)
    ]
    unique_slots = list(dict.fromkeys(participant_slots))
    bindings = {slot: f"CHAR-{index:02d}" for index, slot in enumerate(unique_slots, 1)}
    if isinstance(protagonist_slot, str):
        bound_victim = (
            bindings.get(str(victim_slots[0]))
            if isinstance(victim_slots, list) and victim_slots
            else None
        )
        protagonist_character = (
            bound_victim
            if isinstance(bound_victim, str)
            else next(iter(bindings.values()), "CHAR-01")
        )
        bindings[protagonist_slot] = protagonist_character
    return bindings


def fake_candidate_event_briefs(
    request: LLMRequest,
    project_id: str,
    source_truth: str,
) -> dict[str, object]:
    """구조 후보마다 서로 다른 구체적 사건 Brief를 만든다."""
    variations = context_artifact(request, "variation_candidates")
    candidates = variations.get("candidates") if variations is not None else None
    if not isinstance(candidates, list):
        raise RuntimeExecutionError(
            "RUNTIME_CONFIGURATION_ERROR",
            False,
            "TASK",
            "Event Brief 생성용 Candidate 배열이 없습니다.",
            "variation.elaborate_crime_events",
            "variation_candidates",
            {},
        )
    fact_ledger = context_artifact(request, "verified_fact_ledger")
    raw_facts = fact_ledger.get("facts") if fact_ledger is not None else None
    fact_ids = [
        str(fact["fact_id"])
        for fact in mapping_values(raw_facts)
        if isinstance(fact.get("fact_id"), str)
    ]
    factual_claim_ids = fact_ids[:1]
    contexts = (
        (
            "피해자가 혼자 마감 근무를 한다는 반복된 관찰",
            "피해자가 더 이상의 사적 접근을 거절한 순간",
            "폐점 직전 출입구에서 퇴로를 막고 비선정적 폭력을 가함",
            "치료가 필요한 상해와 즉각적인 안전 상실",
            "업무 공간 복귀를 두려워하는 지속적 불안",
            "우발적 충돌이었다고 주장하며 접근 기록을 부인함",
            "동료의 목격과 출입 기록이 피해 진술을 뒷받침함",
            "서로 독립적인 목격과 기록이 책임 주체를 특정함",
        ),
        (
            "피해자의 귀가 시간이 일정하다는 생활 정보의 악용",
            "피해자가 관계 종료 의사를 분명히 전달한 날",
            "귀가 동선에서 반복 접근한 뒤 이동 자유를 제한함",
            "도움을 요청할 수 없는 시간 동안의 자유 박탈",
            "혼자 이동하기 어려워진 안전감 붕괴",
            "연락이 자발적이었다고 주장하며 강제성을 부정함",
            "예약된 약속 불참과 주변인의 시간 기록이 공백을 드러냄",
            "시간대별 증언이 합쳐져 계획된 접근과 책임을 확인함",
        ),
        (
            "공동 주거의 출입 권한과 가족 일정을 알고 있던 점",
            "경제 문제를 둘러싼 공개적인 책임 요구",
            "허락 없이 주거 공간에 들어와 위협으로 통제권을 행사함",
            "거주 공간의 안전 상실과 방어 중 입은 상처",
            "집에 머무르지 못하고 임시 거처를 전전하는 피해",
            "가족 간 오해였다고 축소하며 침입 사실을 부인함",
            "이웃의 신고 시각과 훼손된 출입 흔적이 침입을 확인함",
            "출입 권한 기록과 현장 증언이 행위자의 공동 책임을 입증함",
        ),
        (
            "업무 평가권을 이용해 피해자를 외부와 단절시킬 수 있던 위치",
            "피해자가 부당한 지시를 공식적으로 문제 삼은 직후",
            "밀폐된 업무 공간에 남겨 두어 외부 이동을 막음",
            "장시간 이동 자유 박탈과 공포 반응",
            "권한자와 단둘이 있는 상황을 회피하게 된 직업적 손실",
            "보안 절차였다고 둘러대며 피해자의 판단을 공격함",
            "예약된 통화의 중단과 동료의 수색이 장소를 특정함",
            "지시 기록과 현장 상태가 의도적 감금 책임을 연결함",
        ),
        (
            "공개 행사에서 피해자의 이동과 연락 상대를 반복 관찰한 정보",
            "피해자가 접근 금지 요구를 주변에 알린 직후",
            "여러 장소에서 기다리며 접근을 반복해 일상 동선을 위축시킴",
            "즉각적인 신변 위협과 대피 필요",
            "직장과 주거지를 바꾸게 된 장기적 생활 손실",
            "우연한 만남이 반복됐다고 주장하며 추적 의도를 부인함",
            "서로 다른 장소의 목격 기록이 반복 접근의 연속성을 드러냄",
            "독립된 기록의 시간 순서가 지속적 추적 책임을 확정함",
        ),
    )
    briefs: list[dict[str, object]] = []
    for index, candidate in enumerate(candidates):
        if not isinstance(candidate, Mapping):
            continue
        candidate_id = candidate.get("candidate_id")
        selection = candidate.get("selection")
        if not isinstance(candidate_id, str) or not isinstance(selection, Mapping):
            continue
        offender_structure = selection.get("responsible_agent_structure")
        victim_structure = selection.get("victim_structure")
        offender_count = (
            1
            if offender_structure == "SINGLE_AGENT"
            else 2
            if offender_structure == "DUAL_AGENTS"
            else 3
        )
        victim_count = 1 if victim_structure == "SINGLE_VICTIM" else 2
        offender_slots = role_slots("OFFENDER", offender_count)
        victim_slots = role_slots("VICTIM", victim_count)
        protagonist_slot = "PROTAGONIST-01"
        primary = selection.get("primary_crime")
        action = selection.get("core_action_type")
        functions = sorted(
            {
                function
                for family in development_families(primary, action)
                for function in DEFAULT_DEVELOPMENT_FUNCTIONS[family]
            }
        )
        causal = contexts[index % len(contexts)]
        classification = "ORIGINAL_FICTION" if source_truth == "ORIGINAL_FICTION" else "FACT"
        claim_ids = [] if classification == "ORIGINAL_FICTION" else factual_claim_ids
        field_evidence = {
            field: {"classification": classification, "claim_ids": claim_ids}
            for field in (
                "PRIMARY_CRIME",
                "CULPRIT",
                "MOTIVE",
                "METHOD",
                "HARM_RESULT",
                "LEGAL_OUTCOME",
            )
        }
        motive_summary = (
            "확인된 동기는 공개되지 않았다."
            if source_truth != "ORIGINAL_FICTION" and not factual_claim_ids
            else f"{selection.get('motive_category')} 욕구가 거절 이후 보복 선택으로 이어졌다."
        )
        reveal_summaries = {
            "CULPRIT": causal[7],
            "MOTIVE": motive_summary,
            "METHOD": causal[2],
            "HARM_RESULT": f"{causal[3]} 이후 {causal[4]}",
        }
        briefs.append(
            {
                "candidate_id": candidate_id,
                "candidate_selection_sha256": canonical_json_hash(selection),
                "primary_crime": primary,
                "core_action_type": action,
                "responsible_agent_structure": offender_structure,
                "victim_structure": victim_structure,
                "offender_role_slots": offender_slots,
                "victim_role_slots": victim_slots,
                "protagonist_role_slot": protagonist_slot,
                "relationship_context": selection.get("relationship_context"),
                "target_selection_reason": causal[0],
                "initiating_context": f"{causal[0]}이 사건 발생 전 접근 조건을 만들었다.",
                "trigger_event": causal[1],
                "motive_category": selection.get("motive_category"),
                "motive_summary": motive_summary,
                "non_actionable_method_summary": causal[2],
                "immediate_harm": causal[3],
                "lasting_harm": causal[4],
                "concealment_or_denial": causal[5],
                "discovery_path": causal[6],
                "responsibility_path": causal[7],
                "central_pursuit_question": (
                    "반복 접근과 피해를 선택한 책임 주체를 어떤 증거가 확인하는가?"
                ),
                "development_functions": [
                    {
                        "development_function_id": f"CDEV-{function_index:03d}",
                        "function_type": function,
                        "summary": f"{function} 기능을 인물의 선택과 결과 변화로 구현한다.",
                        "required": True,
                    }
                    for function_index, function in enumerate(functions, 1)
                ],
                "reveal_targets": [
                    {
                        "reveal_target_id": f"REVEAL-TARGET-{target_index:02d}",
                        "target_type": target_type,
                        "summary": reveal_summaries[target_type],
                        "planned_phase": "LATE",
                        "planned_segment_id": None,
                    }
                    for target_index, target_type in enumerate(
                        ("CULPRIT", "MOTIVE", "METHOD", "HARM_RESULT"),
                        1,
                    )
                ],
                "truth_basis": {
                    "source_truth_classification": source_truth,
                    "field_evidence": field_evidence,
                },
            }
        )
    return {
        "$schema": "../../../STANDARD/schemas/candidate_event_briefs.schema.json",
        "schema_family": "candidate-event-briefs",
        "schema_version": "1.0.0",
        "project_id": project_id,
        "briefs": briefs,
    }


def fake_candidate_evaluation(
    project_id: str,
    variations: Mapping[str, object],
    candidate_event_briefs: Mapping[str, object] | None,
    novelty_precheck: Mapping[str, object],
    candidate_eligibility: Mapping[str, object],
) -> dict[str, object]:
    """Runtime 회귀용 Candidate 평가 근거를 결정론적으로 만든다."""
    candidates = variations.get("candidates")
    raw_eligible_ids = candidate_eligibility.get("eligible_candidate_ids")
    if not isinstance(candidates, list) or not isinstance(raw_eligible_ids, list):
        raise RuntimeExecutionError(
            "RUNTIME_CONFIGURATION_ERROR",
            False,
            "TASK",
            "Candidate 평가용 Variation 또는 Novelty Precheck가 없습니다.",
            "variation.evaluate",
            "candidate_evaluation",
            {},
        )
    eligible_ids = {value for value in raw_eligible_ids if isinstance(value, str)}
    event_first = variations.get("variation_engine_version") == "2.1.0"
    score_fields = EVENT_SCORE_FIELDS if event_first else SCORE_FIELDS
    weights: dict[str, float] = (
        dict(EVENT_WEIGHTS)
        if event_first
        else {
            "crime_threat_score": 15.0,
            "psychological_immersion_score": 15.0,
            "trust_betrayal_score": 15.0,
            "victim_integrity_score": 15.0,
            "character_score": 10.0,
            "twist_score": 10.0,
            "novelty_score": 10.0,
            "production_score": 10.0,
        }
    )
    evaluations: list[dict[str, object]] = []
    for index, candidate in enumerate(candidates):
        if not isinstance(candidate, Mapping):
            continue
        candidate_id = candidate.get("candidate_id")
        if not isinstance(candidate_id, str):
            continue
        base_score = float(max(65, 92 - index * 3))
        dimension_scores = {
            field: (
                95.0 if field == "novelty_score" and candidate_id in eligible_ids else base_score
            )
            for field in score_fields
        }
        if candidate_id not in eligible_ids and "novelty_score" in dimension_scores:
            dimension_scores["novelty_score"] = 0.0
        total_score = round(
            sum(dimension_scores[field] * weights[field] / 100.0 for field in score_fields),
            2,
        )
        evaluations.append(
            {
                "candidate_id": candidate_id,
                "dimension_evidence": {
                    field: [f"{candidate_id}의 {field} 구조 선택을 검토했습니다."]
                    for field in score_fields
                },
                **dimension_scores,
                "total_score": total_score,
                "decision": "REJECTED",
                "decision_reason": "전체 적격 후보의 가중 점수를 비교합니다.",
            }
        )
    eligible = [record for record in evaluations if record["candidate_id"] in eligible_ids]
    if not eligible:
        raise RuntimeExecutionError(
            "GATE_REJECTED",
            False,
            "TASK",
            "추천할 Novelty PASS Candidate가 없습니다.",
            "variation.evaluate",
            "novelty_precheck",
            {"validation_code": "ALL_VARIATION_CANDIDATES_NOVELTY_FAILED"},
        )
    recommended = max(
        eligible,
        key=lambda record: float(cast(float, record["total_score"])),
    )
    recommended_id = cast(str, recommended["candidate_id"])
    for record in evaluations:
        if record["candidate_id"] == recommended_id:
            record["decision"] = "RECOMMENDED"
            record["decision_reason"] = "적격 후보 중 재계산 가중 점수가 가장 높습니다."
        else:
            record["decision_reason"] = "추천 후보보다 가중 점수가 낮거나 Novelty가 실패했습니다."
    input_hashes = candidate_evaluation_input_hashes(
        variations,
        candidate_event_briefs,
        novelty_precheck,
        candidate_eligibility,
    )
    return {
        "schema_family": "candidate-evaluation",
        "schema_version": "1.3.0" if event_first else "1.2.0",
        "project_id": project_id,
        "weights": weights,
        "input_hashes": input_hashes,
        "novelty_report_hash": input_hashes["novelty_precheck"],
        "recommended_candidate_id": recommended_id,
        "evaluations": evaluations,
    }


def true_story_case_dimensions(request: LLMRequest) -> dict[str, object]:
    """Source Truth Contract에서 Case 구조의 검증값과 미상값을 읽는다."""
    contract = context_artifact(request, "source_truth_contract")
    if contract is None:
        return {}
    result: dict[str, object] = {}
    field_mapping = {
        "verified_incident_type": "incident_type",
        "verified_setting": "setting",
        "verified_responsible_agent_structure": "responsible_agent_structure",
        "verified_legal_outcome": "legal_outcome",
    }
    for source_field, target_field in field_mapping.items():
        value = contract.get(source_field)
        if isinstance(value, str):
            result[target_field] = value
    return result


def true_story_character_outputs(
    request: LLMRequest,
    project_id: str,
) -> tuple[dict[str, object], dict[str, object], dict[str, object]]:
    """Source Subject ID를 명시적으로 보존한 Character 묶음을 만든다."""
    subject_document = context_artifact(request, "source_subjects")
    truth_contract = context_artifact(request, "source_truth_contract")
    raw_subjects = subject_document.get("subjects") if subject_document is not None else None
    if not isinstance(raw_subjects, list) or not raw_subjects:
        raise RuntimeExecutionError(
            "RUNTIME_CONFIGURATION_ERROR",
            False,
            "TASK",
            "사실 기반 Character 생성에는 Source Subject가 필요합니다.",
            "character.design",
            "source_subjects",
            {},
        )
    characters: list[dict[str, object]] = []
    event_brief = approved_brief_from_request(request)
    offender_slots = event_brief.get("offender_role_slots") if event_brief is not None else []
    victim_slots = event_brief.get("victim_role_slots") if event_brief is not None else []
    offender_index = 0
    victim_index = 0
    subject_to_character: dict[str, str] = {}
    knowledge_events: list[dict[str, object]] = []
    for index, raw_subject in enumerate(raw_subjects, 1):
        if not isinstance(raw_subject, Mapping):
            continue
        source_subject_id = raw_subject.get("source_subject_id")
        pseudonym = raw_subject.get("pseudonym")
        source_role = raw_subject.get("source_role")
        if not all(isinstance(value, str) for value in (source_subject_id, pseudonym, source_role)):
            continue
        character_id = f"CHAR-{index:02d}"
        source_subject_id_text = cast(str, source_subject_id)
        subject_to_character[source_subject_id_text] = character_id
        character: dict[str, object] = {
            "character_id": character_id,
            "name": cast(str, pseudonym),
            "role": cast(str, source_role),
            "source_subject_id": source_subject_id_text,
        }
        normalized_role = cast(str, source_role).upper()
        crime_role_slots: list[str] = []
        if (
            "OFFENDER" in normalized_role
            and isinstance(offender_slots, list)
            and offender_index < len(offender_slots)
            and isinstance(offender_slots[offender_index], str)
        ):
            crime_role_slots.append(cast(str, offender_slots[offender_index]))
            offender_index += 1
        if (
            "VICTIM" in normalized_role
            and isinstance(victim_slots, list)
            and victim_index < len(victim_slots)
            and isinstance(victim_slots[victim_index], str)
        ):
            crime_role_slots.append(cast(str, victim_slots[victim_index]))
            victim_index += 1
        if crime_role_slots:
            character["crime_role_slots"] = crime_role_slots
        if fake_production_footprint_enabled(request):
            character["production_role"] = "MAJOR"
        characters.append(character)
        related_fact_ids = raw_subject.get("related_fact_ids")
        if isinstance(related_fact_ids, list):
            for fact_order, fact_id in enumerate(related_fact_ids, 1):
                if isinstance(fact_id, str):
                    knowledge_events.append(
                        {
                            "character_id": character_id,
                            "fact_id": fact_id,
                            "learned_scene_order": min(fact_order, 2),
                        }
                    )
    if event_brief is not None:
        protagonist_slot = event_brief.get("protagonist_role_slot")
        first_victim_slot = (
            victim_slots[0]
            if isinstance(victim_slots, list) and victim_slots and isinstance(victim_slots[0], str)
            else None
        )
        for character in characters:
            raw_slots = character.get("crime_role_slots")
            if (
                isinstance(protagonist_slot, str)
                and isinstance(raw_slots, list)
                and first_victim_slot in raw_slots
            ):
                raw_slots.append(protagonist_slot)
                break
    raw_relationships = (
        truth_contract.get("verified_relationships") if truth_contract is not None else None
    )
    relationships: list[dict[str, object]] = []
    if isinstance(raw_relationships, list):
        for index, relationship in enumerate(raw_relationships, 1):
            if not isinstance(relationship, Mapping):
                continue
            from_subject = relationship.get("from_source_subject_id")
            to_subject = relationship.get("to_source_subject_id")
            relationship_type = relationship.get("relationship_type")
            if not all(
                isinstance(value, str) for value in (from_subject, to_subject, relationship_type)
            ):
                continue
            from_character = subject_to_character.get(cast(str, from_subject))
            to_character = subject_to_character.get(cast(str, to_subject))
            if from_character is None or to_character is None:
                continue
            relationships.append(
                {
                    "relationship_id": f"REL-{index:02d}",
                    "from": from_character,
                    "to": to_character,
                    "engine": cast(str, relationship_type),
                }
            )
    return (
        {"project_id": project_id, "characters": characters},
        {"project_id": project_id, "relationships": relationships},
        {"project_id": project_id, "knowledge_events": knowledge_events},
    )


def true_story_timeline_and_causal_graph(
    request: LLMRequest,
    project_id: str,
) -> tuple[dict[str, object], dict[str, object]]:
    """Verified Event ID를 Timeline과 Causal Graph에 그대로 연결한다."""
    event_document = context_artifact(request, "verified_event_ledger")
    character_document = context_artifact(request, "characters")
    raw_events = event_document.get("events") if event_document is not None else None
    raw_characters = (
        character_document.get("characters") if character_document is not None else None
    )
    if not isinstance(raw_events, list) or not raw_events:
        raise RuntimeExecutionError(
            "RUNTIME_CONFIGURATION_ERROR",
            False,
            "TASK",
            "사실 기반 Mystery 생성에는 Verified Event가 필요합니다.",
            "mystery.design",
            "verified_event_ledger",
            {},
        )
    character_records = raw_characters if isinstance(raw_characters, list) else []
    subject_to_character = {
        str(character["source_subject_id"]): str(character["character_id"])
        for character in character_records
        if isinstance(character, Mapping)
        and isinstance(character.get("source_subject_id"), str)
        and isinstance(character.get("character_id"), str)
    }
    sorted_events = sorted(
        (event for event in raw_events if isinstance(event, Mapping)),
        key=lambda event: int(event.get("sequence", 0)),
    )
    timeline_events: list[dict[str, object]] = []
    causal_nodes: list[dict[str, object]] = []
    for index, event in enumerate(sorted_events, 1):
        verified_event_id = event.get("verified_event_id")
        statement = event.get("statement")
        setting = event.get("setting")
        raw_participants = event.get("participant_source_subject_ids")
        if not isinstance(verified_event_id, str) or not isinstance(statement, str):
            continue
        participant_ids = [
            subject_to_character[source_subject_id]
            for source_subject_id in raw_participants or []
            if isinstance(source_subject_id, str) and source_subject_id in subject_to_character
        ]
        start_minute = (index - 1) * 7
        timeline_events.append(
            {
                "event_id": f"EVT-{index:02d}",
                "source_event_id": verified_event_id,
                "start_minute": start_minute,
                "end_minute": start_minute + 7,
                "location_id": setting if isinstance(setting, str) else "UNKNOWN",
                "participant_ids": participant_ids,
                "description": statement,
            }
        )
        causal_nodes.append(
            {
                "node_id": f"CAUSE-{index:02d}",
                "source_event_id": verified_event_id,
                "type": "ROOT_CAUSE" if index == 1 else "RESOLUTION",
            }
        )
    if len(causal_nodes) < 2:
        raise RuntimeExecutionError(
            "RUNTIME_CONFIGURATION_ERROR",
            False,
            "TASK",
            "Causal Graph에는 순서가 검증된 Event가 둘 이상 필요합니다.",
            "mystery.design",
            "verified_event_ledger",
            {},
        )
    edges = [
        {"from": causal_nodes[index - 1]["node_id"], "to": causal_nodes[index]["node_id"]}
        for index in range(1, len(causal_nodes))
    ]
    causal_graph: dict[str, object] = {
        "project_id": project_id,
        "nodes": causal_nodes,
        "edges": edges,
        "fingerprint": {
            "root_cause": "VERIFIED_EVENT",
            "mechanism": "VERIFIED_SEQUENCE",
            "concealment": "SOURCE_LIMITATION",
            "discovery_path": "CLAIM_EVIDENCE_REVIEW",
            "resolution": "VERIFIED_OUTCOME",
        },
        "semantic_normalization": {
            "normalized_roles": ["SOURCE_SUBJECT", "VERIFIED_EVENT"],
            "character_function_chain": ["EVIDENCE_REVIEW", "TRUTH_BINDING"],
            "audience_hypothesis_transitions": ["CLAIM", "VERIFICATION"],
        },
    }
    return {"project_id": project_id, "events": timeline_events}, causal_graph


def crime_trace_artifacts(
    project_id: str,
    contract: Mapping[str, object],
    facts: Mapping[str, object],
    base_timeline: Mapping[str, object] | None,
    base_causal_graph: Mapping[str, object] | None,
) -> tuple[dict[str, object], dict[str, object], dict[str, object]]:
    """최종 사건 계약을 Timeline·Causal Graph·Viewer Reveal로 투영한다."""
    raw_base_events = base_timeline.get("events") if base_timeline is not None else None
    base_events = [deepcopy(dict(event)) for event in mapping_values(raw_base_events)]
    start_minute = max(
        (
            int(end_minute)
            for event in base_events
            if isinstance((end_minute := event.get("end_minute")), int | float)
        ),
        default=0,
    )
    event_id = str(contract.get("event_id"))
    actor_ids = string_values(contract.get("actor_ids"))
    victim_ids = string_values(contract.get("victim_ids"))
    harm_ids = string_values(contract.get("harm_ids"))
    trace_events: list[dict[str, object]] = [
        {
            "event_id": f"EVT-{len(base_events) + 1:02d}",
            "crime_event_id": event_id,
            "actor_ids": actor_ids,
            "victim_ids": victim_ids,
            "harm_ids": [],
            "event_type": "MOTIVE_OR_TRIGGER",
            "start_minute": start_minute,
            "end_minute": start_minute + 3,
            "location_id": "PRIMARY_LOCATION",
            "participant_ids": sorted(set(actor_ids + victim_ids)),
            "description": str(contract.get("trigger_event")),
        },
        {
            "event_id": f"EVT-{len(base_events) + 2:02d}",
            "crime_event_id": event_id,
            "actor_ids": actor_ids,
            "victim_ids": victim_ids,
            "harm_ids": harm_ids,
            "event_type": "CRIME_EVENT",
            "start_minute": start_minute + 3,
            "end_minute": start_minute + 7,
            "location_id": "PRIMARY_LOCATION",
            "participant_ids": sorted(set(actor_ids + victim_ids)),
            "description": str(contract.get("non_actionable_method_summary")),
        },
        {
            "event_id": f"EVT-{len(base_events) + 3:02d}",
            "crime_event_id": event_id,
            "actor_ids": actor_ids,
            "victim_ids": victim_ids,
            "harm_ids": harm_ids,
            "event_type": "HARM_RESULT",
            "start_minute": start_minute + 7,
            "end_minute": start_minute + 10,
            "location_id": "PRIMARY_LOCATION",
            "participant_ids": victim_ids,
            "description": (f"{contract.get('immediate_harm')} / {contract.get('lasting_harm')}"),
        },
    ]
    raw_facts = facts.get("facts")
    fact_ids = [
        str(fact.get("fact_id"))
        for fact in mapping_values(raw_facts)
        if isinstance(fact.get("fact_id"), str)
    ]
    if not fact_ids:
        fact_ids = ["FACT-01"]
    reveal_targets = mapping_values(contract.get("reveal_targets"))
    viewer: dict[str, object] = {
        "project_id": project_id,
        "reveals": [
            {
                "reveal_id": "REV-01",
                "scene_id": "SCN-01",
                "fact_id": fact_ids[0],
                "information": "첫 장면에서 관찰 가능한 사건 단서",
                "effect": "초기 가설을 형성한다.",
            },
            {
                "reveal_id": "REV-02",
                "scene_id": "SCN-02",
                "fact_id": fact_ids[min(1, len(fact_ids) - 1)],
                "information": "두 번째 장면에서 확인되는 사건 단서",
                "effect": "초기 가설을 수정한다.",
            },
            *[
                {
                    "reveal_id": f"REV-{index + 2:02d}",
                    "scene_id": "SCN-02",
                    "fact_id": fact_ids[(index - 1) % len(fact_ids)],
                    "reveal_target_id": target.get("reveal_target_id"),
                    "target_type": target.get("target_type"),
                    "intentional_prereveal": False,
                    "information": target.get("summary"),
                    "effect": "후반 공개가 사건의 책임과 결과를 확정한다.",
                }
                for index, target in enumerate(reveal_targets, 1)
            ],
        ],
    }
    raw_base_nodes = base_causal_graph.get("nodes") if base_causal_graph is not None else None
    raw_base_edges = base_causal_graph.get("edges") if base_causal_graph is not None else None
    base_nodes = [deepcopy(dict(node)) for node in mapping_values(raw_base_nodes)]
    base_edges = [deepcopy(dict(edge)) for edge in mapping_values(raw_base_edges)]
    if not any(node.get("type") == "ROOT_CAUSE" for node in base_nodes):
        base_nodes.insert(0, {"node_id": "ROOT-01", "type": "ROOT_CAUSE"})
    if not any(node.get("type") == "RESOLUTION" for node in base_nodes):
        base_nodes.append({"node_id": "RESOLUTION-01", "type": "RESOLUTION"})
    root_id = str(next(node["node_id"] for node in base_nodes if node.get("type") == "ROOT_CAUSE"))
    resolution_id = str(
        next(node["node_id"] for node in base_nodes if node.get("type") == "RESOLUTION")
    )
    trace_nodes: list[dict[str, object]] = [
        {
            "node_id": "MOTIVE-01",
            "type": "MOTIVE_OR_TRIGGER",
            "crime_event_id": event_id,
        },
        {
            "node_id": "CRIME-01",
            "type": "CRIME_EVENT",
            "crime_event_id": event_id,
            "actor_ids": actor_ids,
            "victim_ids": victim_ids,
            "harm_ids": harm_ids,
        },
        {
            "node_id": "HARM-01",
            "type": "HARM_RESULT",
            "crime_event_id": event_id,
            "harm_ids": harm_ids,
        },
        {
            "node_id": "DENIAL-01",
            "type": "CONCEALMENT_OR_DENIAL",
            "crime_event_id": event_id,
        },
        {
            "node_id": "DISCOVERY-01",
            "type": "DISCOVERY_PATH",
            "crime_event_id": event_id,
        },
        {
            "node_id": "RESPONSIBILITY-01",
            "type": "RESPONSIBILITY_CONFIRMATION",
            "crime_event_id": event_id,
        },
    ]
    trace_edges: list[dict[str, object]] = [
        {"from": root_id, "to": "MOTIVE-01"},
        {"from": "MOTIVE-01", "to": "CRIME-01"},
        {"from": "CRIME-01", "to": "HARM-01"},
        {"from": "HARM-01", "to": "DENIAL-01"},
        {"from": "DENIAL-01", "to": "DISCOVERY-01"},
        {"from": "DISCOVERY-01", "to": "RESPONSIBILITY-01"},
        {"from": "RESPONSIBILITY-01", "to": resolution_id},
    ]
    causal: dict[str, object] = {
        "project_id": project_id,
        "nodes": [*base_nodes, *trace_nodes],
        "edges": [*base_edges, *trace_edges],
        "fingerprint": (
            deepcopy(base_causal_graph.get("fingerprint"))
            if base_causal_graph is not None
            else {
                "root_cause": "OFFENDER_CHOICE",
                "mechanism": "INTERPERSONAL_CRIME",
                "concealment": "DENIAL_OR_CONCEALMENT",
                "discovery_path": "CORROBORATED_DISCOVERY",
                "resolution": "RESPONSIBILITY_CONFIRMED",
            }
        ),
        "semantic_normalization": (
            deepcopy(base_causal_graph.get("semantic_normalization"))
            if base_causal_graph is not None
            else {
                "normalized_roles": ["OFFENDER", "VICTIM", "PROTAGONIST"],
                "character_function_chain": ["THREAT", "HARM", "DISCOVERY"],
                "audience_hypothesis_transitions": ["SUSPICION", "PROOF", "RESPONSIBILITY"],
            }
        ),
    }
    return {"project_id": project_id, "events": [*base_events, *trace_events]}, viewer, causal


def fixture_artifacts(task_id: str, request: LLMRequest) -> list[dict[str, object]]:
    """Task ID를 검증 가능한 Agent Artifact Fixture에 대응한다."""
    metadata = request.metadata
    project_id = metadata.get("project_id")
    source_mode = metadata.get("story_source_mode")
    source_truth = metadata.get("source_truth_classification")
    if (
        not isinstance(project_id, str)
        or not isinstance(source_mode, str)
        or not isinstance(source_truth, str)
    ):
        raise RuntimeExecutionError(
            "RUNTIME_CONFIGURATION_ERROR",
            False,
            "TASK",
            "FakeProvider Metadata에 Project 정보가 없습니다.",
            task_id,
            None,
            {},
        )
    if task_id == "variation.elaborate_crime_events":
        return [
            {
                "artifact_name": "candidate_event_briefs",
                "media_type": "application/json",
                "content": fake_candidate_event_briefs(request, project_id, source_truth),
            }
        ]
    if task_id == "variation.evaluate":
        variations = context_artifact(request, "variation_candidates")
        novelty_precheck = context_artifact(request, "novelty_precheck")
        candidate_eligibility = context_artifact(request, "candidate_eligibility")
        candidate_event_briefs = context_artifact(request, "candidate_event_briefs")
        if variations is None or novelty_precheck is None or candidate_eligibility is None:
            raise RuntimeExecutionError(
                "RUNTIME_CONFIGURATION_ERROR",
                False,
                "TASK",
                "Candidate 평가용 Variation 또는 Novelty Context가 없습니다.",
                task_id,
                "candidate_evaluation",
                {},
            )
        return [
            {
                "artifact_name": "candidate_evaluation",
                "media_type": "application/json",
                "content": fake_candidate_evaluation(
                    project_id,
                    variations,
                    candidate_event_briefs,
                    novelty_precheck,
                    candidate_eligibility,
                ),
            }
        ]
    if task_id == "story.design_dna":
        return [
            {
                "artifact_name": "story_dna",
                "media_type": "application/json",
                "content": story_document(
                    project_id,
                    source_mode,
                    approved_selection(metadata),
                    context_artifact(request, "reference_profile"),
                ),
            }
        ]
    if task_id == "story.define_case":
        selected = approved_selection(metadata)
        event_brief = approved_brief_from_request(request)
        planned_bindings = (
            planned_character_bindings(event_brief) if event_brief is not None else {}
        )
        verified_case_fields: dict[str, object] = {}
        if source_truth in {"VERIFIED_TRUE_CASE", "INSPIRED_BY_TRUE_EVENTS"}:
            ledger = context_artifact(request, "verified_fact_ledger")
            ledger_facts = ledger.get("facts") if isinstance(ledger, Mapping) else None
            if not isinstance(ledger_facts, list) or not ledger_facts:
                raise RuntimeExecutionError(
                    "RUNTIME_CONFIGURATION_ERROR",
                    False,
                    "TASK",
                    "사실 기반 Case 생성에는 검증된 Fact Ledger가 필요합니다.",
                    task_id,
                    "verified_fact_ledger",
                    {},
                )
            crime_fact_types = ("CRIME_ACTION", "HARM_RESULT", "MOTIVE_STATUS", "RESPONSIBILITY")
            ledger_fact_records = mapping_values(ledger_facts)
            facts = [dict(fact) for fact in ledger_fact_records]
            verified_case_fields = true_story_case_dimensions(request)
        else:
            statements = (
                (
                    str(event_brief.get("non_actionable_method_summary"))
                    if event_brief is not None
                    else "반복 접근 뒤 비선정적 범죄 행위가 발생했다."
                ),
                (
                    str(event_brief.get("immediate_harm"))
                    if event_brief is not None
                    else "피해자는 즉각적인 안전 상실을 겪었다."
                ),
                (
                    str(event_brief.get("motive_summary"))
                    if event_brief is not None
                    else "행위자의 보복 동기가 사건을 촉발했다."
                ),
                (
                    str(event_brief.get("responsibility_path"))
                    if event_brief is not None
                    else "독립된 기록이 책임 주체를 확인했다."
                ),
            )
            crime_fact_types = ("CRIME_ACTION", "HARM_RESULT", "MOTIVE_STATUS", "RESPONSIBILITY")
            facts = [
                {
                    "fact_id": f"FACT-{index:02d}",
                    "statement": statement,
                    "classification": "DRAMATIZATION",
                    "normalized_statement_hash": sha256(
                        " ".join(statement.split()).casefold().encode()
                    ).hexdigest(),
                    "source_ids": [],
                    "basis_fact_ids": [],
                    "presented_as_fact": False,
                    "crime_fact_type": crime_fact_types[index - 1],
                    "crime_fact_types": [crime_fact_types[index - 1]],
                }
                for index, statement in enumerate(statements, 1)
            ]
        trace_fact_ids = [
            str(fact.get("fact_id")) for fact in facts if isinstance(fact.get("fact_id"), str)
        ]
        crime_fact_trace = [
            {
                "crime_fact_type": crime_fact_type,
                "fact_ids": [trace_fact_ids[index % len(trace_fact_ids)]],
            }
            for index, crime_fact_type in enumerate(crime_fact_types)
        ]
        return [
            {
                "artifact_name": "case_input",
                "media_type": "application/json",
                "content": {
                    "project_id": project_id,
                    "title_working": "교대 기록의 7분",
                    "source_type": (
                        "TRUE_STORY"
                        if source_truth == "VERIFIED_TRUE_CASE"
                        else "INSPIRED_BY_TRUE_EVENTS"
                        if source_truth == "INSPIRED_BY_TRUE_EVENTS"
                        else "FICTION"
                    ),
                    "central_mystery": (
                        event_brief.get("central_pursuit_question")
                        if event_brief is not None
                        else "작업자는 언제 통제 구역을 벗어났는가?"
                    ),
                    "final_truth": (
                        event_brief.get("responsibility_path")
                        if event_brief is not None
                        else "작업자는 정지한 이송 설비의 점검 공간에 갇혔다."
                    ),
                    "causal_truth": (
                        f"{event_brief.get('trigger_event')} 이후 "
                        f"{event_brief.get('non_actionable_method_summary')}"
                        if event_brief is not None
                        else "센서 차단과 교대 기록 오류가 구조 지연을 만들었다."
                    ),
                    "incident_type": verified_case_fields.get(
                        "incident_type",
                        selected.get("primary_crime", selected.get("incident_type")),
                    ),
                    "setting": verified_case_fields.get("setting", selected["setting"]),
                    **{
                        key: value
                        for key, value in verified_case_fields.items()
                        if key not in {"incident_type", "setting"}
                    },
                    "primary_crime": event_brief.get("primary_crime") if event_brief else None,
                    "responsible_actor_ids": [
                        planned_bindings[slot]
                        for slot in string_values(event_brief.get("offender_role_slots"))
                        if slot in planned_bindings
                    ]
                    if event_brief
                    else [],
                    "victim_ids": [
                        planned_bindings[slot]
                        for slot in string_values(event_brief.get("victim_role_slots"))
                        if slot in planned_bindings
                    ]
                    if event_brief
                    else [],
                    "motive_summary": event_brief.get("motive_summary") if event_brief else None,
                    "crime_method_summary": (
                        event_brief.get("non_actionable_method_summary") if event_brief else None
                    ),
                    "harm_result": (
                        f"{event_brief.get('immediate_harm')} / {event_brief.get('lasting_harm')}"
                        if event_brief
                        else None
                    ),
                    "final_case_truth": (
                        event_brief.get("responsibility_path") if event_brief else None
                    ),
                    "culprit": ("ROLE_BOUND_AFTER_CHARACTER_DESIGN" if event_brief else None),
                    "culprit_motive": (event_brief.get("motive_summary") if event_brief else None),
                    "restrictions": [],
                },
            },
            {
                "artifact_name": "facts",
                "media_type": "application/json",
                "content": {
                    "project_id": project_id,
                    "facts": facts,
                    "crime_fact_trace": crime_fact_trace,
                },
            },
        ]
    if task_id == "story.define_crime_psychology":
        selected = approved_selection(metadata)
        return [
            {
                "artifact_name": "crime_psychology",
                "media_type": "application/json",
                "content": {
                    "schema_family": "crime-psychology",
                    "schema_version": "1.0.0",
                    "project_id": project_id,
                    "applicable": True,
                    "threat_type": selected["threat_type"],
                    "trusted_domain": selected["trusted_domain"],
                    "safe_domain_betrayal": selected["safe_domain_betrayal"],
                    "safe_domain_expectation": "신뢰 관계에서는 안전과 정직을 기대한다.",
                    "psychological_pressure": "관계 단절과 평판 손실에 대한 압박이 누적된다.",
                    "early_warning_signals": [
                        {
                            "warning_signal_id": "WARN-01",
                            "actor_id": "CHAR-01",
                            "victim_id": "CHAR-02",
                            "scene_id": "SCN-01",
                            "order": 1,
                            "description": "사소한 경계 침범이 반복된다.",
                        }
                    ],
                    "boundary_erosion_steps": [
                        {
                            "boundary_step_id": "BOUND-01",
                            "actor_id": "CHAR-01",
                            "victim_id": "CHAR-02",
                            "scene_id": "SCN-01",
                            "order": 2,
                            "description": "거절을 개인적 배신으로 바꿔 말한다.",
                        }
                    ],
                    "control_tactics": [
                        {
                            "control_tactic_id": "CTRL-01",
                            "actor_id": "CHAR-01",
                            "victim_id": "CHAR-02",
                            "scene_id": "SCN-02",
                            "order": 3,
                            "description": "정보 접근을 통제한다.",
                        }
                    ],
                    "victim_exit_barriers": [
                        {
                            "exit_barrier_id": "EXIT-01",
                            "actor_id": "CHAR-01",
                            "victim_id": "CHAR-02",
                            "scene_id": "SCN-02",
                            "order": 4,
                            "description": "평판 손실을 암시한다.",
                        }
                    ],
                    "harm_mechanism": "신뢰를 이용해 판단과 행동 범위를 좁힌다.",
                    "harm_event": {
                        "harm_event_id": "HARM-01",
                        "actor_id": "CHAR-01",
                        "victim_id": "CHAR-02",
                        "scene_id": "SCN-02",
                        "order": 5,
                    },
                    "responsible_agent": "CHAR-01",
                    "responsible_agent_structure": selected["responsible_agent_structure"],
                    "responsible_agent_payoff": "행위 주체의 선택과 책임이 드러난다.",
                    "victim_agency_outcome": {
                        "victim_id": "CHAR-02",
                        "ending_scene_id": "SCN-02",
                        "outcome": "피해자가 증거를 보존하고 경계를 회복한다.",
                    },
                    "victim_agency_mode": selected["victim_agency_mode"],
                    "risk_signal_payoff": "초기 경고 신호가 후반 행동의 의미로 재해석된다.",
                    "episode_theme": selected["episode_theme"],
                },
            }
        ]
    if task_id == "character.design":
        if source_truth in {"VERIFIED_TRUE_CASE", "INSPIRED_BY_TRUE_EVENTS"}:
            characters, relationships, knowledge = true_story_character_outputs(
                request,
                project_id,
            )
            return [
                {
                    "artifact_name": "characters",
                    "media_type": "application/json",
                    "content": characters,
                },
                {
                    "artifact_name": "relationships",
                    "media_type": "application/json",
                    "content": relationships,
                },
                {
                    "artifact_name": "knowledge_matrix",
                    "media_type": "application/json",
                    "content": knowledge,
                },
            ]
        event_brief = approved_brief_from_request(request)
        if event_brief is None:
            default_characters: list[dict[str, object]] = [
                {"character_id": "CHAR-01", "name": "지안", "role": "SUSPECT"},
                {"character_id": "CHAR-02", "name": "태호", "role": "MISSING_COWORKER"},
            ]
        else:
            bindings = planned_character_bindings(event_brief)
            slots_by_character: dict[str, list[str]] = {}
            for role_slot, character_id in bindings.items():
                slots_by_character.setdefault(character_id, []).append(role_slot)
            default_characters = [
                {
                    "character_id": character_id,
                    "name": f"인물 {index}",
                    "role": role_slots_for_character[0].partition("-")[0],
                    "crime_role_slots": role_slots_for_character,
                }
                for index, (character_id, role_slots_for_character) in enumerate(
                    sorted(slots_by_character.items()),
                    1,
                )
            ]
        if fake_production_footprint_enabled(request):
            default_characters = [
                {**character, "production_role": "MAJOR"} for character in default_characters
            ]
        offender_slots = event_brief.get("offender_role_slots") if event_brief is not None else None
        victim_slots = event_brief.get("victim_role_slots") if event_brief is not None else None
        bindings = planned_character_bindings(event_brief) if event_brief is not None else {}
        relationship_from = (
            bindings.get(str(offender_slots[0]))
            if isinstance(offender_slots, list) and offender_slots
            else None
        )
        relationship_to = (
            bindings.get(str(victim_slots[0]))
            if isinstance(victim_slots, list) and victim_slots
            else None
        )
        return [
            {
                "artifact_name": "characters",
                "media_type": "application/json",
                "content": {
                    "project_id": project_id,
                    "characters": default_characters,
                },
            },
            {
                "artifact_name": "relationships",
                "media_type": "application/json",
                "content": {
                    "project_id": project_id,
                    "relationships": [
                        {
                            "relationship_id": "REL-01",
                            "from": relationship_from or str(default_characters[0]["character_id"]),
                            "to": relationship_to or str(default_characters[-1]["character_id"]),
                            "engine": (
                                str(event_brief.get("relationship_context"))
                                if event_brief is not None
                                else "TRUST_TO_RESPONSIBILITY"
                            ),
                        }
                    ],
                },
            },
            {
                "artifact_name": "knowledge_matrix",
                "media_type": "application/json",
                "content": {
                    "project_id": project_id,
                    "knowledge_events": [
                        {
                            "character_id": str(default_characters[0]["character_id"]),
                            "fact_id": "FACT-01",
                            "learned_scene_order": 1,
                        },
                        {
                            "character_id": str(default_characters[0]["character_id"]),
                            "fact_id": "FACT-02",
                            "learned_scene_order": 2,
                        },
                    ],
                },
            },
        ]
    if task_id == "mystery.design":
        selected = approved_selection(metadata)
        truth_timeline: dict[str, object] | None = None
        truth_causal_graph: dict[str, object] | None = None
        if source_truth in {"VERIFIED_TRUE_CASE", "INSPIRED_BY_TRUE_EVENTS"}:
            truth_timeline, truth_causal_graph = true_story_timeline_and_causal_graph(
                request,
                project_id,
            )
        crime_event = context_artifact(request, "crime_event_contract")
        fact_document = context_artifact(request, "facts")
        trace_timeline: dict[str, object] | None = None
        trace_viewer: dict[str, object] | None = None
        trace_causal: dict[str, object] | None = None
        if crime_event is not None and fact_document is not None:
            trace_timeline, trace_viewer, trace_causal = crime_trace_artifacts(
                project_id,
                crime_event,
                fact_document,
                truth_timeline,
                truth_causal_graph,
            )
        return [
            {
                "artifact_name": "actual_timeline",
                "media_type": "application/json",
                "content": trace_timeline
                if trace_timeline is not None
                else truth_timeline
                if truth_timeline is not None
                else {
                    "project_id": project_id,
                    "events": [
                        {
                            "event_id": "EVT-01",
                            "start_minute": 0,
                            "end_minute": 7,
                            "location_id": "CONTROL_ROOM",
                            "participant_ids": ["CHAR-01"],
                        },
                        {
                            "event_id": "EVT-02",
                            "start_minute": 7,
                            "end_minute": 15,
                            "location_id": "CONVEYOR_SHAFT",
                            "participant_ids": ["CHAR-02"],
                        },
                    ],
                },
            },
            {
                "artifact_name": "viewer_timeline",
                "media_type": "application/json",
                "content": trace_viewer
                if trace_viewer is not None
                else {
                    "project_id": project_id,
                    "reveals": [
                        {
                            "reveal_id": "REV-01",
                            "scene_id": "SCN-01",
                            "fact_id": "FACT-01",
                            "information": "기계 로그의 7분 공백",
                            "effect": "작업자 이탈 가능성을 의심한다.",
                        },
                        {
                            "reveal_id": "REV-02",
                            "scene_id": "SCN-02",
                            "fact_id": "FACT-02",
                            "information": "안전 센서의 점검 모드",
                            "effect": "기록 공백을 시스템 오류로 재해석한다.",
                        },
                    ],
                },
            },
            {
                "artifact_name": "audience_belief",
                "media_type": "application/json",
                "content": {
                    "project_id": project_id,
                    "belief_states": [
                        {
                            "scene_id": "SCN-01",
                            "belief": "작업자가 기록 공백을 이용해 이탈했다.",
                            "confidence": 0.65,
                            "known_fact_ids": ["FACT-01"],
                            "active_hypothesis_ids": ["HYP-01"],
                        },
                        {
                            "scene_id": "SCN-02",
                            "belief": "센서 차단이 작업자의 위치를 숨겼다.",
                            "confidence": 0.9,
                            "known_fact_ids": ["FACT-01", "FACT-02"],
                            "active_hypothesis_ids": [],
                        },
                    ],
                },
            },
            {
                "artifact_name": "clue_matrix",
                "media_type": "application/json",
                "content": fake_clue_matrix(request, project_id, selected),
            },
            {
                "artifact_name": "hypothesis_ledger",
                "media_type": "application/json",
                "content": {
                    "project_id": project_id,
                    "hypotheses": [{"hypothesis_id": "HYP-01", "status": "REJECTED"}],
                },
            },
            {
                "artifact_name": "causal_graph",
                "media_type": "application/json",
                "content": trace_causal
                if trace_causal is not None
                else truth_causal_graph
                if truth_causal_graph is not None
                else {
                    "project_id": project_id,
                    "nodes": [
                        {"node_id": "CAUSE-01", "type": "ROOT_CAUSE"},
                        {"node_id": "MECH-01", "type": "MECHANISM"},
                        {"node_id": "DISC-01", "type": "DISCOVERY"},
                        {"node_id": "RES-01", "type": "RESOLUTION"},
                    ],
                    "edges": [
                        {"from": "CAUSE-01", "to": "MECH-01"},
                        {"from": "MECH-01", "to": "DISC-01"},
                        {"from": "DISC-01", "to": "RES-01"},
                    ],
                    "fingerprint": {
                        "root_cause": "SENSOR_BYPASS",
                        "mechanism": "CONVEYOR_LOCK",
                        "concealment": "SHIFT_LOG_GAP",
                        "discovery_path": "MACHINE_LOG_RECONSTRUCTION",
                        "resolution": "MANUAL_RESCUE",
                    },
                    "semantic_normalization": {
                        "normalized_roles": [
                            "INDUSTRIAL_SITE",
                            "INTERNAL_ENTRAPMENT",
                            "MACHINE_LOG_DISCOVERY",
                        ],
                        "character_function_chain": [
                            "INITIAL_MISREAD",
                            "EVIDENCE_REINTERPRETATION",
                            "MANUAL_RESCUE",
                        ],
                        "audience_hypothesis_transitions": [
                            "APPARENT_DEPARTURE",
                            "SYSTEM_FAILURE",
                            "INTERNAL_ENTRAPMENT",
                        ],
                    },
                },
            },
        ]
    if task_id == "story.structure":
        selection = approved_selection(metadata)
        return [
            {
                "artifact_name": "beat_sheet",
                "media_type": "application/json",
                "content": {
                    "project_id": project_id,
                    "architecture": selection["architecture"],
                    "beats": [
                        {"beat_id": "BEAT-01", "type": "HOOK"},
                        {"beat_id": "BEAT-02", "type": "REVEAL"},
                    ],
                },
            },
            {
                "artifact_name": "retention_plan",
                "media_type": "application/json",
                "content": {
                    "project_id": project_id,
                    "checkpoints": [{"scene_id": "SCN-01", "function": "QUESTION"}],
                },
            },
        ]
    if task_id == "story.design_state_transitions":
        return [
            {
                "artifact_name": "character_state_transitions",
                "media_type": "application/json",
                "content": fake_character_state_transitions(request, project_id),
            }
        ]
    if task_id == "scene.design":
        scene_seconds = target_runtime_seconds(metadata) // 2
        crime_event = context_artifact(request, "crime_event_contract")
        scenes: list[dict[str, object]] = [
            {
                "scene_id": "SCN-01",
                "order": 1,
                "beat_id": "BEAT-01",
                "estimated_seconds": scene_seconds,
                "clue_ids": ["CLUE-01", "CLUE-02"],
                "knowledge_claims": [{"character_id": "CHAR-01", "fact_id": "FACT-01"}],
            },
            {
                "scene_id": "SCN-02",
                "order": 2,
                "beat_id": "BEAT-02",
                "estimated_seconds": scene_seconds,
                "clue_ids": ["CLUE-01", "CLUE-02"],
                "knowledge_claims": [{"character_id": "CHAR-01", "fact_id": "FACT-02"}],
            },
        ]
        if crime_event is not None:
            depiction_mode = crime_event.get("depiction_mode")
            realization_mode = {
                "DIRECT_NON_GRAPHIC": "DIRECT_ACTION",
                "IMPLIED": "IMPLIED_ACTION",
                "AFTERMATH_CAUSAL": "AFTERMATH_CAUSAL",
            }.get(str(depiction_mode), "IMPLIED_ACTION")
            scenes[1]["crime_realization"] = [
                {
                    "event_id": crime_event.get("event_id"),
                    "harm_ids": deepcopy(crime_event.get("harm_ids")),
                    "actor_ids": deepcopy(crime_event.get("actor_ids")),
                    "victim_ids": deepcopy(crime_event.get("victim_ids")),
                    "development_function_ids": [
                        str(function["development_function_id"])
                        for function in mapping_values(crime_event.get("development_functions"))
                        if isinstance(function.get("development_function_id"), str)
                        and function.get("required") is True
                    ],
                    "realization_mode": realization_mode,
                    "action_evidence": "행위자의 구체 행동이 피해 발생의 직접 원인으로 보인다.",
                    "dialogue_or_behavior_evidence": "피해자가 위험을 인지하고 즉시 반응한다.",
                    "choice_or_emotion_change": "피해자의 판단이 안전 확보 행동으로 바뀐다.",
                    "result_change": "사건 전후의 신체·자유·안전 상태가 달라진다.",
                    "planned_segment_ids": ["SEG-005"],
                    "expected_excerpt_anchor": "CRIME_TRACE 비가시 추적 정보와 피해 인과",
                }
            ]
        if fake_production_footprint_enabled(request):
            metadata_records = fake_scene_production_metadata(request)
            scenes = [
                {**scene, **metadata_record}
                for scene, metadata_record in zip(scenes, metadata_records, strict=True)
            ]
        return [
            {
                "artifact_name": "scene_cards",
                "media_type": "application/json",
                "content": {
                    "project_id": project_id,
                    "scenes": scenes,
                },
            },
            {
                "artifact_name": "presentation_plan",
                "media_type": "application/json",
                "content": fake_context_presentation_plan(
                    request,
                    project_id,
                    target_runtime_seconds(metadata),
                ),
            },
        ]
    if task_id == "scene.design_reactions":
        total_seconds = target_runtime_seconds(metadata)
        return [
            {
                "artifact_name": "panel_cast",
                "media_type": "application/json",
                "content": fake_panel_cast(project_id),
            },
            {
                "artifact_name": "reaction_segments",
                "media_type": "application/json",
                "content": fake_reaction_segments(project_id, total_seconds),
            },
            {
                "artifact_name": "presentation_plan",
                "media_type": "application/json",
                "content": fake_context_presentation_plan(
                    request,
                    project_id,
                    total_seconds,
                ),
            },
        ]
    if task_id == "scene.design_experts":
        return [
            {
                "artifact_name": "expert_segments",
                "media_type": "application/json",
                "content": {
                    "schema_family": "expert-segments",
                    "schema_version": "1.0.0",
                    "project_id": project_id,
                    "status": "NOT_APPLICABLE",
                    "not_applicable_reason": "FakeProvider 정책 Fixture에는 적용하지 않습니다.",
                    "segments": [],
                },
            }
        ]
    if task_id == "script.compose_screenplay_units":
        return [
            {
                "artifact_name": "screenplay_units",
                "media_type": "application/json",
                "content": fake_screenplay_units(
                    request,
                    project_id,
                    source_truth,
                ),
            }
        ]
    if task_id == "script.write_layers":
        crime_event = context_artifact(request, "crime_event_contract")
        layer_scripts = (
            fake_crime_script_layers(
                target_runtime_seconds(metadata),
                source_disclosure_label(request),
                crime_event,
            )
            if crime_event is not None
            else fake_script_layers(
                target_runtime_seconds(metadata),
                source_disclosure_label(request),
            )
        )
        layer_outputs: list[dict[str, object]] = [
            {
                "artifact_name": artifact_name,
                "media_type": "text/markdown",
                "content": content,
            }
            for artifact_name, content in layer_scripts.items()
        ]
        return layer_outputs
    if task_id == "script.write_expert":
        return [
            {
                "artifact_name": "expert_analysis_script",
                "media_type": "text/markdown",
                "content": "# Expert Analysis\n\n검증된 Claim과 Evidence를 연결합니다.",
            }
        ]
    if task_id == "script.integrate":
        crime_event = context_artifact(request, "crime_event_contract")
        broadcast_master = (
            fake_crime_broadcast_master(
                target_runtime_seconds(metadata),
                source_disclosure_label(request),
                crime_event,
            )
            if crime_event is not None
            else fake_broadcast_master(
                target_runtime_seconds(metadata),
                source_disclosure_label(request),
            )
        )
        return [
            {
                "artifact_name": "draft_script",
                "media_type": "text/markdown",
                "content": broadcast_master,
            },
            {
                "artifact_name": "final_script",
                "media_type": "text/markdown",
                "content": broadcast_master,
            },
        ]
    if task_id == "production.package":
        shooting_script = "SCN-01 통제실 와이드. SCN-02 이송 설비 클로즈업."
        if fake_production_footprint_enabled(request):
            scene_cards = context_artifact(request, "scene_cards")
            raw_scenes = scene_cards.get("scenes") if scene_cards is not None else None
            if not isinstance(raw_scenes, list) or not all(
                isinstance(scene, Mapping) for scene in raw_scenes
            ):
                raise RuntimeExecutionError(
                    "RUNTIME_CONFIGURATION_ERROR",
                    False,
                    "TASK",
                    "Production Package Fixture에는 Scene Card가 필요합니다.",
                    task_id,
                    "shooting_script",
                    {},
                )
            shooting_script = "\n".join(
                f"{production_scene_marker(scene)}\n{scene['scene_id']} 촬영 Cue."
                for scene in raw_scenes
            )
        return [
            {
                "artifact_name": "shooting_script",
                "media_type": "text/markdown",
                "content": shooting_script,
            },
            {
                "artifact_name": "narration",
                "media_type": "text/markdown",
                "content": "실종은 연쇄된 안전 실패였다.",
            },
            {
                "artifact_name": "production_panel_reaction_script",
                "media_type": "text/markdown",
                "content": (
                    "RSEG-001 논리 패널 추리 Cue\n"
                    "RSEG-002 반론 패널 모순 탐지 Cue\n"
                    "RSEG-003 논리 패널 가설 수정 Cue"
                ),
            },
            {
                "artifact_name": "subtitle_script",
                "media_type": "text/markdown",
                "content": "00:00 지안은 7분의 공백을 발견한다.",
            },
            {
                "artifact_name": "edit_script",
                "media_type": "text/markdown",
                "content": fake_edit_script(project_id, target_runtime_seconds(metadata)),
            },
        ]
    if task_id == "production.package_expert":
        return [
            {
                "artifact_name": "production_expert_analysis_script",
                "media_type": "text/markdown",
                "content": "# Production Expert Analysis\n\n전문가 분석 촬영 Cue",
            }
        ]
    if task_id == "editorial.review":
        return [
            {
                "artifact_name": "editorial_review",
                "media_type": "application/json",
                "content": fake_editorial_review(
                    project_id,
                    context_artifacts(request),
                ),
            }
        ]
    raise RuntimeExecutionError(
        "RUNTIME_CONFIGURATION_ERROR",
        False,
        "TASK",
        "FakeProvider Fixture가 없는 Task입니다.",
        task_id,
        None,
        {},
    )


def agent_result_document(request: LLMRequest) -> dict[str, object]:
    """정상 Agent Result Envelope를 생성한다."""
    task_id = request.metadata.get("task_id")
    run_id = request.metadata.get("run_id")
    agent_id = request.metadata.get("agent_id")
    attempt_text = request.metadata.get("attempt")
    if not all(
        isinstance(value, str) and value for value in (task_id, run_id, agent_id, attempt_text)
    ):
        raise RuntimeExecutionError(
            "RUNTIME_CONFIGURATION_ERROR",
            False,
            "TASK",
            "FakeProvider 요청 Metadata가 누락되었습니다.",
            task_id,
            None,
            {},
        )
    return {
        "schema_family": "agent-result",
        "schema_version": "1.0.0",
        "run_id": run_id,
        "task_id": task_id,
        "agent_id": agent_id,
        "attempt": int(cast(str, attempt_text)),
        "status": "SUCCEEDED",
        "artifacts": fixture_artifacts(cast(str, task_id), request),
        "assumptions": [],
        "warnings": [],
        "change_summary": ["결정론적 Runtime 검증 Fixture를 생성함"],
    }


class FakeProvider:
    """Task ID별 Fixture를 반환하고 외부 시스템을 호출하지 않는 Provider."""

    def __init__(
        self,
        fixture_results: Mapping[str, tuple[dict[str, object], ...]],
    ) -> None:
        self._fixture_results = {
            task_id: tuple(deepcopy(result) for result in results)
            for task_id, results in fixture_results.items()
        }
        self._descriptor = ProviderDescriptor(
            interface_version="1.0.0",
            provider_id="fake",
            adapter_id="builtin-fake",
            adapter_version="1.0.0",
            capabilities=(
                "TEXT_GENERATION",
                "JSON_OBJECT",
                "JSON_SCHEMA_OUTPUT",
                "SYSTEM_MESSAGES",
                "USAGE_REPORTING",
            ),
            max_context_tokens=128000,
            max_output_tokens=32000,
        )

    @property
    def descriptor(self) -> ProviderDescriptor:
        """FakeProvider Capability를 반환한다."""
        return self._descriptor

    async def generate(self, request: LLMRequest) -> LLMResponse:
        """Task별 지정 Fixture 또는 기본 정상 Fixture를 반환한다."""
        task_id = request.metadata.get("task_id", "")
        attempt_text = request.metadata.get("attempt", "1")
        attempt = int(attempt_text)
        configured = self._fixture_results.get(task_id)
        if configured:
            selected_index = min(attempt - 1, len(configured) - 1)
            result = deepcopy(configured[selected_index])
        else:
            result = agent_result_document(request)
        input_tokens = sum(len(message.content) for message in request.messages) // 4
        output_tokens = len(json.dumps(result, ensure_ascii=False)) // 4
        return LLMResponse(
            request_id=request.request_id,
            provider_request_id=f"FAKE-{request.request_id}",
            status="COMPLETED",
            finish_reason="STOP",
            text=None,
            structured_output=result,
            tool_calls=(),
            usage=TokenUsage(
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                cached_tokens=0,
            ),
            model_resolved=request.model_ref,
            warnings=(),
        )

    async def close(self) -> None:
        """FakeProvider에는 정리할 외부 자원이 없다."""
        return None
