"""Provider API 없이 전체 Runtime을 검증하는 결정론적 FakeProvider."""

import json
from collections.abc import Mapping
from copy import deepcopy
from typing import cast

from RUNTIME.errors import RuntimeExecutionError
from RUNTIME.models import (
    LLMRequest,
    LLMResponse,
    ProviderDescriptor,
    TokenUsage,
)


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
            "information_mechanism": ["MACHINE_LOG", "CCTV"],
            "clue_mechanism": ["TIMESTAMP", "TECHNICAL"],
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
            "reveal_mode": "TIMELINE_RECONSTRUCTION",
            "ending_type": "BITTERSWEET",
        },
    }


def context_artifact(request: LLMRequest, artifact_name: str) -> Mapping[str, object] | None:
    """컴파일된 비신뢰 Context에서 지정 Artifact 객체를 읽는다."""
    start_marker = '<CONTEXT_DATA instructional="false">\n'
    end_marker = "\n</CONTEXT_DATA>"
    user_messages = [message.content for message in request.messages if message.role == "user"]
    if len(user_messages) != 1:
        raise RuntimeExecutionError(
            "RUNTIME_CONFIGURATION_ERROR",
            False,
            "TASK",
            "FakeProvider는 단일 User Prompt를 요구합니다.",
            request.metadata.get("task_id"),
            artifact_name,
            {"user_message_count": len(user_messages)},
        )
    content = user_messages[0]
    start = content.find(start_marker)
    end = content.find(end_marker, start + len(start_marker))
    if start < 0 or end < 0:
        raise RuntimeExecutionError(
            "RUNTIME_CONFIGURATION_ERROR",
            False,
            "TASK",
            "FakeProvider Prompt에 Context Data 구간이 없습니다.",
            request.metadata.get("task_id"),
            artifact_name,
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
            artifact_name,
            {},
        )
    for item in parsed:
        if not isinstance(item, Mapping) or item.get("artifact_name") != artifact_name:
            continue
        artifact = item.get("content")
        if not isinstance(artifact, Mapping):
            raise RuntimeExecutionError(
                "RUNTIME_CONFIGURATION_ERROR",
                False,
                "TASK",
                "FakeProvider Context Artifact가 객체가 아닙니다.",
                request.metadata.get("task_id"),
                artifact_name,
                {},
            )
        return artifact
    return None


def fixture_artifacts(task_id: str, request: LLMRequest) -> list[dict[str, object]]:
    """Task ID를 검증 가능한 Agent Artifact Fixture에 대응한다."""
    metadata = request.metadata
    project_id = metadata.get("project_id")
    source_mode = metadata.get("story_source_mode")
    if not isinstance(project_id, str) or not isinstance(source_mode, str):
        raise RuntimeExecutionError(
            "RUNTIME_CONFIGURATION_ERROR",
            False,
            "TASK",
            "FakeProvider Metadata에 Project 정보가 없습니다.",
            task_id,
            None,
            {},
        )
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
        return [
            {
                "artifact_name": "case_input",
                "media_type": "application/json",
                "content": {
                    "project_id": project_id,
                    "title_working": "교대 기록의 7분",
                    "source_type": "FICTION",
                    "central_mystery": "작업자는 언제 통제 구역을 벗어났는가?",
                    "final_truth": "작업자는 정지한 이송 설비의 점검 공간에 갇혔다.",
                    "causal_truth": "센서 차단과 교대 기록 오류가 구조 지연을 만들었다.",
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
                    "facts": [
                        {"fact_id": "FACT-01", "statement": "기계 로그에 7분 공백이 있다."},
                        {"fact_id": "FACT-02", "statement": "안전 센서는 점검 모드였다."},
                    ],
                },
            },
        ]
    if task_id == "character.design":
        return [
            {
                "artifact_name": "characters",
                "media_type": "application/json",
                "content": {
                    "project_id": project_id,
                    "characters": [
                        {"character_id": "CHAR-01", "name": "지안", "role": "SUSPECT"},
                        {"character_id": "CHAR-02", "name": "태호", "role": "MISSING_COWORKER"},
                    ],
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
        return [
            {
                "artifact_name": "actual_timeline",
                "media_type": "application/json",
                "content": {
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
                    "reveals": [{"reveal_id": "REV-01", "scene_id": "SCN-01"}],
                },
            },
            {
                "artifact_name": "audience_belief",
                "media_type": "application/json",
                "content": {
                    "project_id": project_id,
                    "belief_states": [{"scene_id": "SCN-01", "belief": "누군가 은폐했다."}],
                },
            },
            {
                "artifact_name": "clue_matrix",
                "media_type": "application/json",
                "content": {
                    "project_id": project_id,
                    "clues": [
                        {
                            "clue_id": "CLUE-01",
                            "role": "CORE",
                            "introduced_scene_order": 1,
                            "introduced_scene_id": "SCN-01",
                            "resolved_scene_order": 2,
                            "resolved_scene_id": "SCN-02",
                        },
                        {
                            "clue_id": "CLUE-02",
                            "role": "RED_HERRING",
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
                "content": {
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
        return [
            {
                "artifact_name": "scene_cards",
                "media_type": "application/json",
                "content": {
                    "project_id": project_id,
                    "scenes": [
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
                    ],
                },
            },
            {
                "artifact_name": "presentation_plan",
                "media_type": "application/json",
                "content": {
                    "project_id": project_id,
                    "modes": ["DRAMA", "NARRATION", "REACTION"],
                    "reaction_ratio": 0.2,
                    "scene_presentations": [
                        {"scene_id": "SCN-01", "mode": "DRAMA"},
                        {"scene_id": "SCN-02", "mode": "NARRATION"},
                    ],
                },
            },
        ]
    if task_id == "script.write":
        return [
            {
                "artifact_name": "draft_script",
                "media_type": "text/markdown",
                "content": "[DRAMA] 지안은 7분의 공백을 발견한다.",
            },
            {
                "artifact_name": "final_script",
                "media_type": "text/markdown",
                "content": "[NARRATION] 실종은 누군가의 계획이 아니라 연쇄된 안전 실패였다.",
            },
        ]
    if task_id == "production.package":
        return [
            {
                "artifact_name": "shooting_script",
                "media_type": "text/markdown",
                "content": "SCN-01 통제실 와이드. SCN-02 이송 설비 클로즈업.",
            },
            {
                "artifact_name": "narration",
                "media_type": "text/markdown",
                "content": "실종은 연쇄된 안전 실패였다.",
            },
            {
                "artifact_name": "subtitle_script",
                "media_type": "text/markdown",
                "content": "00:00 지안은 7분의 공백을 발견한다.",
            },
            {
                "artifact_name": "edit_script",
                "media_type": "text/markdown",
                "content": "SCN-01에서 로그를 제시하고 SCN-02에서 인과를 재구성한다.",
            },
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
