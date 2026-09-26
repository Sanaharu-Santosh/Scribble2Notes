"""The offline CRNN engine.

Split so most of it runs without TensorFlow: preprocessing, decoding and charset
loading are plain numpy and get tested directly, while the tests that need the
model skip when TF isn't installed. TF is a 600MB dependency nobody should have
to install to run the rest of this suite.
"""

from __future__ import annotations

import csv
from pathlib import Path

import numpy as np
import pytest

from app.services.ocr.crnn import (
    IMG_HEIGHT,
    IMG_WIDTH,
    _load_charset,
    beam_search_decode,
    greedy_decode,
    preprocess,
)

MODELS = Path(__file__).resolve().parents[1] / "models" / "crnn"
CHARSET_FILE = MODELS / "charset.txt"
MODEL_FILE = MODELS / "crnn_inference_model.keras"

ALPHABET = [chr(code) for code in range(ord("a"), ord("z") + 1)]
BLANK = len(ALPHABET)


def _logits(sequence: list[int], confidence: float = 12.0) -> np.ndarray:
    """One-hot-ish logits, one row per timestep."""
    out = np.zeros((len(sequence), BLANK + 1), dtype=np.float32)
    for step, symbol in enumerate(sequence):
        out[step, symbol] = confidence
    return out


# --------------------------------------------------------------------------
# Preprocessing — must match the training code exactly
# --------------------------------------------------------------------------


def test_preprocess_produces_the_shape_the_model_expects():
    crop = np.full((40, 200), 255, dtype=np.uint8)

    tensor = preprocess(crop)

    assert tensor.shape == (IMG_HEIGHT, IMG_WIDTH, 1)
    assert tensor.dtype == np.float32


def test_preprocess_inverts_so_ink_is_the_high_signal():
    """The training pipeline does `1.0 - img`. Skip it and every prediction is
    made from the negative of what the weights learned."""
    white_paper = preprocess(np.full((40, 200), 255, dtype=np.uint8))
    black_ink = preprocess(np.zeros((40, 200), dtype=np.uint8))

    assert white_paper.max() == pytest.approx(0.0)
    assert black_ink.min() == pytest.approx(1.0)


def test_preprocess_accepts_colour_crops():
    tensor = preprocess(np.zeros((40, 200, 3), dtype=np.uint8))
    assert tensor.shape == (IMG_HEIGHT, IMG_WIDTH, 1)


# --------------------------------------------------------------------------
# Decoding
# --------------------------------------------------------------------------


def test_greedy_collapses_repeats_and_drops_blanks():
    # c c - a a - t  ->  "cat"
    sequence = [2, 2, BLANK, 0, 0, BLANK, 19]

    text, confidence = greedy_decode(_logits(sequence), ALPHABET)

    assert text == "cat"
    assert 0.0 < confidence <= 1.0


def test_a_blank_between_repeats_keeps_both_letters():
    """Without the blank, CTC cannot express a doubled letter at all — this is
    the whole reason the blank class exists."""
    assert greedy_decode(_logits([11, BLANK, 11]), ALPHABET)[0] == "ll"
    assert greedy_decode(_logits([11, 11]), ALPHABET)[0] == "l"


def test_beam_search_agrees_with_greedy_when_the_model_is_confident():
    """On confident input there is nothing to search, so a disagreement here
    means the beam implementation is wrong rather than clever."""
    sequence = [2, 2, BLANK, 0, 0, BLANK, 19]

    assert beam_search_decode(_logits(sequence), ALPHABET)[0] == "cat"


def test_beam_search_can_prefer_a_path_greedy_never_considers():
    """Greedy commits per timestep; beam keeps alternatives alive.

    Two steps that each marginally favour a blank, but whose combined
    non-blank mass is larger, collapse to nothing under greedy.
    """
    logits = np.zeros((2, BLANK + 1), dtype=np.float32)
    logits[0, BLANK] = 0.6
    logits[0, 0] = 0.5  # 'a'
    logits[1, BLANK] = 0.6
    logits[1, 0] = 0.5

    assert greedy_decode(logits, ALPHABET)[0] == ""
    assert beam_search_decode(logits, ALPHABET, beam_width=8)[0] == "a"


def test_empty_output_is_not_a_crash():
    assert greedy_decode(_logits([BLANK, BLANK]), ALPHABET) == ("", 0.0)


# --------------------------------------------------------------------------
# Charset
# --------------------------------------------------------------------------


@pytest.mark.skipif(not CHARSET_FILE.exists(), reason="model not vendored")
def test_charset_is_sorted_like_the_training_code():
    """CharTable sorts. Load the file in any other order and every prediction
    silently becomes a different letter — no error, just wrong text."""
    charset = _load_charset(str(CHARSET_FILE))

    assert charset == sorted(charset)
    assert charset == ALPHABET


@pytest.mark.skipif(not CHARSET_FILE.exists(), reason="model not vendored")
def test_the_charset_really_is_only_lowercase_letters():
    """Guards the documented limitation: no digit, capital or comma has an
    output class, so no amount of retraining this checkpoint produces one."""
    charset = _load_charset(str(CHARSET_FILE))

    assert len(charset) == 26
    assert not any(char.isdigit() or char.isupper() for char in charset)


# --------------------------------------------------------------------------
# The model itself
# --------------------------------------------------------------------------


@pytest.mark.skipif(not MODEL_FILE.exists(), reason="model not vendored")
def test_the_pipeline_reads_its_own_training_images():
    """End to end on in-distribution data, which is what separates 'the wiring
    is wrong' from 'the model is weak'.

    If this passes and a real page still scores badly, the preprocessing,
    charset order and decoder are all correct and the gap is the model's
    training data — which is exactly the situation documented in
    docs/crnn-engine.md.
    """
    pytest.importorskip("tensorflow", reason="OCR_ENGINE=crnn needs requirements-crnn.txt")

    samples = Path(__file__).resolve().parents[1] / "fixtures" / "crnn_samples"
    labels = samples / "labels.csv"
    if not labels.exists():
        pytest.skip("no sample crops — see fixtures/crnn_samples/README")

    import cv2

    from app.services.ocr.crnn import _load_model

    model = _load_model(str(MODEL_FILE))
    charset = _load_charset(str(CHARSET_FILE))

    rows = list(csv.DictReader(labels.open()))
    crops = [
        preprocess(cv2.imread(str(samples / row["filename"]), cv2.IMREAD_GRAYSCALE))
        for row in rows
    ]
    predictions = model.predict(np.stack(crops), verbose=0)

    correct = sum(
        greedy_decode(logits, charset)[0] == row["label"]
        for logits, row in zip(predictions, rows, strict=True)
    )
    assert correct == len(rows), f"only {correct}/{len(rows)} in-distribution words read correctly"
