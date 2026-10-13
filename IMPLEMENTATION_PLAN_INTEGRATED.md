# 伏線自動設置パイプライン 統合実装計画書

作成日: 2026-10-05
統合対象: `PLAN_FORESHADOW_PLANTING.md`（2026-10-05 付）+ 公開前監査の残タスク
作業ディレクトリ: **`E:\autonovel_qa`**（分離 worktree。`E:\autonovel` は他 LLM が使用中のため使用しない）
基準ブランチ: `qa/audit-remediation` @ `7a1875c`

---

## 0. 実行前の必須事項（衝突回避）

### 0.1 なぜ worktree が必要か

`E:\autonovel` では**別プロセスの LLM が並行で編集している**（2026-10-05 13:34 に
`pytest tests/unit` を実行、54 ファイルが未コミットだった実績あり）。
同じディレクトリで作業すると以下が実際に起きている。

| リスク | 実測された事象 |
|---|---|
| `git checkout -- <file>` による相互破壊 | 監査中に**私自身が 3 ファイルを破壊** |
| SQLite ロック競合 | `autonovel.db-wal` が他テスト実行中に更新、`database is locked` |
| `__pycache__` / `.pytest_cache` の共有 | 予期しない collection 差異 |

したがって **全作業は `E:\autonovel_qa` でのみ行う**。

### 0.2 禁止事項（作業期間中の双方）

- ❌ `E:\autonovel` での pytest 実行（分離先を使う）
- ❌ `git checkout --` / `git reset --hard`（他者の作業.Assertを破壊する）
- ❌ `git add -A`（自分のファイルだけを `git add <path>` で明示する）
- ❌ 他サブエージェントの担当ファイルに手を入れる

---

## 1. 前提の検証結果（計画の誤りを指摘）

`PLAN_FORESHADOW_PLANTING.md` の記載を**実コードで検証**した。
この計画に沿って実装する前に、必ず次の**3件の誤り**を修正する必要がある。

| 計画の記載 | 検証結果 | 判定 |
|---|---|---|
| G1: 生成経路で `add()` を呼ばない | `add()` の呼び出し元は **0 件**（src 全域） | ✅ 正しい |
| G2: `foreshadowing_setup/payoff` は読まれていない | `src/models/plot.py:1035-1036` に存在。`cost_optimization.py:96,112-114` が読むが、**伏線機能からは読まれない** | ✅ 正しい（読み手の意味は限定的） |
| G9: `ForeshadowingModel` に `keywords` 列が無い | 列定義 11 個すべて確認。`keywords` は**存在しない** | ✅ 正しい |
| G3/G4: `generator.py` が空の dict を渡す | `generator.py:206-220` は「簡易版」context を構築し `contract_foreshadowings` を含まない | ✅ 正しい |
| （計画に無い） | **`episode_writer.py:518-531` の `_build_full_context()` は定義されているが呼び出し元 0 件（死んだコード）** | ⚠️ **計画は甘く書いている** |
| Phase 3: `_env_flag("FORESHADOW_PLANTING", True)` | **`_env_flag(name)` は引数1つだけ**。2 個目を渡すと `TypeError` | ❌ **技術的に誤り** |
| Phase 3: 既定を `True` にする | `flags.py` の docstring は **「すべて既定 False。ON にしない限り既存挙動は完全に現状維持される」** と明記 | ❌ **モジュールの原則と矛盾** |
| Phase 1: `alembic/versions/0031_add_foreshadowing_keywords.py` | 実体は **`src/backend/alembic/versions/`**（ルート `alembic/` には `env.py` のみ）。総数 28、HEAD は **`0034_tasks_user_id`**。`0031` は既に埋まっている | ❌ **パスも番号も誤り** |

### 1.1 確定した実装パラメータ（推測禁止）

```python
# マイグレーション（Phase 1 で新設）
#   パス:       src/backend/alembic/versions/0035_add_foreshadowing_keywords.py
#   revision:     "0035_add_foreshadowing_keywords"
#   down_revision: "0034_tasks_user_id"    # ← 実測で確定した HEAD
```

```python
# src/infrastructure/repositories/foreshadowing_repo.py（実測した署名）
async def add(self, book_id: int, title: str, description: str,
              planted_episode: int, target_episode: Optional[int] = None,
              scope: Optional[ForeshadowingScope] = None) -> ForeshadowingModel
# → keywords はキーワード引数として末尾に追加（既存の位置引数呼び出しを壊さない）
# add_many() / bulk_add() は存在しない（Phase 2 で新設）
async def resolve(self, foreshadowing_id: int, episode_num: int) -> bool  # 存在済み

# src/services/foreshadowing/planner.py:145 に plan_foreshadowing が既に存在（Phase 2 で利用）
# src/services/foreshadowing/flags.py の _env_flag は引数1つのみ。既存フラグは全て既定 False
```

```python
# src/infrastructure/repositories/foreshadowing_repo.py
async def add(self, book_id, title, description, planted_episode,
              target_episode=None, scope=None) -> ForeshadowingModel   # 署名確認
async def resolve(self, foreshadowing_id: int, episode_num: int) -> bool  # 存在
# add_many() / bulk_add() は存在しない（Phase 2 で新設が必要）

# src/services/foreshadowing/planner.py:145
def plan_foreshadowing(...)   # 既に存在（Phase 2 で利用）
```

---

## 2. 設計上の変更（計画を 3 点修正）

### C1: Phase 3 のフラグを追加引数なしで実装する

計画の `_env_flag("FORESHADOW_PLANTING", True)` は `TypeError` になる。
かつ既定 True は `flags.py` の「既定 False で既存挙動維持」原則に反する。

**修正方針**: フラグは **既定 False**（モジュール原則に準拠）で導入し、
デフォルトでは**pipeline が無効**、明示的に `FORESHADOW_PLANTING=1` で有効化する。
段階ロールアウトの観点でも既定 False が安全。

```python
# src/services/foreshadowing/flags.py に追加
def is_foreshadowing_planting_enabled() -> bool:
    """伏線自動設置を有効にするか（既定 False = 既存挙動維持）。"""
    return _env_flag("FORESHADOW_PLANTING")
```

### C2: Phase 4 の真の実態を計画に反映する

計画は「`generator.py` が空 dict を渡す」と書いているが、実際は
**`episode_writer._build_full_context()` が死んでいる**。

修正後のPhase 4 は 2 段構えになる:
1. `generator.py` が `contract_foreshadowings` を渡す経路を**新設**する（既存簡易版 context に足す）
2. `episode_writer.run()` から `_build_full_context()` を**実際に呼ぶ**ようにする
   （既に `self.context_builder` を保持しているため配線のみ）

### C3: Phase 2 は他 LLM との衝突が最大（ファイル分割で回避）

Phase 2 のフック先 `bible_service.py` は**他 LLM が編集中**。
後述のファイル分割で担当を分離し、 conflicted ファイルを同一サブエージェントにAssignしない。

---

## 3. ファイル分割（2 サブエージェント）

**衝突しないよう、担当ファイルを排他的に割り当てる。**

### サブエージェント A:「データ層と設置エンジン」（Phase 1, 2, 3, 5）

| 担当ファイル | 独占 |
|---|---|
| `src/backend/database/models_foreshadowing.py` | ✅ A のみ |
| `alembic/versions/0031_add_foreshadowing_keywords.py`（新設） | ✅ A のみ |
| `src/infrastructure/repositories/foreshadowing_repo.py` | ✅ A のみ |
| `src/services/foreshadowing/planting_service.py`（新設） | ✅ A のみ |
| `src/services/foreshadowing/flags.py` | ✅ A のみ |
| `src/services/foreshadowing/kpi.py` | ✅ A のみ |

**触らない**: `bible_service.py`（他 LLM 作業中）→ フックは A が
`planting_service.py` に**独立関数として用意**し、統合は後段 P0 で行う。

### サブエージェント B:「コンテキスト配線」（Phase 4, 6）

| 担当ファイル | 独占 |
|---|---|
| `src/agents/writing/generator.py` | ✅ B のみ |
| `src/agents/writing/episode_writer.py` | ✅ B のみ |
| `src/services/context_compression/*`（既存接続のみ） | ✅ B のみ |
| `tests/integration/test_v53_long_form_wiring_e2e.py`（新設） | ✅ B のみ |

### 共有してよいファイル（競合の可能性あり → 直前に `git status` を確認）

| ファイル | 方針 |
|---|---|
| `src/services/bible_service.py` | **両者触らない**。P0 で統合者が作業 |
| `src/models/plot.py` | 変更不要（読み取りのみ） |
| `docs/` の計画書 | 各担当が自分のフェーズ分のみ追記 |

---

## 4. サブエージェント A の作業手順

### A-P1: `keywords` 列の追加（フェーズ1）

**手順**
1. `src/backend/database/models_foreshadowing.py` に
   `keywords = Column(Text, nullable=True)` を追加
   （カンマ区切り文字列で持つ。JSON 配列は SQLite の既存互換性を崩すため避ける）
2. `src/infrastructure/repositories/foreshadowing_repo.py`:
   - `add()` に `keywords: Optional[Sequence[str]] = None` を**キーワード引数で末尾に追加**
     （既存呼び出しを壊さないため位置引数にしない）
   - 内部で `",".join(keywords)` に変換して保存
   - **読み出しヘルパー** `split_keywords(record) -> list[str]` を新設
3. `alembic/versions/0031_add_foreshadowing_keywords.py` を新設
   - `revision` は既存の最新（Alembic は `down_revision` で直前を指定）。**実際の
     最新リビジョン ID は作業開始時に `alembic history` で確認すること**（推測しない）

**注意**: `ForeshadowingModel` は既存のテストで `Base.metadata.create_all` される。
列追加のみで既存コードは壊れないが、`_report_planted` 経路上のifold テストは確認する。

**工数**: 約 60〜90 行（マイグレーション含む）

---

### A-P2: 設置エンジン（フェーズ2）

**手順**
1. `src/services/foreshadowing/planting_service.py` を新設し、次を提供:
   ```python
   async def plant_from_roadmap(
       uow_or_repo, book_id: int, roadmap_items: Sequence[RoadmapItemLike],
       total_episodes: int, flag_enabled: bool,
   ) -> list[ForeshadowingModel]:
       """roadmap から伏線を設置する（冪等）。"""
   ```
   ロジック:
   - `flag_enabled` が False なら**何もせず空リスト**を返す（ロールバック可能性）
   - `item.foreshadowing_setup` が `"なし"` / 空文字ならスキップ
   - `planner.plan_foreshadowing(planted_episode=item.ep_num, total_episodes=...)`
     で `target_episode` / `scope` を決定
   - **冪等性**: 既存 `get_by_book_id(book_id)` から
     `(planted_episode, title)` の集合を作り、交差したら**スキップ**
     （`INSERT OR IGNORE` ではなく**アプリ側で判定**して明示的にスキップする。
      後者の方が理由がログに残り、診断が容易）
2. `foreshadowing_repo.py` に `add_many()` を新設
   - `add()` を N 回呼ぶのではなく 1 トランザクションで一括
   - ただし **KPI（`foreshadowing_planted_total`）を取りこぼさない**ため、
     `add()` の `_report_planted` 相当を `add_many()` 内でも**必ず呼ぶ**
     （Phase 5 の要件。raw `insert()` を使うと KPI が壊れる）
3. **フックは本 Phase で付けない**（`bible_service.py` は他 LLM 作業中）。
   統合は P0 で行う（§6）

**工数**: 約 120〜160 行

---

### A-P3: 特徴フラグ（フェーズ3）

**手順**
1. `src/services/foreshadowing/flags.py` に
   `is_foreshadowing_planting_enabled() -> bool` を追加（§2 C1 参照）
2. docstring に「既定 False」「Phase 2 の設置エンジンがこれを参照」と明記

**工数**: 約 10 行

---

### A-P4: KPI 経路の保証（フェーズ5）

**手順**
1. `add_many()` が `add()` と同じ `_report_planted` を呼ぶことを**テストで固定**
2. `planting_service` が raw `insert()` を**使わない**ことを**静的ゲートで固定**

**工数**: テストのみ

---

## 5. サブエージェント B の作業手順

### B-P1: generator から契約伏線コンテキストを渡す（フェーズ4 前段）

**手順**
1. `src/agents/writing/generator.py:206-220` の「簡易版」context に、
   `contract_foreshadowings` を**追加**する。ただし**値が空でもよい**：
   本 Phase は「キーを存在させる」（`EpisodeWriter` 側の `.get(...) or []` と整合させる）
2. 値が埋まる経路は B-P2（`episode_writer`）が担う
3. **注意**: `generator.py` は他 LLM が編集中だった。作業前に
   `git status` で他方の未完了変更が無いか確認し、**あれば一旦 P0 へ退避**する

**工数**: 約 20〜40 行

---

### B-P2: `_build_full_context` の死んだコードを復活させる（フェーズ4 後段）

**手順**
1. `src/agents/writing/episode_writer.py:518-531` の `_build_full_context()` は
   **呼び出し元 0 件**（自明に死んでいる）。`run()` 経路からこれを呼ぶように配線する
2. ただし `run()` は既に `self.context_builder` を保持しているため、
   **既存の `write()` 経路を壊さないこと**（新しい引数を追加するか、
   既存の `writing_context` を `context_builder` の出力で**上書きmerge**する）
3. `ContextBuilderAgent` の出力を既存 `writing_context` と**マージ**する（丸ごと置換しない）
   - 理由: `generator.py` が渡す `target_word_count` / `style_intensity` 等を
     失う可能性があり、最小限のenden壊れ方をする

**工数**: 約 40〜70 行

---

### B-P3: 結合検証（フェーズ6）

**手順**
1. `tests/integration/test_v53_long_form_wiring_e2e.py` を新設
2. 検証対象:
   - `contract_foreshadowings` に ID があると**プロンプトに `[伏線ID: n]` が出る**
   - 空なら出ない（ Anchorsambejo ない=Llm 回应不可、が正常）
3. **実際のプロンプト文字列を assert する**（内部メソッドの呼び出し回数のCountingではなく）

**工数**: 約 60〜100 行（テストのみ）

---

## 6. 統合（P0）: 2 サブエージェント完了後

**担当**: 統合者（主线）

| 手順 | 内容 |
|---|---|
| P0-1 | 2 サブエージェントのブランチをマージ。**ファイル重複が無いことを確認**（§3 で排他化したため競合は無いはず） |
| P0-2 | `src/services/bible_service.py` へのフック設置（Phase 2 の統合点）。`_create_*_plan` の直後、`save_full_world_bible` の後に `plant_from_roadmap()` を呼ぶ。**フラグが False のとき何もしない** |
| P0-3 | 統合後、全 Tier1 を走らせ**回帰ゼロ**を確認 |
| P0-4 | `scripts/ci_tier_ratchet.py` で新規失敗 0 件を確認 |

---

## 7. リグレッション防止テスト計画

**方針**: 「テストを足す」ではなく「**壊れたときの検証力を残す**」。
今回の公開前監査で判明した根本原因（意図的な強化にテストが追従せず、
静かに検証力を失う）を踏まえる。

### 7.1 サブエージェント A の担当

| ID | 対象 | 種別 | 内容 |
|---|---|---|---|
| A-T1 | `keywords` 列の永続化 | 契約テスト | `add(keywords=["a","b"])` → 読み出しで `["a","b"]` に戻る往復。**区切り文字を含む文字列**（`,` を含むキーワード）で**壊れない**ことを確認（naive join の危険） |
| A-T2 | `keywords` が `None` の挙動 | 契約テスト | `add()` の既存呼び出し（keywords 未指定）が** breakage なく**動くことを確認 |
| A-T3 | `add()` の後方互換 | 回帰 | 既存呼び出し（位置引数 4 つ）が**そのまま**動くこと（キーワード引数化したため） |
| A-T4 | `plant_from_roadmap` の冪等性 | 契約テスト | 同じ roadmap を2回流しても**行が増えない**（重複設置が起かないこと）。これは本 Phase の**核心**であり、漏れると伏線が二重になる |
| A-T5 | フラグ OFF で何もしない | 契約テスト | `is_foreshadowing_planting_enabled() == False` のとき `plant_from_roadmap` が **0 件**を返し、DB に副作用が無いこと。**ロールバック可能性の担保** |
| A-T6 | `"なし"` / 空文字のスキップ | 契約テスト | `foreshadowing_setup="なし"` の roadmap item が**設置されない**（Risk A の関連） |
| A-T7 | KPI が脱落しない | 回帰（静的） | `planting_service` / `foreshadowing_repo` に**生 `insert()` が無い**ことを AST で固定。raw insert を使うと `foreshadowing_planted_total` が壊れる（Phase 5 の存在的理由） |
| A-T8 | add_many の KPI | 契約テスト | `add_many()` が `add()` と同じ `_report_planted` を呼ぶこと（bulk で KPI が減らないこと） |
| A-T9 | マイグレーション整合 | 回帰 | `alembic upgrade head` 後に `keywords` 列が存在し、`downgrade` で戻ること。`Base.metadata` とマイグレーションの**乖離**を検出 |

### 7.2 サブエージェント B の担当

| ID | 対象 | 種別 | 内容 |
|---|---|---|---|
| B-T1 | プロンプトへのアンカー描画 | 結合 | `contract_foreshadowings` に ID があるとき、プロンプト文字列に `[伏線ID: n]` が**実際に出る**こと（内部呼び出し回数ではなく**文字列**で assert） |
| B-T2 | 空契約では何も出ない | 結合 | 空 list のとき `[伏線ID:` が**出ない**こと（出ると LLM が空 ID を返す） |
| B-T3 | `_build_full_context` が到達可能 | 回帰（静的） | このメソッドが**どこから呼ばれるか**を AST で確認し、**呼び出し元 0 件**の状態を検出（今回見つかった「死んだコード」の再発防止）。<br>`tests/regression/` に置く（全L1 の他サブエージェントが触らない） |
| B-T4 | context のマージで情報が失われない | 契約 | `generator.py` が渡す `target_word_count` などが `context_builder` の出力で**消えない**こと（丸ごと置換による退行防止） |
| B-T5 | 既存の本文生成が壊れない | 回帰 | episode_writer の既存テスト（	ests/unit/** の writing 系）が**全て通ること**。配線を変更することで既存の執筆フローが壊れるのが最大のリスク |

### 7.3 統合後の最終検証

```powershell
# 回帰ゼロの確認（新規失敗ファイル Introduction が無いこと）
python scripts/ci_tier_ratchet.py

# 既存フローの非回帰
python -m pytest tests/unit tests/services tests/regression tests/security -q --tb=line

# 統合が正しいことの確認
python -m pytest tests/integration/test_v53_long_form_wiring_e2e.py -q
```

---

## 8. リスクと緩和策（計画の Risk A/B への回答）

| リスク | 緩和策 |
|---|---|
| **A**: roadmap の `foreshadowing_setup` が空 / 一律 `"なし"` | A-T6 でスキップを固定。**さらに**、Phase 6 で `detailed_blueprint` からのキーワード抽出フォールバックを**別 Phase として保留**する（本次スコープ外。heuristic ではなく LLM 抽出にすべき） |
| **B**: 既存テストへの影響 | フラグが既定 False（A-P3）なので、**フラグをオフにすれば既存の全挙動が完全に現状維持**される。したがって既存テストへの影響は最小であり、万が一evesれば**フラグを_off_** 即可でロールバックできる |
| **C（新規）**: 他 LLM と `generator.py` / `bible_service.py` が衝突 | §0 の worktree 分離 + §3 の排他割当。**`bible_service.py` は P0 でしか触らない** |
| **D（新規）**: Phase 2 と Phase 4 の**順序依存**（設置された伏線が回収されるには B の配線が必要） | A は設置のみ、B は配線のみに**役割を分離**。統合 P0-2 で初めて「設置 → 回収」の**経路が繋がる**。このため**個別のサブエージェントのテストでは end-to-end を主張しない**（P0-3 で初めて主張する） |

---

## 9. マイルストーン

| MS | 内容 | 担当 | 完了条件 |
|---|---|---|---|
| **MS-A1** | データ層（keywords 列 + マイグレーション + repo API） | A | A-T1〜T3, A-T9 が pass |
| **MS-A2** | 設置エンジン + フラグ + KPI 保証 | A | A-T4〜T8 が pass。フラグ OFF で**副作用ゼロ** |
| **MS-B1** | 契約伏線コンテキストの配線 | B | B-T1, B-T2, B-T4 が pass |
| **MS-B2** | 死んだコードの復活的配線 | B | B-T3 が pass（呼び出し元 > 0）、B-T5 が pass |
| **MS-I** | 統合 + 回帰ゼロ証明 | 統合 | ratchet 新規 0 / Tier1 緑 |

---

## 10. この計画が**しない**こと

| 提案 | 却下理由 |
|---|---|
| `bible_service.py` へのフックを A にやらせる | 他 LLM が編集中。**P0 で統合者がやる**（§3 / §8-C） |
| Phase 6 の e2e を各サブエージェントにやらせる | 設置（A）と配線（B）は別フェーズ。**統合後に初めて「設置 → 回収」が繋がるため、P0-3 でのみ主張する |
| フラグの既定を True にする | `flags.py` の「既定 False」原則に反し、ロールバック不能になる |
| `keywords` を JSON 配列で保存する | 既存 SQLite 互換性 + 既存マイグレーションの扱いを壊す。**カンマ区切り**を採る |
| raw `insert()` で高速化する | KPI (`foreshadowing_planted_total`) を脱落させる。`add()` / `add_many()` を通す（A-T7 で固定） |
| roadmap からのキーワード抽出 heurist（Risk A） | heuristic ではなく LLM 抽出が本筋。本次は**スキップする**に留め、別 Phase とする |

---

## 11. 工数サマリ

| 担当 | Phase | 工数（行数目安） |
|---|---|---|
| A | 1（データモデル + マイグレーション） | 60〜90 |
| A | 2（設置エンジン + add_many） | 120〜160 |
| A | 3（フラグ） | 10 |
| A | 5（KPI 保証、テストのみ） | （A-T7/A-T8 に含む） |
| B | 4 前段（generator のコンテキスト） | 20〜40 |
| B | 4 後段（_build_full_context の復活的配線） | 40〜70 |
| B | 6（結合テスト） | 60〜100 |
| 統合 | P0（マージ + bible_service フック + 回帰証明） | 40〜60 |
| **合計** | | **約 350〜520 行** |

新規リグレッションテストは **A: 9 項目 / B: 5 項目**（計 14 項目）。
**既存テストの削除・弱体化は行わない**（削除する場合は別のカバレッジを必ず補充する）。