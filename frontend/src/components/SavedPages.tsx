import { useCallback, useEffect, useState } from "react";

import { api } from "../api/client";
import type { PageSummary } from "../types";

function when(iso: string): string {
  const then = new Date(iso).getTime();
  const minutes = Math.round((Date.now() - then) / 60000);
  if (minutes < 1) return "just now";
  if (minutes < 60) return `${minutes} min ago`;
  if (minutes < 1440) return `${Math.round(minutes / 60)} h ago`;
  return new Date(iso).toLocaleDateString();
}

interface Props {
  onOpen: (id: string) => void;
  /** Bumped by the parent after a save, so the list refreshes. */
  refreshToken: number;
}

export function SavedPages({ onOpen, refreshToken }: Props) {
  const [pages, setPages] = useState<PageSummary[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(() => {
    api
      .pages.list()
      .then(setPages)
      .catch((caught) => setError(caught instanceof Error ? caught.message : String(caught)));
  }, []);

  useEffect(load, [load, refreshToken]);

  async function remove(id: string) {
    await api.pages.remove(id);
    load();
  }

  // Nothing saved yet is not worth a heading — it would just be an empty box
  // under the picker on a first visit.
  if (error) return <p className="error-banner">Saved pages unavailable: {error}</p>;
  if (!pages || pages.length === 0) return null;

  return (
    <section className="saved">
      <h3>Saved pages</h3>
      <ul>
        {pages.map((page) => (
          <li key={page.id}>
            <button type="button" className="saved-entry" onClick={() => onOpen(page.id)}>
              <span className="saved-title">{page.title}</span>
              <span className="saved-meta">
                {page.element_count} objects · {when(page.updated_at)}
                {page.has_scan ? " · scan kept" : ""}
              </span>
            </button>
            <button
              type="button"
              className="ghost saved-delete"
              aria-label={`Delete ${page.title}`}
              onClick={() => void remove(page.id)}
            >
              Delete
            </button>
          </li>
        ))}
      </ul>
    </section>
  );
}
