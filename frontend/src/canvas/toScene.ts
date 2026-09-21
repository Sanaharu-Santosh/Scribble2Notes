import { convertToExcalidrawElements } from "@excalidraw/excalidraw";
import type { ExcalidrawElement } from "@excalidraw/excalidraw/element/types";
import type { BinaryFiles } from "@excalidraw/excalidraw/types";

import type { Annotation, Block, DocumentStructure } from "../types";

/**
 * Turns a detected page into an editable Excalidraw scene.
 *
 * This is where Mode 2 stops describing a page and starts handing over
 * something you can change. Each detected thing becomes the kind of object you
 * would have drawn yourself: a paragraph becomes text you can retype, a table
 * cell becomes a labelled rectangle that keeps its text when you drag it, a
 * highlight becomes a filled shape behind the words.
 *
 * Z-order matters and is why elements are emitted in layers rather than in
 * reading order: a highlight drawn after its text would cover it, and an
 * underline drawn before its text would be hidden by it — the same stacking the
 * marks have on paper.
 */

export const BACKGROUND_ELEMENT_ID = "scanned-page";
export const BACKGROUND_FILE_ID = "scanned-page-file";

/**
 * Element ids encode what each shape came from, so the canvas can be read back
 * into a structured document at export time (`fromScene.ts`).
 *
 * Without this, exporting would have to re-derive structure from a flat list of
 * rectangles and text — re-solving the problem Mode 2 already solved, and
 * badly. Anything *without* this prefix is something the user drew themselves,
 * which is exactly how the reader tells the two apart.
 */
export const ID_PREFIX = "s2n";

export const elementId = (role: string, ...parts: (string | number)[]) =>
  [ID_PREFIX, role, ...parts].join(":");

/** Faint enough to read the digital text over, strong enough to trace against. */
export const BACKGROUND_OPACITY = 30;

const INK = "#1a2233";
const PLACEHOLDER = "#8a93a0";

type Skeleton = Parameters<typeof convertToExcalidrawElements>[0] extends (infer T)[] | null
  ? T
  : never;

export interface PageImage {
  dataURL: string;
  mimeType: string;
  width: number;
  height: number;
}

/**
 * Font size that makes the digital text sit at the scale of the ink under it.
 *
 * Divides by the line count on purpose: block height alone would give a
 * two-line paragraph type twice the size it should have.
 */
function fontSizeFor(block: Block): number {
  const lines = Math.max(block.line_count ?? 1, 1);
  const perLine = block.quad.bbox.height / lines;
  return Math.round(Math.min(Math.max(perLine * 0.7, 10), 48));
}

function textSkeleton(block: Block): Skeleton[] {
  const { bbox } = block.quad;

  if (!block.text) {
    // Nothing was recognized here, but something *is* here. A dashed outline
    // says "type into me" rather than silently dropping the region.
    return [
      {
        type: "rectangle",
        id: elementId("placeholder", block.id),
        x: bbox.x,
        y: bbox.y,
        width: bbox.width,
        height: bbox.height,
        strokeColor: PLACEHOLDER,
        backgroundColor: "transparent",
        strokeStyle: "dashed",
        strokeWidth: 1,
      },
    ];
  }

  return [
    {
      type: "text",
      id: elementId(block.type === "heading" ? "heading" : "paragraph", block.id),
      x: bbox.x,
      y: bbox.y,
      width: bbox.width,
      text: block.text,
      fontSize: fontSizeFor(block),
      strokeColor: INK,
    },
  ];
}

function tableSkeletons(block: Block): Skeleton[] {
  if (!block.table) return [];

  // A labelled rectangle per cell: the text is bound to its cell, so moving or
  // resizing the cell carries the contents along. Lines plus loose text would
  // come apart the first time someone dragged anything.
  return block.table.cells.map((cell) => ({
    type: "rectangle" as const,
    id: elementId("cell", block.id, cell.row, cell.col),
    x: cell.quad.bbox.x,
    y: cell.quad.bbox.y,
    width: cell.quad.bbox.width,
    height: cell.quad.bbox.height,
    strokeColor: INK,
    backgroundColor: "transparent",
    strokeWidth: 1,
    ...(cell.text
      ? { label: { text: cell.text, fontSize: 16, strokeColor: INK, verticalAlign: "middle" } }
      : {}),
  })) as Skeleton[];
}

function figureSkeleton(block: Block): Skeleton {
  const { bbox } = block.quad;
  return {
    type: "rectangle",
    id: elementId("figure", block.id),
    x: bbox.x,
    y: bbox.y,
    width: bbox.width,
    height: bbox.height,
    strokeColor: PLACEHOLDER,
    backgroundColor: "transparent",
    strokeStyle: "dashed",
  };
}

function highlightSkeleton(annotation: Annotation, owner: string, index: number): Skeleton {
  const { bbox } = annotation.quad;
  return {
    type: "rectangle",
    id: elementId("mark", owner, index, "highlight"),
    x: bbox.x,
    y: bbox.y,
    width: bbox.width,
    height: bbox.height,
    strokeColor: "transparent",
    backgroundColor: annotation.color ?? "#ffe14d",
    fillStyle: "solid",
    opacity: 55,
    roundness: null,
  };
}

function markSkeleton(annotation: Annotation, owner: string, index: number): Skeleton {
  const { bbox } = annotation.quad;

  if (annotation.kind === "underline") {
    return {
      type: "line",
      id: elementId("mark", owner, index, "underline"),
      x: bbox.x,
      y: bbox.y,
      width: bbox.width,
      height: 0,
      points: [
        [0, 0],
        [bbox.width, 0],
      ],
      strokeColor: annotation.color ?? INK,
      strokeWidth: 2,
    };
  }

  return {
    type: "rectangle",
    id: elementId("mark", owner, index, annotation.kind),
    x: bbox.x,
    y: bbox.y,
    width: bbox.width,
    height: bbox.height,
    strokeColor: annotation.color ?? INK,
    backgroundColor: "transparent",
    strokeWidth: 2,
  };
}

export interface Scene {
  elements: ExcalidrawElement[];
  files: BinaryFiles;
}

export function structureToScene(structure: DocumentStructure, page: PageImage | null): Scene {
  const background: Skeleton[] = [];
  const highlights: Skeleton[] = [];
  const cells: Skeleton[] = [];
  const contents: Skeleton[] = [];
  const marks: Skeleton[] = [];

  if (page) {
    background.push({
      type: "image",
      id: BACKGROUND_ELEMENT_ID,
      fileId: BACKGROUND_FILE_ID as never,
      x: 0,
      y: 0,
      width: structure.page_width,
      height: structure.page_height,
      opacity: BACKGROUND_OPACITY,
      // Locked, or the first drag moves the page out from under everything.
      locked: true,
    });
  }

  const ordered = [...structure.blocks].sort((a, b) => a.reading_order - b.reading_order);

  for (const block of ordered) {
    block.annotations.forEach((annotation, index) => {
      if (annotation.kind === "highlight") {
        highlights.push(highlightSkeleton(annotation, block.id, index));
      } else {
        marks.push(markSkeleton(annotation, block.id, index));
      }
    });

    if (block.type === "table") cells.push(...tableSkeletons(block));
    else if (block.type === "figure") contents.push(figureSkeleton(block));
    else contents.push(...textSkeleton(block));
  }

  const skeletons = [...background, ...highlights, ...cells, ...contents, ...marks];
  const elements = convertToExcalidrawElements(skeletons, { regenerateIds: false });

  const files: BinaryFiles = page
    ? {
        [BACKGROUND_FILE_ID]: {
          id: BACKGROUND_FILE_ID as never,
          dataURL: page.dataURL as never,
          mimeType: page.mimeType as never,
          created: Date.now(),
        },
      }
    : {};

  return { elements: elements as ExcalidrawElement[], files };
}
