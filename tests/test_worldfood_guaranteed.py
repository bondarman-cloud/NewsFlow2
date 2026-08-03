import os
from datetime import datetime, timezone

os.environ.setdefault("BOT_TOKEN", "test-token")
os.environ.setdefault("CHANNEL_ID", "-1000000000000")
os.environ.setdefault("GEMINI_API_KEY", "test-key")
os.environ.setdefault("BOT_ID", "hardware_news")

from app.config import settings  # noqa: E402
from app.models import Article  # noqa: E402
from app.worldfood_guaranteed import (  # noqa: E402
    FallbackWorldFoodFormatter,
    create_fallback_cover,
    select_fallback_recipe,
)


def test_fallback_recipe_is_complete() -> None:
    recipe = select_fallback_recipe(datetime(2026, 8, 3, 13, tzinfo=timezone.utc))

    assert recipe.publish is True
    assert recipe.dish_name
    assert recipe.cuisine
    assert len(recipe.ingredients) >= 5
    assert len(recipe.steps) >= 4
    assert recipe.history


def test_fallback_cover_is_created(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(settings, "image_cache_dir", tmp_path)
    recipe = select_fallback_recipe(datetime(2026, 8, 3, 13, tzinfo=timezone.utc))

    path = create_fallback_cover(recipe)

    assert path.exists()
    assert path.suffix == ".jpg"
    assert path.stat().st_size > 5_000


def test_fallback_formatter_has_no_broken_source_link() -> None:
    recipe = select_fallback_recipe(datetime(2026, 8, 3, 13, tzinfo=timezone.utc))
    article = Article(
        source="Редакционный резерв WorldFood",
        title=recipe.dish_name,
        url="fallback://worldfood/test",
    )
    formatter = FallbackWorldFoodFormatter()

    caption = formatter.photo_caption(recipe, article)
    history = formatter.history_message(recipe, article)

    assert "href=" not in caption
    assert "href=" not in history
    assert "Редакционный резервный рецепт" in caption
    assert "Подготовлено редакцией WorldFood" in history
