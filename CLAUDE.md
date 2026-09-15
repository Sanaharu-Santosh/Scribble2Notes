# Working in this repo

## Commands

```bash
# backend (from backend/)
.venv/bin/python -m pytest
.venv/bin/python -m ruff check app tests
uvicorn app.main:app --reload

# frontend (from frontend/)
npm run typecheck
npm run build
npm run dev
```

## Conventions

- Coordinates crossing the API are **source-image pixels, top-left origin**.
  Never percentages, never screen pixels. See `docs/architecture.md`.
- New engines subclass `OcrEngine` / `LayoutEngine` and register in the matching
  `registry.py`. Nothing outside `services/` should import a concrete engine.
- Heavy or optional dependencies (`google-cloud-vision`, `paddleocr`) are
  imported **inside** methods, so an unconfigured engine never breaks startup or
  the test suite. They live in their own `requirements-*.txt`.
- Engine failures raise `OcrEngineError` / `LayoutEngineError`, which map to 503
  with a readable `detail`. The frontend shows that text verbatim, so write the
  message for the person reading it.
- `frontend/src/types.ts` mirrors `backend/app/schemas/`. Change both together.
- Geometry changes need a test in `backend/tests/test_geometry.py`. A wrong box
  looks like bad OCR, which is an expensive thing to misdiagnose.

## Please don't

- Don't implement the `ppstructure` or `azure` adapters from memory. Their output
  schemas changed between major versions; each stub's docstring has the mapping
  checklist to work through **with the installed version's docs open**.
- Don't add PaddleOCR to the backend Dockerfile. It turns a ~200 MB image into a
  multi-gigabyte one — Phase 2 gives it its own service.
- Don't commit `.env` or service-account JSON.
- Don't let the mock engines drift from real engine output shape. They are the
  contract's reference implementation, and `fixtures/make_sample_page.py` draws
  the demo asset from the mock's own coordinates.

## Phase discipline

The roadmap in `README.md` is ordered by dependency: each phase proves the
riskiest new idea in the smallest slice before the next builds on it. If
something feels like it belongs to a later phase, it probably does — note it and
move on rather than half-building it now.
