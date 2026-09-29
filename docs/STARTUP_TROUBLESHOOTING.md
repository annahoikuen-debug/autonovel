# 起動とトラブルシューティング

AutoNovel ローカルの起動手順・起動できないときの対処・起動が遅いときの対処をまとめた文書。

> 現在の実装状況の SSOT は [STATUS.md](STATUS.md) を参照してください。

---

## 1. 起動方法

| 方法 | 手順 | 向いている場面 |
|---|---|---|
| **ローカル（推奨）** | `アプリ起動_ローカル.bat` をダブルクリック | SQLite + ローカルファイル。依存极少で最快 |
| Docker | `アプリ起動.bat` をダブルクリック | PostgreSQL / Redis / ChromaDB が必要なとき |
| 停止 | `アプリ停止.bat` | 両方ともこれ |

ローカル起動では次の 3 つが同時に立ち上がります。

| サービス | ポート | プロセス | ログ |
|---|---|---|---|
| Backend (FastAPI) | 8200 | `uvicorn src.backend.server:app` | `logs/backend.log` / `logs/backend.err.log` |
| Worker (Huey) | – | `huey.bin.huey_consumer src.backend.tasks.huey.huey` | `logs/worker.log` / `logs/worker.err.log` |
| Frontend (Vite) | 5173 | `npm run dev` | `logs/frontend.log` / `logs/frontend.err.log` |

起動が完了するとブラウザが自動で `http://localhost:5173` を開きます。

---

## 2. 起動できないときはまずこれ

**`起動診断.bat` をダブルクリックしてください。**
（= `powershell -ExecutionPolicy Bypass -File scripts/doctor.ps1`）

10 項目を自動チェックし、原因と修正コマンドを表示します。

```
1. Project layout   … 必須ファイルの有無
2. Toolchain        … python / node / npm
3. Python candidates… どの Python が実際にバックエンドを起動できるか
4. Configuration    … .env のキー、API キーのプレースホルダ、typing されるキー
5. Database         … SQLite / alembic head revision
6. Ports            … 8200 / 5173 の使用中、残留プロセス
7. Machine          … 空きメモリ / ディスク / ストレージ種別 / .pyc キャッシュ
8. Frontend         … vite.config.ts と node_modules
9. Startup smoke    … src.backend.server の import が通るか・どれだけの時間か
10. Heavy SDK 分析 … -Deep 時のみ
```

---

## 3. よくある症状と対処

### 3.1 3 つのサービスが全部即死する（何も言われずに終わる）

**以前の起動スクリプトはエラーをどこにも出さなかったため、この症状のときは
手がかりがありませんでした。現在の `start_local.ps1` は失敗したサービスの
ログ末尾を自動表示します。**

`logs/*.err.log` を確認してください。

### 3.2 `ModuleNotFoundError: No module named 'fastapi'`

起動に使う Python にバックエンドの依存が入っていません。

```powershell
py -m pip install -e ".[dev]"
```

`.venv` を使っている場合は `.venv` 側に入れてください。

```powershell
.venv\Scripts\python.exe -m pip install -e ".[dev]"
```

> `start_local.ps1` は「実際に import できるか」を判定して Python を選びます。
> ディレクトリがあるだけの空の `.venv` を優先してしまう事故を防ぐためです。
> 壊れた `.venv` は `アプリ起動_ローカル.bat -RecreateVenv` で作り直せます。

### 3.3 `'vite' が内部または外部コマンドとして認識されていません`

`frontend/node_modules` が存在しても `node_modules/.bin/vite.cmd` が無いと発生します。
`npm install` が中断された状態（Ctrl+C、電源断、USB HDD の unplug など）です。

```powershell
cd frontend
npm install
```

> `start_local.ps1` は `node_modules` が存在することだけでなく
> `node_modules\.bin\vite.cmd` まで確認し、欠けていれば自動で `npm install` します。

### 3.4 `MemoryError` と同時に uvicorn が落ちる

メモリ不足です。`起動診断.bat` のセクション 7 で空きメモリを確認してください。

- 他アプリ（ブラウザ、IDE）を閉じる
- ページファイルが「システム管理」 Off なら On にする
- 同時起動するプロセスを減らす（Huey ワーカーを止める: `-NoWorker`）

### 3.5 起動に 60 秒以上かかる

ほぼ確実に **I/O ボトルネック** です。

```powershell
python scripts\debug\import_mem_probe.py     # import 時間とモジュール数
```

AutoNovel のバックエンドは起動時に約 2,300 個の Python モジュールを読み込みます。
これを USB 外付け HDD（BusType=USB）から読むと数分かかります。

**対策の優先順位:**

1. **リポジトリを内蔵 SSD に移す**（効果が最大）
2. `.pyc` を最新化する: `python -m compileall -q src`
3. 重い SDK（chromadb / openai / google-genai）の遅延 import を保つ（下記参照）

### 3.6 ポート 8200 / 5173 が使用中

```powershell
powershell -ExecutionPolicy Bypass -File scripts\stop_local.ps1
```

`start_local.ps1` は起動前に自動でポートを解放しますが、
先に止めるほうがログが掴みやすくなります。

---

## 4. 起動速度 최적化（開発者向け）

### 遅延 import を保つ

`src.backend.server` の import は AppContainer → エージェント → LLM SDK という
大きな連鎖を通ります。API サーバーは起動時に LLM クライアントを 1 つも作らないため、
重い SDK は **トップレベルで import してはいけません**。

遅延 import を守っている場所:

| ファイル | 遅延化したもの |
|---|---|
| `src/agents/__init__.py` | 全エージェント（PEP 562 の `__getattr__`） |
| `src/core/llm/__init__.py` | 全プロバイダアダプタ |
| `src/core/llm_clients/gemini.py` | `google.genai` |
| `src/services/llm/*_adapter.py` | `openai` / `google.genai` |
| `src/services/vector_store/chroma.py` | `chromadb` / `rank_bm25` |
| `src/services/image_service.py` | `google.genai` |

**壊れたかの確認方法:**

```powershell
python scripts\debug\trace_heavy_imports.py
```

すべての重い SDK が `lazy` と表示される状態が正しい状態です。
`LOADED` が残っていたら、誰かが eager import を戻しています。

**元に戻すときの注意:**
`HAS_CHROMA` などは `importlib.util.find_spec` で「導入されているか」だけを判定し、
本体は初回利用時に読み込みます。テストが `chromadb` を `patch()` する経路を壊さないよう、
差し替え済みのグローバル変数を優先する実装になっています。新しく lazy 化するときは
この優先順位を維持してください。

### import 連鎖の可視化

```powershell
python -X importtime -c "import src.backend.server" 2> logs\importtime.txt
python scripts\debug\analyze_importtime.py logs\importtime.txt google.genai openai
```

---

## 5. PowerShell スクリプトを編集したとき

**`.ps1` は UTF-8 BOM 付きで保存してください。**

Windows PowerShell 5.1 は日本語システムでは BOM 无しの UTF-8 を Shift-JIS として読みます。
結果、日本語を含む文字列リテラルが壊れて、 inexplicable な
「変数に null が入る」「引用符が消える」エラーになります
（`Test-Path : パスが null であるために適用できません` 典型例）。

```powershell
# 状態確認（BOM が無いファイルを列挙）
python scripts\fix_ps1_encoding.py --check

# 付与
python scripts\fix_ps1_encoding.py
```

---

## 6. 関連ファイル

| ファイル | 役割 |
|---|---|
| `scripts/start_local.ps1` | ローカル起動（Windows） |
| `scripts/start_local.py` | ローカル起動（クロスプラットフォーム / Linux・macOS） |
| `scripts/stop_local.ps1` | 停止（PID ファイル → ポート → コマンドライン、の 3 段構え） |
| `scripts/doctor.ps1` | 起動診断 |
| `scripts/init_db.py` | SQLite の安全なマイグレーション |
| `scripts/debug/README.md` | 診断ツールの一覧 |
