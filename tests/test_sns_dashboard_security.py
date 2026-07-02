import unittest

from sns_dashboard import _json_for_script, _render_post_card, _render_sns_html


class SnsDashboardSecurityTests(unittest.TestCase):
    def test_script_json_escapes_closing_script(self) -> None:
        html = _render_sns_html(
            [
                {
                    "id": "xss",
                    "content": '</script><img src=x onerror="alert(1)">',
                    "summary": '</script><svg onload="alert(1)">',
                    "mind_theme": "<b>theme</b>",
                    "key_insights": ["<img src=x onerror=alert(1)>"],
                    "category": "その他",
                    "url": "https://x.com/example/status/1",
                    "engagement": {"likes": 1, "views": 2},
                    "author_followers": 100,
                    "author": "attacker",
                    "author_display": "<attacker>",
                    "is_japanese": True,
                }
            ],
            {},
        )

        self.assertNotIn("</script><img", html)
        self.assertNotIn("</script><svg", html)
        self.assertIn("<\\/script><img", html)
        self.assertIn("&lt;/script&gt;&lt;svg", html)

    def test_post_card_escapes_user_and_llm_fields(self) -> None:
        html = _render_post_card(
            {
                "content": "<script>alert(1)</script>",
                "summary": "<img src=x onerror=alert(1)>",
                "mind_theme": "<b>theme</b>",
                "key_insights": ["<i>insight</i>"],
                "category": "cat\" onmouseover=\"alert(1)",
                "credibility": "<strong>bad</strong>",
                "target_audience": "<em>target</em>",
                "url": "https://x.com/example/status/1",
                "engagement": {"likes": 1},
                "author_followers": 100,
                "author_display": "<author>",
            }
        )

        self.assertNotIn("<script>alert(1)</script>", html)
        self.assertNotIn("<img src=x", html)
        self.assertNotIn("<strong>bad</strong>", html)
        self.assertIn("&lt;script&gt;alert(1)&lt;/script&gt;", html)
        self.assertIn("&lt;img src=x onerror=alert(1)&gt;", html)
        self.assertIn("&lt;strong&gt;bad&lt;/strong&gt;", html)

    def test_json_for_script_preserves_json_parseability(self) -> None:
        payload = [{"content": "</script>\u2028x\u2029"}]
        encoded = _json_for_script(payload)

        self.assertIn("<\\/script>", encoded)
        self.assertIn("\\u2028", encoded)
        self.assertIn("\\u2029", encoded)


if __name__ == "__main__":
    unittest.main()
