# Scribble2Notes

Turn handwritten pages into text you can actually use — in two modes.

**Lens** detects text in place and lays a real, selectable text layer over your
photo, so you can drag across handwriting and copy it like any other text on the
web. The image is never modified; the text sits on top of it, rotated and scaled
to match the ink underneath.

**Scan & Edit** breaks a whole page into typed blocks — paragraphs, headings,
tables with real addressable cells, figures, underlines, highlights — and loads
them into a canvas editor as editable objects. Retype a paragraph, drag a table
cell and its text comes with it, draw an arrow, delete what you don't want. The
scan sits underneath at low opacity as a tracing guide; hide it and you have a
clean digital page. Export it as **Word** (flowing and editable — real headings,
real tables) or **PDF** (the page exactly as arranged, with the text still
selectable rather than a screenshot). Export reads the canvas, so it includes
whatever you changed.

> **Status: Phase 5.** Scan a page, edit it, save it, come back to it later, and
> export it as a Word document or a PDF. Structure detection runs locally with
> no credentials, no model weights and no GPU, in about 100ms a page.
>
> Two things are deliberately not done yet. **There is no sign-in** — every
> request resolves to one local account, so don't put this on a public URL as
> it stands (see `app/services/auth.py`, which is the seam a real provider drops
> into). And Mode 1's Cloud Vision mapping still wants one live check against a
> real key: [docs/cloud-vision-setup.md](docs/cloud-vision-setup.md), about
> fifteen minutes. Until then the text you see is generated while the structure
> is real.

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

Or `docker compose up` from the repo root, which runs both plus PostgreSQL and
applies migrations first.

Saving pages needs a database. With Docker that is handled; without it, point
`DATABASE_URL` at a PostgreSQL you control and run `alembic upgrade head`.
Everything else — both modes, export — works with no database at all.

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

| Variable            | Options                                            | Default  |
| ------------------- | -------------------------------------------------- | -------- |
| `OCR_ENGINE`        | `mock`, `fixture`, `cloud_vision`, `paddle`, `crnn` | `mock`  |
| `LAYOUT_ENGINE`     | `opencv`, `mock`, `ppstructure`, `azure`           | `opencv` |
| `OCR_GRANULARITY`   | `line`, `word`                                     | `line`   |
| `LAYOUT_FILL_TEXT`  | `true`, `false`                                    | `true`   |
| `STORAGE_BACKEND`   | `local`, `s3`                                      | `local`  |

This is why the project can start on mocks and end on something real without a
rewrite — and why your own retrained CRNN can later become just another engine
behind the same interface, rather than something the app is built around.

### Mode 2 needs no setup at all

Structure detection is classical computer vision, not a model: ruled tables
become real addressable cell grids, drawn boxes and underlines and highlighter
marks become annotations attached to the block they sit on. Nothing to download,
no GPU, ~100ms a page.

That is the right tool for this job rather than a compromise. A page of notes is
ruled with a pen — its tables are lines, its boxes are lines, its highlights are
colour — and morphology finds those exactly, where a document model trained on
printed PDFs is heavier and less sure. `docs/architecture.md` has the pipeline.

Structure and reading are kept separate: the engine finds *where* and *what
kind*, then asks whichever `OCR_ENGINE` is configured for the words and files
each one into the block or cell it falls inside. So Mode 2 gets better every time
Mode 1 does, and an OCR failure costs you the text but not the structure.

### The from-scratch model, wired up

`OCR_ENGINE=crnn` runs the CRNN from the original NoteBook repo with no network
and no cost. The CV pass supplies what that model never had — it finds the
blocks, splits them into lines and lines into word crops — and each crop goes
through the model.

It is honestly measured rather than quietly shipped: **24/24 exact on its own
training distribution, ~51% character error rate on a real page.** Those two
numbers together say the wiring is right and the model is the limit — its
charset is lowercase `a`–`z`, so digits and capitals are unrepresentable before
recognition even begins. [docs/crnn-engine.md](docs/crnn-engine.md) has the
measurements and what would actually fix it. Use `cloud_vision` to read your
notes; this one makes the offline story true rather than aspirational.

### Saving, and the seam where sign-in goes

A saved page keeps the **canvas scene**, not the detected structure. Detection
is a one-time derivation: re-running it on the original scan would discard every
edit made since. The scene is the document; the scan is provenance, and it goes
through a third seam (`STORAGE_BACKEND`, local disk or S3) rather than into a
JSONB column, because base64 images in rows make every list query slow.

There is **no sign-in**. Every request resolves to one local account, created on
first use. That is a deliberate stopping point rather than an oversight —
hand-rolling password auth for a solo project is a bad trade, and a managed
provider needs an account that belongs to whoever deploys this. What matters is
that the schema is already multi-user: pages carry an owner, every query filters
by it, and someone else's page returns 404 rather than 403 so its existence
doesn't leak. Adding Supabase or Clerk means replacing the body of
`current_user`, not reshaping the database.

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
| `opencv` structure engine              | Real, tested against a page with recorded ground truth |
| `paddle` adapter                       | Written, **not yet verified**; assumes the classic `.ocr()` result shape |
| `ppstructure`, `azure` adapters        | Stubs — install path verified for PP-StructureV3, mapping unwritten |
| Canvas editing (Excalidraw)            | Real, verified in-browser                     |
| DOCX / PDF export                      | Real, verified by opening the generated files |
| Saving and reopening pages             | Real, tested against PostgreSQL               |
| `local` scan storage                   | Real, tested                                  |
| `s3` scan storage                      | Written, **never run** — no bucket to try it against |
| `crnn` offline engine                  | Real and measured: 24/24 in-distribution, **~51% CER on a real page** |
| Sign-in                                | **Not built.** One local account; see the seam in `app/services/auth.py` |

The stubs are stubs on purpose, and PP-StructureV3 is the case in point. Its
install was actually attempted: paddleocr 3.x renamed the class and **removed**
the 2.x `PPStructure` entirely, and the pipeline needs a `paddlex[ocr]` extra
that `pip install paddleocr` does not pull in. A mapping written from memory of
the 2.x result shape would have been wrong on its first line and failed quietly.
`scripts/capture_layout.py` records a real result on a networked machine so the
mapping can be written against fact; the module docstring has the checklist.

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
│       ├── canvas/        # DocumentStructure -> Excalidraw scene
│       ├── components/    # TextOverlay (the Lens trick), ImagePicker
│       ├── modes/         # LensMode, ScanMode
│       └── types.ts       # mirrors backend/app/schemas
└── docs/
    ├── architecture.md        # why each piece is the way it is
    └── cloud-vision-setup.md  # getting a key, and what to check when it fails
```

## Tests

```bash
cd backend
.venv/bin/python -m pytest      # 96 tests (11 skip without PostgreSQL)
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
- **Saving** (`test_pages.py`). Against a real PostgreSQL, not SQLite standing
  in for it: the schema leans on JSONB and a descending composite index, and a
  suite that runs on a different database than production agrees with you right
  up until you deploy. They skip with instructions if Postgres isn't running.
- **The exports** (`test_export.py`). The generated files are opened and read
  back, not byte-counted: the DOCX must have real heading styles and a real
  table with addressable cells, and the PDF's text must *extract as text* —
  which is the entire difference between this and exporting a picture.
- **CV detection** (`test_layout_detect.py`). `fixtures/make_structured_page.py`
  draws a page *and records where it put everything*, so these are real
  assertions — the table is within 0.9 IoU of the real one and has exactly four
  rows and three columns — rather than "it found some boxes, looks about right".
  Tuning that quietly breaks underline detection fails here, not in your notes.

The suite pins its own engine settings, so it keeps passing once you put real
credentials in `backend/.env`.

## Regenerating the sample pages

```bash
cd backend
python fixtures/make_sample_page.py        # Lens demo: lines of writing
python fixtures/make_structured_page.py    # Scan demo: table, box, underline, highlight
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
| 2     | Real Mode 2: CV structure engine, tables as real grids, annotations — **done** |
| 3     | Editable canvas (Excalidraw) — **done** (the CV annotation pass landed in Phase 2) |
| 4     | Export: scene → DOCX (`python-docx`), scene → PDF (WeasyPrint) — **done** |
| 5     | Persistence and storage — **done**; accounts deliberately deferred |
| 6     | The original CRNN wired up as an offline engine — **done**, and measured |
| 7     | Deployment                                              |

## Prior work

This grew out of [`Sanaharu-Santosh/NoteBook`](https://github.com/Sanaharu-Santosh/NoteBook),
a from-scratch CRNN + CTC handwriting recognizer. That repo stays as it is — it
reads one cropped word at a time, which is a different (and genuinely harder to
learn) problem than the one this app solves. Phase 6 is where it can come back as
a pluggable offline engine.
