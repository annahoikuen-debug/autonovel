"""resolve_spine は LLM を一切呼ばないことの証明。"""

import pytest


@pytest.fixture
def no_llm(monkeypatch):
    """すべての LLM 経路を爆発させる。呼ばれたらテストが落ちる。"""
    patched: list[str] = []

    def _boom(*a, **k):
        raise AssertionError("resolve_spine が LLM を呼んだ（設計原則 D2 違反）")

    targets = [
        "src.llm.resilient_gateway.ResilientLLMGateway.generate_text",
        "src.llm.resilient_gateway.ResilientLLMGateway.generate_json",
        "src.llm.resilient_gateway.ResilientLLMGateway._generate",
    ]
    for target in targets:
        try:
            monkeypatch.setattr(target, _boom, raising=True)
            patched.append(target)
        except (ImportError, AttributeError):
            continue
    # 1 つもパッチできていない = no-op を検出する
    assert patched, (
        "パッチ対象が見つからない。no_llm fixture が no-op になっており、"
        "『LLM を呼ばない』の証明になっていない"
    )
    return patched


def test_no_llm_fixture_is_not_vacuous(no_llm):
    """no_llm fixture が実際にターゲットをモックできていることを検証。"""
    assert len(no_llm) >= 3, f"想定より少ないパッチ対象: {no_llm}"


def test_resolve_spine_makes_no_llm_call(no_llm):
    from src.services.spine_resolver import resolve_spine

    for eps in (1, 5, 40, 300):
        assert resolve_spine("exile_rise", "long_serial", "web", eps).beats


def test_full_matrix_makes_no_llm_call(no_llm):
    import itertools

    from config.story_spine import LENGTHS, MARKETS, PATTERNS
    from src.services.spine_resolver import resolve_spine

    for p, l, m in itertools.product(PATTERNS, LENGTHS, MARKETS):
        lo, hi = LENGTHS[l]["eps_range"]
        assert resolve_spine(p, l, m, (lo + hi) // 2).beats


def test_resolve_spine_is_deterministic():
    """同じ入力は常に同じ出力（LLM が関与していることの検出も兼ねる）。"""
    from src.services.spine_resolver import resolve_spine

    a = resolve_spine("exile_rise", "web_volume", "web", 40)
    b = resolve_spine("exile_rise", "web_volume", "web", 40)
    assert a.keys == b.keys
    assert [(x.ep_start, x.ep_end, x.tension, x.duty) for x in a.beats] == [
        (x.ep_start, x.ep_end, x.tension, x.duty) for x in b.beats
    ]


def test_resolver_module_does_not_import_llm():
    """モジュール imports 自体に LLM 経路が含まれないこと（静的検査）。"""
    from pathlib import Path

    src = Path("src/services/spine_resolver.py").read_text(encoding="utf-8")
    for forbidden in ("ResilientLLMGateway", "call_llm", "invoke_llm", "get_default_provider", "async def"):
        assert forbidden not in src, f"spine_resolver に {forbidden!r} が残っている"
