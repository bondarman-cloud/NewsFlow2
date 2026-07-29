import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from app.models import Article


class PublicationDatabase:
    def __init__(self, path: Path) -> None:
        self._path = path
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self._path)
        connection.row_factory = sqlite3.Row
        return connection

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS published_articles (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    url TEXT NOT NULL UNIQUE,
                    source TEXT NOT NULL,
                    title TEXT NOT NULL,
                    article_published_at TEXT,
                    created_at TEXT NOT NULL
                )
                """
            )
            connection.commit()

    def exists(self, url: str) -> bool:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT 1 FROM published_articles WHERE url = ? LIMIT 1",
                (url,),
            ).fetchone()
        return row is not None

    def save(self, article: Article) -> None:
        now = datetime.now(timezone.utc).isoformat()
        article_time = article.published_at.isoformat() if article.published_at else None
        with self._connect() as connection:
            connection.execute(
                """
                INSERT OR IGNORE INTO published_articles
                    (url, source, title, article_published_at, created_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (article.url, article.source, article.title, article_time, now),
            )
            connection.commit()

    def latest_created_at(self) -> datetime | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT created_at FROM published_articles ORDER BY id DESC LIMIT 1"
            ).fetchone()
        if row is None:
            return None
        value = datetime.fromisoformat(row["created_at"])
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
