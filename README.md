# Scribble2Notes

Turn handwritten pages into text you can actually use — in two modes.

**Lens** detects text in place and lays a real, selectable text layer over your
photo, so you can drag across handwriting and copy it like any other text on the
web. The image is never modified; the text sits on top of it, rotated and scaled
to match the ink underneath.

**Scan & Edit** breaks a whole page into typed blocks — paragraphs, headings,
tables with real addressable cells, figures, underlines, highlights — so the page
can be rebuilt as an editable document rather than a picture of one.

> **Status: Phase 1.** The architecture, the API contract and the overlay are
> real and working, and the Cloud Vision mapping — including line grouping — is
> implemented and unit-tested against hand-built responses. What's left in this
> phase is the live check against a real key: see
> [docs/cloud-vision-setup.md](docs/cloud-vision-setup.md), about fifteen
> minutes. Until then the default engines are mocked, so the whole app still
> runs end to end with no API keys, no GPU and no credit card.

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

| Variable          | Options                                        | Default |
| ----------------- | ---------------------------------------------- | ------- |
| `OCR_ENGINE`      | `mock`, `fixture`, `cloud_vision`, `paddle`    | `mock`  |
| `LAYOUT_ENGINE`   | `mock`, `ppstructure`, `azure`                 | `mock`  |
| `OCR_GRANULARITY` | `line`, `word`                                 | `line`  |

This is why the project can start on mocks and end on something real without a
rewrite — and why your own retrained CRNN can later become just another engine
behind the same interface, rather than something the app is built around.

### Granularity, and why it's a switch

Engines detect words; the app groups them into lines, because dragging across a
whole line feels right and selecting word-by-word doesn't. `OCR_GRANULARITY=word`
turns the grouping off.

That switch is a diagnostic, not a preference. When lines come back wrongly
merged or split, run the same page both ways: if the individual words are
correct, the bug is in grouping (`group_into_lines`); if the words themselves are
wrong, it's detection, and no amount of grouping will save it.

### Working against real output without burning quota

Cloud Vision's free tier is 1,000 images a month, and styling an overlay can eat
that in an afternoon. So capture a response once and replay it:

```bash
cd backend
python scripts/try_engine.py --image notes.jpg --engine cloud_vision --save-fixture
# then set OCR_ENGINE=fixture in backend/.env
```

Every upload now replays that saved response — real engine output, no network,
no cost. The UI labels it `fixture<cloud_vision>` so it can't be mistaken for a
live call.

`scripts/try_engine.py` is also the fastest way to compare engines generally: it
runs one image through one engine and prints confidences, positions and slants,
with no browser and no server.

### What's real and what isn't, honestly

| Piece                                  | State                                        |
| -------------------------------------- | -------------------------------------------- |
| API contract, schemas, geometry        | Real, tested                                  |
| Lens overlay (position, rotation, fit)  | Real, verified in-browser                    |
| Multi-line copy/paste                  | Real, verified in-browser                     |
| Mock + fixture engines                 | Real, deterministic                           |
| `cloud_vision` mapping and line grouping | Implemented, unit-tested against hand-built responses |
| `cloud_vision` against the live API    | **Not yet run** — needs a key (15 min, see the setup doc) |
| `paddle` adapter                       | Written, **not yet verified**; assumes the classic `.ocr()` result shape |
| `ppstructure`, `azure` adapters        | Deliberate stubs — each raises with a mapping checklist in its docstring |
| Canvas editing, export, accounts       | Not started (Phases 3–5)                      |

The two stubs are stubs on purpose. Those libraries changed their output schemas
between major versions, and a mapping written from memory would look correct and
fail quietly — worse than an honest error in a file you'll build on for months.

---

## Layout

```
scribble2notes/
├── backend/
│   ├── app/
│   │   ├── api/           # routes: health, lens, scan
│   │   ├── schemas/       # the contract — Quad, TextRegion, Block, Table…
│   │   └── services/
│   │       ├── ocr/       # Mode 1 engines + registry
│   │       ├── layout/    # Mode 2 engines + registry
│   │       └── export/    # Phase 4
│   ├── fixtures/          # demo page generator + saved API responses
│   ├── scripts/           # try_engine.py — run an image through any engine
│   └── tests/
├── frontend/
│   └── src/
│       ├── components/    # TextOverlay (the Lens trick), BlockOverlay
│       ├── modes/         # LensMode, ScanMode
│       └── types.ts       # mirrors backend/app/schemas
└── docs/
    ├── architecture.md        # why each piece is the way it is
    └── cloud-vision-setup.md  # getting a key, and what to check when it fails
```

## Tests

```bash
cd backend
.venv/bin/python -m pytest      # 39 tests
.venv/bin/python -m ruff check app tests scripts fixtures

cd ../frontend
npm run typecheck
npm run build
```

Two areas get their own files, because both fail silently rather than loudly:

- **Geometry** (`test_geometry.py`). The overlay is only as good as this maths,
  and an error here looks like "the OCR is bad" rather than "the box is in the
  wrong place" — an expensive thing to misdiagnose.
- **The Cloud Vision mapping** (`test_cloud_vision_mapping.py`). Response
  walking and line grouping are tested against hand-built responses, so the live
  check is a confirmation rather than a debugging session. It covers the things
  that actually break: break-type handling, line quads keeping their slant, and
  the field-spelling differences between library versions.

The suite pins its own engine settings, so it keeps passing once you put real
credentials in `backend/.env`.

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
| 1     | Real Mode 1: line grouping, fixture replay, engine CLI — **done**, live key check outstanding |
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
