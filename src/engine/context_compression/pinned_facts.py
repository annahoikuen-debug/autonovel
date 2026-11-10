"""重要事実の先頭・末尾両端抽出 (PLAN_M1 Step 15).

LLM を一切使わず、既存の契約伏線・期限超過伏線・前話ダイジェストから
「最重要の確定事実・必守事項」(head) と「執筆直前の再確認」(tail) を
抽出する。

生成方針:
- head: 期限超過伏線 > 本話契約伏線 > 状態変化キーワード の順で箇条書き
- tail: チェックリスト文体で上記を再掲
- 各ブロックは `pinned_max_chars` / `pinned_tail_max_chars` でクランプ
- 超過時は期限超過 → 契約 → 状態変化 の優先順で削る

これにより Lost in the Middle (Liu et al. 2023) 対策として、中盤の事実が
プロンプトの先頭・末尾に保たれる。
"""

from __future__ import annotations

from dataclasses import dataclass

from src.engine.context_compression.rollup_config import RollupConfig


@dataclass(frozen=True)
class PinnedFacts:
    """プロンプト先頭・末尾に配置する重要事実。"""

    head: str
    tail: str


class PinnedFactsGenerator:
    """重要事実を先頭・末尾の両端に抽出するジェネレーター。"""

    # 状態変化を示唆するキーワード（日本語）。いずれかが含まれる文を抽出する。
    STATE_CHANGE_KEYWORDS = (
        "死亡",
        "死んだ",
        "殺された",
        "入手",
        "獲得",
        "手に入れた",
        "拠点",
        "移動",
        "到着",
        "出発",
        "仲間になった",
        "別れた",
        "解放",
        "捕らえ",
        "倒した",
    )

    def __init__(self, cfg: RollupConfig):
        self.cfg = cfg

    def generate(
        self,
        *,
        contract_foreshadowings: list[dict] | None = None,
        overdue_foreshadowings: list[dict] | None = None,
        prev_digest_text: str | None = None,
    ) -> PinnedFacts:
        """重要事実を head / tail で返す。

        Args:
            contract_foreshadowings: 本話で回収必須の伏線リスト
                (各要素に "title" を持つ dict を想定)
            overdue_foreshadowings: 期限超過の未回収伏線リスト
                (各要素に "title" を持つ dict を想定)
            prev_digest_text: 前話の確定事実ダイジェスト（状態変化抽出元）

        Returns:
            PinnedFacts(head, tail)。どちらかが空でも PinnedFacts を返す。
        """
        contract_foreshadowings = contract_foreshadowings or []
        overdue_foreshadowings = overdue_foreshadowings or []

        # ── 優先順に事実を収集 ──
        facts: list[str] = []

        # 1) 期限超過伏線（最優先）
        for fs in overdue_foreshadowings:
            title = fs.get("title") if isinstance(fs, dict) else str(fs)
            if title:
                facts.append(f"【期限超過】{title} の回収が未完了")

        # 2) 本話契約伏線
        for fs in contract_foreshadowings:
            title = fs.get("title") if isinstance(fs, dict) else str(fs)
            if title:
                facts.append(f"【本話回収必須】{title}")

        # 3) 前話 digest から状態変化キーワードを含む行を抽出
        if prev_digest_text:
            for line in prev_digest_text.splitlines():
                line = line.strip()
                if not line:
                    continue
                if any(kw in line for kw in self.STATE_CHANGE_KEYWORDS):
                    facts.append(f"【状態変化】{line}")

        # ── head / tail を構築 ──
        head = self._build_head(facts)
        tail = self._build_tail(facts)

        return PinnedFacts(head=head, tail=tail)

    def _build_head(self, facts: list[str]) -> str:
        """head ブロック（箇条書き）を構築し pinned_max_chars でクランプする。"""
        if not facts:
            return ""
        lines = [f"- {f}" for f in facts]
        text = "\n".join(lines)
        return self._clamp(text, self.cfg.pinned_max_chars, suffix="…")

    def _build_tail(self, facts: list[str]) -> str:
        """tail ブロック（チェックリスト）を構築し pinned_tail_max_chars でクランプする。"""
        if not facts:
            return ""
        lines = [f"☐ {f}" for f in facts]
        text = "\n".join(lines)
        return self._clamp(text, self.cfg.pinned_tail_max_chars, suffix="…")

    @staticmethod
    def _clamp(text: str, max_chars: int, suffix: str = "…") -> str:
        """max_chars を超える場合は末尾を suffix で切詰める。"""
        if len(text) <= max_chars:
            return text
        cut = max_chars - len(suffix)
        if cut < 0:
            return suffix[:max_chars]
        return text[:cut].rstrip() + suffix
