import asyncio
import calendar
from datetime import datetime, timedelta, timezone
from typing import Any

import feedparser
import httpx
import yaml
from bs4 import BeautifulSoup

from app.config import settings
from app.logger import logger
from app.models import Article


class SourceManager:
    USER_AGENT = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 Chrome/131.0 Safari/537.36"
    )

    def __init__(self) -> None:
        data = yaml.safe_load(settings.sources_path.read_text(encoding="utf-8")) or {}
        self._sources: list[dict[str, str]] = data.get("sources", [])
        self._semaphore = asyncio.Semaphore(10)

    async def fetch(self) -> list[Article]:
        async with httpx.AsyncClient(
            timeout=httpx.Timeout(25.0),
            follow_redirects=True,
            headers={"User-Agent": self.USER_AGENT},
        ) as client:
            groups = await asyncio.gather(
                *(self._fetch_source(client, source) for source in self._sources),
                return_exceptions=True,
            )

        articles: list[Article] = []
        available_sources = 0
        for source, result in zip(self._sources, groups, strict=True):
            if isinstance(result, Exception):
                logger.warning("Источник {} недоступен: {}", source.get("name"), result)
                continue
            available_sources += 1
            articles.extend(result)

        unique: dict[str, Article] = {}
        for article in articles:
            unique.setdefault(article.url, article)

        cutoff = datetime.now(timezone.utc) - timedelta(hours=settings.max_age_hours)
        fresh = [
            article
            for article in unique.values()
            if article.published_at is None or article.published_at >= cutoff
        ]
        fresh.sort(
            key=lambda item: item.published_at or datetime.min.replace(tzinfo=timezone.utc),
            reverse=True,
        )
        logger.info(
            "RSS: настроено источников={}, доступно={}, найдено={}, свежих уникальных={}",
            len(self._sources),
            available_sources,
            len(articles),
            len(fresh),
        )

        # Do not truncate here. The service must first rank all manufacturers by
        # relevance, otherwise very active laptop brands crowd out memory and storage.
        return fresh

    async def _fetch_source(
        self,
        client: httpx.AsyncClient,
        source: dict[str, str],
    ) -> list[Article]:
        async with self._semaphore:
            response = await client.get(source["url"])
            response.raise_for_status()

        feed = feedparser.parse(response.content)
        if feed.bozo and not feed.entries:
            raise RuntimeError(str(feed.bozo_exception))

        articles: list[Article] = []
        for entry in feed.entries[:25]:
            link = str(entry.get("link", "")).strip()
            title = BeautifulSoup(str(entry.get("title", "")), "html.parser").get_text(
                " ", strip=True
            )
            if not link or not title:
                continue

            rss_summary = BeautifulSoup(
                str(entry.get("summary", entry.get("description", ""))),
                "html.parser",
            ).get_text(" ", strip=True)

            articles.append(
                Article(
                    source=source["name"],
                    title=title,
                    url=link,
                    published_at=self._published_at(entry),
                    rss_summary=rss_summary,
                    image_url=self._entry_image(entry),
                )
            )

        logger.info("RSS [{}]: {} записей", source["name"], len(articles))
        return articles

    @staticmethod
    def _published_at(entry: Any) -> datetime | None:
        parsed = entry.get("published_parsed") or entry.get("updated_parsed")
        if not parsed:
            return None
        return datetime.fromtimestamp(calendar.timegm(parsed), tz=timezone.utc)

    @staticmethod
    def _entry_image(entry: Any) -> str | None:
        for key in ("media_content", "media_thumbnail"):
            for item in entry.get(key, []) or []:
                url = item.get("url")
                if url:
                    return str(url)

        for item in entry.get("enclosures", []) or []:
            content_type = str(item.get("type", ""))
            url = item.get("href") or item.get("url")
            if url and (not content_type or content_type.startswith("image/")):
                return str(url)
        return None
