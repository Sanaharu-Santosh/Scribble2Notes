# Working in this repo

## Commands

```bash
# backend (from backend/)
.venv/bin/python -m pytest
.venv/bin/python -m ruff check app tests scripts fixtures
uvicorn app.main:app --reload

# run one image through one engine — faster than the browser for engine work
python scripts/try_engine.py --image page.jpg [--engine cloud_vision] [--granularity word]
python scripts/try_engine.py --image page.jpg --mode scan

# regenerate test pages (the structured one carries its own ground truth)
python fixtures/make_sample_page.py
python fixtures/make_structured_page.py

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
- Canvas elements are built as *skeletons* through `convertToExcalidrawElements`,
  never hand-written: real elements carry seeds, nonces and binding metadata
  that are easy to get subtly wrong.
- `toScene.ts` emits elements in layers, not reading order. Z-order is array
  order, so a highlight after its text covers it. Keep the layering.
- Scan mode stays lazy-loaded in `App.tsx`. Importing it eagerly puts
  Excalidraw back on Lens's critical path.
- Geometry changes need a test in `backend/tests/test_geometry.py`. A wrong box
  looks like bad OCR, which is an expensive thing to misdiagnose.
- Engine adapters split response-walking from grouping (see `cloud_vision.py`),
  so the mapping can be tested against hand-built responses with no credentials.
  Keep that split in any new adapter.
- Tests pin their own engine settings via the `hermetic_settings` fixture in
  `conftest.py`. Don't read real config in a test — use `use_settings()`.
- Don't spend live API quota on work a fixture can serve: capture once with
  `try_engine.py --save-fixture`, then `OCR_ENGINE=fixture`.
- `services/layout/detect.py` is pure image processing — it imports no schemas
  and must stay that way, so it can be tested as plain CV.
- Tuning a CV threshold means re-running `test_layout_detect.py`. Those assert
  against recorded ground truth, not vibes; if a change needs the numbers
  loosened, that is the change being wrong, not the test.
- Line morphology closes gaps with a *closing*, never a dilation. Dilation
  lengthens every line by the kernel, which shows up as underlines wider than
  the words above them.

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
