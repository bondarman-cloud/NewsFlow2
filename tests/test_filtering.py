from app.filtering import HardwareNewsFilter
from app.models import Article


def test_accepts_hardware_launch() -> None:
    article = Article(
        source="ASUS",
        title="ASUS announces new ROG OLED gaming monitor",
        url="https://example.com/monitor",
    )
    assert HardwareNewsFilter().accepts(article)


def test_accepts_ddr5_showcase() -> None:
    article = Article(
        source="G.SKILL",
        title="G.SKILL showcases new DDR5-10000 memory kit",
        url="https://example.com/ddr5",
    )
    assert HardwareNewsFilter().accepts(article)


def test_accepts_nvme_storage_launch() -> None:
    article = Article(
        source="TEAMGROUP",
        title="TEAMGROUP launches NV10000 M.2 PCIe 5.0 SSD",
        url="https://example.com/ssd",
    )
    assert HardwareNewsFilter().accepts(article)


def test_rejects_financial_news() -> None:
    article = Article(
        source="Acer",
        title="Acer reports quarterly revenue and financial results",
        url="https://example.com/revenue",
    )
    assert not HardwareNewsFilter().accepts(article)


def test_rejects_memory_award() -> None:
    article = Article(
        source="G.SKILL",
        title="G.SKILL DDR5 memory receives hardware award",
        url="https://example.com/award",
    )
    assert not HardwareNewsFilter().accepts(article)
