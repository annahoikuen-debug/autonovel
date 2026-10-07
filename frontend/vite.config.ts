import { defineConfig } from "vite";
import { configDefaults } from "vitest/config";
import react from "@vitejs/plugin-react";

const backendUrl = process.env.VITE_BACKEND_URL || process.env.BACKEND_URL || "http://localhost:8200";

export default defineConfig({
  plugins: [react()],
  resolve: {
     alias: {
       '@': '/src',
     },
   },
   server: {
    host: true,
    port: 5173,
    // proxy prefix は src/backend/server.py の include_router と 1:1 で対応させる。
    // 両方向の同期は tests/regression/test_H1_routing_drift.py が機械的に検査する
    // （PLAN_H1_SECURITY_HYGIENE_36STEPS H7）。
    // 過去にあった /books /plots /episodes ... は API が /api 配下へ移ったため削除済み。
    proxy: {
      "/api": { target: backendUrl, changeOrigin: true },
      "/admin": { target: backendUrl, changeOrigin: true },
      "/easy_mode": { target: backendUrl, changeOrigin: true },
      "/commercial": { target: backendUrl, changeOrigin: true },
      "/subtext": { target: backendUrl, changeOrigin: true },
      "/health": { target: backendUrl, changeOrigin: true },
      "/metrics": { target: backendUrl, changeOrigin: true },
      "/batch": { target: backendUrl, changeOrigin: true },
      "/generate": { target: backendUrl, changeOrigin: true },
      "/status": { target: backendUrl, changeOrigin: true },
      "/images": { target: backendUrl, changeOrigin: true },
      "/yonkoma": { target: backendUrl, changeOrigin: true },
      "/orchestrated": { target: backendUrl, changeOrigin: true },
      // 条件付きマウント: server.py は plugin_registry.is_enabled("multimedia") が
      // true のときだけ prefix="/multimedia" を include_router する。
      // プラグインを無効にした環境では 404 になるが、proxy 定義は残す。
      "/multimedia": { target: backendUrl, changeOrigin: true },
    },
  },
  preview: { host: true, port: 3000 },
  build: { 
    outDir: "dist",
    rollupOptions: {
      output: {
        manualChunks: {
          vendor: ["react", "react-dom", "react-router-dom"]
        }
      }
    },
    chunkSizeWarningLimit: 1000,
    minify: "esbuild",
  },
  esbuild: {
    drop: ["console", "debugger"],
  },
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: ["./tests/setup.ts"],
    exclude: [...configDefaults.exclude, "tests/e2e/**"],
    /*
     * テストランナーのメモリ設定（R10）。
     *
     * 以前は既定のワーカーで全テストを並行実行し、jsdom のメモリが
     * 1 プロセスに集中して heap 枯渇（OOM）で落ちていた。
     * `forks` に変更し、`isolate` を有効にしたまま並列数を絞る。
     */
    pool: "forks",
    poolOptions: {
      forks: {
        minForks: 1,
        maxForks: 4,
        isolate: true,
      },
    },
    coverage: {
      provider: "v8",
      reporter: ["text", "json", "html"],
      exclude: [
        "src/main.tsx",
        "src/types/**",
        "src/components/branches/**",
        "src/components/character/**",
        "src/components/admin/**",
        "src/components/billing/**",
        "src/components/graph/**",
        "src/components/illustrations/**",
        "src/components/marketing/**",
        "src/components/publishing/**",
        "src/components/showcase/**",
        "src/components/style/**",
        "src/api/hooks/**",
        "src/hooks/_unused/**",
        "src/lib/**",
        "src/models/**",
        "src/services/**",
      ],
      thresholds: {
        lines: 50,
        branches: 50,
        functions: 50,
        statements: 50,
      },
    },
  },
});

