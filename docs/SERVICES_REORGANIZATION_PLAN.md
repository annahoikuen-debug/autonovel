# services 再編計画 (SERVICES_REORGANIZATION_PLAN.md)

> **目的**: `src/services/` の「何でも屋」状態（43,000行・279ファイル・27サブパッケージ＋89ルートファイル）を解消し、
> 責務ごとに3つのパッケージに分割する。

---

## 現状

| カテゴリ | 項目数 |
|----------|--------|
| サブパッケージ | 27個 |
| ルート .py ファイル | 89個 |
| 総行数 | 約43,000行 |

---

## 分類と移動先

### 生成系 → `src/engine/` (12サブパッケージ)

| サブパッケージ | 責務 |
|---------------|------|
| `anti_ai` | AI検出回避・人間味付与 |
| `cadence` | リズム・ cadence 制御 |
| `character` | キャラクター生成・管理 |
| `compression` | トークン圧縮・文脈圧縮 |
| `context_compression` | 文脈圧縮 |
| `foreshadowing` | 伏線管理 |
| `narrative` | ナラティブ構造 |
| `nlp` | 自然言語処理 |
| `prose` | 文章生成・推敲 |
| `graph` | 知識グラフ |
| `auditors` | オーディター（品質チェック） |
| `audit` | 監査ログ |

### 出版系 → `src/publishing/` (7サブパッケージ)

| サブパッケージ | 責務 |
|---------------|------|
| `ebook` | EPUB/PDF 出力 |
| `exporters` | 各種エクスポート |
| `formatters` | 文体整形 |
| `publishers` | 各プラットフォーム向け出力 |
| `publishing` | 出版ワークフロー |
| `illustration` | 挿絵生成・管理 |
| `manga` | マンガ組版 |

### 外部連携系 → `src/integrations/` (8サブパッケージ)

| サブパッケージ | 責務 |
|---------------|------|
| `billing` | 課金・決済 |
| `marketing` | マーケティング・CTR |
| `cost_guard` | コスト監視・ガード |
| `observability` | 可視化・メトリクス |
| `prefetch` | プリフェッチ |
| `rag` | RAG（検索拡張生成） |
| `vector_store` | ベクトルストア |
| `audio` | 音声処理 |

### shim のみ（`src/services/` に維持）

| サブパッケージ | 理由 |
|---------------|------|
| `llm` | Step 10 で `src/llm/adapters/` への shim 化済み |

---

## 移動マッピング詳細

| Step | 移動元 | 移動先 | シム |
|------|--------|--------|------|
| 33 | 分類計画文書作成 | `docs/SERVICES_REORGANIZATION_PLAN.md` | — |
| 34 | `src/services/{anti_ai,cadence,...}/` | `src/engine/{anti_ai,cadence,...}/` | `src/services/{anti_ai,cadence,...}/__init__.py` |
| 35 | `src/services/{ebook,exporters,...}/` | `src/publishing/{ebook,exporters,...}/` | `src/services/{ebook,exporters,...}/__init__.py` |
| 36 | `src/services/{billing,marketing,...}/` | `src/integrations/{billing,marketing,...}/` | `src/services/{billing,marketing,...}/__init__.py` |

---

## 進捗チェックリスト

| Step | 内容 | ステータス |
|------|------|-----------|
| 33 | `src/services/` の分類と移動計画確定（本ファイル） | ✅ 完了 |
| 34 | 生成系サブパッケージ → `src/engine/` | 未着手 |
| 35 | 出版系サブパッケージ → `src/publishing/` | 未着手 |
| 36 | 外部連携系サブパッケージ → `src/integrations/` + 総合リグレッションテスト | 未着手 |
