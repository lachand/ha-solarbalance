import { defineConfig } from "vite";

export default defineConfig({
  build: {
    lib: {
      entry: "src/solarbalance-card.ts",
      formats: ["es"],
      fileName: () => "solarbalance-card.js",
    },
    rollupOptions: {
      // Lit is bundled — HA does not expose it globally.
      external: [],
    },
    outDir: "../../custom_components/solarbalance/www",
    emptyOutDir: false,
    minify: true,
    sourcemap: false,
    target: "es2022",
  },
});
