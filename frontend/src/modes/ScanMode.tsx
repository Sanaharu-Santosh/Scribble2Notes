import { Excalidraw } from "@excalidraw/excalidraw";
import type { ExcalidrawElement } from "@excalidraw/excalidraw/element/types";
import type { ExcalidrawImperativeAPI } from "@excalidraw/excalidraw/types";
import { useCallback, useEffect, useState } from "react";

import "@excalidraw/excalidraw/index.css";

import { api } from "../api/client";
import { ImagePicker } from "../components/ImagePicker";
import { SavedPages } from "../components/SavedPages";
import { sceneToDocument } from "../canvas/fromScene";
import {
  BACKGROUND_ELEMENT_ID,
  BACKGROUND_FILE_ID,
  BACKGROUND_OPACITY,
  structureToScene,
} from "../canvas/toScene";
import type { DocumentStructure } from "../types";
import type { PageImage, Scene } from "../canvas/toScene";

function readAsDataURL(blob: Blob): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onerror = () => reject(new Error("Could not read that image"));
    reader.onload = () => resolve(String(reader.result));
    reader.readAsDataURL(blob);
  });
}

async function readPageImage(file: File): Promise<PageImage> {
  const dataURL = await readAsDataURL(file);
  const size = await new Promise<{ width: number; height: number }>((resolve, reject) => {
    const probe = new Image();
    probe.onload = () => resolve({ width: probe.naturalWidth, height: probe.naturalHeight });
    probe.onerror = () => reject(new Error("Could not decode that image"));
    probe.src = dataURL;
  });
  return { dataURL, mimeType: file.type || "image/png", ...size };
}

function summarize(structure: DocumentStructure): string {
  const tables = structure.blocks.filter((block) => block.type === "table");
  const cells = tables.reduce((total, block) => total + (block.table?.cells.length ?? 0), 0);
  const marks = structure.blocks.reduce((total, block) => total + block.annotations.length, 0);

  const parts = [`${structure.blocks.length} blocks`];
  if (tables.length) {
    parts.push(`${tables.length} table${tables.length > 1 ? "s" : ""} (${cells} cells)`);
  }
  if (marks) parts.push(`${marks} annotation${marks > 1 ? "s" : ""}`);
  return parts.join(" · ");
}

interface PageMeta {
  width: number;
  height: number;
}

export function ScanMode() {
  const [scene, setScene] = useState<Scene | null>(null);
  const [meta, setMeta] = useState<PageMeta | null>(null);
  const [detection, setDetection] = useState<DocumentStructure | null>(null);
  const [scanFile, setScanFile] = useState<File | null>(null);

  const [savedId, setSavedId] = useState<string | null>(null);
  const [title, setTitle] = useState("Untitled page");
  const [saving, setSaving] = useState(false);
  const [savedAt, setSavedAt] = useState<string | null>(null);
  const [refreshToken, setRefreshToken] = useState(0);

  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [showScan, setShowScan] = useState(true);
  const [exporting, setExporting] = useState<"docx" | "pdf" | null>(null);
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

  function reset() {
    setScene(null);
    setMeta(null);
    setDetection(null);
    setScanFile(null);
    setSavedId(null);
    setSavedAt(null);
    setTitle("Untitled page");
    setCanvas(null);
  }

  const handlePick = useCallback(async (picked: File) => {
    setBusy(true);
    setError(null);
    setScene(null);
    setDetection(null);
    setSavedId(null);
    setSavedAt(null);
    try {
      const [page, result] = await Promise.all([readPageImage(picked), api.scan(picked)]);
      setScanFile(picked);
      setMeta({ width: result.page_width, height: result.page_height });
      setDetection(result);
      setScene(structureToScene(result, page));
      setTitle(picked.name.replace(/\.[^.]+$/, "") || "Untitled page");
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : String(caught));
    } finally {
      setBusy(false);
    }
  }, []);

  const openSaved = useCallback(async (id: string) => {
    setBusy(true);
    setError(null);
    setDetection(null);
    try {
      const page = await api.pages.read(id);

      // The stored scene is already Excalidraw elements. Only the scan has to
      // be re-attached, because the bytes never went into the row.
      let files: Scene["files"] = {};
      if (page.has_scan) {
        const response = await fetch(api.pages.scanUrl(id));
        if (response.ok) {
          const blob = await response.blob();
          files = {
            [BACKGROUND_FILE_ID]: {
              id: BACKGROUND_FILE_ID as never,
              dataURL: (await readAsDataURL(blob)) as never,
              mimeType: (blob.type || "image/png") as never,
              created: Date.now(),
            },
          };
        }
      }

      setScene({ elements: page.scene as unknown as ExcalidrawElement[], files });
      setMeta({ width: page.page_width, height: page.page_height });
      setTitle(page.title);
      setSavedId(page.id);
      setScanFile(null);
      setSavedAt(page.updated_at);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : String(caught));
    } finally {
      setBusy(false);
    }
  }, []);

  async function save() {
    if (!canvas || !meta) return;
    setSaving(true);
    setError(null);
    try {
      const elements = canvas.getSceneElements();

      if (savedId) {
        const updated = await api.pages.update(savedId, { title, scene: [...elements] });
        setSavedAt(updated.updated_at);
      } else {
        const created = await api.pages.create({
          title,
          page_width: meta.width,
          page_height: meta.height,
          scene: [...elements],
        });
        setSavedId(created.id);
        setSavedAt(created.updated_at);

        // Uploaded separately, and only once: the scan never changes after the
        // first save, so later saves send only the scene.
        if (scanFile) await api.pages.uploadScan(created.id, scanFile);
      }
      setRefreshToken((token) => token + 1);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : String(caught));
    } finally {
      setSaving(false);
    }
  }

  async function exportAs(format: "docx" | "pdf") {
    if (!canvas || !meta) return;
    setExporting(format);
    setError(null);
    try {
      // Read the canvas, not the detection — by now the user has edited it.
      const model = sceneToDocument(canvas.getSceneElements(), meta, title);
      const { blob, filename } = await api.export(format, model);

      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = filename;
      link.click();
      URL.revokeObjectURL(url);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : String(caught));
    } finally {
      setExporting(null);
    }
  }

  return (
    <section className="mode">
      <header className="mode-header">
        <div>
          <h2>Scan &amp; Edit</h2>
          <p>
            Every detected thing is an object you can change: retype a paragraph, drag a table cell,
            draw an arrow, delete what you don&apos;t want. The scan sits underneath as a tracing
            guide — hide it and you have a clean digital page. Saving and exporting both read the
            canvas, so your edits come with them.
          </p>
        </div>

        {scene && (
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
            <button type="button" onClick={() => void save()} disabled={saving}>
              {saving ? "Saving…" : savedId ? "Save" : "Save page"}
            </button>
            <button type="button" onClick={() => void exportAs("docx")} disabled={!!exporting}>
              {exporting === "docx" ? "Building…" : "Export Word"}
            </button>
            <button type="button" onClick={() => void exportAs("pdf")} disabled={!!exporting}>
              {exporting === "pdf" ? "Building…" : "Export PDF"}
            </button>
            <button type="button" className="ghost" onClick={reset}>
              Close
            </button>
          </div>
        )}
      </header>

      {!scene && (
        <>
          <ImagePicker
            onPick={handlePick}
            busy={busy}
            samplePath="/sample-structured.png"
            hint="Use a full page — the more structure it has (tables, boxes, headings), the more there is to find."
          />
          <SavedPages onOpen={(id) => void openSaved(id)} refreshToken={refreshToken} />
        </>
      )}

      {error && <p className="error-banner">{error}</p>}
      {busy && <p className="status">Reading the page…</p>}

      {scene && meta && (
        <>
          <div className="page-title-row">
            <label htmlFor="page-title">Title</label>
            <input
              id="page-title"
              value={title}
              onChange={(event) => setTitle(event.target.value)}
              placeholder="Untitled page"
            />
            {savedAt && (
              <span className="saved-flag">Saved {new Date(savedAt).toLocaleTimeString()}</span>
            )}
          </div>

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

          {detection && (
            <div className="result-bar">
              <span>{summarize(detection)}</span>
              <span>
                engine <b>{detection.engine.name}</b>
                {detection.engine.is_mock && <em className="mock-flag"> (mock)</em>}
              </span>
              <span>{detection.engine.duration_ms} ms</span>
            </div>
          )}
        </>
      )}
    </section>
  );
}
