import { type DragEvent, useRef, useState } from "react";

interface Props {
  onPick: (file: File) => void;
  busy: boolean;
  /** Shown inside the drop area so each mode can say what it will do. */
  hint: string;
  /**
   * Each mode demos a different page: Lens wants lines of writing, Scan wants
   * something with a table and a box on it.
   */
  samplePath?: string;
}

export function ImagePicker({ onPick, busy, hint, samplePath = "/sample-note.png" }: Props) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [dragging, setDragging] = useState(false);
  const [sampleError, setSampleError] = useState<string | null>(null);

  function handleDrop(event: DragEvent<HTMLDivElement>) {
    event.preventDefault();
    setDragging(false);
    const dropped = event.dataTransfer.files?.[0];
    if (dropped) onPick(dropped);
  }

  async function useSample() {
    setSampleError(null);
    try {
      const response = await fetch(samplePath);
      if (!response.ok) throw new Error(`Sample page missing (${response.status})`);
      const blob = await response.blob();
      const name = samplePath.split("/").pop() ?? "sample.png";
      onPick(new File([blob], name, { type: blob.type || "image/png" }));
    } catch (error) {
      setSampleError(error instanceof Error ? error.message : String(error));
    }
  }

  return (
    <div
      className={`picker${dragging ? " is-dragging" : ""}`}
      onDragOver={(event) => {
        event.preventDefault();
        setDragging(true);
      }}
      onDragLeave={() => setDragging(false)}
      onDrop={handleDrop}
    >
      <p className="picker-hint">{hint}</p>

      <div className="picker-actions">
        <button type="button" onClick={() => inputRef.current?.click()} disabled={busy}>
          Choose an image
        </button>
        <button type="button" className="ghost" onClick={useSample} disabled={busy}>
          Use the sample page
        </button>
      </div>

      <p className="picker-note">…or drop a photo anywhere in this box</p>
      {sampleError && <p className="error-text">{sampleError}</p>}

      <input
        ref={inputRef}
        type="file"
        accept="image/*"
        hidden
        onChange={(event) => {
          const picked = event.target.files?.[0];
          if (picked) onPick(picked);
          event.target.value = "";
        }}
      />
    </div>
  );
}
