# ADR 003: Phase 3 挿絵生成の本線クライアント決定と Increment 1 の範囲

## ステータス

承認 (Accepted) — 2026-11-25。Phase 3 Increment 1(表示配線)の実装開始指示により承認。

## コンテキスト

Phase 3 事前調査(`docs/plans/PHASE3_ILLUSTRATION_WIRING_SURVEY.md`)により、挿絵生成の実装が**3 系統並存**していることが判明した:

| 系統 | 実装 | 配線状況 |
|:--|:---|:---|
| A. `ImageService`(Imagen 直叩き、google-genai SDK) | `src/publishing/illustration/image_service.py:18` | **本線。配線済み**(DI・DB・Studio UI・CLI がこの前提) |
| B. env 駆動ファクトリ群 | `factory.py:24/:58`(DALL·E/fal.ai/SD WebUI/Mock) | src 本体から未使用(テストのみ) |
| C. 新 Protocol 群 | `clients/gemini_image_client.py:31` 他(統合器 `UnifiedIllustrationGenerator` は docstring のみで実体なし) | 未配線 |

さらに以下の構造的欠落が確認されている(§3 ギャップリスト P0):

- パイプラインからの挿絵生成は常に no-op(`ctx.artifacts["request"]` をセットする箇所がゼロ)
- `POST /generate` は DI が `repo` を注入しないため DB 非保存
- `/static/illustrations/` の配信マウントが存在しない
- Play モード用の episode_number 決定的クエリ API が無い

## 検討した選択肢

| # | 選択肢 | 評価 |
|:--|:---|:---|
| 1 | **A(ImageService/Imagen)を本線として維持** | 配線済み・テスト済み・DB と既存 UI がこの前提で動く。Increment 1(表示配線)はこの前提で即実装可能 |
| 2 | C(新 Protocol)へ統合リファクタしてから進む | `UnifiedIllustrationGenerator` は実体がなく、統合は大規模リファクタ。Phase 3 の価値(表示)と直接関係しない先行投資 |
| 3 | B(env ファクトリ)を復活させる | マルチプロバイダ対応の見かけだが src 本体未使用・settings の Literal とも不整合があり、修復コストに見合う価値が現時点でない |

## 決定事項

- **選択肢 1 を採用**: Phase 3 の本線は **`ImageService`(Google Imagen)** のままとする
- **B/C(未配線のファクトリ・Protocol・`GeminiImageClient`)は Phase 3 対象外**。削除はせず、後日この ADR の改訂または別 ADR で整理(削除/統合/維持)を判断する
- 開発・CI は **mock 運用**を維持: `ImageService` はキー必須だが、DI/テストではスタブ注入(`generation_tasks.py:271` の `_DummyImageService` 等が既存)。`IMAGE_PROVIDER` 既定 `mock` の env ファクトリとは独立
- Increment 1(表示配線)の実装順:
  1. `episode_number` + `illustration_type` の決定的クエリ API(新規 GET エンドポイント)
  2. Play モードでの表示 + フォールバック(`found:false` → 画像非表示)
  3. `/static` の配信マウント(バックエンド)と vite proxy 追加
- Increment 2 以降(生成・保存経路の修復: DI への `repo` 注入、パイプライン接続)は別コミット/別計画に分離する

## 結果・影響

- **利点**: Increment 1 は既存 DB 行の読み取りのみで成立し、既存挙動を変更しない(新規エンドポイントと UI 追加のみ・flag 不要)。生成経路の修復(コスト・レイテンシが絡む)と表示配線を切り分けて検証できる
- **トレードオフ**: B/C の未配線コードが残存する(技術的負債の棚上げ)。`docstring` の `UnifiedIllustrationGenerator` 言及は実体がないまま残る
- **コスト**: Increment 1 は生成を行わないため新規 API コストはゼロ。生成経路の修復(Increment 2)は Imagen の課金(モデル別)が発生するため、別途レート制限・上限の設計を要する

## 関連

- `docs/plans/PHASE3_ILLUSTRATION_WIRING_SURVEY.md` — 本決定の根拠となる調査
- `docs/plans/ROADMAP_PLAYABLE_NOVEL.md` §4 Phase 3 — Increment の位置づけ
- `docs/adr/002-play-mode-mainline.md` — Play モード本線化の決定
