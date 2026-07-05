import tempfile
import unittest
from pathlib import Path

from scripts.send_news_email import build_news_body, latest_analysis


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


class SendNewsEmailTests(unittest.TestCase):
    def test_latest_analysis_prefers_evening_within_same_date(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            _write(base / "data/analysis/2026-07-05_morning.json", '{"slot":"morning"}')
            _write(base / "data/analysis/2026-07-05_evening.json", '{"slot":"evening"}')
            _write(base / "data/analysis/2026-07-04_evening.json", '{"slot":"evening"}')

            path, analysis = latest_analysis(base)

            self.assertEqual(path.name, "2026-07-05_evening.json")
            self.assertEqual(analysis["slot"], "evening")

    def test_build_news_body_includes_links_and_top_articles(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            diagram = base / "docs/diagrams/2026-07-05-morning.html"
            _write(diagram, "<html></html>")
            analysis = {
                "trend_summary": "今日の概要",
                "slot": "morning",
                "top_articles": [
                    {
                        "rank": 1,
                        "title": "重要ニュース",
                        "summary": "要約",
                        "url": "https://example.com/news",
                        "source_label": "rss:Example",
                    }
                ],
            }

            body = build_news_body(Path("2026-07-05_morning.json"), analysis, base)

            self.assertIn("AIニュース 2026-07-05 朝便", body)
            self.assertIn("https://k-hira-shine.github.io/ai-news-dashboard/index.html", body)
            self.assertIn("https://k-hira-shine.github.io/ai-news-dashboard/diagrams/2026-07-05-morning.html", body)
            self.assertIn("1. 重要ニュース", body)
            self.assertIn("https://example.com/news", body)


if __name__ == "__main__":
    unittest.main()
