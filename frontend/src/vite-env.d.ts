declare const process: {
  env: {
    VITE_API_BASE_URL?: string;
  };
};

interface ImportMetaEnv {
  readonly VITE_API_BASE_URL?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
