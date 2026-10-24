"""Surgical Patch & Local Diff Provider for MCP Server (Proposal 3)."""

from __future__ import annotations

import difflib
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from src.services.safe_replace import SafeReplacer


@dataclass
class PatchApplicationResult:
    """局所パッチ適用結果"""

    patched_text: str
    original_text: str
    total_requested: int
    applied_count: int
    failed_count: int
    applied_diffs: List[Dict[str, Any]] = field(default_factory=list)
    failed_diffs: List[Dict[str, Any]] = field(default_factory=list)
    is_fully_applied: bool = True
    token_savings_estimate: int = 0  # 全文再生成と比較した推定節約出力トークン数


@dataclass
class PatchWindow:
    """局所パッチ修正用コンテキストウィンドウ"""

    window_id: str
    target_quote: str
    padded_context: str
    start_char_idx: int
    end_char_idx: int
    location_desc: str = ""


class SurgicalPatchProvider:
    """小説本文に対する外科的（Surgical）パッチ適用および局所コンテキスト抽出プロバイダー"""

    def __init__(self) -> None:
        pass

    def apply_actionable_diffs(
        self,
        original_text: str,
        diffs: List[Any],
        allow_fuzzy: bool = True,
    ) -> PatchApplicationResult:
        """オーディターから提案された ActionableDiff 群を本文に安全にピンポイント適用する。

        全文再生成を行わずに、指定箇所のみをミリ秒・0トークンで外科的に置換する。
        """
        if not diffs:
            return PatchApplicationResult(
                patched_text=original_text,
                original_text=original_text,
                total_requested=0,
                applied_count=0,
                failed_count=0,
                is_fully_applied=True,
                token_savings_estimate=0,
            )

        mappings: Dict[str, str] = {}
        applied: List[Dict[str, Any]] = []
        failed: List[Dict[str, Any]] = []

        for diff in diffs:
            orig = ""
            sug = ""
            loc = ""
            rat = ""

            if isinstance(diff, dict):
                orig = diff.get("original_quote", "").strip()
                sug = diff.get("improved_suggestion", "").strip()
                loc = diff.get("location", "")
                rat = diff.get("rationale", "")
            else:
                orig = getattr(diff, "original_quote", "").strip()
                sug = getattr(diff, "improved_suggestion", "").strip()
                loc = getattr(diff, "location", "")
                rat = getattr(diff, "rationale", "")

            if not orig or not sug:
                failed.append(
                    {
                        "location": loc,
                        "original_quote": orig,
                        "improved_suggestion": sug,
                        "reason": "original_quote または improved_suggestion が空です",
                    }
                )
                continue

            # 1. 完全一致の探索
            if orig in original_text:
                mappings[orig] = sug
                applied.append(
                    {
                        "location": loc,
                        "original_quote": orig,
                        "improved_suggestion": sug,
                        "rationale": rat,
                        "match_type": "exact",
                    }
                )
            elif allow_fuzzy:
                # 2. ファジーマッチ（空白・改行・記号の差異を許容）
                matched_target = self._find_fuzzy_match(original_text, orig)
                if matched_target:
                    mappings[matched_target] = sug
                    applied.append(
                        {
                            "location": loc,
                            "original_quote": matched_target,
                            "improved_suggestion": sug,
                            "rationale": rat,
                            "match_type": "fuzzy",
                        }
                    )
                else:
                    failed.append(
                        {
                            "location": loc,
                            "original_quote": orig,
                            "improved_suggestion": sug,
                            "reason": "本文中に一致する引用箇所が見つかりませんでした",
                        }
                    )
            else:
                failed.append(
                    {
                        "location": loc,
                        "original_quote": orig,
                        "improved_suggestion": sug,
                        "reason": "本文中に一致する引用箇所が見つかりませんでした",
                    }
                )

        # 衝突なしの1パス安全置換を実行
        if mappings:
            replacer = SafeReplacer(mappings)
            patched_text = replacer.replace(original_text)
        else:
            patched_text = original_text

        # 全文再生成をスキップしたことによる推定節約トークン（日本語: 約2文字で1トークン）
        full_regen_tokens = max(1, len(original_text) // 2)
        diff_tokens = sum(len(d.get("improved_suggestion", "")) // 2 for d in applied)
        saved_tokens = max(0, full_regen_tokens - diff_tokens) if applied else 0

        return PatchApplicationResult(
            patched_text=patched_text,
            original_text=original_text,
            total_requested=len(diffs),
            applied_count=len(applied),
            failed_count=len(failed),
            applied_diffs=applied,
            failed_diffs=failed,
            is_fully_applied=len(failed) == 0,
            token_savings_estimate=saved_tokens,
        )

    def extract_patch_windows(
        self,
        original_text: str,
        target_quotes: List[str],
        padding_lines: int = 2,
    ) -> List[PatchWindow]:
        """指定の修正対象箇所について、前後N行を含む最小限のパッチウィンドウを切り出す。

        LLMに章全体ではなく、この局所ウィンドウのみを渡して推敲させることで入力・出力トークンを最小化する。
        """
        lines = original_text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
        windows: List[PatchWindow] = []

        for idx, quote in enumerate(target_quotes):
            q_clean = quote.strip()
            if not q_clean:
                continue

            # 該当行を特定
            hit_line_idx = -1
            for l_idx, line in enumerate(lines):
                if q_clean in line or line.strip() in q_clean:
                    hit_line_idx = l_idx
                    break

            if hit_line_idx == -1:
                continue

            start_idx = max(0, hit_line_idx - padding_lines)
            end_idx = min(len(lines), hit_line_idx + padding_lines + 1)
            padded_lines = lines[start_idx:end_idx]
            padded_text = "\n".join(padded_lines)

            # 文字オフセット計算
            start_char = len("\n".join(lines[:start_idx])) + (1 if start_idx > 0 else 0)
            end_char = start_char + len(padded_text)

            windows.append(
                PatchWindow(
                    window_id=f"win_{idx}_{start_idx}_{end_idx}",
                    target_quote=q_clean,
                    padded_context=padded_text,
                    start_char_idx=start_char,
                    end_char_idx=end_char,
                    location_desc=f"{hit_line_idx + 1}行目付近",
                )
            )

        return windows

    def _find_fuzzy_match(self, text: str, query: str, threshold: float = 0.90) -> Optional[str]:
        """改行や空白の揺らぎを吸収して本文中から最も一致する部分文字列を探す"""
        norm_query = re.sub(r"\s+", "", query)
        if not norm_query:
            return None

        # 文単位で分割して類似判定
        sentences = re.split(r"(?<=[。！？\n])", text)
        best_candidate = None
        best_ratio = 0.0

        for s in sentences:
            s_clean = s.strip()
            if not s_clean:
                continue
            norm_s = re.sub(r"\s+", "", s_clean)
            ratio = difflib.SequenceMatcher(None, norm_query, norm_s).ratio()
            if ratio > best_ratio and ratio >= threshold:
                best_ratio = ratio
                best_candidate = s_clean

        return best_candidate
