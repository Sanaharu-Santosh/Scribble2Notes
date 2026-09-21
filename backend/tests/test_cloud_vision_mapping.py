"""Verify the Cloud Vision mapping without calling Cloud Vision.

The adapter's two halves are tested separately: response-walking against
hand-built response objects, and line grouping against hand-built words. Between
them they cover the parts that actually break — break-type handling, line quad
geometry, and the field-spelling differences between library versions.

A live check still belongs in Phase 1 (see docs/cloud-vision-setup.md); these
tests are what make that check a confirmation rather than a debugging session.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.services.images import slanted_quad
from app.services.ocr.cloud_vision import (
    BREAK_EOL_SURE_SPACE,
    BREAK_LINE_BREAK,
    BREAK_SPACE,
    DetectedWord,
    as_word_regions,
    extract_words,
    group_into_lines,
    merge_line_quad,
)

# --------------------------------------------------------------------------
# Builders for fake google-cloud-vision response objects
# --------------------------------------------------------------------------


def _symbol(char: str, break_type: int | None = None, *, legacy_spelling: bool = False):
    if break_type is None:
        detected = None
    elif legacy_spelling:
        # google-cloud-vision has spelled this field both ways across releases.
        detected = SimpleNamespace(type=break_type)
    else:
        detected = SimpleNamespace(type_=break_type)
    return SimpleNamespace(text=char, property=SimpleNamespace(detected_break=detected))


def _word(
    text: str,
    x: float = 0,
    y: float = 0,
    width: float = 40,
    height: float = 20,
    confidence: float = 0.9,
    break_type: int | None = None,
    legacy_spelling: bool = False,
    vertex_count: int = 4,
):
    symbols = [_symbol(char) for char in text[:-1]]
    symbols.append(_symbol(text[-1], break_type, legacy_spelling=legacy_spelling))

    corners = [
        (x, y),
        (x + width, y),
        (x + width, y + height),
        (x, y + height),
    ][:vertex_count]

    return SimpleNamespace(
        symbols=symbols,
        bounding_box=SimpleNamespace(vertices=[SimpleNamespace(x=cx, y=cy) for cx, cy in corners]),
        confidence=confidence,
    )


def _response(paragraphs: list[list], full_text: str = ""):
    return SimpleNamespace(
        full_text_annotation=SimpleNamespace(
            pages=[
                SimpleNamespace(
                    blocks=[
                        SimpleNamespace(
                            paragraphs=[SimpleNamespace(words=words) for words in paragraphs]
                        )
                    ]
                )
            ],
            text=full_text,
        ),
        error=SimpleNamespace(message=""),
    )


# --------------------------------------------------------------------------
# extract_words
# --------------------------------------------------------------------------


def test_breaks_drive_line_endings():
    response = _response(
        [
            [
                _word("hello", x=0, break_type=BREAK_SPACE),
                _word("world", x=50, break_type=BREAK_LINE_BREAK),
                _word("second", x=0, break_type=BREAK_SPACE),
                _word("line", x=50),
            ]
        ]
    )

    words = extract_words(response)
    regions = group_into_lines(words)

    assert [region.text for region in regions] == ["hello world", "second line"]
    assert all(region.level == "line" for region in regions)


def test_words_without_a_space_break_are_joined_tight():
    """A missing space break means the glyphs ran together — don't invent one."""
    response = _response([[_word("Fig", x=0), _word(".1", x=40, break_type=BREAK_LINE_BREAK)]])

    assert group_into_lines(extract_words(response))[0].text == "Fig.1"


def test_paragraph_boundary_ends_a_line_without_any_break():
    """One missing field must not merge two paragraphs into one region."""
    response = _response([[_word("first", x=0)], [_word("second", x=0, y=30)]])

    regions = group_into_lines(extract_words(response))
    assert [region.text for region in regions] == ["first", "second"]


def test_legacy_break_field_spelling_still_works():
    response = _response(
        [
            [
                _word("old", x=0, break_type=BREAK_SPACE, legacy_spelling=True),
                _word("client", x=40, break_type=BREAK_EOL_SURE_SPACE, legacy_spelling=True),
            ]
        ]
    )

    assert group_into_lines(extract_words(response))[0].text == "old client"


def test_malformed_bounding_boxes_are_skipped():
    response = _response(
        [
            [
                _word("good", x=0, break_type=BREAK_SPACE),
                _word("bad", x=50, vertex_count=3, break_type=BREAK_SPACE),
                _word("also-good", x=100, break_type=BREAK_LINE_BREAK),
            ]
        ]
    )

    assert group_into_lines(extract_words(response))[0].text == "good also-good"


def test_confidence_is_averaged_across_the_line():
    response = _response(
        [
            [
                _word("sure", x=0, confidence=1.0, break_type=BREAK_SPACE),
                _word("unsure", x=50, confidence=0.5, break_type=BREAK_LINE_BREAK),
            ]
        ]
    )

    assert group_into_lines(extract_words(response))[0].confidence == pytest.approx(0.75)


# --------------------------------------------------------------------------
# Line geometry
# --------------------------------------------------------------------------


def _detected(text: str, quad, ends_line: bool = False, trailing_space: bool = True):
    return DetectedWord(
        text=text, quad=quad, confidence=0.9, trailing_space=trailing_space, ends_line=ends_line
    )


def test_line_quad_spans_first_to_last_word():
    first = slanted_quad(10, 100, 40, 20, 0)
    last = slanted_quad(60, 100, 40, 20, 0)

    merged = merge_line_quad([first, last])

    assert merged.points[0] == first.points[0]  # top-left of the first word
    assert merged.points[1] == last.points[1]  # top-right of the last word
    assert merged.bbox.width == pytest.approx(90)


def test_line_quad_keeps_the_slant_of_the_writing():
    """A bounding box around slanted words is taller than the text, which would
    make the overlay font too big. The merged quad has to stay slanted."""
    angle = 6.0
    first = slanted_quad(10, 100, 40, 20, angle)
    last = slanted_quad(60, 105, 40, 20, angle)

    merged = merge_line_quad([first, last])

    assert merged.angle_deg == pytest.approx(angle, abs=1.5)
    assert merged.height == pytest.approx(20, abs=0.5)
    assert merged.bbox.height > merged.height  # the bbox really is taller


def test_out_of_order_words_fall_back_to_a_bounding_box():
    right = slanted_quad(200, 100, 40, 20, 0)
    left = slanted_quad(10, 100, 40, 20, 0)

    merged = merge_line_quad([right, left])

    assert merged.bbox.x == pytest.approx(10)
    assert merged.bbox.width == pytest.approx(230)
    assert merged.angle_deg == pytest.approx(0.0)


# --------------------------------------------------------------------------
# Granularity
# --------------------------------------------------------------------------


def test_word_granularity_keeps_every_word_separate():
    words = [
        _detected("alpha", slanted_quad(0, 0, 40, 20, 0)),
        _detected("beta", slanted_quad(50, 0, 40, 20, 0), ends_line=True),
    ]

    regions = as_word_regions(words)

    assert [region.text for region in regions] == ["alpha", "beta"]
    assert all(region.level == "word" for region in regions)
    assert len({region.id for region in regions}) == 2


def test_trailing_whitespace_is_trimmed_from_a_line():
    words = [_detected("solo", slanted_quad(0, 0, 40, 20, 0), ends_line=True, trailing_space=True)]

    assert group_into_lines(words)[0].text == "solo"
