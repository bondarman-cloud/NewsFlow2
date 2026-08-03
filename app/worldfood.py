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
                    result = self._parse(self._extract_text(response.json()))
                    logger.info("Gemini подготовил рецепт через {}", model)
                    return result
                except (httpx.HTTPError, KeyError, ValueError, TypeError) as exc:
                    last_error = exc
                    logger.warning("Ошибка Gemini {}: {}", model, exc)

        raise RuntimeError(f"Все модели Gemini недоступны: {last_error}")

    @staticmethod
    def _extract_text(payload: dict) -> str:
        parts = payload["candidates"][0]["content"]["parts"]
        return "".join(str(part.get("text", "")) for part in parts).strip()

    @classmethod
    def _parse(cls, text: str) -> RecipeEditorialResult:
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
        publish = bool(data.get("publish", False))
        if not dish_name or not cuisine or not ingredients or not steps or not history:
            publish = False
            if not reason:
                reason = "ответ не содержит полного названия, кухни, ингредиентов, шагов или истории"

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
        content = (article.content or article.rss_summary or article.title)[:18_000]
        return (
            template.replace("{{BOT_TITLE}}", settings.title)
            .replace("{{SOURCE}}", article.source)
            .replace("{{URL}}", article.url)
            .replace("{{TITLE}}", article.title)
            .replace("{{CONTENT}}", content)
            .strip()
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
        caption += f"\n\n🔗 <a href=\"{url}\">Источник: {source}</a>"
        return caption

    def recipe_message(self, result: RecipeEditorialResult) -> str:
        dish = html.escape(self._short(result.dish_name, 120))
        ingredients = "\n".join(
            f"• {html.escape(self._short(item, 110))}"
            for item in result.ingredients[:16]
        )
        steps = "\n\n".join(
            f"{index}. {html.escape(self._short(step, 190))}"
            for index, step in enumerate(result.steps[:11], start=1)
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
        footer = f"\n\n🔗 <a href=\"{url}\">Источник рецепта: {source}</a>"
        if tags:
            footer += f"\n\n{tags}"
        return f"📜 <b>Краткая история: {dish}</b>\n\n{history}{footer}"


class WorldFoodService:
    MAX_AI_ATTEMPTS = 20
    MAX_CANDIDATES_PER_SOURCE = 2
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
            logger.info("Ручной WorldFood: интервал и недавние неудачные проверки игнорируются")
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
            "insufficient_recipe": 0,
            "no_image": 0,
            "ai_attempts": 0,
            "ai_rejected": 0,
        }

        try:
            logger.info("Запуск {} в режиме {}", settings.bot_id, settings.run_mode)
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
            candidates = self._diversify(eligible)
            logger.info(
                "Кандидатов на рецепт: {} из {} свежих; локально отклонено={}",
                len(candidates),
                len(articles),
                counters["local_filtered"],
            )

            for article in candidates:
                if published >= settings.max_articles_per_run:
                    break
                if counters["ai_attempts"] >= self.MAX_AI_ATTEMPTS:
                    logger.info("Достигнут лимит AI-проверок WorldFood: {}", self.MAX_AI_ATTEMPTS)
                    break

                original_url = article.url
                if self._is_duplicate(article):
                    counters["duplicates"] += 1
                    logger.info(
                        "WorldFood пропускает уже опубликованный или недавно проверенный материал: "
                        "[{}] {}",
                        article.source,
                        article.title,
                    )
                    continue

                logger.info("WorldFood проверяет [{}]: {}", article.source, article.title)
                try:
                    article = await self._loader.load(article)
                except Exception as exc:
                    counters["load_errors"] += 1
                    logger.warning("Страница рецепта не загружена {}: {}", original_url, exc)
                    continue

                if article.used_feed_fallback:
                    counters["feed_fallbacks"] += 1

                if self._is_duplicate(article):
                    counters["duplicates"] += 1
                    logger.info(
                        "WorldFood обнаружил дубль после раскрытия URL: [{}] {}",
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
                        "WorldFood отклонил [{}] {}: текста недостаточно для честного рецепта "
                        "({} символов, нужно минимум {})",
                        article.source,
                        article.title,
                        content_length,
                        minimum_chars,
                    )
                    continue

                article.image_path = await self._images.download(article.image_url, article.url)
                if article.image_path is None:
                    counters["no_image"] += 1
                    self._database.save(article, "no_image", aliases=(original_url,))
                    logger.info(
                        "WorldFood отклонил [{}] {}: фотография готового блюда недоступна",
                        article.source,
                        article.title,
                    )
                    continue

                counters["ai_attempts"] += 1
                editorial = await self._editor.process(article)
                if not editorial.publish:
                    counters["ai_rejected"] += 1
                    self._database.save(article, "ai_rejected", aliases=(original_url,))
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
                    raise RuntimeError(f"WorldFood publication failed: {exc}") from exc

                article.translated_title = editorial.dish_name
                self._database.save(
                    article,
                    "published",
                    aliases=(original_url,),
                    publication_mode=settings.run_mode,
                )
                published += 1
                logger.info(
                    "Опубликовано блюдо [{}]: {} ({})",
                    settings.run_mode,
                    editorial.dish_name,
                    editorial.cuisine,
                )

            logger.info(
                "Итог worldfood_bot: блюд={}, локально отклонено={}, дубли={}, "
                "ошибки загрузки={}, RSS fallback={}, мало текста={}, без фото={}, "
                "AI-проверок={}, отклонено AI={}",
                published,
                counters["local_filtered"],
                counters["duplicates"],
                counters["load_errors"],
                counters["feed_fallbacks"],
                counters["insufficient_recipe"],
                counters["no_image"],
                counters["ai_attempts"],
                counters["ai_rejected"],
            )
            return published
        finally:
            await self._telegram.close()
