import asyncio
import hashlib
from io import BytesIO
from pathlib import Path
from urllib.parse import urlparse

import httpx
from PIL import Image, ImageOps, UnidentifiedImageError

from app.config import settings
from app.logger import logger


class ImageService:
    HEADERS = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/131.0 Safari/537.36"
        ),
        "Accept": "image/avif,image/webp,image/apng,image/svg+xml,image/*,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
    }
    RETRYABLE_STATUS_CODES = {403, 408, 425, 429, 500, 502, 503, 504}

    def __init__(self) -> None:
        settings.image_cache_dir.mkdir(parents=True, exist_ok=True)

    async def download(self, image_url: str | None, referer: str) -> Path | None:
        if not image_url:
            return None

        response = await self._fetch_image(image_url, referer)
        if response is None:
            return None

        content_type = response.headers.get("content-type", "").lower()
        if content_type and not content_type.startswith("image/"):
            logger.info("Отклонён не-графический ответ {}: {}", image_url, content_type)
            return None
        if len(response.content) < 5_000 or len(response.content) > 20_000_000:
            logger.info("Отклонён размер изображения {}: {} байт", image_url, len(response.content))
            return None

        digest = hashlib.sha256(image_url.encode("utf-8")).hexdigest()[:24]
        destination = settings.image_cache_dir / f"{digest}.jpg"
        try:
            with Image.open(BytesIO(response.content)) as source:
                image = ImageOps.exif_transpose(source)
                image.thumbnail((2560, 2560), Image.Resampling.LANCZOS)
                if image.mode not in ("RGB", "L"):
                    background = Image.new("RGB", image.size, "white")
                    if "A" in image.getbands():
                        background.paste(image, mask=image.getchannel("A"))
                    else:
                        background.paste(image.convert("RGB"))
                    image = background
                elif image.mode == "L":
                    image = image.convert("RGB")
                image.save(destination, format="JPEG", quality=90, optimize=True)
        except (UnidentifiedImageError, OSError, ValueError) as exc:
            logger.info("Не удалось подготовить изображение {}: {}", image_url, exc)
            return None

        if destination.stat().st_size < 5_000:
            destination.unlink(missing_ok=True)
            return None
        logger.info("Изображение готово: {}", destination)
        return destination

    async def _fetch_image(self, image_url: str, referer: str) -> httpx.Response | None:
        article_host = urlparse(referer).netloc
        origin_referer = f"https://{article_host}/" if article_host else referer
        header_variants = (
            {**self.HEADERS, "Referer": referer},
            {**self.HEADERS, "Referer": origin_referer},
            self.HEADERS,
        )
        last_error: httpx.HTTPError | None = None

        async with httpx.AsyncClient(
            timeout=httpx.Timeout(30.0),
            follow_redirects=True,
        ) as client:
            for attempt, headers in enumerate(header_variants, start=1):
                try:
                    response = await client.get(image_url, headers=headers)
                    response.raise_for_status()
                    return response
                except httpx.HTTPError as exc:
                    last_error = exc
                    status = exc.response.status_code if isinstance(exc, httpx.HTTPStatusError) else None
                    if status not in self.RETRYABLE_STATUS_CODES or attempt == len(header_variants):
                        break
                    logger.info(
                        "Повтор загрузки изображения {}/{} после HTTP {}: {}",
                        attempt + 1,
                        len(header_variants),
                        status,
                        image_url,
                    )
                    await asyncio.sleep(attempt)

        logger.info("Изображение не скачано {}: {}", image_url, last_error)
        return None
