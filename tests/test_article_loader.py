import asyncio

import httpx

from app.article_loader import ArticleLoader
from app.models import Article


def test_blocked_page_uses_rss_summary_and_image(monkeypatch) -> None:
    loader = ArticleLoader()
    article = Article(
        source="Microsoft",
        title="Microsoft launches a new Azure AI service",
        url="https://blogs.microsoft.com/example",
        rss_summary="Microsoft introduced a new Azure AI service for developers.",
        image_url="https://cdn.example.com/azure.jpg",
    )

    async def blocked(_url: str) -> tuple[str, str]:
        request = httpx.Request("GET", article.url)
        response = httpx.Response(403, request=request)
        raise httpx.HTTPStatusError("Forbidden", request=request, response=response)

    monkeypatch.setattr(loader, "_fetch_html", blocked)

    result = asyncio.run(loader.load(article))

    assert result.content == article.rss_summary
    assert result.image_url == "https://cdn.example.com/azure.jpg"
    assert result.used_feed_fallback is True


def test_blocked_page_without_summary_still_uses_title(monkeypatch) -> None:
    loader = ArticleLoader()
    article = Article(
        source="Example",
        title="Example releases a new API",
        url="https://example.com/release",
    )

    async def blocked(_url: str) -> tuple[str, str]:
        request = httpx.Request("GET", article.url)
        response = httpx.Response(403, request=request)
        raise httpx.HTTPStatusError("Forbidden", request=request, response=response)

    monkeypatch.setattr(loader, "_fetch_html", blocked)

    result = asyncio.run(loader.load(article))

    assert result.content == article.title
    assert result.used_feed_fallback is True
