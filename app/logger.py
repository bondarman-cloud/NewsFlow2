import sys

from loguru import logger

from app.config import settings


logger.remove()
logger.add(
    sys.stderr,
    level=settings.log_level.upper(),
    format="{time:YYYY-MM-DD HH:mm:ss} | {level:<8} | {name}:{function}:{line} - {message}",
)
