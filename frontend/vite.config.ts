import { defineConfig, type Plugin } from "vite";
import react from "@vitejs/plugin-react";
import { copyFileSync, existsSync } from "node:fs";
import path from "node:path";

/** ketcher-core's ESM build still calls require("raphael"), which browsers reject. */
function ketcherRaphael(): Plugin {
  const requireRaphael = /require\(['"]raphael['"]\)/g;
  return {
    name: "ketcher-raphael",
    enforce: "pre",
    transform(code, id) {
      if (!id.includes("ketcher") || !requireRaphael.test(code)) return;
      requireRaphael.lastIndex = 0;
      const replaced = code.replace(requireRaphael, "__raphael");
      return {
        code: `import __raphael from "raphael";\n${replaced}`,
        map: null,
      };
    },
  };
}

/** Starlette StaticFiles(html=True) serves 404.html for unknown paths — use as SPA fallback. */
function spaFallback404(): Plugin {
  return {
    name: "spa-fallback-404",
    closeBundle() {
      const outDir = path.resolve(__dirname, "dist");
      const index = path.join(outDir, "index.html");
      const fallback = path.join(outDir, "404.html");
      if (existsSync(index)) copyFileSync(index, fallback);
    },
  };
}

export default defineConfig({
  plugins: [ketcherRaphael(), react(), spaFallback404()],
  define: {
    global: "globalThis",
  },
  optimizeDeps: {
    include: ["raphael", "ketcher-core", "ketcher-react", "ketcher-standalone", "3dmol"],
  },
  server: {
    port: 5173,
    proxy: {
      "/api": "http://127.0.0.1:8000",
    },
  },
  build: {
    outDir: "dist",
    emptyOutDir: true,
    commonjsOptions: {
      transformMixedEsModules: true,
    },
  },
});
