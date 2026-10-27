# AutoNovel T6 是正計画書【残り穴埋め18ステップ】

- **文書ID**: PLAN_T6_REMEDIATION_18STEPS
- **作成日**: 2026-09-29
- **前提文書**: [PLAN_V53_V6_INTEGRATED_36STEPS.md](PLAN_V53_V6_INTEGRATED_36STEPS.md)（以下「親計画」）
- **対象バージョン**: AutoNovel v5.3.0 → v6.0.0
- **ステータス**: 未着手
- **目的**: 親計画36ステップの実装評価で残った欠陥を、低性能LLMでも確実に完遂できる粒度に分割して是正する。

---

## 0. この計画書の位置づけ

親計画36ステップは**コード修正のほぼ全部が実現済み**（C0/C1系、horizon 0、CAS遷移、監査並列化、スコア集約ゲート、
Layer2バジェット、背景伏線供給など）。残る穴は **「ダミー実装」「二重実行」「未計測」「バージョン不整合」** に集中している。

本計画は **1ステップ = 1ファイル主担当 + 検証コマンド1本** に分割し、各ステップが
**他のステップに依存せず、途中で中断しても壊れない** ことを保証する。

### 0.1 分割原則（低性能LLM向け）

| 原則 | 内容 |
|---|---|
| **P1 単一ファイル** | 1ステップで触る**主要ファイルは高々1つ**。2ファイル以上になる場合は分割する |
| **P2 機械的置換のみ** | ロジック設計を要求しない。`str.replace` / 正規表現で完了する_changesのみ |
| **P3 判定が1行** | 「完了判定」は `pytest ... -q` が緑か赤かのみ。数値の解釈をLLMにさせない |
| **P4 テスト先行** | 回帰テストを**先に作り、赤くなることを確認してから** 実装する |
| **P5 ロールバック可能** | 機能フラグは**既存パターン**（`os.environ` 読み → 既定値）に従う。新仕組みquakeいらない |
| **P6 猜测禁止** | 対象ファイルの行番号・関数名を必ず grep で確認してから編集する。記憶で編集しない |

### 0.2 実行順序の依存関係

```
  Step 1 ─┐
  Step 2 ─┼─→ Step 3 ──→ Step 4 ──→ Step 5
          │   (logger)   (自己診断)  (integration)
  Step 6 ─┤
  Step 7 ─┤
  Step 8 ─┼─→ Step 9 ──→ Step 10 ──→ Step 11 ──→ Step 12
  Step 9 ─┤  (deprecate)  (version)   (ruff)    (回帰)
  ...     │
  Step 13 ┤  Step 14 ┐
  Step 14 ┘  Step 15 ┼─→ Step 16 ──→ Step 17 ──→ Step 18
  Step 15 ┘  Step 16 ┘
```

- **Step 1〜8 は完全に独立**。順序を 마음대로 바꿔よい。
- **Step 9 → 10 → 11 → 12** は直列（version → ruff → 回帰 の順）。
- **Step 13〜16 は独立**。**Step 16 → 17 → 18** は直列。

---

## 1. 残存欠陥一覧（本計画の対象）

| ID | 深刻度 | 内容 | 担当Step |
|:---|:---|:---|:---|
| R01 | Critical | `_post_episode_finalize` が `run()` と `write_beat_to_scene()` の**両方で実行**され、1話あたりダイジェスト生成LLMが2回分コスト発生 | 1 |
| R02 | Critical | `hasattr(self, "logger")` が全コードで **False**（`BaseAgent` はモジュールレベル `logger` のみ）。`episode_writer.py` に15箇所、`context_builder_agent.py` に10箇所の警告が**永久に無言化** | 2 |
| R03 | Critical | バージョンが矛盾。`CHANGELOG.md` に `[6.0.0]` があるのに `pyproject.toml:3` = `5.3.0`、README も 5.3.0。`test_v5_version_consistency.py` は pyproject を正準とするため自己矛盾 | 9 |
| R04 | Critical | `ruff check src tests` が **2460 エラー**。今回変更ファイルも全てエラーあり | 10 |
| R05 | Major | `IllustrationAgent` は `no-op` 化したが `artifacts["request"]` 供給元が**依然存在せず**、`next_agent=None` のため後続 `MARKETING` に到達しない | 4 |
| R06 | Major | `MODEL_PRICING` が**モデル単位のみ**。per-skill 単価なし。**未知モデルは黙って $0.00** で報告 | 5 |
| R07 | Major | 1話あたりUSDを出す **CLI が存在しない**（pytest の `print` のみ）。`TokenTracker.get_total_cost_usd` は**テストからしか呼ばれていない** | 6 |
| R08 | Major | `_resolve_session` が**定義されているがどこからも呼ばれていない**。元の食い違う2箇所が残存 | 3 |
| R09 | Major | `LocalPolisher.polish` が**同期・モジュールグローバル `call_llm_api` 呼び**で、注入された追跡可能LLMをバイパス。`audit_agent.py:760` は `await` なし | 7 |
| R10 | Major | 効果測定表が**未作成**。1話あたりLLM回数・監査レイテンシ・再生成比率・USD が**リポジトリ内に実在しない** | 13,14 |
| R11 | Minor | `agent.py:359,505` が `update_chapter_content(chapter.id, ...)` と呼ぶが実引数は `(branch_id, ep_num, content)` → runtime で無言の書き込み失敗 | 8 |
| R12 | Minor | `test_quality_score_not_degraded_vs_baseline` の baseline が**ハードコード `legacy_ratio = 1.0`**（tautology）。`test_severity_weighting_ranks_failures` は定数のみアサート | 12 |

---

## 2. 18ステップ

---

### Step 1. `_post_episode_finalize` の二重実行を排除する
- **対象ファイル**: `src/agents/writing/episode_writer.py`
- **依存**: なし
- **P分類**: P1（1ファイル）

**背景**
```
episode_writer.py:454  if use_beat_to_scene:  →  write_beat_to_scene()
episode_writer.py:286   await self._post_episode_finalize(...)   ← 第1回
episode_writer.py:552   await self._post_episode_finalize(...)   ← 第2回（run() 側）
```
`run()` → `write()` → `write_beat_to_scene()` → finalize、**その後** `run()` が finalize を再度呼ぶ。
ダイジェスト生成は1話1回のブロッキングLLM呼出（約2500字入力）なので、**実コストが2倍**。

**作業内容**
1. `write_beat_to_scene()` 末尾（`episode_writer.py:286`）の `_post_episode_finalize` 呼び出しを削除する。
2. 代わりに、`write_beat_to_scene()` の**呼び出し元を1箇所だけ**にするため、`run()` 側（`:552`）を唯一の実行点として残す。
3. ただし `use_beat_to_scene=False` 経路（`write()` の else 側）も `run()` を通るため、**:552 の1箇所だけで両経路をカバーできる**ことを確認する。
4. `:280-285` のコメント（「beat-to-scene 経路でも実行する」旨）を、実装に合わせて書き換える。

**回帰テスト（先に作る）**: `tests/unit/writing/test_episode_finalize_called_once.py`（新規）

```python
"""1話につき _post_episode_finalize が必ず1回だけ呼ばれることの回帰テスト。"""
import pytest


@pytest.mark.asyncio
async def test_finalize_called_exactly_once_on_beat_to_scene_path(monkeypatch):
    """use_beat_to_scene=True の既定経路で finalize が二重実行されないこと。"""
    writer = _make_writer()                       # ローカルヘルパで最小構成を生成
    calls = []
    monkeypatch.setattr(
        writer, "_post_episode_finalize",
        _recorder(calls),
    )
    await writer.run(_make_ctx(ep_num=1, use_beat_to_scene=True))
    assert len(calls) == 1, f"finalize が {len(calls)} 回呼ばれた（1回であるべき）"


@pytest.mark.asyncio
async def test_finalize_called_exactly_once_on_legacy_path(monkeypatch):
    """use_beat_to_scene=False の旧経路でも finalize がちょうど1回であること。"""
    writer = _make_writer()
    calls = []
    monkeypatch.setattr(writer, "_post_episode_finalize", _recorder(calls))
    await writer.run(_make_ctx(ep_num=1, use_beat_to_scene=False))
    assert len(calls) == 1


@pytest.mark.asyncio
async def test_finalize_receives_split_path_text(monkeypatch):
    """beat-to-scene 経路でも run() 側へ統合後のテキストが渡ること。"""
    writer = _make_writer()
    seen = {}
    monkeypatch.setattr(
        writer, "_post_episode_finalize",
        async def **kw: seen.update(kw),
    )
    await writer.run(_make_ctx(ep_num=1, use_beat_to_scene=True))
    assert seen["written_text"], "written_text が空では finalize に渡せない"
    assert seen["ep_num"] == 1
```

> 実装者への注意: `_make_writer` / `_make_ctx` / `_recorder` は
> `tests/e2e/test_v53_long_form_wiring_e2e.py` の既存ヘルパを**そのまま流用**してよい。
> 新しく発生させなくてよい。LLMは `MagicMock` でよい。

**検証コマンド**
```powershell
C:\Python314\python.exe -m pytest tests/unit/writing/test_episode_finalize_called_once.py -v
```

**完了判定**: 3テスト緑。かつ `pytest tests/e2e/test_v53_long_form_wiring_e2e.py -q` も緑（回帰なし）。

---

### Step 2. `hasattr(self, "logger")` を全置換する
- **対象ファイル**: `src/agents/writing/episode_writer.py`、`src/agents/context_builder_agent.py`
- **依存**: なし
- **P分類**: P1（2ファイルだが**置換のみ**。P2 の例外）

**背景**
`src/agents/base.py:9` は **モジュールレベル** `logger` のみ定義。クラスに `self.logger` は**存在しない**。
よって以下の25箇所の `if hasattr(self, "logger"):` は**常に False** で、警告が永久に無言化する。

```powershell
# 確認コマンド（実装前に必ず実行）
Select-String -Path src/agents/writing/episode_writer.py,src/agents/context_builder_agent.py -Pattern 'hasattr\(self, "logger"\)'
```

**作業内容**
1. 各ファイルに `from src.agents.base import logger` が**既にあれば確認**、無ければ追加する。
2. 機械的に以下の置換を**全件**に適用する。
   - `if hasattr(self, "logger"):` → `if True:` は**使わない**。代わりに本体のみ残す。
   - 手順: `hasattr(self, "logger"):` の行を削除し、その下の本体を**1段だけデデント**して残す。
3. `self.logger.info(` → `logger.info(`、`self.logger.warning(` → `logger.warning(`、
   `self.logger.debug(` → `logger.debug(` に全置換。
4. 置換後、`episode_writer.py` と `context_builder_agent.py` に `hasattr(self, "logger")` が
   **残っていないこと**を grep で確認する。

**回帰テスト**: `tests/unit/agents/test_logger_guards_regression.py`（新規）

```python
"""`hasattr(self, "logger")` のデッドガードが復活していないことの回帰テスト。"""
import ast
from pathlib import Path

TARGETS = [
    Path("src/agents/writing/episode_writer.py"),
    Path("src/agents/context_builder_agent.py"),
    Path("src/agents/audit_agent.py"),
]


def test_no_dead_logger_guard_remains():
    """`hasattr(self, "logger")` による無言化ガードが 1 件も存在しないこと。"""
    offenders = []
    for path in TARGETS:
        source = path.read_text(encoding="utf-8")
        tree = ast.parse(source)
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Name)
                and node.func.id == "hasattr"
                and node.args
                and isinstance(node.args[0], ast.Attribute)
                and node.args[0].attr == "logger"
            ):
                offenders.append(f"{path}:{node.lineno}")
    assert not offenders, f"デッドガードが残存: {offenders}"


def test_no_self_logger_attribute_access():
    """`self.logger.*` アクセスが残っていないこと（BaseAgent に属性は無い）。"""
    offenders = []
    for path in TARGETS:
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Attribute)
                and node.attr == "logger"
                and isinstance(node.value, ast.Name)
                and node.value.id == "self"
            ):
                offenders.append(f"{path}:{node.lineno}")
    assert not offenders, f"self.logger 参照が残存: {offenders}"


def test_deadlock_free_import_check():
    """2ファイルが import 层面的にも壊れていないこと。"""
    import importlib
    for mod in ("src.agents.writing.episode_writer", "src.agents.context_builder_agent"):
        importlib.import_module(mod)
```

> このテストは「**構造を検証する**」ため、将来谁かが `self.logger` を再導入したら即座に落ちる。
> 機能テストではないが、北極の欠陥の再発防止には最も効く。

**検証コマンド**
```powershell
C:\Python314\python.exe -m pytest tests/unit/agents/test_logger_guards_regression.py -v
```

**完了判定**: 3テスト緑。かつ grep で `hasattr(self, "logger")` が 0 件。

---

### Step 3. `_resolve_session` を実際に2箇所へ結線する
- **対象ファイル**: `src/services/episode_context.py`
- **依存**: なし
- **P分類**: P1

**背景**
Step 32 で「セッション解決の共通ヘルパー `_resolve_session` に抽出」と計画されたが、
`_resolve_session` は**定義されているだけでどこからも呼ばれていない**（死んだコード）。
元々は「伏線側は `or repo.session`、ダイジェスト側は `artifacts.get("session")` のみ」で**食い違っていた**。

**作業内容**
1. まず `episode_context.py` 内の `_resolve_session` 定義位置を確認する。
2. ダイジェスト読込と伏線読込の**2つの呼び出し元**をMackriftし、それぞれを `_resolve_session(...)` 経由に置き換える。
3. `_resolve_session` を使わない `or repo.session`  Burkissen 形式の残存が無かったか grep で確認する。
4. 呼び出しが**1箇所だけ**だった場合、`_resolve_session` を**削除**して「ヘルパー無し」に戻す判断も可。
   ただし本計画では「結線」方向を採る（可読性のため）。

**回帰テスト**: `tests/unit/services/test_episode_context_session_resolution.py`（新規）

```python
"""セッション解決が一意に定まることの回帰テスト。"""
from src.services.episode_context import EpisodeContextBuilder


def test_resolve_session_is_actually_used():
    """`_resolve_session` が定義だけでなく、本文中の呼び出しATTRを持つこと。

    ステップ3で結線し忘れると必ず落ちるテスト。
    """
    import ast
    from pathlib import Path

    path = Path("src/services/episode_context.py")
    tree = ast.parse(path.read_text(encoding="utf-8"))
    calls = [
        n.lineno
        for n in ast.walk(tree)
        if isinstance(n, ast.Call)
        and isinstance(n.func, ast.Attribute)
        and n.func.attr == "_resolve_session"
    ]
    assert len(calls) >= 2, (
        f"_resolve_session の呼び出しが {len(calls)} 箇所しか無い"
        "（2箇所: ダイジェスト読込 / 伏線読込 のはず）"
    )


async def test_resolve_session_prefers_artifacts_session():
    builder = EpisodeContextBuilder(db=None)
    sentinel = object()
    got = builder._resolve_session({"session": sentinel}, None)
    assert got is sentinel


async def test_resolve_session_falls_back_to_repo():
    builder = EpisodeContextBuilder(db=None)

    class _Repo:
        session = "REPO_SESSION"

    got = builder._resolve_session({}, _Repo())
    assert got == "REPO_SESSION"


async def test_resolve_session_returns_none_when_absent():
    builder = EpisodeContextBuilder(db=None)
    assert builder._resolve_session({}, None) is None
```

> 実装者は `EpisodeContextBuilder` の実際の `__init__` シグネチャを
> 先に確認し、必要ならテスト側の生成引数を合わせること。**シグネチャは記憶で書かない。**

**検証コマンド**
```powershell
C:\Python314\python.exe -m pytest tests/unit/services/test_episode_context_session_resolution.py -v
```

**完了判定**: 4テスト緑。

---

### Step 4. `IllustrationAgent` の後続チェーン断線を解消する
- **対象ファイル**: `src/agents/illustration_agent.py`
- **依存**: なし
- **P分類**: P1

**背景**
`src/backend/tasks/generation_tasks.py:253-267` は `ILLUSTRATION` → `MARKETING` の順に登録する。
`IllustrationAgent.execute` は `request is None` のとき `next_agent=None` を返すため、
`src/agents/orchestrator.py:808` の `current = result.next_agent` が `None` になり、
**`MarketingAgent` に到達しない**（親計画の K4 が未解決のまま）。

**判断（記録）**
- 親計画 Step 11 は「(A) request を生成して挿絵 vocation」または「(B) no-op 終了」の2案を提示した。
- 既に **(B) が実装済み**。残るのは「no-op でも**後続チェーンを止めない**」という契約の修正のみ。
- **(A) の実装（挿絵生成のFedral wiring）は本計画の対象外**。別途 Issue 化する。

**作業内容**
1. `illustration_agent.py` の `execute` を確認verbsし、`request is None` 時の `next_agent` を
   `None` ではなく **`"MARKETING"`**（実定数は orchestrator のレジストリ名）に変更する。
2. ただし `next_agent` に**名前文字列**を渡してよい仕様か、`AgentResult` 型が
   `str | Agent | None` を許すかを**必ず型定義で確認**する。許さなければ
   `next_agent=ILLUSTRATION_NEXT_AGENT_NAME` の定数を使う形に組み替える。
3. 既に登録済みの後続エージェントが**存在しない**場合（manifest 経路で `runs_before: []` のとき）は
   `next_agent=None` のままでもよい。分岐は「後続が登録されているか」で判定する。

**回帰テスト**: `tests/unit/agents/test_illustration_agent_chain.py`（新規）

```python
"""IllustrationAgent が後続チェーンを止めないことの回帰テスト。"""
import pytest


@pytest.mark.asyncio
async def test_illustration_agent_does_not_break_chain_when_no_request():
    """request 未設定でも error=None かつ後続へ進めること（K4 の回帰防止）。"""
    from src.agents.illustration_agent import IllustrationAgent

    agent = IllustrationAgent(llm=None, repo=None)
    ctx = _make_ctx()          # artifacts に "request" を持たない
    result = await agent.execute(ctx)

    assert result.error is None, f"unexpected error: {result.error}"
    assert result.artifacts.get("illustration_skipped") is True
    assert result.next_agent is not None, (
        "no-op でも next_agent=None を返すと orchestrator がループを終了し、"
        "後続スキルが未実行になる（K4 の再発）"
    )


@pytest.mark.asyncio
async def test_illustration_agent_does_not_consume_whole_chain_via_orchestrator():
    """orchestrator 経由で実行しても後続エージェントが到達されること。"""
    from src.agents.orchestrator import AgentOrchestrator

    # orchestrator を最小構成で組み立て、ILLUSTRATION→MARKETING の
    # 2段チェーンで MARKETING まで到達することをアサートする。
    # 既存 tests/unit/test_orchestrator.py の fixture を流用すること。
    ...
```

**検証コマンド**
```powershell
C:\Python314\python.exe -m pytest tests/unit/agents/test_illustration_agent_chain.py -v
C:\Python314\python.exe -m pytest tests/unit/test_orchestrator.py -q
```

**完了判定**: `next_agent` の非 None が保証され、後続チェーンのテストが緑。

---

### Step 5. `MODEL_PRICING` の未知モデルを可視化する
- **対象ファイル**: `src/config/cost_optimization.py`
- **依存**: なし
- **P分類**: P1

**背景**
`cost_optimization.py:6-11` の `MODEL_PRICING` は**モデル単位のみ**。
未知のモデルは `token_tracker.py:205-206` で**黙って $0.00** として報告される。
モデルルーティングを有効化すると、**未知モデルに切り替わった瞬間にコスト計測が無言でゼロになる**。
これは Step 6（CLI 整備）の前提になるため先に潰す。

> 親計画 Step 2 の「スキル別USD算出」自体は、`MODEL_PRICING` に per-skill を足すのではなく
> `token_tracker` の `task_type` キーで**集約**する設計で既に充足している。本ステップで
> 追加するのは**未知モデルの検出**のみ。

**作業内容**
1. `cost_optimization.py` に `class UnknownModelPricingError(ValueError)` を追加する。
2. `resolve_pricing(model: str) -> dict` を追加する。`MODEL_PRICING` に無いモデルは
   **例外を投げる**（null を返さない）。
3. `src/services/token_tracker.py:205-206` の呼び出し箇所を `resolve_pricing` に置き換える。
4. **後方互換のため**、`token_tracker` 側は `try/except UnknownModelPricingError` で囲み、
   例外時は **0 を返しつつ `logger.warning` を1回だけ出す** ようにする
   （1行ごとに警告を出し続きにしない）。

**回帰テスト**: `tests/unit/test_cost_optimization_pricing.py`（新規）

```python
"""未知モデルの価格解決が黙って0にならないことの回帰テスト。"""
import pytest

from src.config.cost_optimization import UnknownModelPricingError, resolve_pricing


def test_known_model_resolves():
    pricing = resolve_pricing("claude-3-5-haiku")
    assert pricing["input"] > 0
    assert pricing["output"] > 0


def test_unknown_model_raises_instead_of_zero():
    with pytest.raises(UnknownModelPricingError):
        resolve_pricing("totally-unknown-model-xyz")


def test_unknown_model_is_reported_by_tracker(caplog):
    """tracker は後方互換のため0を返すが、warningを1回出すこと。"""
    from src.services.token_tracker import TokenTracker

    tracker = TokenTracker()
    with caplog.at_level("WARNING"):
        cost = tracker._price("totally-unknown-model-xyz", 1000, 500)
    assert cost == 0.0
    assert any("totally-unknown-model-xyz" in r.message for r in caplog.records), (
        "未知モデルのコストが0のまま警告も出ないのは計測の無言化"
    )
```

**検証コマンド**
```powershell
C:\Python314\python.exe -m pytest tests/unit/test_cost_optimization_pricing.py -v
C:\Python314\python.exe -m pytest tests/unit/test_cost_optimization.py -q
```

**完了判定**: 4テスト緑。`test_cost_optimization.py` 既存に回帰なし。

---

### Step 6. 1話あたりコスト計測 CLI を新設する
- **対象ファイル**: `scripts/report_episode_cost.py`（新規）
- **依存**: Step 5（`resolve_pricing` を使うため）
- **P分類**: P1

**背景**
親計画 Step 27 の「効果測定レポート（1話あたりUSD）を出力するCLIを整備する」が**未達**。
現状は `tests/perf/test_v6_llm_call_budget.py:182` の `print` のみで、
`TokenTracker.get_total_cost_usd` / `get_task_breakdown` / `get_tier_breakdown` は
**テストからしか呼ばれていない**（本番呼び出し元なし）。

**作業内容**
1. `scripts/report_episode_cost.py` を新規作成する。
2. 以下の CLI を持たせる。

   ```powershell
   C:\Python314\python.exe scripts/report_episode_cost.py --db <sqlite path> --book-id 1
   C:\Python314\python.exe scripts/report_episode_cost.py --json
   ```

3. 出力は1話ごとに以下を含める（**requirements  Gorgeous**）。
   | 列 | 出典 |
   |---|:---|
   | `ep_num` | token_usage レコード |
   | `total_cost_usd` | `TokenTracker.get_total_cost_usd` |
   | `by_task` | `TokenTracker.get_task_breakdown` |
   | `by_tier` | `TokenTracker.get_tier_breakdown` |
   | `llm_calls` | `TokenTracker` の呼び出しカウンタ |
4. `--json` フラグで機械可読出力（Step 13 の測定表生成がこれを読む）。

> **低性能LLMへの注意**: このスクリプトは「JSONを整形して印字するだけ」。
> 集計ロジックを**再実装しない**こと。必ず `TokenTracker` の既存メソッドを呼ぶ。

**回帰テスト**: `tests/unit/scripts/test_report_episode_cost.py`（新規）

```python
"""コスト計測CLIが正しいJSON構造を返すことの回帰テスト。"""
import json
import subprocess
import sys
from pathlib import Path


def test_cli_emits_valid_json(tmp_path):
    """--json フラグで機械可読な出力が得られること。"""
    out = tmp_path / "cost.json"
    result = subprocess.run(
        [sys.executable, "scripts/report_episode_cost.py", "--json"],
        capture_output=True, text=True, cwd=Path.cwd(),
    )
    assert result.returncode == 0, f"CLI が失敗: {result.stderr}"
    payload = json.loads(result.stdout)
    assert "episodes" in payload, "episodes キーが無い"
    assert isinstance(payload["episodes"], list)


def test_report_keys_are_stable(tmp_path):
    """1話レポートの必須キーが揃っていること（出力契約の固定）。"""
    from scripts.report_episode_cost import build_episode_row

    row = build_episode_row({
        "ep_num": 1,
        "input_tokens": 1000,
        "output_tokens": 500,
        "model": "claude-3-5-haiku",
        "task_type": "audit",
        "tier": "tier1_light",
    })
    assert set(row) >= {"ep_num", "total_cost_usd", "by_task", "by_tier", "llm_calls"}
```

**検証コマンド**
```powershell
C:\Python314\python.exe -m pytest tests/unit/scripts/test_report_episode_cost.py -v
C:\Python314\python.exe scripts/report_episode_cost.py --json
```

**完了判定**: CLI が JSON を出力し、テストが緑。

---

### Step 7. `LocalPolisher` の LLM バイパスを解消する
- **対象ファイル**: `src/generation/local_polish.py`
- **依存**: なし
- **P分類**: P1

**背景**
`local_polish.py:93` が**モジュールグローバル** `call_llm_api` を呼ぶ同期メソッドである。
`audit_agent.py:760-764` はこれを `await` せずに呼ぶため、
**注入された `llm` / `TokenTracker` を完全にバイパス**し、計測されない LLM 呼出になる。
親計画 Step 25「局所パッチ化」がコスト観点で成立していない。

**作業内容**
1. `local_polish.py` の `polish()` シグネチャを確認し、`llm` を受け取れる形に拡張する。
   既存は `polish(self, ...)` なので、`llm: Any = None` を**後方互換の位置引数**で追加する。
2. `llm` が渡された場合は**注入된 llm のみ**を使い、グローバル `call_llm_api` は使わない。
3. `llm` が `None` の場合は**グローバルへフォールバック**して従来挙動を維持する
   （既存テストを壊さないため）。
4. `src/agents/audit_agent.py:760-764` の呼び出しで、`self.llm`（または利用可能な llm）を渡す。
5. 归来った後、Step 6 の CLI が local_polish も計測対象に含められることを確認する。

**回帰テスト**: `tests/unit/services/test_local_polisher_llm_injection.py`（新規）

```python
"""LocalPolisher が注入 LLM を使い、グローバル関数を呼ばないことの回帰テスト。"""
import pytest


@pytest.mark.asyncio
async def test_polish_uses_injected_llm(monkeypatch):
    """注入された llm のみが使用され、グローバル未被_arm がないこと。"""
    import src.generation.local_polish as mod

    called = {"global": 0, "injected": 0}

    def _boom(*a, **k):
        called["global"] += 1
        raise AssertionError("グローバル call_llm_api が呼ばれた（バイパス）")

    monkeypatch.setattr(mod, "call_llm_api", _boom)

    class _FakeLLM:
        async def generate_text(self, prompt, **k):
            called["injected"] += 1
            return "修正済み"

    polisher = mod.LocalPolisher()
    out = await polisher.polish(
        text="原文", conflicts=[], llm=_FakeLLM(),
    )
    assert called["injected"] >= 1
    assert called["global"] == 0


@pytest.mark.asyncio
async def test_polish_falls_back_when_llm_missing(monkeypatch):
    """llm=None のとき従来挙動（グローバル）が維持されること。"""
    import src.generation.local_polish as mod

    async def _fake_global(*a, **k):
        return "fallback"

    monkeypatch.setattr(mod, "call_llm_api", _fake_global)
    polisher = mod.LocalPolisher()
    out = await polisher.polish(text="原文", conflicts=[])
    assert out == "fallback"
```

**検証コマンド**
```powershell
C:\Python314\python.exe -m pytest tests/unit/services/test_local_polisher_llm_injection.py -v
C:\Python314\python.exe -m pytest tests/unit/services/test_local_polisher.py -q
```

**完了判定**: 2新規テスト緑 + 既存 `test_local_polisher.py` に回帰なし。

---

### Step 8. `update_chapter_content` の引数シグネチャ不整合を修正する
- **対象ファイル**: `src/agents/writing/agent.py`
- **依存**: なし
- **P分類**: P1

**背景**
`agent.py:359` と `:505` が
```python
self.repo.update_chapter_content(chapter.id, rewritten_text)
```
と呼ぶが、`ChapterRepository.update_chapter_content` の実シグネチャは
**`(branch_id, ep_num, content)`** である。
→ **1章の本文を id ではなく branch_id として渡す**ため、runtime で無言の誤書き込みまたは
`TypeError` になる（親計画外の既存バグだが、R04 系の「無言化」系なので一緒に潰す）。

**作業内容**
1. まず `ChapterRepository.update_chapter_content` の実シグネチャを grep で**必ず確認**する。
2. `agent.py:359` / `:505` の呼び出しを、実引数に合わせて修正する。
3. その周辺で `chapter` 変数が何を保持しているかを確認し、`branch_id` / `ep_num` を
   取得する方法を**既存コードから**探す（新しいクエリをDont 書かない）。
4. 両箇所を直した後、1度の実行で**両方が同じ章を指す**ことを確認する。

**回帰テスト**: `tests/unit/agents/test_update_chapter_content_call.py`（新規）

```python
"""update_chapter_content が実シグネチャ通り_called されることの回帰テスト。"""
import inspect
from unittest.mock import MagicMock


async def test_agent_calls_update_chapter_content_with_correct_args(monkeypatch):
    """引数順が (branch_id, ep_num, content) であること。"""
    from src.infrastructure.repositories.chapter import ChapterRepository

    sig = list(inspect.signature(ChapterRepository.update_chapter_content).parameters)
    assert sig[:3] == ["branch_id", "ep_num", "content"], (
        f"リポジトリのシグネチャが変わった: {sig}"
    )

    # agent.py の該当箇所が同じ順序で呼んでいることを spies で確認する
    from src.agents.writing.agent import WritingAgent

    agent = WritingAgent(repo=MagicMock(), llm=MagicMock())
    recorded = {}
    agent.repo.update_chapter_content = lambda *a, **k: recorded.update(
        args=a, kwargs=k
    )
    # ... agent.py:359 付近のコードパスを実行 ...
    # 記録された引数が (branch_id, ep_num, content) であることを確認
```

**検証コマンド**
```powershell
C:\Python314\python.exe -m pytest tests/unit/agents/test_update_chapter_content_call.py -v
C:\Python314\python.exe -m pytest tests/unit/test_writing_workflow.py -q
```

**完了判定**: テスト緑 + 既存執筆系テストに回帰なし。

---

### Step 9. バージョンを v6.0.0 に昇格する
- **対象ファイル**: `pyproject.toml`、`README.md`
- **依存**: なし
- **P分類**: P1

**背景**
`CHANGELOG.md:5` に `[6.0.0] - 2026-09-28` エントリがある一方、
`pyproject.toml:3` は `version = "5.3.0"`、`README.md:9` も `version-5.3.0`。
`tests/regression/test_v5_version_consistency.py:46-52` が pyproject を**正準**とするため、
6.0.0 の CHANGELOG を持つ 5.3.0 プロジェクトという**自己矛盾**になっている。
（同テストは現状緑だが、矛盾が潜在化しており脆い。）

**作業内容**
1. `pyproject.toml:3` の `version` を `"6.0.0"` に変更する。
2. `README.md:9` のバージョン表記を `version-6.0.0` に変更する。
3. `tests/regression/test_v5_version_consistency.py` に「CHANGELOG の最新エントリが
   pyproject の version と一致する」アサーションがあるか確認し、無ければ**追加**する。
4. Step 16（全体回帰）で version 一致テストが通ることを確認する。

**回帰テスト**: `tests/regression/test_v6_version_consistency.py`（新規）

```python
"""pyproject / README / CHANGELOG のバージョンが一致することの回帰テスト。"""
import re
import tomllib
from pathlib import Path


def test_pyproject_version_is_v6():
    data = tomllib.loads(Path("pyproject.toml").read_text(encoding="utf-8"))
    assert data["project"]["version"] == "6.0.0"


def test_readme_version_matches_pyproject():
    readme = Path("README.md").read_text(encoding="utf-8")
    data = tomllib.loads(Path("pyproject.toml").read_text(encoding="utf-8")
    assert f"version-{data['project']['version']}" in readme


def test_changelog_has_top_entry_for_current_version():
    changelog = Path("CHANGELOG.md").read_text(encoding="utf-8")
    data = tomllib.loads(Path("pyproject.toml").read_text(encoding="utf-8")
    top = re.search(r"^##\s*\[(\d+\.\d+\.\d+)\]", changelog, re.MULTILINE)
    assert top is not None, "CHANGELOG .EXPECT なエントリ"
    assert top.group(1) == data["project"]["version"], (
        f"CHANGELOG 先頭は {top.group(1)} だが pyproject は "
        f"{data['project']['version']}"
    )
```

**検証コマンド**
```powershell
C:\Python314\python.exe -m pytest tests/regression/test_v6_version_consistency.py -v
C:\Python314\python.exe -m pytest tests/regression/test_v5_version_consistency.py -q
```

**完了判定**: 3テスト緑 + 既存 version consistency に回帰なし。

---

### Step 10. `ruff check` を緑にする
- **対象ファイル**: Step 9 で確定した変更ファイル群
- **依存**: Step 9
- **P分類**: P1（ただし**機械的のみ**）

**背景**
`ruff check src tests` が **2460 エラー**。親計画 Step 36 の項目1（lint）を満たしていない。
 대부분は自動修正可能（`2083 fixable`）。

**作業内容**
1. **自動修正を先にBulkで**適用する。
   ```powershell
   C:\Python314\python.exe -m ruff check src\ tests\ --fix
   ```
2. 残った非自動修正エラーを**ファイル単位で**処理する。
   優先度順:
   - 本計画 Step 1-9 で変更したファイルのエラー → **全て解消する**
   - 他ファイルの自動修正可能なもの → `--fix` で解消
   - 残るもの → `# noqa: <code>` を**理由をコメント付きで**付与（**消さない**）
3. `pyproject.toml` の `[tool.ruff]` で、意図的に除外するルールを明示する。
   ただし **除外は最小限**に留める（大量除外は「lint を無効化した」だけとみなす）。
4. `scripts/lint.ps1` が存在する場合は、そこの ruff 呼び出しも確認する。

**回帰テスト**: 既存 `tests/regression/test_repo_hygiene.py` が lint チェックを含むか確認し、
含まない場合のみ以下を**新規追加**する（`--fix` 後の自動整形が再導入されないようにする）。

```python
"""ruff check が0件であること（自動整形の巻き戻し防止）。"""
import subprocess
import sys


def test_ruff_is_clean():
    result = subprocess.run(
        [sys.executable, "-m", "ruff", "check", "src", "tests"],
        capture_output=True, text=True, cwd=Path.cwd(),
    )
    assert result.returncode == 0, (
        f"ruff check が {result.stdout.count('error')} 件のエラーを報告:\n"
        f"{result.stdout[:2000]}"
    )
```

**検証コマンド**
```powershell
C:\Python314\python.exe -m ruff check src\ tests\ --fix
C:\Python314\python.exe -m ruff check src\ tests\
```

**完了判定**: `ruff check src tests` の出力が `All checks passed!`。
`Found 0 errors` なら合格。

---

### Step 11. `hasattr(self,"logger")` 除去の副作用を統合テストで固定する
- **対象ファイル**: `tests/integration/test_writing_pipeline_observability.py`（新規）
- **依存**: Step 2
- **P分類**: P1

**背景**
Step 2 で 25 箇所のデッドガードを機械置換した。
**置換が正しく行われたか**をgrepではなく**機能**で証明する必要がある。
同時に、Step 2 で「デッドコードを消した」ことで**Thought隠れていたバグが表面化する**可能性がある
（例: `context_builder_agent.py:499` のセッション型不一致警告がlung其实是**本物の TypeError**）。

**作業内容**
1. 実 SQLite + モック LLM で 1 话を `EpisodeWriter.run()` まで走らせる統合テストを作る。
2. ログキャプチャ（`caplog`）で、以下の**少なくとも1つ**が `WARNING` として出力されることを確認する。
   - セッション型不一致（`ContextBuilderAgent` が同期 session を受けた場合）
   - ダイジェスト生成失敗
   - 伏線回収の per-item 失敗
3. 出力されるはずの警告が**出ない**（=握り潰しが再導入された）場合にテストが赤くなることを保証する。
4. Step 2 で表面化した実バグがあれば、**本ステップではログを出すだけでよい**。
   実修正は本計画外（Issue 化）。

**回帰テスト**: 上記本身就是本ステップの成果物

```python
"""警告が実際にログへ出ることの統合回帰テスト。"""
import logging
import pytest


@pytest.mark.asyncio
async def test_session_type_mismatch_is_actually_logged(caplog, ...):
    """同期 session を渡すと warning が実際に記録されること。"""
    caplog.set_level(logging.WARNING)
    ...  # 同期 session を渡して ContextBuilderAgent を実行
    assert any("session" in r.message.lower() for r in caplog.records), (
        "セッション型不一致の warning がログに出ていない"
        "（hasattr(self,'logger') デッドガードの复发）"
    )


@pytest.mark.asyncio
async def test_digest_failure_is_actually_logged(caplog, ...):
    """ダイジェスト永続化の失敗が握り潰されず warning になること。"""
    caplog.set_level(logging.WARNING)
    ...  # session を無効化して 1 话を走らせる
    assert caplog.records, "ダイジェスト失敗が無言化された"
```

**検証コマンド**
```powershell
C:\Python314\python.exe -m pytest tests/integration/test_writing_pipeline_observability.py -v
```

**完了判定**: 2テスト緑。

---

### Step 12. ゲート閾値テストの tautology を解消する
- **対象ファイル**: `tests/contract/test_v6_audit_gate_thresholds.py`
- **依存**: なし
- **P分類**: P1

**背景**
2つのテストが**何も検証していない**。
| テスト | 問題 |
|---|:---|
| `test_quality_score_not_degraded_vs_baseline` (`:341-346`) | `legacy_ratio = 1.0` が**ハードコード**。`score_ratio < 1.0` は「少なくとも1パターンは引き続き失敗する」ことしか言っていない |
| `test_severity_weighting_ranks_failures` (`:355-369`) | **モジュール定数のみ**をアサート。プロダクション経路を一切通さない |

**作業内容**
1. `test_quality_score_not_degraded_vs_baseline` を書き直す。
   - baseline を**実測**から算出する。具体的には：
     同じ入力セットに対し `ENABLE_AUDIT_SCORE_GATE=0`（旧 all-or-nothing）と
     `ENABLE_AUDIT_SCORE_GATE=1`（新スコア集約）の**両方で** `agent.execute()` を走らせ、
     `aggregate_score` の分布を比較する。
   - 主張する内容を「再生成比率が下がり、かつ aggregate_score の平均が低下しない」に変更する。
   - **再度ハードコード禁止**。比率の期待値は「1.0 より小さい」等の**構造的性質**にする。
2. `test_severity_weighting_ranks_failures` を書き直す。
   - 実際の `WEIGHT` 定数が**ゲート計算に本当に使われている**ことを、
     異なる `severity` の入力で `aggregate_score` が変わることを観測して証明する。
   - 定数の値を直接アサートするだけのテストは**削除**する。
3. `test_audit_latency_is_reduced`（`:251`、既定スキップ）を**常時有効**にするか、
   ，最低限 CI での**1回実行**を必須にする仕組み（`RUN_LATENCY_TESTS` の既定を `1` にする）を入れる。
   常時有効が不安定な場合は「スキップ理由ではなく CI 設定で有効化」する方を選ぶ。

**回帰テスト**: これが本ステップの成果物（既存ファイルの上書き）

```python
def test_quality_score_not_degraded_vs_baseline(monkeypatch):
    """スコア集約化で aggregate_score が低下しないことを実測で証明する。"""
    # 同一入力で新方式・旧方式を実際に走らせ、分布を比較する
    new_scores = _run_all_patterns(gate_enabled=True)
    old_scores = _run_all_patterns(gate_enabled=False)

    mean_new = sum(new_scores) / len(new_scores)
    mean_old = sum(old_scores) / len(old_scores)
    assert mean_new >= mean_old, (
        f"集約化で品質スコアが低下: {mean_old:.1f} → {mean_new:.1f}"
    )


def test_severity_weighting_actually_affects_score():
    """severity 重みが実際のゲート計算に効くことを観測で証明する。"""
    minor = _score_with(severity="minor")
    critical = _score_with(severity="critical")
    assert critical < minor, (
        "severity がスコア計算に反映されていない"
        "（WEIGHT 定数の定義だけが変わっている疑い）"
    )
```

**検証コマンド**
```powershell
C:\Python314\python.exe -m pytest tests/contract/test_v6_audit_gate_thresholds.py -v
```

**完了判定**: 書き直した2テストが緑。かつ**元より弱いテストになっていることを確認しない**ため、
書き換え前後で**1つでもアサーションが減っていない**ことを自查する。

---

### Step 13. 1話あたりLLM回数の実測値を確定する
- **対象ファイル**: `tests/perf/test_v6_llm_call_budget.py`
- **依存**: Step 5, Step 6
- **P分類**: P1

**背景**
`tests/perf/test_v6_llm_call_budget.py:64-75` の `SKILL_LLM_CALLS` は
**ハードコードされた想定構造の辞書**であり、**実測値ではない**。
親計画 Step 36 の効果測定表の主要項目「1話あたりLLM呼び出し回数」が
**リポジトリ内に実在しない**。

**作業内容**
1. `SKILL_LLM_CALLS` の**ハードコードを削除**する。
2. 代わりに、`tracked_adapter` / 計装済みLLMゲートウェイの**カウンタから実測**する。
   - `src/services/llm/tracked_adapter.py:79-86` の `_record` が既に全呼出を計装している。
   - 1 话完走後に `TokenTracker` から**スキル別の呼出回数**を取得する。
3. 取得した値を pytest の出力に出す（`[実測] 1話あたりLLM呼出: N回`）。
4. 目標値（10 → 4-5）に対する**達成/未達を判定**し、結果を返す。
   - 未達の場合は**失敗させない**（計測が主目的）。ログに `ATTENTION` として出す。
5. 硬编码していた `SKILL_LLM_CALLS` への他参照が残っていないか grep で確認する。

**回帰テスト**: 既存ファイルの本ステップ分Assertion

```python
def test_llm_calls_per_episode_is_measured_not_hardcoded():
    """LLM回数が実測値であり、ハードコード辞書でないこと。"""
    from tests.perf.test_v6_llm_call_budget import measure_calls_per_episode

    calls = measure_calls_per_episode()
    assert isinstance(calls, int) and calls > 0
    assert calls > 0, "1話あたりのLLM回数が計測できていない"

    # 目標値との比較結果を必ず返す（未達でも fail しない）
    verdict = judge_against_target(calls, target_min=4, target_max=5)
    assert verdict["measured"] == calls
    assert verdict["meets_target"] in (True, False)
```

**検証コマンド**
```powershell
C:\Python314\python.exe -m pytest tests/perf/test_v6_llm_call_budget.py -v
```

**完了判定**: 1话あたりのLLM回数が**実測数値**としてログに出る。

---

### Step 14. 監査レイテンシの再生成比率を実測する
- **対象ファイル**: `tests/perf/test_v6_audit_latency_and_regen.py`（新規）
- **依存**: Step 12
- **P分類**: P1

**背景**
- **監査レイテンシ実測値が存在しない**（`test_audit_latency_is_reduced` は既定スキップ）。
- **本文再生成比率の実測値が存在しない**（`test_v6_audit_failure_rate.py:450-480` は
  **STUB 校正値**混じりの構造的推定で、LLM 実値ではない）。

親計画 §6 完了定義 #9（効果測定表を埋める）の残り2項目。

**作業内容**
1. `tests/perf/test_v6_audit_latency_and_regen.py` を新規作成する。
2. **監査レイテンシ**の実測を行う。
   - 同一の模擬入力に対し `run_audit_phase(..., parallel=False)` と `parallel=True` を各10回実行。
   - 中央値で報告し、並列化的效果（目標: 約1/5）を**判定**する。
   - 1/5に届いていない場合も**記録は残す**（fail はさせない）。
3. **再生成比率**を実測する。
   - 複数の模擬テキスト（plot / logical / deai / ability / plot_monitor の各軸で失敗を作る）に対し
     ゲートを通し、`requires_regeneration` が `True` になった割合を算出する。
   - 目標値（67% → 10%未満）との差を**レポート**する。
4. 結果を `docs/STATUS.md` に出力できる形で**整形**する（実際の追記は Step 15）。

> **低性能LLMへの注意**: ここで書くのは「機械的計測」に限る。
> LLMの「精度」で判定するコードは書かない。必ず**閾値比較**で書く。

**回帰テスト**: 本ステップの成果物そのもの

```python
@pytest.mark.asyncio
async def test_audit_latency_measured_parallel_vs_serial():
    """並列/直列のレイテンシが実測値として得られること。"""
    serial = await _measure_audit_latency(parallel=False, runs=5)
    parallel = await _measure_audit_latency(parallel=True, runs=5)
    assert parallel["median_ms"] > 0
    assert serial["median_ms"] > 0
    print(f"[実測] 監査レイテンシ: 直列 {serial['median_ms']:.0f}ms / "
          f"並列 {parallel['median_ms']:.0f}ms "
          f"(短縮率 {serial['median_ms']/parallel['median_ms']:.2f}倍)")


async def test_regeneration_ratio_is_measured():
    """再生成比率が実測値として得られること。"""
    ratio = await _measure_regeneration_ratio()
    assert 0.0 <= ratio["ratio"] <= 1.0
    print(f"[実測] 再生成比率: {ratio['ratio']:.1%} (目標: 10%未満)")
```

**検証コマンド**
```powershell
C:\Python314\python.exe -m pytest tests/perf/test_v6_audit_latency_and_regen.py -v -s
```

**完了判定**: 2つの実測値が pytest 出力 `-s` で**数値として見える**。

---

### Step 15. 効果測定表を `docs/STATUS.md` に作成する
- **対象ファイル**: `docs/STATUS.md`
- **依存**: Step 13, Step 14, Step 6
- **P分類**: P1

**背景**
親計画 Step 36 の**主要な成果物**「効果測定表」が**未作成**。
`docs/STATUS.md` に v6 / 最適化 / コスト / レイテンシの記載が**一切ない**。

**作業内容**
1. `docs/STATUS.md` に「v6 効果測定」節を新設する。
2. 親計画 §3 Step 36 の表をそのまま**実測値で埋める**。

   | 指標 | 現状 | 目標 | 実測 | 判定 |
   |:---|:---|:---|:---|:---|
   | 1話あたりLLM呼出回数 | 10 | 4-5 | (Step 13) | |
   | 監査レイテンシ | 5x | 1/5 | (Step 14) | |
   | 本文再生成比率 | 67% | <10% | (Step 14) | |
   | 1話あたりUSD | (Step 3) | 大幅減 | (Step 6 CLI) | |
   | 長編完走率 | - | 100% | (benchmarks) | |
   | 伏線回収率 | - | 実測可能 | (KPI API) | |

3. **未達の項目には「どのステップが原因か」を必ず書く**（親計画 §3 Step 36 項目4）。
4. **数値を推測で埋めない**。Step 13/14/6 の出力値を**そのまま転記**する。
5. 出典（どのテスト/スクリプトの出力か）を**各行に明記**する。

> **低性能LLMへの注意**: このステップは「転記」作業。**新しい数値を生成してはいけない**。
> 数値が不明なセルは `未計測` と**正直に書く**。

**回帰テスト**: `tests/regression/test_status_doc_has_effect_measurement.py`（新規）

```python
"""docs/STATUS.md に v6 効果測定表があることの回帰テスト。"""
from pathlib import Path


def test_status_doc_has_effect_measurement_table():
    text = Path("docs/STATUS.md").read_text(encoding="utf-8")
    assert "効果測定" in text, "docs/STATUS.md に効果測定の節が無い"
    for metric in ("LLM呼出", "監査レイテンシ", "再生成比率", "USD"):
        assert metric in text, f"効果測定表に「{metric}」の行が無い"


def test_no_placeholder_numbers_left():
    """`(Step 13)` のような未確定プレースホルダが残っていないこと。"""
    text = Path("docs/STATUS.md").read_text(encoding="utf-8")
    section = text.split("効果測定")[-1]
    assert "(Step 1" not in section, "未計測セルが未解決のまま残っている"
```

**検証コマンド**
```powershell
C:\Python314\python.exe -m pytest tests/regression/test_status_doc_has_effect_measurement.py -v
```

**完了判定**: 2テスト緑。

---

### Step 16. ベースライン比較で新規回帰ゼロを確認する
- **対象ファイル**: なし（実行のみ。必要なら `scripts/compare_test_baseline.ps1` の微調整）
- **依存**: Step 1〜15 すべて
- **P分類**: 実行ステップ

**作業内容**
1. Step 1-15 の全変更を**コミット**する（未コミットだと baseline=HEAD に含まれず
   新規テストが全部「回帰」扱いになる）。
2. ベースライン比較を実行する。
   ```powershell
   pwsh -File scripts/compare_test_baseline.ps1
   ```
3. **新規回帰が 0 件**であることを確認する。
4. 1件でも出たら、そのテストを**修正 or 記録**する（握り潰さない）。

**回帰テスト**: なし（実行ステップ）

**検証コマンド**
```powershell
pwsh -File scripts/compare_test_baseline.ps1
```

**完了判定**: スクリプトが `新規回帰: 0 件` を出力し、`exit 0`。

---

### Step 17. 本計画全体の回帰テストを実行する
- **対象ファイル**: `tests/`
- **依存**: Step 1〜16
- **P分類**: 実行ステップ

**作業内容**
1. 主要スイートを全て走らせる。
   ```powershell
   C:\Python314\python.exe -m pytest tests\regression tests\unit tests\services tests\integration -q
   ```
2. 契約テスト・E2E を走らせる。
   ```powershell
   C:\Python314\python.exe -m pytest tests\contract tests\e2e\test_v53_long_form_wiring_e2e.py -q
   ```
3. ベンチマークを走らせる。
   ```powershell
   C:\Python314\python.exe -m tests.benchmarks.long_form --eps 20,50,100 --check
   ```
4. 失敗したテストはすべて**新規回帰（Step 1-15 由来）か既存（変更前gazら）か**を区別する。
   新規回帰は**必ず直す**。

**回帰テスト**: なし（実行ステップ）

**完了コマンド**
```powershell
C:\Python314\python.exe -m pytest tests\regression tests\unit tests\services tests\integration -q
C:\Python314\python.exe -m pytest tests\contract tests\e2e\test_v53_long_form_wiring_e2e.py -q
C:\Python314\python.exe -m ruff check src\ tests\
```

**完了判定**: 全スイート緑 + `ruff` が `All checks passed!`。

---

### Step 18. `README.md` の数値を実測値に同期し、CHANGELOG を確定する
- **対象ファイル**: `README.md`、`CHANGELOG.md`
- **依存**: Step 13, 14, 15
- **P分類**: P1

**背景**
親計画 Step 35 は**部分実施**。CHANGELOG の 6.0.0 エントリと 5.3.0 の訂正ブロックは良いが、
`pyproject.toml` が 5.3.0 のまま（Step 9 で解消する）。
また v6 の効果数値が README/CHANGELOG に**記載されていない**。

**作業内容**
1. `README.md` の「長編耐性の計測」節の数値が**現在のコードと一致**することを確認する。
   - Step 1（finalize 二重実行解消）でダイジェスト LLM コストが**半減**した
     → ダイジェストコストの表（`README.md:509-515`）を**再計算**する。
   - Step 7（local_polish 計測化）で計測対象が広がった → コスト表を更新。
2. `README.md` に「1話あたりLLM回数」「監査レイテンシ」「再生成比率」の実測値を追記する
   （Step 13/14 の出力値を転記）。
3. `CHANGELOG.md` の `[6.0.0]` エントリに、以下を明記する。
   - 本計画（Step 1-18）で消除した欠陥一覧
   - 効果測定の実測値（`docs/STATUS.md` を参照する旨）
   - 「5.3.0 初回リリース時は配線が未接続だった」歴史の訂正（既に記載済み・維持）
4. **推測の数値を書かない**。Step 13/14/15 の出力のみを転記する。

**回帰テスト**: `tests/regression/test_docs_numbers_consistency.py`（新規）

```python
"""README / CHANGELOG の数値が実測値と矛盾しないことの回帰テスト。"""
import re
from pathlib import Path


def test_readme_llm_calls_matches_perf_test():
    """README の1話あたりLLM回数が perf テストの実測値と一致すること。"""
    readme = Path("README.md").read_text(encoding="utf-8")
    perf = Path("tests/perf/test_v6_llm_call_budget.py").read_text(encoding="utf-8")
    readme_n = re.search(r"1話あたりLLM呼出\D{0,10}(\d+)\s*回", readme)
    perf_n = re.search(r"target_min\s*=\s*(\d+)", perf)
    assert readme_n is not None, "README に1話あたりLLM回数の記載が無い"
    assert readme_n.group(1).isdigit()


def test_readme_digest_cost_is_current():
    """ダイジェスト1话あたりのコストが Step 1/7 の変更後の値になっていること。"""
    readme = Path("README.md").read_text(encoding="utf-8")
    # Step 1 により finalize は1话1回のみ。旧値（2回分）が残っていないこと。
    assert "2回" not in readme.split("ダイジェスト")[-1][:500], (
        "二重実行時代のダイジェストコストが README に残っている"
    )


def test_changelog_6_entry_mentions_this_plan():
    changelog = Path("CHANGELOG.md").read_text(encoding="utf-8")
    entry = changelog.split("## [6.0.0]")[-1].split("\n## ")[0]
    for keyword in ("二重実行", "logger", "効果測定"):
        assert keyword in entry, f"CHANGELOG 6.0.0 に「{keyword}」の記載が無い"
```

**検証コマンド**
```powershell
C:\Python314\python.exe -m pytest tests/regression/test_docs_numbers_consistency.py -v
C:\Python314\python.exe -m pytest tests/regression/test_v5_version_consistency.py -q
```

**完了判定**: 3テスト緑。

---

## 3. フェーズ別完了条件

| Phase | ステップ | 完了条件 |
|:---|:---|:---|
| **A: 実害の解消** | 1-3 | 二重実行が 0 件。`hasattr(self,"logger")` が 0 件。`_resolve_session` が 2 箇所で使われる |
| **B: 契約の穴** | 4-5, 7, 8, 12 | チェーン断線・無言コスト・LLMバイパス・引数不整合・tautology テストが全て解消 |
| **C: 計測の整備** | 6, 9, 10 | コストCLIが動作。version 6.0.0。ruff 緑 |
| **D: 観測の証明** | 11, 13, 14 | 警告が実際にログに出る。LLM回数・レイテンシ・再生成比率が実測 |
| **E: 総仕上げ** | 15-18 | 効果測定表あり。新規回帰 0 件。docs が実測値と一致 |

---

## 4. 完了の定義 (Definition of Done)

0. `_post_episode_finalize` が 1 话につき**ちょうど 1 回**だけ呼ばれることがテストで証明される。
1. `hasattr(self, "logger")` が `src/` 全体で **0 件**、かつ警告が**実際にログに出る**ことがテストで証明される。
2. `_resolve_session` が**実際に 2 箇所から呼ばれている**。
3. `IllustrationAgent` の no-op が後続チェーンを**止めない**。
4. 未知モデルのコストが **$0 で無言化しない**。
5. 1話あたりUSDを印字する **CLI が存在する**。
6. `LocalPolisher` が**注入 LLM のみ**を使う。
7. `pyproject.toml` / `README.md` / `CHANGELOG.md` のバージョンが**6.0.0 で一致**。
8. `ruff check src tests` が **`All checks passed!`**。
9. 効果測定表に**実測値**が数値として埋まり、未達項目には**原因ステップ**が書いてある。
10. ベースライン比較で**新規回帰 0 件**。
11. 2つの tautology テストが**実測ベース**に書き換えられている。

---

## 5. リスクと対策

| リスク | 影響 | 対策 |
|---|:---|:---|
| **Step 2 の機械置換で意図しない行まで消える** | High | 置換前後で `git diff` を確認し、**1ステップずつ**コミットする。25箇所の bulk 置換を1回でやらない |
| Step 7 で `LocalPolisher.polish` の async 化が既存呼び出しを壊す | Medium | `await` Assignable なラッパーを**別名で追加**し、既存同期呼び出しは残す（Step 7 のフォールバック分岐が担保） |
| Step 10 の ruff `--fix` が 2000 箇所の自動修正で**意図しないコード変更**をする | High | `--fix` の前に `git stash` / バックアップを取り、`--diff` で**preview** してから適用する |
| Step 13/14 の「実測」が**また STUB 校正値**になる | Medium | 実測必ず**実データ**（実 SQLite 行・実カウンタ）から取得する。STUB を使う場合は `STUB` と明記し、効果測定表にも `推定` と書く |
| Step 15 の数値が**推測で埋まる** | Medium | 未計測セルは `未計測` と**正直に**書く。プレースホルダ残存テスト（Step 15）で機械的に防ぐ |
| Step 16 のベースライン比較が**未コミット変更を全部回帰扱い**にする | Medium | Step 16 前に**必ずコミット**する（`compare_test_baseline.ps1` の baseline は HEAD） |
| Step 1 の finalize 除去で **beat-to-scene 経路の後処理が消える** | Critical | Step 1 の 3 テストのうち `test_finalize_receives_split_path_text` が**経路をまたいでテキストが届く**ことを保証する。緑になるまで完了判定しない |

---

## 6. 低性能LLM実装者向けの最終注意事項

1. **行番号は記憶で書かない**。必ず `Select-String` / `grep` で**その場で確認**する。
2. **1ステップ()==1コミット**。途中で失敗したら `git revert` して次のステップに進む。
3. **「完了判定」= 検証コマンドが緑**。それ以外は判断しない。
4. **テストを弱めない**。Step 12 の書き換えで**アサーション数が減っていない**か必ず自查する。
5. **推測の数値を書かない**。不明なものは `未計測` と書く。
6. **既存テストを削除して通さない**。壊れた既存テストは**実装を直す**のが正解。
7. 迷ったら**元の 36 ステップ計画書を読み直す**。本計画は差分であり、全部Defsではない。
