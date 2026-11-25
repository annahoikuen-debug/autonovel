import { execSync } from "child_process";
import fs from "fs";
import path from "path";

console.log("🚀 [TypeSync] Exporting OpenAPI spec from Backend...");
// src.backend の依存(fastapi 等)が入った venv の python を使う。
// 素の `python` は PATH に無い環境(Windows の py ランチャ / Ubuntu 24.04+)で失敗する。
const repoPython = path.resolve("../.venv/bin/python");
const pythonCmd = fs.existsSync(repoPython) ? repoPython : "python3";
// export_openapi.py は CWD 相対で config/settings.toml を解決するため
// リポジトリルートで実行する必要がある(スクリプトパスは絶対化する)
const exportScript = path.resolve("../scripts/export_openapi.py");
execSync(`${pythonCmd} ${exportScript}`, {
  stdio: "inherit",
  cwd: path.resolve(".."),
});

const openapiPath = path.resolve("../docs/openapi.json");
const outputPath = path.resolve("./src/types/api.generated.ts");

if (!fs.existsSync(openapiPath)) {
  console.error("❌ openapi.json not found!");
  process.exit(1);
}

console.log("⚡ [TypeSync] Generating TypeScript definitions...");
execSync(`npx openapi-typescript ${openapiPath} -o ${outputPath}`, { stdio: "inherit" });

console.log(`✅ [TypeSync] Successfully generated: ${outputPath}`);
