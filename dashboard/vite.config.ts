import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

// The build is written into the Python package, so `pip install` plus
// `apix serve` gives a working dashboard on a machine with no Node at all.
// CI rebuilds it and fails if the committed output differs from the source.
export default defineConfig({
  plugins: [react()],
  base: "/",
  build: {
    outDir: "../src/apix/api/dashboard",
    emptyOutDir: true,
    sourcemap: false,
    // Never inline assets as data: URIs; the CSP allows images from 'self' only.
    assetsInlineLimit: 0,
  },
  server: {
    // `npm run dev` talks to a locally running `apix serve`.
    proxy: { "/v1": "http://127.0.0.1:8600" },
  },
  test: {
    environment: "jsdom",
  },
});
