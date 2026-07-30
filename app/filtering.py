import re

from app.models import Article


class HardwareNewsFilter:
    PRODUCT_KEYWORDS = {
        "graphics card", "gpu", "geforce", "radeon", "motherboard", "mainboard",
        "processor", "cpu", "ryzen", "core ultra", "laptop", "notebook",
        "gaming pc", "desktop", "mini pc", "workstation", "monitor", "display",
        "oled", "qd-oled", "mini-led", "keyboard", "mouse", "headset",
        "headphones", "earbuds", "microphone", "webcam", "controller", "gamepad",
        "ssd", "solid state", "nvme", "m.2", "pcie 5.0", "pcie gen5", "pcie 4.0",
        "external ssd", "portable ssd", "hard drive", "hdd", "storage", "flash drive",
        "nand", "3d nand", "memory", "memory kit", "dram", "ddr5", "ddr6",
        "udimm", "u-dimm", "sodimm", "so-dimm", "cudimm", "cu-dimm", "rdimm",
        "power supply", "psu", "computer case", "pc case", "chassis", "cpu cooler",
        "liquid cooler", "aio cooler", "cooling fan", "router", "wi-fi 7", "wifi 7",
        "dock", "docking station", "capture card", "gaming handheld", "handheld pc",
        "gaming monitor", "gaming laptop", "graphics", "pc hardware", "peripheral",
        "ssd controller", "storage controller",
    }

    RELEASE_KEYWORDS = {
        "announce", "announces", "announced", "unveil", "unveils", "unveiled",
        "launch", "launches", "launched", "introduce", "introduces", "introduced",
        "release", "releases", "released", "availability", "available", "debuts",
        "debut", "reveals", "revealed", "ships", "shipping", "pre-order", "preorder",
        "new", "latest", "showcase", "showcases", "showcased", "demo", "demos",
        "demonstrates", "expands", "expanded", "adds", "added", "presents",
        "presented", "rolls out", "now available", "starts shipping", "brings",
        "refreshes", "upgrades", "first look",
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
        "cloud gaming", "login", "explore:", "celebration", "win rtx",
        "market share", "shipment milestone", "ships globally", "certification",
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

    def priority(self, article: Article) -> int:
        title = self._normalize(article.title)
        text = self._normalize(f"{article.title} {article.rss_summary}")
        if any(term in text for term in self.EXCLUDED_KEYWORDS):
            return -10_000

        product_hits = sum(term in text for term in self.PRODUCT_KEYWORDS)
        release_hits = sum(term in text for term in self.RELEASE_KEYWORDS)
        title_release_hits = sum(term in title for term in self.RELEASE_KEYWORDS)
        model_like = bool(re.search(r"\b[A-Z]{1,6}[- ]?\d{2,5}[A-Z0-9-]*\b", article.title))
        storage_bonus = sum(
            term in text
            for term in ("ssd", "nvme", "hard drive", "hdd", "ddr5", "memory kit", "dram")
        )

        return (
            product_hits * 4
            + release_hits * 5
            + title_release_hits * 4
            + storage_bonus * 3
            + (3 if model_like else 0)
        )
