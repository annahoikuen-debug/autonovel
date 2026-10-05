"""テストおよびローカル実行用のモック LLM アダプタ。"""

from __future__ import annotations

import asyncio
import json
import re
from collections.abc import AsyncIterator
from typing import Any

from src.services.llm.base import BaseLLMAdapter

#: モックが返す固定本文。短いので「字数まで本番同等」にはならないが、
#: パイプラインの配線（企画→執筆→保存→エクスポート）を確認できる。
_MOCK_PROSE = (
    "薄暗い洞窟の奥、古びた石扉の前に立ったアルトは、静かに息を呑んだ。\n"
    "手にした魔導剣が微かに共鳴し、暗闇を青白い光が照らし出す。\n"
    "「ここが、封印の祭壇か……」\n"
    "扉に刻まれた古代文字が突如として紅く輝き、不気味な地鳴りと共に守護獣が姿を現した。"
)

#: モックが返す固定 JSON。
#: 1つのオブジェクトに複数の消費側キーをまとめて詰めている。各消費側の
#: Pydantic モデルは ``extra="allow"`` なので、知らないキーは無視される。
_MOCK_JSON_PAYLOAD: dict[str, Any] = {
    # --- GraphRAG エンティティ抽出 (GraphExtractionResult) ---
    "entities": [
        {
            "name": "アルト",
            "type": "Character",
            "description": "封印の魔導剣を抜いた青年",
            "properties": {"is_alive": True},
        },
        {
            "name": "聖剣エクスカリバー",
            "type": "Item",
            "description": "封印された古代の魔導剣",
            "properties": {},
        },
    ],
    "relationships": [
        {
            "source": "アルト",
            "target": "聖剣エクスカリバー",
            "type": "POSSESSES",
            "detail": "所持",
        }
    ],
    "plot_summary": "アルトが封印の魔導剣を抜いた。",
    # --- 統合企画 (UltraFastWorldBible) ---
    "bible_core": {
        "title": "封印の魔導剣",
        "concept": "封印された古代の魔導剣を抜いた青年が、その世界の危機と向き合う物語。",
        "genre": "ファンタジー",
        "keywords": "ダンジョン, 魔導剣",
        "synopsis": (
            "封印の祭壇から魔導剣を引き抜いたアルトは、剣に眠る意志と自分の過去の一片に"
            "触れ、世界を救うためだけの旅を続ける。"
        ),
        "story_direction": "序盤の理不尽を堆積させ、中盤で反転させる。",
        "engine_key": "conflict",
    },
    "full_story_roadmap": [
        {
            "ep_num": 1,
            "one_line_summary": "アルトが封印の魔導剣を抜く。",
            "resolution_style": "Cheat",
            "antagonist_status": "現状維持",
        },
        {
            "ep_num": 2,
            "one_line_summary": "剣の残片からアルトの過去が判り始める。",
            "resolution_style": "Focus_Drama",
            "antagonist_status": "触手",
        },
        {
            "ep_num": 3,
            "one_line_summary": "最初の試練を越え、一人の仲間を得る。",
            "resolution_style": "Cheat",
            "antagonist_status": "進行",
        },
    ],
    # --- プロット一括生成 (UltraFastPlotBatch) ---
    "plots": [
        {
            "ep_num": 1,
            "title": "封印の祭壇",
            "one_line_summary": "アルトが封印の魔導剣を抜く。",
            "detailed_blueprint": ("洞窟の祭壇。剣を引き抜くと守護獣が現れ、辛うじて第一の門就越える。"),
            "tension": 62,
        },
        {
            "ep_num": 2,
            "title": "剣の声",
            "one_line_summary": "剣の残片からアルトの過去が判り始める。",
            "detailed_blueprint": ("宿屋で剣に憑依される。過去の一片が閃き、真偽が分かれ始める。"),
            "tension": 68,
        },
        {
            "ep_num": 3,
            "title": "最初の仲間",
            "one_line_summary": "試練を越え、一人の仲間を得る。",
            "detailed_blueprint": "街で追われるアルトに、手を差し伸べた少女が現れる。",
            "tension": 75,
        },
    ],
}

# 文字列化は 1 度だけ行う（生成のたびに dict を組み立て直すのを避ける）。
_MOCK_JSON = json.dumps(_MOCK_JSON_PAYLOAD, ensure_ascii=False)

#: プロット一括生成プロンプトに現れる話数指定（例: ``【対象話数】第2話``）。
_EP_NUM_RE = re.compile(r"第\s*(\d+)\s*話")


def _mock_json_for(prompt: str) -> str:
    """プロンプトの指定話数に合わせて ``plots`` を絞った JSON を返す。

    ``WorldBibleGenerator`` は ``initial_plot_limit`` 個のタスクを
    ``asyncio.TaskGroup`` で並列実行し、それぞれ 1 話ずつのバッチを要求する。
    モックが常に同じ話数のプロットを返すと
    ``plots(book_id, branch_id, ep_num)`` の UNIQUE 制約に衝突し、
    ``autonovel generate --provider mock`` が企画途中で落ちる。
    本物の LLM は「指定された話数だけ」を返すので、モックもそれに合わせる。
    """
    if "PlotEpisode" not in prompt:
        return _MOCK_JSON

    requested = {int(m) for m in _EP_NUM_RE.findall(prompt)}
    if not requested:
        return _MOCK_JSON

    plots = [p for p in _MOCK_JSON_PAYLOAD["plots"] if p["ep_num"] in requested]
    if not plots:
        plots = [
            {
                "ep_num": ep,
                "title": f"第{ep}話 モックプロット",
                "one_line_summary": f"第{ep}話のモック用あらすじ。",
                "detailed_blueprint": f"第{ep}話detail のモック設計図。",
                "tension": 60,
            }
            for ep in sorted(requested)
        ]

    payload = {**_MOCK_JSON_PAYLOAD, "plots": plots}
    return json.dumps(payload, ensure_ascii=False)


class MockLLMAdapter(BaseLLMAdapter):
    """モック用 LLM アダプタ。"""

    def __init__(self) -> None:
        self._cancelled = False

    def cancel(self) -> None:
        """ストリーム中断フラグを立てる。"""
        self._cancelled = True

    async def generate_text(
        self,
        prompt: str,
        system_prompt: str | None = None,
        max_tokens: int = 2000,
        temperature: float = 0.7,
        response_format: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> str:
        await asyncio.sleep(0.01)
        if response_format and response_format.get("type") in ("json_object", "json_schema"):
            return _mock_json_for(prompt)
        return _MOCK_PROSE

    async def stream_text(
        self,
        prompt: str,
        system_prompt: str | None = None,
        max_tokens: int = 2000,
        temperature: float = 0.7,
        **kwargs: Any,
    ) -> AsyncIterator[str]:
        chunks = [
            "薄暗い洞窟の奥、",
            "古びた石扉の前に立ったアルトは、",
            "静かに息を呑んだ。\n",
            "手にした魔導剣が微かに共鳴し、",
            "暗闇を青白い光が照らし出す。\n",
            "「ここが、封印の祭壇か……」\n",
            "扉に刻まれた古代文字が突如として紅く輝き、",
            "守護獣が姿を現した。",
        ]
        delay_ms = int(kwargs.get("stream_delay_ms", 10))
        for chunk in chunks:
            if self._cancelled:
                raise asyncio.CancelledError("MockLLMAdapter cancelled")
            await asyncio.sleep(delay_ms / 1000)
            yield chunk
