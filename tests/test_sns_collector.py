import unittest

from sns_collector import (
    _article_blocks_to_text,
    _enrich_x_article,
    _find_x_article_url,
)


class XArticleEnrichmentTests(unittest.TestCase):
    def test_finds_x_article_url_from_entities(self) -> None:
        tweet = {
            "entities": {
                "urls": [
                    {"expanded_url": "https://example.com"},
                    {"expanded_url": "https://x.com/i/article/2043276218892767232"},
                ]
            }
        }

        self.assertEqual(
            _find_x_article_url(tweet),
            "https://x.com/i/article/2043276218892767232",
        )

    def test_converts_article_blocks_to_text(self) -> None:
        blocks = [
            {"type": "header-two", "text": "Mindset"},
            {"type": "paragraph", "text": "Start before you are ready."},
            {"type": "unordered-list-item", "text": "Ship daily"},
            {"type": "ordered-list-item", "text": "Review what worked"},
            {"type": "media", "url": "https://example.com/image.png"},
        ]

        self.assertEqual(
            _article_blocks_to_text(blocks),
            "Mindset\n\nStart before you are ready.\n- Ship daily\n1. Review what worked",
        )

    def test_enriches_item_from_cached_article(self) -> None:
        item = {
            "url": "https://x.com/teihen_ns_fire/status/2044009897562718238",
            "title": "https://t.co/WP6aX5RUEv",
            "content": "https://t.co/WP6aX5RUEv",
        }
        tweet = {
            "id": "2044009897562718238",
            "entities": {
                "urls": [
                    {"expandedUrl": "https://x.com/i/article/2043276218892767232"},
                ]
            },
        }
        cache = {
            "2044009897562718238": {
                "article": {
                    "title": "30日で人生を変える習慣",
                    "previewText": "Youtube登録者840万人の女性が提唱する...",
                    "contents": [
                        {"type": "paragraph", "text": "朝起きたらまず今日の一番大事なことを決める。"},
                        {"type": "paragraph", "text": "小さく継続できる習慣だけを選ぶ。"},
                    ],
                }
            }
        }

        _enrich_x_article(item, tweet, cache)

        self.assertEqual(item["article_source"], "x_article")
        self.assertEqual(item["article_title"], "30日で人生を変える習慣")
        self.assertEqual(
            item["content"],
            "朝起きたらまず今日の一番大事なことを決める。\n小さく継続できる習慣だけを選ぶ。",
        )


if __name__ == "__main__":
    unittest.main()
