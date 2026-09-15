import { useEffect, useRef, useState } from "react";

import { api } from "../api/client";
import { BlockOverlay } from "../components/BlockOverlay";
import { ImagePicker } from "../components/ImagePicker";
import { useRenderedScale } from "../hooks";
import type { Block, DocumentStructure } from "../types";

function blockSummary(block: Block): string {
  if (block.type === "table" && block.table) {
    return `${block.table.rows} × ${block.table.cols} grid, ${block.table.cells.length} cells`;
  }
  if (block.type === "figure") return "figure region (cropped in Phase 5)";
  return block.text ?? "—";
}

export function ScanMode() {
  const [imageUrl, setImageUrl] = useState<string | null>(null);
  const [result, setResult] = useState<DocumentStructure | null>(null);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const imageRef = useRef<HTMLImageElement>(null);
  const scale = useRenderedScale(imageRef, result?.page_width);

  useEffect(() => {
    if (!imageUrl) return;
    return () => URL.revokeObjectURL(imageUrl);
  }, [imageUrl]);

  async function handlePick(picked: File) {
    setImageUrl(URL.createObjectURL(picked));
    setBusy(true);
    setError(null);
    setResult(null);
    setSelectedId(null);
    try {
      setResult(await api.scan(picked));
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : String(caught));
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="mode">
      <header className="mode-header">
        <div>
          <h2>Scan &amp; Edit</h2>
          <p>
            The page is broken into typed blocks — paragraphs, tables with real cells, figures,
            underlines and highlights. Phase 3 turns these into editable canvas objects; for now
            they are drawn so you can check the structure is right.
          </p>
        </div>
      </header>

      {!imageUrl && (
        <ImagePicker
          onPick={handlePick}
          busy={busy}
          hint="Use a full page — the more structure it has (tables, boxes, headings), the more there is to find."
        />
      )}

      {error && <p className="error-banner">{error}</p>}
      {busy && <p className="status">Analyzing the page…</p>}

      {imageUrl && (
        <div className="scan-layout">
          <div className="stage">
            <img ref={imageRef} src={imageUrl} alt="Scanned page" />
            {result && scale > 0 && (
              <BlockOverlay
                blocks={result.blocks}
                scale={scale}
                selectedId={selectedId}
                onSelect={(id) => setSelectedId((current) => (current === id ? null : id))}
              />
            )}
          </div>

          {result && (
            <aside className="block-list">
              <h3>Blocks in reading order</h3>
              <ol>
                {[...result.blocks]
                  .sort((a, b) => a.reading_order - b.reading_order)
                  .map((block) => (
                    <li key={block.id}>
                      <button
                        type="button"
                        className={`block-entry${block.id === selectedId ? " is-selected" : ""}`}
                        onClick={() =>
                          setSelectedId((current) => (current === block.id ? null : block.id))
                        }
                      >
                        <span className="block-entry-type">{block.type}</span>
                        <span className="block-entry-text">{blockSummary(block)}</span>
                        {block.annotations.length > 0 && (
                          <span className="block-entry-annotations">
                            {block.annotations.map((annotation) => annotation.kind).join(", ")}
                          </span>
                        )}
                      </button>
                    </li>
                  ))}
              </ol>
              <p className="panel-footer">
                engine <b>{result.engine.name}</b>
                {result.engine.is_mock && <em className="mock-flag"> (mock)</em>} ·{" "}
                {result.engine.duration_ms} ms
              </p>
              <button type="button" className="ghost" onClick={() => setImageUrl(null)}>
                Try another page
              </button>
            </aside>
          )}
        </div>
      )}
    </section>
  );
}
