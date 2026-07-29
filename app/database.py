import re
import sqlite3
import unicodedata
from datetime import datetime, timezone
from difflib import SequenceMatcher
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

from app.models import Article


class PublicationDatabase:
    DUPLICATE_TITLE_THRESHOLD = 0.90

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
                    canonical_url TEXT,
                    title_key TEXT,
                    status TEXT NOT NULL,
                    source TEXT NOT NULL,
                    title TEXT NOT NULL,
                    article_published_at TEXT,
                    created_at TEXT NOT NULL
                )
                """
            )

            columns = {
                row["name"]
                for row in connection.execute("PRAGMA table_info(processed_articles)").fetchall()
            }
            if "canonical_url" not in columns:
                connection.execute("ALTER TABLE processed_articles ADD COLUMN canonical_url TEXT")
            if "title_key" not in columns:
                connection.execute("ALTER TABLE processed_articles ADD COLUMN title_key TEXT")

            rows = connection.execute(
                "SELECT id, url, title FROM processed_articles "
                "WHERE canonical_url IS NULL OR title_key IS NULL"
            ).fetchall()
            for row in rows:
                connection.execute(
                    "UPDATE processed_articles SET canonical_url = ?, title_key = ? WHERE id = ?",
                    (
                        self.canonical_url(row["url"]),
                        self.title_key(row["title"]),
                        row["id"],
                    ),
                )

            connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_processed_canonical_url "
                "ON processed_articles(canonical_url)"
            )
            connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_processed_title_status "
                "ON processed_articles(title_key, status)"
            )
            connection.commit()

    @staticmethod
    def canonical_url(url: str) -> str:
        value = url.strip()
        if not value:
            return value

        parts = urlsplit(value)
        host = parts.netloc.lower()
        path = re.sub(r"/{2,}", "/", parts.path).rstrip("/") or "/"

        # Google News adds locale parameters to the same article URL. They must not
        # turn one story into several database records.
        query = "" if "news.google." in host else parts.query
        return urlunsplit((parts.scheme.lower(), host, path, query, ""))

    @staticmethod
    def title_key(title: str) -> str:
        value = unicodedata.normalize("NFKC", title).lower().strip()
        # Google News commonly appends the publisher after the final dash.
        value = re.sub(r"\s+[-–—]\s+[^-–—]{2,50}$", "", value)
        value = re.sub(r"\b(the|a|an)\b", " ", value)
        value = re.sub(r"[^a-zа-яё0-9]+", " ", value, flags=re.IGNORECASE)
        return re.sub(r"\s+", " ", value).strip()

    def exists(self, url: str) -> bool:
        canonical = self.canonical_url(url)
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT 1
                FROM processed_articles
                WHERE url = ? OR canonical_url = ?
                LIMIT 1
                """,
                (url, canonical),
            ).fetchone()
        return row is not None

    def is_duplicate(self, article: Article) -> bool:
        canonical = self.canonical_url(article.url)
        key = self.title_key(article.title)

        with self._connect() as connection:
            exact = connection.execute(
                """
                SELECT 1
                FROM processed_articles
                WHERE url = ? OR canonical_url = ?
                   OR (status = 'published' AND title_key = ?)
                LIMIT 1
                """,
                (article.url, canonical, key),
            ).fetchone()
            if exact is not None:
                return True

            recent = connection.execute(
                """
                SELECT title_key
                FROM processed_articles
                WHERE status = 'published' AND title_key IS NOT NULL
                ORDER BY id DESC
                LIMIT 500
                """
            ).fetchall()

        if len(key) < 20:
            return False

        return any(
            SequenceMatcher(None, key, row["title_key"]).ratio()
            >= self.DUPLICATE_TITLE_THRESHOLD
            for row in recent
            if row["title_key"]
        )

    def save(
        self,
        article: Article,
        status: str,
        aliases: tuple[str, ...] = (),
    ) -> None:
        urls = tuple(dict.fromkeys((article.url, *aliases)))
        now = datetime.now(timezone.utc).isoformat()
        article_time = article.published_at.isoformat() if article.published_at else None
        key = self.title_key(article.title)

        with self._connect() as connection:
            for url in urls:
                connection.execute(
                    """
                    INSERT OR IGNORE INTO processed_articles
                        (url, canonical_url, title_key, status, source, title,
                         article_published_at, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        url,
                        self.canonical_url(url),
                        key,
                        status,
                        article.source,
                        article.title,
                        article_time,
                        now,
                    ),
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
