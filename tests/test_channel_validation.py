"""Channel DNA와 Production Artifact 일관성 검증."""

from copy import deepcopy
from pathlib import Path

from VALIDATORS.channel_validation import validate_channel_consistency
from VALIDATORS.io import load_json_object

ROOT = Path(__file__).resolve().parents[1]
CHANNEL_PATH = ROOT / "CHANNELS" / "mystery_main" / "channel_dna.json"


def make_project_inputs() -> tuple[dict[str, object], dict[str, object], dict[str, object]]:
    """Channel 일관성 테스트용 Story와 제작 설정을 만든다."""
    story: dict[str, object] = {"story_dna": {"mystery_type": "WHY"}}
    production: dict[str, object] = {
        "genre": "CRIME_EVENT_THRILLER",
        "tones": ["GROUNDED", "SUSPENSEFUL"],
    }
    presentation: dict[str, object] = {
        "modes": ["DRAMA", "NARRATION", "PANEL_REACTION"],
        "segments": [
            {"segment_type": "DRAMA", "duration_sec": 60},
            {"segment_type": "NARRATION", "duration_sec": 20},
            {"segment_type": "PANEL_REACTION", "duration_sec": 20},
        ],
    }
    return story, production, presentation


def test_matching_channel_project_passes() -> None:
    """허용 장르·톤·표현 모드를 지킨 프로젝트는 통과해야 한다."""
    channel = load_json_object(CHANNEL_PATH)
    story, production, presentation = make_project_inputs()

    assert validate_channel_consistency(channel, story, production, presentation) == []


def test_genre_tone_and_presentation_violations_fail() -> None:
    """장르·금지 톤·필수 표현 모드 위반을 모두 보고해야 한다."""
    channel = load_json_object(CHANNEL_PATH)
    changed_channel = deepcopy(channel)
    capabilities = changed_channel["capabilities"]
    assert isinstance(capabilities, dict)
    tone_policy = capabilities["TONE_POLICY"]
    assert isinstance(tone_policy, dict)
    tone_policy["prohibited_tones"] = ["COMEDIC"]
    story, production, presentation = make_project_inputs()
    production["genre"] = "ROMANCE"
    production["tones"] = ["COMEDIC"]
    presentation["modes"] = ["DRAMA"]
    presentation["segments"] = [
        {"segment_type": "DRAMA", "duration_sec": 20},
        {"segment_type": "PANEL_REACTION", "duration_sec": 80},
    ]

    issues = validate_channel_consistency(
        changed_channel,
        story,
        production,
        presentation,
    )
    codes = {issue["code"] for issue in issues}

    assert codes == {
        "CHANNEL_GENRE_VIOLATION",
        "CHANNEL_TONE_VIOLATION",
        "CHANNEL_PRESENTATION_VIOLATION",
        "PANEL_REACTION_RATIO_OUT_OF_RANGE",
    }
