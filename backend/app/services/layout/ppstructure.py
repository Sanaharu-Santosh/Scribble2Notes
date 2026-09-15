"""PP-StructureV3 adapter — the self-hosted Mode 2 default.

STATUS: deliberately not implemented yet. This is Phase 2 work.

Why it is a stub rather than a guess: PaddleOCR's structure output schema
changed materially between 2.x (``PPStructure``, list-of-dict results with
``type`` / ``bbox`` / ``res``) and 3.x (``PPStructureV3``, pipeline results with
a different envelope). Writing a mapping against the wrong one produces code
that looks right and fails quietly, which is worse than an honest stub in a file
you are going to build on for months.

What Phase 2 has to do here, with the installed version's docs open:

1. Construct the pipeline once (weights download on first use) and cache it,
   the same way :class:`~app.services.ocr.paddle.PaddleOcrEngine` does.
2. Map each returned region's ``type`` onto :class:`~app.schemas.scan.BlockType`
   (text/title -> PARAGRAPH/HEADING, table -> TABLE, figure -> FIGURE).
3. For tables, turn the recognized HTML grid into
   :class:`~app.schemas.scan.TableCell` rows/cols — this is the part that makes
   a table editable rather than a picture of a table.
4. Sort blocks into reading order and assign ``reading_order``.
5. Leave ``annotations`` empty: underlines and highlights come from our own
   OpenCV pass, not from this engine.

Until then, ``LAYOUT_ENGINE=mock`` gives the frontend a realistic page to build
the canvas against.
"""

from __future__ import annotations

from app.schemas.scan import DocumentStructure
from app.services.layout.base import LayoutEngine, LayoutEngineError


class PPStructureLayoutEngine(LayoutEngine):
    name = "ppstructure"

    async def analyze(self, image: bytes) -> DocumentStructure:
        raise LayoutEngineError(
            "The PP-StructureV3 adapter is a Phase 2 task and is not implemented yet. "
            "Use LAYOUT_ENGINE=mock for now — see this module's docstring for the "
            "mapping checklist."
        )
