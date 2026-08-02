import asyncio
import base64
import json
import re
from dataclasses import dataclass

import httpx
from PIL import Image

from app.config import settings
from app.logger import logger
from app.models import Article


@dataclass(slots=True)
class EditorialResult:
    publish: bool
    title: str
    summary: str
    tags: list[str]


class GeminiEditor:
    MODELS = (
        "gemini-3.5-flash-lite",
        "gemini-3.6-flash",
        "gemini-flash-latest",
        "gemini-3.1-flash-lite",
    )
    MAX_INLINE_IMAGE_BYTES = 8_000_000
    RETRY_DELAYS = (0, 3, 10)
    RETRYABLE_STATUS_CODES = {429, 500, 502, 503, 504}

    async def process(self, article: Article) -> EditorialResult:
        prompt = self._prompt(article)
        last_error: Exception | None = None
        text_parts: list[dict] = [{"text": prompt}]
        parts: list[dict] = list(text_parts)

        if article.image_path and article.image_path.exists():
            image_bytes = article.image_path.read_bytes()
            if len(image_bytes) <= self.MAX_INLINE_IMAGE_BYTES:
                parts.append(
                    {
                        "inlineData": {
                            "mimeType": self._image_mime_type(article.image_path),
                            "data": base64.b64encode(image_bytes).decode("ascii"),
                        }
                    }
                )
            else:
                logger.warning(
                    "Изображение слишком большое для проверки Gemini: {} байт",
                    len(image_bytes),
                )

        variants = [parts]
        if len(parts) > len(text_parts):
            # A malformed or unsupported image must not block the entire publication.
            variants.append(text_parts)

        async with httpx.AsyncClient(timeout=httpx.Timeout(75.0)) as client:
            for model in self.MODELS:
                for variant_index, current_parts in enumerate(variants):
                    using_image = len(current_parts) > len(text_parts)

                    for attempt, delay in enumerate(self.RETRY_DELAYS, start=1):
                        if delay:
                            await asyncio.sleep(delay)

                        url = (
                            "https://generativelanguage.googleapis.com/v1beta/models/"
                            f"{model}:generateContent?key={settings.gemini_api_key}"
                        )
                        payload = {
                            "contents": [{"parts": current_parts}],
                            "generationConfig": {
                                "thinkingConfig": {"thinkingLevel": "minimal"},
                                "responseMimeType": "application/json",
                            },
                        }

                        try:
                            response = await client.post(url, json=payload)

                            if response.status_code in self.RETRYABLE_STATUS_CODES:
                                last_error = RuntimeError(
                                    f"Gemini {model} HTTP {response.status_code}"
                                )
                                logger.warning(
                                    "Gemini {} вернул HTTP {} (попытка {}/{}): {}",
                                    model,
                                    response.status_code,
                                    attempt,
                                    len(self.RETRY_DELAYS),
                                    response.text[:300],
                                )
                                if attempt < len(self.RETRY_DELAYS):
                                    continue
                                break

                            if response.status_code in {400, 404}:
                                last_error = RuntimeError(
                                    f"Gemini {model} HTTP {response.status_code}"
                                )
                                logger.warning(
                                    "Gemini {} вернул HTTP {}{}: {}",
                                    model,
                                    response.status_code,
                                    " с изображением" if using_image else "",
                                    response.text[:300],
                                )
                                break

                            response.raise_for_status()
                            text = self._extract_text(response.json())
                            result = self._parse(text)
                            logger.info(
                                "Gemini обработал статью для {} через {}{}",
                                settings.bot_id,
                                model,
                                " без изображения" if variant_index else "",
                            )
                            return result
                        except (httpx.HTTPError, KeyError, ValueError, TypeError) as exc:
                            last_error = exc
                            logger.warning(
                                "Ошибка Gemini {} (попытка {}/{}): {}",
                                model,
                                attempt,
                                len(self.RETRY_DELAYS),
                                exc,
                            )
                            if attempt < len(self.RETRY_DELAYS):
                                continue
                            break

        raise RuntimeError(f"Все модели Gemini недоступны: {last_error}")

    @staticmethod
    def _image_mime_type(path) -> str:
        try:
            with Image.open(path) as image:
                return Image.MIME.get(image.format, "image/jpeg")
        except OSError:
            return "image/jpeg"

    @staticmethod
    def _extract_text(payload: dict) -> str:
        parts = payload["candidates"][0]["content"]["parts"]
        return "".join(str(part.get("text", "")) for part in parts).strip()

    @staticmethod
    def _parse(text: str) -> EditorialResult:
        cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", text.strip(), flags=re.I | re.S)
        start = cleaned.find("{")
        end = cleaned.rfind("}")
        if start < 0 or end < start:
            raise ValueError("Gemini не вернул JSON")
        data = json.loads(cleaned[start : end + 1])
        return EditorialResult(
            publish=bool(data.get("publish", False)),
            title=str(data.get("title", "")).strip(),
            summary=str(data.get("summary", "")).strip(),
            tags=[str(tag).strip() for tag in data.get("tags", []) if str(tag).strip()],
        )

    @staticmethod
    def _prompt(article: Article) -> str:
        template = settings.prompt_path.read_text(encoding="utf-8")
        content = (article.content or article.rss_summary or article.title)[:12_000]
        return (
            template.replace("{{BOT_TITLE}}", settings.title)
            .replace("{{SOURCE}}", article.source)
            .replace("{{TITLE}}", article.title)
            .replace("{{CONTENT}}", content)
            .strip()
        )
