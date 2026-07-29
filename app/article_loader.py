import json
from urllib.parse import urljoin, urlparse

import httpx
import trafilatura
from bs4 import BeautifulSoup

from app.logger import logger
from app.models import Article


class ArticleLoader:
    HEADERS = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 Chrome/131.0 Safari/537.36"
        ),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
    }

    async def load(self, article: Article) -> Article:
        async with httpx.AsyncClient(
            timeout=httpx.Timeout(30.0),
            follow_redirects=True,
            headers=self.HEADERS,
        ) as client:
            response = await client.get(article.url)
            response.raise_for_status()

        final_url = str(response.url)
        html = response.text
        soup = BeautifulSoup(html, "html.parser")

        canonical = soup.find("link", rel=lambda value: value and "canonical" in value)
        canonical_url = canonical.get("href") if canonical else None
        if canonical_url:
            candidate = urljoin(final_url, str(canonical_url))
            if "news.google." not in urlparse(candidate).netloc:
                final_url = candidate

        article.url = final_url
        article.image_url = article.image_url or self._extract_image(soup, final_url)
        article.content = (
            trafilatura.extract(
                html,
                url=final_url,
                include_comments=False,
                include_tables=False,
                favor_precision=True,
            )
            or article.rss_summary
        )
        logger.info("Страница загружена: {} символов, {}", len(article.content), final_url)
        return article

    def _extract_image(self, soup: BeautifulSoup, base_url: str) -> str | None:
        selectors = (
            ("meta", {"property": "og:image:secure_url"}, "content"),
            ("meta", {"property": "og:image"}, "content"),
            ("meta", {"name": "twitter:image"}, "content"),
            ("meta", {"name": "twitter:image:src"}, "content"),
            ("link", {"rel": "image_src"}, "href"),
        )
        for tag_name, attrs, field in selectors:
            tag = soup.find(tag_name, attrs=attrs)
            value = tag.get(field) if tag else None
            if value:
                return urljoin(base_url, str(value))

        for script in soup.find_all("script", type="application/ld+json"):
            try:
                payload = json.loads(script.string or script.get_text())
            except (json.JSONDecodeError, TypeError):
                continue
            value = self._json_image(payload)
            if value:
                return urljoin(base_url, value)

        for image in soup.find_all("img"):
            classes = " ".join(image.get("class", [])).lower()
            alt = str(image.get("alt", "")).lower()
            if any(token in f"{classes} {alt}" for token in ("logo", "icon", "avatar")):
                continue
            for field in ("data-src", "data-lazy-src", "data-original", "src"):
                value = image.get(field)
                if value and not str(value).startswith("data:"):
                    return urljoin(base_url, str(value))
        return None

    def _json_image(self, value: object) -> str | None:
        if isinstance(value, dict):
            image = value.get("image")
            if isinstance(image, str):
                return image
            if isinstance(image, dict):
                candidate = image.get("url") or image.get("contentUrl")
                if isinstance(candidate, str):
                    return candidate
            if isinstance(image, list):
                for item in image:
                    candidate = self._json_image({"image": item})
                    if candidate:
                        return candidate
            for child in value.values():
                candidate = self._json_image(child)
                if candidate:
                    return candidate
        elif isinstance(value, list):
            for child in value:
                candidate = self._json_image(child)
                if candidate:
                    return candidate
        return None
