import json
import os

os.environ.setdefault("BOT_TOKEN", "test-token")
os.environ.setdefault("CHANNEL_ID", "-1000000000000")
os.environ.setdefault("GEMINI_API_KEY", "test-key")
os.environ.setdefault("BOT_ID", "hardware_news")

from app.models import Article  # noqa: E402
from app.worldfood import GeminiRecipeEditor, WorldFoodFormatter  # noqa: E402


def test_recipe_editor_parses_complete_recipe() -> None:
    payload = {
        "publish": True,
        "dish_name": "Хоровац",
        "cuisine": "армянская",
        "intro": "Армянское блюдо из мяса, приготовленного на углях.",
        "ingredients": ["1 кг свинины", "2 луковицы"],
        "steps": ["Нарезать мясо.", "Обжарить на углях."],
        "history": "Хоровац занимает важное место в армянской застольной культуре.",
        "tags": ["армянская кухня", "гриль"],
    }

    result = GeminiRecipeEditor._parse(json.dumps(payload, ensure_ascii=False))

    assert result.publish is True
    assert result.dish_name == "Хоровац"
    assert result.cuisine == "армянская"
    assert len(result.ingredients) == 2
    assert len(result.steps) == 2


def test_recipe_editor_rejects_incomplete_recipe() -> None:
    payload = {
        "publish": True,
        "dish_name": "Неизвестное блюдо",
        "cuisine": "",
        "ingredients": [],
        "steps": [],
        "history": "",
    }

    result = GeminiRecipeEditor._parse(json.dumps(payload, ensure_ascii=False))

    assert result.publish is False


def test_worldfood_formatter_builds_three_posts() -> None:
    result = GeminiRecipeEditor._parse(
        json.dumps(
            {
                "publish": True,
                "dish_name": "Манты",
                "cuisine": "турецкая",
                "intro": "Тесто с мясной начинкой.",
                "ingredients": ["500 г муки", "400 г фарша"],
                "steps": ["Замесить тесто.", "Сформировать и приготовить манты."],
                "history": "Блюдо распространено в Турции и соседних регионах.",
                "tags": ["турецкая кухня"],
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
