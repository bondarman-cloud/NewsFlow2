import json
import os

os.environ.setdefault("BOT_TOKEN", "test-token")
os.environ.setdefault("CHANNEL_ID", "-1000000000000")
os.environ.setdefault("GEMINI_API_KEY", "test-key")
os.environ.setdefault("BOT_ID", "hardware_news")

from app.models import Article  # noqa: E402
from app import worldfood  # noqa: E402
from app.worldfood import (  # noqa: E402
    GeminiRecipeEditor,
    WorldFoodFormatter,
    WorldFoodService,
)


def test_recipe_editor_parses_complete_recipe() -> None:
    payload = {
        "publish": True,
        "dish_name": "Хоровац",
        "cuisine": "армянская",
        "intro": "Армянское блюдо из мяса, приготовленного на углях.",
        "ingredients": ["1 кг свинины", "2 луковицы", "1 ч. л. соли"],
        "steps": ["Нарезать мясо.", "Обжарить на углях."],
        "history": "Хоровац занимает важное место в армянской застольной культуре.",
        "tags": ["армянская кухня", "гриль"],
        "reason": "",
    }

    result = GeminiRecipeEditor._parse(json.dumps(payload, ensure_ascii=False))

    assert result.publish is True
    assert result.dish_name == "Хоровац"
    assert result.cuisine == "армянская"
    assert len(result.ingredients) == 3
    assert len(result.steps) == 2
    assert result.reason == ""


def test_trusted_source_recipe_overrides_false_gate_when_complete() -> None:
    payload = {
        "publish": False,
        "dish_name": "Гхорме сабзи",
        "cuisine": "персидская",
        "intro": "Травяное рагу.",
        "ingredients": ["зелень", "мясо", "фасоль"],
        "steps": ["Обжарить зелень.", "Тушить с мясом и фасолью."],
        "history": "Блюдо широко распространено в иранской кухне.",
        "tags": ["персидская кухня"],
        "reason": "модель ошибочно решила отклонить",
    }

    result = GeminiRecipeEditor._parse(
        json.dumps(payload, ensure_ascii=False),
        trusted_source_recipe=True,
    )

    assert result.publish is True
    assert result.reason == ""


def test_recipe_editor_rejects_incomplete_recipe_with_reason() -> None:
    payload = {
        "publish": True,
        "dish_name": "Неизвестное блюдо",
        "cuisine": "",
        "ingredients": [],
        "steps": [],
        "history": "",
        "reason": "на странице нет полного рецепта",
    }

    result = GeminiRecipeEditor._parse(json.dumps(payload, ensure_ascii=False))

    assert result.publish is False
    assert result.reason == "на странице нет полного рецепта"


def test_worldfood_manual_mode_retries_non_published_candidates(monkeypatch) -> None:
    class FakeDatabase:
        retry_non_published: bool | None = None

        def is_duplicate(self, article, *, retry_non_published=False):
            self.retry_non_published = retry_non_published
            return False

    service = WorldFoodService.__new__(WorldFoodService)
    database = FakeDatabase()
    service._database = database
    monkeypatch.setattr(worldfood.settings, "force_publish", True)

    assert service._is_duplicate(Article(source="test", title="Recipe", url="https://x.test")) is False
    assert database.retry_non_published is True


def test_worldfood_formatter_builds_three_posts() -> None:
    result = GeminiRecipeEditor._parse(
        json.dumps(
            {
                "publish": True,
                "dish_name": "Манты",
                "cuisine": "турецкая",
                "intro": "Тесто с мясной начинкой.",
                "ingredients": ["500 г муки", "400 г фарша", "1 луковица"],
                "steps": ["Замесить тесто.", "Сформировать и приготовить манты."],
                "history": "Блюдо распространено в Турции и соседних регионах.",
                "tags": ["турецкая кухня"],
                "reason": "",
            },
            ensure_ascii=False,
        )
    )
    article = Article(
        source="Example Recipes",
        title="Turkish manti recipe",
        url="https://example.com/manti",
    )
    formatter = WorldFoodFormatter()

    caption = formatter.photo_caption(result, article)
    recipe = formatter.recipe_message(result)
    history = formatter.history_message(result, article)

    assert "Кухня" in caption
    assert "турецкая" in caption
    assert "Ингредиенты" in recipe
    assert "Приготовление" in recipe
    assert "Краткая история" in history
    assert "Источник рецепта" in history
