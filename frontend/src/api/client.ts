import type { DocumentStructure, Health, LensResult } from "../types";

/** Empty by default: Vite proxies /api to the backend in dev (see vite.config.ts). */
const BASE = import.meta.env.VITE_API_BASE ?? "";

export class ApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

async function unwrap<T>(response: Response): Promise<T> {
  if (response.ok) return (await response.json()) as T;

  // FastAPI puts human-readable messages in `detail` — including the engine
  // errors ("PP-StructureV3 adapter is a Phase 2 task..."), which are worth
  // showing verbatim rather than replacing with a generic failure message.
  let detail = `Request failed (${response.status})`;
  try {
    const body = await response.json();
    if (typeof body?.detail === "string") detail = body.detail;
  } catch {
    /* response had no JSON body */
  }
  throw new ApiError(detail, response.status);
}

async function postImage<T>(path: string, file: File): Promise<T> {
  const form = new FormData();
  form.append("file", file);
  return unwrap<T>(await fetch(`${BASE}${path}`, { method: "POST", body: form }));
}

export const api = {
  health: async (): Promise<Health> => unwrap<Health>(await fetch(`${BASE}/api/health`)),
  lens: (file: File) => postImage<LensResult>("/api/lens", file),
  scan: (file: File) => postImage<DocumentStructure>("/api/scan", file),
};
