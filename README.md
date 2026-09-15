# Inkwell

Turn handwritten pages into text you can actually use — in two modes.

**Lens** detects text in place and lays a real, selectable text layer over your
photo, so you can drag across handwriting and copy it like any other text on the
web. The image is never modified; the text sits on top of it, rotated and scaled
to match the ink underneath.

**Scan & Edit** breaks a whole page into typed blocks — paragraphs, headings,
tables with real addressable cells, figures, underlines, highlights — so the page
can be rebuilt as an editable document rather than a picture of one.

> **Status: Phase 0 (scaffold).** The architecture, the API contract and the
> overlay are real and working. The engines that read the ink are mocked, so the
> whole app runs end to end with no API keys, no GPU and no credit card. Swapping
> in a real engine is one line in `backend/.env`.

---

## Quickstart

Two terminals, four commands:

```bash
# 1 — API
cd backend
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
cp .env.example .env
uvicorn app.main:app --reload          # http://localhost:8000/docs

# 2 — web
cd frontend
npm install
npm run dev                            # http://localhost:5173
```

Or `docker compose up` from the repo root, which runs both.

Open the app and hit **Use the sample page** — you'll get the Lens overlay
immediately, on generated text. The banner at the top tells you when you're
looking at mock output.

---

## The one idea worth understanding: the engine seam

Everything that reads an image sits behind a single interface. The API routes and
the frontend never know which engine is running.

```
POST /api/lens  ──>  OcrEngine.recognize(image)   ──>  LensResult
POST /api/scan  ──>  LayoutEngine.analyze(image)  ──>  DocumentStructure
```

Implementations register in `services/ocr/registry.py` and
`services/layout/registry.py`, and you pick one with an environment variable:

| Variable        | Options                              | Today   |
| --------------- | ------------------------------------ | ------- |
| `OCR_ENGINE`    | `mock`, `cloud_vision`, `paddle`     | `mock`  |
| `LAYOUT_ENGINE` | `mock`, `ppstructure`, `azure`       | `mock`  |

This is why the project can start on mocks and end on something real without a
rewrite — and why your own retrained CRNN can later become just another engine
behind the same interface, rather than something the app is built around.

### What's real and what isn't, honestly

| Piece                                 | State                                        |
| ------------------------------------- | -------------------------------------------- |
| API contract, schemas, geometry       | Real, tested                                 |
| Lens overlay (position, rotation, fit) | Real, verified in-browser                   |
| Mock OCR + mock layout engines        | Real, deterministic                          |
| `cloud_vision` adapter                | Written, **not yet verified** against the live API |
| `paddle` adapter                      | Written, **not yet verified**; assumes the classic `.ocr()` result shape |
| `ppstructure`, `azure` adapters       | Deliberate stubs — each raises with a mapping checklist in its docstring |
| Canvas editing, export, accounts      | Not started (Phases 3–5)                     |

The two stubs are stubs on purpose. Those libraries changed their output schemas
between major versions, and a mapping written from memory would look correct and
fail quietly — worse than an honest error in a file you'll build on for months.

---

## Layout

```
inkwell/
├── backend/
│   ├── app/
│   │   ├── api/           # routes: health, lens, scan
│   │   ├── schemas/       # the contract — Quad, TextRegion, Block, Table…
│   │   └── services/
│   │       ├── ocr/       # Mode 1 engines + registry
│   │       ├── layout/    # Mode 2 engines + registry
│   │       └── export/    # Phase 4
│   ├── fixtures/          # generates the demo page asset
│   └── tests/
├── frontend/
│   └── src/
│       ├── components/    # TextOverlay (the Lens trick), BlockOverlay
│       ├── modes/         # LensMode, ScanMode
│       └── types.ts       # mirrors backend/app/schemas
└── docs/architecture.md   # why each piece is the way it is
```

## Tests

```bash
cd backend
.venv/bin/python -m pytest      # 15 tests
.venv/bin/python -m ruff check app tests

cd ../frontend
npm run typecheck
npm run build
```

Geometry gets its own test file. The overlay is only as good as that maths, and a
silent error there looks like "OCR is bad" rather than "the box is in the wrong
place".

## Regenerating the sample page

```bash
cd backend && python fixtures/make_sample_page.py
```

It asks the mock engine where it will claim text is, then draws the text into
exactly those boxes — so a fresh clone shows a perfectly aligned overlay, which
makes it obvious later when a real engine lands badly.

---

## Roadmap

| Phase | What                                                    |
| ----- | ------------------------------------------------------- |
| 0     | Scaffold, engine seam, mocks, working overlay — **done** |
| 1     | Real Mode 1: verify the Cloud Vision adapter, line-level grouping |
| 2     | Real Mode 2: implement a structure engine, check blocks against real pages |
| 3     | Editable canvas (Excalidraw) + the OpenCV underline/highlight pass |
| 4     | Export: scene → DOCX (`python-docx`), scene → PDF (WeasyPrint) |
| 5     | Persistence, storage, accounts                          |
| 6     | Optional: retrain the original CRNN into an offline engine |
| 7     | Deployment                                              |

## Prior work

This grew out of [`Sanaharu-Santosh/NoteBook`](https://github.com/Sanaharu-Santosh/NoteBook),
a from-scratch CRNN + CTC handwriting recognizer. That repo stays as it is — it
reads one cropped word at a time, which is a different (and genuinely harder to
learn) problem than the one this app solves. Phase 6 is where it can come back as
a pluggable offline engine.
