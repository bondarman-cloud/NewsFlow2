from bs4 import BeautifulSoup

from app.article_loader import ArticleLoader
from app.sources import SourceManager


def test_extracts_schema_org_recipe() -> None:
    html = '''
    <html><head>
    <script type="application/ld+json">
    {
      "@context": "https://schema.org",
      "@type": "Recipe",
      "name": "Ghormeh Sabzi",
      "recipeCuisine": "Persian",
      "image": "https://example.com/ghormeh.jpg",
      "recipeIngredient": ["500 g herbs", "300 g beef", "100 g beans"],
      "recipeInstructions": [
        {"@type": "HowToStep", "text": "Fry the herbs."},
        {"@type": "HowToStep", "text": "Simmer with beef and beans."}
      ]
    }
    </script>
    </head></html>
    '''
    recipe = ArticleLoader()._extract_structured_recipe(
        BeautifulSoup(html, "html.parser")
    )

    assert recipe is not None
    assert recipe["name"] == "Ghormeh Sabzi"
    assert recipe["cuisine"] == "Persian"
    assert len(recipe["ingredients"]) == 3
    assert len(recipe["instructions"]) == 2


def test_archive_url_filter_rejects_news_and_accepts_recipe_slug() -> None:
    assert not SourceManager._likely_recipe_url(
        "https://example.com/news/summit-menu/"
    )
    assert SourceManager._likely_recipe_url(
        "https://example.com/ghormeh-sabzi/"
    )


def test_sitemap_children_prefer_post_and_recipe_maps() -> None:
    selected = SourceManager._select_sitemap_children(
        [
            "https://example.com/category-sitemap.xml",
            "https://example.com/page-sitemap.xml",
            "https://example.com/post-sitemap.xml",
            "https://example.com/recipe-sitemap.xml",
        ]
    )

    assert selected[:2] == [
        "https://example.com/post-sitemap.xml",
        "https://example.com/recipe-sitemap.xml",
    ]
