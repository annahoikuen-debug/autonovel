"""PLAN_S1 P1 の回帰テスト — 伏線 LLM 投票の fail-open とマスキング契約。

壊れ方: 投票の例外が check_and_resolve を止める / プロンプトに出力元の痕跡が
混入 / temp が変わる / コスト上限 (3000字) を超える → この回帰が赤になる。
"""

from __future__ import annotations


from src.engine.foreshadowing.llm_voter import (
    ForeshadowingLLMVoter,
    LLMVoteResult,
    build_windowed_excerpt,
)

# プロンプトに含めてはならない出力元痕跡 (マスキング原則 / judge_panel と同一方針)
PROVENANCE_TOKENS = ("gpt", "gemini", "claude", "openai", "anthropic", "google", "model_name", "provider")


class _RecordingLLM:
    """generate 呼び出しを記録し、固定応答を返すスタブ。"""

    def __init__(self, response: str = '{"action": "resolved", "evidence_quote": "魔剣が抜かれた"}'):
        self.response = response
        self.calls: list[dict] = []

    def generate(self, prompt: str, temperature: float = 0.7, **kwargs):
        self.calls.append({"prompt": prompt, "temperature": temperature, **kwargs})
        return self.response


class _ExplodingLLM:
    def generate(self, prompt: str, temperature: float = 0.7, **kwargs):
        raise RuntimeError("gateway down")


def _vote(llm, **kwargs):
    import asyncio

    voter = ForeshadowingLLMVoter(llm)
    return asyncio.run(
        voter.vote(
            foreshadowing_id=1,
            foreshadowing_title="封印の魔剣",
            foreshadowing_description="古代王が封じた剣",
            keywords=["魔剣", "封印"],
            draft_text=kwargs.pop("draft_text", "ついに魔剣が抜かれた。封印は解け、光があふれる。"),
            episode_num=3,
            **kwargs,
        )
    )


class TestFailOpen:
    def test_voter_exception_returns_none_vote(self):
        """gateway 例外は None 投票に倒れること (P3)。"""
        result = _vote(_ExplodingLLM())
        assert result is None

    def test_malformed_json_returns_none(self):
        """不正 JSON は None 投票になること。"""
        result = _vote(_RecordingLLM(response="すみません、わかりません"))
        assert result is None

    def test_wrong_action_returns_none(self):
        """規定外の action は None 投票になること。"""
        result = _vote(_RecordingLLM(response='{"action": "deleted", "evidence_quote": ""}'))
        assert result is None

    def test_empty_text_returns_none(self):
        """本文が空なら LLM を呼ばず None を返すこと。"""
        llm = _RecordingLLM()
        result = _vote(llm, draft_text="   ")
        assert result is None
        assert llm.calls == []

    def test_none_llm_returns_none(self):
        """llm=None でも例外にしないこと。"""
        result = _vote(None)
        assert result is None


class TestMasking:
    def test_prompt_is_masked(self):
        """プロンプトに model 名・provider 痕跡が含まれないこと。"""
        llm = _RecordingLLM()
        _vote(llm)
        prompt = llm.calls[0]["prompt"].lower()
        for token in PROVENANCE_TOKENS:
            assert token not in prompt, f"プロンプトに痕跡 '{token}' が含まれる (マスキング違反)"

    def test_prompt_contains_judgment_axes(self):
        """判定基準 3 値と JSON キーが指示されていること。"""
        llm = _RecordingLLM()
        _vote(llm)
        prompt = llm.calls[0]["prompt"]
        assert "resolved" in prompt and "progressed" in prompt and "unmentioned" in prompt
        assert "evidence_quote" in prompt


class TestCostControls:
    def test_temperature_is_low(self):
        """LLM 呼び出しに temp=0.2 が渡ること (SSOT 既定)。"""
        llm = _RecordingLLM()
        _vote(llm)
        assert llm.calls[0]["temperature"] == 0.2

    def test_windowed_excerpt_and_token_budget(self):
        """長文はキーワード前後 ±500 字・全体 ≤3000 字に圧縮されること。"""
        long_text = ("背景描写。" * 2000) + "ここで魔剣が抜かれた。" + ("余韻。" * 2000)
        excerpt = build_windowed_excerpt(long_text, ["魔剣"])
        assert len(excerpt) <= 3000
        assert "魔剣" in excerpt

    def test_short_text_passed_through(self):
        """3000 字以下の本文はそのまま渡されること。"""
        text = "短い本文。"
        assert build_windowed_excerpt(text, ["魔剣"]) == text

    def test_no_keyword_hits_uses_head(self):
        """キーワード未出現なら先頭 3000 字を使うこと。"""
        long_text = "無関係な文章。" * 1000
        excerpt = build_windowed_excerpt(long_text, ["存在しないキーワード"])
        assert len(excerpt) <= 3000
        assert excerpt == long_text[:3000]


class TestVoteResult:
    def test_success_result_shape(self):
        """正常応答が LLMVoteResult に変換されること。"""
        result = _vote(_RecordingLLM(response='{"action": "progressed", "evidence_quote": "剣に触れたが抜いていない"}'))
        assert isinstance(result, LLMVoteResult)
        assert result.foreshadowing_id == 1
        assert result.action == "progressed"
        assert "剣に触れた" in result.evidence_quote

    def test_code_fenced_json_is_parsed(self):
        """コードブロック付き JSON もパースされること。"""
        llm = _RecordingLLM(response='```json\n{"action": "resolved", "evidence_quote": "x"}\n```')
        result = _vote(llm)
        assert result is not None and result.action == "resolved"

    def test_raw_response_capped(self):
        """raw_response は 500 字に丸められること (ログ肥大防止)。"""
        llm = _RecordingLLM(response='{"action": "resolved", "evidence_quote": "x"}' + "あ" * 1000)
        result = _vote(llm)
        assert result is not None
        assert len(result.raw_response) <= 500
