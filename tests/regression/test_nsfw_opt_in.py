"""ENABLE_NSFW オプトイン契約の回帰テスト。

デフォルト (ENABLE_NSFW=false) では官能生成経路が全て拒否されることを固定する。
明示的に ENABLE_NSFW=true にしない限り、官能シーン生成は動作しない。

NSFW 分離・ガードレール (TRACK-N N3) の一環として、
官能生成経路の入口 (EroticSpecialist.build_scene_prompt) で
ENABLE_NSFW フラグをチェックする動作をカバーする。
"""

from __future__ import annotations

import pytest


def test_is_nsfw_enabled_default_false() -> None:
    """ENABLE_NSFW は既定で False、is_nsfw_enabled() も False を返す。"""
    from src.backend.config import settings

    assert settings.ENABLE_NSFW is False
    assert settings.is_nsfw_enabled() is False


def test_erotic_generation_rejected_when_nsfw_disabled(monkeypatch) -> None:
    """ENABLE_NSFW=false では官能生成経路が拒否される (デフォルト拒否)。"""
    from src.backend.config import settings
    from src.engine.prompts.erotic_specialist import EroticSpecialist
    from config.erotic_pacing import EroticCurve

    monkeypatch.setattr(settings, "ENABLE_NSFW", False)
    assert settings.is_nsfw_enabled() is False

    specialist = EroticSpecialist()
    curve = EroticCurve.create_default(intensity=2)
    context: dict = {}

    with pytest.raises(RuntimeError):
        specialist.build_scene_prompt(curve, context)


def test_erotic_generation_allowed_when_nsfw_enabled(monkeypatch) -> None:
    """ENABLE_NSFW=true では官能生成経路が通る (オプトイン)。"""
    from src.backend.config import settings
    from src.engine.prompts.erotic_specialist import EroticSpecialist
    from config.erotic_pacing import EroticCurve

    monkeypatch.setattr(settings, "ENABLE_NSFW", True)
    assert settings.is_nsfw_enabled() is True

    specialist = EroticSpecialist()
    curve = EroticCurve.create_default(intensity=2)
    context: dict = {}

    prompt = specialist.build_scene_prompt(curve, context)
    assert isinstance(prompt, str)
    assert len(prompt) > 0


# ---------------------------------------------------------------------------
# EroticEnhancer.enhance_erotic_content の入口ガード (バイパス経路の遮断)
# ---------------------------------------------------------------------------

class _StubAgent:
    """Enhancer の検証に十分な最小スタブ。"""

    logger = None

    def run(self, *args, **kwargs):  # pragma: no cover - 呼ばれない
        return None


def test_erotic_enhancer_noop_when_nsfw_disabled(monkeypatch) -> None:
    """ENABLE_NSFW=false では官能強化が実行されず入力をそのまま返す。"""
    from src.agents.erotic_enhancer import EroticEnhancer
    from src.backend.config import settings

    monkeypatch.setattr(settings, "ENABLE_NSFW", False)

    enhancer = EroticEnhancer(_StubAgent())  # type: ignore[arg-type]
    context = {"erotic_intensity": 4, "enable_erotic": True}

    result = enhancer.enhance_erotic_content("prompt", "original", context)
    assert result == "original"


def test_erotic_enhancer_runs_when_nsfw_enabled(monkeypatch) -> None:
    """ENABLE_NSFW=true かつゲート有効なら官能強化パイプラインに進む。"""
    from src.agents.erotic_enhancer import EroticEnhancer
    from src.backend.config import settings

    monkeypatch.setattr(settings, "ENABLE_NSFW", True)

    enhancer = EroticEnhancer(_StubAgent())  # type: ignore[arg-type]
    # ゲート有効・高強度のコンテキスト（GraphRAG パラメータ解決まで進む経路）
    context = {"erotic_intensity": 4, "enable_erotic": True, "relationship_type": "LOVES"}

    result = enhancer.enhance_erotic_content("prompt", "original", context)
    assert isinstance(result, str)
