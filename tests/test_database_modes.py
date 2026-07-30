from app.database import PublicationDatabase
from app.models import Article


def test_publication_modes_are_tracked_separately(tmp_path) -> None:
    database = PublicationDatabase(tmp_path / "newsflow2.db")

    manual_article = Article(
        source="MSI",
        title="MSI announces a new gaming monitor",
        url="https://example.com/manual",
    )
    scheduled_article = Article(
        source="ASUS",
        title="ASUS launches a new graphics card",
        url="https://example.com/scheduled",
    )

    database.save(manual_article, "published", publication_mode="manual")
    assert database.latest_published_at("manual") is not None
    assert database.latest_published_at("scheduled") is None

    database.save(scheduled_article, "published", publication_mode="scheduled")
    assert database.latest_published_at("scheduled") is not None
