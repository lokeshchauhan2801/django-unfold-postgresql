import { resolve } from "node:path";
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";

export default defineConfig({
  plugins: [react(), tailwindcss()],
  base: "/static/chat/",
  build: {
    outDir: resolve(import.meta.dirname, "../static/chat"),
    emptyOutDir: true,
    rollupOptions: {
      input: resolve(import.meta.dirname, "index.html"),
      output: {
        entryFileNames: "chat.js",
        assetFileNames: "chat.[ext]",
      },
    },
  },
});
