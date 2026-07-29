from datetime import datetime, timezone

from app.ai import GeminiEditor
from app.article_loader import ArticleLoader
from app.config import settings
from app.database import PublicationDatabase
from app.filtering import HardwareNewsFilter
from app.formatter import PostFormatter
from app.images import ImageService
from app.logger import logger
from app.sources import SourceManager
from app.telegram import TelegramPublisher


class NewsFlowService:
    MAX_AI_ATTEMPTS = 20

    def __init__(self) -> None:
        self._database = PublicationDatabase(settings.database_path)
        self._sources = SourceManager()
        self._filter = HardwareNewsFilter()
        self._loader = ArticleLoader()
        self._images = ImageService()
        self._editor = GeminiEditor()
        self._formatter = PostFormatter()
        self._telegram = TelegramPublisher()

    def _interval_has_elapsed(self) -> bool:
        if settings.force_publish:
            logger.info("Ручной запуск: часовой интервал отключён")
            return True

        latest = self._database.latest_published_at()
        if latest is None:
            return True

        elapsed = (datetime.now(timezone.utc) - latest).total_seconds()
        remaining = settings.publish_interval - elapsed
        if remaining <= 0:
            return True

        logger.info(
            "До следующей публикации осталось примерно {} мин.",
            max(1, int((remaining + 59) // 60)),
        )
        return False

    async def run(self) -> int:
        if not self._interval_has_elapsed():
            await self._telegram.close()
            return 0

        published = 0
        counters = {
            "already_processed": 0,
            "duplicates": 0,
            "filtered": 0,
            "load_errors": 0,
            "no_image": 0,
            "ai_rejected": 0,
            "ai_attempts": 0,
        }

        try:
            articles = await self._sources.fetch()
            articles.sort(
                key=lambda item: (
                    self._filter.priority(item),
                    item.published_at or datetime.min.replace(tzinfo=timezone.utc),
                ),
                reverse=True,
            )

            for article in articles:
                if published >= settings.max_articles_per_run:
                    break
                if counters["ai_attempts"] >= self.MAX_AI_ATTEMPTS:
                    logger.info("Достигнут лимит AI-проверок за проход: {}", self.MAX_AI_ATTEMPTS)
                    break

                original_url = article.url
                if self._database.is_duplicate(article):
                    counters["duplicates"] += 1
                    self._database.save(article, "duplicate", aliases=(original_url,))
                    continue

                if not self._filter.accepts(article):
                    counters["filtered"] += 1
                    self._database.save(article, "filtered", aliases=(original_url,))
                    continue

                logger.info(
                    "Кандидат [{}], приоритет={}: {}",
                    article.source,
                    self._filter.priority(article),
                    article.title,
                )
                try:
                    article = await self._loader.load(article)
                except Exception as exc:
                    counters["load_errors"] += 1
                    logger.warning("Страница не загружена {}: {}", original_url, exc)
                    continue

                # The same launch can enter through several Google News searches and
                # slightly different URLs. Check again after resolving the real page.
                if self._database.is_duplicate(article):
                    counters["duplicates"] += 1
                    self._database.save(article, "duplicate", aliases=(original_url,))
                    continue

                article.image_path = await self._images.download(article.image_url, article.url)
                if article.image_path is None:
                    counters["no_image"] += 1
                    self._database.save(article, "no_image", aliases=(original_url,))
                    continue

                counters["ai_attempts"] += 1
                editorial = await self._editor.process(article)
                if not editorial.publish:
                    counters["ai_rejected"] += 1
                    self._database.save(article, "ai_rejected", aliases=(original_url,))
                    continue

                article.translated_title = editorial.title
                article.translated_summary = editorial.summary
                article.tags = editorial.tags
                caption = self._formatter.format(article)

                try:
                    await self._telegram.publish(caption, article.image_path)
                except Exception as exc:
                    logger.exception("Telegram-публикация не удалась: {}", exc)
                    raise RuntimeError(f"Telegram publication failed: {exc}") from exc

                self._database.save(article, "published", aliases=(original_url,))
                published += 1
                logger.info("Опубликовано: {}", article.url)

            logger.info(
                "Итог: опубликовано={}, обработано ранее={}, дубли={}, локальный фильтр={}, "
                "ошибки загрузки={}, без картинки={}, AI-проверок={}, отклонено AI={}",
                published,
                counters["already_processed"],
                counters["duplicates"],
                counters["filtered"],
                counters["load_errors"],
                counters["no_image"],
                counters["ai_attempts"],
                counters["ai_rejected"],
            )
            return published
        finally:
            await self._telegram.close()
