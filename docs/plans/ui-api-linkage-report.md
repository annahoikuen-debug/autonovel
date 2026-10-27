# UI/UX と実機能の接続検証レポート

実行日: 2026-09-27
検証スクリプト: [`scripts/verify_ui_api_linkage.py`](../scripts/verify_ui_api_linkage.py)
検証範囲: フロントエンドの API 呼び出し **78 パス** vs バックエンドのルート定義 **229 ルート**

---

## 1. 結論

| 区分 | 判定 | 件数 |
|---|---|---|
| 主要導線（ウィザード / Studio / コスト / 編集） | 接続済み | **29 / 43** |
| 全体 | 接続済み | **50 / 78** |
| 未マッチ | 要確認 | 28 件 |

**今回追加した UI（3 入口・進捗表示・出口 CTA・3 グループタブ）はすべて実機能に接続済み**です。
一方、**既存機能の中に「UI はあるが叩くと 404 になる」ものが 14 件見つかりました**。

---

## 2. 今回追加した UI の接続確認（重要）

すべて実機能に接続されていることを確認しました。

| UI 要素 | 接続先 API | 判定 |
|---|---|---|
| ウィザード Step1（方針入力） | `POST /api/plots/expand-beats` | 接続済み |
| ウィザード Step2（構成確認） | `POST /api/plots/wizard-save` | 接続済み |
| ウィザード Step3（本文執筆） | `GET /api/stream/writing/{book_id}/{ep_num}` | 接続済み |
| ウィザード本文の表示 | SSE の `content` フィールドを state に蓄積 | 接続済み |
| ウィザードの Studio 引き継ぎ | `book_id` を保持 → `/studio/{book_id}` | 接続済み |
| ウィザード進捗インジケータ | SSE の `progress` / `phase` フィールド | 接続済み |
| ウィザードの「前のステップ」戻る | ローカル state（API 不要） | 接続済み |
| Studio タブ「矛盾診断」 | `POST /api/editor/audit` | 接続済み |
| Studio タブ「IF分岐ルート」 | `GET /api/branches/{book_id}/tree` | 接続済み |
| Studio タブ「マルチメディア」 | `GET /multimedia/artifacts/{id}/download` 等 | 接続済み |
| Studio コスト表示 | `GET /api/cost/budget/{book_id}` | 接続済み |
| EasyMode 品質スコア表示 | `GET /api/books/{book_id}/...` | 接続済み |
| Studio PDCA 監視（fold 化） | `GET /api/books/{book_id}/pdca/cycles/{n}` | 接続済み |
| EasyMode → Studio 昇格 | `POST /easy_mode/promote` | 接続済み |
| EasyMode 品質スコア監視 | `GET /easy_mode/status/{id}` 等 | 接続済み |
| `/welcome` 入口選択 | ルート遷移のみ（API 不要） | 接続済み |

### 進捗インジケータが表示される根拠

バックエンド [`stream_writing.py`](../../src/backend/routers/stream_writing.py) は
`ContextBuilding → Drafting → Auditing → Complete` の 4 フェーズで
`progress`（10 → 100）と `message` を SSE で送っており、UI 側の
`StreamingProgressBar` がそれをそのまま描画しています。

### Step3 本文が表示される根拠

同ファイル 176-185 行目の完了イベントで `content: chapter.content` が
送信されます。UI 側 [`Step3InteractiveWriting.tsx`](../../frontend/src/components/wizard/Step3InteractiveWriting.tsx) 65-75 行目は
`phase === "Complete"` のとき `content` を**全文として確定**して親に渡すため、
逐次的な差分配信ではない仕様でも、正しく本文が画面に入ります。

---

## 3. 検出された既存の問題（14 件が実在の不整合）

### 3.1 致命的：prefix の不一致で 404 になるもの

| フロントの呼び出し | 実際のバックエンド | 影響 |
|---|---|---|
| `/api/commercial/schedules` | `/commercial/schedules` | **「商用投稿」タブのスケジュール一覧が 404** |
| `/api/commercial/schedules/{id}` | `/commercial/schedules/{id}` | 詳細が 404 |
| `/api/commercial/schedules/{id}/run-now` | `/commercial/schedules/{id}/run-now` | **手動実行が 404** |
| `/api/illustrations/batch` | `/illustrations/batch` | 挿絵一括生成が 404 |
| `/api/publishing-assistant/format` | `/publishing-assistant/format` | 投稿アシスタントが 404 |

**原因**: バックエンドの [`commercial.py`](../../src/backend/routers/commercial.py:24) は
`prefix="/commercial"`、`illustrations.py` は `prefix` なし、`publishing_assistant.py` は
`prefix="/publishing-assistant"` ですが、フロントは `/api/` を付けています。

### 3.2 警告：バックエンドに対応 API が存在しないもの

UI にはボタンがありますが、バックエンドに実体がありません。

| フロントの呼び出し | 状態 | 影響 |
|---|---|---|
| `/api/ai/coach` | 未定義 | AI コーチ機能（押しても何も起きない） |
| `/api/collab/books/*/chapters/*/sync` | 未定義 | 共同執筆の本文同期が 404 |
| `/api/collab/books/*/chapters/*/presence` | 未定義 | 在席表示が 404 |
| `/api/novel/books/*/chapters/*/line-scores` | 未定義 | 行単位スコアが 404 |
| `/api/export/publish/{platform}` | 意図的に無効化 | 自動投稿（UI 側で縮退誘導が必要） |
| `/api/graph/nodes/{label}` | `/api/graph/nodes/{label}/{name}` のみ | 単一ノード取得が 404 |
| `/api/graph` | `/api/graph/nodes` 等 | クエリ付き呼び出しが不一致 |

**影響を受ける UI**: Studio の「📢 商用投稿」タブの投稿スケジュール機能、
共同執筆の表示。これらは「ボタンがあるのに押すとエラーになる」状態です。

### 3.3 誤検出だったもの（検出ロジックの不備で、実在の不整合ではない）

| フロント | 判定 | 備考 |
|---|---|---|
| `/multimedia/*`（3 件） | **接続済み** | `include_router(multimedia.router, prefix="/multimedia")` |
| `/api/books/*/pdca/cycles/*` | **接続済み** | |
| `/api/branches/*`（5 件） | **接続済み** | |
| `/api/editor/*`（5 件） | **接続済み** | |

スクリプト側の `include_router(prefix=...)` 検出を追加ことで解消済みです。

---

## 4. 推奨する修正（優先度順）

| 優先度 | 修正内容 | 対象ファイル |
|---|---|---|
| **高** | `BASE_URL` を `/commercial` に変更（`/api/` を落とす） | [`frontend/src/api/commercial.ts`](../../frontend/src/api/commercial.ts:13) |
| **高** | 挿絵一括生成の prefix を `/illustrations` に変更 | [`frontend/src/api/illustrations.ts`](../../frontend/src/api/illustrations.ts) |
| **高** | 投稿アシスタントの prefix を `/publishing-assistant` に変更 | [`frontend/src/api/publishingAssistant.ts`](../../frontend/src/api/publishingAssistant.ts) |
| **中** | 共同執筆の sync / presence に対応する API を実装するか、UI ボタンを無効化 | collab 系 |
| **中** | AI コーチ / 行スコアの API を実装するか、UI ボタンを削除 | 各所 |
| **中** | 商用投稿タブに「自動投稿は無効です。半自動投稿アシスタントをご利用ください」の注記を表示 | CommercialPublishPanel |
| 低 | 検証スクリプトを CI に組み込む | Makefile |

---

## 5. 検証方法の再現手順

```bash
# プロジェクトルートで実行
py -X utf8 scripts/verify_ui_api_linkage.py
```

スクリプトは以下を機械的に照合します。

1. フロントの `apiFetch(...)` / `fetch(...)` 呼び出しを静的評価で抽出
2. `${BASE_URL}/path` 形式のベースパス合成を**ファイルスコープ**で解決
3. バックエンドの `@router.get/post(...)` を抽出し、`APIRouter(prefix=...)` を適用
4. `include_router(mod, prefix=...)` の上書き_prefix を反映（server.py も走査）
5. 動的パラメータ（`${bookId}` / `{book_id}`）をワイルドカードに正規化して照合

> **注意**: この検証は**静的なパス照合**です。認証・レスポンス形式・
> 実際の 200 応答までは検証しません。実 LLM 接続での通し確認は別途必要です。
