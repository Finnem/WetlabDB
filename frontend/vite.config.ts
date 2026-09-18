import { defineConfig, type Plugin } from "vite";
import react from "@vitejs/plugin-react";

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

export default defineConfig({
  plugins: [ketcherRaphael(), react()],
  define: {
    global: "globalThis",
  },
  optimizeDeps: {
    include: ["raphael", "ketcher-core", "ketcher-react", "ketcher-standalone"],
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
