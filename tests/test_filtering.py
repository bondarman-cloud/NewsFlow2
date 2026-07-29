from app.filtering import HardwareNewsFilter
from app.models import Article


def test_accepts_hardware_launch() -> None:
    article = Article(
        source="ASUS",
        title="ASUS announces new ROG OLED gaming monitor",
        url="https://example.com/monitor",
    )
    assert HardwareNewsFilter().accepts(article)


def test_rejects_financial_news() -> None:
    article = Article(
        source="Acer",
        title="Acer reports quarterly revenue and financial results",
        url="https://example.com/revenue",
    )
    assert not HardwareNewsFilter().accepts(article)
