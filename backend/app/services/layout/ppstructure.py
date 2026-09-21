"""PP-StructureV3 adapter — the heavyweight Mode 2 option.

STATUS: install path verified, output mapping still unwritten.

What changed since this was first stubbed: the install was actually attempted
and the following is now known rather than assumed.

* The class is ``paddleocr.PPStructureV3``. The 2.x ``PPStructure`` class does
  **not exist** in paddleocr 3.x — so any mapping written from memory of the 2.x
  ``[{"type": ..., "bbox": ..., "res": ...}]` result shape would have been wrong
  from the first line.
* ``pip install paddleocr paddlepaddle`` is not enough. Constructing the
  pipeline raises ``paddlex.utils.deps.DependencyError`` until you also install
  the matching extra::

      pip install "paddlex[ocr]==$(python -c 'import paddlex; print(paddlex.__version__)')"

* Constructing it downloads model weights from one of HuggingFace, ModelScope,
  AIStudio or BOS. All four are unreachable from a sandboxed CI-style
  environment, which is why the mapping below still isn't written: there was no
  way to see a real result object, and guessing is what this file exists to
  avoid.

To finish it, on a machine with normal network access::

    python scripts/capture_layout.py --image fixtures/structured_page.png

That saves the raw pipeline output to ``fixtures/ppstructure_raw.json``. With
that in hand the remaining work is mechanical:

1. Cache the pipeline on the instance — weights load once, not once per request,
   the same way :class:`~app.services.ocr.paddle.PaddleOcrEngine` does.
2. Map each region's type onto :class:`~app.schemas.scan.BlockType`
   (text/title -> PARAGRAPH/HEADING, table -> TABLE, figure -> FIGURE).
3. Turn each table's recognized HTML into :class:`~app.schemas.scan.TableCell`
   rows and columns — this is the step that makes a table editable instead of a
   picture of a table.
4. Sort into reading order and assign ``reading_order``.
5. Leave ``annotations`` empty. Underlines and highlights come from our own CV
   pass, which the ``opencv`` engine already does.

Until then ``LAYOUT_ENGINE=opencv`` is the default and needs none of this: no
weights, no downloads, no GPU, and it handles ruled tables — which is what a
page of notes actually has — well. Reach for PP-StructureV3 when you need prose
layout analysis on dense printed documents, not before.
"""

from __future__ import annotations

from app.schemas.scan import DocumentStructure
from app.services.layout.base import LayoutEngine, LayoutEngineError


class PPStructureLayoutEngine(LayoutEngine):
    name = "ppstructure"

    async def analyze(self, image: bytes) -> DocumentStructure:
        raise LayoutEngineError(
            "The PP-StructureV3 adapter is not implemented yet — its output shape has "
            "never been observed here (model hosts were unreachable). Use "
            "LAYOUT_ENGINE=opencv, or run scripts/capture_layout.py on a networked "
            "machine to record a real result first. See this module's docstring."
        )
