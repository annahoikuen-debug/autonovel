"""tests/unit/agents/test_illustration_agent_contract.py.

v5.3 / Step 11 (K4): `IllustrationAgent` のチェーン契約の検証。

`IllustrationAgent.execute` は `artifacts["request"]` を要求するが、
設定する箇所がリポジトリ内に存在せず、常に `error` を返していた。
`error` を返すと Orchestrator の `error_continued` 分岐に落ち、
artifacts にエラーが混入していた。

`IllustrationSkill` は manifest 上で終端ノード（`runs_before: []`）なので
`next_agent=None` 自体は正しい。問題は「error を返していた」ことのみ。
"""

from __future__ import annotations

import inspect
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

ROOT_DIR = Path(__file__).resolve().parent.parent.parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

import src.backend.database  # noqa: F401
from src.agents.illustration_agent import IllustrationAgent  # noqa: E402


def _agent() -> IllustrationAgent:
    agent = IllustrationAgent.__new__(IllustrationAgent)
    agent.llm = MagicMock()
    agent.cover_generator = MagicMock()
    agent.character_illustrator = MagicMock()
    agent.scene_illustrator = MagicMock()
    agent.scene_service = MagicMock()
    agent.yonkoma_illustrator = MagicMock()
    agent.emit_event = MagicMock()  # type: ignore[method-assign]
    return agent


@pytest.mark.asyncio
async def test_missing_request_is_noop_not_error() -> None:
    """`request` 不在は error ではなく正常な no-op であること。"""
    from src.agents.orchestrator import AgentContext

    agent = _agent()
    ctx = AgentContext(book_id=1, branch_id=1, ep_num=1, artifacts={})
    result = await agent.execute(ctx)

    assert result.error is None, (
        f"request 不在を error として返している: {result.error}"
    )
    assert result.artifacts.get("illustration_skipped") is True
    assert result.artifacts.get("illustration_result") is None


@pytest.mark.asyncio
async def test_missing_request_terminates_chain_cleanly() -> None:
    """終端ノードなので `next_agent=None` が正しい（Chain を断たない）。"""
    from src.agents.orchestrator import AgentContext

    agent = _agent()
    ctx = AgentContext(book_id=1, branch_id=1, ep_num=1, artifacts={})
    result = await agent.execute(ctx)
    assert result.next_agent is None


@pytest.mark.asyncio
async def test_skipped_event_is_emitted() -> None:
    """スキップの事実がイベントとして通知されること（可観測性）。"""
    from src.agents.orchestrator import AgentContext

    agent = _agent()
    ctx = AgentContext(book_id=1, branch_id=1, ep_num=1, artifacts={})
    await agent.execute(ctx)

    events = [c.args for c in agent.emit_event.call_args_list]
    names = [e[0] for e in events if e]
    assert "illustration.skipped" in names, f"skip イベントが発火していない: {names}"
    assert "illustration.error" not in names, "error イベントがまだ発火している"


def test_no_error_string_remains_in_early_return() -> None:
    """`request is required in artifacts` の error 文字列が残っていないこと。"""
    src = inspect.getsource(IllustrationAgent.execute)
    assert 'error="request is required in artifacts"' not in src, (
        "request 不在時の error 返却が残っている"
    )


def test_illustration_is_terminal_in_manifest() -> None:
    """manifest 上で IllustrationSkill が終端ノードであることの固定。"""
    manifest = (ROOT_DIR / "src" / "agents" / "skills" / "manifest.yaml").read_text("utf-8")
    block_start = manifest.index("name: IllustrationSkill")
    block = manifest[block_start : block_start + 400]
    assert "runs_before: []" in block, (
        "IllustrationSkill が終端ノードでない場合、next_agent の設計を見直すこと"
    )
