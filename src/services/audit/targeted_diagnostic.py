"""
Targeted diagnostic for mapping audit findings to specific paragraphs.

W4 Step 4: 以前は TODO スタブで常に空リストを返していたため、
閉ループPDCA の段落パッチ経路が到達不能だった（常に全文再生成へ落ちる）。
ここでは LLM を一切使わず、指摘文字列との部分一致だけで対象段落を決める。
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List

from src.models.patch_pdca import ParagraphTarget
from src.services.prose.paragraph_indexer import ParagraphIndexer

logger = logging.getLogger(__name__)

# 指摘文とみなすキー名（再帰的に拾う）
_HINT_KEYS = ("feedback", "critique", "detail", "directive", "suggestion", "comment")
# 一致する段落が無くても返す1件の指示（末尾で切れるLLMへの俨 spiel 的な指示）
_FALLBACK_DIRECTIVE = "weak_paragraph_revision"


def _collect_hints(node: Any, out: List[str]) -> None:
    """dict / list を再帰的に辿り、指摘系の文字列だけを誤差なく集める。"""
    if isinstance(node, dict):
        for key, value in node.items():
            if key in _HINT_KEYS and isinstance(value, str) and value.strip():
                out.append(value.strip())
            else:
                _collect_hints(value, out)
    elif isinstance(node, (list, tuple)):
        for item in node:
            _collect_hints(item, out)


class TargetedDiagnostic:
    """
    Maps audit findings to specific paragraphs using semantic search or keyword matching.
    """

    def __init__(self, max_targets: int = 3):
        # LLM・ネットワークを使わない決定論的な索引のみ
        self.max_targets = max_targets
        self.indexer = ParagraphIndexer()

    def identify_weak_paragraphs(
        self, audit_result: Dict[str, any], text: str = ""
    ) -> List[ParagraphTarget]:
        """
        Identify which paragraphs need revision based on audit results.
        Args:
            audit_result: The result from the audit aggregator (containing scores and feedback).
            text: 対象本文。空文字なら従来どおり空リストを返す（後方互換）。
        Returns:
            A list of ParagraphTarget objects indicating paragraphs to revise and why.
        """
        if not text or not text.strip():
            return []
        try:
            hints: List[str] = []
            _collect_hints(audit_result, hints)
            paragraphs = self.indexer.index_paragraphs(text)
            if not paragraphs:
                return []
            targets: List[ParagraphTarget] = []
            for para in paragraphs:
                matched = next((h for h in hints if h in para["text"]), None)
                if matched:
                    targets.append(ParagraphTarget(
                        index=para["index"],
                        original_text=para["text"],
                        issue_category="weak_paragraph",
                        directive=matched,
                    ))
            if not targets:
                # LLMが末尾で切るため、末尾1件を対象にする
                last = paragraphs[-1]
                targets.append(ParagraphTarget(
                    index=last["index"],
                    original_text=last["text"],
                    issue_category="weak_paragraph",
                    directive=_FALLBACK_DIRECTIVE,
                ))
            return targets[: max(0, self.max_targets)]
        except Exception:
            # pdca_cycle を落とさないため、空リストへ倒す
            logger.warning("弱段落の特定に失敗しました", exc_info=True)
            return []
