from collections import Counter
from datetime import datetime, timezone

from app.ai import GeminiEditor
from app.article_loader import ArticleLoader
from app.config import settings
from app.database import PublicationDatabase
from app.filtering import build_filter
from app.formatter import PostFormatter
from app.images import ImageService
from app.logger import logger
from app.models import Article
from app.sources import SourceManager
from app.telegram import TelegramPublisher


class NewsFlowService:
    MAX_AI_ATTEMPTS = 30
    MAX_CANDIDATES_PER_SOURCE = 3

    def __init__(self) -> None:
        self._database = PublicationDatabase(settings.database_path)
        self._sources = SourceManager()
        self._filter = build_filter(settings.filter_type)
        self._loader = ArticleLoader()
        self._images = ImageService()
        self._editor = GeminiEditor()
        self._formatter = PostFormatter()
        self._telegram = TelegramPublisher()

    def _interval_has_elapsed(self) -> bool:
        if settings.force_publish:
            logger.info(
                "Ручной запуск [{}]: интервал автоматических публикаций не учитывается",
                settings.bot_id,
            )
            return True

        latest = self._database.latest_published_at(publication_mode="scheduled")
        if latest is None:
            return True

        elapsed = (datetime.now(timezone.utc) - latest).total_seconds()
        remaining = settings.publish_interval - elapsed
        if remaining <= 0:
            return True

        logger.info(
            "До следующей автоматической публикации [{}] осталось примерно {} мин.",
            settings.bot_id,
            max(1, int((remaining + 59) // 60)),
        )
        return False

    def _diversify(self, articles: list[Article]) -> list[Article]:
        selected: list[Article] = []
        source_counts: Counter[str] = Counter()

        for article in articles:
            if source_counts[article.source] >= self.MAX_CANDIDATES_PER_SOURCE:
                continue
            selected.append(article)
            source_counts[article.source] += 1
            if len(selected) >= settings.max_candidates:
                break

        return selected

    async def run(self) -> int:
        if not self._interval_has_elapsed():
            await self._telegram.close()
            return 0

        published = 0
        counters = {
            "local_filtered": 0,
            "duplicates": 0,
            "load_errors": 0,
            "feed_fallbacks": 0,
            "no_image": 0,
            "ai_rejected": 0,
            "ai_attempts": 0,
        }

        try:
            logger.info(
                "Запуск бота {} ({}) в режиме {}",
                settings.bot_id,
                settings.title,
                settings.run_mode,
            )
            articles = await self._sources.fetch()
            articles.sort(
                key=lambda item: (
                    self._filter.priority(item),
                    item.published_at or datetime.min.replace(tzinfo=timezone.utc),
                ),
                reverse=True,
            )

            eligible = [article for article in articles if self._filter.accepts(article)]
            counters["local_filtered"] = len(articles) - len(eligible)
            eligible_by_source = Counter(article.source for article in eligible)
            logger.info(
                "Локально подходящих материалов [{}]: {} из {}. Источники: {}",
                settings.bot_id,
                len(eligible),
                len(articles),
                ", ".join(
                    f"{source}={count}"
                    for source, count in eligible_by_source.most_common(40)
                ) or "нет",
            )

            articles = self._diversify(eligible)
            logger.info(
                "После ранжирования и ограничения по {} материала на источник проверяем {} кандидатов",
                self.MAX_CANDIDATES_PER_SOURCE,
                len(articles),
            )

            for article in articles:
                if published >= settings.max_articles_per_run:
                    break
                if counters["ai_attempts"] >= self.MAX_AI_ATTEMPTS:
                    logger.info("Достигнут лимит AI-проверок за проход: {}", self.MAX_AI_ATTEMPTS)
                    break

                original_url = article.url
                if self._database.is_duplicate(
                    article,
                    retry_non_published=settings.force_publish,
                ):
                    counters["duplicates"] += 1
                    self._database.save(article, "duplicate", aliases=(original_url,))
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
                    logger.warning("Страница и RSS-анонс не загружены {}: {}", original_url, exc)
                    continue

                if article.used_feed_fallback:
                    counters["feed_fallbacks"] += 1

                if self._database.is_duplicate(
                    article,
                    retry_non_published=settings.force_publish,
                ):
                    counters["duplicates"] += 1
                    self._database.save(article, "duplicate", aliases=(original_url,))
                    continue

                article.image_path = await self._images.download(article.image_url, article.url)
                if article.image_path is None and settings.require_image:
                    counters["no_image"] += 1
                    self._database.save(article, "no_image", aliases=(original_url,))
                    logger.info(
                        "Кандидат отклонён: для {} обязательно изображение, но оно недоступно",
                        article.title,
                    )
                    continue

                counters["ai_attempts"] += 1
                editorial = await self._editor.process(article)
                if not editorial.publish:
                    counters["ai_rejected"] += 1
                    self._database.save(article, "ai_rejected", aliases=(original_url,))
                    logger.info(
                        "AI отклонил [{}] {}. Причина: {}",
                        article.source,
                        article.title,
                        editorial.reason or "модель не указала причину",
                    )
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

                self._database.save(
                    article,
                    "published",
                    aliases=(original_url,),
                    publication_mode=settings.run_mode,
                )
                published += 1
                logger.info(
                    "Опубликовано [{}:{}]: {}",
                    settings.bot_id,
                    settings.run_mode,
                    article.url,
                )

            logger.info(
                "Итог [{}]: опубликовано={}, локально отсеяно={}, дубли={}, "
                "RSS-fallback={}, ошибки загрузки={}, без картинки={}, "
                "AI-проверок={}, отклонено AI={}",
                settings.bot_id,
                published,
                counters["local_filtered"],
                counters["duplicates"],
                counters["feed_fallbacks"],
                counters["load_errors"],
                counters["no_image"],
                counters["ai_attempts"],
                counters["ai_rejected"],
            )
            return published
        finally:
            await self._telegram.close()
