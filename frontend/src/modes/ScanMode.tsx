import { Excalidraw } from "@excalidraw/excalidraw";
import type { ExcalidrawImperativeAPI } from "@excalidraw/excalidraw/types";
import { useCallback, useEffect, useState } from "react";

import "@excalidraw/excalidraw/index.css";

import { api } from "../api/client";
import { ImagePicker } from "../components/ImagePicker";
import { BACKGROUND_ELEMENT_ID, BACKGROUND_OPACITY, structureToScene } from "../canvas/toScene";
import type { DocumentStructure } from "../types";
import type { PageImage, Scene } from "../canvas/toScene";

function readPageImage(file: File): Promise<PageImage> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onerror = () => reject(new Error("Could not read that image"));
    reader.onload = () => {
      const dataURL = String(reader.result);
      const probe = new Image();
      probe.onload = () =>
        resolve({
          dataURL,
          mimeType: file.type || "image/png",
          width: probe.naturalWidth,
          height: probe.naturalHeight,
        });
      probe.onerror = () => reject(new Error("Could not decode that image"));
      probe.src = dataURL;
    };
    reader.readAsDataURL(file);
  });
}

function summarize(structure: DocumentStructure): string {
  const tables = structure.blocks.filter((block) => block.type === "table");
  const cells = tables.reduce((total, block) => total + (block.table?.cells.length ?? 0), 0);
  const marks = structure.blocks.reduce((total, block) => total + block.annotations.length, 0);

  const parts = [`${structure.blocks.length} blocks`];
  if (tables.length) parts.push(`${tables.length} table${tables.length > 1 ? "s" : ""} (${cells} cells)`);
  if (marks) parts.push(`${marks} annotation${marks > 1 ? "s" : ""}`);
  return parts.join(" · ");
}

export function ScanMode() {
  const [scene, setScene] = useState<Scene | null>(null);
  const [structure, setStructure] = useState<DocumentStructure | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [showScan, setShowScan] = useState(true);
  const [canvas, setCanvas] = useState<ExcalidrawImperativeAPI | null>(null);

  /*
   * Fit the whole page in view on open.
   *
   * Two traps here. `scrollToContent` in initialData centres the page but keeps
   * 100% zoom, so an A4 scan opens showing its top third — hence doing it
   * imperatively with `fitToViewport`, which is allowed to zoom *out*
   * (`fitToContent` caps at 100% and would not help). And the API becomes
   * available a frame before the scene is measurable, so asking immediately
   * fits against an empty scene and silently does nothing.
   */
  useEffect(() => {
    if (!canvas) return;
    let cancelled = false;

    const fit = () => {
      if (cancelled) return;
      const elements = canvas.getSceneElements();
      if (!elements.length) {
        requestAnimationFrame(fit);
        return;
      }
      canvas.scrollToContent(elements, {
        fitToViewport: true,
        viewportZoomFactor: 0.9,
        animate: false,
      });
    };

    requestAnimationFrame(fit);
    return () => {
      cancelled = true;
    };
  }, [canvas]);

  // The scan is a tracing guide, not content — toggling it changes only its
  // opacity, so hiding it leaves a clean digital page and showing it again
  // doesn't disturb anything the user has moved.
  useEffect(() => {
    if (!canvas) return;
    const next = canvas.getSceneElements().map((element) =>
      element.id === BACKGROUND_ELEMENT_ID
        ? { ...element, opacity: showScan ? BACKGROUND_OPACITY : 0 }
        : element,
    );
    canvas.updateScene({ elements: next });
  }, [canvas, showScan]);

  const handlePick = useCallback(async (picked: File) => {
    setBusy(true);
    setError(null);
    setScene(null);
    setStructure(null);
    try {
      const [page, result] = await Promise.all([readPageImage(picked), api.scan(picked)]);
      setStructure(result);
      setScene(structureToScene(result, page));
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : String(caught));
    } finally {
      setBusy(false);
    }
  }, []);

  function reset() {
    setScene(null);
    setStructure(null);
    setCanvas(null);
  }

  return (
    <section className="mode">
      <header className="mode-header">
        <div>
          <h2>Scan &amp; Edit</h2>
          <p>
            Every detected thing is now an object you can change: retype a paragraph, drag a table
            cell, draw an arrow, delete what you don&apos;t want. The scan sits underneath as a
            tracing guide — hide it and you have a clean digital page.
          </p>
        </div>

        {structure && (
          <div className="toolbar">
            <label className="toggle">
              <input
                type="checkbox"
                id="show-scan"
                checked={showScan}
                onChange={(event) => setShowScan(event.target.checked)}
              />
              Show the scan
            </label>
            <button type="button" className="ghost" onClick={reset}>
              Try another page
            </button>
          </div>
        )}
      </header>

      {!scene && (
        <ImagePicker
          onPick={handlePick}
          busy={busy}
          samplePath="/sample-structured.png"
          hint="Use a full page — the more structure it has (tables, boxes, headings), the more there is to find."
        />
      )}

      {error && <p className="error-banner">{error}</p>}
      {busy && <p className="status">Reading the page…</p>}

      {scene && structure && (
        <>
          <div className="canvas-frame">
            <Excalidraw
              excalidrawAPI={setCanvas}
              initialData={{
                elements: scene.elements,
                files: scene.files,
                appState: { viewBackgroundColor: "#ffffff" },
              }}
            />
          </div>

          <div className="result-bar">
            <span>{summarize(structure)}</span>
            <span>
              engine <b>{structure.engine.name}</b>
              {structure.engine.is_mock && <em className="mock-flag"> (mock)</em>}
            </span>
            <span>{structure.engine.duration_ms} ms</span>
          </div>
        </>
      )}
    </section>
  );
}
