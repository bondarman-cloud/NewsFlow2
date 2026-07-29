import asyncio
import json
from urllib.parse import urljoin, urlparse

import httpx
import trafilatura
from bs4 import BeautifulSoup
from googlenewsdecoder import gnewsdecoder

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
        original_url = article.url
        resolved_url = await self._resolve_google_news_url(original_url)

        try:
            html, response_url = await self._fetch_html(resolved_url)
            final_url = response_url
            content_url = final_url
            logger.info("Оригинальная страница загружена: {}", final_url)
        except httpx.HTTPError as exc:
            if resolved_url == original_url or "news.google." not in urlparse(original_url).netloc:
                raise

            logger.warning(
                "Официальный сайт недоступен ({}). Использую данные Google News: {}",
                exc,
                resolved_url,
            )
            html, _ = await self._fetch_html(original_url)
            final_url = resolved_url
            content_url = original_url

        soup = BeautifulSoup(html, "html.parser")

        canonical = soup.find("link", rel=lambda value: value and "canonical" in value)
        canonical_url = canonical.get("href") if canonical else None
        if canonical_url:
            candidate = urljoin(content_url, str(canonical_url))
            if "news.google." not in urlparse(candidate).netloc:
                final_url = candidate

        article.url = final_url
        article.image_url = article.image_url or self._extract_image(soup, content_url)
        extracted = trafilatura.extract(
            html,
            url=content_url,
            include_comments=False,
            include_tables=False,
            favor_precision=True,
        )
        article.content = extracted or article.rss_summary or article.title
        logger.info("Материал подготовлен: {} символов, {}", len(article.content), final_url)
        return article

    async def _fetch_html(self, url: str) -> tuple[str, str]:
        async with httpx.AsyncClient(
            timeout=httpx.Timeout(12.0),
            follow_redirects=True,
            headers=self.HEADERS,
        ) as client:
            response = await client.get(url)
            response.raise_for_status()
        return response.text, str(response.url)

    async def _resolve_google_news_url(self, url: str) -> str:
        host = urlparse(url).netloc.lower()
        if "news.google." not in host:
            return url

        try:
            result = await asyncio.to_thread(gnewsdecoder, url)
        except Exception as exc:
            logger.warning("Google News URL не декодирован: {}", exc)
            return url

        if isinstance(result, dict) and result.get("status"):
            decoded_url = str(result.get("decoded_url", "")).strip()
            if decoded_url and "news.google." not in urlparse(decoded_url).netloc.lower():
                logger.info("Google News URL раскрыт: {}", decoded_url)
                return decoded_url

        message = result.get("message") if isinstance(result, dict) else result
        logger.warning("Google News URL остался обёрткой: {}", message)
        return url

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
