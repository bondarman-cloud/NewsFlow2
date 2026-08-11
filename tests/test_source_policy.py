from pathlib import Path

from app.source_policy import OfficialSourcePolicy


def test_extracts_official_domains_from_google_news_queries(tmp_path: Path) -> None:
    sources = tmp_path / "sources.yaml"
    sources.write_text(
        """
sources:
  - name: ASUS
    url: "https://news.google.com/rss/search?q=site%3Apress.asus.com+launches"
  - name: Corsair
    url: "https://news.google.com/rss/search?q=site%3Acorsair.com+announces"
""".strip(),
        encoding="utf-8",
    )

    policy = OfficialSourcePolicy(sources)

    assert policy.canonical_source("https://press.asus.com/news/example") == "ASUS"
    assert policy.canonical_source("https://www.corsair.com/news/example") == "Corsair"


def test_rejects_secondary_media_domains(tmp_path: Path) -> None:
    sources = tmp_path / "sources.yaml"
    sources.write_text(
        """
sources:
  - name: NVIDIA
    url: "https://news.google.com/rss/search?q=site%3Anvidia.com+announces"
""".strip(),
        encoding="utf-8",
    )

    policy = OfficialSourcePolicy(sources)

    assert policy.is_official("https://www.nvidia.com/en-us/geforce/news/example")
    assert not policy.is_official("https://www.techpowerup.com/12345/example")
    assert not policy.is_official("https://videocardz.com/newz/example")
    assert not policy.is_official("https://www.tomshardware.com/pc-components/example")


def test_explicit_domains_are_supported(tmp_path: Path) -> None:
    sources = tmp_path / "sources.yaml"
    sources.write_text(
        """
sources:
  - name: Example Vendor
    url: "https://feeds.example.net/vendor.xml"
    domains:
      - example.com
      - press.example.com
""".strip(),
        encoding="utf-8",
    )

    policy = OfficialSourcePolicy(sources)

    assert policy.canonical_source("https://shop.example.com/products/new") == "Example Vendor"
    assert policy.canonical_source("https://press.example.com/release") == "Example Vendor"
    assert policy.canonical_source("https://example.org/story") is None
