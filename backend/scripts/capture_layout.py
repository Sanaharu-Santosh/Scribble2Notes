"""Record PP-StructureV3's real output so the adapter can be written against it.

Run this on a machine with normal network access — the first run downloads model
weights (hundreds of MB) from HuggingFace or one of Paddle's other hosts.

    pip install -r requirements-paddle.txt
    python scripts/capture_layout.py --image fixtures/structured_page.png

It writes two things:

* ``fixtures/ppstructure_raw.json`` — the full result, for writing the mapping
  against and for tests to replay.
* a printed summary of the actual key names and types, which is the bit that
  differs between versions and the reason this script exists rather than a
  mapping written from memory.

Nothing here converts to our schemas. That is deliberate: capture first, look at
what really came back, then map.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

DEFAULT_OUTPUT = Path("fixtures/ppstructure_raw.json")


def describe(value, indent: int = 2, depth: int = 0) -> None:
    """Print the shape of a nested result without dumping megabytes of numbers."""
    pad = " " * indent
    if depth > 3:
        return
    if isinstance(value, dict):
        for key, item in value.items():
            kind = type(item).__name__
            size = f" len={len(item)}" if hasattr(item, "__len__") else ""
            print(f"{pad}{key}: {kind}{size}")
            if isinstance(item, dict | list):
                describe(item, indent + 2, depth + 1)
    elif isinstance(value, list) and value:
        print(f"{pad}[0] is {type(value[0]).__name__}")
        describe(value[0], indent + 2, depth + 1)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--image", required=True, type=Path)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()

    if not args.image.exists():
        print(f"No such image: {args.image}", file=sys.stderr)
        return 1

    try:
        from paddleocr import PPStructureV3
    except ImportError:
        print("paddleocr is not installed. Run: pip install -r requirements-paddle.txt")
        return 2

    try:
        pipeline = PPStructureV3()
    except Exception as exc:  # dependency extras, or no reachable model host
        print(f"Could not construct PPStructureV3: {exc}\n", file=sys.stderr)
        print(
            'If this mentions dependencies, run:\n'
            '  pip install "paddlex[ocr]==$(python -c \'import paddlex; '
            "print(paddlex.__version__)')\"\n"
            "If it mentions model hosts, the machine cannot reach HuggingFace / "
            "ModelScope / AIStudio / BOS.",
            file=sys.stderr,
        )
        return 3

    results = list(pipeline.predict(str(args.image)))
    print(f"results: {len(results)}  (type: {type(results[0]).__name__})")

    payload = None
    for attribute in ("json", "res"):
        if hasattr(results[0], attribute):
            payload = getattr(results[0], attribute)
            print(f"reading result.{attribute} ({type(payload).__name__})")
            break
    if payload is None and isinstance(results[0], dict):
        payload = results[0]

    if payload is None:
        print("Could not find a dict payload on the result object.", file=sys.stderr)
        print("attributes:", [a for a in dir(results[0]) if not a.startswith("_")])
        return 4

    print("\n=== shape ===")
    describe(payload)

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
    print(f"\nwrote {args.out}")
    print("Next: map these keys onto our schemas in app/services/layout/ppstructure.py")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
