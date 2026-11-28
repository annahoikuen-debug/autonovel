"""Play モード動的継続生成の契約テスト (ADR 002 / PLAN_P1 TRACK-P / P6)。

契約:
- `ENABLE_DYNAMIC_BRANCH=false`（既定）: WS の `dynamic_continue` は error 応答のみ・
  既存 `choose` は無影響・REST は 503（flag ゲート。off 差分ゼロの HTTP 検証は
  `tests/branches/test_dynamic_continue_ws.py` の REST テスト）
- use case は LLM 応答の JSON パースに fail-open し、決定論的プロンプトを持つ
- メトリクスは flag OFF で無音（拒否経路を実際に実行して前後比較する）
"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock

import pytest

from src.application.use_cases.play_dynamic_continue import (
    PlayDynamicContinueUseCase,
    build_dynamic_scene_prompt,
)


def _sample_llm_response() -> str:
    return json.dumps(
        {"scene": "彼は剣を構えた。夜風が剣の冷たさを運ぶ。", "choices": ["前へ進む", "周囲を警戒する", "引き返す"]},
        ensure_ascii=False,
    )


# ============================================================================
# use case 層（モック LLM・決定論的）
# ============================================================================


async def test_use_case_generates_scene_and_choices() -> None:
    use_case = PlayDynamicContinueUseCase(llm=AsyncMock(return_value=_sample_llm_response()))
    scene = await use_case.execute(current_scene_text="彼は扉の前に立っていた。", choice_text="前へ進む")

    assert "剣" in scene.text
    assert len(scene.choices) == 3
    assert scene.choices[0]["text"] == "前へ進む"
    assert scene.choices[0]["kind"] == "dynamic"


async def test_use_case_fail_open_on_invalid_json() -> None:
    """LLM が JSON 以外を返しても本文 + フォールバック選択肢で成立する（fail-open）。"""
    use_case = PlayDynamicContinueUseCase(llm=AsyncMock(return_value="ただの本文です。選択肢はありません。"))
    scene = await use_case.execute(current_scene_text="x", choice_text="y")

    assert scene.text == "ただの本文です。選択肢はありません。"
    assert len(scene.choices) == 1
    assert scene.choices[0]["kind"] == "dynamic"


async def test_use_case_prompt_is_deterministic() -> None:
    """プロンプト構築は決定論的（同一入力 → 同一出力・LLM 0 回）。"""
    kwargs = {"current_scene_text": "あ", "choice_text": "い", "genre": "x", "title": "y", "scene_number": 2}
    assert build_dynamic_scene_prompt(**kwargs) == build_dynamic_scene_prompt(**kwargs)


async def test_use_case_truncates_oversized_scene() -> None:
    """生成本文は 800 字上限で打ち切られる（コスト上限の一部）。"""
    use_case = PlayDynamicContinueUseCase(llm=AsyncMock(return_value="あ" * 5000))
    scene = await use_case.execute(current_scene_text="x", choice_text="y")
    assert len(scene.text) == 800


# ============================================================================
# settings 契約（off 差分ゼロの土台）
# ============================================================================


def test_dynamic_branch_flag_defaults_off() -> None:
    from src.infrastructure.config.settings import settings

    assert settings.ENABLE_DYNAMIC_BRANCH is False
    assert settings.PLAY_DYNAMIC_MAX_PER_SESSION == 30


def test_dynamic_branch_flag_on_via_env() -> None:
    from src.infrastructure.config.settings import Settings

    assert Settings().ENABLE_DYNAMIC_BRANCH is False  # 既定インスタンスは不変
    with pytest.MonkeyPatch.context() as mp:
        mp.setenv("ENABLE_DYNAMIC_BRANCH", "1")
        assert Settings().ENABLE_DYNAMIC_BRANCH is True


# ============================================================================
# API 表面の契約
# ============================================================================


def test_dynamic_continue_rest_registered_but_flag_gated() -> None:
    """動的継続は WS と REST に実装される（Play UI は REST ベース・Phase 0 方針と整合）。

    REST は flag OFF で 503 を返すため、既定挙動に影響しない。
    HTTP レベルの 503/200 検証は
    `tests/branches/test_dynamic_continue_ws.py` の REST テストで担保する。
    """
    from src.backend.routers import branches as br

    paths = {r.path for r in br.router.routes}
    assert "/api/branches/play/{session_id}/dynamic" in paths


def _metric_samples(metric) -> list[tuple[str, float]]:
    """prometheus メトリクスの (sample_name, value) 一覧を安定に取得する。"""
    return [(s.name, s.value) for family in metric.collect() for s in family.samples]


def test_dynamic_metrics_silent_by_default() -> None:
    """flag OFF（既定）では動的生成メトリクスが増えない（無音性契約）。

    before/after の間で flag OFF の**拒否経路を実際に実行**する
    （router 共有ヘルパーが `_DynamicContinueRejected` を送出するまで進む。
    repo/session は触られる前に拒否されるため None でよい）。
    拒否経路がカウンタに触れないことの実質検証であり、
    恒真 assert（before と after の間に何も実行しない比較）は排除した
    （review-loop Phase 1 Round 1 指摘 2）。
    """
    import asyncio

    from src.backend.observability import metrics as m
    from src.backend.routers import branches as br

    assert settings_enabled() is False
    before = _metric_samples(m.play_dynamic_scenes_total)
    with pytest.raises(br._DynamicContinueRejected):
        asyncio.run(br._handle_dynamic_continue(repo=None, session=None, sess=None, choice_text="x"))
    after = _metric_samples(m.play_dynamic_scenes_total)
    assert before == after


def settings_enabled() -> bool:
    from src.infrastructure.config.settings import settings

    return bool(settings.ENABLE_DYNAMIC_BRANCH)
