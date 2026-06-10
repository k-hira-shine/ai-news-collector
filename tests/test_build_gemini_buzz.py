from build_gemini_buzz import _contains_japanese, ensure_post_translations


def test_contains_japanese() -> None:
    assert _contains_japanese("Geminiの新機能")
    assert not _contains_japanese("Gemini can build an app")


def test_translation_cache_is_applied_without_api(monkeypatch, tmp_path) -> None:
    cache_path = tmp_path / "translations.json"
    cache_path.write_text(
        '{"by_url":{"https://x.com/a/status/1":"日本語訳"}}',
        encoding="utf-8",
    )
    monkeypatch.setattr("build_gemini_buzz.TRANSLATIONS_PATH", cache_path)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)

    posts = [
        {
            "url": "https://x.com/a/status/1",
            "text": "Gemini can build an app.",
        }
    ]

    assert ensure_post_translations(posts)[0]["text_ja"] == "日本語訳"


def test_japanese_post_does_not_require_translation(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(
        "build_gemini_buzz.TRANSLATIONS_PATH",
        tmp_path / "missing.json",
    )
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    posts = [{"url": "https://x.com/a/status/2", "text": "Geminiの新機能です"}]

    assert ensure_post_translations(posts)[0]["text_ja"] == ""
