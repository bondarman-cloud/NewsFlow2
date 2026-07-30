import html
import re

from app.config import settings
from app.models import Article


class PostFormatter:
    MAX_CAPTION_LENGTH = 1000

    def format(self, article: Article) -> str:
        title = html.escape(article.translated_title or article.title)
        source = html.escape(article.source)
        url = html.escape(article.url, quote=True)
        tags = self._format_tags(article.tags)

        footer = f"\n\n🔗 <a href=\"{url}\">Источник: {source}</a>"
        if tags:
            footer = f"\n\n{tags}{footer}"

        prefix = f"<b>{title}</b>\n\n"
        available = self.MAX_CAPTION_LENGTH - len(prefix) - len(footer)
        summary = html.escape(article.translated_summary).strip()
        if len(summary) > available:
            summary = summary[: max(0, available - 1)].rsplit(" ", 1)[0].rstrip(".,:; ") + "…"

        return f"{prefix}{summary}{footer}"

    @staticmethod
    def _format_tags(tags: list[str]) -> str:
        base_tag = re.sub(
            r"[^\wа-яА-ЯёЁ]+",
            "_",
            settings.base_tag.strip(),
        ).strip("_").lower()
        normalized: list[str] = [base_tag] if base_tag else []
        for tag in tags:
            clean = re.sub(r"[^\wа-яА-ЯёЁ]+", "_", tag.strip()).strip("_").lower()
            if clean and clean not in normalized:
                normalized.append(clean)
        return " ".join(f"#{tag}" for tag in normalized[:5])
