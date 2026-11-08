# AutoNovel アーキテクチャ設計

AutoNovel のシステムアーキテクチャを解説します。4層アーキテクチャ（domain / application / infrastructure / interfaces）に基づき、関心の分離と依存性の方向性を明確にしています。

> 📘 **関連ドキュメント**  
> - [4層圧縮モジュール](compression_module.md) — FourLayerCompressor の構造・DI・設定（中核機能の詳細）  
> - [開発者ガイド](development_guide.md) — 開発環境構築・コーディング規約  
> - [APIリファレンス](api.md) — バックエンドREST API  
> - [現況ステータス（SSOT）](STATUS.md) — 実装状況の唯一の正

---

## 1. 全体構成

AutoNovel は、ブラウザ（React 18 + TypeScript）から FastAPI バックエンドへREST/WebSocketで接続し、Hueyタスクキュー経由でAI生成ワークフローを非同期実行する構成です。

```
┌─────────────┐      REST / SSE / WebSocket      ┌──────────────────┐
│  ブラウザ    │ ◄───────────────────────────────► │  FastAPI (8200)   │
│  React 18   │                                   │  API ルーター群   │
└─────────────┘                                   │  JWT / RBAC /      │
        ▲                                         │  レートリミット    │
        │ REST / SSE                              └────────┬─────────┘
        │                                                 │ enqueue
┌─────────────┐                             ┌────────────▼────────────┐
│  Huey Task  │ ◄─────────────────────────► │  AutoWorkflowPipeline   │
│  キュー      │  (Redisバックエンド)        │  二段階プロット展開       │
│  (ワーカー)  │                             │  4層圧縮 + Reflective RAG│
└─────────────┘                             │  二層ハイブリッド監査   │
        ▲                                   │  Blind Peer Review        │
        │                                   └────────────┬─────────────┘
        │  永続化                                         │
┌─────────────┐                             ┌────────────▼─────────────┐
│  PostgreSQL │ ◄─────────────────────────► │  永続化レイヤー           │
│  16 / SQLite│                             │  本文・挿絵・音声ストレージ │
│  ChromaDB   │                             │  ChromaDB / pgvector      │
└─────────────┘                             └───────────────────────────┘
        ▲
        │ 外部プロバイダ
┌─────────────┐
│ OpenAI /    │
│ Gemini /    │
│ Claude /    │
│ Ollama / vLLM│
│ DALL·E 3 /  │
│ SD WebUI    │
│ ElevenLabs  │
└─────────────┘
```

---

## 2. 4層アーキテクチャ

ソースコードは `src/` 配下を以下の4層に分割しています。

| 層 | ディレクトリ | 役割 | 依存方向 |
|---|---|---|---|
| **domain** | `src/domain/` | ビジネスルール・エンティティ・ドメインサービス。最も内側。他の層に依存しない | なし（最内側） |
| **application** | `src/application/` | ユースケース・DTO・アプリケーションサービス。domainを利用 | domain → |
| **infrastructure** | `src/infrastructure/` | DBリポジトリ・外部APIクライアント・ファイルストレージ。domain/applicationを利用 | domain, application → |
| **interfaces** | `src/interfaces/` | REST APIルーター・CLI・GraphQL・画像プロバイダ。infrastructure/applicationを利用 | domain, application, infrastructure → |

### 依存性のルール

- 外側の層は内側の層に依存できるが、**内側の層が外側の層に依存してはならない**
- `src/domain/` は他の任意の層に依存しない（純粋なビジネスロジック）
- DI（依存性注入）コンテナにより、インターフェースと実装を結合

---

## 3. 主要コンポーネント

### 3.1 AutoWorkflowPipeline（コアパイプライン）

小説生成の中核ワークフロー。以下のステップから構成されます。

1. **二段階プロット展開** — 企画からプロット、エピソードへと段階的に展開
2. **4層圧縮 + Reflective RAG** — プロンプト・文脈・キャラクター情報を階層的に圧縮し、関連情報を検索
3. **二層ハイブリッド監査（UnifiedAuditor）** — 第1層 静的ルール解析（文長リズム・会話文比率・AI定型表現・クリフハンガー、0ms/0円）+ 第2層 単一LLM定性評価（フック・感情・キャラクター整合性・総合）。総合 = 定量40% + 定性60%、合格ライン 70.0
4. **Blind Peer Review（盲検読）** — 3案企画ガチャなどで、他案の出力を伏せた状態で独立に採点

### 3.2 二層ハイブリッド監査（UnifiedAuditor）

`src/agents/specialists/unified_auditor.py` に実装。v5.0 で 8 名並列オーディター呼び出しを廃止し、LLM コストとレイテンシを大幅に削減しました。

| 層 | 内容 | コスト・速度 |
|---|---|---|
| **第1層：静的ルール解析** | 文長リズム・会話文比率・AI定型表現検出・クリフハンガー評価をルールベースで判定 | 0ms / 0円 |
| **第2層：LLM定性評価** | 単一LLM によるフック・感情・キャラクター整合性・総合採点（3000字まで） | LLM 1 回呼び出し |

- **総合得点** = 定量スコア 40% + 定性スコア 60%
- **合格ライン** = 70.0 点以上、かつ AI 定型表現検出数 3 未満
- **Fail-closed** = LLM 未設定または呼び出し失敗時は不合格（品質が担保されない原稿は先に進めない）
- **監査不合格時** = 最低得点項目にフォーカスした「再生成指示（Actionable Diffs）」とともに執筆ステップへ戻され、局所的な改稿が行われます

8 専門オーディタークラス（一貫性・創造性・読者フック・感情曲線・文体・事実性・構造・マルチメディア）は後方互換のため `src/agents/specialists/` に維持されていますが、実際の監査実行は UnifiedAuditor の二層ハイブリッドに一本化されています。

### 3.3 認証・課金

- **認証**: JWT / RBAC。開発環境でもJWT必須（`/api/billing/plans` のみ認証不要）
- **課金**: Stripe Checkout + Webhook。4プラン（free/starter/pro/enterprise）と月次クレジット制。`src/config/billing_plans.py` がSSOT

---

## 4. データフロー

```
ユーザー入力
    │
    ▼
FastAPI APIルーター（認証・バリデーション）
    │
    ▼
Application ユースケース（執筆・エクスポート・課金等）
    │
    ▼
Domain エンティティ・ドメインサービス
    │
    ▼
Infrastructure リポジトリ / 外部API（LLM・画像生成・音声合成）
    │
    ▼
Hueyタスクキュー → ワーカー → AutoWorkflowPipeline
    │
    ▼
PostgreSQL / ChromaDB / ストレージへ永続化
    │
    ▼
結果をクライアントへREST/SSEで返却
```

---

## 5. 設定・環境変数

重要な環境変数は [`.env.example`](.env.example) を参照してください。デフォルト値は `src/backend/config.py` / `config/settings.py` で定義されています。

| 環境変数 | 説明 | 既定値 |
|---|---|---|
| `DATABASE_URL` | DB接続URL | SQLite |
| `APP_ENV` | `development` / `testing` / `production` | `development` |
| `HOST` / `PORT` | 待ち受けアドレスとポート | `0.0.0.0` / `8200` |
| `LLM_PROVIDER` | 推論エンジン（mock / openai / gemini / claude / ollama / vllm） | `mock` |
| `IMAGE_PROVIDER` | 画像生成（mock / dalle3 / sd_webui / comfyui） | `mock` |
| `TTS_PROVIDER` | 音声合成（mock / elevenlabs） | `mock` |
| `ENABLE_NSFW` | 官能コンテンツ生成の明示オプトイン | `false` |
| `VITE_SITE_URL` | フロントエンド本番オリジン（canonical/OGP用） | 未設定時は相対パス |
| `VITE_API_BASE_URL` | APIベースURL | `http://localhost:8200` |

---

## 6. テスト

| テスト種別 | 実行コマンド | 対象 |
|---|---|---|
| 単体テスト | `make test-unit` | バックエンドドメイン・アプリケーション層 |
| 統合テスト | `make test-integration` | PG+Redis必須 |
| 契約テスト | `make test-contract` | OpenAPIスナップショット・Pydanticスキーマ |
| フロントエンド単体 | `cd frontend && npx vitest run` | Reactコンポーネント |
| フロントエンドE2E | `cd frontend && npx playwright test` | ブラウザE2E（LP含む） |

---

## 7. 更新履歴

| バージョン | 日付 | 変更内容 |
|---|---|---|
| 1.0 | 2026-11-04 | 4層アーキテクチャ設計文書として初版作成（`compression_module.md` から圧縮モジュール詳細を分離） |
