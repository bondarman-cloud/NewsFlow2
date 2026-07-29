import re

from app.models import Article


class HardwareNewsFilter:
    PRODUCT_KEYWORDS = {
        "graphics card", "gpu", "geforce", "radeon", "motherboard", "mainboard",
        "processor", "cpu", "ryzen", "core ultra", "laptop", "notebook",
        "gaming pc", "desktop", "mini pc", "workstation", "monitor", "display",
        "oled", "qd-oled", "mini-led", "keyboard", "mouse", "headset",
        "headphones", "earbuds", "microphone", "webcam", "controller", "gamepad",
        "ssd", "solid state", "memory", "dram", "ddr5", "ddr6", "power supply",
        "psu", "computer case", "pc case", "chassis", "cpu cooler", "liquid cooler",
        "aio cooler", "cooling fan", "router", "wi-fi 7", "wifi 7", "dock",
        "docking station", "capture card", "gaming handheld", "handheld pc",
    }

    RELEASE_KEYWORDS = {
        "announce", "announces", "announced", "unveil", "unveils", "unveiled",
        "launch", "launches", "launched", "introduce", "introduces", "introduced",
        "release", "releases", "released", "availability", "available", "debuts",
        "reveals", "ships", "shipping", "pre-order", "preorder",
    }

    EXCLUDED_KEYWORDS = {
        "smartphone", "phone", "android tablet", "e-bike", "ebike", "scooter",
        "automotive", "vehicle", "server platform", "data center", "datacenter",
        "enterprise ai", "ai factory", "healthcare", "medical", "earnings", "revenue",
        "financial results", "award", "awards", "partnership", "partners with",
        "sponsorship", "esports tournament", "giveaway", "promotion", "discount",
        "bios update", "driver update", "firmware update", "how to", "guide",
    }

    @staticmethod
    def _normalize(value: str) -> str:
        return re.sub(r"\s+", " ", value.lower()).strip()

    def accepts(self, article: Article) -> bool:
        text = self._normalize(f"{article.title} {article.rss_summary}")
        if any(term in text for term in self.EXCLUDED_KEYWORDS):
            return False

        has_product = any(term in text for term in self.PRODUCT_KEYWORDS)
        has_release = any(term in text for term in self.RELEASE_KEYWORDS)
        return has_product and has_release
