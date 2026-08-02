import base64
import json
import re
from dataclasses import dataclass

import httpx

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
        "gemini-3.1-flash-lite",
        "gemini-3.5-flash-lite",
        "gemini-flash-latest",
    )
    MAX_INLINE_IMAGE_BYTES = 8_000_000

    async def process(self, article: Article) -> EditorialResult:
        prompt = self._prompt(article)
        last_error: Exception | None = None
        parts: list[dict] = [{"text": prompt}]

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
            else:
                logger.warning(
                    "Изображение слишком большое для проверки Gemini: {} байт",
                    len(image_bytes),
                )

        async with httpx.AsyncClient(timeout=httpx.Timeout(60.0)) as client:
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
                        logger.warning(
                            "Gemini {} вернул HTTP {}: {}",
                            model,
                            response.status_code,
                            response.text[:300],
                        )
                        last_error = RuntimeError(
                            f"Gemini {model} HTTP {response.status_code}"
                        )
                        continue
                    response.raise_for_status()
                    text = self._extract_text(response.json())
                    result = self._parse(text)
                    logger.info(
                        "Gemini обработал статью для {} через {}",
                        settings.bot_id,
                        model,
                    )
                    return result
                except (httpx.HTTPError, KeyError, ValueError, TypeError) as exc:
                    last_error = exc
                    logger.warning("Ошибка Gemini {}: {}", model, exc)

        raise RuntimeError(f"Все модели Gemini недоступны: {last_error}")

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
