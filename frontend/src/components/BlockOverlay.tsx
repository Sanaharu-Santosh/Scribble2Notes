import type { Annotation, Block, BlockType } from "../types";

/**
 * Draws Mode 2's structural output over the page image.
 *
 * Read-only on purpose: Phase 2's job is to prove the structure contract is
 * right — correct types, correct places, tables as real grids — before Phase 3
 * swaps this overlay for the editable canvas. Getting the contract wrong is
 * cheap to fix now and expensive to fix once an editor is built on top of it.
 */

const TYPE_COLORS: Record<BlockType, string> = {
  heading: "#d63a2e",
  paragraph: "#2a5adb",
  list_item: "#c77b1a",
  table: "#177a64",
  figure: "#7c4dd1",
};

function AnnotationMark({ annotation, scale }: { annotation: Annotation; scale: number }) {
  const { bbox } = annotation.quad;
  const shared = {
    left: `${bbox.x * scale}px`,
    top: `${bbox.y * scale}px`,
    width: `${bbox.width * scale}px`,
    height: `${Math.max(bbox.height * scale, 2)}px`,
  };

  if (annotation.kind === "highlight") {
    return (
      <div
        className="annotation annotation-highlight"
        style={{ ...shared, background: annotation.color ?? "#ffe14d" }}
        title={`highlight — ${Math.round(annotation.confidence * 100)}%`}
      />
    );
  }

  if (annotation.kind === "underline") {
    return (
      <div
        className="annotation annotation-underline"
        style={{ ...shared, background: annotation.color ?? "#1a1a1a" }}
        title={`underline — ${Math.round(annotation.confidence * 100)}%`}
      />
    );
  }

  return (
    <div
      className="annotation annotation-box"
      style={{ ...shared, borderColor: annotation.color ?? "#1a1a1a" }}
      title={`box — ${Math.round(annotation.confidence * 100)}%`}
    />
  );
}

interface Props {
  blocks: Block[];
  scale: number;
  selectedId: string | null;
  onSelect: (id: string) => void;
}

export function BlockOverlay({ blocks, scale, selectedId, onSelect }: Props) {
  return (
    <div className="overlay">
      {blocks.map((block) => {
        const { bbox } = block.quad;
        const color = TYPE_COLORS[block.type];
        const isSelected = block.id === selectedId;

        return (
          <div key={block.id}>
            <button
              type="button"
              className={`block-region${isSelected ? " is-selected" : ""}`}
              onClick={() => onSelect(block.id)}
              style={{
                left: `${bbox.x * scale}px`,
                top: `${bbox.y * scale}px`,
                width: `${bbox.width * scale}px`,
                height: `${bbox.height * scale}px`,
                borderColor: color,
                background: isSelected ? `${color}22` : "transparent",
              }}
            >
              <span className="block-tag" style={{ background: color }}>
                {block.reading_order + 1} · {block.type}
              </span>
            </button>

            {block.table?.cells.map((cell) => (
              <div
                key={`${block.id}-${cell.row}-${cell.col}`}
                className="table-cell"
                style={{
                  left: `${cell.quad.bbox.x * scale}px`,
                  top: `${cell.quad.bbox.y * scale}px`,
                  width: `${cell.quad.bbox.width * scale}px`,
                  height: `${cell.quad.bbox.height * scale}px`,
                  borderColor: color,
                }}
                title={`r${cell.row} c${cell.col}: ${cell.text}`}
              />
            ))}

            {block.annotations.map((annotation, index) => (
              <AnnotationMark
                key={`${block.id}-annotation-${index}`}
                annotation={annotation}
                scale={scale}
              />
            ))}
          </div>
        );
      })}
    </div>
  );
}
