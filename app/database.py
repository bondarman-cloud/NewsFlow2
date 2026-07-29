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
                CREATE TABLE IF NOT EXISTS processed_articles (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    url TEXT NOT NULL UNIQUE,
                    status TEXT NOT NULL,
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
                "SELECT 1 FROM processed_articles WHERE url = ? LIMIT 1",
                (url,),
            ).fetchone()
        return row is not None

    def save(
        self,
        article: Article,
        status: str,
        aliases: tuple[str, ...] = (),
    ) -> None:
        urls = tuple(dict.fromkeys((article.url, *aliases)))
        now = datetime.now(timezone.utc).isoformat()
        article_time = article.published_at.isoformat() if article.published_at else None
        with self._connect() as connection:
            for url in urls:
                connection.execute(
                    """
                    INSERT OR IGNORE INTO processed_articles
                        (url, status, source, title, article_published_at, created_at)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (url, status, article.source, article.title, article_time, now),
                )
            connection.commit()

    def latest_published_at(self) -> datetime | None:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT created_at
                FROM processed_articles
                WHERE status = 'published'
                ORDER BY id DESC
                LIMIT 1
                """
            ).fetchone()
        if row is None:
            return None
        value = datetime.fromisoformat(row["created_at"])
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
