from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path


@dataclass(slots=True)
class Article:
    source: str
    title: str
    url: str
    published_at: datetime | None = None
    rss_summary: str = ""
    content: str = ""
    image_url: str | None = None
    image_path: Path | None = None
    translated_title: str = ""
    translated_summary: str = ""
    tags: list[str] = field(default_factory=list)
    used_feed_fallback: bool = False
    is_recipe_source: bool = False
    from_archive: bool = False
    has_structured_recipe: bool = False
    recipe_cuisine: str = ""
