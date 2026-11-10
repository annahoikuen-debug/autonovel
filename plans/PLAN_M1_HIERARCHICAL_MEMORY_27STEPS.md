# PLAN_M1: 階層的逐次要約メモリ実装計画書 (27 Steps)

> **目的**: 長編(30話〜)で Layer2 の「1話ごとの独立100字ダイジェスト+中間省略マーカー」が
> 中盤の確定事実を失う問題を解消する。話→章(ブロック)→巻の**ツリー状逐次要約**へ刷新し、
> さらに**重要情報をプロンプト両端へ配置**(Lost in the Middle 対策)して、
> 長編でも確定事実・伏線・キャラ状態が執筆プロンプトに保たれることを保証する。
>
> **根拠**: Packer et al. 2023 (MemGPT, 階層記憶) / Wang et al. 2023 (RecurrentGPT, 逐次更新) /
> Liu et al. 2023 (Lost in the Middle, 両端バイアス) / Adams et al. 2023 (Chain-of-Density, 高密度要約)
>
> **原則**:
> - 既存挙動はフィーチャーフラグで完全後方互換 (**flag off で出力が現行とバイト単位で同一**)
> - 各ステップは「実装 + 完了条件テスト」で完結。既存テスト全緑を維持
> - ハードコード禁止 (`tests/regression/test_no_hardcoded_thresholds.py` の思想を継承)
> - LLM 呼び出し増は明示的に予算内であることをテストで保証
>
> **前提事実(コード調査済み、2026-11-10 時点)**:
> - 生成: `src/agents/writing/episode_writer.py:617-660` `_persist_episode_digest` →
>   `src/engine/context_compression/digest_service.py:25-107` (`generate_episode_digest`, 100〜150字, 本文先頭2500字から)
> - 永続化: `src/backend/database/models_digest.py` `episode_digests` (book_id, episode_num, **branch_id なし**) /
>   Alembic 最新は `0034` → 新規は **0035**
> - 消費: `src/engine/episode_context.py:289-435` `_build_layer2_summary`
>   (`LAYER2_MAX_CHARS=4000`, `RECENT_FULL_DIGEST_EPISODES=10`, `PRESERVE_INITIAL_EPISODES=2`,
>    history/foreshadowing 50:50 分割, 話数>10 で中間を省略マーカー化 :332-341)
> - 配線: `context_builder_agent.py:265` → `context["three_layer_context"]` →
>   `prompt_composer.py:132/431` `_format_three_layer_context` → `prompts/manager.py:710` →
>   `prompts/templates/narrative/final_writing_prompt.j2:40-42` (**プロンプト中央に配置**)
> - `Chapter` に巻/章カラムなし。`src/engine/pipeline_base.py:74` `volume_index` はランタイムカウンタのみ
> - **注意**: `src/engine/context_compression/rolling_memory.py` `RollingMemoryBuilder` は
>   本番から未使用(テストのみ)。本計画では触らず、実経路 `EpisodeContextBuilder` を対象にする

---

## 仕様サマリ (目標状態)

| 項目 | 現行 | 改修後 |
|---|---|---|
| Layer2 の構成 | flat な1話要約リスト + 中間省略マーカー | **巻要約(全巻) > 章要約(現在巻) > 直近話ダイジェスト(現在章+最初2話)** |
| 中盤の事実 | 話数>10 で省略され**永久喪失** | 章要約に圧縮され**保持** |
| 重要情報の位置 | プロンプト中央 (`final_writing_prompt.j2:40`) | **先頭(必守ブロック)+末尾(再確認ブロック)** の両端 |
| 要約密度 | 1 pass、100字固定 | rollup は Chain-of-Density 型 2 pass (抽出→圧縮) |
| ロールアップ生成 | なし | 章境界(+1 LLM call/10話)・巻境界(+1/50話)で冪等生成 |
| flag off 時 | - | **現行出力と完全同一** (characterization test で保証) |

---

## 全体マップ

```
Phase 0: ベースライン固定と設定基盤      (Steps  1- 3)
Phase 1: ロールアップ基盤 (DB/生成/配線)  (Steps  4- 9)
Phase 2: Layer2 階層組立                  (Steps 10-14)
Phase 3: 両端配置 (Lost in the Middle)   (Steps 15-19)
Phase 4: Chain-of-Density 高密度化        (Steps 20-22)
Phase 5: 統合検証と段階リリース           (Steps 23-27)
```

---

## Phase 0: ベースライン固定と設定基盤

### Step 1: 実経路トークン安定性の characterization テスト追加

- **背景**: `tests/perf/test_long_form_token_stability.py` は **本番未使用の `RollingMemoryBuilder`** のみを検証しており、実経路 `EpisodeContextBuilder` の長編安定性は未カバー。
- **実装**: テスト追加のみ(本番コード変更なし)。
  - `tests/perf/test_long_form_token_stability.py` に `EpisodeContextBuilder` 経路のケースを追加:
    1〜100話のモック DB(`Chapter` 100件 + `episode_digests` 100件)で `_build_layer2_summary` を毎話実行し、`layer2_chars ≤ LAYER2_MAX_CHARS` が全話で成立することを検証。
  - 中間省略マーカーが10話超で発生すること(現行挙動の固定)。
- **変更ファイル**: `tests/perf/test_long_form_token_stability.py`
- **完了条件**: 上記テストが現行コードで緑。**ここが以後のリグレッション基準線。**

### Step 2: プロンプト黄金スナップショット (flag off 不変性の基盤)

- **実装**: `tests/regression/test_hierarchical_memory_golden.py` を新設。
  - 固定フィクスチャ(キャラ3名・過去20話のdigest・未回収伏線2本・直前話本文)で
    `compose_writing_prompt` を実行し、出力全文を golden ファイル
    (`tests/regression/golden/writing_prompt_baseline.txt`) と比較。
  - 以後の全 Phase で、**新フラグが全て off の場合のみ**この golden と一致することを必須条件とする。
- **変更ファイル**: `tests/regression/test_hierarchical_memory_golden.py` + golden ファイル
- **完了条件**: 現行コードで緑(ベースライン確定)。

### Step 3: 設定モジュール新設とハードコード防止ゲート拡張

- **実装**: `src/engine/context_compression/rollup_config.py` を新設。

  | 設定 | env | 既定 | 意味 |
  |---|---|---|---|
  | `rollup_enabled` | `ENABLE_DIGEST_ROLLUP` | `0` (off) | ロールアップ全体の ON/OFF |
  | `episodes_per_block` | `DIGEST_EPISODES_PER_BLOCK` | `10` | 章(ブロック)境界 |
  | `blocks_per_volume` | `DIGEST_BLOCKS_PER_VOLUME` | `5` | 巻境界 (50話/巻) |
  | `pinned_edges_enabled` | `ENABLE_PINNED_FACTS_EDGES` | `0` | 両端配置 ON/OFF |
  | `cod_rounds` | `DIGEST_COD_ROUNDS` | `1` | 要約パス数 (1=現行, 2=CuD) |
  | `block_digest_chars` | `DIGEST_BLOCK_MAX_CHARS` | `300` | 章要約上限 |
  | `volume_digest_chars` | `DIGEST_VOLUME_MAX_CHARS` | `800` | 巻要約上限 |

  すべて `os.getenv` 経由の dataclass。**リテラル禁止**。
- **変更ファイル**: `rollup_config.py`(新規), `tests/regression/test_no_hardcoded_thresholds.py` の
  `TARGET_FILES` に `src/engine/context_compression/rollup_config.py` と
  `src/engine/episode_context.py` を追加し、数字リテラル出現を禁止(定数宣言行のみ許可)。
- **完了条件**: 設定の単体テスト(`tests/unit/engine/context_compression/test_rollup_config.py`: 既定値・env 上書き・不正値フォールバック)+ 既存ハードコード防止テスト緑。

---

## Phase 1: ロールアップ基盤

### Step 4: Alembic migration 0035 — `digest_rollups` テーブル

- **スキーマ**:

  ```sql
  digest_rollups (
    id            INTEGER PK,
    book_id       INTEGER FK books.id ON DELETE CASCADE NOT NULL,
    level         TEXT NOT NULL,          -- 'block' | 'volume'
    start_ep      INTEGER NOT NULL,
    end_ep        INTEGER NOT NULL,
    digest_text   TEXT NOT NULL,
    stale_at      TIMESTAMP NULL,         -- メンバdigest更新で失効 (Step 14)
    created_at    TIMESTAMP NOT NULL,
    updated_at    TIMESTAMP NOT NULL,
    UNIQUE (book_id, level, start_ep, end_ep)
  )
  ```
- **変更ファイル**: `src/backend/alembic/versions/0035_digest_rollups.py`
  (up/down 対。既存 `0031_episode_digests.py` を雛形にする。FK 閉包は
  `tests/e2e/test_v53_long_form_wiring_e2e.py:_tables_with_fk_closure` 方式で SQLite でも成り立たせる)
- **完了条件**: `alembic upgrade head / downgrade 0034` の往復テスト
  (`tests/regression/test_alembic_env_isolation.py` と同方式で追加)。

### Step 5: ORM モデルとリポジトリ

- **実装**:
  - `src/backend/database/models_rollup.py` — `DigestRollupModel` (上記スキーマに忠実に)。
  - `src/engine/context_compression/rollup_repository.py` — `DigestRollupRepository`:
    - `upsert_rollup(...)` (UNIQUE キーで冪等)
    - `get_rollups(book_id, level)` (start_ep 昇順)
    - `find_stale(book_id, current_ep)`
  - 既存 `EpisodeDigestRepository` (`digest_service.py:110-175`) のスタイル(AsyncSession 注入・`flush()`)に合わせる。
- **完了条件**: `tests/unit/engine/context_compression/test_rollup_repository.py`
  (upsert 冪等 = 同キー2回で1行 / 異レベル混在可 / cascade 削除)。モック `AsyncSession` は
  `tests/unit/services/test_episode_context_3layer.py` の fixture 方式を踏襲。

### Step 6: RollupGenerator (章/巻要約の生成)

- **実装**: `src/engine/context_compression/rollup_generator.py`
  - `should_generate_block(ep_num, cfg)` — `ep_num % episodes_per_block == 0`
  - `should_generate_volume(ep_num, cfg)` — 境界かつ `ep_num % (block × volume) == 0`
  - `generate_block_rollup(book_id, ep_range, member_digests, llm)` — メンバの1話digest(≤150字×10=最大1500字)を入力に**章要約**(≤300字)を生成
  - `generate_volume_rollup(...)` — メンバ章 rollup から**巻要約**(≤800字)
  - モデルは `_resolve_digest_llm` (`episode_writer.py:72-`) と同様 **tier1 軽量モデル**
  - **fail-open**: LLM 失敗時はロールアップ行を作らず warning ログのみ(執筆は継続)。空リスト・`None` LLM でも例外を出さない
  - 長さ超過時は既存 `digest_service.py:102-105` と同じクランプ方式で切詰め
- **完了条件**: `tests/unit/engine/context_compression/test_rollup_generator.py`
  (境界判定の表駆動 / tier1 解決のモック / LLM 失敗で例外なし / 文字数クランプ)。

### Step 7: ロールアップ生成の冪等性・タイミングテスト (純粋ロジック)

- **実装**: Step 6 の関数群に対して **状態遷移シミュレーション** テストを追加。
  - 1〜12話を順に digest 保存 → 章rollup が ep10 で1件、ep12 で増えない
  - 同一 ep を再保存 → rollup 重複なし (Step 5 upsert 保証の結合確認)
- **変更ファイル**: 同 Step 6 テストファイルに追加。
- **完了条件**: 上記が green。

### Step 8: `_persist_episode_digest` への配線 (flag-gated)

- **実装**: `src/agents/writing/episode_writer.py:617-660` に既存 try/except 内で追加:
  1. 既存の `EpisodeDigestService.summarize_and_save` (現行維持)
  2. `rollup_enabled` なら `should_generate_*` 判定 → 該当する rollup を生成・upsert
  3. 生成後、同巻の **stale rollup** を再生成 (Step 14 の基盤、今回は呼び口だけ用意)
  - `ENABLE_EPISODE_DIGEST=0` なら rollup も生成しない (上位フラグの優先)
- **変更ファイル**: `episode_writer.py`
- **完了条件**:
  - **Step 9 の配線リグレッションテスト** green
  - 既存 `tests/e2e/test_v53_long_form_wiring_e2e.py` (digest永続化の検証) が flag off で従来通り green

### Step 9: 配線リグレッションテスト (AST 到達性)

- **実装**: `tests/regression/test_hierarchical_memory_wiring.py` を新設。
  既存 `test_v53_wiring_reachability.py` の AST 手法を踏襲し、以下を**実行時静的検証**:
  1. `_persist_episode_digest` の呼び出しグラフに `rollup_generator` への到達が存在 (flag 条件付きでも可)
  2. `rollup_config` の env 読み取りが `rollup_config.py` 以外の場所に存在しない (SSOT)
  3. `RollingMemoryBuilder` が本番モジュールから import されていないこと (死蔵コード混入防止)
  4. `episode_writer.py` が rollup 生成を `try/except` で握りつぶさず warning を出す構造であること
- **完了条件**: 上記4項目 green。**以後このファイルは全 Phase の完了条件に含める。**

---

## Phase 2: Layer2 階層組立

### Step 10: `_build_layer2_hierarchical` の実装

- **実装**: `src/engine/episode_context.py` に追加(既存 `_build_layer2_summary` は**残す**)。
  新ルーチンの組立順と優先クランプ:

  ```
  【巻の確定事実】          ← 全巻 rollup (level=volume, 最大 K 件)      優先度 1
  【章の確定事実】          ← 現在巻の rollup (level=block)              優先度 2
  【直近の確定事実】        ← 現在章の1話digest + 最初2話 (現行窓の継承)  優先度 4
  【未回収伏線一覧】        ← 現行ロジックをそのまま維持                  優先度 3
  ```

  - history 側予算(`HISTORY_BUDGET_RATIO=0.5`)内で優先度 1→2→4 の順にクランプ。
    伏線側(優先度3)の分離と期限超過最優先ソート(:373-377)は**現行コードを無改変で再利用**。
  - rollup テキストの整形は `_format_three_layer_context` (`prompt_composer.py:29-60`) の
    `【Layer2: ...】` ヘッダを維持したまま差し替え(配線側の変更を最小化)。
- **完了条件**: Step 11 のフォールバックテスト green。

### Step 11: legacy フォールバック (完全後方互換)

- **実装**: 次のいずれかのとき **現行 `_build_layer2_summary` にフォールバック**:
  - `rollup_enabled == False`
  - rollup 0件 (既存作品 / 生成途中)
  - DB 異常 (取得例外は現行 `_load_episode_digests` :263-287 と同じ fail-soft)
- **変更ファイル**: `episode_context.py`
- **完了条件**: **Step 2 golden スナップショットが flag off で引き続き完全一致** (最重要)。

### Step 12: 層構造・優先クランプ・フォールバックの単体テスト

- **実装**: `tests/unit/services/test_episode_context_hierarchy.py` を新設:
  1. rollup あり: 巻要約→章要約→直近digest の順でテキストに現れる
  2. 予算超過: 巻要約が最優先で残り、直近digest から削られる (優先度順の実証)
  3. rollup なし: 現行 `_build_layer2_summary` の出力と**完全一致**
  4. 伏線の期限超過最優先ソートが階層化後も維持されること
  5. `foreshadowing_omitted` / `foreshadowing_overdue` の統計フィールドが消えないこと
     (現行 `episode_context.py:431-434` の戻り値契約を維持)
- **完了条件**: 上記5件 green。

### Step 13: 実経路ロングフォーム性能テストの拡張

- **実装**: `tests/perf/test_long_form_token_stability.py` に追加:
  - `rollup_enabled=True` で 1〜100話: `layer2_chars ≤ LAYER2_MAX_CHARS` 全話成立
  - 100話時点のプロンプト合計文字数が flag off 時と比較して **+10% 以内** (予算破壊の予防線)
  - 実行時間: 100話の Layer2 組立が 100ms/話以内 (rollup は DB 読み取りのみで LLM 不要)
- **完了条件**: 上記 green。劣化時は Step 10 のクランプ定数を見直す。

### Step 14: retake (再生成) への追従 — stale rollup 再生成

- **背景**: `Chapter` は `branch_id` を持つが `episode_digests` は持たず、リテイクで digest が
  更新されると既存 rollup が古くなる。
- **実装**: Step 8 で用意した呼び口を完成:
  1. digest upsert 時、その話が属する章/巻 rollup の `stale_at` を設定
  2. 次の digest 保存時に `find_stale` で該当 rollup を**メンバ digest から再生成** (tier1, +1 call)
  3. 再生成失敗時は stale を保持 (次回再試行)。執筆は止めない
- **変更ファイル**: `digest_service.py` (stale 設定フック) / `rollup_repository.py` / `rollup_generator.py`
- **完了条件**: `tests/unit/engine/context_compression/test_rollup_staleness.py`
  (ep3 を再保存 → 章rollup が stale → 次回保存で再生成 → stale 解消 / 再生成失敗で stale 維持)。

---

## Phase 3: 両端配置 (Lost in the Middle 対策)

### Step 15: pinned facts の生成 (LLM 0 回)

- **実装**: `src/engine/context_compression/pinned_facts.py` を新設。
  既存データの文字列整形のみで以下を抽出:
  - **必守事実**: 期限超過伏線 + 本話契約伏線 (既存 `contract_foreshadowings` / 期限超過フラグを再利用)
  - **不可逆な状態変化**: 前話 digest から死亡・所持品入手・拠点移動を示す文 (digest が既にあるので LLM 不要)
  - 出力: `{"head": str, "tail": str}` (head = 箇条書き、tail = チェックリスト文体)
  - 上限は `pinned_max_chars` (既定 300字/head, 300字/tail)。超過時は期限超過→契約→状態変化の順で残す
- **完了条件**: `tests/unit/engine/context_compression/test_pinned_facts.py`
  (抽出順・上限クランプ・digest なしでも空文字を返して例外なし)。

### Step 16: 配線 — context → composer → manager (2 経路)

- **実装**:
  - `context_builder_agent.py` (~:489 の artifacts 辞書) に `pinned_facts` を追加
  - `prompt_composer.py`:
    - `compose_writing_prompt` (:66-) と **`compose_scene_prompt` (:431 側) の両方**で
      `pinned_head` / `pinned_tail` をキーワード引数として `build_final_writing_prompt` へ渡す
  - `prompts/manager.py:710` `build_final_writing_prompt`: kwargs から受け取り context 辞書へ
    (`char_static_ctx` 等と同じパターン。**シグネチャは `**kwargs` 済みなので破壊的変更なし**)
  - `pinned_edges_enabled=False` なら両方空文字 (現行出力と同一)
- **変更ファイル**: `context_builder_agent.py`, `prompt_composer.py`, `prompts/manager.py`
- **完了条件**: Step 9 の配線テストに項目追加 (`compose_writing_prompt` と `compose_scene_prompt` の
  両方から `pinned_*` が到達すること) + golden (off 時) 維持。

### Step 17: テンプレート — 先頭・末尾ブロックの追加

- **実装**: `prompts/templates/narrative/final_writing_prompt.j2`
  - **先頭**: thought_process 指示の直後に
    ```jinja
    {% if pinned_head %}
    【最重要の確定事実・必守事項】(執筆前に必ず遵守)
    {{ pinned_head }}
    {% endif %}
    ```
  - **末尾**: `■ 目標文字数` の直後・`--- 出力形式 ---` の直前に
    ```jinja
    {% if pinned_tail %}
    【執筆直前の再確認】(以下に矛盾する描写を書かないこと)
    {{ pinned_tail }}
    {% endif %}
    ```
  - 既存ブロック(char_static / three_layer / rag)の**位置は一切動かさない** (回帰リスク最小化)。
    両端に *追加* するだけにする。
- **変更ファイル**: `final_writing_prompt.j2`
- **完了条件**: Step 18 の位置テスト green。

### Step 18: 両端配置のリグレッションテスト (位置不変条件)

- **実装**: `tests/unit/agents/test_pinned_facts_placement.py` を新設。
  flag on/off 両方のプロンプト文字列に対し **インデックス順序アサーション**:
  1. off 時: `pinned_head` ブロックが現れない (`【最重要の確定事実` not in prompt)
  2. on 時: `prompt.index("【最重要の確定事実") < prompt.index("【作品文脈】")` (先頭側)
  3. on 時: `prompt.index("【執筆直前の再確認】") > prompt.index("■ 目標文字数")` かつ
     `< prompt.index("--- 出力形式 ---")` (末尾側・出力指示の前)
  4. 既存3層ブロックの相対順序 (char_static → prev → foreshadowing → three_layer → rag) が
     変更前後で不変であること (**既存構造のリグレッション防止**)
- **完了条件**: 上記4件 green。

### Step 19: E2E — 実プロンプトへの両端反映

- **実装**: `tests/e2e/test_hierarchical_memory_e2e.py` を新設。
  既存 `test_v53_long_form_wiring_e2e.py` の実 SQLite (aiosqlite) + モック LLM 方式を踏襲:
  1. 11話分の章を書き込み、11話目の執筆プロンプトを構築
  2. **章 rollup 1件 (ep10) が Layer2 に含まれる**ことを確認 (Step 1-2 の前提: 本話は11話)
  3. pinned_head がプロンプト先頭側、pinned_tail が末尾側に存在
  4. flag 全 off で同じシナリオ → 現行 golden と同等の構造 (中間省略マーカーが出現)
- **完了条件**: 上記 green。

---

## Phase 4: Chain-of-Density 高密度化

### Step 20: rollup 生成の 2 pass 化 (Cod)

- **実装**: `rollup_generator.py` に `DIGEST_COD_ROUNDS >= 2` 時のパス追加:
  - **Pass 1 (抽出)**: メンバ digest から客観的事実を無制限リスト化 (重複統合)
  - **Pass 2 (圧縮)**: 目標字数内で「各文が新事実を追加する」よう再構成 (Adams et al. 2023 の原則:
    冗長削除・情報量維持・固定長)
  - `cod_rounds=1` なら**現行の1 pass と完全同一** (off 相当)
  - ログに pass 数と入出力字数を記録 (コスト検証用)
- **完了条件**: `tests/unit/engine/context_compression/test_rollup_cod.py`
  (rounds=1 で出力が現行パスと同一 / rounds=2 で字数内・例外なし / モック LLM が2回呼ばれる)。

### Step 21: episode digest の Cod はオプション (既定 off)

- **実装**: `digest_service.py` の `generate_episode_digest` に `cod_rounds` 引数を追加
  (既定 1 = 現行挙動)。**既定 off のまま**とし、コスト (+1 call/話) を払う価値があるかは
  Step 26 の A/B で判断する。
- **完了条件**: 現行呼び出し元 (`episode_writer.py`, `llm_voter.py:112` の契約) が
  引数なしで従来通り動くこと。既存 digest テスト green。

### Step 22: 事実密度メトリクスのテスト

- **実装**: `tests/unit/engine/context_compression/test_fact_density.py`
  - 密度 = **固有事実エントリ数 / 字数**。LLM 不要の評価器:
    事実エントリ = 行分割後の箇条書き行数 + 固有名詞(カタカナ/漢字固有名詞)の出現種類数
  - 合成フィクスチャ(10話digest)で:章 rollup (300字) の密度 ≥ 任意の1話digest (100字) の密度 ×0.8
    (圧縮でも情報密度が著しく落ちないこと)
  - Cod rounds=2 が rounds=1 より密度が**同等以上**であること (回帰防止)
- **完了条件**: 上記 green。

---

## Phase 5: 統合検証と段階リリース

### Step 23: E2E 拡張 — 連続執筆・リテイク・巻境界

- **実装**: `tests/e2e/test_hierarchical_memory_e2e.py` に追加:
  1. **50話連続** (巻境界) → 巻 rollup が1件生成され Layer2 先頭に現れる
  2. **retake**: ep3 の digest を更新 → 章 rollup が stale → 次回保存で再生成 (Step 14)
  3. LLM モックが rollup 生成で想定外の呼び出しをしないこと (**呼び出し回数の契約**)
     - 1〜10話: rollup 0回 / 10話目: +1 (章) / 50話目: +1 (巻) / それ以外: 0
- **完了条件**: 上記 green。

### Step 24: LLM コスト予算テストの更新

- **実装**: 既存 `tests/perf/test_v6_llm_call_budget.py` を確認し、rollup の呼び出しを
  **予算項目として明示追加**:
  - rollup off: 従来の呼び出し回数と**完全同一**であること (回帰防止)
  - rollup on: 10話ごとに +1 call、50話ごとに +1 call を超えないこと (上限契約)
  - tier1 モデルが使われること (tier2/3 への昇格をテストで禁止)
- **完了条件**: 両 flag 状態で green。

### Step 25: 事実保持リグレッションテスト (本計画の価値証明)

- **実装**: `tests/regression/test_long_form_fact_retention.py` を新設 — **提案4 の核心を直接検証**:
  1. 第3話の digest に識別可能な事実を1件埋め込む (例: 「第3話: アルスは龍の鱗を入手した」)
  2. 1〜50話を生成し、50話目の Layer2 コンテキストを構築
  3. **rollup off**: 現行仕様どおり中間省略マーカーで事実が**消える**ことを確認
     (現行挙動の characterization = 提案4 の問題の実証)
  4. **rollup on**: 事実が**章要約経由で保持される**ことを確認 (改善の実証)
  5. 両 flag で Layer2 が `LAYER2_MAX_CHARS` 内に収まる
- **完了条件**: 上記 green。**このテストが本計画の完了宣言 (Definition of Done)。**

### Step 26: A/B 計測とドキュメント更新

- **実装**:
  - `benchmarks/hierarchical_memory_bench.py` (既存 `benchmarks/` 方式の合成ベンチ):
    - 指標: 事実保持率 (Step 25 の拡張, 20件の埋め込み事実) / Layer2 文字数 / 100話の LLM コスト
    - flag off vs on の比較表を出力
  - `docs/compression_module.md` に階層メモリ節を追記、`CHANGELOG.md` に追加
  - `README.md` の「3層ローリング記憶」記述を階層版に更新
- **完了条件**: ベンチが両 flag で実行でき、`docs/` と `CHANGELOG.md` が更新されている。

### Step 27: 段階リリース (既定値の切り替え)

- **手順** (各段階で1週間バーンし、監査スコアの劣化を監視):
  1. **Week 1**: `ENABLE_DIGEST_ROLLUP=1` (生成のみ, Layer2 は現行 = 参照なし)
     → rollup の生成失敗率・コストが予算内か確認 (`monitoring/alert_rules.yml` に
     `rollup_generation_failure_ratio > 0.1` のアラート追加)
  2. **Week 2**: `ENABLE_PINNED_FACTS_EDGES=1`
     → 位置テスト + 人手サニティチェック (プロンプト可読性)
  3. **Week 3**: `ENABLE_DIGEST_ROLLUP=1` で Layer2 階層組立を有効化 (本体 ON)
     → `tests/perf/test_v6_audit_failure_rate.py` の監査不合格率が +2pt 以内か確認
  4. **Week 4**: `DIGEST_COD_ROUNDS=2` の A/B 結果を見て採否判断 (Step 21 の据え置き解除)
  5. 各段階のロールバック = 該当 env を 0 に戻すだけ (DB・スキーマは後方互換のため不要)
- **完了条件**: 3 週間の監査スコア・コスト・失敗率が許容内。`plans/` の本ファイルに結果を追記。

---

## テスト計画まとめ (リグレッション防止の全体像)

| # | テストファイル | 種別 | 守るもの | Step |
|---|---|---|---|---|
| T1 | `tests/perf/test_long_form_token_stability.py` (拡張) | perf | 実経路 `EpisodeContextBuilder` の文字数不変性 | 1, 13 |
| T2 | `tests/regression/test_hierarchical_memory_golden.py` | golden | **flag off で現行プロンプトとバイト同一** | 2, 11 |
| T3 | `tests/unit/engine/context_compression/test_rollup_config.py` | unit | 設定 SSOT・env 上書き・既定値 | 3 |
| T4 | `tests/regression/test_no_hardcoded_thresholds.py` (拡張) | regression | マジックナンバー再導入の禁止 | 3, 10, 15 |
| T5 | migration 往復テスト (alembic) | integration | 0035 の up/down 安全性 | 4 |
| T6 | `test_rollup_repository.py` | unit | upsert 冪等・UNIQUE・cascade | 5 |
| T7 | `test_rollup_generator.py` | unit | 境界判定・tier1・fail-open・クランプ | 6, 7 |
| T8 | `tests/e2e/test_v53_long_form_wiring_e2e.py` (既存維持) | e2e | digest 永続化の現行経路が不変 | 8 |
| T9 | `tests/regression/test_hierarchical_memory_wiring.py` | regression | AST 到達性: 配線・SSOT・死蔵コード混入防止 | 9, 16 |
| T10 | `test_episode_context_hierarchy.py` | unit | 層順序・優先クランプ・legacy 完全同一 | 12 |
| T11 | `test_rollup_staleness.py` | unit | retake 追従 (stale→再生成→解消) | 14 |
| T12 | `test_pinned_facts.py` | unit | 両端事実の抽出順・上限・fail-soft | 15 |
| T13 | `tests/unit/agents/test_pinned_facts_placement.py` | regression | **プロンプト内位置の不変条件** (両端配置+既存順序維持) | 18 |
| T14 | `tests/e2e/test_hierarchical_memory_e2e.py` | e2e | rollup/pinned が実プロンプトへ届く・呼び出し回数契約 | 19, 23 |
| T15 | `test_rollup_cod.py` | unit | Cod rounds=1 が現行同一・rounds=2 の呼び出し回数 | 20 |
| T16 | `test_fact_density.py` | unit | 圧縮後の情報密度が落ちない | 22 |
| T17 | `tests/perf/test_v6_llm_call_budget.py` (拡張) | perf | コスト予算: +1/10話の上限・tier1 固定 | 24 |
| T18 | `tests/regression/test_long_form_fact_retention.py` | regression | **中盤の事実保持 (提案4 の価値そのもの)** | 25 |

**共通ガード**: 全 Phase の完了条件には「既存テスト全緑 + T2 (golden) 維持 + T9 (配線) green」を含める。

---

## リスクと対策

| リスク | 影響 | 対策 |
|---|---|---|
| プロンプト長の増加で Lost in the Middle 悪化 | 本文品質低下 | T1 の +10% 上限 / 両端配置で重要情報のみ先頭末尾 / 中央の既存ブロックは不変 |
| rollup 生成の LLM コスト | 費用増 | +1 call/10話 の上限を T17 で強制 / tier1 固定 / `ENABLE_EPISODE_DIGEST=0` で上位遮断 |
| retake で rollup が陳腐化 | 間違った要約を参照 | stale マーカー+次回保存時再生成 (Step 14) / 失敗時は stale 維持で旧要約参照 |
| 既存作品で rollup が無い | Layer2 空になる | legacy フォールバック (Step 11) + golden 不変 (T2) |
| `episode_digests` に `branch_id` が無い (既存制約) | 分岐作品で digest 混在 | **本計画の範囲外**と明記。既存の挙動を維持し、課題として別タスク化 (リスク明文化) |
| 死蔵の `RollingMemoryBuilder` と二重実装 | 保守混乱 | 触らない + T9 で本番混入を禁止。完全削除は別計画 |
| Cod (rounds=2) の品質が逆に低下 | 要約の歪み | 既定 off (Step 21) + T16 密度メトリクス + Step 27 Week4 の A/B 判断 |
| マイグレーション失敗 | デプロイ不能 | 0035 の up/down 往復テスト (T5) + `0031` 雛形踏襲 |

## Definition of Done

1. **T18 (事実保持テスト)** が green — 中盤の事実が rollup on で Layer2 に残ることを実証
2. **T2 (golden)** が flag off で完全一致 — 既存利用者への影響ゼロを実証
3. T1 (トークン不変) + T17 (コスト予算) + T13 (位置不変) が green
4. 既存テスト全体が緑 (`make test` / CI の coverage gate 60% 維持)
5. `docs/compression_module.md` + `CHANGELOG.md` 更新済み、Step 27 の段階リリース結果を本ファイルに追記
