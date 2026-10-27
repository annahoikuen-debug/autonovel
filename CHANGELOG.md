# Changelog

本プロジェクトの変更履歴。[Semantic Versioning](https://semver.org/lang/ja/) に準拠。

## [Unreleased] - 2026-10-02 - 公開前ハードニング（セキュリティ・データ整合性）

公開前の多角監査で見つかった欠陥をまとめて修正した。個別（約 60 件）の内訳ではなく、
影響領域ごとにまとめる。破壊的変更（開発環境での認証必須化）を含む。

### セキュリティ

- IDOR（他者の作品への越境アクセス）の全面的な遮断
    - 認証が無かった／所有権が未検証だったルーティング（`novel` / `misc` / `books` /
      `graph` / `orchestrated` / `branches` の play 系 / `multimedia` /
      `illustrations` / `commercial` など）に `get_current_user` と
      `verify_book_ownership` を追加。`session_id` / `task_id` / `correlation_id` /
      `asset_id` のような推測可能な ID 経由の経路も所有者を辿って検証し、
      所有者が記録されていないタスクは fail-closed で管理者に限定した。
    - 所有者 `NULL` の作品を非管理者に公開していた判定も修正（seed で投入される
      `Book(id=1)` が誰でも読み書きできる状態だった）。
  - Stripe webhook の署名検証
    - `STRIPE_WEBHOOK_SECRET` が空というだけで署名検証をスキップしていたため、
      `APP_ENV` の既定が `development` である以上ほぼ全環境で webhook を偽装し
      クレジットを付与できた。`ALLOW_UNSIGNED_WEBHOOKS`（既定 `false`）が明示的に
      `true` のときだけ省略するようにした。
  - API キーとペイロードの URL 漏えい
    - `GET /easy_mode/generate/stream` の base64 `payload` クエリパラメータは
      `llm_config.api_key` / `base_url` をアクセスログ・ブラウザ履歴に平文で残し、
      SSRF の起点にもなっていた。`400` で明示的に拒否し、入力はリクエストボディ
      か個別のクエリフィールドに移した。
    - 未認証の manuscript エクスポートと、クエリ文字列での API キー受理を廃止。
  - JWT / 起動時ガード
    - `.env.example` に載っている `JWT_SECRET_KEY` / `SECRET_KEY` の例示値を
      本番起動時に拒否するようにした（管理者トークンの偽造が可能だった）。
    - `CORS_ORIGINS=*` を `APP_ENV=production` で起動時に拒否。
    - `docker-compose.yml` の `AUTH_DISABLED=true` を撤去し、開発用バックエンドの
      ポートを Loopback 限定（`127.0.0.1:8200:8200`）にバインド。
    - 開発環境でもトークンが必要になったため、README のセットアップ手順を
      登録／ログイン／`Authorization: Bearer` の手順に更新した。

### データ整合性（無言で壊れていた経路）

  - 課金プランの無言降格 — Stripe webhook が受信 price id を `"unknown"` で
    上書きしており、全有料利用者が `plan_tier=free` になっていた。
  - 成功／失敗の反転 — `system.py` の再計算サマリが 0 件（失敗）を 1 件
    （成功）として計上していた。
  - 品質スコアが常に F — plot 品質軸の重み集合と book 次元の重み集合に
    共通要素が無く、重み合計 0 → `overall` が常に 0 だった。
  - 作品横断の上書き — 一部のリポジトリが `branch_id` のみで絞り込んでおり、
    一意制約 `(book_id, branch_id, ep_num)` と食い違い別作品の行を上書きしていた。
  - スキーマ生成の漏れ — `create_all` が 2 モデルモジュールしか import せず
    6 テーブルが生成されず、その結果 billing 経路の初回 INSERT が死在していた。
  - 時刻の凍結 — `created_at` などの default 値が import 時に評価され、
    プロセス起動時刻で固定されていた。
  - 物語生成の上書き — CSP 変換が 40 個の作者済みビートを placeholder で
    上書きしていた。
  - 潜在テキストルールの飢餓 — `final` フラグが「チェーン全体を停止」だったため、
    優先度 50/60 のルールが拡張ルール（80-115）の適用を妨げていた。
    「同一優先度以下のみを停止する」定義に改めた。
  - 発話の消失 — 潜在テキストの一部ルールが舞台指示への置換でキャラクターの
    発話そのものを削除していた。発話を保持したまま前置きする形に修正。

### 信頼性・依存関係

  - リトライの挙動是正 — サーバー指定の `Retry-After` が局所バックオフ上限
    （既定 2 秒）に丸められ、即座に再 429 していた。サーバー指定値には専用の
    上限を、導出バックオフには従来の上限を適用するよう分離。
  - 恒久的な 4xx のリトライ — 408 / 409 / 429 を除く 4xx を一時エラー扱いにして
    いたため、リトライしても必ず失敗する処理を 3 回回していた。
  - ストリーミングの計測漏れ — 早期終了や上流例外で計測が飛んでいた
    `stream_text` を `try/finally` 化し、`system_prompt` も計測対象に含めた。
  - 未導入の必須依存と壊れたビルド定義 — `ortools` の宣言漏れ、
    `COPY database/`（存在しないディレクトリ）の指定、`docker/postgres/Dockerfile`
    の誤った build-context パスを修正し、コンテナ image が実際にビルドできる
    状態に復元した。
  - フロントエンドのビルド阻断 — 欠落していた `indexedDbClient` の実装と
    `QueryClientProvider` の未配置を補い、`tsc` / `vite build` を通した。
  - その他の修正 — 商用ルートの同期 `Session` を非同期に統一、
    `RateLimitMiddleware` が 429 ではなく 500 を返していた問題、
    非同期関数の未 await によるグラフ無音更新、SSE ストリームの所有者検証漏れ。

## [6.0.0] - 2026-09-28 - V6 コスト・レイテンシ最適化＋v5.3 配線の是正

「v5.3 で計画した長編機構が、実際には配線が未接続だった」という欠陥を是正し、
同時に v6 のコスト最適化（tier ルーティング・ダイジェスト cost 制御）を実効化した。

### T6 是正計画（`plans/PLAN_T6_REMEDIATION_18STEPS.md`、2026-09-29）

上記の実装評価で残った欠陥の是正。**二重実行**と**無言化**が中心的な問題だった。

- **ダイジェスト生成の二重実行**（コスト実害）
  - `_post_episode_finalize` が `run()` と `write_beat_to_scene()` の両方から呼ばれ、
    既定経路（`use_beat_to_scene=True`）では**1話につき2回**走っていた。
    1話1回のブロッキング LLM 呼出のため、実コストが2倍になっていた。
    実行点を `run()` の1箇所に集約。
  - 回帰防止: `tests/unit/writing/test_episode_finalize_called_once.py`（4件）
- **警告ログの恒久的無言化**
  - `if hasattr(self, "logger"):` が25箇所あったが、`SkillAgent` には
    `self.logger` 属性が無く**常に False**。伏線回収・ダイジェスト永続化・
    セッション型不一致などの警告が一度も出力されていなかった。
    モジュールレベル `logger` へ置換（`context_builder_agent.py` には
    `logger` の定義自体が無く、置換後は `NameError` になるため追加）。
  - 回帰防止: `tests/unit/agents/test_logger_guards_regression.py`（5件）
- ** IllustrationAgent の後続チェーン断線**（K4）
  - `IllustrationAgent` は公開 API `run(request=...)` のために
    `SkillAgent.run(ctx)` を**非互換シグネチャで上書き**しており、
    そのままノード登録すると `TypeError` かつ `next_agent=None` で
    後続 `MarketingAgent` に到達しなかった。
    `execute(ctx)` を直接呼ぶ `_make_execute_node` を追加して連鎖を回復。
- **未知モデルのコストが無言で $0 になっていた**
  - `MODEL_PRICING` に無いモデルは黙って 0.0 を返しており、
    モデルルーティングを有効化すると**コスト計測が無言でゼロ化**していた。
    `resolve_pricing` / `UnknownModelPricingError` を追加し、
    tracker 側は後方互換のため 0 を返しつつ**1度だけ警告**する。
- **`update_chapter_content` の引数シグネチャ不整合**
  - 実シグネチャは `(branch_id, ep_num, content)` だが、
    `chapter.id` を `branch_id` に、`rewritten_text` を `ep_num` に渡しており
    `content` が欠落して**書き直しが TypeError で無言に失敗**していた（2箇所）。
- **`LocalPolisher` が計測 LLM をバイパス**
  - モジュールグローバル `call_llm_api` を直接呼ぶ同期メソッドで
    `tracked_adapter` を完全に迂回していた。`polish_with_llm()` を追加し、
    `AuditAgent.try_local_patch`（async 化）から注入 LLM を渡すようにした。
- **ダイジェスト永続化の失敗が話全体を落としていた**
  - 伏線回収側は隔離済みだったが、ダイジェスト側は例外が伝播していた。
    警告付きで隔離し、1話を丸ごと失うことを避免。
- **バージョンの自己矛盾**
  - `CHANGELOG` に `[6.0.0]` があるのに `pyproject.toml` / CLI / backend /
    frontend / docker-compose / README が `5.3.0` のままだった。**6.0.0 に統一**。
- **効果測定表の作成**（親計画 Step 36 の未達分）
  - `docs/STATUS.md` §5 に実測値と出典を記載。
    1話LLM呼出 **10回（目標 4-5 で未達）**、再執筆率 **100% → 11%**（実測比較）、
    監査レイテンシは**スタブ LLM では測定不能**（I/O待ちなし）と正直に明記。
    未計測項目は `未計測` と記載し、推測値を置いていない。
- **lint**
  - 純整形系（W291/W292/W293）**1,646 件を解消**。
  - F401（483件）は機械削除すると
    `src/narrative_balancer` の再エクスポートが壊れ **ImportError** になることが
    実測で判明したため、**意図的な import として残置**。
    残存数を `tests/regression/test_lint_budget.py` で上限固定し、
    再エクスポート Names が消えないことも固定した。

### 修正（v5.3 配線の未接続）

- **メタデータ指示テンプレートの JSON が不正**
  - `writing_metadata_instruction.j2` の
    `"action": "resolved または progressed または mentioned_only"` と
    `"word_count_estimate": 本文の推定文字数（整数）` は JSON リテラルとして無効。
    LLM がそのまま echo すると `WritingMetadata` 全体が `None` に化け、
    伏線回収の報告が全話ぶん失われていた。
    実 enum 値を1つだけ出力し、候補は注釈へ移動、推定文字数は整数例に置換。
- **背景（継続中）の未回収伏線がプロンプトから消えていた**
  - `final_writing_prompt.j2` の `{% if %}/{% elif %}` により
    契約伏線か背景伏線のどちらか一方しか描画されなかった。
    両方を描画できるように変更。
  - `prompts/manager.py` の `"background_foreshadowings": []` ハードコードを
    実供給に置換。契約伏線と重複排除し、直近20件へ上限、
    残りは「他N件あり（うち期限超過M件）」の1行サマリに圧縮。
- **`foreshadowing_ctx` が dead-letter だった**
  - `PromptComposer.compose_writing_prompt` が `context["foreshadowing_ctx"]` を
    渡さず RAG のみ使用していた。ctx を優先し、空のときだけ RAG へ
    フォールバックするよう変更。
  - `compose_scene_prompt`（Step 8 項目2 の未実施分）にも契約伏線と3層記憶を渡す。
- **Layer2 が予算の 5 倍に膨張していた**
  - `_build_layer2_summary` は未回収伏線セクションを予算クランプの**後**に連結していた
    （60話・伏線79本の条件で実測 21,149 字 / 予算 4,000 字）。
  - 予算を過去話要約／未回収伏線の 50/50 に分割し、両方をクランプ。
    期限超過を最優先（`target_episode` 昇順）、残りは1行サマリへ圧縮。
    期限超過の Signals は必ず保持。
  - 実測（200話・未回収150本）で **3,318 字**（従来 21,149 字 → 予算 4,000 字内）。
- **Layer2 のデータ源が `episode_digests` でなかった**
  - `episode_digests` を優先し、無ければ本文冒頭100字へフォールバック。
  - セッション解決の不一致（伏線側は `or repo.session`、ダイジェスト側は
    `artifacts.get("session")` のみ）を共通ヘルパー `_resolve_session` に統合。
- **伏線判定の例外隔離と KPI レポーター未接続**
  - `check_and_resolve` のループに per-item `try/except` を追加
    （1件の DB エラーで当該話全体が判定全滅していた）。
  - `report_planted` / `report_transition` / `report_rescheduled` を
    実呼び出し箇所に結線（`DbForeshadowingRepository.add` と
    `ForeshadowingService` の遷移・延期・回収放棄）。
  - `abandon()` の本番経路を新設。作品末尾で延期不能になった伏線を
    `abandoned` へ遷移させる（無かったため `collection_rate` が
    原理的に 1.0 / 0.0 しか取れなかった）。
  - `total_episodes` を `Book.target_eps` から解決して
    `check_and_resolve` に渡す（`max_episode` が常に `None` だった）。
  - 死んだ `kpi.terminal_statuses` を削除。
  - `datetime.utcnow()` → `datetime.now(timezone.utc)`（M17）。

### 追加

- **`ENABLE_EPISODE_DIGEST` フィーチャーフラグ**（既定 on）
  - ダイジェスト生成は1話につき1回のブロッキング LLM 呼出
    （入力 ≒2,636 字 / ≒1,318 token）を伴うため、無効化できるようにした。
  - ダイジェスト用モデルに tier1（`gemini-2.0-flash`）を割り当てる。
- **ダイジェスト cost の実測**（1話あたり）

  | 条件 | 実測 cost |
  |---|---:|
  | tier1（`gemini-2.0-flash`、v6.0.0 の既定） | **約 0.00013 USD** |
  | tier2（`claude-3-5-haiku`、従来相当） | 約 0.00108 USD |

  入力 2,636 字・出力 13 字の前提。tier 割り当ての効果はそのまま cost 差になる。
- **`web/demo/README_DEMO.md` を復元**
  - README がリンクしていたが実体が存在せず、
    `tests/regression/test_v5_version_consistency.py::test_documents_referenced_by_readme_exist`
    を失敗させていた。

### テスト

- `tests/contract/test_v53_prompt_contract.py`（新規、11 テスト）:
  メタデータ JSON の妥当性 / echo した `WritingMetadata` のパース /
  不正エントリ1件の隔離 / 契約・背景ブロックの同時描画 /
  背景の上限と省略サマリ / `foreshadowing_ctx` の到達 / 3層記憶の描画。
- `tests/e2e/test_v53_long_form_wiring_e2e.py`（新規、5 テスト）:
  モック LLM + 実 SQLite で `EpisodeWriter.run()` まで走らせ、
  伏線 `planted → resolved` / 契約伏線の最終プロンプト到達 /
  ダイジェスト1行永続化 / 3層記憶のプロンプト到達 /
  作品末尾での回収放棄を実経路で検証。

### 修正（テスト資産）

- `tests/perf/test_v6_audit_failure_rate.py` に残っていた
  `test_tmp_probe_for_baseline_script`（意図的に `assert False`）を削除。

## [5.3.0] - 2026-09-28 - V5.3 長編耐性（伏線ステートマシン実体化・3層記憶配線・KPI計測）

> ⚠️ **履歴の訂正**: 5.3.0 の初回リリース時点では、
> 本エントリに書かれた多くの配線は**未接続**でした。すなわち
> 「伏線IDの描画」「背景伏線ブロック」「3層記憶の Layer2 バジェット」
> 「ダイジェスト永続化」「KPI レポーター」は、コードは存在するが
>   本番経路から到達しない、または期待どおりの挙動になっていませんでした。
> 詳細は v6.0.0 の「修正（v5.3 配線の未接続）」を参照してください。
> 以下の記述は**設計意図**として記録しています。

ロードマップの主要KPI「**長編（20〜50話）で破綻なく完走する**」「**伏線回収率**」を
目標に、v5.2 まで*配線されていなかった*長編機構を実体化した。

### 修正（長編破綻の根本原因）

- **伏線ステートマシンの未実装**
  - `ForeshadowingStatus` に遷移テーブル（`can_transition` / `allowed_transitions`）を実装。
    終端状態（resolved / abandoned）からの巻き戻しは UPDATE せず拒否。
  - `DbForeshadowingRepository` に共通 `_transition()` を導入し、
    `resolve` / `progress` / `abandon` をすべて遷移ガード経由に統一。
  - 不変条件 `resolved_episode >= planted_episode` を `resolve()` で検証。
    従来は「設置話より前の話で回収する」ことが(DB上)可能だった。
- **`update_target_episode` の欠如による延期サイレント no-op**
  - `ForeshadowingRescheduler` は `hasattr(repo, "update_target_episode")` で
    呼び出しをガードしていたが、`DbForeshadowingRepository` にそのメソッドが
    存在せず、**UPDATE は発行されないまま成功ログだけ出力**していた。
  - 実 API を実装し、API 不在時・拒否時は成功を偽装せず `None` を返すよう修正。
- **`target_episode` が常に NULL**
  - `promotion_service` / `plots.py` の経験則 `ep_num <= 5 → short_term` を
    ビートシート基準の計画に置き換え（`src/services/foreshadowing/planner.py` 新設）。
  - NULL のままだと `ForeshadowingService.check_and_resolve` の `is_contracted` が
    常に `True` となり、アンサンブルスコアの「契約ボーナス」が機能していなかった。

### 追加

- **伏線設置計画 `src/services/foreshadowing/planner.py`**
  - 回収ビート（`foreshadowing_directive` に「回収」を含むビート。判定基準は
    `ForeshadowingRescheduler` と共通）から scope と回収予定話を決定。
  - 回収先は回収区間内に**設置位置に応じて線形分散**させ、同一話への集中を防ぐ。
  - 回収ビート内に設置された場合は同ビート内で回収（クライマックス中に撒いた伏線が
    クライマックス後に回収される構造的破綻を解消）。
  - 不変条件: 回収予定話 > 設置話、horizon >= 1、同時回収は最大3本/話。
- **契約伏線プレビューの本番配線**
  - `ContextBuilderAgent._load_db_foreshadowings()` で伏線テーブルから
    未回収伏線・契約伏線を取得し、`writing_context` に載せる
    （正典を `plot_json` から `foreshadowings` テーブルへ移行）。
  - `PromptManager.build_final_writing_prompt` が
    `foreshadowing_contract_instruction.j2` を実際に描画するようにした
    （同テンプレートは v5.2 までテストからのみ描画され、本番では未使用）。
  - `writing_metadata_instruction.j2` の `contract_foreshadowings` ループに
    データを供給。**LLM が「どの伏線を回収したか」を ID で報告できるようになった**
    （従来は `foreshadowings` 配列が常に空で `WritingMetadata.foreshadowings` は
    常に `[]`。`EnsembleJudge` は常に閾値下げモードで動作していた）。
  - `EpisodeWriter.run` が `contract_ids` を `check_and_resolve` に渡す。
- **3層ローリング記憶の実配線**
  - `three_layer_context` は v5.2 まで `ContextBuilderAgent` で組み立てられるだけだった。
    `PromptComposer._format_three_layer_context` を追加し、
    `final_writing_prompt.j2` に注入する配線を追加。
  - `episode_context.py` に Layer2 のトークンバジェット制御を導入。
    直近10話は全文ダイジェスト、最初は2話を保持し、間は省略マーカーで圧縮、
    総文字数は `LAYER2_MAX_CHARS`(既定4000) で頭打ち。
    従来は過去話全文を無制限に積み上げて N話目に比例して肥大していた。
- **ダイジェストの永続化**
  - `EpisodeDigestService.summarize_and_save` に本番呼び出しが無い状態だったため、
    `EpisodeWriter._persist_episode_digest` を追加。
  - `episode_digests` テーブルの Alembic マイグレーション `0031_episode_digests.py` を新設
    （テーブル定義はあったが DDL が存在せず、Alembic 構築の DB には不在だった）。
- **伏線KPIの計測基盤**
  - `src/services/foreshadowing/kpi.py` 新設: 回収率・解決率・未回収数・期限超過数を算出。
    `DbForeshadowingRepository.get_balance` は完成していたが**本番から一度も
    呼ばれていなかった**（デッドコード）状態を解消。
  - Prometheus メトリクス 9 種を新設（`foreshadowing_collection_rate`,
    `foreshadowing_active`, `foreshadowing_overdue`,
    `foreshadowing_status_transitions_total`,
    `foreshadowing_transitions_rejected_total`,
    `foreshadowing_rescheduled_total`, `foreshadowing_planted_total`,
    `longform_context_tokens`, `longform_context_chars`）。
  - `GET /api/graph/foreshadowing/kpi` エンドポイントを追加。
- **長編ベンチマーク `tests/benchmarks/long_form.py`**
  - 完走率・回収率・解決率・Layer2 文字数の推移を 20/50/100/200話で計測。
  - `python -m tests.benchmarks.long_form --eps 20,50,100 --check`

### 変更

- `format_unresolved_foreshadowings` が伏線 ID と現状ステータスを描画するようにした
  （ID が無いと LLM は回収を報告できない）。出力書式は
  `- **{id}** (第N話提示 → 第M話回収予定): 『タイトル』説明 [現状: status]`。
- `ConsistencyAuditor` の伏線パーサを `_extract_foreshadowing_descriptions()`
  として共通化し、同一書式でパースすることをテストで固定化。
- バージョン表記を 5.3.0 へ統一。

### テスト

- `tests/regression/test_v53_long_form_integrity.py`（41 テスト）:
  ステートマシン遷移ガード / 設置計画の不変条件 / プロンプトID配線 /
  Rescheduler の偽成功防止 / KPI算出 / 3層記憶の注入 / 長編プラトー。
- ベンチマーク実測（LLM 呼び出しなし）:
  - 完走率 100%（20/50/100/200話すべて）
  - 回収率 100%、解決率 98〜100%
  - **Layer2 最大文字数が 50話で 995 にプラトー**（200話でも 995。線形成長しない）
- 回帰確認: HEAD の worktree と差分比較し、**新規回帰 0 件**。

## [Unreleased] - v5.2.1 後の欠陥修正・テスト復旧

`docs/STATUS.md` を追加し、現在の機能実装状況（SSOT）を一元化した。

### 修正
- **fix(v5)**: GraphRAG pipeline の await 漏れにより `/api/graph/pipeline/process` と `/api/graph/pipeline/batch` が常に 500 を返していた（両ハンドラを `async` 化）
  - `src/backend/routers/graph.py`
- **fix(v5)**: branches ルータの所有者検証をラッパー方式から FastAPI 依存方式へ変更（ラッパー方式は単体テストの直接呼び出しを 401 で壊していた）
  - `src/backend/routers/branches.py` / `src/backend/security/owner_guard.py`
- **fix(v5)**: `jinja2.sandbox` の import 漏れでサブテキストテンプレートの描画が全滅していた
  - `src/narrative/subtext_templates/renderer.py`
- **fix(v5)**: 章インポートの実装判定マーカー (`_unimplemented_marker`) が未設定で、ガードが機能していなかった
  - `src/agents/writing/agent.py`, `src/agents/writing/generator.py`, `src/domain/writing/coordinator.py`
- **fix(v5)**: メトリクスポートのシグネチャ不一致で BookScore メトリクスが記録されていなかった
  - `src/backend/observability/metrics.py`, `src/backend/database/repositories/book_score.py`
- **fix(v5)**: `.env.example` の `HUEY_BACKEND=memory` が `Settings` の `Literal` と食い違い、初回起動が `ValidationError` で失敗していた
  - `.env.example`（`HUEY_BACKEND=sqlite` へ修正）

### テスト
- 契約テストが認証導入後 401 で全滅していた件の復旧
- 本番設定バリデーションのテストが `AUTH_DISABLED=true` に汚染されていた件の自己完結化
- 執筆グラフの経路分岐テストを v5.0 Early Exit 方針に合わせる

### 保守
- 追跡されていた生成物を解除（`$null`、Vite 一時ファイル、`output/` のカバレッジ JSON と調査用 txt、`logs/*.jsonl`）。`artifacts/` は回帰防止の基準値として追跡を維持
  - `.gitignore`

### ドキュメント
- `docs/STATUS.md`: 現行の機能実装状況・既知の制限を记录的した SSOT を新規追加
- ルートの 6 つのサマリ文書（`IMPROVEMENT_SUMMARY.md` / `IMPROVEMENT_SUMMARY_CONCISE.md` / `IMPROVEMENT_SUGGESTIONS.md` / `IMPLEMENTATION_SUMMARY.md` / `IMPLEMENTATION_SUMMARY_JA.md` / `FINAL_SUMMARY.md`）に「過去スナップショット・現状ではない」旨のバナーを追加。本文は改変しない
- `plans/README.md`: A1〜A4 の 96 ステップ文書は設計文書であり進捗 SSOT ではない旨を明記

## [5.2.1] - 2026-09-26 - V5 ファイナライゼーション（マンガ/low-cost パイプライン統合）

### 追加
- **1シート24コマの低コストマンガ生成パイプライン**:
  - `src/services/manga/`: `client.py` / `config.py` / `models.py` / `pipeline.py` / `prompt_generator.py` / `quality_gate.py` / `typesetter.py` / `upscaler.py`
  - `tests/regression/test_manga_regression.py`, `tests/services/test_manga_pipeline.py`
  - `tests/e2e/test_v5_workflow_e2e.py`, `tests/e2e/test_v5_storage_parity.py`
  - `frontend/src/tests/workflow_promotion.test.tsx`
- **イラストクライアントの抽象化**: `src/services/illustration/clients/` に `base.py` / `gemini_image_client.py` / `legacy_imagen_client.py` / `mock_client.py`、`config/image_models.py`
- **フォアショーディング状態の同期**: `src/services/graph_pipeline.py`, `src/services/promotion_service.py`, `tests/unit/test_v5_foreshadowing_promotion_sync.py`

### 変更
- `src/core/container/`: 遅延ロード（lazy loading）の安定化
- `src/backend/server.py`: 本番ルーターのマウント（`billing.py` / `commercial_planning.py` / `orchestrated.py` / `plots.py`）
- `src/backend/config.py`, `prompts/`, `src/agents/marketing.py`, `src/services/rag/rag_service.py`
- `pytest.ini`: pytest 設定の統合
- バージョン表記を 5.2.1 へ統一（`pyproject.toml` / `src/cli/main.py` / `src/backend/__init__.py` / `frontend/package.json` / `docker-compose.prod.yml`）

### 削除
- `chore: repository cleanup`: リポジトリルート直下のデバッグ用スクリプト群（`analyze_models.py`, `debug_parser.py`, `debug_persist.py`, `debug_regex.py`, `debug_target.py`, `comparison_table.md` 等）を削除

## [5.2.0] - 2026-09-25 - Coarse-to-Fine ナラティブパイプライン統合・Phase 2

### 追加
- **Coarse-to-Fine ナラティブ生成**:
  - `prompts/manager.py`, `prompts/templates/narrative/macro_plot_skeleton.j2`, `prompts/templates/narrative/micro_scene_expander.j2`
  - `config/constants.py`
- **設計・計画ドキュメント**: `plans/PLAN_J1_COARSE_FINE_MODELS_36STEPS.md`, `plans/PLAN_J2_JIT_EXPANDER_SERVICE_36STEPS.md`, `plans/PLAN_J3_PIPELINE_INTEGRATION_36_STEPS.md`, `plans/PLAN_CODE_REVIEW_PHASE2_REMEDIATION_24STEPS.md`
- **計測・検証スクリプト**: `scripts/coverage_summary.py`, `scripts/run_full_coverage.py`, `benchmarks/bench_plot_resolution.py`, `scripts/debug/check_*.py`

### 変更
- `.env.example`: Phase 2 設定の追記（8 行追加）
- `docker-compose.yml`: Phase 2 対応（12 行変更）
- `plans/PHASE_ROADMAP_MASTER.md`: ロードマップ更新
- バージョン表記を 5.2.0 へ統一

## [5.1.1] - 2026-09-25 - リリース用バージョン更新のみ

### 変更
- バージョン表記のリリースノート記録のみ（`5.1.0..5.1.1` 間に機能変更のコミットなし）

## [Unreleased] - Phase 2: Blind Peer Review / Specialist Audit / Reflective RAG

ガイドライン Phase 2 (Guidelines #1, #3, #7) を実装。創造性・品質・RAG精度を大幅向上。

### 追加
- **Blind Peer Review (Guideline #1)**: `src/services/blind_review.py` に `BlindReviewGate` 実装。3案企画ガチャ等で他案出力を参照せず独立採点可能。`EventBus.publish_blind()` で自動マスク適用。
- **Multi-layer Specialist Audit (Guideline #3)**: 8名の専門オーディター (`src/agents/specialists/`) を並列実行。
  - Consistency / Creativity / ReaderHook / EmotionCurve / Style / Factual / Structure / Multimodal
  - `AuditAggregator` でジャンル・フェーズ別重み (`config/audit_weights.yaml`) による加重集約
  - `v2` audit skill (`src/agents/skills/v2/audit_skill.py`) が並列起動・再生成フォーカス設定を自動化
- **Reflective RAG Screening (Guideline #7)**: `src/services/reflective_rag.py` に反復クエリ精緻化ループ実装。
  - BM25 キーワード抽出 (`rank-bm25` 既存依存流用)
  - GraphRAG 文脈適合性チェック (is_forbidden 属性)
  - 最大3回反復で収束判定、履歴を `rag_reflection_history` テーブルに保存
- **DB 拡張**: `audit_specialist_results` / `rag_reflection_history` テーブル + Alembic migration
- **EventBus 拡張**: `publish_blind()` / 専門オーディター用イベント型 (`audit.specialist.started/completed`)
- **管理者 API**: `/admin/audit/*` (専門オーディター一覧・集約テスト) / `/admin/rag/*` (反射テスト・統計)
- **Prometheus メトリクス**: blind_review_blocked_keys / specialist_audit_duration / specialist_audit_score / reflective_rag_iterations / reflective_rag_convergence 等
- **設定**: `config/audit_weights.yaml` (デフォルト/ジャンル別/フェーズ別完全重みマップ)

### 変更
- `src/agents/skills/v2/audit_skill.py`: プレースホルダ実装を本物の並列監査に置換
- `src/services/rag_service.py`: `retrieve_with_reflection()` メソッド追加 (機能フラグ `RAG_REFLECTION_ENABLED` 対応)

### テスト
- `tests/unit/test_blind_review.py` (11 テスト): スクラブ/ハッシュ/ネスト/性能
- `tests/unit/test_specialist_auditors.py` (26 テスト): 8専門家のスコア/フィードバック/LLMフォールバック
- `tests/unit/test_audit_aggregator.py` (14 テスト): 並列実行/重み集約/欠損処理/イベント発行
- `tests/unit/test_reflective_rag.py` (8 テスト): 収束/閾値/履歴/空結果
- `tests/e2e/phase2_full_flow.py`: 3案盲検 → 8専門家並列 → 反射RAG の完全フロー

---

## [Unreleased] - Pipeline Unification (Phase 3-4)

統合パイプライン (AutoWorkflowPipeline) への完全委譲を完了。

### 変更
- **FullAutoWorkflow / EasyModeWorkflow → AutoWorkflowPipeline 委譲**: 両ワークフローが `pipeline.execute(ctx, self.engine, adapter)` 経由で統合パイプラインに完全委譲。インライン実装は削除済み
- **Adapter 統一**: `EasyModeWorkflow` も `FullAutoWorkflow` と同様に `ProgressReporterAdapter` を使用 (`UnifiedProgressReporter` から切替)
- **重複 wrap 解消**: `AutoWorkflowPipeline.execute()` が `ProgressReporterAdapter` インスタンスを既に受け取った場合は再 wrap をスキップ
- **USE_UNIFIED_PIPELINE フラグ整理**: `=0` 指定時に `NotImplementedError` を送出。旧実装は削除済みのため明示的にエラー化

### 削除
- `src/services/progress_reporter.py` から `UnifiedProgressReporter` / `StatusReporterAdapter` / `create_progress_adapter` 関数を削除（未使用）
- `src/services/progress_reporter.py` から `ProgressReporterProtocol` / `ProgressCallbackProtocol` を削除（未使用）

### テスト
- `tests/test_easy_mode_workflow.py` 新規 (7 テスト): 委譲 / Context 設定 / Adapter 初期化 / 戻り値形式 / デフォルト値 / フラグ伝搬を検証
- `tests/test_full_auto_workflow.py` 新規 (5 テスト): 委譲 / Context 設定 / Adapter 初期化 / 戻り値形式 / エンジン直接呼び出ししないことを検証
- 既存 `tests/test_unified_pipeline.py` (26 テスト) は pass を維持

---

## [Unreleased] - Multimedia (Phase 7)

マルチメディア展開 (Asset Pack / Media Mix / IF Routes / eBook Export) の初回統合リリース。
3,700 行の孤児コードを FastAPI ルータ + React UI から利用可能にし、機能フラグ `ENABLE_MULTIMEDIA` で段階ロールアウト可能化。

### 追加
- **機能フラグ**: `ENABLE_MULTIMEDIA` / `ENABLE_AUDIO_SYNTH` / `MULTIMEDIA_OUTPUT_DIR` を `config.py` に追加
- **バックエンド**:
  - `routers/multimedia.py` (8 エンドポイント: `/multimedia/media-mix`, `/ebook`, `/if-routes`, `/asset-pack`, `/artifacts/{id}`, `/artifacts/{id}/download`, `/tasks/{id}`, `/files/{filename}`)
  - `multimedia_service.py` 統合サービス層
  - `multimedia_storage.py` 出力ディレクトリ管理
  - `feature_flags.py` フラグ判定ユーティリティ
  - `tasks/multimedia_tasks.py` Huey 非同期タスク
  - `schemas/multimedia.py` Pydantic スキーマ
  - `MultimediaArtifact` / `MultimediaTask` テーブル (alembic 0011)
  - `MultimediaDisabledError` (HTTP 503)
  - `series_serializer.py` ユーティリティ
- **フロントエンド**:
  - `types/multimedia.ts` 型定義
  - `api/multimedia.ts` API クライアント
  - `hooks/useMultimedia.ts` React フック
  - `components/AssetPackPanel.tsx` Studio 統合
- **メトリクス**: `multimedia_requests_total` / `multimedia_errors_total` カウンタ追加
- **ドキュメント**: `docs/multimedia.md`, `docs/multimedia_slo.md`, `docs/multimedia_security.md`, `docs/user/multimedia.md`
- **アラート**: `docker/grafana/alerts/multimedia.yaml`

### テスト (54 件)
- `tests/unit/test_media_mix.py`, `test_ebook_export.py`, `test_asset_pack.py`, `test_multimedia_service.py`, `test_feature_flags.py`, `test_multimedia_storage.py`, `test_multimedia_schemas.py`, `test_series_serializer.py`, `test_multimedia_tasks.py`
- `tests/integration/test_multimedia_router.py`, `test_multimedia_e2e.py`
- `tests/unit/test_if_routes.py` 拡充 (BranchCondition.apply_effects, IFRouteGenerator minimum nodes, IFRouteGraph.validate)

### マイグレーション
- `alembic/versions/0011_multimedia_artifacts.py`: `multimedia_artifacts` / `multimedia_tasks` テーブル

## [Unreleased] - Phase 5: 品質・観測・ドキュメント (Step 51-62)

ロギング・オブザーバビリティ・ドキュメントの三点で運用信頼性と保守性を向上。

### 追加
- **オブザーバビリティ**: `src/backend/observability.py` 新設。DB 接続確認 (`SELECT 1`) と Huey 生存確認 (`len(huey)`) を統合した `build_health_payload` ([`src/backend/observability.py`](src/backend/observability.py))
- **メトリクス**: `GET /metrics` エンドポイント追加。プロセス内カウンタ (`tasks_enqueued` / `tasks_completed` / `tasks_failed` / `exports_attempted` / `exports_succeeded` / `health_checks`) を提供 ([`src/backend/server.py`](src/backend/server.py))
- **テスト**: `test_health.py` に拡充ヘルスチェック (`components` / `metrics`) と `/metrics` エンドポイントの検証を追加 ([`tests/test_health.py`](tests/test_health.py))

### 変更
- **ヘルスチェック**: `GET /health` を DB/Huey 生存 + メトリクススナップショットを含めた総合ペイロードへ拡充 (`status` は `ok` / `degraded`)。後方互換のため `{"status": "ok"}` のスーパーセット ([`src/backend/server.py`](src/backend/server.py))
- **ロギング**: `logging_config.py` 強化。`app` / `version` / `env` コンテキスト付与、`LOG_FORMAT` / `LOG_LEVEL_<NAME>` / `APP_ENV` 環境変数対応、ノイズロガー抑制 ([`src/backend/logging_config.py`](src/backend/logging_config.py))
- **重要処理ログ**: タスク投入 / 生成完了 / 生成失敗 / エクスポート要求・成功 / ステータスポーリング / ヘルスチェック呼出に構造化ログを追加 ([`src/backend/routers/easy_mode.py`](src/backend/routers/easy_mode.py), [`src/backend/tasks/generation_tasks.py`](src/backend/tasks/generation_tasks.py), [`src/services/marketing.py`](src/services/marketing.py))
- **メトリクス連携**: 主要処理 (タスク投入/完了/失敗・エクスポート試行/成功・ヘルスチェック) から `metrics.increment` を呼出し
- **ドキュメント**: `docs/api.md` を `/metrics` と拡充 `/health`・環境変数 (`LOG_FORMAT`, `APP_ENV`, `LOG_LEVEL_<NAME>`) で更新 ([`docs/api.md`](docs/api.md))
- **ドキュメント**: `docs/openapi.json` を `scripts/generate_openapi.py` で再生成 ([`docs/openapi.json`](docs/openapi.json), [`scripts/generate_openapi.py`](scripts/generate_openapi.py))
- **README**: API テーブルに `/health` (拡充版) / `/metrics` を追加、環境変数テーブル拡充、新規「オブザーバビリティ」セクション追加・目次更新 ([`README.md`](README.md))

## [5.1.0] - 2026-09-24 - Stabilization and Architectural Consolidation (P1〜P3)

### 追加
- **ローカル起動の完全修復 (Part 1: Step 1-8)**:
  - `scripts/check_env.py`: Python バージョン・仮想環境・ポート空き状況の事前自己診断（カラー/JSON 出力）
  - `scripts/init_db.py`: SQLite 安全マイグレーション（既存 DB 保護、`--force` オプション）
  - `scripts/start_local.ps1`: 堅牢な協調起動ランナー（`-DryRun` / `-SkipInstall`、孤立プロセス防止）
  - `scripts/stop_local.ps1` + `アプリ停止.bat`: ポート 8200/5173 の Graceful Termination
  - `アプリ起動_ローカル.bat` の正式ラッパー化（`--skip-migrations` 問題の解消）
  - `tests/integration/test_local_startup.py`: 起動プロセス自動検証テスト
- **マルチメディアのプラグイン疎結合化 (Part 3: Step 15-22)**:
  - `src/interfaces/plugin.py`: `PluginProtocol`（initialize / is_available / shutdown）
  - `src/interfaces/image_provider.py`: `ImageProviderProtocol`（Imagen / DALL-E / SD WebUI / ComfyUI 統一抽象）
  - `src/core/plugin_registry.py`: `PluginRegistry`（環境変数フラグによる動的ロード・無効化）
  - `src/plugins/multimedia/`: MultimediaService のオプショナルプラグインカプセル化
  - `src/plugins/audio/voicevox.py`: VOICEVOX サーバー不在時の Graceful Fallback（スキップ / 無音 WAV）
  - `tests/unit/core/test_core_without_plugins.py`: プラグイン 0 件でのコア完全動作保証
- **CLI・監視の整理 (Part 4: Step 23-28)**:
  - `src/cli/main.py`: 統一 CLI `autonovel`（balance / export / init-db / check-env / plugins サブコマンド）
  - `pyproject.toml`: `[project.scripts]` に `autonovel = "src.cli.main:main"` 登録（旧エイリアス維持）
  - `/health` エンドポイント: 非同期並行チェック + 各コンポーネント 1.0 秒タイムアウト制限
  - `/metrics`: 固定キー集計限定・動的ラベル生成抑制（メモリリーク防止）
  - `tests/unit/cli/`, `tests/unit/api/test_health_timeout.py`, `tests/unit/api/test_metrics_memory.py`
- **ドキュメントの刷新 (Part 5: Step 29-34)**:
  - `docs/development_guide.md`: 15 分オンボーディングガイド新規作成
  - `docs/openapi.json`: 最新ルーター構成からの再エクスポート
  - `frontend/src/types/api.generated.ts`: TypeScript 型定義の自動再生成

### 変更
- `.env.example`: 旧バージョン表記を解消し、必須/オプショナルの区分けと `ENABLE_*` 機能フラグを明記
- `docker-compose.yml`: 開発用メモリ制限（backend 1024M / chromadb 512M）とヘルスゲート依存の厳格化
- `Dockerfile`: マルチステージビルド最適化（`--prefix=/opt/deps` による依存隔離・最小ランタイムコピー）
- `src/backend/server.py`: multimedia プラグイン無効時の条件付きルーターマウント（Step 19）
- README.md: 「Windows ワンクリック起動（非推奨）」の汚名返上、正式起動手順として認定

### 削除
- README.md の旧「非推奨：既知の問題あり」警告文

## [5.0.2] - 2026-09-18 - 4層圧縮統合・CI・ドキュメント更新

### 追加
- DI コンテナによる FourLayerCompressor シングルトン提供 (AppContainer)
- WritingService、ContextBuilderAgent、EpisodeWriter、EasyMode パイプラインへのコンプレッサー注入
- 4層圧縮モジュールの詳細設計と書類追加 (docs/compression_module.md、docs/architecture.md 更新)
- CI パイプラインの追加 (.github/workflows/ci.yml) で自動テスト実行
- README.md に 4層圧縮統合の概要と使用例を追加

### 変更
- なし


### 追加
- **第1の柱: 表現力・窓枠評価**:
  - `NovelSectionExtractor`: 冒頭/末尾/等間隔起承転結/重要シーンの文頭・文末スナップ窓枠抽出（4000字打ち切り全廃）。
  - 文法整合性保護五感拡充（`sentence_span`、会話文保護、句読点サニタイズ）。
  - 自然文トリビアリライト（Jinja2、POV適応）。
  - `ActionableDiff`: 原文引用、改善案、改稿理由の構造化。
- **第2の柱: 状態管理・非同期インフラ**:
  - `SocialInteractionManager` & `SocialRepository`: キャラクター手記・相互コメント・動態ステートのSQLite WAL非同期永続化。
  - `Huey` 分散キュー: RedisHuey ＋ SqliteHuey 自動フォールバック。
  - `DAGScheduler`: CPU/RAM/GPU セマフォバックプレッシャー、タスクタイムアウト/リトライ、チェックポイント永続化。
- **第3の柱: セマンティックRAG & 4層圧縮**:
  - `DynamicTaxonomyEngine`: 形態素接尾辞ルール＋埋め込み類似度アンカー＋LLM動的推論（固定辞書完全脱却）。
  - `ProtectedContext` & `Layer4SceneTrimmer`: 9大シーン適応トリミング、重要伏線・登場人物保持率100%。
  - `HybridRetriever` (Dense+BM25 RRF) ＋ `QueryReformulator` (HyDE / 意図誘導) ＋ World Bible整合性フィルター。
  - `ProposalIsolationRunner` & `BlindFeedbackPurifier`: 3案企画ガチャ物理サンドボックス隔離とリーク自動純化。
- **第4の柱: 評価・閉ループPDCA統合**:
  - 8専門家 High/Mid/Low アンカー事例注入（採点甘辛ブレ抑止）。
  - `ScoreCalibrator`: 事前分布、ベイズ的信頼度シュリンク、シグモイド有界化、分散ペナルティ。
  - `UnifiedBookScoreBridge`: 8専門家×5次元変換マトリクス、ジャンル/フェーズ別シフター、寄与度内訳分解。
  - `ClosedLoopPDCARunner`: 最低次元特定、Actionable Diff $\to$ 必須制約変換、再執筆・再監査・収束判定（改善率 $\ge 15\%$）。
  - `DAGReplanner`: ドラフトノード局所リトライ、BFS下流タスク特定＆安全キャンセル、EventBus `dag.replanned` 発行。
  - `CommercialBenchmarkJudge`: 商業出版水準（85+ Sランク）、Web連載水準（75+ Aランク）、全次元足切り（60+）、7大ヘルスチェック（7/7 PASS）。

### 変更
- バージョンを 4.7.0 に更新 (`pyproject.toml`, `src/backend/config.py`, `frontend/package.json`, `README.md`)。

`docs/bugs/ui-functionality-gap-plan.md` 計画書に基づく 36 ステップ・14 バグの是正。

### 追加
- **Studio モード タブ UI 復旧 (BUG-01/04)**: `frontend/src/components/studio/StudioWorkspace.tsx` に ✏️ エディタ / 🖼️ マルチメディア 切替タブを追加。localStorage 永続化付き。
- **画像生成モーダル導線 (BUG-04)**: `frontend/src/App.tsx` ヘッダに「🖼️ 画像生成」ボタン追加し、`AssetPackPanel` をモーダル表示。
- **state_token 保存 (BUG-02)**: `src/services/promotion_service.py` に `save_state_token` メソッド追加。`InternalState` テーブルへ TTL 24h 付きで永続化。
- **`/studio/:bookId?token=` ルート (BUG-02)**: `ExportPanel.handlePromote` で `redirect_url` を `history.pushState` 経由で URL に反映。`App.tsx` の popstate リスナーが Studio モードへ自動切替。
- **ジャンル → preset 辞書 (BUG-05)**: `src/backend/routers/easy_mode.py` に `GENRE_TO_PRESET` 優先度順マッピングと `resolve_genre_to_preset()` 関数を追加。`vrmmo`/`slow_life`/`zarma`/`aku_reijo`/`dungeon_admin`/`loop`/`modern_cheat` 全てが UI から到達可能。
- **`GENRE_OPTIONS` 定数 (BUG-05)**: `frontend/src/constants/genres.ts` を新規作成し、`<select>` を `.map()` 化。
- **Reverse Plot データ保護 (BUG-06)**: `GeneratePanel.handleReversePlotComplete` で `window.confirm` 確認 + 既存 `chapter.content` 保持ロジックを追加。
- **未使用 hook 隔離 (BUG-10)**: `useCollabSync` / `usePatchReviews` を `frontend/src/hooks/_unused/` へ移動。`useLocalDraft` の自動保存を `Editor.tsx` に組み込み (5秒間隔 localStorage ミラー)。

### 変更
- **本文管理の単一ソース化 (BUG-03/11/12/13)**: `GenerationState.currentOutput` フィールドを削除し、全編集フローを `currentChapterText` に統一。`useStreamingWriter` / `useNovelGeneration` / `ExportPanel` / `NovelContext` を更新。
- **SSE エラー可視化 (BUG-08)**: `useStreamingWriter` の catch ブロックから無音フォールバック (ハードコード和文タイプライター) を撤去。明示エラー通知に変更。
- **`Ctrl+S` 嘘トースト撤去 (BUG-07)**: `Editor.tsx:117-119` の誤認トーストを撤去。
- **`promote` redirect_url 形式 (BUG-02)**: `/advanced/{book_id}` → `/studio/{book_id}` に変更。
- **ヘッダキャッチコピー (BUG-09)**: "Notion AI × Sudowrite 式" → 実機能列挙 ("AI 執筆・設定管理・矛盾診断・マルチメディア生成スタジオ")。

### 削除
- フォールバック用ハードコードテキスト (`useStreamingWriter.ts:135` 旧) 全削除
- `GenerationState.currentOutput` setter 4 箇所全削除
- `useCollabSync` / `usePatchReviews` の import パス 1 箇所 (`ConflictModal.tsx`) を `_unused` 経由に変更

### テスト
- **新規**: `frontend/tests/components/StudioWorkspace.test.tsx` にタブ切替・localStorage 永続化テスト 2 件追加 (合計 3 tests)
- **新規**: `frontend/tests/components/GeneratePanel.reversePlotProtection.test.tsx` に confirm 動作テスト 2 件追加
- **新規**: `tests/test_genre_mapping.py` (Python) ジャンル → preset マッピングテスト 2 件
- **回帰**: 既存 14 test files / 48 tests / 46 pass / 2 fail → 修正後 15 test files / 52 tests / 50 pass / 2 fail (リグレッションなし)
- ベースライン: `docs/bugs/baseline-frontend.txt` / 最終: `docs/bugs/final-frontend-test.txt` / TypeScript 型チェック: pass

### ドキュメント
- `docs/bugs/ui-functionality-gap.md` (新規): 14 BUG の追跡ドキュメント
- `docs/bugs/ui-functionality-gap-plan.md` (新規): 36 ステップ実装計画書
- `docs/bugs/asset-pack-todo.md` (新規): AssetPackPanel 残 TODO リスト
- `docs/bugs/baseline-frontend.txt` (新規): 修正前テスト結果
- `docs/bugs/final-frontend-test.txt` (新規): 修正後テスト結果

## [4.7.0] - 2026-09-08 - 4大改善の柱（Pillar 1〜4: 全288ステップ）完全統合・商業品質化

## [4.2.0] - 2026-09-04

### 修正（P0: 致命的バグ・リリースブロッカー）
- **alembic パス整合**: 不要な `COPY alembic/ ./alembic/` を削除。`src/` 配下の `src/backend/alembic` が `alembic.ini` の `script_location` を満たす
- **DATABASE_URL → ALEMBIC_DATABASE_URL ブリッジ**: `docker/backend/entrypoint.sh` で compose の `DATABASE_URL` を `ALEMBIC_DATABASE_URL` としてエクスポート。`localhost` への誤接続を解消
- **worker entrypoint パス**: `docker-compose.yml` をリポジトリ相対パスから `/usr/local/bin/entrypoint.sh` に修正
- **LLMProviderFactory cooldown 注入**: ヘルスチェックでの `TypeError` を解消。`AdaptiveCooldown` 経由で no-op cooldown を渡す
- **ヘルスチェックのキー/モデル整合**: OpenAI キー → Gemini キー (`settings.GEMINI_API_KEY`) に統一
- **HealthResponse.version ハードコード解消**: `"3.0.0"` → `settings.APP_VERSION` 連動

### 変更
- **APP_VERSION / pyproject バージョン**: 4.0.0 / 4.1.0 → 4.2.0 に揃え
- **easy_mode ルタ二重登録の本番ガード**: `APP_ENV=development` のみで `/api/easy-mode` をマウント
- **easyMode.ts のBASE 統一**: `/generate/stream` を `${BASE}/generate/stream` に統一
- **nginx プロキシ経路拡張**: styles / multimedia / patches / issues / marketing / novel / illustrations / collab / export / hooks / branches / prompt_versions / commercial / system / trace / structure / orchestrated / reverse_plot / prompt_compare をロケーションに追加
- **LLM ファクトリのフェイルファスト化**: 設定プロバイダのAPI キーが未設定なら `RuntimeError` を送出（Mock フォールバック廃止）

### 削除
- `src/backend/worker_config.py`: Huey 設定は `src/backend/tasks/huey.py` に統合済み

### テスト
- `tests/unit/test_llm_factory.py` を全面書き換え（Mock フォールバック前提をフェイルファスト前提に変更、OpenRouter 用の `BASE_URL` 単独設定ケースを追加）
- `tests/unit/test_health_checks.py` を新規作成（cooldown 注入、disabled フラグ、factory 例外系の網羅）

---

## [4.1.0] - 2026-09-04

Phase 1 (短期・高影響度) 完了: スキル駆動型エージェントアーキテクチャ + BookScore 統一100点尺度メトリクス実装。ガイドライン準拠で運用レベル到達。マルチエージェントオーケストレーション正式対応。

### 追加
- **スキル駆動型エージェントアーキテクチャ**:
  - `SkillAgent` 抽象基底クラス (`src/agents/skill_base.py`) - `execute()`/`emit_event()`/`discover_skills()`/`load_manifest()` 実装
  - 既存 6 エージェント (`PlanningAgent`/`PlotAgent`/`BibleAgent`/`ContextBuilderAgent`/`AuditAgent`/`IllustrationAgent`) を `SkillAgent` 継承へリファクタ
  - `WritingAgent` 新規実装 + 後方互換エイリアス (`WritingAgent` + `WritingGenerator`)
  - スキルマニフェスト (`src/agents/skills/manifest.yaml`) - 9スキル定義・依存関係解決 (トポロジカルソート)
  - EventBus 統合 (`publish_async`/`emit_event_sync`/`flush`) - 全スキルへイベント発行追加
  - v1/v2 バージョン管理・ホットスワップ (`set_skill_version`/`promote_ab_winner`)
  - A/Bテスト自動化 (`run_ab_test` - 統計的有意差判定・p値計算・勝者自動昇格)
  - 管理者 API: `/admin/skills/switch_version`, `/admin/skills/ab_test/*`, `/admin/skills/metrics`, `/admin/skills/ab_test/auto_promote`
  - Prometheus メトリクス: `skill_version_active`, `ab_test_result_total`, `ab_test_duration_seconds`, `ab_test_success_rate`, `skill_promotion_total`
  - フォールトトレラント実行 (`error_continued`/`exception_continued` イベント)
  - E2E テスト: EventBus統合・A/Bテスト・PDCAサイクル・自動昇格 (38テスト全パス)

- **BookScore 統一100点尺度メトリクス**:
  - 5次元実スコアリング実装 (構造・一貫性・事実性・視覚×テキスト・読者体験) - 重み設定対応
  - 設定ファイル (`config/book_score_weights.yaml`) - デフォルト/ジャンル別/フェーズ別重み
  - DBモデル (`BookScore`)・マイグレーション (`0018_create_book_scores.py`)・リポジトリ完備
  - PlanningService: `predict_book_score_for_proposals` (3案ガチャ比較・推奨フラグ)
  - WritingService: 自動再生成ループ (閾値70点・リトライ3回・次元別アクション生成)
  - ContextBuilder/Illustration/WritingAgent: 再生成フック (`regeneration_focus`/`regenerate_prompts`/`rewrite_with_focus`)
  - API: `/books/{id}/chapters/{num}/score`, `/books/{id}/promotion`, `/books/{id}/pdca`, `/books/{id}/alerts`, `/admin/book_score/improvement_priorities`, `/admin/book_score/recalc`
  - 時系列分析 (`analyze_trend`: 線形回帰・移動平均・変化点検出・次章予測)
  - PDCA自動レポート (`generate_pdca_report`: Plan-Do-Check-Act 4象限)
  - アラート種別: `score_drop`/`stagnation`/`anomaly`/`no_improvement`
  - Prometheus: `book_score_overall`, `book_score_dimensions`, `book_score_regeneration_triggered`, `book_score_trend`, `book_score_promotion_eligible`, `book_score_improvement_priority`, `book_score_alert_total`, `book_score_forecast`
  - E2E テスト: フィードバックループ・3案比較・昇格判定・PDCA・アラート (17統合テスト全パス)

- **開発インフラ**: 単体テスト 21件 + 統合テスト 17件 = **38テスト全パス**
- **ドキュメント**: `docs/features/phase1_implementation_guide.md`, `docs/FUTURE_IMPROVEMENT_GUIDELINES.md` (Phase 1 ✅ 完了マーク)

### 修正・改善
- Orchestrator: `run()` を非同期 EventBus 対応 (`publish_async`/`flush`)
- SkillAgent: `ab_test_variant` 属性追加・`emit_event_sync` 同期発行対応
- BookScoreCalculator: `_fetch_*` ヘルパー統一・`_score_*` 5次元実装
- ContextBuilderAgent/IllustrationAgent/WritingAgent: 再生成フック実装

## [4.0.0] - 2026-09-01

大規模リファクタリング・健全化リリース。タスク実行基盤の修復、ID二重管理の解消、テストカバレッジ・品質保証を大幅強化。

### 修正・改善
- **タスク実行基盤**: Huey タスク投入シグネチャの不整合を解消し、`generate_chapter_task` 呼び出しを正規化
- **ID統合**: DB の `Task.id` を UUID 文字列型へ刷新し、Huey タスクIDと完全同期。タスクキャンセル機能（`cancel_task`）が確実に反映されるよう改修
- **テスト・品質**: フロントエンドの Vitest カバレッジ基準をクリア（Funcs 55.5% / Stmts 85.2%）、Toast コンポーネント等の単体テストを追加
- **コードベース整理**: 未使用コンポーネント（`Sidebar.tsx`）および不要スクリプト（`sync_reqs.py`, `revenue_simulation.py`）を削除
- **ビルド・依存関係**: `Makefile` のインストールターゲットを `pip install -e .[dev]` に修正

## [0.2.0] - 2026-07-27

72 ステップ実装計画 (Phase 0-6) のうち Phase 0-5 を完了。バックエンド非同期生成フルロー、エクスポート ZIP、React 18 フロントエンド、CI/CD、Docker 本番構成を整備。

### 追加
- **バックエンド**: FastAPI lifespan ハンドラで `init_db()` を確実起動 ([`src/backend/server.py`](src/backend/server.py))
- **非同期生成**: Huey `generate_chapter_task` 実装、成功時に `_persist_success` で DB へ結果保存 → `delete_task` でクリーンアップ ([`src/backend/tasks/generation_tasks.py`](src/backend/tasks/generation_tasks.py))
- **エクスポート**: `MarketingAgent.create_export_package` が ZIP 生成、`Cache-Control: no-store` + RFC 6266 filename ヘッダ ([`src/services/marketing.py`](src/services/marketing.py))
- **バリデーション**: `book_id` に `Path(ge=1)`、`content_length_limit` に `Field(ge=1, le=10000)` (422 応答)
- **ロギング**: `python-json-logger` による JSON 構造化ログ ([`src/backend/logging_config.py`](src/backend/logging_config.py))
- **フロントエンド**: React 18 `createRoot` + GeneratePanel / ExportPanel / API クライアント + ポーリング ([`frontend/src/`](frontend/src/))
- **CI**: GitHub Actions バックエンド (ruff + pytest + OpenAPI 生成) & フロントエンド (typecheck + lint + test:ci) ([`.github/workflows/ci.yml`](.github/workflows/ci.yml))
- **OpenAPI 自動生成**: `scripts/generate_openapi.py` ([`scripts/generate_openapi.py`](scripts/generate_openapi.py))
- **ドキュメント**: API リファレンス ([`docs/api.md`](docs/api.md))
- **テスト**: `test_easy_mode_export.py` (実 DB・fallback・ZIP 内容検証)、`test_health.py` (200/422)、`test_generate_flow.py` (generate→status 統合)、`test_async_generation.py` (クリーンアップ検証)
- **Docker**: バックエンド multi-stage (builder→runtime slim)、フロントエンド nginx 配信 + `/easy_mode/` リバースプロキシ ([`Dockerfile`](Dockerfile), [`frontend/Dockerfile`](frontend/Dockerfile))

### 変更
- [`src/models/book.py`](src/models/book.py): `List`/`Optional` → `list[...]`/`X | None` モダン型ヒント
- [`src/backend/database/__init__.py`](src/backend/database/__init__.py): 未使用 import 削除 + `__all__` 整備
- [`src/backend/database/repository.py`](src/backend/database/repository.py): `is_(False)` 採用、近代化 typig
- [`src/services/marketing.py`](src/services/marketing.py): DB キャラクタ抽出に `personality`/`ability` を追加
- [`src/backend/routers/easy_mode.py`](src/backend/routers/easy_mode.py): `from src.backend import database` 形式へ統一 (テスト時 engine 差替え対応)
- `pyproject.toml`: pytest `asyncio_mode=auto`, `-q --tb=short --strict-markers`
- `requirements-dev.txt`: `pytest-cov`, `httpx`, `python-json-logger` 追加

### 削除
- 不要な空 stub パッケージ (`pydantic/`, `fastapi/`, `huey/`, `sqlalchemy/`) を削除 (sys.path 衝突回避)

### テスト結果
- pytest: 9 passed (バックエンド)
- フロントエンド: typecheck / lint / test:ci は CI 上で実行

## [0.1.0] - 初期リリース

FastAPI + SQLAlchemy + Huey の最小構成。easy_mode ルータープロトタイプ、Book/Chapter/Character/Plot/Bible モデル定義。
