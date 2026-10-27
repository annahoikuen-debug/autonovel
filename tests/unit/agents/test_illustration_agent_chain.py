"""IllustrationAgent が後続チェーンを止めないことの回帰テスト。

T6 Step 4（K4）の回帰防止。

`IllustrationAgent` は `ctx.artifacts["request"]` を要求するが、
その供給元がリポジトリ内に存在しないため常に no-op（`next_agent=None`）になる。
素に `.run` をノード登録すると `orchestrator.py:808` の
`current = result.next_agent` が None になり、**後続の MarketingAgent に到達しない**。

一方 manifest 経路では `IllustrationSkill` は終端ノード（`runs_before: []`）のため、
`next_agent=None` のままが正しい。よって修正は**エージェント本体ではなく
登録箇所**（`generation_tasks.py` での `_make_skill_node` 利用）で行う。
"""

import inspect
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from src.agents.orchestrator import (
    AgentContext,
    AgentName,
    _make_execute_node,
)

GENERATION_TASKS = Path("src/backend/tasks/generation_tasks.py")
MANIFEST = Path("src/agents/skills/manifest.yaml")


def _ctx_without_request() -> AgentContext:
    """`request` を含まない artifacts（= 本番の実状）。"""
    return AgentContext(
        book_id=1,
        branch_id=1,
        ep_num=1,
        artifacts={"title": "テスト作品"},
    )


def _make_illustration_agent():
    from src.agents.illustration_agent import IllustrationAgent

    return IllustrationAgent(image_service=MagicMock(), repo=MagicMock(), llm=MagicMock())


# ── 実挙動 ───────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_noop_is_not_an_error():
    """request が無くても error を返さないこと（Step 11 の判断の前提）。"""
    agent = _make_illustration_agent()
    result = await agent.execute(_ctx_without_request())
    assert result.error is None
    assert result.artifacts.get("illustration_skipped") is True


@pytest.mark.asyncio
async def test_illustration_agent_itself_stays_terminal():
    """エージェント本体は `next_agent=None` を返す（manifest 経路の終端契約）。

    ここを直すと manifest 経路（IllustrationSkill = 終端）が壊れる。
    """
    agent = _make_illustration_agent()
    result = await agent.execute(_ctx_without_request())
    assert result.next_agent is None, (
        "IllustrationAgent 本体が MARKETING を返すようになっていない。"
        "manifest 経路で終端ノードの契約が壊れる。"
    )


@pytest.mark.asyncio
async def test_registered_node_chains_to_marketing():
    """`_make_execute_node` で登録した場合、後続 MARKETING へ進めること（K4 の解消）。"""
    node = _make_execute_node(_make_illustration_agent(), AgentName.MARKETING)
    result = await node(_ctx_without_request())
    assert result.error is None
    assert result.next_agent == AgentName.MARKETING, (
        "no-op でも後続チェーンを止めている（K4 の再発）"
    )


@pytest.mark.asyncio
async def test_registered_node_satisfies_orchestrator_node_protocol():
    """ノードプロトコル `Callable[[AgentContext], ...]` に乗ること。

    `IllustrationAgent` は公開 API のため `run` を上書きしており、
    そのまま登録すると `run(ctx)` が TypeError になる。
    """
    node = _make_execute_node(_make_illustration_agent(), AgentName.MARKETING)
    result = await node(_ctx_without_request())  # TypeError が出てはいけない
    assert result.artifacts.get("illustration_skipped") is True


def test_public_run_api_is_preserved():
    """公開 API `run(request=...)` を上書きで壊していないこと。"""
    from src.agents.illustration_agent import IllustrationAgent

    sig = inspect.signature(IllustrationAgent.run)
    has_var_keyword = any(
        p.kind is inspect.Parameter.VAR_KEYWORD for p in sig.parameters.values()
    )
    assert has_var_keyword, (
        "IllustrationAgent.run の **kwargs シグネチャを壊した。"
        "illustration_workflow.py / illustrations.py がDependsしている"
    )


@pytest.mark.asyncio
async def test_explicit_next_agent_is_not_overridden():
    """エージェントが明示した next_agent は上書きしないこと。"""

    class _Stub:
        async def execute(self, ctx):
            from src.agents.orchestrator import AgentResult

            return AgentResult(next_agent=AgentName.AUDIT, artifacts={})

    node = _make_execute_node(_Stub(), AgentName.MARKETING)
    result = await node(_ctx_without_request())
    assert result.next_agent == AgentName.AUDIT


# ── 配線の固定 ───────────────────────────────────────────────────


def test_generation_tasks_registers_illustration_with_execute_node():
    """`generation_tasks.py` が `_make_execute_node` 経由で登録していること。"""
    source = GENERATION_TASKS.read_text(encoding="utf-8")
    assert "_make_execute_node" in source, (
        "generation_tasks が _make_execute_node を import/使用していない。"
        "ILLUSTRATION → MARKETING のチェーンが切れている。"
    )
    assert "nodes[AgentName.ILLUSTRATION] = illustration_node" in source, (
        "ILLUSTRATION ノードが execute ベースのノードに置き換えられていない"
    )


def test_manifest_still_declares_illustration_terminal():
    """manifest 経路の終端契約が維持されていること（回帰防止）。"""
    text = MANIFEST.read_text(encoding="utf-8")
    block = text.split("name: IllustrationSkill", 1)[-1].split("- name:", 1)[0]
    assert "runs_before: []" in block, (
        "manifest で IllustrationSkill が終端ノードでなくなった"
    )
