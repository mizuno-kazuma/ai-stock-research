import { dirname } from "node:path";
import { fileURLToPath } from "node:url";
import { FlatCompat } from "@eslint/eslintrc";

const compat = new FlatCompat({
  baseDirectory: dirname(fileURLToPath(import.meta.url)),
});

const config = [
  ...compat.extends("next/core-web-vitals", "next/typescript"),
  {
    ignores: [".next/**", "node_modules/**", "public/sw.js"],
  },
  {
    rules: {
      // 表示ロジックは packages/ui のフォーマッタに寄せる方針なので、
      // any の混入をエラーとして止める。
      "@typescript-eslint/no-explicit-any": "error",
    },
  },
];

export default config;
