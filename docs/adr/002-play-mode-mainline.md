# ADR 002: Play モード(生成小説の再生体験)を本線機能として採用

## ステータス

承認 (Accepted) — 2026-11-23。Phase 0 実装開始の指示により承認とし、Phase 0 を完了済み(`docs/implementation_plans/playable_novel_phase0.md` §7 実行記録参照)。Phase 1 の GO/NO-GO は Phase 0 の KPI ベースライン取得後。

## コンテキスト

AutoNovel は「条件を入れたら小説が届く」**生成→納品型**のツールであり、生成した本文を読者が再体験する手段を持たない。
一方、外部参照サービス ISEKAI ZERO(AIチャット × 物語ゲーム)が示した「選択肢で物語が進む」「キャラが記憶する」「ビジュアルノベル演出」という体験需要は、小説生成ツールの延長線上にあると判断される。

本プロジェクトには、この体験の裏側がすでに実装済みである(`docs/STATUS.md` §2):

- IF ルート分岐コア(`src/easy_mode/phase3/if_routes.py`、`CHOICE/CONDITIONAL/RANDOM/LOOP/MERGE` の 5 分岐タイプ)
- Branch REST API + プレイセッション + 認証付き WebSocket(`src/backend/routers/branches.py`)
- RAG 基盤(pgvector > Chroma > InMemory フォールバック)、Stripe 課金、メディアミックス台本(`src/easy_mode/phase3/media_mix.py`)

欠落は**フロントの「遊ぶ見せ方」**と**「選択時の動的生成」**のみである。

## 検討した選択肢

| # | 選択肢 | 評価 |
|:--|:---|:---|
| 1 | 現状維持(生成→納品で完結) | 差別化の機会を捨てる。生成資産の再体験価値が死んだまま |
| 2 | フルフリーチャット RP の導入(ISEKAI ZERO の全面模倣) | 既存 AI チャット市場と正面衝突し、執筆パイプラインの品質優位が活きない。非目標 |
| 3 | **プレイアブルノベル**(生成済み小説を遊べる形に変換) | 既存資産の延長で実現でき、「監査・RAG・改稿を通った本文を遊べる」品質が差別化軸になる |

## 決定事項

- **選択肢 3 を採用**する。機能名は「**Play モード**」とする(Easy Mode Suite の「Interactive Writer」との混同回避、`docs/easy_mode_suite.md` §2.1 参照)
- 全体構想は `docs/plans/ROADMAP_PLAYABLE_NOVEL.md` に従う
  - Phase 0(Play モード UI)→ Phase 1(動的継続生成)→ Phase 2(キャラ対話)→ Phase 3(マルチメディア)→ Phase 4(UGC 公開: ゲート制)
- 動的継続生成は feature flag(例: `ENABLE_DYNAMIC_BRANCH`)**既定 OFF** で導入し、「OFF = 既存挙動不変」を契約テストで担保する(提案 5/8 で採用済みのパターン)
- フルフリーチャット RP は非目標。UGC 公開・収益分配は Phase 4 の意思決定ゲート(別 ADR)を通すまで着手しない

## 結果・影響

- **利点**:
  - Phase 0 はバックエンド無変更で開始できる(既存 `/api/branches/play/*` の表面化のみ)
  - KPI(プレイ開始率・完走率)を小コストで取得でき、Phase 1 以降の GO/NO-GO を実データで判断できる
  - 撤退が容易: 反応が薄ければ Phase 0 で止まっても「既存機能の表面化」として価値が残る
- **トレードオフ**:
  - Phase 1 以降、同期生成経路(LLM 応答)が新たなコスト・レイテンシ管理対象になる
  - グラフ型(事前生成)と動的型(選択時に生成)の二様のプレイを、1 つの play セッションモデル(`branch_play_sessions`)で支える必要がある
- **撤回条件**: Phase 0 の KPI ベースライン(プレイ開始率)が基準値を大きく下回り、改善の見込みが立たない場合、本 ADR を「却下 (Rejected)」に更新する

## 関連

- `docs/plans/ROADMAP_PLAYABLE_NOVEL.md` — 全体構想(SSOT 的な現状マップを含む)
- `docs/implementation_plans/playable_novel_phase0.md` — Phase 0 実装計画
- `docs/adr/001-agent-memory-architecture.md` — Phase 2(キャラ対話の記憶設計)で参照する
