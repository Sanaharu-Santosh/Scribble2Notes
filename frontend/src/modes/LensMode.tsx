import { useEffect, useRef, useState } from "react";

import { api } from "../api/client";
import { ImagePicker } from "../components/ImagePicker";
import { TextOverlay } from "../components/TextOverlay";
import { useRenderedScale } from "../hooks";
import type { LensResult } from "../types";

export function LensMode() {
  const [file, setFile] = useState<File | null>(null);
  const [imageUrl, setImageUrl] = useState<string | null>(null);
  const [result, setResult] = useState<LensResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [showBoxes, setShowBoxes] = useState(false);
  const [copied, setCopied] = useState(false);

  const imageRef = useRef<HTMLImageElement>(null);
  const scale = useRenderedScale(imageRef, result?.image_width);

  useEffect(() => {
    if (!imageUrl) return;
    return () => URL.revokeObjectURL(imageUrl);
  }, [imageUrl]);

  async function run(picked: File) {
    setBusy(true);
    setError(null);
    setResult(null);
    setCopied(false);
    try {
      setResult(await api.lens(picked));
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : String(caught));
    } finally {
      setBusy(false);
    }
  }

  function handlePick(picked: File) {
    setFile(picked);
    setImageUrl(URL.createObjectURL(picked));
    void run(picked);
  }

  async function copyAll() {
    if (!result) return;
    await navigator.clipboard.writeText(result.full_text);
    setCopied(true);
    window.setTimeout(() => setCopied(false), 1600);
  }

  return (
    <section className="mode">
      <header className="mode-header">
        <div>
          <h2>Lens</h2>
          <p>
            Text is detected in place and laid over the photo as a real, selectable text layer —
            drag across the writing to select it, then copy as usual.
          </p>
        </div>
        {result && (
          <div className="toolbar">
            <label className="toggle">
              <input
                type="checkbox"
                checked={showBoxes}
                onChange={(event) => setShowBoxes(event.target.checked)}
              />
              Show detected boxes
            </label>
            <button type="button" onClick={copyAll}>
              {copied ? "Copied" : "Copy all text"}
            </button>
            {file && (
              <button type="button" className="ghost" onClick={() => void run(file)} disabled={busy}>
                Run again
              </button>
            )}
          </div>
        )}
      </header>

      {!imageUrl && (
        <ImagePicker
          onPick={handlePick}
          busy={busy}
          hint="Point it at a page of notes, a whiteboard, a textbook — anything with text on it."
        />
      )}

      {error && <p className="error-banner">{error}</p>}
      {busy && <p className="status">Reading the page…</p>}

      {imageUrl && (
        <>
          <div className="stage">
            <img ref={imageRef} src={imageUrl} alt="Uploaded page" />
            {result && scale > 0 && (
              <TextOverlay regions={result.regions} scale={scale} showBoxes={showBoxes} />
            )}
          </div>

          {result && (
            <div className="result-bar">
              <span>
                <b>{result.regions.length}</b> regions
              </span>
              <span>
                engine <b>{result.engine.name}</b>
                {result.engine.is_mock && <em className="mock-flag"> (mock)</em>}
              </span>
              <span>{result.engine.duration_ms} ms</span>
              <button type="button" className="ghost" onClick={() => setImageUrl(null)}>
                Try another image
              </button>
            </div>
          )}
        </>
      )}
    </section>
  );
}
