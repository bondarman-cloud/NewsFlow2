import re
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import yaml


class OfficialSourcePolicy:
    SITE_PATTERN = re.compile(r"\bsite:([a-z0-9.-]+)", re.IGNORECASE)
    GOOGLE_NEWS_HOSTS = {"news.google.com", "www.news.google.com"}

    def __init__(self, sources_path: Path) -> None:
        data = yaml.safe_load(sources_path.read_text(encoding="utf-8")) or {}
        configured = data.get("sources", []) or []

        domains: dict[str, str] = {}
        for source in configured:
            if not isinstance(source, dict):
                continue
            name = str(source.get("name", "")).strip()
            if not name:
                continue

            explicit_domains = source.get("domains", []) or []
            if isinstance(explicit_domains, str):
                explicit_domains = [explicit_domains]

            discovered = {
                self._normalize_domain(str(value))
                for value in explicit_domains
                if str(value).strip()
            }
            discovered.update(self._domains_from_source_url(str(source.get("url", ""))))

            for domain in discovered:
                if domain:
                    domains.setdefault(domain, name)

        if not domains:
            raise ValueError(
                f"В {sources_path} не удалось определить официальные домены источников"
            )

        self._domains = domains

    @classmethod
    def _domains_from_source_url(cls, url: str) -> set[str]:
        if not url:
            return set()

        parsed = urlparse(url)
        host = cls._normalize_domain(parsed.hostname or "")
        domains: set[str] = set()

        query_values = parse_qs(parsed.query).get("q", [])
        search_text = " ".join(query_values)
        for match in cls.SITE_PATTERN.finditer(search_text):
            domain = cls._normalize_domain(match.group(1))
            if domain:
                domains.add(domain)

        if host and host not in cls.GOOGLE_NEWS_HOSTS:
            domains.add(host)

        return domains

    @staticmethod
    def _normalize_domain(value: str) -> str:
        domain = value.strip().lower().rstrip(".")
        if domain.startswith("www."):
            domain = domain[4:]
        return domain

    def canonical_source(self, url: str) -> str | None:
        host = self._normalize_domain(urlparse(url).hostname or "")
        if not host:
            return None

        matches = [
            (domain, source_name)
            for domain, source_name in self._domains.items()
            if host == domain or host.endswith(f".{domain}")
        ]
        if not matches:
            return None

        _, source_name = max(matches, key=lambda item: len(item[0]))
        return source_name

    def is_official(self, url: str) -> bool:
        return self.canonical_source(url) is not None
