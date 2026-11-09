from __future__ import annotations

"""擾乱変換カタログ (M1: 検証平面の中核)。

すべての変換は以下を満たす：
- 決定的 (seed 固定)
- 入力非破壊 (新しい文字列を返す)
- 出力非空
- min_chars 未満の入力は変換せず元の text を返す
"""

import re
import random
from dataclasses import dataclass, field
from typing import Literal

from src.engine.auditors.rule_based_metrics import AI_CLICHE_PATTERNS

PerturbationKind = Literal["DIR", "INV"]

# 日本語の文区切り
_SENTENCE_SPLIT = re.compile(r"([。！？\n])")
# フックマーカー（末尾引きの検出用）
_HOOK_MARKER = re.compile(r"(まさか|突如|その時|現れた|気付いた|信じられない)")
# 会話行検出
_DIALOGUE_LINE = re.compile(r"「[^」]*」")


@dataclass
class PerturbationTransform:
    """単一の擾乱変換。"""

    id: str
    kind: PerturbationKind
    affected_axes: list[str]
    seed: int = 42
    strength: float = 1.0
    min_chars: int = 0

    def apply(self, text: str) -> str:
        """変換を適用して新しい文字列を返す。"""
        raise NotImplementedError

    def _rng(self) -> random.Random:
        return random.Random(self.seed)

    def _guard(self, text: str, result: str) -> str:
        """結果が空になったら元の text を返す（安全策）。"""
        if not result or len(result) < 1:
            return text
        return result


def _split_sentences(text: str) -> list[str]:
    """日本語の文に分割する（句読点を保持）。"""
    if not text:
        return []
    parts = _SENTENCE_SPLIT.split(text)
    sentences: list[str] = []
    buf = ""
    for part in parts:
        buf += part
        if part in ("。", "！", "？", "\n"):
            if buf.strip():
                sentences.append(buf)
            buf = ""
    if buf.strip():
        sentences.append(buf)
    return [s for s in sentences if s.strip()]


def _split_paragraphs(text: str) -> list[str]:
    """空行で段落に分割する。"""
    if not text:
        return []
    return [p for p in re.split(r"\n\s*\n", text) if p.strip()]


class RemoveEndingHook(PerturbationTransform):
    """T01: 末尾フック文削除 (DIR)。

    末尾からフックマーカーを含む文を 1-3 文削除する。
    最低 1 文は残す。
    """

    def __init__(self) -> None:
        super().__init__(
            id="T01",
            kind="DIR",
            affected_axes=["hook"],
            seed=42,
            min_chars=200,
        )

    def apply(self, text: str) -> str:
        if len(text) < self.min_chars:
            return text
        sentences = _split_sentences(text)
        if len(sentences) <= 1:
            return text
        rng = self._rng()
        max_removed = max(1, int(self.strength))
        removed = 0
        result = list(sentences)
        while removed < max_removed and len(result) > 1:
            tail = result[-1]
            is_hook = bool(
                re.search(r"[！？!?]$", tail)
                or tail.endswith("」")
                or _HOOK_MARKER.search(tail)
            )
            if is_hook:
                result.pop()
                removed += 1
            else:
                break
        if removed == 0:
            # フック文が見つからない場合は末尾から1文削除（強制変換）
            result.pop()
            removed = 1
        return self._guard(text, "".join(result))


class ShuffleScenes(PerturbationTransform):
    """T02: シーン順序シャッフル (DIR)。

    空行でシーンを分割し、seed 固定でシャッフルする。
    """

    def __init__(self) -> None:
        super().__init__(
            id="T02",
            kind="DIR",
            affected_axes=["overall"],
            seed=42,
            min_chars=300,
        )

    def apply(self, text: str) -> str:
        if len(text) < self.min_chars:
            return text
        scenes = _split_paragraphs(text)
        if len(scenes) <= 1:
            return text
        rng = self._rng()
        shuffled = scenes[:]
        rng.shuffle(shuffled)
        return self._guard(text, "\n\n".join(shuffled))


class ReplaceCharacterNameOneParagraph(PerturbationTransform):
    """T03: キャラ名不整合入替 (DIR)。

    固有名詞1種を別名へ置換し、最初の1段落のみ適用する。
    """

    def __init__(self) -> None:
        super().__init__(
            id="T03",
            kind="DIR",
            affected_axes=["character_consistency"],
            seed=42,
            min_chars=200,
        )
        self._source_name = "アルト"
        self._target_name = "セオドア"

    def apply(self, text: str) -> str:
        if len(text) < self.min_chars:
            return text
        if self._source_name not in text:
            return text
        paragraphs = _split_paragraphs(text)
        if not paragraphs:
            return text
        max_replace = max(1, int(self.strength))
        replace_count = min(max_replace, len(paragraphs))
        rng = self._rng()
        indices = rng.sample(range(len(paragraphs)), replace_count)
        for idx in indices:
            paragraphs[idx] = paragraphs[idx].replace(self._source_name, self._target_name)
        return self._guard(text, "\n\n".join(paragraphs))


class InjectAICliches(PerturbationTransform):
    """T04: AI定型注入 (DIR)。

    AI_CLICHE_PATTERNS から strength に応じた句数を文末に注入する。
    strength=1.0 → 5句、2.0 → 10句、3.0 → 15句。
    """

    def __init__(self) -> None:
        super().__init__(
            id="T04",
            kind="DIR",
            affected_axes=["cliche_count", "overall"],
            seed=42,
            strength=1.0,
            min_chars=100,
        )

    def apply(self, text: str) -> str:
        if len(text) < self.min_chars:
            return text
        rng = self._rng()
        count = int(5 * self.strength)
        selected = rng.sample(AI_CLICHE_PATTERNS, min(count, len(AI_CLICHE_PATTERNS)))
        injected = "".join(selected) + "。"
        return self._guard(text, text.rstrip() + "\n" + injected)


class SummarizeDialogueToNarrative(PerturbationTransform):
    """T05: 会話→地の文要約 (DIR)。

    「…」を含む行を地の文要約に置換し、会話比率を下げる。
    """

    def __init__(self) -> None:
        super().__init__(
            id="T05",
            kind="DIR",
            affected_axes=["emotional"],
            seed=42,
            min_chars=200,
        )

    def apply(self, text: str) -> str:
        if len(text) < self.min_chars:
            return text
        lines = text.split("\n")
        max_replace = max(1, int(self.strength))
        replaced = 0
        for i, line in enumerate(lines):
            if replaced >= max_replace:
                break
            if _DIALOGUE_LINE.search(line):
                lines[i] = "主人公は何かを告げた。"
                replaced += 1
        if replaced == 0:
            return text
        return self._guard(text, "\n".join(lines))


class RemoveMiddleParagraph(PerturbationTransform):
    """T06: 中盤段落除去 (DIR)。

    中盤（30%〜70% 付近）の段落を1つ除去する。
    先頭3000字は保護し、3000字盲検出判定器の診断シグナルとする。
    """

    def __init__(self) -> None:
        super().__init__(
            id="T06",
            kind="DIR",
            affected_axes=["overall"],
            seed=42,
            min_chars=800,
        )

    def apply(self, text: str) -> str:
        if len(text) < self.min_chars:
            return text
        paragraphs = _split_paragraphs(text)
        if len(paragraphs) <= 2:
            return text
        max_remove = max(1, int(self.strength))
        # 先頭1段落と末尾1段落を保護（先頭3000字付近を守る）
        candidates = list(range(1, len(paragraphs) - 1))
        if not candidates:
            return text
        remove_count = min(max_remove, len(candidates))
        rng = self._rng()
        indices = sorted(rng.sample(candidates, remove_count), reverse=True)
        for idx in indices:
            paragraphs.pop(idx)
        return self._guard(text, "\n\n".join(paragraphs))


class DuplicateParagraph(PerturbationTransform):
    """T07: 段落重複挿入 (DIR)。

    ランダムな段落を重複挿入し、n-gram 反復率を上げる。
    """

    def __init__(self) -> None:
        super().__init__(
            id="T07",
            kind="DIR",
            affected_axes=["overall"],
            seed=42,
            min_chars=300,
        )

    def apply(self, text: str) -> str:
        if len(text) < self.min_chars:
            return text
        paragraphs = _split_paragraphs(text)
        if not paragraphs:
            return text
        max_dup = max(1, int(self.strength))
        rng = self._rng()
        for _ in range(max_dup):
            idx = rng.randrange(len(paragraphs))
            duplicated = paragraphs[idx]
            paragraphs.insert(idx, duplicated)
        return self._guard(text, "\n\n".join(paragraphs))


class RenameCharacterConsistently(PerturbationTransform):
    """T08: 一貫した固有名詞改名 (INV)。

    全出現箇所を一括改名する。意味的には同じなので全軸不変が期待される。
    """

    def __init__(self) -> None:
        super().__init__(
            id="T08",
            kind="INV",
            affected_axes=["hook", "emotional", "character_consistency", "overall"],
            seed=42,
            min_chars=100,
        )
        self._source_name = "アルト"
        self._target_name = "リオン"

    def apply(self, text: str) -> str:
        if len(text) < self.min_chars:
            return text
        if self._source_name not in text:
            return text
        return self._guard(text, text.replace(self._source_name, self._target_name))


class NormalizePunctuation(PerturbationTransform):
    """T09: 句読点・記号正規化 (INV)。

    引用符・ダーシ等を正規化する。意味は保持される。
    """

    def __init__(self) -> None:
        super().__init__(
            id="T09",
            kind="INV",
            affected_axes=["hook", "emotional", "character_consistency", "overall"],
            seed=42,
            min_chars=100,
        )

    def apply(self, text: str) -> str:
        if len(text) < self.min_chars:
            return text
        normalized = text.replace("「", "『").replace("」", "』").replace("〜", "～")
        return self._guard(text, normalized)


# 全変換のレジストリ
TRANSFORM_REGISTRY: dict[str, PerturbationTransform] = {}


def register(transform: PerturbationTransform) -> PerturbationTransform:
    """レジストリに変換を登録する。"""
    TRANSFORM_REGISTRY[transform.id] = transform
    return transform


# モジュール読み込み時に全変換を登録
register(RemoveEndingHook())
register(ShuffleScenes())
register(ReplaceCharacterNameOneParagraph())
register(InjectAICliches())
register(SummarizeDialogueToNarrative())
register(RemoveMiddleParagraph())
register(DuplicateParagraph())
register(RenameCharacterConsistently())
register(NormalizePunctuation())

__all__ = [
    "PerturbationTransform",
    "PerturbationKind",
    "RemoveEndingHook",
    "ShuffleScenes",
    "ReplaceCharacterNameOneParagraph",
    "InjectAICliches",
    "SummarizeDialogueToNarrative",
    "RemoveMiddleParagraph",
    "DuplicateParagraph",
    "RenameCharacterConsistently",
    "NormalizePunctuation",
    "TRANSFORM_REGISTRY",
    "register",
    "_split_sentences",
    "_split_paragraphs",
]
