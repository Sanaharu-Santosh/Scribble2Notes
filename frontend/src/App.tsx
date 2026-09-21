import { useEffect, useState } from "react";

import { api } from "./api/client";
import { LensMode } from "./modes/LensMode";
import { ScanMode } from "./modes/ScanMode";
import type { Health } from "./types";

type Mode = "lens" | "scan";

export function App() {
  const [mode, setMode] = useState<Mode>("lens");
  const [health, setHealth] = useState<Health | null>(null);
  const [offline, setOffline] = useState(false);

  useEffect(() => {
    api
      .health()
      .then(setHealth)
      .catch(() => setOffline(true));
  }, []);

  return (
    <div className="app">
      <header className="app-header">
        <div className="brand">
          <span className="brand-mark">S</span>
          <div>
            <h1>Scribble2Notes</h1>
            <p>Handwritten pages in, usable text out.</p>
          </div>
        </div>

        <nav className="tabs" role="tablist">
          <button
            type="button"
            role="tab"
            aria-selected={mode === "lens"}
            className={mode === "lens" ? "is-active" : ""}
            onClick={() => setMode("lens")}
          >
            Lens
          </button>
          <button
            type="button"
            role="tab"
            aria-selected={mode === "scan"}
            className={mode === "scan" ? "is-active" : ""}
            onClick={() => setMode("scan")}
          >
            Scan &amp; Edit
          </button>
        </nav>
      </header>

      {offline && (
        <p className="banner banner-error">
          Can’t reach the API. Start it with <code>uvicorn app.main:app --reload</code> in{" "}
          <code>backend/</code>.
        </p>
      )}

      {health?.using_mocks && (
        <p className="banner banner-mock">
          Running on mock engines — the text below is generated, not read from your image. Set{" "}
          <code>OCR_ENGINE</code> / <code>LAYOUT_ENGINE</code> in <code>backend/.env</code> to use a
          real one.
        </p>
      )}

      <main>{mode === "lens" ? <LensMode /> : <ScanMode />}</main>

      <footer className="app-footer">
        Phase 0 scaffold · the seam is real, the engines are swappable, the output is mock until you
        add a key.
      </footer>
    </div>
  );
}
