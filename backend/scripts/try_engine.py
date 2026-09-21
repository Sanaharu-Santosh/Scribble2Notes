"""Run one image through one engine, print what came back, optionally save it.

This is the fastest way to compare engines — no browser, no server, no upload.

    # what does the mock produce?
    python scripts/try_engine.py --image ../frontend/public/sample-note.png

    # the real thing, and keep the response for offline work
    python scripts/try_engine.py --image page.jpg --engine cloud_vision --save-fixture

    # raw detection granularity, to see whether bad lines are grouping or detection
    python scripts/try_engine.py --image page.jpg --engine cloud_vision --granularity word

Saving a fixture writes a LensResult JSON that ``OCR_ENGINE=fixture`` replays,
so you can iterate on the overlay for hours against real output without
spending more quota.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config import get_settings  # noqa: E402
from app.services.layout.base import LayoutEngineError  # noqa: E402
from app.services.layout.registry import get_layout_engine  # noqa: E402
from app.services.ocr.base import OcrEngineError  # noqa: E402
from app.services.ocr.registry import get_ocr_engine  # noqa: E402

DEFAULT_FIXTURE = Path("fixtures/lens_fixture.json")


def _apply_overrides(args: argparse.Namespace) -> None:
    if args.engine:
        os.environ["OCR_ENGINE" if args.mode == "lens" else "LAYOUT_ENGINE"] = args.engine
    if args.granularity:
        os.environ["OCR_GRANULARITY"] = args.granularity

    get_settings.cache_clear()
    get_ocr_engine.cache_clear()
    get_layout_engine.cache_clear()


def _print_lens(result) -> None:
    print(f"\n{len(result.regions)} regions · {result.image_width}×{result.image_height}px\n")
    for region in result.regions:
        box = region.quad.bbox
        confidence = f"{region.confidence:.0%}".rjust(4)
        position = f"({box.x:>5.0f},{box.y:>5.0f})"
        angle = f"{region.quad.angle_deg:+.1f}°"
        print(f"  {confidence} {position} {angle:>7}  {region.text}")


def _print_structure(result) -> None:
    print(f"\n{len(result.blocks)} blocks · {result.page_width}×{result.page_height}px\n")
    for block in sorted(result.blocks, key=lambda b: b.reading_order):
        summary = block.text or ""
        if block.table:
            summary = f"{block.table.rows}×{block.table.cols} grid, {len(block.table.cells)} cells"
        marks = f"  [{', '.join(a.kind for a in block.annotations)}]" if block.annotations else ""
        print(f"  {block.reading_order}. {block.type.value:<10} {summary[:68]}{marks}")


async def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--image", required=True, type=Path, help="Image to run")
    parser.add_argument("--mode", choices=["lens", "scan"], default="lens")
    parser.add_argument("--engine", help="Override OCR_ENGINE / LAYOUT_ENGINE for this run")
    parser.add_argument("--granularity", choices=["line", "word"], help="Override OCR_GRANULARITY")
    parser.add_argument(
        "--save-fixture",
        nargs="?",
        const=str(DEFAULT_FIXTURE),
        metavar="PATH",
        help=f"Save the result for OCR_ENGINE=fixture (default: {DEFAULT_FIXTURE})",
    )
    parser.add_argument("--json", action="store_true", help="Print the full JSON payload")
    args = parser.parse_args()

    if not args.image.exists():
        print(f"No such image: {args.image}", file=sys.stderr)
        return 1

    _apply_overrides(args)
    image = args.image.read_bytes()

    engine = get_ocr_engine() if args.mode == "lens" else get_layout_engine()
    print(f"engine: {engine.name}{'  (MOCK OUTPUT)' if engine.is_mock else ''}")

    try:
        result = (
            await engine.recognize(image) if args.mode == "lens" else await engine.analyze(image)
        )
    except (OcrEngineError, LayoutEngineError) as exc:
        print(f"\nEngine unavailable: {exc}", file=sys.stderr)
        return 2

    print(f"took:   {result.engine.duration_ms} ms")

    if args.mode == "lens":
        _print_lens(result)
    else:
        _print_structure(result)

    if args.json:
        print(json.dumps(result.model_dump(mode="json"), indent=2))

    if args.save_fixture:
        if args.mode != "lens":
            print("\n--save-fixture only applies to --mode lens", file=sys.stderr)
            return 1
        path = Path(args.save_fixture)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(result.model_dump(mode="json"), indent=2), encoding="utf-8")
        print(f"\nsaved {path} — replay it with OCR_ENGINE=fixture")

    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
