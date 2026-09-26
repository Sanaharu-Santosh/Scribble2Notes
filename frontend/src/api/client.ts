import type {
  DocumentStructure,
  ExportDocument,
  Health,
  LensResult,
  PageDetail,
  PageSummary,
} from "../types";

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

async function postImage<T>(path: string, file: File, method = "POST"): Promise<T> {
  const form = new FormData();
  form.append("file", file);
  return unwrap<T>(await fetch(`${BASE}${path}`, { method, body: form }));
}

/** Pull the server's filename out of Content-Disposition, if it gave one. */
function filenameFrom(header: string | null, fallback: string): string {
  const match = header?.match(/filename="([^"]+)"/);
  return match?.[1] ?? fallback;
}

async function exportAs(
  format: "docx" | "pdf",
  document: ExportDocument,
): Promise<{ blob: Blob; filename: string }> {
  const response = await fetch(`${BASE}/api/export/${format}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(document),
  });

  if (!response.ok) {
    // Error responses are JSON even though success is a binary file.
    let detail = `Export failed (${response.status})`;
    try {
      const body = await response.json();
      if (typeof body?.detail === "string") detail = body.detail;
    } catch {
      /* no JSON body */
    }
    throw new ApiError(detail, response.status);
  }

  return {
    blob: await response.blob(),
    filename: filenameFrom(response.headers.get("Content-Disposition"), `notes.${format}`),
  };
}

async function json<T>(path: string, method: string, body?: unknown): Promise<T> {
  return unwrap<T>(
    await fetch(`${BASE}${path}`, {
      method,
      headers: body === undefined ? {} : { "Content-Type": "application/json" },
      body: body === undefined ? undefined : JSON.stringify(body),
    }),
  );
}

export const api = {
  health: async (): Promise<Health> => unwrap<Health>(await fetch(`${BASE}/api/health`)),
  lens: (file: File) => postImage<LensResult>("/api/lens", file),
  scan: (file: File) => postImage<DocumentStructure>("/api/scan", file),
  export: exportAs,

  pages: {
    list: () => json<PageSummary[]>("/api/pages", "GET"),
    read: (id: string) => json<PageDetail>(`/api/pages/${id}`, "GET"),
    create: (body: {
      title: string;
      page_width: number;
      page_height: number;
      scene: unknown[];
    }) => json<PageDetail>("/api/pages", "POST", body),
    update: (id: string, body: { title?: string; scene?: unknown[] }) =>
      json<PageDetail>(`/api/pages/${id}`, "PUT", body),
    remove: async (id: string): Promise<void> => {
      const response = await fetch(`${BASE}/api/pages/${id}`, { method: "DELETE" });
      if (!response.ok) throw new ApiError(`Could not delete (${response.status})`, response.status);
    },
    uploadScan: (id: string, file: File) =>
      postImage<PageSummary>(`/api/pages/${id}/scan`, file, "PUT"),
    scanUrl: (id: string) => `${BASE}/api/pages/${id}/scan`,
  },
};
