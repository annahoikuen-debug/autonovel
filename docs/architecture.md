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
└─────────────┘                             │  8専門オーディター       │
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
3. **8専門オーディター監査** — 矛盾・感情・続き・構成・事実性・スタイル・構造・マルチモダルの8視点で自動診断
4. **Blind Peer Review** — オーディター間の相互レビューによる品質保証

### 3.2 8専門オーディター

`src/agents/specialists/` に以下の8体のオーディターが実装されています。

| オーディター | 役割 |
|---|---|
| ConsistencyAuditor | 設定・プロットの矛盾チェック |
| CreativityAuditor | 創造性・独創性の評価 |
| ReaderHookAuditor | 読者の興味・引き込みの評価 |
| EmotionCurveAuditor | 感情曲線の起伏評価 |
| StyleAuditor | 文体の一貫性評価 |
| FactualAuditor | 事実関係の正確性評価 |
| StructureAuditor | 構成・ pacing の評価 |
| MultimodalAuditor | 画像・音声との整合性評価 |

なお、Anti-AIDetector（AI生成検出回避）はオーディターとは別枠のモジュールとして配置されています。

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
