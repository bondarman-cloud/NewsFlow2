import re
from typing import Protocol

from app.models import Article


class ArticleFilter(Protocol):
    def accepts(self, article: Article) -> bool: ...

    def priority(self, article: Article) -> int: ...


class HardwareNewsFilter:
    PRODUCT_KEYWORDS = {
        "graphics card", "gpu", "geforce", "radeon", "motherboard", "mainboard",
        "processor", "cpu", "ryzen", "core ultra", "gaming pc", "desktop", "mini pc",
        "workstation", "monitor", "display", "oled", "qd-oled", "mini-led", "keyboard",
        "mouse", "headset", "headphones", "earbuds", "microphone", "webcam",
        "controller", "gamepad", "ssd", "solid state", "nvme", "m.2", "pcie 5.0",
        "pcie gen5", "pcie 4.0", "external ssd", "portable ssd", "hard drive", "hdd",
        "storage", "flash drive", "nand", "3d nand", "memory", "memory kit", "dram",
        "ddr5", "ddr6", "udimm", "u-dimm", "sodimm", "so-dimm", "cudimm",
        "cu-dimm", "rdimm", "power supply", "psu", "computer case", "pc case",
        "chassis", "cpu cooler", "liquid cooler", "aio cooler", "cooling fan", "router",
        "wi-fi 7", "wifi 7", "dock", "docking station", "capture card",
        "gaming handheld", "handheld pc", "gaming monitor", "graphics", "pc hardware",
        "peripheral", "ssd controller", "storage controller", "thermal paste", "case fan",
    }

    LAPTOP_KEYWORDS = {
        "laptop", "gaming laptop", "notebook", "gaming notebook", "chromebook",
        "ultrabook", "mobile workstation", "laptop gpu", "laptop processor",
    }

    RELEASE_KEYWORDS = {
        "announce", "announces", "announced", "unveil", "unveils", "unveiled",
        "launch", "launches", "launched", "launching", "introduce", "introduces",
        "introduced", "release", "releases", "released", "availability", "available",
        "debuts", "debut", "reveals", "revealed", "ships", "shipping", "pre-order",
        "preorder", "new", "latest", "showcase", "showcases", "showcased", "demo",
        "demos", "demonstrates", "expands", "expanded", "adds", "added", "presents",
        "presented", "rolls out", "now available", "starts shipping", "brings",
        "refreshes", "upgrades", "first look", "arrives", "lands", "hits", "gets",
        "comes in", "available now", "up for pre-order", "goes on sale",
    }

    EXCLUDED_KEYWORDS = {
        "smartphone", "phone", "android tablet", "e-bike", "ebike", "scooter",
        "automotive", "vehicle", "server platform", "server motherboard", "servers powered",
        "data center", "datacenter", "enterprise ai", "ai factory", "healthcare",
        "medical", "earnings", "revenue", "financial results", "award", "awards",
        "partnership", "partners with", "sponsorship", "esports tournament", "giveaway",
        "promotion", "discount", "warehouse sale", "feedback thread", "support thread",
        "known issues", "supported operating systems", "software and driver downloads",
        "driver update", "bios update", "firmware update", "how to", "guide",
        "what is the", "how do", "best laptops", "search results for", "geforce now",
        "cloud gaming", "login", "explore:", "celebration", "win rtx", "review",
        "market share", "shipment milestone", "certification", "rumor", "rumour",
        "leak", "leaked", "benchmark leak", "concept product",
    }

    @staticmethod
    def _normalize(value: str) -> str:
        return re.sub(r"\s+", " ", value.lower()).strip()

    def accepts(self, article: Article) -> bool:
        text = self._normalize(f"{article.title} {article.rss_summary}")
        if any(term in text for term in self.LAPTOP_KEYWORDS):
            return False
        if any(term in text for term in self.EXCLUDED_KEYWORDS):
            return False
        return any(term in text for term in self.PRODUCT_KEYWORDS)

    def priority(self, article: Article) -> int:
        title = self._normalize(article.title)
        text = self._normalize(f"{article.title} {article.rss_summary}")
        if any(term in text for term in self.LAPTOP_KEYWORDS):
            return -10_000
        if any(term in text for term in self.EXCLUDED_KEYWORDS):
            return -10_000

        product_hits = sum(term in text for term in self.PRODUCT_KEYWORDS)
        release_hits = sum(term in text for term in self.RELEASE_KEYWORDS)
        title_release_hits = sum(term in title for term in self.RELEASE_KEYWORDS)
        model_like = bool(re.search(r"\b[A-Z]{1,6}[- ]?\d{2,5}[A-Z0-9-]*\b", article.title))
        storage_bonus = sum(
            term in text
            for term in (
                "ssd", "nvme", "hard drive", "hdd", "ddr5", "ddr6",
                "memory kit", "dram", "nand",
            )
        )

        return (
            product_hits * 4
            + release_hits * 5
            + title_release_hits * 4
            + storage_bonus * 4
            + (3 if model_like else 0)
        )


class TechNewsFilter:
    EXCLUDED_KEYWORDS = {
        "earnings", "revenue", "financial results", "stock price", "share price",
        "sponsorship", "giveaway", "discount", "promotion", "job opening", "hiring",
        "podcast", "webinar", "conference recap", "event recap", "weekly roundup",
        "how to", "tutorial", "beginner guide", "customer story", "case study",
        "award", "awards", "anniversary", "celebration",
    }
    PRIORITY_KEYWORDS = {
        "announce", "announces", "announced", "launch", "launches", "launched",
        "release", "releases", "released", "introduce", "introduces", "introduced",
        "open source", "api", "model", "security", "vulnerability", "database",
        "python", "linux", "github", "docker", "cloud", "browser", "developer",
        "artificial intelligence", "machine learning", "available now", "new",
    }

    @staticmethod
    def _normalize(value: str) -> str:
        return re.sub(r"\s+", " ", value.lower()).strip()

    def accepts(self, article: Article) -> bool:
        text = self._normalize(f"{article.title} {article.rss_summary}")
        return len(article.title.strip()) >= 12 and not any(
            term in text for term in self.EXCLUDED_KEYWORDS
        )

    def priority(self, article: Article) -> int:
        text = self._normalize(f"{article.title} {article.rss_summary}")
        if any(term in text for term in self.EXCLUDED_KEYWORDS):
            return -10_000
        hits = sum(term in text for term in self.PRIORITY_KEYWORDS)
        title_hits = sum(term in article.title.lower() for term in self.PRIORITY_KEYWORDS)
        return hits * 4 + title_hits * 3


class RecipeFilter:
    RECIPE_KEYWORDS = {
        "recipe", "ingredients", "instructions", "how to make", "traditional",
        "homemade", "dish", "soup", "stew", "curry", "bread", "salad", "dessert",
        "cake", "pastry", "noodles", "rice", "pasta", "dumplings", "roast", "grill",
        "sauce", "cookies", "pie", "breakfast", "dinner", "lunch", "appetizer",
    }
    CUISINE_KEYWORDS = {
        "armenian", "turkish", "georgian", "greek", "italian", "french", "spanish",
        "portuguese", "mexican", "brazilian", "peruvian", "argentinian", "uruguayan",
        "indian", "pakistani", "thai", "vietnamese", "chinese", "japanese", "korean",
        "indonesian", "malaysian", "lebanese", "syrian", "persian", "moroccan",
        "ethiopian", "nigerian", "german", "polish", "ukrainian", "russian",
    }
    EXCLUDED_KEYWORDS = {
        "roundup", "best recipes", "recipe collection", "meal plan", "restaurant review",
        "restaurant news", "celebrity", "giveaway", "sponsored", "product review",
        "kitchen gadget", "cookbook review", "weekly menu", "travel guide",
    }

    @staticmethod
    def _normalize(value: str) -> str:
        return re.sub(r"\s+", " ", value.lower()).strip()

    def accepts(self, article: Article) -> bool:
        text = self._normalize(f"{article.title} {article.rss_summary}")
        if len(article.title.strip()) < 5:
            return False
        return not any(term in text for term in self.EXCLUDED_KEYWORDS)

    def priority(self, article: Article) -> int:
        text = self._normalize(f"{article.title} {article.rss_summary}")
        if any(term in text for term in self.EXCLUDED_KEYWORDS):
            return -10_000
        recipe_hits = sum(term in text for term in self.RECIPE_KEYWORDS)
        cuisine_hits = sum(term in text for term in self.CUISINE_KEYWORDS)
        return recipe_hits * 4 + cuisine_hits * 6


def build_filter(filter_type: str) -> ArticleFilter:
    filters: dict[
        str,
        type[HardwareNewsFilter | TechNewsFilter | RecipeFilter],
    ] = {
        "hardware": HardwareNewsFilter,
        "tech": TechNewsFilter,
        "recipe": RecipeFilter,
    }
    try:
        return filters[filter_type]()
    except KeyError as exc:
        raise ValueError(f"Неизвестный тип фильтра: {filter_type!r}") from exc
