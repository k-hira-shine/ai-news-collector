from translation_config import (
    DEFAULT_SOCIAL_TRANSLATION_MODEL,
    DEFAULT_TRANSLATION_MODEL,
    get_social_translation_model,
    get_translation_model,
)


def test_translation_model_defaults_to_flash_lite(monkeypatch) -> None:
    monkeypatch.delenv("GEMINI_TRANSLATION_MODEL", raising=False)

    assert get_translation_model() == DEFAULT_TRANSLATION_MODEL


def test_translation_model_can_be_overridden(monkeypatch) -> None:
    monkeypatch.setenv("GEMINI_TRANSLATION_MODEL", "test-translation-model")

    assert get_translation_model() == "test-translation-model"


def test_social_translation_defaults_to_flash(monkeypatch) -> None:
    monkeypatch.delenv("GEMINI_SOCIAL_TRANSLATION_MODEL", raising=False)

    assert get_social_translation_model() == DEFAULT_SOCIAL_TRANSLATION_MODEL
