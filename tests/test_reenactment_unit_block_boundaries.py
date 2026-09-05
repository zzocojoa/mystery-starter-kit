"""독립 Unit Block의 접두부·반복·변조를 전체 Export 경로에서 검증한다."""

from collections.abc import Mapping
from typing import TypedDict, cast

import pytest
from test_reenactment_export import (
    build_report_with_sources,
    clue_matrix,
    crime_event_contract,
    facts_document,
    report_codes,
)
from test_screenplay_renderers import (
    characters_document,
    output_profile,
    presentation_plan,
    reaction_segments,
    references,
    relationships_document,
    screenplay_document,
    screenplay_unit,
)

from RUNTIME.screenplay_renderers import (
    characters_by_id,
    reenactment_unit_text,
    render_broadcast_master,
    render_drama_layer,
    render_narration_layer,
    render_panel_layer,
    render_reenactment_character_script,
)
from VALIDATORS.reenactment_export import ScreenplayDerivedOutputs


class BoundaryFixture(TypedDict):
    """원본 Unit과 그 원본에서 새로 렌더링한 모든 출력을 묶는다."""

    screenplay: dict[str, object]
    outputs: ScreenplayDerivedOutputs


def boundary_screenplay(texts: tuple[str, ...]) -> dict[str, object]:
    """기존 독립 Fixture의 두 장면 사이에 경계 검증용 대사를 추가한다."""
    document = screenplay_document()
    scenes = cast(list[dict[str, object]], document["scenes"])
    assert len(scenes) == 2
    assert len(texts) >= 3
    first_units = cast(list[dict[str, object]], scenes[0]["units"])
    last_units = cast(list[dict[str, object]], scenes[1]["units"])
    empty = references([], [], [], [], [], [])
    first_additions = [
        screenplay_unit(
            f"UNIT-BLOCK-{index:02}",
            len(first_units) + index,
            "DIALOGUE",
            text,
            "SEG-001",
            "CHAR-001",
            empty,
        )
        for index, text in enumerate(texts[:-1], start=1)
    ]
    last_addition = screenplay_unit(
        f"UNIT-BLOCK-{len(texts):02}",
        len(last_units) + 1,
        "DIALOGUE",
        texts[-1],
        "SEG-004",
        "CHAR-001",
        empty,
    )
    bindings = cast(list[dict[str, object]], scenes[1]["reconstruction_bindings"])
    matching_sources = [
        index for index, text in enumerate(texts[:-1], start=1) if text == texts[-1]
    ]
    repeated_bindings: list[dict[str, object]] = (
        [
            {
                "source_unit_id": f"UNIT-BLOCK-{matching_sources[0]:02}",
                "repeated_unit_id": f"UNIT-BLOCK-{len(texts):02}",
                "preservation": "EXACT_VISIBLE_IDENTITY",
                "reference_policy": "PRESERVE_REFERENCES",
            }
        ]
        if matching_sources
        else []
    )
    return {
        **document,
        "scenes": [
            {**scenes[0], "units": [*first_units, *first_additions]},
            {
                **scenes[1],
                "units": [*last_units, last_addition],
                "reconstruction_bindings": [*bindings, *repeated_bindings],
            },
        ],
    }


def boundary_fixture(texts: tuple[str, ...]) -> BoundaryFixture:
    """추가한 원본에서 계층·통합·재연 출력을 모두 다시 만든다."""
    screenplay = boundary_screenplay(texts)
    plan = presentation_plan()
    contract = crime_event_contract()
    drama = render_drama_layer(screenplay, plan, contract)
    narration = render_narration_layer(screenplay, plan, contract)
    panel = render_panel_layer(reaction_segments(), plan)
    master = render_broadcast_master(
        plan,
        {"drama_script": drama, "narration_script": narration, "panel_reaction_script": panel},
    )
    markdown = render_reenactment_character_script(
        screenplay, characters_document(), relationships_document(), output_profile()
    )
    return {
        "screenplay": screenplay,
        "outputs": ScreenplayDerivedOutputs(
            drama_script=drama,
            narration_script=narration,
            panel_reaction_script=panel,
            draft_script=master,
            final_script=master,
            reenactment_character_script=markdown,
        ),
    }


def report_for_markdown(fixture: BoundaryFixture, markdown: str) -> dict[str, object]:
    """현재 원본과 지정한 실제 재연 출력으로 전체 Report를 재구성한다."""
    outputs: ScreenplayDerivedOutputs = {
        **fixture["outputs"],
        "reenactment_character_script": markdown,
    }
    return build_report_with_sources(
        fixture["screenplay"],
        facts_document(),
        characters_document(),
        relationships_document(),
        crime_event_contract(),
        clue_matrix(),
        output_profile(),
        presentation_plan(),
        reaction_segments(),
        outputs,
    )


def unit_coverage(report: Mapping[str, object]) -> Mapping[str, object]:
    """전체 Report가 계산한 Unit Coverage를 반환한다."""
    value = report["unit_coverage"]
    assert isinstance(value, Mapping)
    return value


def visible_block(text: str) -> str:
    """정식 Profile로 내부 Marker 없는 대사 Block을 만든다."""
    unit = screenplay_unit(
        "UNIT-BLOCK-99",
        1,
        "DIALOGUE",
        text,
        "SEG-001",
        "CHAR-001",
        references([], [], [], [], [], []),
    )
    return reenactment_unit_text(unit, characters_by_id(characters_document()), output_profile())


@pytest.mark.parametrize(
    ("long_text", "short_text"),
    [
        ("준비됐어요. 계속 말씀하세요.", "준비됐어요."),
        ("Sí, 좋아요. 続けてください。🙂", "Sí, 좋아요."),
        (
            "Café에서 기다립니다.\n了解しました。\n다음 문장도 읽습니다.",
            "Café에서 기다립니다.\n了解しました。",
        ),
        ("준비됐어요.\n\n빈줄 뒤의 추가 설명도 같은 Unit에 속합니다.", "준비됐어요."),
    ],
    ids=[
        "korean-prefix",
        "international-prefix",
        "international-multiline-prefix",
        "internal-blank-line-prefix",
    ],
)
def test_prefix_blocks_preserve_full_report_order(long_text: str, short_text: str) -> None:
    """긴 대사의 접두부를 뒤 장면의 독립 대사로 오인하지 않는다."""
    fixture = boundary_fixture((long_text, "중간 문장을 확인합니다.", short_text))
    report = report_for_markdown(fixture, fixture["outputs"]["reenactment_character_script"])
    coverage = unit_coverage(report)

    assert report["result"] == "NEEDS_REVIEW"
    assert report["issues"] == []
    assert coverage["rendered_order"] == coverage["expected_ids"]
    assert coverage["missing_ids"] == []
    assert coverage["duplicate_ids"] == []


def test_identical_blocks_with_distinct_unit_owners_remain_valid() -> None:
    """같은 대사를 소유한 두 Unit은 독립 Block 두 번과 대응한다."""
    fixture = boundary_fixture(
        ("준비됐어요. 계속 말씀하세요.", "중간 문장을 확인합니다.", "준비됐어요.", "준비됐어요.")
    )
    report = report_for_markdown(fixture, fixture["outputs"]["reenactment_character_script"])
    coverage = unit_coverage(report)

    assert report["result"] == "NEEDS_REVIEW"
    assert report["issues"] == []
    assert coverage["rendered_order"] == coverage["expected_ids"]
    assert coverage["duplicate_ids"] == []


def test_repeated_multiline_blocks_do_not_create_overlapping_extra_owner() -> None:
    """동일 다중 문단 Block 두 개 사이에 걸친 겹침을 세 번째 Unit으로 세지 않는다."""
    short_text = "확인했습니다."
    long_text = short_text + "\n\n" + visible_block(short_text)
    fixture = boundary_fixture(
        ("앞선 문장을 확인합니다.", long_text, long_text, "마지막 문장을 확인합니다.")
    )
    report = report_for_markdown(fixture, fixture["outputs"]["reenactment_character_script"])
    coverage = unit_coverage(report)

    assert report["result"] == "NEEDS_REVIEW"
    assert report["issues"] == []
    assert coverage["rendered_order"] == coverage["expected_ids"]
    assert coverage["missing_ids"] == []
    assert coverage["duplicate_ids"] == []


@pytest.mark.parametrize("text_orders", [(0, 1), (1, 0)], ids=["short-long", "long-short"])
def test_adjacent_short_and_long_blocks_keep_source_ownership(
    text_orders: tuple[int, int],
) -> None:
    """인접 Unit과 긴 Unit 내부 문단의 문구가 겹쳐도 원본 소유권을 보존한다."""
    short_text = "확인했습니다."
    texts = (short_text, short_text + "\n\n" + visible_block(short_text))
    fixture = boundary_fixture(
        (texts[text_orders[0]], texts[text_orders[1]], "마지막 문장을 확인합니다.")
    )
    report = report_for_markdown(fixture, fixture["outputs"]["reenactment_character_script"])
    coverage = unit_coverage(report)

    assert report["result"] == "NEEDS_REVIEW"
    assert report["issues"] == []
    assert coverage["rendered_order"] == coverage["expected_ids"]
    assert coverage["missing_ids"] == []
    assert coverage["duplicate_ids"] == []


def test_missing_exact_block_cannot_be_replaced_by_long_prefix() -> None:
    """독립 대사를 지우면 앞선 긴 대사가 누락된 Unit을 대신하지 못한다."""
    fixture = boundary_fixture(
        ("준비됐어요. 계속 말씀하세요.", "중간 문장을 확인합니다.", "준비됐어요.")
    )
    markdown = fixture["outputs"]["reenactment_character_script"]
    tail = visible_block("준비됐어요.") + "\n"
    assert markdown.endswith(tail)
    report = report_for_markdown(fixture, markdown.removesuffix(tail))

    assert unit_coverage(report)["missing_ids"] == ["UNIT-BLOCK-03"]
    assert report["result"] == "FAIL"
    assert "UNIT_RENDER_MISMATCH" in report_codes(report)


def test_additional_exact_block_is_rejected_by_full_report() -> None:
    """승인된 원본보다 대사 Block이 하나 더 많으면 중복과 출력 변조로 거부한다."""
    fixture = boundary_fixture(
        ("준비됐어요. 계속 말씀하세요.", "중간 문장을 확인합니다.", "준비됐어요.")
    )
    markdown = fixture["outputs"]["reenactment_character_script"]
    report = report_for_markdown(fixture, markdown + "\n" + visible_block("준비됐어요.") + "\n")

    assert unit_coverage(report)["duplicate_ids"] == ["UNIT-BLOCK-03"]
    assert report["result"] == "FAIL"
    assert "UNIT_RENDER_MISMATCH" in report_codes(report)


def test_reordered_exact_blocks_are_rejected_by_full_report() -> None:
    """대사 수와 원문이 같아도 실제 독립 Block 순서를 바꾸면 거부한다."""
    long_text = "준비됐어요. 계속 말씀하세요."
    short_text = "준비됐어요."
    fixture = boundary_fixture((long_text, "중간 문장을 확인합니다.", short_text))
    markdown = fixture["outputs"]["reenactment_character_script"]
    tail = visible_block(short_text) + "\n"
    anchor = visible_block(long_text) + "\n\n"
    assert markdown.endswith(tail)
    assert markdown.count(anchor) == 1
    reordered = markdown.removesuffix(tail).replace(
        anchor, anchor + visible_block(short_text) + "\n\n", 1
    )
    report = report_for_markdown(fixture, reordered)
    coverage = unit_coverage(report)

    assert coverage["missing_ids"] == []
    assert coverage["duplicate_ids"] == []
    assert report["result"] == "FAIL"
    assert {"REENACTMENT_UNIT_ORDER_INVALID", "UNIT_RENDER_MISMATCH"}.issubset(report_codes(report))
