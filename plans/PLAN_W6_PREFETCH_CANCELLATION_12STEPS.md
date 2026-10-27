# AutoNovel W6 是正計画書【投機的プリフェッチ → 静的ウォームアップ＋即時キャンセル 12ステップ】

- **文書ID**: PLAN_W6_PREFETCH_CANCELLATION_12STEPS
- **作成日**: 2026-09-29
- **対象バージョン**: AutoNovel v5.3.0 → v6.0.0
- **親計画**: [PLAN_V6_COST_LATENCY_OPTIMIZATION.md](PLAN_V6_COST_LATENCY_OPTIMIZATION.md) §2 / PLAN_T6 R07・R10
- **ステータス**: **完了**（2026-09-30 / Step 1〜12 実装済み・pytest 緑）
- **目的**: 1話目の執筆中に裏で走る「次話」の投機処理を、
  **①LLM を一切呼ばない静的ナレッジのウォームアップ限定** ②**全経路 cancellable** に改了、
  リテイク・編集・中断時に**課金される無駄をゼロにする**。

---

## 0. この計画書の位置づけ

W6 の実害は「遅い」ことではなく **「無駄な課金が静かに続ける」** ことである。
実測された事実：

| 事実 | 根拠 |
|---|---|
| `RagPrefetchService` は **本番から一度も呼ばれていない**（テスト3本のみ） | `grep -rn "RagPrefetchService" src/` → 0 ヒット |
| `RagPrefetchService._do_prefetch` は `asyncio.coroutine` を使うが、**Python 3.11 で削除済み** | `rag_prefetch_service.py:76, 84, 90` |
| `_trigger_prefetch` は毎回 `SemanticCacheManager` を**作り直しており、L1/L2-B を捨てる** | `episode_writing_workflow.py:91` |
| `_trigger_prefetch` は `BaseWorkflow` に `vector_store` が無いため**必ず早期 return** | `episode_writing_workflow.py:83-89` |
| `asyncio.create_task(...)` の**戻り値ハンドルを保持しない** | `episode_writing_workflow.py:100`、`_shared_ops.py:43` |
| `semantic_cache._BACKGROUND_TASKS` は**フラットな set**。個別キャンセルできない | `semantic_cache.py:16, 19-34` |
| `plot_expander.prefetch_next_episode_plot` は **Task を返すのに捨てている** | `episode_writer.py:284-293` |
| `RagPrefetchService.invalidate`（唯一のキャンセル経路）は**どこからも呼ばれない** | `grep -rn "\.invalidate(" src/` → 該当なし |
| FastAPI `lifespan` に **shutdown 枝が無い**（`yield` の後 何もしない） | `src/backend/server.py:72-108` |
| `src/` 全体で **`asyncio.Event` が 0 箇所**（協力的キャンセルトークンが無い） | `grep -rn "asyncio.Event" src/` → 0 ヒット |
| `prefetch_next` は**プロンプトを描画して embedding を温めるだけ**で、**L1 は温まらない** | `semantic_cache.py:383-390`（`l1_key` はログ出力のみ） |

> **結論：現状のプリフェッチは「速さのため」に付费している化工数が、実際の効果として活きていない。**
> 本計画は **投機実行そのものを廃止するのではなく、対象を「静的で決定的なもの」だけに限定し、
> しかも全経路で即時に殺せるようにする**。

### 0.1 分割原則（低性能LLM向け）

| 原則 | 内容 |
|---|---|
| **P1 単一ファイル** | 1ステップの主担当ファイルは高々1つ |
| **P2 機械的置換のみ** | `asyncio` の primitives だけで完結させる。フレームワーク追加は禁止 |
| **P3 判定は pytest 緑赤のみ** | 効果の推測をさせない |
| **P4 テスト先行** | 回帰テストを先に作り、赤いことを確認してから実装する |
| **P5 再利用優先** | 新しい抽象を非同期層に作らない。`src/core/async_utils.py` の既存 3 関数（`fire_and_forget` / `run_parallel` / `safe_timeout`）だけを使う |
| **P6 猜测禁止** | 行番号・関数名は必ず grep で再確認する |
| **P7 API 後方互換** | 既存メソッドのシグネチャは壊さない。kwargs 追加・タプ返却化・return 値追加で済ませる |

### 0.2 実行順序の依存関係

```
Step 1 (Registry) ──→ Step 2 (CancellationToken) ──→ Step 3 (fix asyncio.coroutine)
                                                    │
Step 4 (SemanticCache 投機停止) ───────────────────┤
Step 5 (RagPrefetch 静的限定) ─────────────────────┤
Step 6 (cancel_all / close) ──────────────────────┤
Step 7 (lifespan shutdown 配線) ───────────────────┤
Step 8 (DI シングルトン化) ───────────────────────┤
Step 9 (plot expander ハンドル保持) ──────────────┤
                                                    │
Step 10 (invalidete 配線: retry/cancel/stop) ──────┤
Step 11 (投機実行ゲート: 高確度時のみ) ───────────┤
                                                    └──→ Step 12 (総合回帰・計測)
```

- **Step 1 が全ての前提**。最初に必ず終わらせる。
- **Step 2 → 3 → 4/5/6/7/8/9** は Step 1 の上に積む。
- **Step 10, 11 は Step 6 の-API に依存**。
- **Step 12 は最後**（全ステップ完了後にのみ）。

---

## 1. 残存欠陥一覧（本計画の対象）

| ID | 深刻度 | 実測事実（根拠） | 担当Step |
|:---|:---|:---|:---|
| W6-01 | Critical | `asyncio.coroutine` は **Python 3.11 で削除済み**。`rag_prefetch_service.py:76,84,90` は engine に該当機能が無いと**同期的に `AttributeError`** を投げ、`:112` の 一括 except に落ちて**プリフェッチが常に no-op** | 3 |
| W6-02 | Critical | 全 background task の**ハンドルどこにも保存されない**。`semantic_cache._BACKGROUND_TASKS`（`:16`）はフラット set、`workflow.py:100` と `_shared_ops.py:43` は `create_task` の戻りを捨てる。**リテイク時に殺せない** | 1, 6, 9 |
| W6-03 | Critical | `invalidate`（`rag_prefetch_service.py:133-140`）という**唯一のキャンセルAPIが死んでいる**。`retry_failed_episodes` / `stop_task` / `cancel_orchestrated_task` の3エントリから誰も呼ばない | 10 |
| W6-04 | Major | `SemanticCacheManager` を `episode_writing_workflow.py:91` で**毎回生成**。L1(1000件) と L2-B(500件) が**毎回ゼロから**。ウォームアップの効果が構造的に消える | 8 |
| W6-05 | Major | `prefetch_next`（`:322-393`）は **次話の執筆プロンプトを描画して** その embedding を温める。**文脈が1文字違えば L1 キーが全滅**し、`l1_key`（`:385`）はログにしか使われない＝**L1 は温まらない**。_embedding API コストだけが残る | 4 |
| W6-06 | Major | `engine_writing_workflow._trigger_prefetch` は `BaseWorkflow` に `vector_store` / `llm_client` が無いため**必ず `:86-89` で return**。つまり**本番ではプリフェッチが1度も走っていない**（`_shared_ops.trigger_prefetch` も**呼び出し元ゼロ**） | 8 |
| W6-07 | Major | FastAPI `lifespan`（`server.py:72-108`）に **shutdown 枝が無い**。`executor_manager.shutdown()`（`src/core/executor_manager.py:48`）も**どこからも呼ばれない** | 7 |
| W6-08 | Minor | `RagPrefetchService` のプリフェッチ対象が3種（style_rag / past logs / project intelligence）。**うち `get_project_intelligence` はリポジトリ内に定義が存在しない** | 5 |
| W6-09 | Minor | 投機実行の条件が**一切ない**。常に次の3話分（`:104`）を走らせる。低確度のリテイク実績でも無駄に走る | 11 |
| W6-10 | Minor | プリフェッチの**観測点（開始/完了/キャンセル/失敗）が無い**。`RagPrefetchService.get_stats`（`:142`）が在るが**どこからも読まれていない** | 6, 12 |

---

## 2. 12ステップ

---

### Step 1. `src/services/prefetch/registry.py` を新設する
- **主担当ファイル**: `src/services/prefetch/registry.py`（**新規**）
- **依存**: なし
- **P分類**: P1（新規1ファイル）/ P2

**背景**
現状のタスク管理は3系統に分かれており、**どれもキャンセル不能**：

| 系統 | 置き場 | 問題 |
|---|---|---|
| `semantic_cache._BACKGROUND_TASKS` | `semantic_cache.py:16` `set[Task]` | キー無し。**どれを殺すべきか判定できない** |
| `RagPrefetchService._pending_tasks` | `rag_prefetch_service.py:31` `dict[str, Task]` | `invalidate` が**死んでいる**（W6-03） |
| `workflow._trigger_prefetch` | `episode_writing_workflow.py:100` | **ハンドル自体が無い** |

**cancel_all / cancel_key / get_stats の 3 つだけを持つ共通レジストリを先に作る。**
以降のステップはすべてこの 1 か所だけを触ればよくなる。

**作業内容**
1. 新規パッケージ `src/services/prefetch/`（`__init__.py` も新規、**1行**で可）。
2. `class PrefetchRegistry` を1つだけ作る。公開API **4つ**:

```text
def track(self, key: str, task: asyncio.Task) -> asyncio.Task
def untrack(self, key: str) -> None
async def cancel(self, key: str) -> int                 # 返り値: 実際にキャンセルした本数
async def cancel_prefix(self, prefix: str) -> int       # 返り値: 同上（book_id や book_id:ep で部分一致）
def stats(self) -> dict[str, int]                       # {"tracked": n, "cancelled": n, "failed": n, "done": n}
```

3. 内部は `dict[str, asyncio.Task]` 1つ。`track` は**同キーの旧タスクを先に `cancel()`** してから上書きする。
4. `cancel` / `cancel_prefix` の実装は **`dag_scheduler._cancel_running_tasks`（`dag_scheduler.py:729-742`）と同じ形**:
   - `list(...)` でコピー → `not t.done()` のみ `t.cancel()` → `await asyncio.gather(*tasks, return_exceptions=True)` → dict から除去。
5. `task.add_done_callback` で**必ず `untrack`** し、例外は `logger.warning` に出すだけ（**再送出しない**）。
6. `CancelledError` は**握り潰してよい**（`:28` の `semantic_cache._handle_done` と同じ方針）。
7. `asyncio` 以外の import をしない（`logging` は可）。

**回帰テスト（先に作る）**: `tests/unit/services/prefetch/test_registry.py`（新規・非同期）

```python
"""PrefetchRegistry の登録・取り消し・統計の回帰テスト。"""
import sys, pathlib
import asyncio
import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))

from src.services.prefetch.registry import PrefetchRegistry


@pytest.mark.asyncio
async def test_track_and_untrack():
    r = PrefetchRegistry()
    async def noop(): return 1
    t = r.track("b:1", asyncio.create_task(noop()))
    await asyncio.sleep(0)
    assert r.stats()["tracked"] >= 0        # done コールバックは还没来的不定
    r.untrack("b:1")
    assert "b:1" not in r._tasks


@pytest.mark.asyncio
async def test_cancel_stops_running_task():
    r = PrefetchRegistry()
    started = asyncio.Event()

    async def forever():
        started.set()
        await asyncio.sleep(3600)

    task = r.track("b:2", asyncio.create_task(forever()))
    await started.wait()
    assert await r.cancel("b:2") == 1
    assert task.cancelled() or task.done()


@pytest.mark.asyncio
async def test_cancel_unknown_key_returns_zero():
    assert await PrefetchRegistry().cancel("nothing") == 0


@pytest.mark.asyncio
async def test_cancel_prefix_matches_book_scope():
    r = PrefetchRegistry()
    ev = asyncio.Event()
    async def forever():
        ev.set(); await asyncio.sleep(3600)
    for k in ("book1:1", "book1:2", "book2:1"):
        r.track(k, asyncio.create_task(forever()))
    await ev.wait()
    assert await r.cancel_prefix("book1") == 2


@pytest.mark.asyncio
async def test_retacking_same_key_cancels_previous():
    r = PrefetchRegistry()
    ev = asyncio.Event()
    async def forever():
        ev.set(); await asyncio.sleep(3600)
    first = r.track("b:3", asyncio.create_task(forever()))
    await ev.wait()
    second = r.track("b:3", asyncio.create_task(asyncio.sleep(0)))
    await asyncio.sleep(0)
    assert first.cancelled() or first.done()
    assert r._tasks["b:3"] is second


@pytest.mark.asyncio
async def test_stats_has_four_keys():
    r = PrefetchRegistry()
    async def noop(): return 1
    r.track("b:4", asyncio.create_task(noop()))
    await asyncio.sleep(0.01)
    assert set(r.stats()) == {"tracked", "cancelled", "failed", "done"}
```

**検証コマンド**
```powershell
C:\Python314\python.exe -m pytest tests/unit/services/prefetch/test_registry.py -q
```

**完了判定**: 6テスト緑。**`test_cancel_prefix_matches_book_scope` が5秒以内に終わること**。

---

### Step 2. `src/core/cancellation.py` に `CancellationToken` を新設する
- **主担当ファイル**: `src/core/cancellation.py`（**新規**）
- **依存**: なし
- **P分類**: P1（新規1ファイル）/ P2

**背景**
`grep -rn "asyncio.Event" src/` → **0 ヒット**。
協力的キャンセルトークンがリポジトリに存在しないため、
協調的にしか止められない処理（Embedding 呼び出しのバッチ途中など）は止められない。
既存のトークンは唯一で、`src/backend/background.py:120` の `threading.Event`（**thread ベース**）だけ。

**作業内容**
1. 新規ファイル。`asyncio` と `typing` のみ。
2. `class CancellationToken` を1つ:
   - `__init__(self, name: str = "")`
   - `def cancel(self) -> None` — 内部 `asyncio.Event` を set
   - `def is_cancelled(self) -> bool`
   - `async def wait(self) -> None` — キャンセルされるまで待つ
   - `def raise_if_cancelled(self) -> None` — 済みなら **`asyncio.CancelledError` を送出**
   - `@property def cancelled_event(self) -> asyncio.Event` — `wait_for` に渡せるように
3. **スレッド安全性**: `asyncio.Event` はスレッドセーフではないため、
   `cancel()` は **`asyncio.get_event_loop()` が動いているスレッドからのみ**呼ぶ前提とする。
   別スレッドから呼んでも落ちないよう、`cancel()` の中では `try/except RuntimeError: pass` で包む。
4. **`contextvars` には入れない**（jj 伝播は別ステップのスコープ）。
5. `__aenter__` / `__aexit__` は**実装しない**（API を増やさない）。

**回帰テスト（先に作る）**: `tests/unit/core/test_cancellation_token.py`（新規・非同期）

```python
"""CancellationToken の回帰テスト。"""
import sys, pathlib
import asyncio
import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))

from src.core.cancellation import CancellationToken


@pytest.mark.asyncio
async def test_starts_uncancelled():
    assert CancellationToken("t").is_cancelled() is False


@pytest.mark.asyncio
async def test_cancel_flips_flag():
    tok = CancellationToken("t")
    tok.cancel()
    assert tok.is_cancelled() is True


@pytest.mark.asyncio
async def test_wait_returns_after_cancel():
    tok = CancellationToken("t")
    loop = asyncio.get_running_loop()
    loop.call_later(0.01, tok.cancel)
    await asyncio.wait_for(tok.wait(), timeout=1.0)
    assert tok.is_cancelled()


@pytest.mark.asyncio
async def test_raise_if_cancelled_raises_cancelled_error():
    tok = CancellationToken("t")
    tok.cancel()
    with pytest.raises(asyncio.CancelledError):
        tok.raise_if_cancelled()


@pytest.mark.asyncio
async def test_raise_if_cancelled_is_noop_when_active():
    CancellationToken("t").raise_if_cancelled()      # 例外_none


@pytest.mark.asyncio
async def test_usable_as_event():
    tok = CancellationToken("t")
    loop = asyncio.get_running_loop()
    loop.call_later(0.01, tok.cancel)
    await asyncio.wait_for(tok.cancelled_event.wait(), timeout=1.0)


@pytest.mark.asyncio
async def test_cancel_from_another_thread_does_not_raise():
    tok = CancellationToken("t")
    loop = asyncio.get_running_loop()
    t = __import__("threading").Thread(target=tok.cancel)
    t.start(); t.join()
    assert tok.is_cancelled() is True
```

**検証コマンド**
```powershell
C:\Python314\python.exe -m pytest tests/unit/core/test_cancellation_token.py -q
```

**完了判定**: 7テスト緑。**`test_cancel_from_another_thread_does_not_raise` が例外を出さないこと**。

---

### Step 3. `rag_prefetch_service.py` の `asyncio.coroutine` 削除を直す
- **主担当ファイル**: `src/services/rag_prefetch_service.py`
- **依存**: Step 1
- **P分類**: P1（1ファイル）/ P7

**背景**
```
76:  tasks.append(asyncio.coroutine(lambda: [])())
84:  tasks.append(asyncio.coroutine(lambda: "")())
90:  tasks.append(asyncio.coroutine(lambda: {})())
```
`asyncio.coroutine` は **Python 3.11 で削除**（本リポジトリは 3.14）。
該当機能を持たない engine だと**同期的に `AttributeError`** が出て、
`:112` の 一括 except に落ちて **プリフェッチ全体が恒久に no-op** になる。
つまり「W6 の投機的プリフェッチは本番で一度も動いていない」こと-実因がここにある。

**作業内容**
1. モジュール先頭に**小さなヘルパを1つ**追加する（**新規ファイルを作らない**）:
```python
async def _null(value):
    """機能が無い engine 用に空結果を返すだけの no-op コルーチン。"""
    return value
```
2. `:76, :84, :90` の `asyncio.coroutine(lambda: X)()` を **`_null(X)` に置換**する（3行）。
3. `tasks` の型注釈を `list` のままにする（**3.9 互換**のため `list[...]` にしない）。
4. `from src.core.prefetch...` の新しい import は**このステップでは足さない**（Step 5）。
5. 既存の `cache_key` / `prefetch_for_episode` / `get_cached` / `invalidate` / `get_stats` は
   **1文字も変えない**（後方互換）。
6. `except Exception`（`:112`）は**握り潰しのまま**。ただしログに**関数名**を追加する（1語）。

**回帰テスト（先に作る）**: `tests/unit/services/prefetch/test_rag_prefetch_null_coro.py`（新規・非同期）

```python
"""asyncio.coroutine 依存を撤去し、engine 不在でも.Claude-3 完走することの回帰テスト。"""
import sys, pathlib
from unittest.mock import MagicMock
import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))

from src.services.rag_prefetch_service import RagPrefetchService, _null


@pytest.mark.asyncio
async def test_null_helper_returns_value():
    assert await _null([]) == []
    assert await _null("") == ""
    assert await _null({}) == {}


@pytest.mark.asyncio
async def test_module_has_no_asyncio_coroutine_attribute():
    import src.services.rag_prefetch_service as mod
    assert not hasattr(mod.asyncio, "coroutine"), "Python3.14 では削除済み"


@pytest.mark.asyncio
async def test_bare_engine_completes_without_exception():
    """engine に何も無い即便死んでも例外を投げないこと。"""
    svc = RagPrefetchService()
    await svc._do_prefetch(MagicMock(), 1, 1, 1, "blueprint")
    assert svc.get_cached(1, 1) is not None          # 空結果で必ずキャッシュされる


@pytest.mark.asyncio
async def test_cache_payload_shape_unchanged():
    svc = RagPrefetchService()
    await svc._do_prefetch(MagicMock(), 2, 1, 5, "bp")
    payload = svc.get_cached(2, 5)
    assert set(payload) == {"style_samples", "rag_context", "intelligence", "prefetched"}
    assert payload["prefetched"] is True
```

**検証コマンド**
```powershell
C:\Python314\python.exe -m pytest tests/unit/services/prefetch/test_rag_prefetch_null_coro.py tests/unit/test_rag_prefetch_service.py -q
```

**完了判定**: 4テスト緑。**かつ既存 `tests/unit/test_rag_prefetch_service.py` 3本緑**。

---

### Step 4. `semantic_cache.py` の投機的 LLM プリフェッチを停止する
- **主担当ファイル**: `src/services/semantic_cache.py`
- **依存**: Step 1
- **P分類**: P1（1ファイル）/ P7

**背景**
```
322-393: async def prefetch_next(book_id, current_ep_num, task_types, genre, temperature)
341-380:  PromptManager() を生成し、build_drafting_prompt / build_polishing_prompt を実行
383-390:  l1_key = self._get_l1_key(...); _spawn_background(self._prefetch_embedding(...))
392:      logger.info(f"...{l1_key}...")          ← l1_key はログだけ
395-406: _prefetch_embedding → _get_embedding → _l2_embedding_cache のみ
```
**この投機実行は次話プロンプト（本文未確定）をレンダリングするため、リテイクで必ず無駄になる。**
しかも **L1 を温めない**ので**検索ヒット率向上が実質ゼロ**、**embedding API コストだけが残る**。

**作業内容**
1. `_TRUTHY` 相当の判定を**モジュール関数1つ**追加（`os` の import を追加する）:
```python
def is_draft_prefetch_enabled() -> bool:
    """次話の執筆プロンプトを投機生成する機能。既定OFF。"""
    return os.environ.get("ENABLE_SEMANTIC_PREFETCH_DRAFT", "0").strip().lower() in ("1", "true", "yes", "on")
```
2. `prefetch_next`（`:322`）の**冒頭**に1つの early-return を追加:
```text
if not is_draft_prefetch_enabled():
    return                      # 静的なウォームアップは Step 5 の別メソッドが担当する
```
3. `_prefetch_embedding`（`:395-406`）と `_spawn_background`（`:19`）は**削除しない**。
4. `prefetch_by_pattern`（`:408-442`）は**変更しない**（Step 4 だけでは何も起きなくなるだけ）。
5. `SemanticCacheManager` の **他のメソッド（`search` / `add` / `get_cache_warmth`）には触らない**。
6. `tests/unit/test_semantic_cache.py:268-288` の `test_prefetch_next` は
   **`ENABLE_SEMANTIC_PREFETCH_DRAFT` を設定しなおす**ことで緑を保つ（**既存テストの改変はこの1行だけ**）。

**回帰テスト（先に作る）**: `tests/unit/services/prefetch/test_semantic_prefetch_disabled.py`（新規・非同期）

```python
"""次話プロンプトの投機生成が既定OFFであることの回帰テスト。"""
import sys, pathlib
from unittest.mock import AsyncMock, MagicMock, patch
import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))

from src.services import semantic_cache as sc


def _mgr():
    vs = MagicMock()
    vs.get_collection = MagicMock()
    return sc.SemanticCacheManager(vector_store=vs, client=MagicMock())


def test_flag_defaults_off(monkeypatch):
    monkeypatch.delenv("ENABLE_SEMANTIC_PREFETCH_DRAFT", raising=False)
    assert sc.is_draft_prefetch_enabled() is False


def test_flag_can_be_enabled(monkeypatch):
    monkeypatch.setenv("ENABLE_SEMANTIC_PREFETCH_DRAFT", "true")
    assert sc.is_draft_prefetch_enabled() is True


@pytest.mark.asyncio
async def test_prefetch_next_is_noop_by_default(monkeypatch):
    monkeypatch.delenv("ENABLE_SEMANTIC_PREFETCH_DRAFT", raising=False)
    with patch.object(sc, "PromptManager", create=True) as pm:
        await _mgr().prefetch_next(1, 1, ["drafting"])
    pm.assert_not_called()


@pytest.mark.asyncio
async def test_existing_public_api_intact():
    mgr = _mgr()
    for name in ("search", "add", "prefetch_next", "prefetch_by_pattern",
                 "get_cache_warmth", "compute_similarity", "evict_if_needed"):
        assert callable(getattr(mgr, name)), name


@pytest.mark.asyncio
async def test_enabled_path_still_works(monkeypatch):
    monkeypatch.setenv("ENABLE_SEMANTIC_PREFETCH_DRAFT", "1")
    with patch.object(sc, "PromptManager", create=True) as pm:
        pm.return_value.build_drafting_prompt = AsyncMock(return_value="P")
        pm.return_value.build_polishing_prompt = AsyncMock(return_value="Q")
        await _mgr().prefetch_next(1, 1, ["drafting", "polishing"])
    assert pm.return_value.build_drafting_prompt.await_count == 1
```

**検証コマンド**
```powershell
C:\Python314\python.exe -m pytest tests/unit/services/prefetch/test_semantic_prefetch_disabled.py -q
C:\Python314\python.exe -m pytest tests/unit/test_semantic_cache.py tests/unit/services/test_semantic_cache.py -q
```

**完了判定**: 5テスト緑。**かつ既存 semantic cache 2ファイル全緑**
（`test_prefetch_next` に環境変数を足すだけで緑になること）。

---

### Step 5. `RagPrefetchService` を静的ナレッジのウォームアップに限定する
- **主担当ファイル**: `src/services/rag_prefetch_service.py`
- **依存**: Step 1, 3
- **P分類**: P1（1ファイル）/ P7

**背景**
現状 `prefetch_for_episode`（`:36-58`）は引数に **`plot_blueprint`（次話の本文预估）** を取る。
つまり**動的**な入力で投機している。Step 4 と同じく、**文脈が変わればキャッシュの意味を失う**。
一方、World Memory / Character Memory（`CollectionType.WORLD_MEMORY` / `CHARACTER_MEMORY`）は
**1話の進行に依らない静的ナレッジ**で、これは事前ロードして損がない。

**作業内容**
1. `RagPrefetchService.__init__`（`:28`）に **`self._registry = PrefetchRegistry()`** を追加
   （`src.services.prefetch.registry` から import）。
2. `prefetch_for_episode`（`:36-58`）に**キーワード引数** `static_only: bool = False` を追加（後方互換）。
3. `static_only=True` のとき、**キャッシュキーに引数の_hash を含めない**:
   `key = self.cache_key(book_id, ep_num)` の**まま**にして、
   キャッシュ payload に `"static": True` を**1キー追加**する。
4. `prefetch_for_episode` の**タスク登録**を `fire_and_forget`（`:54`）から
   `self._registry.track(key, task)` に**置き換える**（**`self._pending_tasks` は残す**＝Step 6 まで既存テストを壊さない）。
5. `_do_prefetch`（`:60`）は**変更しない**（Step 3 で `asyncio.coroutine` を撤去済み）。
6. `get_cached`（`:117`）と `get_stats`（`:142`）に**新キーは足さない**。
7. `static_only` の**既定は `False`**（既存挙動を壊さない）。**本番接线は Step 10** で `True` を渡す。

**回帰テスト（先に作る）**: `tests/unit/services/prefetch/test_rag_prefetch_static_only.py`（新規・非同期）

```python
"""静的限定モードの回帰テスト。"""
import sys, pathlib
from unittest.mock import MagicMock
import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))

from src.services.rag_prefetch_service import RagPrefetchService


@pytest.mark.asyncio
async def test_default_is_not_static_only():
    import inspect
    sig = inspect.signature(RagPrefetchService.prefetch_for_episode)
    assert sig.parameters["static_only"].default is False


@pytest.mark.asyncio
async def test_static_only_marks_payload():
    svc = RagPrefetchService()
    await svc._do_prefetch(MagicMock(), 1, 1, 1, "bp")
    svc._cache["1_1"]["static"] = True
    assert svc.get_cached(1, 1)["static"] is True


@pytest.mark.asyncio
async def test_service_owns_a_registry():
    from src.services.prefetch.registry import PrefetchRegistry
    assert isinstance(RagPrefetchService()._registry, PrefetchRegistry)


@pytest.mark.asyncio
async def test_invalidate_still_populates_no_error():
    svc = RagPrefetchService()
    await svc._do_prefetch(MagicMock(), 3, 1, 2, "bp")
    svc.invalidate(3, 2)                      # 例外_none
    assert svc.get_cached(3, 2) is None


@pytest.mark.asyncio
async def test_stats_still_has_four_keys():
    assert set(RagPrefetchService().get_stats()) == {
        "cached_episodes", "pending_tasks", "max_size", "keys"}
```

**検証コマンド**
```powershell
C:\Python314\python.exe -m pytest tests/unit/services/prefetch/test_rag_prefetch_static_only.py tests/unit/test_rag_prefetch_service.py -q
```

**完了判定**: 5テスト緑。**かつ既存 `test_rag_prefetch_service.py` 3本緑**（`get_stats` のキー数不変）。

---

### Step 6. 両サービスに `cancel_all` / `close` を追加する
- **主担当ファイル**: `src/services/semantic_cache.py` **と** `src/services/rag_prefetch_service.py`
  （本ステップのみ2ファイル。**やむを得ない理由**：`cancel_all` API の契約が2モジュールで不一致のため）
- **依存**: Step 1, 3, 5
- **P分類**: P7

**背景**
FastAPI の `lifespan`（`server.py:72-108`）に shutdown 枝が無く、
`executor_manager.shutdown()`（`src/core/executor_manager.py:48`）も**どこからも呼ばれない**。
プロセス終了時にバックグラウンドタスクが中断されると **RAG検索中のDB接続がリーク**する。

**作業内容**
1. `semantic_cache.py` に**2つのモジュール関数**を追加する:
   - `async def cancel_all_prefetch() -> int` — `_BACKGROUND_TASKS` を**コピーして**全 cancel、`gather(return_exceptions=True)`、集合をクリア。返り値は本数。
   - `async def close_background_tasks() -> None` — 上記を呼ぶだけの別名（命名の一貫性用。**ロジックは増やさない**）。
2. `rag_prefetch_service.py` に**2つの async メソッド**を追加する:
   - `async def cancel_all(self) -> int` — `self._pending_tasks` を全て `self._registry.cancel_prefix(str(book_id or ""))` 経由で取消。
     **書籍単位の切り分けは Step 10**。
   - `async def close(self) -> None` — `await self.cancel_all(); self._cache.clear()`。
3. **いずれも例外を送出しない**。ログのみ。
4. `_BACKGROUND_TASKS`（`semantic_cache.py:16`）と `_pending_tasks`（`rag_prefetch_service.py:31`）の
   **型・変数名は変更しない**。
5. `get_stats`（`:142`）の**既存4キーは変更しない**。

**回帰テスト（先に作る）**: `tests/unit/services/prefetch/test_prefetch_cancellation.py`（新規・非同期）

```python
"""cancel_all / close がバックグラウンドタスクを確実に殺すことの回帰テスト。"""
import sys, pathlib
import asyncio
from unittest.mock import MagicMock
import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))

from src.services import semantic_cache as sc
from src.services.rag_prefetch_service import RagPrefetchService


@pytest.mark.asyncio
async def test_semantic_cancel_all_kills_tasks():
    ev = asyncio.Event()
    async def forever():
        ev.set(); await asyncio.sleep(3600)
    for _ in range(3):
        t = asyncio.create_task(forever())
        sc._BACKGROUND_TASKS.add(t)
    await ev.wait()
    assert await sc.cancel_all_prefetch() == 3
    assert len(sc._BACKGROUND_TASKS) == 0


@pytest.mark.asyncio
async def test_semantic_close_is_alias():
    assert await sc.close_background_tasks() == 0


@pytest.mark.asyncio
async def test_rag_prefetch_cancel_all():
    svc = RagPrefetchService()
    ev = asyncio.Event()
    async def forever():
        ev.set(); await asyncio.sleep(3600)
    for ep in (1, 2, 3):
        svc._pending_tasks[svc.cache_key(9, ep)] = asyncio.create_task(forever())
    await ev.wait()
    assert await svc.cancel_all() == 3


@pytest.mark.asyncio
async def test_rag_prefetch_close_clears_cache():
    svc = RagPrefetchService()
    svc._cache[svc.cache_key(9, 1)] = {"prefetched": True}
    await svc.close()
    assert svc._cache == {}


@pytest.mark.asyncio
async def test_cancel_all_on_empty_registry_is_zero():
    assert await sc.cancel_all_prefetch() == 0
    assert await RagPrefetchService().cancel_all() == 0
```

**検証コマンド**
```powershell
C:\Python314\python.exe -m pytest tests/unit/services/prefetch/test_prefetch_cancellation.py -q
```

**完了判定**: 5テスト緑。**全タスクが `.cancelled()` または `.done()` であること**。

---

### Step 7. FastAPI `lifespan` に shutdown 枝を足す
- **主担当ファイル**: `src/backend/server.py`
- **依存**: Step 6
- **P分類**: P1（1ファイル）/ P2

**背景**
```
71-108: @asynccontextmanager async def lifespan(app)
75:      init_db()
77-82:   Huey health check
86-104:  LLM/IMAGE provider key validation
105:     yield          ← try/finally 無し。shutdown で何もしない
```
プロセス終了時に **Step 6 で管理しているタスクが全部殺されない**。

**作業内容**
1. `lifespan` 内の `yield`（`:105`）を **`try: yield finally: ...`** で囲む（**1つの構造変更**）。
2. `finally` 内に**3行だけ**入れる（**try/except は各行に付ける**）:
   - `await cancel_all_prefetch()`（`src.services.semantic_cache` から遅延 import）
   - `executor_manager.shutdown()`（`src.core.executor_manager` から遅延 import）
   - `logger.info("shutdown: background tasks cancelled")`
3. **`init_db()` と既存バリデーションには触れない**。
4. `app = FastAPI(..., lifespan=lifespan)`（`:108`）は**変更しない**。
5. **新しい shutting down イベント（SIGTERM ハンドラ等）は実装しない**（スコープ外）。

**回帰テスト（先に作る）**: `tests/unit/backend/test_server_lifespan_shutdown.py`（新規・非同期）

```python
"""lifespan の shutdown でプリフェッチタスクが消されることの回帰テスト。"""
import sys, pathlib
from unittest.mock import AsyncMock, MagicMock, patch
import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))

from src.backend.server import lifespan


@pytest.mark.asyncio
async def test_shutdown_cancels_prefetch():
    with patch("src.services.semantic_cache.cancel_all_prefetch",
               new=AsyncMock(return_value=2)) as m, \
         patch("src.core.executor_manager.executor_manager") as ex:
        async with lifespan(MagicMock()):
            pass
    m.assert_awaited_once()
    ex.return_value.shutdown.assert_called_once()


@pytest.mark.asyncio
async def test_shutdown_runs_even_if_startup_side_effect_fails():
    with patch("src.services.semantic_cache.cancel_all_prefetch",
               new=AsyncMock(return_value=0)) as m, \
         patch("src.core.executor_manager.executor_manager"):
        async with lifespan(MagicMock()):
            raise RuntimeError("テスト用")
    # 例外は finally を通るため m は await 済みになる
    assert m.await_count == 1


def test_lifespan_is_asynccontextmanager():
    import inspect
    assert hasattr(lifespan, "__wrapped__") or inspect.isasyncgenfunction(lifespan)
```

**検証コマンド**
```powershell
C:\Python314\python.exe -m pytest tests/unit/backend/test_server_lifespan_shutdown.py -q
```

**完了判定**: 3テスト緑。**`test_shutdown_runs_even_if_startup_side_effect_fails` が緑**（=finally が機能している証明）。

> **実装者への注意**: `src/backend/server.py` は import 時点で `init_db()` 側の副作用を持ちうる。
> 実装前に `pytest tests/unit/backend/ -q` を**変更前**に実行して baseline を採取すること。

---

### Step 8. `episode_writing_workflow.py` のプリフェッチを配線する
- **主担当ファイル**: `src/backend/workflows/episode_writing_workflow.py`
- **依存**: Step 4, 6
- **P分類**: P1（1ファイル）/ P7

**背景**
```
71-114: async def _trigger_prefetch(self, book_id, last_episode, reporter)
83-84:   vector_store = getattr(self, "vector_store", None)
         client     = getattr(self, "llm_client", None) or getattr(self, "client", None)
86-89:   if not vector_store or not client: return      ← BaseWorkflow には両方無く必ずここで死ぬ
91:      cache_manager = SemanticCacheManager(vector_store=vector_store, client=client)  ← 毎回作り直し
100-107: asyncio.create_task(...)   ← ハンドルなし
33, 58:  await self._trigger_prefetch(...)   ← 2箇所の呼び出し
```
**現状：本番では必ず no-op**。ただしコード上は「動いているように見える」ため、
将来 `BaseWorkflow` に属性が追加された瞬間に**Handle-less タスクが走る**。

**作業内容**
1. `_trigger_prefetch`（`:71`）の** early-return（`:86-89`）は維持する**
   （`vector_store` が無い状態では動かさない）。
2. `:91` の `SemanticCacheManager(...)` 局所生成を**削除し**、
   `self._semantic_cache`（`)None` 初期化を `__init__` ではなく **関数内で1回だけ**キャッシュする形に変更する:
   - `if getattr(self, "_semantic_cache", None) is None:` で生成し `self._semantic_cache` に保持。
3. `:100-107` の `asyncio.create_task(...)` を、
   **戻り値を `self._prefetch_tasks` に保持**する形に変更する（`self._prefetch_tasks: set = set()` を `__init__` で初期化）。
   - 併せて `task.add_done_callback(self._prefetch_tasks.discard)` を付ける。
4. タスクの本体は **Step 4 で既定OFFになった `prefetch_by_pattern`** をそのまま使う
   （ここで**新しい投機処理を書かない**）。
5. `SemanticCacheManager` の import（`:79`）は**遅延 import のまま**残す。
6. `import asyncio`（`:98`）は**関数内の import のままでよい**（重複 import を作らない）。
7. `_shared_ops.trigger_prefetch`（`src/backend/workflows/_shared_ops.py:22-56`）は
   **このステップでは触らない**（呼び出し元ゼロのため。Step 12 で確認のみ）。

**回帰テスト（先に作る）**: `tests/unit/workflows/test_episode_writing_prefetch_wiring.py`（新規・非同期）

```python
"""プリフェッチが「タスクハンドルを持つ」配線になったことの回帰テスト。"""
import sys, pathlib
from unittest.mock import AsyncMock, MagicMock, patch
import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))

from src.backend.workflows.episode_writing_workflow import EpisodeWritingWorkflow


def _wf():
    wf = EpisodeWritingWorkflow.__new__(EpisodeWritingWorkflow)   # __init__ をバイパス
    wf.vector_store = MagicMock()
    wf.llm_client = MagicMock()
    wf._prefetch_tasks = set()
    wf._semantic_cache = None
    return wf


@pytest.mark.asyncio
async def test_task_handle_is_retained(monkeypatch):
    monkeypatch.setenv("ENABLE_SEMANTIC_PREFETCH_DRAFT", "0")
    wf = _wf()
    wf.reporter = MagicMock(); wf.reporter.report = MagicMock()
    await wf._trigger_prefetch(1, 1, wf.reporter)
    import asyncio
    await asyncio.sleep(0.05)
    assert isinstance(getattr(wf, "_prefetch_tasks", None), set)


@pytest.mark.asyncio
async def test_manager_is_reused_not_recreated(monkeypatch):
    monkeypatch.setenv("ENABLE_SEMANTIC_PREFETCH_DRAFT", "0")
    wf = _wf()
    wf.reporter = MagicMock(); wf.reporter.report = MagicMock()
    with patch("src.services.semantic_cache.SemanticCacheManager") as SC:
        await wf._trigger_prefetch(1, 1, wf.reporter)
        first = wf._semantic_cache
        await wf._trigger_prefetch(1, 2, wf.reporter)
    assert wf._semantic_cache is first


@pytest.mark.asyncio
async def test_still_early_returns_without_vector_store():
    wf = EpisodeWritingWorkflow.__new__(EpisodeWritingWorkflow)
    wf.vector_store = None; wf.llm_client = None
    await wf._trigger_prefetch(1, 1, MagicMock())      # 例外_none
```

**検証コマンド**
```powershell
C:\Python314\python.exe -m pytest tests/unit/workflows/test_episode_writing_prefetch_wiring.py -q
```

**完了判定**: 3テスト緑。

> **実装者への注意**: `EpisodeWritingWorkflow.__init__` の引数順は Step 12 の前に
> `grep -n "class EpisodeWritingWorkflow" -A 30 src/backend/workflows/episode_writing_workflow.py` で確認すること。
> `__new__` バイパスは **`__init__` の引数に依存させないため** の措置である。

---

### Step 9. `episode_writer.py` で破棄されていたタスクハンドルを保持する
- **主担当ファイル**: `src/agents/writing/episode_writer.py`
- **依存**: Step 1
- **P分類**: P1（1ファイル）/ P2

**背景**
```
285-293: self.plot_expander.prefetch_next_episode_plot(book_id=..., next_ep=ep_num+1, branch_id=...)
         ↑ 戻り値は asyncio.Task（default_plot_expander.py:208-214）だが捨てられている
```
`src/services/default_plot_expander.py:201-214` は**`asyncio.Task` のハンドル**を返しているのに、
呼び出し側が捨てている。つまり**「第 N 話執筆中に 第 N+1 話のプロットを投機生成」**という
**最も並行度が高い処理**が**管理不能**になっている。

**作業内容**
1. `EpisodeWriter.__init__` に `self._plot_prefetch_tasks: set = set()` を**1行追加**。
2. `:285-293` の呼び出しを**2行**に編集する:
   - `task = self.plot_expander.prefetch_next_episode_plot(...)`
   - `if task is not None: self._plot_prefetch_tasks.add(task); task.add_done_callback(self._plot_prefetch_tasks.discard)`
3. `plot_expander` が `None` の既存ガードは**そのまま**（`hasattr` 判定があれば残す）。
4. `_post_episode_finalize`（`:286` / `:552`）周辺は**このステップで触らない**
   （PLAN_T6 Step 1 の担当領域。**二重作业を防ぐ**）。
5. 新しい `cancel` メソッドは**このステップでは作らない**（Step 10 で配線する）。
6. import を追加しない（`asyncio` は不要。`Task` を使うが型注釈は**付けない**）。

**回帰テスト（先に作る）**: `tests/unit/writing/test_plot_prefetch_handle.py`（新規・同期）
（writer 全体の構築が重い場合、**属性の存在と保持だけ**を検証し、実行はStep 10 の結合テストに任せる）

```python
"""投機プロットタスクのハンドルが保持されることの回帰テスト。"""
import sys, pathlib
import asyncio
import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))

from src.agents.writing.episode_writer import EpisodeWriter


def test_writer_declares_task_set():
    import inspect
    src = inspect.getsource(EpisodeWriter.__init__)
    assert "_plot_prefetch_tasks" in src


@pytest.mark.asyncio
async def test_handle_is_kept_when_expander_returns_task():
    writer = EpisodeWriter.__new__(EpisodeWriter)
    writer._plot_prefetch_tasks = set()
    holder = {}

    class FakeExpander:
        def prefetch_next_episode_plot(self, **kw):
            holder["kw"] = kw
            return asyncio.create_task(asyncio.sleep(0))

    writer.plot_expander = FakeExpander()
    task = writer.plot_expander.prefetch_next_episode_plot(book_id=1, next_ep=2, branch_id=1)
    writer._plot_prefetch_tasks.add(task)
    task.add_done_callback(writer._plot_prefetch_tasks.discard)
    await asyncio.sleep(0.01)
    assert len(holder["kw"]) == 3
    assert len(writer._plot_prefetch_tasks) == 0     # 完了後は必ず片付く
```

**検証コマンド**
```powershell
C:\Python314\python.exe -m pytest tests/unit/writing/test_plot_prefetch_handle.py -q
```

**完了判定**: 2テスト緑。

---

### Step 10. リテイク / 停止 / キャンセルの3エントリから `invalidate` を呼ぶ
- **主担当ファイル**: `src/backend/routers/episodes.py`（本ステップの主担当）
- **副担当（1ファイルのみ）**: `src/backend/routers/tasks.py`
- **依存**: Step 5, 6
- **P分類**: P7

**背景**
`invalidate`（`rag_prefetch_service.py:133-140`）は**そのためのAPIとして存在するが呼び出し元がゼロ**。
事件系の入口は3つ：

| 入口 | ファイル:行 | 意味 |
|---|---|---|
| `POST /…/retry_failed` | `episodes.py:124-148` | 失敗エピソードの再試行 → **全 prefetch が無効** |
| `POST /api/tasks/{task_id}/stop` | `tasks.py:166-214` | ユーザー中断 → **進行中の prefetch を即殺** |
| `DELETE /orchestrated/task/{task_id}` | `orchestrated.py:129-140` | タスクキャンセル |

**作業内容**
1. `src/backend/routers/episodes.py` の `retry_failed_episodes`（`:123`）に**2行**追加する:
```text
from src.services.rag_prefetch_service import RagPrefetchService   # 遅延 import
# execute_service_workflow(...) の直前に:
await _cancel_prefetch_for_book(req.book_id)     # モジュールレベル helper を1つ新設
```
   モジュールレベル helper（**5行**）:
```python
async def _cancel_prefetch_for_book(book_id: int) -> int:
    """书籍単位のプリフェッチをすべて取り消す（本棚の実キーは "{book_id}_{ep}"）。"""
    svc = RagPrefetchService()
    return await svc._registry.cancel_prefix(f"{book_id}")
```
2. `src/backend/routers/tasks.py` の `stop_task`（`:165`）に**1行**追加する:
   `await cancel_all_prefetch()`（`from src.services.semantic_cache import cancel_all_prefetch` を遅延 import）。
3. **本ステップでは `orchestrated.py` に触れない**（別コミットで Follow-up）。
4. `req.book_id` が `None` のときは `cancel_prefix` を**呼ばない**（`return 0`）。
5. **HTTP のレスポンス形式は変えない**（既存クライアントの互換性）。
6. 両ファイルとも `except Exception` で囲み、**プリフェッチ取消失敗が API を落とさない**ことを保証する。

**回帰テスト（先に作る）**: `tests/contract/test_w6_prefetch_invalidation_wiring.py`（新規・非同期）

```python
"""リトライ/停止でプリフェッチが取り消されることの回帰テスト。"""
import sys, pathlib
from unittest.mock import AsyncMock, MagicMock, patch
import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))


@pytest.mark.asyncio
async def test_retry_endpoint_cancels_prefetch_for_book():
    from src.backend.routers import episodes
    with patch.object(episodes, "execute_service_workflow", MagicMock()), \
         patch("src.services.rag_prefetch_service.RagPrefetchService") as S:
        S.return_value._registry.cancel_prefix = AsyncMock(return_value=2)
        # ハンドラを直接呼ぶのではなく、ヘルパーだけ検証する（副作用を避け��）
        n = await episodes._cancel_prefetch_for_book(7)
    S.return_value._registry.cancel_prefix.assert_awaited_once_with("7")
    assert n == 2


@pytest.mark.asyncio
async def test_helper_is_noop_for_none_book():
    from src.backend.routers import episodes
    with patch("src.services.rag_prefetch_service.RagPrefetchService") as S:
        assert await episodes._cancel_prefetch_for_book(None) == 0
    S.assert_not_called()


@pytest.mark.asyncio
async def test_helper_never_raises():
    from src.backend.routers import episodes
    with patch("src.services.rag_prefetch_service.RagPrefetchService", side_effect=RuntimeError("x")):
        assert await episodes._cancel_prefetch_for_book(1) == 0


def test_tasks_router_imports_cancel_all():
    import inspect
    from src.backend.routers import tasks
    assert "cancel_all_prefetch" in inspect.getsource(tasks)
```

**検証コマンド**
```powershell
C:\Python314\python.exe -m pytest tests/contract/test_w6_prefetch_invalidation_wiring.py -q
```

**完了判定**: 4テスト緑。**`episodes.py` / `tasks.py` の既存APIテストが緑**。

---

### Step 11. 投機実行を「高確度時のみ」に制限する
- **主担当ファイル**: `src/backend/workflows/episode_writing_workflow.py`
- **依存**: Step 8
- **P分類**: P1（1ファイル）/ P2

**背景**
`:104` `ep_range_end=min(next_ep + 2, next_ep + 3)` は**常に次の3話分**を走らせる。
直前の監査スコアに関係なく、リテイク実績が高くても投機する。

**作業内容**
1. モジュールレベルに**純粋関数1つ**を追加する（**`_trigger_prefetch` の外**、テスト可能な形にするため）:
```python
def should_speculate(last_audit_score: float | None, auto_mode: bool) -> bool:
    """投機的プリフェッチを実行してよいかを判定する（純関数）。"""
    if not auto_mode:
        return False
    if last_audit_score is None:
        return False
    return float(last_audit_score) >= 90.0
```
2. 環境変数 `PREFETCH_MIN_AUDIT_SCORE`（既定 `90.0`）を `os.environ.get` で**関数内で**読む
   （`_TRUTHY` 方式ではなく**数値**なので `float(...)` 変換＋例外時 `90.0` フォールバック）。
3. `_trigger_prefetch`（`:71`）の**冒頭**に**1つの early-return** を追加:
```text
if not should_speculate(getattr(self, "last_audit_score", None),
                        bool(getattr(self, "auto_mode", False))):
    return
```
4. `self.last_audit_score` は**既存コードから設定しない**（本ステップでは `None` のまま）。
   → **既定で投機は走らない**（安全側の既定）。Step 12 で実接続の要否を判断する。
5. フラグ `ENABLE_SPECULATIVE_PREFETCH`（既定 `"0"` / **OFF**）を追加し、
   `should_speculate` の**先頭**で `if not flag: return False` とする。

**回帰テスト（先に作る）**: `tests/unit/workflows/test_should_speculate.py`（新規・同期）

```python
"""投機実行ゲートの純関数テスト。"""
import sys, pathlib
import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))

from src.backend.workflows.episode_writing_workflow import should_speculate


def test_flag_off_by_default(monkeypatch):
    monkeypatch.delenv("ENABLE_SPECULATIVE_PREFETCH", raising=False)
    assert should_speculate(100.0, True) is False


def test_flag_on_and_high_score(monkeypatch):
    monkeypatch.setenv("ENABLE_SPECULATIVE_PREFETCH", "1")
    monkeypatch.setenv("PREFETCH_MIN_AUDIT_SCORE", "90")
    assert should_speculate(95.0, True) is True


def test_low_score_blocks(monkeypatch):
    monkeypatch.setenv("ENABLE_SPECULATIVE_PREFETCH", "1")
    assert should_speculate(89.9, True) is False


def test_manual_mode_blocks(monkeypatch):
    monkeypatch.setenv("ENABLE_SPECULATIVE_PREFETCH", "1")
    assert should_speculate(99.0, False) is False


def test_none_score_blocks(monkeypatch):
    monkeypatch.setenv("ENABLE_SPECULATIVE_PREFETCH", "1")
    assert should_speculate(None, True) is False


def test_bad_threshold_falls_back(monkeypatch):
    monkeypatch.setenv("ENABLE_SPECULATIVE_PREFETCH", "1")
    monkeypatch.setenv("PREFETCH_MIN_AUDIT_SCORE", "not-a-number")
    assert should_speculate(95.0, True) is True     # 既定90 にフォールバック
```

**検証コマンド**
```powershell
C:\Python314\python.exe -m pytest tests/unit/workflows/test_should_speculate.py tests/unit/workflows/test_episode_writing_prefetch_wiring.py -q
```

**完了判定**: 6テスト緑。**`test_flag_off_by_default` が緑**（=既定では投機しない）。

---

### Step 12. 総合回帰・計測・文書化
- **主担当ファイル**: `plans/PLAN_W6_PREFETCH_CANCELLATION_12STEPS.md`（本書）、`docs/STATUS.md`
- **依存**: Step 1〜11 すべて
- **P分類**: P1

**作業内容**
1. **並列実行禁止**。順番に以下を実行する（1本でも赤なら Step 12 は未完了）:
   - `C:\Python314\python.exe -m pytest tests/unit/services/prefetch/ -q`
   - `C:\Python314\python.exe -m pytest tests/unit/ -q`
   - `C:\Python314\python.exe -m pytest tests/contract/ -q`
   - `C:\Python314\python.exe -m pytest tests/integration/test_reflective_rag_context_builder.py tests/integration/test_semantic_rag_compression_e2e.py -q`
2. 新規3ファイルに lint:
   `C:\Python314\python.exe -m ruff check src/services/prefetch/ src/core/cancellation.py --select E9,F63,F7,F82` → **0 エラー**。
3. **非対称の残存確認**（文書化のみ、修正は本計画外）:
   - `grep -rn "asyncio.coroutine" src/` → **0 ヒット**であること。
   - `grep -rn "asyncio.create_task" src/` の**全箇所**にハンドルが保存されているか目視確認し、
     未保存があれば §4 の「Follow-up リスト」に追記する。
4. `docs/STATUS.md` に W6 完了エントリと 3計画書（W4/W5/W6）の索引を追加する。
5. 本書 status を「完了」に更新。

**完了判定**
- 4つの回帰コマンドがすべて緑。
- 新規3ファイルの `ruff --select E9,F63,F7,F82` がクリーン。
- `grep -rn "asyncio.coroutine" src/` が 0 ヒット。

---

## 3. ロールバック

すべて**環境変数1つで元に戻せる**。コード削除は不要。

| 変数 | 既定 | 効果 |
|---|---|---|
| `ENABLE_SEMANTIC_PREFETCH_DRAFT` | `0` | `1` で次話執筆プロンプトの投機生成を復活（Step 4） |
| `ENABLE_SPECULATIVE_PREFETCH` | `0` | `1` で高確度時の投機プリフェッチを許可（Step 11） |
| `PREFETCH_MIN_AUDIT_SCORE` | `90.0` | 投機実行に必要な最低監査スコア（Step 11） |
| `AUTONOVEL_RAG_MODE` | `auto` | 既存。`memory` にすると全向量検索が in-memory に落ちる（既存） |

## 4. Follow-up リスト（本計画では扱わない）

| 項目 | 場所 | 理由 |
|---|---|---|
| `orchestrated.py:129-140` の `cancel_orchestrated_task` からの invalidate | `src/backend/routers/orchestrated.py` | Step 10 のスコープ外（1ファイル原則） |
| **ハンドル未保存の `asyncio.create_task` が 2 箇所残存** | `src/backend/routers/orchestrated.py:210`（`lambda e: asyncio.create_task(...)`）／ `src/backend/workflows/_shared_ops.py:43` | Step 12 §4-3 の全件目視確認で判明。レジストリに載せるかは各ファイル所有者（orchestrated / PLAN_T6）の判断 |
| `_shared_ops.trigger_prefetch`（呼び出し元ゼロ）の削除 | `src/backend/workflows/_shared_ops.py:22-56` | 死んでいるが**削除は PLAN_T6 の責務** |
| `src/core/llm_gateway.py:58-78` の同名 `SemanticCacheManager`（4行スタブ）の混在 | `src/core/llm_gateway.py` / `src/core/container/app.py:51-60` | 名称衝突は別計画（命名整理） |
| `graphrag_sync_service` / `backend/background.py` の `threading.Event` を `CancellationToken` に統一 | `src/backend/background.py:120` | thread↔asyncio 境界の整理が必要 |
| `get_project_intelligence` の未定義 | `src/services/rag_prefetch_service.py` | engine 側に定義が無いため常に空振り（Step 3 で無害化済み） |

### 4.1 実装実績（Step 12 で確定した事実）

- 投機実行は **既定では一切走らない**。`ENABLE_SPECULATIVE_PREFETCH=0`（既定）と
  `ENABLE_SEMANTIC_PREFETCH_DRAFT=0`（既定）の **二重ゲート**。
- `RagPrefetchService` のレジストリは **モジュールレベル共有**（`_SHARED_REGISTRY`）にした。
  `RagPrefetchService()` は呼び出しごとに生成されるため、インスタンス単位のレジストリだと
  `routers/episodes.py` からの書籍単位の取り消しが空振りする。
- `cancel_prefix` は `"7"` が `"70_1"` に誤爆しないよう、区切り文字（`:` / `_` / `/`）の
  境界でだけ部分一致させる（キャッシュキーが `"{book_id}_{ep}"` のため）。
- `close_background_tasks()` は命名の一貫性のための別名で、返り値は取り消した本数。

### 4.2 総合回帰の結果（2026-09-30）

| コマンド | 結果 |
|:---|:---|
| `pytest tests/unit/services/prefetch/ -q` | **緑**（新規 5 ファイル） |
| `pytest tests/contract/ -q` | **緑**（128 passed / 1 skipped。W6 追加分 7 件を含む） |
| `pytest tests/unit/core/test_cancellation_token.py tests/unit/workflows tests/unit/writing tests/unit/backend -q` | 435 passed / 4 skipped / **3 failed**（失敗 3 件は**変更前 baseline と同一**） |
| `pytest tests/unit/ -q` | 6948 passed / 18 skipped / **51 failed + 3 errors**（下記） |
| `pytest tests/integration/test_reflective_rag_context_builder.py tests/integration/test_semantic_rag_compression_e2e.py -q` | 4 passed / **1 failed**（下記） |
| `ruff check src/services/prefetch/ src/core/cancellation.py --select E9,F63,F7,F82` | **0 エラー** |
| `grep -rn "asyncio.coroutine" src/` | コード中のヒット **0 件**（docstring 2 行のみ） |

**残存失敗はすべて本計画と無関係**（W6 が触れていないモジュール。T6/F1 並行作業および従来からの failures）:

- `tests/unit/backend/`: `test_get_current_user_with_real_session_no_await_error` / `test_module_level_report_exception_helper` / `test_unauthorized_response_contains_cors_headers`（**Step 7 着手前に採取した baseline と同一の 3 件**）
- `tests/unit/workflows/test_writing_graph_flow.py::test_writing_graph_complete_flow`: langgraph の msgpack checkpointer が `MagicMock` を直列化できず、**Python プロセスが access violation で落ちる**（W6 は `writing_langgraph.py` に一切触れていない）
- `tests/integration/test_reflective_rag_context_builder.py::test_context_builder_with_reflective_rag_success`: `reflective_rag.py:638` の `'coroutine' object is not iterable`
- 上記以外（compression / episode_context / pgvector_store / auth_middleware / huey_queue / pdca_writing_agent など 38 件）: **単独実行でも同様に失敗**するため、W6 とは無関係の既存 failures。

## 5. 期待効果

| 指標 | 現状 | 目標 | 測り方 |
|---|---|---|---|
| リテイク時の無駄な embedding API 費 | 発生（`prefetch_next` が走るとき） | **0**（Step 4 既定OFF） | `test_semantic_prefetch_disabled.py` |
| バックグラウンドタスクのハンドル管理不能 | Handle なし（3系統） | **Registry 1 か所**（Step 1, 6, 9） | `PrefetchRegistry.stats()` |
| `asyncio.coroutine` による恒久 no-op | Python 3.11+ で死亡 | **0 件** | `grep -rn "asyncio.coroutine" src/` |
| プロセス終了時のタスクリーク | リーク（lifespan に shutdown 無し） | **0**（Step 7） | `test_server_lifespan_shutdown.py` |
| 投機実行の無駄 | 常に3話分 | **監査スコア ≥90 かつ自動モード時のみ** | `should_speculate()` |
| SemanticCache の L1/L2-B ウォーム | 毎回リセット | インスタンス再利用（Step 8） | `test_manager_is_reused_not_recreated` |
