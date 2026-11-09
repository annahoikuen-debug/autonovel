"""M3: 3 系統判定パネルテスト。

- マスキング: プロンプトにモデル名/family が含まれない
- 自己偏好除外: 同一 family の judge は excluded
- score_axis: z正規化 + 中央値、fail-closed
- pairwise: 順序スワップ付きペアワイズ比較
- PanelUnavailable: 全 judge 失敗時
"""

from __future__ import annotations

from typing import Any

import pytest

from src.audit.judge_panel import (
    JudgePanel,
    JudgeSpec,
    PanelScore,
    PairwiseVerdict,
    PanelUnavailable,
)


class _FakeGateway:
    """generate_text を模擬するゲートウェイ。"""

    def __init__(
        self,
        responses: dict[str, str] | None = None,
        fail_map: dict[str, bool] | None = None,
    ):
        self._responses = responses or {}
        self.fail_map = fail_map or {}
        self.calls: list[dict[str, Any]] = []

    async def generate_text(
        self,
        prompt: str,
        primary_provider: str | None = None,
        system_instruction: str | None = None,
        temperature: float = 0.7,
        **kwargs: Any,
    ) -> str:
        self.calls.append(
            {
                "prompt": prompt,
                "primary_provider": primary_provider,
                "temperature": temperature,
            }
        )
        if self.fail_map.get(primary_provider or "default", False):
            raise RuntimeError(f"gateway failure for {primary_provider}")
        key = primary_provider or "default"
        return self._responses.get(key, '{"hook": 70, "critique": "ok"}')


class _FakeCalibrator:
    """ScoreCalibrator を模擬。raw_score をそのまま返す。"""

    def calibrate_single(self, specialist_name, raw_score, confidence=1.0, genre="general"):
        return raw_score, {"specialist_name": specialist_name}


def _make_panel(
    judges: list[JudgeSpec] | None = None,
    *,
    gateway_responses: dict[str, str] | None = None,
    fail_map: dict[str, bool] | None = None,
) -> tuple[JudgePanel, _FakeGateway]:
    if judges is None:
        judges = [
            JudgeSpec(family="gemini", model="gemini-1.5-flash"),
            JudgeSpec(family="anthropic", model="claude-3-haiku"),
            JudgeSpec(family="openai", model="gpt-4o-mini"),
        ]
    gateway = _FakeGateway(responses=gateway_responses, fail_map=fail_map)
    calibrator = _FakeCalibrator()
    panel = JudgePanel(judges=judges, gateway=gateway, calibrator=calibrator)
    return panel, gateway


# ---- マスキングテスト ----


@pytest.mark.asyncio
async def test_masking_no_model_name_in_prompt():
    """プロンプトにモデル名や family が含まれない。"""
    gateway = _FakeGateway(responses={"gemini": '{"hook": 70, "critique": "ok"}'})
    panel = JudgePanel(
        judges=[JudgeSpec(family="gemini", model="gemini-1.5-flash")],
        gateway=gateway,
        calibrator=_FakeCalibrator(),
    )
    await panel.score_axis("テスト本文です。", "hook")
    prompt = gateway.calls[0]["prompt"]
    assert "gemini" not in prompt.lower()
    assert "claude" not in prompt.lower()
    assert "gpt" not in prompt.lower()
    assert "テスト本文です。" in prompt
    assert "hook" in prompt


# ---- 自己偏好除外テスト ----


@pytest.mark.asyncio
async def test_self_preference_exclusion():
    """provenance_family と同一の judge は excluded になる。"""
    gateway = _FakeGateway(
        responses={
            "gemini": '{"hook": 80, "critique": "ok"}',
            "anthropic": '{"hook": 70, "critique": "ok"}',
            "openai": '{"hook": 60, "critique": "ok"}',
        }
    )
    panel = JudgePanel(
        judges=[
            JudgeSpec(family="gemini", model="gemini-1.5-flash"),
            JudgeSpec(family="anthropic", model="claude-3-haiku"),
            JudgeSpec(family="openai", model="gpt-4o-mini"),
        ],
        gateway=gateway,
        calibrator=_FakeCalibrator(),
    )
    # 出力原稿の family が gemini の場合、gemini judge は除外
    score = await panel.score_axis(
        "テスト本文です。", "hook", provenance_family="gemini"
    )
    assert score.n_excluded == 1
    assert score.n_available == 2
    # 除外された judge は scores に含まれない（available=False なので）
    # n_excluded で除外数を確認する
    assert score.n_excluded == 1


@pytest.mark.asyncio
async def test_no_provenance_family_all_participate():
    """provenance_family が不明な場合は全 judge が参加する。"""
    gateway = _FakeGateway(
        responses={
            "gemini": '{"hook": 80, "critique": "ok"}',
            "anthropic": '{"hook": 70, "critique": "ok"}',
            "openai": '{"hook": 60, "critique": "ok"}',
        }
    )
    panel = JudgePanel(
        judges=[
            JudgeSpec(family="gemini", model="gemini-1.5-flash"),
            JudgeSpec(family="anthropic", model="claude-3-haiku"),
            JudgeSpec(family="openai", model="gpt-4o-mini"),
        ],
        gateway=gateway,
        calibrator=_FakeCalibrator(),
    )
    score = await panel.score_axis("テスト本文です。", "hook")
    assert score.n_excluded == 0
    assert score.n_available == 3


# ---- score_axis 中央値テスト ----


@pytest.mark.asyncio
async def test_score_axis_median():
    """z正規化後の中央値が返される（_FakeCalibrator は raw_score をそのまま返す）。"""
    gateway = _FakeGateway(
        responses={
            "gemini": '{"hook": 80, "critique": "ok"}',
            "anthropic": '{"hook": 70, "critique": "ok"}',
            "openai": '{"hook": 60, "critique": "ok"}',
        }
    )
    panel = JudgePanel(
        judges=[
            JudgeSpec(family="gemini", model="gemini-1.5-flash"),
            JudgeSpec(family="anthropic", model="claude-3-haiku"),
            JudgeSpec(family="openai", model="gpt-4o-mini"),
        ],
        gateway=gateway,
        calibrator=_FakeCalibrator(),
    )
    score = await panel.score_axis("テスト本文です。", "hook")
    assert score.median_score == 70.0  # 80, 70, 60 の中央値


@pytest.mark.asyncio
async def test_score_axis_fail_closed_all_fail():
    """全 judge 失敗時は PanelUnavailable。"""
    gateway = _FakeGateway(fail_map={"gemini": True, "anthropic": True, "openai": True})
    panel = JudgePanel(
        judges=[JudgeSpec(family="gemini", model="gemini-1.5-flash")],
        gateway=gateway,
        calibrator=_FakeCalibrator(),
    )
    with pytest.raises(PanelUnavailable):
        await panel.score_axis("テスト本文です。", "hook")


@pytest.mark.asyncio
async def test_score_axis_some_fail():
    """一部 judge 失敗時は残りで中央値を計算。"""
    gateway = _FakeGateway(
        responses={
            "gemini": '{"hook": 80, "critique": "ok"}',
            "anthropic": '{"hook": 70, "critique": "ok"}',
            "openai": '{"hook": 60, "critique": "ok"}',
        },
        fail_map={"openai": True},
    )
    panel = JudgePanel(
        judges=[
            JudgeSpec(family="gemini", model="gemini-1.5-flash"),
            JudgeSpec(family="anthropic", model="claude-3-haiku"),
            JudgeSpec(family="openai", model="gpt-4o-mini"),
        ],
        gateway=gateway,
        calibrator=_FakeCalibrator(),
    )
    score = await panel.score_axis("テスト本文です。", "hook")
    assert score.n_available == 2
    assert score.median_score == 75.0  # 80, 70 の中央値


# ---- pairwise 順序スワップテスト ----


@pytest.mark.asyncio
async def test_pairwise_order_swap_tie():
    """(A,B) と (B,A) で勝者が異なる場合は tie。"""

    async def _swapping_generate(prompt, primary_provider=None, **kwargs):
        # 本文が先に記載されている方を勝ちとする（位置バイアス模擬）
        a_pos = prompt.find("本文Aです。")
        b_pos = prompt.find("本文Bです。")
        if a_pos >= 0 and b_pos >= 0:
            if a_pos < b_pos:
                return '{"winner": "A", "critique": "A is first"}'
            else:
                return '{"winner": "B", "critique": "B is first"}'
        return '{"winner": "tie", "critique": "cannot determine"}'

    gateway = _FakeGateway()
    gateway.generate_text = _swapping_generate  # type: ignore[method-assign]
    panel = JudgePanel(
        judges=[JudgeSpec(family="gemini", model="gemini-1.5-flash")],
        gateway=gateway,
        calibrator=_FakeCalibrator(),
    )
    verdict = await panel.pairwise("本文Aです。", "本文Bです。", axis="overall")
    assert verdict.winner == "tie"
    # 全員 tie に一致しているので agreement_rate=1.0 が正しい
    assert verdict.agreement_rate == 1.0


@pytest.mark.asyncio
async def test_pairwise_consistent_winner():
    """(A,B) と (B,A) で同じ勝者ならその勝者。"""

    async def _consistent_generate(prompt, primary_provider=None, **kwargs):
        # 常に A 勝ち
        return '{"winner": "A", "critique": "A is better"}'

    gateway = _FakeGateway()
    gateway.generate_text = _consistent_generate  # type: ignore[method-assign]
    panel = JudgePanel(
        judges=[JudgeSpec(family="gemini", model="gemini-1.5-flash")],
        gateway=gateway,
        calibrator=_FakeCalibrator(),
    )
    verdict = await panel.pairwise("本文Aです。", "本文Bです。", axis="overall")
    assert verdict.winner == "A"
    assert verdict.agreement_rate == 1.0


@pytest.mark.asyncio
async def test_pairwise_fail_closed_all_fail():
    """ペアワイズで全 judge 失敗時は PanelUnavailable。"""
    gateway = _FakeGateway(fail_map={"gemini": True})
    panel = JudgePanel(
        judges=[JudgeSpec(family="gemini", model="gemini-1.5-flash")],
        gateway=gateway,
        calibrator=_FakeCalibrator(),
    )
    with pytest.raises(PanelUnavailable):
        await panel.pairwise("A", "B", axis="overall")


# ---- 型チェック ----


def test_judge_spec_creation():
    """JudgeSpec が正しく作成できる。"""
    spec = JudgeSpec(family="gemini", model="gemini-1.5-flash", purpose="audit", weight=1.0)
    assert spec.family == "gemini"
    assert spec.model == "gemini-1.5-flash"
    assert spec.purpose == "audit"
    assert spec.weight == 1.0


def test_pairwise_verdict_fields():
    """PairwiseVerdict のフィールドが正しい。"""
    v = PairwiseVerdict(winner="A", axis="overall")
    assert v.winner == "A"
    assert v.axis == "overall"
    assert v.judge_verdicts == []
    assert v.agreement_rate == 0.0
