# AutoNovel 4層アーキテクチャ設計（改善案3）

> 本書は「30超の `src/` サブディレクトリを 4 層に再編する」ための**設計図**である。
> 本ドキュメントの作成時点では、実際のディレクトリ移動はまだ行っていない
> （既存の未コミット作業と衝突するため、まず設計と境界の機械的強制を先行させた）。
> 移行は §5 のフェーズに沿い、クリーンな作業ツリーでリーフモジュールから進める。

## 1. 目的

- ドメインロジック（小説生成のルール）を、フレームワーク・DB・外部API・UI から**独立**させる。
- 依存の方向を **内側 → 外側** の一方向に固定し、変更の影響範囲を局所化する。
- 「どこに何を置くか」を機械的に検証できるようにし、テスト不要の静的境界チェックで崩れを早期検出する（フルテストが 3 時間規模の本リポジトリでは特に有効）。

## 2. 4層の定義と依存ルール

内側 → 外側の順。**外側から内側への import は禁止**（内側は外側を知らない）。

| 層 | 役割 | 依存してよいもの |
|---|---|---|
| **domain**（最内） | エンティティ・値オブジェクト・領域サービス・ドメインルール。I/O もフレームワークも知らない。 | 標準ライブラリ、shared/utils/schemas |
| **application** | ユースケースのオーケストレーション。DTO・port（インターフェース）を定義。 | domain、shared |
| **infrastructure** | adapter。DB・外部LLM・ベクトルストア・ログ等の実装。port の実装を提供。 | domain、application（port） |
| **interfaces**（最外） | FastAPI ルーター・CLI・GraphQL・WebSocket 等のエントリポイント。 | application、domain、infrastructure |

```
        ┌──────────────────────────────────────┐
        │ interfaces  (routers / cli / graphql) │
        │      ↓  application                   │
        │ application (use_cases / dtos / ports)│
        │      ↓  domain                        │
        │ domain      (entities / rules / svc)  │
        └──────────────────────────────────────┘
   infrastructure は domain / application の port を「実装」し、
   interfaces から使われる（内側には依存しない）。
```

## 3. ディレクトリ対応表（現状 → 目標層）

`src/` 配下を規模順に、目標の層へ割り当てる。

### 3.1 正規4層（既に存在・整備済み／拡充対象）

| 現在のディレクトリ | 規模 | 目標層 | 備考 |
|---|---:|---|---|
| `src/domain/` | 64 files / 9.1k | domain | entities, models, repositories, domain_services, value_objects, writing |
| `src/application/` | 21 files / 2.7k | application | use_cases, dtos, ports |
| `src/infrastructure/` | 47 files / 5.3k | infrastructure | database(mappers/models), repositories, external |
| `src/interfaces/` | 5 files / 0.1k | interfaces | api, cli, graphql（薄い・拡充が必要） |

### 3.2 旧来の巨大モノリス（4層へ分割・統合していく）

| 現在のディレクトリ | 規模 | 目標層への行き先 |
|---|---:|---|
| `src/services/` | 278 files / 44.7k | ロジックの多くは **domain/application**、DB・外部API 部分は **infrastructure** へ |
| `src/backend/` | 218 files / 36.3k | routers→**interfaces**、database/security→**infrastructure**、workflows→**application** |
| `src/agents/` | 122 files / 24.0k | オーディター/生成エージェント→**application**（use_case）＋**domain**（ルール） |
| `src/narrative_balancer/` | 61 files / 3.4k | 物質バランスのルール→**domain**、解算器(CSP/DSP)→**infrastructure** |
| `src/core/` | 52 files / 4.5k | DI コンテナ→bootstrap、LLM gateway→**infrastructure**、SPI→**application**(port) |
| `src/models/` | 48 files / 5.6k | ORM→**infrastructure**、Pydanticスキーマ→**application**(dto) |
| `src/narrative/` | 16 files / 2.4k | 物語ロジック→**domain** |
| `src/pipeline/` | 11 files / 1.5k | オーケストレーション→**application** |
| `src/rules/` | 9 files / 1.4k | 執筆ルール→**domain** |
| `src/easy_mode/` | 8 files / 4.8k | ユースケース→**application**、EPUB出力→**infrastructure** |
| `src/llm/` | 7 files / 1.2k | LLM adapter→**infrastructure** |
| `src/fusion/` | 10 files / 1.1k | 統合ロジック→**domain/application** |
| `src/audit/` | 5 files / 0.6k | 監査ルール→**domain**、実行→**application** |
| `src/stores/` | 4 files / 0.9k | 永続化→**infrastructure** |
| `src/generation/` | 4 files / 0.5k | 生成→**application** |
| `src/engine/` | 6 files / 0.6k | 実行エンジン→**application/infrastructure** |
| `src/annotations/` | 6 files / 0.8k | 注釈→**domain** |
| `src/cli/` | 4 files / 0.5k | CLI→**interfaces** |
| `src/api/` | 6 files / 0.4k | ミドルウェア/API→**interfaces** |
| `src/monitoring/` `src/logging/` | 2+1 | **infrastructure** |
| `src/plugins/` `src/presets/` | 8+2 | プラグイン→**infrastructure**、プリセット→**domain** |
| `src/prompts/` `src/schemas/` | 1+2 | prompt→**infrastructure**、schema→**application** |
| `src/config/` `src/shared/` `src/utils/` `src/types/` `src/security/` | — | 横断（shared 側）。`config` は SSOT 整合済み（改善案2） |

> 空/極小のプレースホルダ（`src/components/` `src/data/` `src/hooks/` `src/types/`）は移行時に廃止候補。

## 4. 境界の機械的強制

手順書ではなく「壊れたら CI で落ちる」仕組みを `scripts/check_layer_boundaries.py` として実装した（外部依存なし・`ast` ベース・数秒で完了）。

### 契約1「純粋な内側依存」（HARD・恒久ルール）
- 内側レイヤーが外側の正規レイヤーを import しない。
- `domain ≁ {application, infrastructure, interfaces}` / `application ≁ {infrastructure, interfaces}` / `infrastructure ≁ {interfaces}`。
- **現在 0 違反**。baseline を持たず、増加したら即 fail。4層の不変条件を固定する。

### 契約2「旧巨大モノリスへの依存」（RATCHET・縮小のみ許可）
- 正規レイヤーが `src.backend` / `src.services` / `src.agents` を import しない。
- 現状の違反数を `config/layer_boundaries_baseline.json` に記録し、減少のみ自動採用・増加は fail（既存 `ci_lint_ratchet.py` と同じ方式）。

```bash
python scripts/check_layer_boundaries.py                   # チェック
python scripts/check_layer_boundaries.py --report          # 違反内訳（移行 TODO）
python scripts/check_layer_boundaries.py --update-baseline # ベースライン再記録
make lint-layers                                           # Makefile ターゲット
```

## 5. 移行フェーズ（今後の本格再編）

各フェーズは「境界チェックが緑のまま」進める。必ずクリーンな作業ツリー（未コミット WIP を整理後）で実施すること。

| フェーズ | 内容 | 対象（規模順） |
|---|---|---|
| **F0** | 設計＋境界チェック導入（本書・本スクリプト） | ✅ 完了 |
| **F1** | 契約2 の 0 件化: `domain/writing` の `agents/services` 依存を port 経由に置換 | domain 4件・application 1件 |
| **F2** | `src/backend/database` + `src/infrastructure` を統合（ORM/mapper を infrastructure に一元） | infrastructure 39件の大半 |
| **F3** | `src/backend/routers` → `src/interfaces/api`、`server.py` → bootstrap | backend の routers 部分 |
| **F4** | `src/services` のロジックを domain/application へ分割（最大工事） | services 278件 |
| **F5** | `src/agents` を application(use_case)＋domain(rule) へ | agents 122件 |
| **F6** | 残レガシー（models/core/narrative 等）の統合と空ディレクトリ廃止 | 上表 §3.2 残 |

各フェーズ完了時に `config/layer_boundaries_baseline.json` を下げ、F1〜F6 で契約2 を 0 へ近づける。

## 6. 現状の境界違反（移行 TODO スナップショット）

境界チェック実行時点の計 **7 件**（`--report` で常に最新を取得可能）。
`config/layer_boundaries_baseline.json` は total=7 に記録済み（TRACK-A1〜A9 完了時点）。
目標値 ≤10 を達成済み。

| レイヤー | 件数 | 主な内容 |
|---:|---:|---|
| domain | 0 | —（TRACK-A1/A2 で `coordinator.py`, `quality_loop.py` を port 経由 DI に置換し解消） |
| application | 0 | —（TRACK-A3 で `book_use_cases.py` を port 化し解消） |
| infrastructure | 2 | `repositories/foreshadowing_repo.py` が `backend`(observability) / `services` を依存（残） |
| interfaces | 5 | `interfaces/api/` に移設した 3 ルーター（`metrics`, `platform_export`, `styles`）が `backend`/`services` を直接 import（TRACK-A8 で旧パス shim 化済み。F3 フェーズでポート化予定） |

> 契約1（正規レイヤー間の逆方向依存）は **0 件**で維持されている。4層の骨格は既に保たれており、残は「レガシー接続の断線」である。
> 契約2 は 44 件 → 7 件へ削減（目標 ≤10 達成済み）。残 2 件（infrastructure）は F2 フェーズで対応予定。
