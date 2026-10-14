"""Novel Formatting & Multi-Platform Linting Provider for MCP Server (Proposal 9)."""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from src.services.formatters.ruby_transpiler import PublishPlatform, RubyTranspiler
from src.services.formatters.platform_formatter import PlatformFormatter


@dataclass
class LintIssue:
    """リント検出項目"""
    issue_type: str
    message: str
    severity: str  # error, warning, info
    line_number: Optional[int] = None
    snippet: Optional[str] = None
    suggested_fix: Optional[str] = None


@dataclass
class FormattedNovelResult:
    """整形・リント結果"""
    formatted_text: str
    original_length: int
    formatted_length: int
    platform: str
    issues: List[LintIssue] = field(default_factory=list)
    is_valid: bool = True
    stats: Dict[str, Any] = field(default_factory=dict)


class NovelFormatterProvider:
    """完全決定論的な小説マルチプラットフォーム整形・リンタープロバイダー"""

    def __init__(self) -> None:
        pass

    def format_novel(
        self,
        text: str,
        platform: str = "kakuyomu",
        options: Optional[Dict[str, Any]] = None,
    ) -> FormattedNovelResult:
        """指定プラットフォーム向けに小説本文を完全決定論的に整形する"""
        opts = options or {}
        auto_remove_dialogue_period = opts.get("remove_dialogue_period", True)

        target_platform = self._normalize_platform(platform)

        # 1. PlatformFormatter によるタイポグラフィ正規化（インデント・連続空行・三点リーダー・ルビ）
        formatted = PlatformFormatter.normalize_typography(text, target_platform)

        # 2. 会話文末尾の余計な句点（「〜。」）の自動除去（Web小説の黄金作法）
        if auto_remove_dialogue_period:
            formatted = re.sub(r"「([^」\n]*?)[。]」", r"「\1」", formatted)

        # 3. リント実行
        lint_res = self.lint_novel(formatted, platform)

        return FormattedNovelResult(
            formatted_text=formatted,
            original_length=len(text),
            formatted_length=len(formatted),
            platform=target_platform.value,
            issues=lint_res.issues,
            is_valid=lint_res.is_valid,
            stats={
                "line_count": len(formatted.split("\n")),
                "dialogue_count": len(re.findall(r"「[^」]*」", formatted)),
                "ruby_count": len(RubyTranspiler.RUBY_PATTERN.findall(formatted)),
            },
        )

    def lint_novel(
        self,
        text: str,
        platform: str = "kakuyomu",
    ) -> FormattedNovelResult:
        """プラットフォーム作法・体裁の決定論的リンター"""
        target_platform = self._normalize_platform(platform)
        issues: List[LintIssue] = []
        lines = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")

        # 1. 括弧対応チェック
        pairs = [("「", "」"), ("『", "』"), ("（", "）"), ("【", "】")]
        for opener, closer in pairs:
            if text.count(opener) != text.count(closer):
                issues.append(
                    LintIssue(
                        issue_type="unbalanced_quotes",
                        message=f"括弧 '{opener}{closer}' の数が一致しません（開: {text.count(opener)}, 閉: {text.count(closer)}）。",
                        severity="error",
                        suggested_fix="閉じ忘れの括弧を補完してください。",
                    )
                )

        # 2. 三点リーダー・ダッシュの奇数チェック
        for match in re.finditer(r"…+|―+|―+", text):
            chunk = match.group(0)
            if len(chunk) % 2 != 0:
                line_no = text[:match.start()].count("\n") + 1
                issues.append(
                    LintIssue(
                        issue_type="odd_ellipses",
                        message=f"三点リーダーまたはダッシュが奇数個（{len(chunk)}個）です。",
                        severity="warning",
                        line_number=line_no,
                        snippet=chunk,
                        suggested_fix="2個セット（偶数個）に統一してください。",
                    )
                )

        # 3. 会話文末尾の句点
        for i, line in enumerate(lines, 1):
            if re.search(r"「[^」\n]*?[。]」", line):
                issues.append(
                    LintIssue(
                        issue_type="dialogue_trailing_period",
                        message="会話文の末尾に句点が付いています。",
                        severity="warning",
                        line_number=i,
                        snippet=line.strip()[:40],
                        suggested_fix="会話文末の『。』を除去してください。",
                    )
                )

        # 4. 地の文の全角インデント漏れ
        for i, line in enumerate(lines, 1):
            s = line.strip()
            if s and not s.startswith(("「", "『", "（", "(", "【", "［", "[", "〈", "《", "“", "\"")):
                if not line.startswith("　"):
                    issues.append(
                        LintIssue(
                            issue_type="missing_indent",
                            message="地の文の行頭に全角空白字下げがありません。",
                            severity="info",
                            line_number=i,
                            snippet=s[:30],
                            suggested_fix="行頭に全角スペースを挿入してください。",
                        )
                    )

        # 5. 空行連続チェック
        consecutive_blanks = 0
        for i, line in enumerate(lines, 1):
            if not line.strip():
                consecutive_blanks += 1
                if consecutive_blanks >= 3:
                    issues.append(
                        LintIssue(
                            issue_type="excessive_blank_lines",
                            message="3行以上の連続空行があります。",
                            severity="warning",
                            line_number=i,
                            suggested_fix="空行は1〜2行に整理してください。",
                        )
                    )
                    consecutive_blanks = 0
            else:
                consecutive_blanks = 0

        is_valid = not any(iss.severity == "error" for iss in issues)

        return FormattedNovelResult(
            formatted_text=text,
            original_length=len(text),
            formatted_length=len(text),
            platform=target_platform.value,
            issues=issues,
            is_valid=is_valid,
            stats={"issue_count": len(issues)},
        )

    def export_episode(
        self,
        title: str,
        content: str,
        platform: str = "kakuyomu",
        foreword: str = "",
        afterword: str = "",
    ) -> Dict[str, Any]:
        """前書き・後書き・タイトル制限を含めたエピソード完全パッケージング"""
        target_platform = self._normalize_platform(platform)

        formatted_content = self.format_novel(content, platform).formatted_text
        formatted_foreword = (
            self.format_novel(foreword, platform).formatted_text if foreword else ""
        )
        formatted_afterword = (
            self.format_novel(afterword, platform).formatted_text if afterword else ""
        )

        # タイトル長チェック
        limit_warnings = PlatformFormatter.validate_limits(title, "", target_platform)

        # パッケージ組み立て
        parts: List[str] = []
        if formatted_foreword:
            parts.append(f"【前書き】\n{formatted_foreword}\n\n{'=' * 20}\n")
        parts.append(formatted_content)
        if formatted_afterword:
            parts.append(f"\n\n{'=' * 20}\n【後書き】\n{formatted_afterword}")

        full_package = "\n".join(parts)

        return {
            "title": title,
            "platform": target_platform.value,
            "formatted_content": formatted_content,
            "formatted_foreword": formatted_foreword,
            "formatted_afterword": formatted_afterword,
            "full_package": full_package,
            "total_character_count": len(full_package),
            "warnings": limit_warnings,
        }

    def _normalize_platform(self, platform: str) -> PublishPlatform:
        p = platform.lower().strip()
        if p in ("narou", "syosetu", "なろう", "小説家になろう"):
            return PublishPlatform.NAROU
        elif p in ("kakuyomu", "カクヨム"):
            return PublishPlatform.KAKUYOMU
        elif p in ("alphapolis", "アルファポリス"):
            return PublishPlatform.ALPHAPOLIS
        elif p in ("aozora", "青空文庫"):
            return PublishPlatform.AOZORA
        elif p in ("kdp", "epub", "kdp_epub"):
            return PublishPlatform.KDP_EPUB
        return PublishPlatform.KAKUYOMU
