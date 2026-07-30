import os
from pathlib import Path

os.environ.setdefault("BOT_TOKEN", "test-token")
os.environ.setdefault("CHANNEL_ID", "-1000000000000")
os.environ.setdefault("GEMINI_API_KEY", "test-key")
os.environ.setdefault("BOT_ID", "hardware_news")

from app.config import load_bot_profile  # noqa: E402


def test_hardware_profile() -> None:
    profile = load_bot_profile("hardware_news", root=Path.cwd())
    assert profile.filter_type == "hardware"
    assert profile.require_image is True
    assert profile.discovery_queries


def test_tech_profile() -> None:
    profile = load_bot_profile("tech_news", root=Path.cwd())
    assert profile.filter_type == "tech"
    assert profile.require_image is False
    assert profile.sources_path.name == "sources.yaml"
