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
from VALIDATORS.crime_event import canonical_json_hash
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

PresentationDefinition: TypeAlias = tuple[
    str,
    str,
    str,
    float,
    str | None,
    str,
    list[str],
]


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
                        "spoken_line": "7분의 공백이 이탈의 증거인지부터 확인해야 합니다.",
                        "evidence_ids": ["CLUE-01"],
                        "known_fact_ids": ["FACT-01"],
                        "tone": "SUSPICIOUS",
                    },
                    {
                        "turn_id": "TURN-001-02",
                        "panelist_id": "PANEL-03",
                        "function": "CONTRADICTION_DETECTION",
                        "spoken_line": "공백을 사람의 선택으로만 보기엔 빠른 것 같아요.",
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
                        "spoken_line": "이동 기록이 아니라 센서 자체가 멈춘 것일 수도 있죠.",
                        "evidence_ids": ["CLUE-01"],
                        "known_fact_ids": ["FACT-01"],
                        "tone": "ANALYTICAL",
                    },
                    {
                        "turn_id": "TURN-002-02",
                        "panelist_id": "PANEL-02",
                        "function": "EMOTIONAL_REACTION",
                        "spoken_line": "그렇다면 공백 안에 남은 사람을 먼저 찾아야 해요.",
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
                        "spoken_line": "안전 센서가 점검 모드였다면 공백은 이탈 증거가 아닙니다.",
                        "evidence_ids": ["CLUE-01", "CLUE-02"],
                        "known_fact_ids": ["FACT-01", "FACT-02"],
                        "tone": "RECONSIDERING",
                    },
                    {
                        "turn_id": "TURN-003-02",
                        "panelist_id": "PANEL-02",
                        "function": "TENSION_RELEASE",
                        "spoken_line": "이제야 사람을 잘못 탓하던 시간을 되돌릴 수 있겠네요.",
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
                    "[PANEL-01] “7분의 공백이 이탈의 증거인지부터 확인해야 합니다.”\n"
                    "[PANEL-03] “공백을 사람의 선택으로만 보기엔 빠른 것 같아요.”",
                ),
                broadcast_marker(
                    "SEG-004",
                    "PANEL_REACTION",
                    "SCN-01",
                    reaction_duration,
                    "[RSEG-002] [PANEL-03] [CONTRADICTION_DETECTION]\n"
                    "[PANEL-03] “이동 기록이 아니라 센서 자체가 멈춘 것일 수도 있죠.”\n"
                    "[PANEL-02] “그렇다면 공백 안에 남은 사람을 먼저 찾아야 해요.”",
                ),
                broadcast_marker(
                    "SEG-006",
                    "PANEL_REACTION",
                    "SCN-02",
                    reaction_duration,
                    "[RSEG-003] [PANEL-01] [HYPOTHESIS_REVISION]\n"
                    "[PANEL-01] “안전 센서가 점검 모드였다면 공백은 이탈 증거가 아닙니다.”\n"
                    "[PANEL-02] “이제야 사람을 잘못 탓하던 시간을 되돌릴 수 있겠네요.”",
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
    """범죄 행동과 피해 인과 Marker를 Drama Layer에 삽입한다."""
    layers = fake_script_layers(total_seconds, audience_label_text)
    event_id = crime_event.get("event_id")
    action_type = crime_event.get("core_action_type")
    harm_ids = crime_event.get("harm_ids")
    harm_id = harm_ids[0] if isinstance(harm_ids, list) and harm_ids else None
    if not all(isinstance(value, str) for value in (event_id, action_type, harm_id)):
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
        f"[CRIME_EVENT:{event_id}] [CRIME_ACTION:{action_type}] "
        f"[HARM:{harm_id}] [CAUSES:{event_id}>{harm_id}] "
    )
    layers["drama_script"] = layers["drama_script"].replace(
        "[FACT:FACT-02]",
        marker + "[FACT:FACT-02]",
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
        for index, target in enumerate(target_records, 5):
            target_id = target.get("reveal_target_id")
            semantic_assessments.append(
                {
                    "assessment_id": f"ASSESS-{index:02d}",
                    "category": "REVEAL_TIMING",
                    "subject_id": str(target_id),
                    "status": "EVIDENCED",
                    "evidence": [
                        make_editorial_evidence(
                            artifacts,
                            "final_script",
                            "SEGMENT_ID",
                            "SEG-005" if index < 7 else "SEG-006",
                        )
                    ],
                    "notes": "계획된 후반 Segment에서 공개됨",
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
            "incident_type": selection["incident_type"],
            "setting": selection["setting"],
            "setting_logic": ["ACCESS_LOG", "MACHINE_LOG", "SHIFT_CHANGE"],
            "culprit_structure": selection["culprit_structure"],
            "causal_truth": (
                "차단된 안전 센서와 교대 기록 오류가 결합되어 실종처럼 보이는 사고가 발생했다."
            ),
            "primary_twist": selection["primary_twist"],
            "secondary_twists": ["TW-10_CAUSALITY"],
            "information_mechanism": [selection.get("information_mechanism", "MACHINE_LOG")],
            "clue_mechanism": [selection.get("clue_mechanism", "TIMESTAMP")],
            "motive_class": "NO_INTENT",
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
                "final_reframe": "범죄처럼 보인 사건은 연쇄적인 안전 실패의 결과였다.",
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


def fake_candidate_evaluation(
    project_id: str,
    variations: Mapping[str, object],
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


def fake_crime_event_contract(
    request: LLMRequest,
    project_id: str,
    source_truth: str,
) -> dict[str, object]:
    """승인 Candidate의 사건 개요를 Case 계약으로 그대로 결속한다."""
    variations = context_artifact(request, "variation_candidates")
    facts = context_artifact(request, "facts")
    candidates = variations.get("candidates") if variations is not None else None
    candidate_records = candidates if isinstance(candidates, list) else []
    approved_id = variations.get("approved_candidate_id") if variations is not None else None
    candidate = next(
        (
            item
            for item in candidate_records
            if isinstance(item, Mapping) and item.get("candidate_id") == approved_id
        ),
        None,
    )
    event = candidate.get("crime_event") if isinstance(candidate, Mapping) else None
    if not isinstance(approved_id, str) or not isinstance(event, Mapping):
        raise RuntimeExecutionError(
            "RUNTIME_CONFIGURATION_ERROR",
            False,
            "TASK",
            "승인 Candidate의 사건 개요가 없습니다.",
            "story.define_crime_event",
            "variation_candidates",
            {},
        )
    fact_records = facts.get("facts") if facts is not None else None
    normalized_fact_records = fact_records if isinstance(fact_records, list) else []
    source_fact_ids = [
        str(item["fact_id"])
        for item in normalized_fact_records
        if isinstance(item, Mapping)
        and item.get("classification") == "FACT"
        and isinstance(item.get("fact_id"), str)
    ]
    event_fields = {
        key: deepcopy(value)
        for key, value in event.items()
        if key not in {"centrality", "truth_status"}
    }
    return {
        "schema_family": "crime-event-contract",
        "schema_version": "1.0.0",
        "project_id": project_id,
        "approved_candidate_id": approved_id,
        "candidate_event_sha256": canonical_json_hash(event),
        **event_fields,
        "truth_basis": {
            "source_truth_classification": source_truth,
            "status": (
                "ORIGINAL_FICTION" if source_truth == "ORIGINAL_FICTION" else "EVIDENCE_LOCKED"
            ),
            "source_fact_ids": ([] if source_truth == "ORIGINAL_FICTION" else source_fact_ids),
            "unknown_fields": [],
        },
    }


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
    if task_id == "variation.evaluate":
        variations = context_artifact(request, "variation_candidates")
        novelty_precheck = context_artifact(request, "novelty_precheck")
        candidate_eligibility = context_artifact(request, "candidate_eligibility")
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
            facts = [dict(fact) for fact in ledger_facts if isinstance(fact, Mapping)]
            verified_case_fields = true_story_case_dimensions(request)
        else:
            statements = (
                "기계 로그에 7분 공백이 있다.",
                "안전 센서는 점검 모드였다.",
            )
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
                }
                for index, statement in enumerate(statements, 1)
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
                    "central_mystery": "작업자는 언제 통제 구역을 벗어났는가?",
                    "final_truth": "작업자는 정지한 이송 설비의 점검 공간에 갇혔다.",
                    "causal_truth": "센서 차단과 교대 기록 오류가 구조 지연을 만들었다.",
                    "incident_type": verified_case_fields.get(
                        "incident_type", selected["incident_type"]
                    ),
                    "setting": verified_case_fields.get("setting", selected["setting"]),
                    **{
                        key: value
                        for key, value in verified_case_fields.items()
                        if key not in {"incident_type", "setting"}
                    },
                    "culprit": None,
                    "culprit_motive": None,
                    "restrictions": [],
                },
            },
            {
                "artifact_name": "facts",
                "media_type": "application/json",
                "content": {
                    "project_id": project_id,
                    "facts": facts,
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
    if task_id == "story.define_crime_event":
        return [
            {
                "artifact_name": "crime_event_contract",
                "media_type": "application/json",
                "content": fake_crime_event_contract(
                    request,
                    project_id,
                    source_truth,
                ),
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
        default_characters: list[dict[str, object]] = [
            {"character_id": "CHAR-01", "name": "지안", "role": "SUSPECT"},
            {"character_id": "CHAR-02", "name": "태호", "role": "MISSING_COWORKER"},
        ]
        if fake_production_footprint_enabled(request):
            default_characters = [
                {**character, "production_role": "MAJOR"} for character in default_characters
            ]
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
                            "from": "CHAR-01",
                            "to": "CHAR-02",
                            "engine": "TRUST_TO_RESPONSIBILITY",
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
                        {"character_id": "CHAR-01", "fact_id": "FACT-01", "learned_scene_order": 1},
                        {"character_id": "CHAR-01", "fact_id": "FACT-02", "learned_scene_order": 2},
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
        return [
            {
                "artifact_name": "actual_timeline",
                "media_type": "application/json",
                "content": truth_timeline
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
                "content": {
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
                "content": {
                    "project_id": project_id,
                    **(
                        {
                            "final_proof_mechanism": selected["final_proof_mechanism"],
                            "technical_dependency_level": selected["technical_dependency_level"],
                        }
                        if "final_proof_mechanism" in selected
                        and "technical_dependency_level" in selected
                        else {}
                    ),
                    "clues": [
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
                    ],
                },
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
                "content": truth_causal_graph
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
                    "realization_mode": realization_mode,
                    "action_evidence": "행위자의 구체 행동이 피해 발생의 직접 원인으로 보인다.",
                    "dialogue_or_behavior_evidence": "피해자가 위험을 인지하고 즉시 반응한다.",
                    "choice_or_emotion_change": "피해자의 판단이 안전 확보 행동으로 바뀐다.",
                    "result_change": "사건 전후의 신체·자유·안전 상태가 달라진다.",
                    "planned_segment_ids": ["SEG-005"],
                    "expected_excerpt_anchor": "CRIME_EVENT Marker와 피해 인과",
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
