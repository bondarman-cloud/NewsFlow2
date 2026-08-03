from app.filtering import (
    HardwareNewsFilter,
    RecipeFilter,
    TechNewsFilter,
    build_filter,
)
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


def test_rejects_laptop_launch() -> None:
    article = Article(
        source="MSI",
        title="MSI launches gaming laptop with GeForce RTX graphics and NVMe SSD",
        url="https://example.com/laptop",
    )
    assert not HardwareNewsFilter().accepts(article)


def test_rejects_chromebook_launch() -> None:
    article = Article(
        source="Acer",
        title="Acer announces Chromebook with new processor and DDR5 memory",
        url="https://example.com/chromebook",
    )
    assert not HardwareNewsFilter().accepts(article)


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


def test_tech_filter_accepts_release() -> None:
    article = Article(
        source="GitHub Blog",
        title="GitHub releases a new security API for developers",
        url="https://example.com/api",
    )
    assert TechNewsFilter().accepts(article)
    assert TechNewsFilter().priority(article) > 0


def test_tech_filter_rejects_webinar() -> None:
    article = Article(
        source="Cloudflare",
        title="Join our webinar about cloud security",
        url="https://example.com/webinar",
    )
    assert not TechNewsFilter().accepts(article)


def test_recipe_filter_accepts_single_dish() -> None:
    article = Article(
        source="World Recipes",
        title="Traditional Armenian khorovats recipe",
        url="https://example.com/khorovats",
        rss_summary="Ingredients and instructions for grilled Armenian pork",
    )
    recipe_filter = RecipeFilter()
    assert recipe_filter.accepts(article)
    assert recipe_filter.priority(article) > 0


def test_recipe_filter_accepts_recipe_archive_entry() -> None:
    article = Article(
        source="Persian Mama",
        title="Ghormeh Sabzi",
        url="https://example.com/ghormeh-sabzi/",
        from_archive=True,
        is_recipe_source=True,
    )
    assert RecipeFilter().accepts(article)


def test_recipe_filter_rejects_roundup() -> None:
    article = Article(
        source="World Recipes",
        title="The 25 best recipes for this summer",
        url="https://example.com/roundup",
    )
    assert not RecipeFilter().accepts(article)


def test_recipe_filter_rejects_summit_menu_news() -> None:
    article = Article(
        source="Food Travel",
        title="The secret NATO summit menu unveiled",
        url="https://example.com/news/summit-menu/",
        is_recipe_source=True,
    )
    assert not RecipeFilter().accepts(article)


def test_filter_factory() -> None:
    assert isinstance(build_filter("hardware"), HardwareNewsFilter)
    assert isinstance(build_filter("tech"), TechNewsFilter)
    assert isinstance(build_filter("recipe"), RecipeFilter)
