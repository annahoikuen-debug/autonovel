"""Play モードの動的継続生成ユースケース (ADR 002 / PLAN_P1 TRACK-P)。

選択された分岐の続きを LLM で生成し、次の選択肢を提示する。

- **同期応答**（Huey を経由しない）: 対話型プレイは即時応答が前提
  （`docs/plans/ROADMAP_PLAYABLE_NOVEL.md` §5 の「同期 vs バッチ」方針）
- **軽量版**: 監査・RAG を含む本執筆パイプラインは使わず、単発 LLM 呼び出しで
  1 シーン（300〜600 字）を生成する。コスト・レイテンシを優先
- **4 層境界**: 本モジュールは domain / core のみに依存し、`src.backend` を
  import しない。LLM は `async def llm(prompt: str) -> str` として interfaces 層から注入する
- **flag 契約**: `ENABLE_DYNAMIC_BRANCH=0`（既定）では WS 経路自体が
  未定義アクション扱いになるため、本ユースケースは実行されない（off 差分ゼロ）
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)

_SCENE_MAX_CHARS = 800
_CHOICE_COUNT = 3


@dataclass
class DynamicScene:
    """動的に生成された次シーン。"""

    text: str
    choices: list[dict[str, str]] = field(default_factory=list)


def build_dynamic_scene_prompt(
    *,
    current_scene_text: str,
    choice_text: str,
    genre: str = "",
    title: str = "",
    scene_number: int = 1,
) -> str:
    """動的シーン生成プロンプトを構築する（決定論的・LLM 呼び出しを含まない）。"""
    return f"""あなたは web 小説の続きを書く小説家です。以下の現在のシーンと読者の選択に続きを 1 シーン書いてください。

作品: {title or "無題"}
ジャンル: {genre or "ファンタジー"}
現在のシーン番号: 第{scene_number}シーン

【現在のシーン】
{current_scene_text[:2000]}

【読者の選択】
{choice_text}

【指示】
1. 選択の直後の場面を、日本語で 300〜600 字で書く
2. 引き続き続けられるよう、場面の終わりに次の展開の余地を残す
3. 最後に、次の展開の選択肢を 3 つ提示する

【出力形式】(この JSON 形式のみを出力すること)
{{
  "scene": "シーン本文...",
  "choices": ["選択肢1", "選択肢2", "選択肢3"]
}}"""


def parse_dynamic_scene_response(raw: str) -> DynamicScene:
    """LLM 応答をパースする。JSON 失敗時は本文のみ + 単一選択肢フォールバック（fail-open）。"""
    scene_text = (raw or "").strip()
    choices: list[dict[str, str]] = []
    m = re.search(r"\{.*\}", scene_text, re.DOTALL)
    if m:
        try:
            data = json.loads(m.group(0))
            body = str(data.get("scene") or "").strip()
            if body:
                scene_text = body
            raw_choices = data.get("choices") or []
            if isinstance(raw_choices, list):
                choices = [
                    {"id": f"dyn_{i + 1}", "text": str(c).strip(), "kind": "dynamic"}
                    for i, c in enumerate(raw_choices)
                    if str(c).strip()
                ][:_CHOICE_COUNT]
        except (json.JSONDecodeError, TypeError, ValueError):
            logger.debug("dynamic scene response is not JSON; using raw text")
    if not scene_text:
        scene_text = "（続きの生成に失敗しました。もう一度お試しください。）"
    if not choices:
        choices = [{"id": "dyn_1", "text": "この場面で様子を探る", "kind": "dynamic"}]
    return DynamicScene(text=scene_text[:_SCENE_MAX_CHARS], choices=choices)


class PlayDynamicContinueUseCase:
    """選択の続きを LLM で生成するユースケース（同期応答）。

    llm は `async def llm(prompt: str) -> str` の形で注入する。
    """

    def __init__(self, llm: Any) -> None:
        self._llm = llm

    async def execute(
        self,
        *,
        current_scene_text: str,
        choice_text: str,
        genre: str = "",
        title: str = "",
        scene_number: int = 1,
    ) -> DynamicScene:
        prompt = build_dynamic_scene_prompt(
            current_scene_text=current_scene_text,
            choice_text=choice_text,
            genre=genre,
            title=title,
            scene_number=scene_number,
        )
        raw = await self._llm(prompt)
        return parse_dynamic_scene_response(raw or "")
