import sqlite3

from app.database import PublicationDatabase
from app.models import Article


def _article(title: str = "MSI launches a new gaming monitor") -> Article:
    return Article(
        source="MSI",
        title=title,
        url="https://example.com/news/monitor",
    )


def test_old_non_published_result_is_reprocessed(tmp_path) -> None:
    path = tmp_path / "newsflow.db"
    database = PublicationDatabase(path)
    article = _article()
    database.save(article, "filtered")

    with sqlite3.connect(path) as connection:
        connection.execute(
            "UPDATE processed_articles SET pipeline_version = 0 WHERE url = ?",
            (article.url,),
        )
        connection.commit()

    assert not database.is_duplicate(article)


def test_published_result_is_always_duplicate(tmp_path) -> None:
    database = PublicationDatabase(tmp_path / "newsflow.db")
    article = _article()
    database.save(article, "published")

    assert database.is_duplicate(article)


def test_published_status_is_not_downgraded(tmp_path) -> None:
    path = tmp_path / "newsflow.db"
    database = PublicationDatabase(path)
    article = _article()
    database.save(article, "published")
    database.save(article, "duplicate")

    with sqlite3.connect(path) as connection:
        status = connection.execute(
            "SELECT status FROM processed_articles WHERE url = ?",
            (article.url,),
        ).fetchone()[0]

    assert status == "published"


def test_old_filtered_result_can_be_upgraded_to_published(tmp_path) -> None:
    path = tmp_path / "newsflow.db"
    database = PublicationDatabase(path)
    article = _article()
    database.save(article, "filtered")
    database.save(article, "published")

    with sqlite3.connect(path) as connection:
        status = connection.execute(
            "SELECT status FROM processed_articles WHERE url = ?",
            (article.url,),
        ).fetchone()[0]

    assert status == "published"
