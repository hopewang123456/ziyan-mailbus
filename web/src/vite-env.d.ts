/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_API_MODE?: "real" | "mock";
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
