import asyncio
import calendar
import hashlib
import re
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from typing import Any
from urllib.parse import unquote, urlencode, urlparse, urlunparse

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
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0 Safari/537.36"
    )
    MAX_ARCHIVE_URLS_PER_SOURCE = 240
    MAX_SITEMAPS_PER_SOURCE = 8
    ARCHIVE_EXCLUDED_TOKENS = (
        "/category/",
        "/tag/",
        "/author/",
        "/page/",
        "/about",
        "/contact",
        "/privacy",
        "/terms",
        "/shop",
        "/product/",
        "/cart",
        "/newsletter",
        "/subscribe",
        "/restaurant",
        "/travel",
        "/menu",
        "/news/",
        "/press/",
        "/giveaway",
        "/roundup",
        "/collection",
        "/best-",
    )

    def __init__(self) -> None:
        data = yaml.safe_load(settings.sources_path.read_text(encoding="utf-8")) or {}
        configured: list[dict[str, Any]] = data.get("sources", [])
        discovery = [
            {
                "name": item["name"],
                "url": self._google_news_url(
                    f"{item['query']} {settings.query_exclusions}".strip()
                ),
                "recipe_only": False,
                "archive": False,
            }
            for item in settings.discovery_queries
        ]
        self._sources: list[dict[str, Any]] = [*configured, *discovery]
        self._semaphore = asyncio.Semaphore(10)

    @staticmethod
    def _google_news_url(query: str) -> str:
        params = urlencode(
            {
                "q": query,
                "hl": "en-US",
                "gl": "US",
                "ceid": "US:en",
            }
        )
        return f"https://news.google.com/rss/search?{params}"

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
            key=lambda item: item.published_at
            or datetime.min.replace(tzinfo=timezone.utc),
            reverse=True,
        )
        logger.info(
            "RSS [{}]: настроено источников={}, доступно={}, найдено={}, "
            "свежих уникальных={}",
            settings.bot_id,
            len(self._sources),
            available_sources,
            len(articles),
            len(fresh),
        )
        return fresh

    async def fetch_archive(self) -> list[Article]:
        sources = [source for source in self._sources if source.get("archive", False)]
        if not sources:
            return []

        async with httpx.AsyncClient(
            timeout=httpx.Timeout(22.0),
            follow_redirects=True,
            headers={
                "User-Agent": self.USER_AGENT,
                "Accept": "application/xml,text/xml,text/plain,*/*;q=0.7",
            },
        ) as client:
            groups = await asyncio.gather(
                *(self._fetch_source_archive(client, source) for source in sources),
                return_exceptions=True,
            )

        articles: list[Article] = []
        available_sources = 0
        for source, result in zip(sources, groups, strict=True):
            if isinstance(result, Exception):
                logger.warning(
                    "Архив рецептов {} недоступен: {}",
                    source.get("name"),
                    result,
                )
                continue
            if result:
                available_sources += 1
                articles.extend(result)

        unique: dict[str, Article] = {}
        for article in articles:
            unique.setdefault(article.url, article)

        result = list(unique.values())
        logger.info(
            "Архив рецептов [{}]: источников={}, доступно={}, кандидатов={}",
            settings.bot_id,
            len(sources),
            available_sources,
            len(result),
        )
        return result

    async def _fetch_source(
        self,
        client: httpx.AsyncClient,
        source: dict[str, Any],
    ) -> list[Article]:
        async with self._semaphore:
            response = await client.get(str(source["url"]))
            response.raise_for_status()

        feed = feedparser.parse(response.content)
        if feed.bozo and not feed.entries:
            raise RuntimeError(str(feed.bozo_exception))

        articles: list[Article] = []
        recipe_only = bool(source.get("recipe_only", False))
        for entry in feed.entries[:100]:
            link = str(entry.get("link", "")).strip()
            title = BeautifulSoup(
                str(entry.get("title", "")),
                "html.parser",
            ).get_text(" ", strip=True)
            if not link or not title:
                continue

            rss_summary = BeautifulSoup(
                str(entry.get("summary", entry.get("description", ""))),
                "html.parser",
            ).get_text(" ", strip=True)

            articles.append(
                Article(
                    source=str(source["name"]),
                    title=title,
                    url=link,
                    published_at=self._published_at(entry),
                    rss_summary=rss_summary,
                    image_url=self._entry_image(entry),
                    is_recipe_source=recipe_only,
                )
            )

        logger.info("RSS [{}]: {} записей", source["name"], len(articles))
        return articles

    async def _fetch_source_archive(
        self,
        client: httpx.AsyncClient,
        source: dict[str, Any],
    ) -> list[Article]:
        sitemap_urls = await self._discover_sitemap_urls(client, source)
        if not sitemap_urls:
            return []

        entries: list[tuple[str, datetime | None]] = []
        for sitemap_url in sitemap_urls[: self.MAX_SITEMAPS_PER_SOURCE]:
            try:
                content = await self._fetch_bytes(client, sitemap_url)
                root = ET.fromstring(content)
            except (httpx.HTTPError, ET.ParseError, ValueError) as exc:
                logger.info(
                    "Sitemap {} не прочитан для {}: {}",
                    sitemap_url,
                    source["name"],
                    exc,
                )
                continue

            root_name = self._local_name(root.tag)
            if root_name == "sitemapindex":
                nested = [
                    self._element_text(item, "loc")
                    for item in root
                    if self._local_name(item.tag) == "sitemap"
                ]
                for child_url in self._select_sitemap_children(nested):
                    try:
                        child_content = await self._fetch_bytes(client, child_url)
                        child_root = ET.fromstring(child_content)
                    except (httpx.HTTPError, ET.ParseError, ValueError):
                        continue
                    entries.extend(self._urlset_entries(child_root))
                    if len(entries) >= self.MAX_ARCHIVE_URLS_PER_SOURCE * 4:
                        break
            elif root_name == "urlset":
                entries.extend(self._urlset_entries(root))

            if len(entries) >= self.MAX_ARCHIVE_URLS_PER_SOURCE * 4:
                break

        filtered: list[tuple[str, datetime | None]] = []
        seen: set[str] = set()
        for url, lastmod in entries:
            if url in seen or not self._likely_recipe_url(url):
                continue
            seen.add(url)
            filtered.append((url, lastmod))

        selected = self._rotating_window(
            filtered,
            source_name=str(source["name"]),
            limit=self.MAX_ARCHIVE_URLS_PER_SOURCE,
        )
        recipe_only = bool(source.get("recipe_only", True))
        articles = [
            Article(
                source=str(source["name"]),
                title=self._title_from_url(url),
                url=url,
                published_at=lastmod,
                rss_summary="Recipe archive entry",
                is_recipe_source=recipe_only,
                from_archive=True,
            )
            for url, lastmod in selected
        ]
        logger.info(
            "Архив [{}]: найдено URL={}, после фильтра={}, выбрано={}",
            source["name"],
            len(entries),
            len(filtered),
            len(articles),
        )
        return articles

    async def _discover_sitemap_urls(
        self,
        client: httpx.AsyncClient,
        source: dict[str, Any],
    ) -> list[str]:
        configured = source.get("sitemaps") or source.get("sitemap") or []
        if isinstance(configured, str):
            candidates = [configured]
        else:
            candidates = [str(value) for value in configured if value]

        origin = self._origin(str(source["url"]))
        try:
            robots = (await self._fetch_bytes(client, f"{origin}/robots.txt")).decode(
                "utf-8",
                errors="ignore",
            )
            for line in robots.splitlines():
                if line.lower().startswith("sitemap:"):
                    value = line.split(":", 1)[1].strip()
                    if value:
                        candidates.append(value)
        except httpx.HTTPError:
            pass

        candidates.extend(
            [
                f"{origin}/sitemap_index.xml",
                f"{origin}/wp-sitemap.xml",
                f"{origin}/sitemap.xml",
            ]
        )
        return list(dict.fromkeys(candidates))

    async def _fetch_bytes(self, client: httpx.AsyncClient, url: str) -> bytes:
        async with self._semaphore:
            response = await client.get(url)
            response.raise_for_status()
            return response.content

    @classmethod
    def _select_sitemap_children(cls, urls: list[str]) -> list[str]:
        clean = [url.strip() for url in urls if url and url.strip()]
        preferred = [
            url
            for url in clean
            if any(token in url.lower() for token in ("recipe", "post", "posts"))
            and not any(
                token in url.lower()
                for token in ("category", "tag", "author", "page", "product")
            )
        ]
        others = [
            url
            for url in clean
            if url not in preferred
            and not any(
                token in url.lower()
                for token in ("category", "tag", "author", "page", "product", "image")
            )
        ]
        return [*preferred, *others][: cls.MAX_SITEMAPS_PER_SOURCE]

    @classmethod
    def _urlset_entries(
        cls,
        root: ET.Element,
    ) -> list[tuple[str, datetime | None]]:
        if cls._local_name(root.tag) != "urlset":
            return []
        entries: list[tuple[str, datetime | None]] = []
        for item in root:
            if cls._local_name(item.tag) != "url":
                continue
            loc = cls._element_text(item, "loc")
            if not loc:
                continue
            lastmod = cls._parse_lastmod(cls._element_text(item, "lastmod"))
            entries.append((loc, lastmod))
        return entries

    @staticmethod
    def _element_text(element: ET.Element, local_name: str) -> str:
        for child in element:
            if SourceManager._local_name(child.tag) == local_name:
                return (child.text or "").strip()
        return ""

    @staticmethod
    def _local_name(tag: str) -> str:
        return tag.rsplit("}", 1)[-1].lower()

    @classmethod
    def _likely_recipe_url(cls, url: str) -> bool:
        parsed = urlparse(url)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            return False
        lowered = f"{parsed.path}/".lower()
        if lowered in {"//", "/"}:
            return False
        if any(token in lowered for token in cls.ARCHIVE_EXCLUDED_TOKENS):
            return False
        if re.search(r"/(?:19|20)\d{2}/\d{1,2}/?$", lowered):
            return False
        return True

    @staticmethod
    def _rotating_window(
        entries: list[tuple[str, datetime | None]],
        *,
        source_name: str,
        limit: int,
    ) -> list[tuple[str, datetime | None]]:
        if len(entries) <= limit:
            return entries
        day = datetime.now(timezone.utc).date().isoformat()
        digest = hashlib.sha256(f"{source_name}:{day}".encode("utf-8")).hexdigest()
        start = int(digest[:12], 16) % len(entries)
        doubled = [*entries, *entries]
        return doubled[start : start + limit]

    @staticmethod
    def _title_from_url(url: str) -> str:
        path = urlparse(url).path.rstrip("/")
        slug = unquote(path.rsplit("/", 1)[-1])
        title = re.sub(r"[-_]+", " ", slug)
        title = re.sub(r"\s+", " ", title).strip()
        return title.title() or "Recipe"

    @staticmethod
    def _origin(url: str) -> str:
        parsed = urlparse(url)
        return urlunparse((parsed.scheme or "https", parsed.netloc, "", "", "", "")).rstrip("/")

    @staticmethod
    def _parse_lastmod(value: str) -> datetime | None:
        if not value:
            return None
        cleaned = value.strip().replace("Z", "+00:00")
        try:
            parsed = datetime.fromisoformat(cleaned)
        except ValueError:
            try:
                parsed = datetime.strptime(cleaned[:10], "%Y-%m-%d")
            except ValueError:
                return None
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)

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
