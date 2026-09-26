"""The from-scratch CRNN, wired up as a real engine.

This is the model from
`Sanaharu-Santosh/NoteBook <https://github.com/Sanaharu-Santosh/NoteBook>`_ —
a CNN + bidirectional LSTM trained with CTC loss. It reads **one pre-cropped
word** and has no idea where words are on a page, so everything around it here
is the part it was missing: the CV pass finds blocks, splits them into lines and
lines into word crops (``detect.find_words``), and each crop goes through the
model. No network, no API key, no per-call cost.

Read this before using it
-------------------------

**The charset is lowercase a-z.** Twenty-six classes plus the CTC blank. Digits,
punctuation, capitals and spaces are not representable *at all* — "Unit 4" comes
back as letters only, not because recognition is poor but because there is no
output symbol for "4". No amount of retraining fixes that without changing the
output layer.

**It was trained on ~90 synthetic words** rendered from system fonts. Its own
README reports ~27% character error rate on words outside that vocabulary, which
is the honest number for anything real.

So this engine is architecturally complete and practically weak, and that is
worth being precise about rather than shipping quietly. It exists because it is
the only engine here that runs with no network and no cost, and because the path
to making it good is clear and written down in ``docs/crnn-engine.md``: retrain
on IAM with a charset that includes digits and punctuation.

Preprocessing matches ``dataset.py`` from that repo exactly — grayscale, scale to
[0,1], invert so ink is the high signal, then a plain resize to 32x128. Note the
original README describes an aspect-preserving resize with padding; the training
code does not do that, and the weights learned what the code did.
"""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

import cv2
import numpy as np
from starlette.concurrency import run_in_threadpool

from app.config import get_settings
from app.schemas.common import Quad, TextRegion
from app.schemas.lens import LensResult
from app.services.layout.detect import find_grids, find_text_blocks, find_words
from app.services.ocr.base import OcrEngine, OcrEngineError

IMG_HEIGHT, IMG_WIDTH = 32, 128


@lru_cache
def _load_model(model_path: str):
    # TensorFlow's import alone costs seconds and a lot of memory, so it stays
    # inside the engine rather than at module scope — importing the registry
    # must not drag TF into a process that will never use it.
    os.environ.setdefault("TF_CPP_MIN_LOG_LEVEL", "3")
    try:
        import tensorflow as tf  # noqa: PLC0415
    except ImportError as exc:
        raise OcrEngineError(
            "tensorflow is not installed. Run: pip install -r requirements-crnn.txt"
        ) from exc

    if not Path(model_path).exists():
        raise OcrEngineError(f"No CRNN model at {model_path}")
    return tf.keras.models.load_model(model_path, compile=False)


@lru_cache
def _load_charset(charset_path: str) -> list[str]:
    if not Path(charset_path).exists():
        raise OcrEngineError(f"No charset at {charset_path}")
    chars = [
        line.rstrip("\n")
        for line in Path(charset_path).read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    # Sorted, matching CharTable in the training code — the class order the
    # weights were trained against. Sorting differently silently scrambles
    # every prediction into a different letter.
    return sorted(set(chars))


def preprocess(crop: np.ndarray) -> np.ndarray:
    """Grayscale crop -> the exact tensor the model was trained on."""
    if crop.ndim == 3:
        crop = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
    image = crop.astype(np.float32) / 255.0
    image = 1.0 - image  # ink becomes the high signal
    image = cv2.resize(image, (IMG_WIDTH, IMG_HEIGHT), interpolation=cv2.INTER_LINEAR)
    return image[..., np.newaxis]


def greedy_decode(logits: np.ndarray, charset: list[str]) -> tuple[str, float]:
    """Argmax per step, collapse repeats, drop blanks."""
    blank = len(charset)
    ids = logits.argmax(axis=-1)
    probabilities = _softmax(logits)

    out: list[str] = []
    scores: list[float] = []
    previous = None
    for step, symbol in enumerate(ids):
        if symbol != blank and symbol != previous:
            out.append(charset[symbol])
            scores.append(float(probabilities[step, symbol]))
        previous = symbol

    return "".join(out), float(np.mean(scores)) if scores else 0.0


def beam_search_decode(
    logits: np.ndarray, charset: list[str], beam_width: int = 8
) -> tuple[str, float]:
    """Prefix beam search over the CTC output.

    Greedy decoding commits to the most likely symbol at each step and cannot
    recover when that is locally confident but globally wrong. Beam search keeps
    several partial transcriptions alive and lets a later step decide between
    them, which is where most of CTC's recoverable errors live.
    """
    blank = len(charset)
    probabilities = _softmax(logits)

    # prefix -> (probability it ends in blank, probability it ends in a symbol)
    beams: dict[str, tuple[float, float]] = {"": (1.0, 0.0)}

    for step in probabilities:
        next_beams: dict[str, tuple[float, float]] = {}

        for prefix, (p_blank, p_symbol) in beams.items():
            total = p_blank + p_symbol

            # Extend with a blank: the prefix is unchanged.
            entry = next_beams.get(prefix, (0.0, 0.0))
            next_beams[prefix] = (entry[0] + total * step[blank], entry[1])

            for index, char in enumerate(charset):
                probability = step[index]
                if probability < 1e-6:
                    continue

                if prefix and char == prefix[-1]:
                    # Repeating the last character only counts as a new symbol
                    # if a blank came between — otherwise CTC collapses it.
                    same = next_beams.get(prefix, (0.0, 0.0))
                    next_beams[prefix] = (same[0], same[1] + p_symbol * probability)
                    extended = prefix + char
                    entry = next_beams.get(extended, (0.0, 0.0))
                    next_beams[extended] = (entry[0], entry[1] + p_blank * probability)
                else:
                    extended = prefix + char
                    entry = next_beams.get(extended, (0.0, 0.0))
                    next_beams[extended] = (entry[0], entry[1] + total * probability)

        beams = dict(
            sorted(next_beams.items(), key=lambda item: sum(item[1]), reverse=True)[:beam_width]
        )

    best, (p_blank, p_symbol) = max(beams.items(), key=lambda item: sum(item[1]))
    return best, float(min(p_blank + p_symbol, 1.0))


def _softmax(logits: np.ndarray) -> np.ndarray:
    shifted = logits - logits.max(axis=-1, keepdims=True)
    exponentials = np.exp(shifted)
    return exponentials / exponentials.sum(axis=-1, keepdims=True)


class CrnnOcrEngine(OcrEngine):
    name = "crnn"

    async def recognize(self, image: bytes) -> LensResult:
        started = self._now()
        settings = get_settings()

        array = cv2.imdecode(np.frombuffer(image, np.uint8), cv2.IMREAD_COLOR)
        if array is None:
            raise OcrEngineError("Could not decode the image")
        height, width = array.shape[:2]

        model = _load_model(settings.crnn_model_path)
        charset = _load_charset(settings.crnn_charset_path)

        tables = [grid for grid in find_grids(array) if grid.is_table]
        blocks = find_text_blocks(array, exclude=tables)
        per_block = find_words(array, blocks)

        crops: list[np.ndarray] = []
        boxes: list[tuple[int, int, int, int]] = []
        for words in per_block:
            for rect in words:
                x, y, w, h = rect
                crops.append(preprocess(array[y : y + h, x : x + w]))
                boxes.append(rect)

        if not crops:
            return LensResult(
                image_width=width,
                image_height=height,
                regions=[],
                full_text="",
                engine=self._engine_info(started),
            )

        batch = np.stack(crops)
        logits = await run_in_threadpool(lambda: model.predict(batch, verbose=0))

        decode = beam_search_decode if settings.crnn_decoder == "beam" else greedy_decode
        regions: list[TextRegion] = []
        for index, (rect, word_logits) in enumerate(zip(boxes, logits, strict=True)):
            text, confidence = decode(word_logits, charset)
            if not text:
                continue
            x, y, w, h = rect
            regions.append(
                TextRegion(
                    id=f"crnn-word-{index}",
                    text=text,
                    quad=Quad.from_bbox(float(x), float(y), float(w), float(h)),
                    confidence=min(max(confidence, 0.0), 1.0),
                    level="word",
                )
            )

        return LensResult(
            image_width=width,
            image_height=height,
            regions=regions,
            full_text=" ".join(region.text for region in regions),
            engine=self._engine_info(started),
        )
