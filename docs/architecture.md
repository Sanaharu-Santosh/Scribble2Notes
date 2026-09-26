# Architecture notes

Why the pieces are shaped the way they are. The README covers *what* to run; this
covers *why*, so a decision made once doesn't get relitigated from scratch later.

## Coordinate system

Every coordinate crossing the API is in **source-image pixels, origin top-left** —
never percentages, never screen pixels. The frontend computes one scale factor
(`rendered width ÷ source width`) and multiplies everything by it.

This is why the overlay survives window resizes, zoom, and a phone rotating:
there is exactly one place where display size enters the maths, and it's
recomputed by a `ResizeObserver` (`frontend/src/hooks.ts`).

## Quads, not rectangles

Regions come back as four corner points, clockwise from top-left, rather than
`{x, y, w, h}`. Handwriting is rarely axis-aligned — a line written on a slant
needs its own rotation or the overlay text sits *beside* the ink instead of on
it. Engines that only produce rectangles use `Quad.from_bbox()`.

`Quad` also serves three computed values so the frontend doesn't re-derive them:

- `bbox` — the tightest axis-aligned box, for hit-testing and block outlines.
- `angle_deg` — rotation of the top edge, clockwise-positive.
- `height` — top edge to bottom edge. **Not** the bbox height: for a slanted
  region the bbox is taller than the text, and sizing overlay text from the bbox
  makes every slanted line too big.

## The Lens overlay technique

`frontend/src/components/TextOverlay.tsx`. Per region:

1. Place a `<span>` at the quad's top-left corner, scaled by the display factor.
2. Set `font-size` to the quad's text height, `line-height: 1`, `white-space: pre`.
3. Measure the span's natural rendered width.
4. Apply `transform: rotate(angle) scaleX(targetWidth / naturalWidth)`.
5. Paint the glyphs `transparent`, but leave `::selection` visible.

Step 4 is what makes selection highlights line up: rather than hunting for a font
that happens to match the handwriting, render *any* font at the right height and
stretch it horizontally onto the measured target. This is the same approach
pdf.js uses for its text layer.

The reads and writes are batched — clear every transform, measure every width,
then write every transform — because interleaving them forces a reflow per
region, which is visible on a page with a hundred lines.

### Separators are load-bearing

Absolutely positioned spans sit next to each other in the DOM with nothing
between them, so a selection spanning several regions serializes as
`"...modelsCTC solves..."` — the copied text runs together and the headline
feature is worthless. `TextOverlay` inserts a `<br>` after each line region and a
space after each word region to fix that.

Those separators only survive because `.overlay` sets `white-space: pre`: a
whitespace-only text node in a normal-flow container is collapsed away, and
collapsed whitespace does not appear in the serialized selection. The same rule
sets `font-size: 0` and `line-height: 0` there, so the separators can't paint a
stray selection highlight in the corner; region spans set their own font size
inline and are unaffected.

If copied text ever loses its line breaks, this CSS rule is the first place to
look — it fails silently and only in the clipboard.

## Words in, lines out

Engines detect *words*. The app shows *lines*, because dragging across a whole
line is what selection is for — word-by-word selection feels broken even when
every word is correct.

Cloud Vision marks line endings on the symbol they follow, via
`detected_break`: `EOL_SURE_SPACE`, `LINE_BREAK` and `HYPHEN` end a line, while
`SPACE` and `SURE_SPACE` join words within one. `group_into_lines` walks those
and flushes a region at each ending. Two defensive details:

- A paragraph boundary always ends a line, even when the response carries no
  break — otherwise one missing field silently merges two paragraphs into a
  single unreadable region.
- Break types are compared as integers, not by importing the enum. The field has
  been spelled `type` and `type_` across library releases and the enum's import
  path has moved; the numbers have not.

A line's quad is built from the first word's left corners and the last word's
right corners, *not* a bounding box around all of them. For slanted writing a
bounding box is taller than the text, and the overlay sizes its font from the
quad height — so a bounding box would render every slanted line too large. When
words aren't in left-to-right order (the right edge lands left of the left edge)
the merge falls back to a bounding box, accepting the lost slant over a
nonsensical quad.

`OCR_GRANULARITY=word` turns grouping off. That exists as a diagnostic: run a
bad page both ways and you learn whether grouping or detection is at fault,
which are fixed in completely different places.

## The engine seam

`OcrEngine` and `LayoutEngine` (in `services/*/base.py`) are the only types the
routes know about. Concrete engines are chosen by environment variable through a
cached registry.

Three things this buys:

- **Mocks are first-class.** The app runs end to end from the first commit, so
  every later phase is "replace one implementation and compare", never "build
  everything and hope".
- **Provider choices stay reversible.** Cloud Vision today, self-hosted tomorrow,
  a mix per mode — no caller changes.
- **The CRNN has a way back in.** A retrained model becomes another engine behind
  the same interface (Phase 6), rather than something the app is rebuilt around.

Engines are cached (`@lru_cache`) because a self-hosted model loads weights on
construction; building one per request would be pathological.

## Structure without a model

Mode 2's default engine (`opencv`) finds structure with morphology rather than a
document model. That is a deliberate choice, not a stopgap.

A page of notes is ruled with a pen. Its tables are *lines*; its boxes are
*lines*; its underlines are *lines*; its highlights are *colour*. Morphology
finds those exactly, in about 100ms on a CPU, with nothing to download — where a
document model trained on printed PDFs is heavier, slower, and less sure about a
hand-ruled grid. And since underlines and highlights were always going to be
ours to detect, extracting horizontal lines for them makes table rules and box
edges fall out of the same pass.

The pipeline, in `services/layout/detect.py`:

1. Otsu threshold to an ink mask — a photographed page is never the same
   brightness twice, so a fixed threshold is no use.
2. Open with a long thin kernel, once horizontally and once vertically, to leave
   only rules. Gaps are closed with a *closing*, never a dilation: dilation
   stretches every line by the kernel length, which surfaces later as underlines
   wider than the words above them.
3. Connected components of `horizontal | vertical` give one blob per ruled
   rectangle. Crossings inside each blob cluster into row and column edges.
4. A grid with more than one cell is a table; a one-cell grid is a drawn box.

Step 3 is the part worth understanding. An earlier version clustered the
crossing points themselves by coordinate alignment, and merged the table with a
box two hundred pixels below it because they shared a left margin. **Alignment is
not connection.** Components of the ruling mask encode actual connection, which
is what "same table" means.

Text blocks come from the same mask with the ruling subtracted (grown slightly
first, or anti-aliased line edges survive as phantom paragraphs), smeared
horizontally into lines and then vertically into paragraphs.

Headings are classified by *line* height, never block height — a two-line
paragraph is taller than a one-line title, so comparing block heights labels
paragraphs as headings. `TextBlock.line_count` exists for exactly this.

### Structure and text are different problems

The `opencv` engine finds structure but cannot read. When `LAYOUT_FILL_TEXT` is
on it asks whichever `OCR_ENGINE` is configured for the page's words, then files
each recognized region into the block or cell containing its centre point —
centre containment rather than overlap, so a line poking a few pixels past a
cell border still belongs to one cell instead of two.

This composition is why Mode 2 improves for free whenever Mode 1's engine
does, and why neither half needs rewriting when the other changes. An OCR
failure is caught and ignored: structure without text still beats failing a
whole scan because a key expired.

## What no engine gives you

Underlines, highlights and hand-drawn boxes are not classes in any mainstream
layout model. They come from our own OpenCV pass (Phase 3) and arrive as
`Annotation` objects attached to the block they sit on:

- **Highlight** — HSV threshold for saturated, bright, non-ink colour behind text.
- **Underline** — near-horizontal line segments just below a text baseline
  (Hough transform or contour analysis), matched to the line above them.
- **Box** — closed near-rectangular contours containing text.

Expect iterative tuning here, not a library import. Budget accordingly.

## The canvas

`frontend/src/canvas/toScene.ts` turns a `DocumentStructure` into an Excalidraw
scene. Built from *skeletons* passed through `convertToExcalidrawElements`, not
hand-written elements: real Excalidraw elements carry seeds, version nonces and
binding metadata that are easy to get subtly wrong and that the library will
happily regenerate for you.

Each detected thing becomes the kind of object you would have drawn yourself:

| Detected | Becomes | Why that shape |
| --- | --- | --- |
| paragraph / heading | text element | retypeable in place |
| table cell | rectangle with a bound `label` | the text travels with the cell when dragged or resized; loose text beside a line would come apart on the first drag |
| block with no recognized text | dashed rectangle | says "type into me" instead of silently dropping a region that is really there |
| highlight | filled rectangle, 55% opacity | sits *behind* the words, as marker does |
| underline | line | |
| box | stroked rectangle | |
| the scan itself | locked image at 30% opacity | |

**Elements are emitted in layers, not in reading order.** Z-order is array
order, so a highlight written after its text would cover it and an underline
written before its text would be hidden — the stacking has to match what the
marks do on paper: background, highlights, cells, text, then marks on top.

**The background is locked.** Without it, the first drag moves the scanned page
out from under everything aligned to it. Toggling it changes only opacity, so
hiding it leaves a clean digital page and showing it again disturbs nothing the
user has moved.

**Font size divides by `line_count`.** Block height alone gives a two-line
paragraph type twice the size it should have — the same trap as heading
classification, one layer up. That is why `Block.line_count` exists in the
schema at all.

**Fitting the page needs `fitToViewport`, imperatively.** `scrollToContent` in
`initialData` centres the page but holds 100% zoom, so an A4 scan opens showing
its top third; `fitToContent` caps at 100% and cannot zoom out far enough
either. And the imperative API is handed to you a frame before the scene is
measurable, so fitting immediately fits an empty scene and silently does
nothing — hence the `requestAnimationFrame` retry.

**Scan mode is lazy-loaded.** Excalidraw is ~750KB gzipped-to-190KB plus its
font chunks. Lens is the lighter mode and the one people open first, so it
should not pay for an editor it never shows.

## Export

**Export reads the canvas, not the detection.** By the time someone exports they
have retyped paragraphs, moved cells and drawn arrows; exporting
`DocumentStructure` would hand them a file that ignores every edit they made.
`fromScene.ts` reads the live scene back into `ExportDocument`, using the id
prefixes from `toScene.ts` to recover structure — so a table is still a table
after the round trip, without re-deriving it from a flat list of rectangles.
Elements *without* that prefix are things the user drew, and are carried through
as their own items rather than dropped.

The two exporters want different things from the same document, which is why
`ExportItem` carries both geometry and role:

- **DOCX is flow.** Real heading styles (so Word's navigation pane works), real
  tables with addressable cells, reading order taken from current positions —
  move a paragraph up the page and it moves up the document. Positions are then
  discarded. Lines and arrows are dropped: they are spatial marks with no
  meaning in a flowed document, and they survive in the PDF instead.
- **PDF is place.** Absolutely positioned HTML rendered by WeasyPrint, so the
  page looks like what was on screen *and the text is still text* — selectable,
  searchable, copyable. That is the whole reason not to export a PNG of the
  canvas, and `test_export.py` asserts it by extracting the text back out.

Scale: scanned pages are ~150dpi and PDF works in points, so `px * 72/150` maps
a 1240×1754 scan onto exactly A4.

### Two things that bite here

**Word's highlight palette is fixed**, so the page's marker colour is matched to
the nearest named one — by *hue*, not RGB distance. Highlighter ink is pale and
grey sits in the middle of the RGB cube, so by Euclidean distance a pale green
is nearer grey than green: straight RGB matching sends almost every real
highlight to grey.

**A mark applies to the whole paragraph in DOCX.** The canvas knows an underline
runs from x=244 to x=634 but not which characters sit under those pixels, and
recovering that would need per-word coordinates that do not survive the user
retyping the paragraph. Underlining the whole paragraph is wrong in a way that
is visible and fixable in two clicks; guessing a character range is wrong in a
way you would have to hunt for.

**The document is user content and ends up inside HTML.** Text is escaped, and
colours — which also come from the canvas — are validated against a strict
pattern rather than escaped, because they land in `style` attributes and there
is no legitimate colour containing a semicolon.

## Persistence

**A saved page keeps the scene, not the structure.** Detection is a one-time
derivation; re-running it on the original scan would throw away every edit made
since. The scene *is* the document, and the scan is provenance.

**The scene is one JSONB column, not a normalised element table.** Nothing
queries *into* a scene — it is loaded and saved whole — and normalising it would
mean chasing Excalidraw's element schema forever, for no query that benefits.

**The scan is not in the row.** Base64 image data in JSONB makes every row
megabytes and every list query slow, so the bytes go through a third seam
(`STORAGE_BACKEND`: local disk or S3) and the row keeps a key. Deleting a page
drops the blob first: a row without its blob is a broken page, a blob without
its row is only wasted bytes.

**Timestamps are timezone-aware.** A naive one means "whatever zone the server
was in", which is fine until it is deployed on a UTC host and read by someone
who is not, and every "saved 3 hours ago" is wrong.

**`eager_defaults` on the mappers is load-bearing, not tuning.** Server-generated
values (`created_at`, and `updated_at` after an UPDATE) are otherwise marked
expired and refreshed on next access. Under async that is IO from a synchronous
property read, and the result is a `MissingGreenlet` error the moment anything
reads `updated_at` after a save.

**Migrations, not `create_all()`.** A deployed app needs a path from one schema
to the next, and Alembic reads the URL from the app's settings rather than
`alembic.ini` so there is exactly one place a connection string is configured.
Generated migrations are excluded from the linter — hand-formatting machine
output only means the next generated one fails.

### There is no sign-in

Every request resolves to one local account, created on first use. That is a
stopping point rather than an oversight: hand-rolling password auth for a solo
project is a bad trade, and a managed provider needs an account and keys
belonging to whoever deploys this.

What matters is that the schema is already multi-user. Pages carry an owner,
every query filters by it, and someone else's page returns **404 rather than
403** — a 403 confirms the id exists, which is more than a stranger should
learn. Adding Supabase or Clerk means replacing the body of `current_user` with
"verify the bearer token, look up or create the user it names", not reshaping
the database or revisiting every query.

Until then, treat a running instance as private. It is not so much insecure as
unauthenticated: whoever can reach the API is the user.

## The CRNN comes back as an engine

Phase 0 said the from-scratch model could "come back as another engine behind
the same interface" later. It did, and nothing outside
`app/services/ocr/crnn.py` changed to allow it — which is the seam doing the job
it was built for.

The interesting part is that the model reads *one pre-cropped word* and has no
idea where words are on a page. The CV pass already built for Mode 2 supplies
exactly that missing step: blocks, then lines, then word crops
(`detect.find_words`), by projection profile rather than by smearing ink
sideways — dilation needs a kernel wider than a letter gap and narrower than a
word gap, and on real text those distributions overlap.

It is measured, not assumed: 24/24 on its own training crops, ~51% CER on a real
page. `docs/crnn-engine.md` has the detail, including why beam search is
implemented but *not* the default — it scored worse, which is what beam search
does to a model that is confidently wrong rather than uncertain.

## Decisions on record

**Excalidraw, not tldraw, for the Phase 3 canvas.** tldraw's SDK is
source-available and requires a paid licence for production use; its free hobby
tier mandates a "made with tldraw" watermark on the canvas. Excalidraw is MIT,
embeddable as a React component, and its scene format can be built
programmatically from `DocumentStructure` — which is exactly the Phase 2 → 3
hand-off.

**React 18, not 19.** Pinned for Excalidraw peer-dependency compatibility. Revisit
when the canvas is actually wired up.

**Cloud for Mode 1, self-hosted for Mode 2.** Lens has to feel instant, and CPU
inference (seconds per image) doesn't; Cloud Vision's free tier covers all of
development. Scan is a batch operation where a few seconds is fine, so the free,
self-hosted engine fits — and Mode 2 is where per-page API costs would otherwise
add up fastest.

**Types are hand-mirrored in `frontend/src/types.ts` for now.** When the contract
starts moving (Phase 2), generate them from the OpenAPI document instead —
`npx openapi-typescript http://localhost:8000/openapi.json` — so the two sides
can't drift silently.

**`python-docx` + WeasyPrint for Phase 4 export.** `python-docx` produces real
Word paragraphs, tables and inline images, so the export stays editable after it
leaves the app. WeasyPrint renders the same scene as HTML/CSS to a
text-searchable PDF rather than a screenshot of one.
