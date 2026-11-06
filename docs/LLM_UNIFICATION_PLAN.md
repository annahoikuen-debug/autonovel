# LLM 統合計画 (LLM_UNIFICATION_PLAN.md)

> **目的**: LLM 関連モジュールが分散している4箇所を `src/llm/` に統合する。
>
> **統合先**: `src/llm/`（既に `resilient_gateway.py`, `circuit_breaker.py`, `model_router.py` がここにあり、`src/core/llm/__init__.py` がここを re-export している）

---

## 現状: LLM 関連モジュールの分散

| 場所 | 内容 | ファイル数 | 行数 | 依存ファイル数 |
|------|------|-----------|------|--------------|
| `src/llm/` | resilient_gateway, circuit_breaker, model_router, base, fallback_policy, gemini_provider, openai_provider | 7 | ~1,161 | 13 |
| `src/core/llm/` | unified_interface, factory, types, adapters (5種) | ~8 | ~4,453 | 22 |
| `src/core/llm_clients/` | base, gemini, openai (低レベルクライアント) | 3 | ~696 | 3 |
| `src/services/llm/` | adapters, factory, failover, retry, tracked_adapter, prompts 等 | ~14 | ~1,431 | 35 |

**既存の shim（後方互換）**:
- `src/services/llm/circuit_breaker.py` → `src/llm/circuit_breaker.py` への shim（既存）
- `src/core/llm/__init__.py` → PEP 562 遅延 import で `src/llm/` 等から re-export（既存）

---

## 統合後のディレクトリ構成

```
src/llm/  ← 統合先（公開 API のエントリポイント）
├── __init__.py              (新規作成: 公開 API 一覧)
├── base.py                  (維持: LLMProvider, LLMResponse)
├── circuit_breaker.py       (維持: LLMCircuitBreaker - 統合の中心)
├── fallback_policy.py       (維持)
├── model_router.py          (維持: resolve_model 等)
├── resilient_gateway.py     (維持: ResilientLLMGateway)
├── gemini_provider.py       (維持)
├── openai_provider.py       (維持)
├── clients/                 ← src/core/llm_clients/ を移設 (Step 8)
│   ├── __init__.py
│   ├── base.py              (旧 base.py)
│   ├── gemini.py            (旧 gemini.py)
│   └── openai.py            (旧 openai.py)
├── unified/                 ← src/core/llm/ を移設 (Steps 9, 11)
│   ├── __init__.py
│   ├── interface.py         (旧 unified_interface.py)
│   ├── types.py             (旧 types.py)
│   ├── factory.py           (旧 factory.py)
│   └── adapters/            ← src/core/llm/adapters/ を移設 (Step 9)
│       ├── __init__.py
│       ├── claude.py        (旧 claude_unified_client.py)
│       ├── gemini.py        (旧 gemini_unified_client.py)
│       ├── mock.py          (旧 mock_unified_client.py)
│       ├── ollama.py        (旧 ollama_unified_client.py)
│       └── openai.py        (旧 openai_unified_client.py)
└── adapters/                ← src/services/llm/ を移設 (Step 10)
    ├── __init__.py
    ├── base.py              (旧 base.py)
    ├── factory.py           (旧 factory.py)
    ├── gemini.py            (旧 gemini_adapter.py)
    ├── mock.py              (旧 mock_adapter.py)
    ├── openai.py            (旧 openai_adapter.py)
    ├── ollama.py            (旧 ollama_adapter.py)
    ├── claude.py            (旧 claude_adapter.py)
    ├── vllm.py              (旧 vllm_adapter.py)
    ├── tracked.py           (旧 tracked_adapter.py)
    ├── failover.py          (旧 provider_failover.py)
    ├── retry.py             (旧 retry.py)
    ├── prompts.py           (旧 prompts.py)
    └── prompt_cache.py      (旧 prompt_cache_builder.py)
```

---

## 移動マッピング詳細

| Step | 移動元 | 移動先 | シム |
|------|--------|--------|------|
| 8 | `src/core/llm_clients/{base,gemini,openai}.py` | `src/llm/clients/{base,gemini,openai}.py` | `src/core/llm_clients/__init__.py` |
| 9 | `src/core/llm/adapters/{claude,gemini,mock,ollama,openai}_unified_client.py` | `src/llm/unified/adapters/{claude,gemini,mock,ollama,openai}.py` | `src/core/llm/adapters/__init__.py` |
| 10 | `src/services/llm/{base,factory,gemini,mock,openai,ollama,claude,vllm,tracked,failover,retry,prompts,prompt_cache}.py` | `src/llm/adapters/{base,factory,gemini,mock,openai,ollama,claude,vllm,tracked,failover,retry,prompts,prompt_cache}.py` | `src/services/llm/__init__.py` |
| 11 | `src/core/llm/{unified_interface,types,factory}.py` | `src/llm/unified/{interface,types,factory}.py` | `src/core/llm/__init__.py` (_LAZY_EXPORTS パス更新) |
| 12 | `src/services/llm/circuit_breaker.py` | 移動なし（既存 shim を維持） | `src/services/llm/circuit_breaker.py` |

---

## 依存グラフの参照 (var/import_graph.json)

移動前に `var/import_graph.json` で各ファイルの import 依存を確認し、移動後に import が壊れていないことを機械的に検証する。

### 確認すべき主要な import 経路

```
src/core/llm_clients → src/core/llm/__init__.py, src/core/llm_gateway.py, src/llm/gemini_provider.py, src/llm/openai_provider.py
src/core/llm/adapters → src/core/llm/__init__.py, tests/
src/services/llm → src/agents/erotic/evaluator.py, src/agents/specialists/unified_auditor.py, src/audit/unified_llm_auditor.py, src/backend/routers/*.py, src/backend/tasks/generation_tasks.py, src/core/container/app.py, src/llm/resilient_gateway.py, src/services/*.py, tests/
src/llm → src/agents/specialists/model_router.py, src/agents/writing/episode_writer.py, src/backend/engine.py, src/backend/routers/*.py, src/backend/tasks/generation_tasks.py, src/core/llm/__init__.py, src/core/llm_gateway.py, src/services/llm/circuit_breaker.py, src/services/llm_service.py, tests/
```

---

## 注意点

1. **circuit_breaker の重複**: `src/llm/circuit_breaker.py`（本体）と `src/services/llm/circuit_breaker.py`（既存 shim）がある。Step 12 で shim であることを再確認し、追加移動は行わない。

2. **`src/core/llm_gateway.py`**: `src/core/llm_clients` を import している。Step 8 後、import パスを `src.llm.clients` に更新する必要がある。

3. **`src/llm/openai_provider.py`**: `src.backend.engine_utils` を import している。これは `src.backend` への依存だが、LLM 層が backend に依存するのは問題ない（下位層への依存）。

4. **テストの再配置**: Step 13 で `tests/unit/llm_clients/` → `tests/unit/llm/clients/`、`tests/unit/services/llm/` → `tests/unit/llm/adapters/` に移設する。
