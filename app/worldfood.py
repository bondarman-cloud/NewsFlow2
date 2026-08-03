import asyncio
import base64
import html
import json
import re
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone

import httpx

from app.ai import GeminiEditor
from app.article_loader import ArticleLoader
from app.config import settings
from app.database import PublicationDatabase
from app.filtering import build_filter
from app.images import ImageService
from app.logger import logger
from app.models import Article
from app.sources import SourceManager
from app.telegram import TelegramPublisher


@dataclass(slots=True)
class RecipeEditorialResult:
    publish: bool
    dish_name: str
    cuisine: str
    intro: str
    ingredients: list[str]
    steps: list[str]
    history: str
    tags: list[str]
    reason: str = ""


class GeminiRecipeEditor:
    MODELS = GeminiEditor.MODELS
    MAX_INLINE_IMAGE_BYTES = GeminiEditor.MAX_INLINE_IMAGE_BYTES

    async def process(self, article: Article) -> RecipeEditorialResult:
        parts: list[dict] = [{"text": self._prompt(article)}]
        if article.image_path and article.image_path.exists():
            image_bytes = article.image_path.read_bytes()
            if len(image_bytes) <= self.MAX_INLINE_IMAGE_BYTES:
                parts.append(
                    {
                        "inlineData": {
                            "mimeType": "image/jpeg",
                            "data": base64.b64encode(image_bytes).decode("ascii"),
                        }
                    }
                )

        last_error: Exception | None = None
        last_result: RecipeEditorialResult | None = None
        async with httpx.AsyncClient(timeout=httpx.Timeout(75.0)) as client:
            for model in self.MODELS:
                url = (
                    "https://generativelanguage.googleapis.com/v1beta/models/"
                    f"{model}:generateContent?key={settings.gemini_api_key}"
                )
                payload = {
                    "contents": [{"parts": parts}],
                    "generationConfig": {
                        "thinkingConfig": {"thinkingLevel": "minimal"},
                    },
                }
                try:
                    response = await client.post(url, json=payload)
                    if response.status_code in {400, 404, 429}:
                        last_error = RuntimeError(
                            f"Gemini {model} HTTP {response.status_code}"
                        )
                        logger.warning(
                            "Gemini {} вернул HTTP {}: {}",
                            model,
                            response.status_code,
                            response.text[:300],
                        )
                        continue
                    response.raise_for_status()
                    result = self._parse(
                        self._extract_text(response.json()),
                        trusted_source_recipe=article.has_structured_recipe,
                    )
                    logger.info(
                        "Gemini подготовил рецепт через {} "
                        "(структурированный источник={})",
                        model,
                        article.has_structured_recipe,
                    )
                    if result.publish:
                        return result
                    last_result = result
                    if not article.has_structured_recipe:
                        return result
                except (httpx.HTTPError, KeyError, ValueError, TypeError) as exc:
                    last_error = exc
                    logger.warning("Ошибка Gemini {}: {}", model, exc)

        if last_result is not None:
            return last_result
        raise RuntimeError(f"Все модели Gemini недоступны: {last_error}")

    @staticmethod
    def _extract_text(payload: dict) -> str:
        parts = payload["candidates"][0]["content"]["parts"]
        return "".join(str(part.get("text", "")) for part in parts).strip()

    @classmethod
    def _parse(
        cls,
        text: str,
        *,
        trusted_source_recipe: bool = False,
    ) -> RecipeEditorialResult:
        cleaned = re.sub(
            r"^```(?:json)?\s*|\s*```$",
            "",
            text.strip(),
            flags=re.IGNORECASE | re.DOTALL,
        )
        start = cleaned.find("{")
        end = cleaned.rfind("}")
        if start < 0 or end < start:
            raise ValueError("Gemini не вернул JSON")

        data = json.loads(cleaned[start : end + 1])
        ingredients = cls._string_list(data.get("ingredients", []))
        steps = cls._string_list(data.get("steps", []))
        dish_name = str(data.get("dish_name", "")).strip()
        cuisine = str(data.get("cuisine", "")).strip()
        history = str(data.get("history", "")).strip()
        reason = str(data.get("reason", "")).strip()

        complete = bool(
            dish_name
            and cuisine
            and len(ingredients) >= 3
            and len(steps) >= 2
            and history
        )
        publish = bool(data.get("publish", False)) and complete
        if trusted_source_recipe and complete:
            publish = True
            reason = ""

        if not complete and not reason:
            reason = (
                "ответ не содержит полного названия, кухни, ингредиентов, "
                "шагов или истории"
            )

        return RecipeEditorialResult(
            publish=publish,
            dish_name=dish_name,
            cuisine=cuisine,
            intro=str(data.get("intro", "")).strip(),
            ingredients=ingredients,
            steps=steps,
            history=history,
            tags=cls._string_list(data.get("tags", [])),
            reason=reason,
        )

    @staticmethod
    def _string_list(value: object) -> list[str]:
        if not isinstance(value, list):
            return []
        result: list[str] = []
        for item in value:
            if isinstance(item, dict):
                amount = str(item.get("amount", "")).strip()
                name = str(item.get("item", item.get("name", ""))).strip()
                text = " ".join(part for part in (amount, name) if part)
            else:
                text = str(item).strip()
            if text:
                result.append(text)
        return result

    @staticmethod
    def _prompt(article: Article) -> str:
        template = settings.prompt_path.read_text(encoding="utf-8")
        content = (article.content or article.rss_summary or article.title)[:24_000]
        structured_note = ""
        if article.has_structured_recipe:
            structured_note = (
                "\n\nВАЖНО: на странице найден валидный блок schema.org Recipe. "
                "Ингредиенты и шаги ниже извлечены именно из источника. "
                "Не оценивай материал как новость или обзор. Переведи и аккуратно "
                "оформи этот рецепт, установи publish=true. Нельзя добавлять "
                "ингредиенты или этапы, отсутствующие в исходном блоке Recipe."
            )
        return (
            template.replace("{{BOT_TITLE}}", settings.title)
            .replace("{{SOURCE}}", article.source)
            .replace("{{URL}}", article.url)
            .replace("{{TITLE}}", article.title)
            .replace("{{CONTENT}}", content)
            .strip()
            + structured_note
        )


class WorldFoodFormatter:
    @staticmethod
    def _short(value: str, limit: int) -> str:
        text = re.sub(r"\s+", " ", value).strip()
        if len(text) <= limit:
            return text
        return text[: limit - 1].rsplit(" ", 1)[0].rstrip(".,:; ") + "…"

    @staticmethod
    def _tags(tags: list[str]) -> str:
        values = [settings.base_tag, *tags]
        normalized: list[str] = []
        for value in values:
            clean = re.sub(r"[^\wа-яА-ЯёЁ]+", "_", value.strip()).strip("_").lower()
            if clean and clean not in normalized:
                normalized.append(clean)
        return " ".join(f"#{tag}" for tag in normalized[:5])

    def photo_caption(self, result: RecipeEditorialResult, article: Article) -> str:
        dish = html.escape(self._short(result.dish_name, 120))
        cuisine = html.escape(self._short(result.cuisine, 80))
        intro = html.escape(self._short(result.intro, 450))
        source = html.escape(article.source)
        url = html.escape(article.url, quote=True)
        caption = f"<b>{dish}</b>\n\n🌍 <b>Кухня:</b> {cuisine}"
        if intro:
            caption += f"\n\n{intro}"
        caption += f'\n\n🔗 <a href="{url}">Источник: {source}</a>'
        return caption

    def recipe_message(self, result: RecipeEditorialResult) -> str:
        dish = html.escape(self._short(result.dish_name, 120))
        ingredients = "\n".join(
            f"• {html.escape(self._short(item, 110))}"
            for item in result.ingredients[:20]
        )
        steps = "\n\n".join(
            f"{index}. {html.escape(self._short(step, 240))}"
            for index, step in enumerate(result.steps[:14], start=1)
        )
        return (
            f"🍽 <b>Рецепт: {dish}</b>\n\n"
            f"<b>Ингредиенты</b>\n{ingredients}\n\n"
            f"<b>Приготовление</b>\n{steps}"
        )

    def history_message(self, result: RecipeEditorialResult, article: Article) -> str:
        dish = html.escape(self._short(result.dish_name, 120))
        history = html.escape(self._short(result.history, 1500))
        source = html.escape(article.source)
        url = html.escape(article.url, quote=True)
        tags = self._tags(result.tags)
        footer = f'\n\n🔗 <a href="{url}">Источник рецепта: {source}</a>'
        if tags:
            footer += f"\n\n{tags}"
        return f"📜 <b>Краткая история: {dish}</b>\n\n{history}{footer}"


class WorldFoodService:
    MAX_AI_ATTEMPTS = 50
    MAX_CANDIDATES_PER_SOURCE = 10
    MIN_FULL_PAGE_CHARS = 250
    MIN_FEED_FALLBACK_CHARS = 120

    def __init__(self) -> None:
        self._database = PublicationDatabase(settings.database_path)
        self._sources = SourceManager()
        self._filter = build_filter(settings.filter_type)
        self._loader = ArticleLoader()
        self._images = ImageService()
        self._editor = GeminiRecipeEditor()
        self._formatter = WorldFoodFormatter()
        self._telegram = TelegramPublisher()

    def _interval_has_elapsed(self) -> bool:
        if settings.force_publish:
            logger.info(
                "Ручной WorldFood: интервал и недавние неудачные проверки игнорируются"
            )
            return True
        latest = self._database.latest_published_at(publication_mode="scheduled")
        if latest is None:
            return True
        elapsed = (datetime.now(timezone.utc) - latest).total_seconds()
        return elapsed >= settings.publish_interval

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

    def _is_duplicate(self, article: Article) -> bool:
        return self._database.is_duplicate(
            article,
            retry_non_published=settings.force_publish,
        )

    @staticmethod
    def _looks_like_recipe_text(article: Article) -> bool:
        if article.has_structured_recipe:
            return True
        text = article.content.lower()
        ingredients = any(
            marker in text
            for marker in ("ingredients", "ingredient list", "you will need")
        )
        instructions = any(
            marker in text
            for marker in (
                "instructions",
                "directions",
                "method",
                "preparation",
                "how to make",
            )
        )
        return ingredients and instructions

    @staticmethod
    def _deduplicate_urls(articles: list[Article]) -> list[Article]:
        unique: dict[str, Article] = {}
        for article in articles:
            unique.setdefault(article.url, article)
        return list(unique.values())

    async def run(self) -> int:
        if not self._interval_has_elapsed():
            logger.info("Интервал публикации worldfood_bot ещё не истёк")
            await self._telegram.close()
            return 0

        published = 0
        counters = {
            "local_filtered": 0,
            "duplicates": 0,
            "load_errors": 0,
            "feed_fallbacks": 0,
            "archive_candidates": 0,
            "not_recipe_page": 0,
            "insufficient_recipe": 0,
            "no_image": 0,
            "ai_attempts": 0,
            "ai_rejected": 0,
        }

        try:
            logger.info("Запуск {} в режиме {}", settings.bot_id, settings.run_mode)
            feed_articles, archive_articles = await asyncio.gather(
                self._sources.fetch(),
                self._sources.fetch_archive(),
            )
            counters["archive_candidates"] = len(archive_articles)
            articles = self._deduplicate_urls([*feed_articles, *archive_articles])
            articles.sort(
                key=lambda item: (
                    self._filter.priority(item),
                    item.published_at
                    or datetime.min.replace(tzinfo=timezone.utc),
                ),
                reverse=True,
            )

            eligible = [article for article in articles if self._filter.accepts(article)]
            counters["local_filtered"] = len(articles) - len(eligible)

            new_articles: list[Article] = []
            for article in eligible:
                if self._is_duplicate(article):
                    counters["duplicates"] += 1
                    continue
                new_articles.append(article)

            candidates = self._diversify(new_articles)
            logger.info(
                "Кандидатов WorldFood: всего={}, RSS={}, архив={}, "
                "локально отклонено={}, опубликованных дублей до отбора={}, "
                "к проверке={}",
                len(articles),
                len(feed_articles),
                len(archive_articles),
                counters["local_filtered"],
                counters["duplicates"],
                len(candidates),
            )

            for article in candidates:
                if published >= settings.max_articles_per_run:
                    break
                if counters["ai_attempts"] >= self.MAX_AI_ATTEMPTS:
                    logger.info(
                        "Достигнут лимит AI-проверок WorldFood: {}",
                        self.MAX_AI_ATTEMPTS,
                    )
                    break

                original_url = article.url
                logger.info(
                    "WorldFood проверяет [{}]{}: {}",
                    article.source,
                    " [архив]" if article.from_archive else "",
                    article.title,
                )
                try:
                    article = await self._loader.load(article)
                except Exception as exc:
                    counters["load_errors"] += 1
                    logger.warning(
                        "Страница рецепта не загружена {}: {}",
                        original_url,
                        exc,
                    )
                    continue

                if article.used_feed_fallback:
                    counters["feed_fallbacks"] += 1

                if self._is_duplicate(article):
                    counters["duplicates"] += 1
                    logger.info(
                        "WorldFood обнаружил опубликованный дубль после раскрытия URL: "
                        "[{}] {}",
                        article.source,
                        article.title,
                    )
                    continue

                minimum_chars = (
                    self.MIN_FEED_FALLBACK_CHARS
                    if article.used_feed_fallback
                    else self.MIN_FULL_PAGE_CHARS
                )
                content_length = len(article.content.strip())
                if content_length < minimum_chars:
                    counters["insufficient_recipe"] += 1
                    self._database.save(
                        article,
                        "insufficient_recipe",
                        aliases=(original_url,),
                    )
                    logger.info(
                        "WorldFood отклонил [{}] {}: текста недостаточно "
                        "({} символов, нужно минимум {})",
                        article.source,
                        article.title,
                        content_length,
                        minimum_chars,
                    )
                    continue

                if not self._looks_like_recipe_text(article):
                    counters["not_recipe_page"] += 1
                    self._database.save(
                        article,
                        "not_recipe_page",
                        aliases=(original_url,),
                    )
                    logger.info(
                        "WorldFood отклонил [{}] {}: на странице нет schema.org Recipe "
                        "и не найдены одновременно разделы ингредиентов и приготовления",
                        article.source,
                        article.title,
                    )
                    continue

                article.image_path = await self._images.download(
                    article.image_url,
                    article.url,
                )
                if article.image_path is None:
                    counters["no_image"] += 1
                    self._database.save(article, "no_image", aliases=(original_url,))
                    logger.info(
                        "WorldFood отклонил [{}] {}: фотография блюда недоступна",
                        article.source,
                        article.title,
                    )
                    continue

                counters["ai_attempts"] += 1
                editorial = await self._editor.process(article)
                if not editorial.publish:
                    counters["ai_rejected"] += 1
                    self._database.save(
                        article,
                        "ai_rejected",
                        aliases=(original_url,),
                    )
                    logger.info(
                        "AI отклонил рецепт [{}] {}. Причина: {}",
                        article.source,
                        article.title,
                        editorial.reason or "причина не указана",
                    )
                    continue

                caption = self._formatter.photo_caption(editorial, article)
                recipe = self._formatter.recipe_message(editorial)
                history = self._formatter.history_message(editorial, article)

                try:
                    await self._telegram.publish_photo(caption, article.image_path)
                    await self._telegram.publish_text(recipe)
                    await self._telegram.publish_text(history)
                except Exception as exc:
                    logger.exception("Серия WorldFood не опубликована полностью: {}", exc)
                    raise RuntimeError(
                        f"WorldFood publication failed: {exc}"
                    ) from exc

                article.translated_title = editorial.dish_name
                self._database.save(
                    article,
                    "published",
                    aliases=(original_url,),
                    publication_mode=settings.run_mode,
                )
                published += 1
                logger.info(
                    "Опубликовано блюдо из источника [{}]: {} ({})",
                    article.source,
                    editorial.dish_name,
                    editorial.cuisine,
                )

            logger.info(
                "Итог worldfood_bot: блюд={}, локально отклонено={}, дубли={}, "
                "ошибки загрузки={}, RSS fallback={}, архивных URL={}, "
                "не страницы рецептов={}, мало текста={}, без фото={}, "
                "AI-проверок={}, отклонено AI={}",
                published,
                counters["local_filtered"],
                counters["duplicates"],
                counters["load_errors"],
                counters["feed_fallbacks"],
                counters["archive_candidates"],
                counters["not_recipe_page"],
                counters["insufficient_recipe"],
                counters["no_image"],
                counters["ai_attempts"],
                counters["ai_rejected"],
            )

            if published == 0:
                raise RuntimeError(
                    "WorldFood не нашёл новый источник-рецепт после проверки "
                    f"{len(candidates)} кандидатов. Редакционный резерв отключён."
                )
            return published
        finally:
            await self._telegram.close()
