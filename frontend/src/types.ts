/**
 * Mirrors the Pydantic schemas in backend/app/schemas/.
 *
 * Hand-written for now. When the contract starts changing often (Phase 2), swap
 * this file for types generated from the API's OpenAPI document — e.g.
 * `npx openapi-typescript http://localhost:8000/openapi.json` — so the two sides
 * cannot drift apart silently.
 */

export interface Point {
  x: number;
  y: number;
}

export interface BBox {
  x: number;
  y: number;
  width: number;
  height: number;
}

export interface Quad {
  /** Four corners, clockwise from top-left, in source-image pixels. */
  points: Point[];
  bbox: BBox;
  /** Rotation of the top edge, degrees clockwise from horizontal. */
  angle_deg: number;
  /** Top edge to bottom edge — the text height, not the bounding box height. */
  height: number;
}

export type RegionLevel = "word" | "line" | "paragraph";

export interface TextRegion {
  id: string;
  text: string;
  quad: Quad;
  confidence: number;
  level: RegionLevel;
}

export interface EngineInfo {
  name: string;
  duration_ms: number;
  is_mock: boolean;
}

export interface LensResult {
  image_width: number;
  image_height: number;
  regions: TextRegion[];
  full_text: string;
  engine: EngineInfo;
}

export type BlockType = "paragraph" | "heading" | "list_item" | "table" | "figure";

export interface TableCell {
  row: number;
  col: number;
  row_span: number;
  col_span: number;
  text: string;
  quad: Quad;
}

export interface Table {
  rows: number;
  cols: number;
  cells: TableCell[];
}

export interface Annotation {
  kind: "underline" | "highlight" | "box";
  quad: Quad;
  color: string | null;
  confidence: number;
}

export interface Block {
  id: string;
  type: BlockType;
  quad: Quad;
  reading_order: number;
  text: string | null;
  /** Lines of text in the block — the canvas sizes its font from this. */
  line_count: number | null;
  table: Table | null;
  figure_ref: string | null;
  annotations: Annotation[];
}

export interface DocumentStructure {
  page_width: number;
  page_height: number;
  blocks: Block[];
  engine: EngineInfo;
}

export interface Health {
  status: string;
  environment: string;
  ocr_engine: string;
  layout_engine: string;
  using_mocks: boolean;
}
