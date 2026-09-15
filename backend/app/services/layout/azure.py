"""Azure AI Document Intelligence (Layout model) — the managed Mode 2 fallback.

STATUS: deliberately not implemented yet. This is Phase 2 work, and only if
self-hosting PP-StructureV3 turns out to be more operational pain than it is
worth. Free tier covers 500 pages/month.

What Phase 2 has to do here, against the ``azure-ai-documentintelligence`` SDK:

1. Build ``DocumentIntelligenceClient(endpoint, AzureKeyCredential(key))`` from
   ``AZURE_DI_ENDPOINT`` / ``AZURE_DI_KEY``, and run ``prebuilt-layout``.
2. Map ``result.paragraphs`` -> PARAGRAPH/HEADING blocks (``paragraph.role``
   distinguishes titles and section headings).
3. Map ``result.tables`` -> :class:`~app.schemas.scan.Table`, using each cell's
   ``row_index`` / ``column_index`` / ``row_span`` / ``column_span``.
4. Convert Azure polygons — a flat ``[x1, y1, x2, y2, ...]`` list — into
   :class:`~app.schemas.common.Quad`, and confirm the unit is pixels for image
   input (it is inches for PDF input, which would silently misplace everything).
"""

from __future__ import annotations

from app.schemas.scan import DocumentStructure
from app.services.layout.base import LayoutEngine, LayoutEngineError


class AzureLayoutEngine(LayoutEngine):
    name = "azure"

    async def analyze(self, image: bytes) -> DocumentStructure:
        raise LayoutEngineError(
            "The Azure Document Intelligence adapter is a Phase 2 task and is not "
            "implemented yet. Use LAYOUT_ENGINE=mock for now — see this module's "
            "docstring for the mapping checklist."
        )
