"""翻訳用途で使う低コストGeminiモデルの共通設定。"""

import os
from pathlib import Path

import yaml

ROOT = Path(__file__).parent
DEFAULT_TRANSLATION_MODEL = "gemini-2.5-flash-lite"
DEFAULT_SOCIAL_TRANSLATION_MODEL = "gemini-2.5-flash"


def get_translation_model() -> str:
    override = os.environ.get("GEMINI_TRANSLATION_MODEL")
    if override:
        return override
    try:
        config = yaml.safe_load((ROOT / "config.yaml").read_text(encoding="utf-8")) or {}
        return (
            config.get("analysis", {})
            .get("models", {})
            .get("translation", DEFAULT_TRANSLATION_MODEL)
        )
    except (OSError, yaml.YAMLError):
        return DEFAULT_TRANSLATION_MODEL


def get_social_translation_model() -> str:
    override = os.environ.get("GEMINI_SOCIAL_TRANSLATION_MODEL")
    if override:
        return override
    try:
        config = yaml.safe_load((ROOT / "config.yaml").read_text(encoding="utf-8")) or {}
        return (
            config.get("analysis", {})
            .get("models", {})
            .get("social_translation", DEFAULT_SOCIAL_TRANSLATION_MODEL)
        )
    except (OSError, yaml.YAMLError):
        return DEFAULT_SOCIAL_TRANSLATION_MODEL
