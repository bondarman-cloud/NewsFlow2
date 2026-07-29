from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    bot_token: str = Field(..., alias="BOT_TOKEN")
    channel_id: str = Field(..., alias="CHANNEL_ID")
    gemini_api_key: str = Field(..., alias="GEMINI_API_KEY")

    database_path: Path = Field(
        default=Path("data/newsflow2.db"),
        alias="DATABASE_PATH",
    )
    sources_path: Path = Field(
        default=Path("data/sources.yaml"),
        alias="SOURCES_PATH",
    )
    image_cache_dir: Path = Field(
        default=Path("cache/images"),
        alias="IMAGE_CACHE_DIR",
    )

    max_articles_per_run: int = Field(default=1, alias="MAX_ARTICLES_PER_RUN")
    max_candidates: int = Field(default=120, alias="MAX_CANDIDATES")
    max_age_hours: int = Field(default=336, alias="MAX_AGE_HOURS")
    publish_interval: int = Field(default=3300, alias="PUBLISH_INTERVAL")
    force_publish: bool = Field(default=False, alias="FORCE_PUBLISH")
    log_level: str = Field(default="INFO", alias="LOG_LEVEL")


settings = Settings()
