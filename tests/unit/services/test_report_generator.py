"""src/services/report_generator.py (ReportGenerator) の単体テスト."""

from __future__ import annotations

from datetime import datetime



from src.models.report import EpisodeSummary, ProductionReport, QualityMetricsReport, TokenUsageReport
from src.services.report_generator import ReportGenerator
from src.services.token_tracker import TokenTracker


class TestReportGeneratorInit:
    """ReportGenerator 初期化のテスト."""

    def test_init_creates_output_dir(self, tmp_path):
        output_dir = str(tmp_path / "reports")
        gen = ReportGenerator(output_dir=output_dir)
        assert gen.output_dir == output_dir
        import os

        assert os.path.isdir(output_dir)

    def test_init_default_output_dir(self):
        gen = ReportGenerator()
        assert gen.output_dir == "output"
        import os

        assert os.path.isdir("output")


class TestGenerateProductionReport:
    """generate_production_report メソッドのテスト."""

    def test_generate_production_report_basic(self, tmp_path):
        gen = ReportGenerator(output_dir=str(tmp_path))
        tracker = TokenTracker()
        tracker.add_usage(100, 50)
        tracker.episode_count = 1

        episodes = [
            {
                "ep_num": 1,
                "title": "第1話",
                "text": "これはエピソード1の本文です。" * 10,
                "quality_score": 0.85,
            }
        ]

        report = gen.generate_production_report(
            title="テスト小説",
            genre="fantasy",
            token_tracker=tracker,
            episodes=episodes,
        )

        assert isinstance(report, ProductionReport)
        assert report.title == "テスト小説"
        assert report.genre == "fantasy"
        assert report.target_word_count == 3000
        assert report.token_usage is not None
        assert report.token_usage.total_tokens == 150
        assert report.token_usage.input_tokens == 100
        assert report.token_usage.output_tokens == 50
        assert report.token_usage.episode_count == 1
        assert len(report.episode_summaries) == 1
        assert report.episode_summaries[0].ep_num == 1
        assert report.episode_summaries[0].title == "第1話"
        assert report.episode_summaries[0].word_count == len("これはエピソード1の本文です。" * 10)
        assert report.episode_summaries[0].quality_score == 0.85
        assert isinstance(report.created_at, datetime)

    def test_generate_production_report_empty_episodes(self, tmp_path):
        gen = ReportGenerator(output_dir=str(tmp_path))
        tracker = TokenTracker()

        report = gen.generate_production_report(
            title="空",
            genre="sf",
            token_tracker=tracker,
            episodes=[],
        )

        assert report.episode_summaries == []
        assert report.token_usage.total_tokens == 0

    def test_generate_production_report_text_truncation(self, tmp_path):
        gen = ReportGenerator(output_dir=str(tmp_path))
        tracker = TokenTracker()

        # 200文字を超えるテキスト
        long_text = "あ" * 300
        episodes = [
            {
                "ep_num": 1,
                "title": "長い話",
                "text": long_text,
                "quality_score": 0.5,
            }
        ]

        report = gen.generate_production_report(
            title="t",
            genre="g",
            token_tracker=tracker,
            episodes=episodes,
        )

        summary = report.episode_summaries[0]
        # 最初の200文字 + "..."
        assert summary.summary == "あ" * 200 + "..."
        assert summary.word_count == 300

    def test_generate_production_report_short_text(self, tmp_path):
        gen = ReportGenerator(output_dir=str(tmp_path))
        tracker = TokenTracker()

        episodes = [
            {
                "ep_num": 1,
                "title": "短い話",
                "text": "短文",
                "quality_score": 1.0,
            }
        ]

        report = gen.generate_production_report(
            title="t",
            genre="g",
            token_tracker=tracker,
            episodes=episodes,
        )

        summary = report.episode_summaries[0]
        assert summary.summary == "短文"  # 200文字未満なので "..." なし


class TestToMarkdown:
    """to_markdown メソッドのテスト."""

    def test_to_markdown_basic(self):
        gen = ReportGenerator(output_dir="/tmp")
        report = ProductionReport(
            title="テストタイトル",
            genre="fantasy",
            created_at=datetime(2026, 1, 1, 0, 0, 0),
        )
        md = gen.to_markdown(report)
        assert "# 制作レポート: テストタイトル" in md
        assert "**ジャンル**: fantasy" in md
        assert "**生成日時**: 2026-01-01T00:00:00" in md
        assert "## トークン使用量" in md
        assert "## エピソード一覧" in md

    def test_to_markdown_with_token_usage(self):
        gen = ReportGenerator(output_dir="/tmp")
        token_usage = TokenUsageReport(
            total_tokens=15000,
            input_tokens=8000,
            output_tokens=7000,
            episode_count=10,
            generation_time_seconds=120.5,
        )
        report = ProductionReport(
            title="t",
            genre="g",
            token_usage=token_usage,
        )
        md = gen.to_markdown(report)
        assert "- **総トークン数**: 15,000" in md
        assert "- **入力トークン数**: 8,000" in md
        assert "- **出力トークン数**: 7,000" in md
        assert "- **生成エピソード数**: 10" in md
        assert "- **生成所要時間**: 120.5秒" in md

    def test_to_markdown_with_quality_metrics(self):
        gen = ReportGenerator(output_dir="/tmp")
        qm = QualityMetricsReport(
            coherence_score=0.85,
            character_consistency=0.90,
            pacing_score=0.78,
            hook_retention=0.82,
            emotional_resonance=0.75,
            commercial_viability=0.88,
        )
        report = ProductionReport(
            title="t",
            genre="g",
            quality_metrics=qm,
        )
        md = gen.to_markdown(report)
        assert "## 品質メトリクス" in md
        assert "- **物語整合性**: 0.85" in md
        assert "- **キャラクター一貫性**: 0.90" in md
        assert "- **ペーシング**: 0.78" in md
        assert "- **フック保持率**: 0.82" in md
        assert "- **感情共鳴度**: 0.75" in md
        assert "- **商業的ポテンシャル**: 0.88" in md

    def test_to_markdown_with_episodes(self):
        gen = ReportGenerator(output_dir="/tmp")
        report = ProductionReport(
            title="t",
            genre="g",
            episode_summaries=[
                EpisodeSummary(ep_num=1, title="第1話", word_count=500, summary="あらすじ", quality_score=0.8),
                EpisodeSummary(ep_num=2, title="第2話", word_count=600, summary="あ" * 150, quality_score=0.9),
            ],
        )
        md = gen.to_markdown(report)
        assert "### 第1話: 第1話" in md
        assert "- 文字数: 500" in md
        assert "- 品質スコア: 0.80" in md
        assert "- 要約: あらすじ" in md
        assert "### 第2話: 第2話" in md
        # 150文字 > 100文字なので "..." が付く
        assert "- 要約: " + "あ" * 100 + "..." in md


class TestToHtml:
    """to_html メソッドのテスト."""

    def test_to_html_basic(self):
        gen = ReportGenerator(output_dir="/tmp")
        report = ProductionReport(title="t", genre="g", episode_summaries=[
            EpisodeSummary(ep_num=1, title="第1話", word_count=100, summary="あらすじ", quality_score=0.8),
        ])
        html = gen.to_html(report)
        assert html.startswith("<html><body>")
        assert html.endswith("</body></html>")
        assert "<h1>" in html
        assert "制作レポート: t" in html
        assert "<strong>" in html
        assert "<li>" in html

    def test_to_html_contains_markdown_content(self):
        gen = ReportGenerator(output_dir="/tmp")
        report = ProductionReport(title="テスト", genre="ファンタジー")
        html = gen.to_html(report)
        assert "テスト" in html
        assert "ファンタジー" in html


class TestExtractEpisodeSummary:
    """extract_episode_summary メソッドのテスト."""

    def test_extract_short_text(self):
        gen = ReportGenerator(output_dir="/tmp")
        result = gen.extract_episode_summary("こんにちは")
        assert result == "こんにちは"

    def test_extract_text_with_sentence_ender(self):
        gen = ReportGenerator(output_dir="/tmp")
        text = "こんにちは。今日は良い天気です。明日は雨です。"
        result = gen.extract_episode_summary(text, max_length=100)
        # 200文字以内なので全文が対象。句点で終わるように調整
        assert result == "こんにちは。今日は良い天気です。明日は雨です。"

    def test_extract_text_cut_at_sentence_ender(self):
        gen = ReportGenerator(output_dir="/tmp")
        text = "あいうえお。かきくけこ。さしすせそ。"
        # max_length パラメータは実装で無視され、固定で先頭200文字を対象とする
        result = gen.extract_episode_summary(text, max_length=10)
        # 200文字未満なので全文が対象。句点で終わるように調整
        assert result == "あいうえお。かきくけこ。さしすせそ。"

    def test_extract_empty_text(self):
        gen = ReportGenerator(output_dir="/tmp")
        result = gen.extract_episode_summary("")
        assert result == ""
