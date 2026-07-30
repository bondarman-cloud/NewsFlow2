from pathlib import Path

from aiogram import Bot
from aiogram.types import FSInputFile

from app.config import settings


class TelegramPublisher:
    def __init__(self) -> None:
        self._bot = Bot(token=settings.bot_token)

    async def publish(self, text: str, image_path: Path | None = None) -> None:
        if image_path is None:
            await self._bot.send_message(
                chat_id=settings.channel_id,
                text=text,
                parse_mode="HTML",
            )
            return

        if not image_path.exists():
            raise RuntimeError(f"Файл изображения не найден: {image_path}")
        await self._bot.send_photo(
            chat_id=settings.channel_id,
            photo=FSInputFile(image_path, filename=image_path.name),
            caption=text,
            parse_mode="HTML",
        )

    async def close(self) -> None:
        await self._bot.session.close()
