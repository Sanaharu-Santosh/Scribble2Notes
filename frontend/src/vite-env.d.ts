/// <reference types="vite/client" />

interface ImportMetaEnv {
  /** Absolute API origin. Leave unset in dev — vite.config.ts proxies /api. */
  readonly VITE_API_BASE?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
