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

## What no engine gives you

Underlines, highlights and hand-drawn boxes are not classes in any mainstream
layout model. They come from our own OpenCV pass (Phase 3) and arrive as
`Annotation` objects attached to the block they sit on:

- **Highlight** — HSV threshold for saturated, bright, non-ink colour behind text.
- **Underline** — near-horizontal line segments just below a text baseline
  (Hough transform or contour analysis), matched to the line above them.
- **Box** — closed near-rectangular contours containing text.

Expect iterative tuning here, not a library import. Budget accordingly.

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
