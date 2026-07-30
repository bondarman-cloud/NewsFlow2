import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


BOT_ID_PATTERN = re.compile(r"^[a-z][a-z0-9_]*$")


@dataclass(frozen=True, slots=True)
class BotProfile:
    id: str
    title: str
    filter_type: str
    base_tag: str
    sources_path: Path
    prompt_path: Path
    require_image: bool
    discovery_queries: tuple[dict[str, str], ...]
    query_exclusions: str
    max_articles_per_run: int
    max_candidates: int
    max_age_hours: int
    publish_interval: int


def load_bot_profile(bot_id: str | None = None, root: Path | None = None) -> BotProfile:
    selected = (bot_id or os.getenv("BOT_ID") or "hardware_news").strip().lower()
    if not BOT_ID_PATTERN.fullmatch(selected):
        raise ValueError(f"Недопустимый BOT_ID: {selected!r}")

    project_root = (root or Path.cwd()).resolve()
    profile_path = project_root / "bots" / selected / "config.yaml"
    if not profile_path.is_file():
        raise FileNotFoundError(
            f"Профиль бота {selected!r} не найден: {profile_path}"
        )

    data: dict[str, Any] = yaml.safe_load(profile_path.read_text(encoding="utf-8")) or {}
    profile_id = str(data.get("id", selected)).strip().lower()
    if profile_id != selected:
        raise ValueError(
            f"ID профиля {profile_id!r} не совпадает с выбранным BOT_ID {selected!r}"
        )

    defaults = data.get("defaults", {}) or {}
    profile_dir = profile_path.parent

    def relative_path(key: str, fallback: str) -> Path:
        value = Path(str(data.get(key, fallback)))
        return value if value.is_absolute() else (project_root / value).resolve()

    queries = tuple(
        {
            "name": str(item["name"]).strip(),
            "query": str(item["query"]).strip(),
        }
        for item in (data.get("discovery_queries", []) or [])
        if isinstance(item, dict) and item.get("name") and item.get("query")
    )

    return BotProfile(
        id=profile_id,
        title=str(data.get("title", profile_id)).strip(),
        filter_type=str(data.get("filter", "tech")).strip().lower(),
        base_tag=str(data.get("base_tag", "новости")).strip(),
        sources_path=relative_path("sources", str(profile_dir / "sources.yaml")),
        prompt_path=relative_path("prompt", str(profile_dir / "prompt.txt")),
        require_image=bool(data.get("require_image", True)),
        discovery_queries=queries,
        query_exclusions=str(data.get("query_exclusions", "")).strip(),
        max_articles_per_run=int(defaults.get("max_articles_per_run", 1)),
        max_candidates=int(defaults.get("max_candidates", 500)),
        max_age_hours=int(defaults.get("max_age_hours", 336)),
        publish_interval=int(defaults.get("publish_interval", 3300)),
    )


profile = load_bot_profile()


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    bot_id: str = Field(default=profile.id, alias="BOT_ID")
    bot_token: str = Field(..., alias="BOT_TOKEN")
    channel_id: str = Field(..., alias="CHANNEL_ID")
    gemini_api_key: str = Field(..., alias="GEMINI_API_KEY")

    database_path: Path = Field(
        default=Path(f"data/{profile.id}.db"),
        alias="DATABASE_PATH",
    )
    image_cache_dir: Path = Field(
        default=Path(f"cache/images/{profile.id}"),
        alias="IMAGE_CACHE_DIR",
    )

    max_articles_per_run: int = Field(
        default=profile.max_articles_per_run,
        alias="MAX_ARTICLES_PER_RUN",
    )
    max_candidates: int = Field(default=profile.max_candidates, alias="MAX_CANDIDATES")
    max_age_hours: int = Field(default=profile.max_age_hours, alias="MAX_AGE_HOURS")
    publish_interval: int = Field(
        default=profile.publish_interval,
        alias="PUBLISH_INTERVAL",
    )
    force_publish: bool = Field(default=False, alias="FORCE_PUBLISH")
    run_mode: str = Field(default="scheduled", alias="RUN_MODE")
    log_level: str = Field(default="INFO", alias="LOG_LEVEL")

    @property
    def title(self) -> str:
        return profile.title

    @property
    def filter_type(self) -> str:
        return profile.filter_type

    @property
    def base_tag(self) -> str:
        return profile.base_tag

    @property
    def sources_path(self) -> Path:
        return profile.sources_path

    @property
    def prompt_path(self) -> Path:
        return profile.prompt_path

    @property
    def require_image(self) -> bool:
        return profile.require_image

    @property
    def discovery_queries(self) -> tuple[dict[str, str], ...]:
        return profile.discovery_queries

    @property
    def query_exclusions(self) -> str:
        return profile.query_exclusions


settings = Settings()
