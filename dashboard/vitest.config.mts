import path from "node:path";
import { defineConfig } from "vitest/config";

export default defineConfig({
  // tsconfigはNext.js用にjsx: preserveのため、テストではJSXを自動ランタイムで変換する
  oxc: { jsx: { runtime: "automatic" } },
  resolve: { alias: { "@": path.resolve(import.meta.dirname, "src") } },
  test: { css: { modules: { classNameStrategy: "non-scoped" } } },
});
