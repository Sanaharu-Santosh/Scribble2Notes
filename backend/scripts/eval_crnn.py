"""Measure what the CRNN engine actually gets right.

Run it after any change to the model, the decoder or the word segmentation, so
"did that help" is a number rather than an impression::

    python scripts/eval_crnn.py

It reports character error rate against a page whose text is known, for both
decoders. CER is the fair metric here rather than word accuracy: the charset is
lowercase a-z, so every digit, capital and comma on the page is unrepresentable
and word accuracy would mostly measure that rather than recognition quality.

Both sides are normalised to lowercase letters only, for the same reason —
scoring the model on symbols it has no output class for tells you nothing you
did not already know.
"""

from __future__ import annotations

import argparse
import asyncio
import os
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

os.environ.setdefault("TF_CPP_MIN_LOG_LEVEL", "3")

from app.config import get_settings  # noqa: E402
from app.services.ocr.crnn import CrnnOcrEngine  # noqa: E402
from app.services.ocr.registry import get_ocr_engine  # noqa: E402

# The non-table text of fixtures/structured_page.png. Table cells are excluded
# because the layout pass hands them to the table path, not to word crops.
GROUND_TRUTH = """
Unit 4 - Layout analysis
A page is not a flat list of words. It has
structure: tables, boxes and underlines, which
each become a different editable object.
CER = edits / chars
No layout model reports underlines or highlights,
so we detect those ourselves and attach them.
"""


def normalise(text: str) -> str:
    return re.sub(r"[^a-z]", "", text.lower())


def edit_distance(a: str, b: str) -> int:
    """Levenshtein, iterative with two rows."""
    if len(a) < len(b):
        a, b = b, a
    previous = list(range(len(b) + 1))
    for i, char_a in enumerate(a, start=1):
        current = [i]
        for j, char_b in enumerate(b, start=1):
            current.append(
                min(previous[j] + 1, current[j - 1] + 1, previous[j - 1] + (char_a != char_b))
            )
        previous = current
    return previous[-1]


async def run(decoder: str, image: Path) -> tuple[str, int, float]:
    os.environ["OCR_ENGINE"] = "crnn"
    os.environ["CRNN_DECODER"] = decoder
    get_settings.cache_clear()
    get_ocr_engine.cache_clear()

    result = await CrnnOcrEngine().recognize(image.read_bytes())
    predicted = normalise(result.full_text)
    truth = normalise(GROUND_TRUTH)
    distance = edit_distance(predicted, truth)
    return predicted, len(result.regions), distance / max(len(truth), 1)


async def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--image", type=Path, default=Path("fixtures/structured_page.png"), help="Page to read"
    )
    args = parser.parse_args()

    if not args.image.exists():
        print(f"No such image: {args.image}", file=sys.stderr)
        return 1

    truth = normalise(GROUND_TRUTH)
    print(f"ground truth: {len(truth)} characters (lowercase letters only)\n")

    for decoder in ("greedy", "beam"):
        predicted, regions, cer = await run(decoder, args.image)
        print(f"{decoder:>6}: CER {cer:6.1%}   {regions} words   {len(predicted)} chars")
        print(f"         {predicted[:96]}…\n")

    print(
        "For context: the model's own README reports ~27% CER on held-out words\n"
        "from its synthetic training vocabulary. Anything well above that here is\n"
        "the gap between rendered training fonts and a real page."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
