import type { ExcalidrawElement } from "@excalidraw/excalidraw/element/types";

import { BACKGROUND_ELEMENT_ID, ID_PREFIX } from "./toScene";
import type { ExportDocument, ExportItem, ExportMark, ExportTable } from "../types";

/**
 * Reads the live canvas back into a structured document for export.
 *
 * The important property: this reads the canvas, not the detection. By the time
 * someone exports, they have retyped paragraphs, moved cells and drawn arrows —
 * exporting `DocumentStructure` would hand them a file that ignores every edit
 * they made.
 *
 * Element ids carry where each shape came from (see `toScene.ts`), so structure
 * survives the round trip without having to be re-derived from a flat list of
 * rectangles. Anything without that prefix is something the user drew, and is
 * carried through as its own item rather than dropped.
 */

interface ParsedId {
  role: string;
  owner: string;
  rest: string[];
}

function parseId(id: string): ParsedId | null {
  if (!id.startsWith(`${ID_PREFIX}:`)) return null;
  const [, role, owner, ...rest] = id.split(":");
  if (!role || !owner) return null;
  return { role, owner, rest };
}

/** Text bound inside a container (a table cell's label) lives in its own element. */
function boundTextByContainer(elements: readonly ExcalidrawElement[]): Map<string, string> {
  const map = new Map<string, string>();
  for (const element of elements) {
    if (element.type === "text" && element.containerId) {
      map.set(element.containerId, element.text.trim());
    }
  }
  return map;
}

function markKind(role: string[]): ExportMark["kind"] {
  const kind = role[role.length - 1];
  return kind === "highlight" || kind === "box" ? kind : "underline";
}

export function sceneToDocument(
  elements: readonly ExcalidrawElement[],
  page: { width: number; height: number },
  title?: string,
): ExportDocument {
  const live = elements.filter(
    (element) => !element.isDeleted && element.id !== BACKGROUND_ELEMENT_ID,
  );
  const bound = boundTextByContainer(live);

  const items: ExportItem[] = [];
  const marksByOwner = new Map<string, ExportMark[]>();
  const cellsByTable = new Map<string, { rows: number; cols: number; cells: ExportTable["cells"] }>();
  const tableBounds = new Map<string, { x: number; y: number; right: number; bottom: number }>();

  for (const element of live) {
    const parsed = parseId(element.id);
    const base = {
      id: element.id,
      x: element.x,
      y: element.y,
      width: element.width,
      height: element.height,
      color: element.strokeColor,
      reading_order: 0,
    };

    // ---- things that came from detection -------------------------------
    if (parsed) {
      if (parsed.role === "mark") {
        const kind = markKind(parsed.rest);
        const existing = marksByOwner.get(parsed.owner) ?? [];
        existing.push({
          kind,
          color: kind === "highlight" ? element.backgroundColor : element.strokeColor,
          x: element.x,
          y: element.y,
          width: element.width,
          height: element.height,
        });
        marksByOwner.set(parsed.owner, existing);
        continue;
      }

      if (parsed.role === "cell") {
        const [row, col] = parsed.rest.map(Number);
        const table = cellsByTable.get(parsed.owner) ?? { rows: 0, cols: 0, cells: [] };
        table.cells.push({ row, col, text: bound.get(element.id) ?? "" });
        table.rows = Math.max(table.rows, row + 1);
        table.cols = Math.max(table.cols, col + 1);
        cellsByTable.set(parsed.owner, table);

        const box = tableBounds.get(parsed.owner);
        tableBounds.set(parsed.owner, {
          x: Math.min(box?.x ?? element.x, element.x),
          y: Math.min(box?.y ?? element.y, element.y),
          right: Math.max(box?.right ?? 0, element.x + element.width),
          bottom: Math.max(box?.bottom ?? 0, element.y + element.height),
        });
        continue;
      }

      if (parsed.role === "heading" || parsed.role === "paragraph") {
        if (element.type !== "text") continue;
        items.push({
          ...base,
          kind: parsed.role,
          text: element.text.trim(),
          font_size: element.fontSize,
        });
        continue;
      }

      if (parsed.role === "placeholder") {
        // An empty placeholder is not content. If the user typed into it, it
        // has become a real paragraph and exports as one.
        const typed = bound.get(element.id);
        if (typed) items.push({ ...base, kind: "paragraph", text: typed });
        continue;
      }

      if (parsed.role === "figure") {
        items.push({ ...base, kind: "figure", text: bound.get(element.id) || null });
        continue;
      }
    }

    // ---- things the user drew themselves --------------------------------
    if (element.type === "text") {
      if (element.containerId) continue; // belongs to its container
      items.push({ ...base, kind: "paragraph", text: element.text.trim(), font_size: element.fontSize });
    } else if (element.type === "arrow" || element.type === "line" || element.type === "freedraw") {
      items.push({
        ...base,
        kind: element.type === "arrow" ? "arrow" : "line",
        points: (element.points as readonly (readonly [number, number])[]).map(
          ([x, y]) => [x, y] as [number, number],
        ),
      });
    } else if (
      element.type === "rectangle" ||
      element.type === "ellipse" ||
      element.type === "diamond"
    ) {
      items.push({
        ...base,
        kind: "figure",
        text: bound.get(element.id) || null,
        background: element.backgroundColor,
      });
    }
  }

  for (const [owner, table] of cellsByTable) {
    const box = tableBounds.get(owner);
    if (!box) continue;
    items.push({
      id: `${ID_PREFIX}:table:${owner}`,
      kind: "table",
      x: box.x,
      y: box.y,
      width: box.right - box.x,
      height: box.bottom - box.y,
      reading_order: 0,
      table: { rows: table.rows, cols: table.cols, cells: table.cells },
    });
  }

  // Attach marks to the item they belong to, by the owner encoded in their id.
  for (const item of items) {
    const parsed = parseId(item.id);
    const marks = parsed ? marksByOwner.get(parsed.owner) : undefined;
    if (marks) item.marks = marks;
  }

  // Reading order is top-to-bottom, left-to-right over the *current* positions,
  // so moving a paragraph up the page moves it up the exported document too.
  const ordered = [...items].sort((a, b) => a.y - b.y || a.x - b.x);
  ordered.forEach((item, index) => {
    item.reading_order = index;
  });

  return { page_width: page.width, page_height: page.height, title: title ?? null, items: ordered };
}
