from __future__ import annotations

import importlib.util
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path


MODULE_PATH = Path(__file__).resolve().parents[1] / "skills" / "habr-digest" / "scripts" / "habr_digest.py"
spec = importlib.util.spec_from_file_location("habr_digest", MODULE_PATH)
assert spec is not None and spec.loader is not None
habr_digest = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = habr_digest
spec.loader.exec_module(habr_digest)


def sitemap_xml(entries: list[tuple[int, datetime]]) -> str:
    body = "".join(
        f"""
  <url>
    <loc>https://habr.com/ru/articles/{article_id}/</loc>
    <lastmod>{lastmod.isoformat()}</lastmod>
  </url>"""
        for article_id, lastmod in entries
    )
    return f"""<?xml version='1.0' encoding='UTF-8'?>
<urlset xmlns='http://www.sitemaps.org/schemas/sitemap/0.9'>{body}
</urlset>
"""


def test_fetch_candidates_overcollects_recent_article_ids_even_when_lastmod_is_old(monkeypatch):
    newest = 900_000
    now = datetime(2026, 6, 3, tzinfo=timezone.utc)
    old_lastmod = now - timedelta(days=90)
    fresh_lastmod = now
    xml = sitemap_xml(
        [
            (newest, fresh_lastmod),
            (newest - 10, old_lastmod),
            (newest - 20_000, fresh_lastmod),
        ]
    )
    monkeypatch.setattr(habr_digest, "request_text", lambda url: xml)
    monkeypatch.setattr(habr_digest, "MIN_ARTICLE_ID_LOOKBACK", 1500)
    monkeypatch.setattr(habr_digest, "MAX_ARTICLE_ID_LOOKBACK", 1500)
    monkeypatch.setattr(habr_digest, "ARTICLE_IDS_PER_DAY_LOOKBACK", 1)

    candidates = habr_digest.fetch_candidates(now - timedelta(days=7))
    ids = [item.article_id for item in candidates]

    assert str(newest) in ids
    assert str(newest - 10) in ids, "recent article IDs must not be lost because sitemap lastmod is old"
    assert str(newest - 20_000) not in ids, "ancient article IDs should stay outside the over-collection range"


def test_fetch_candidates_scans_above_stale_sitemap_max_id(monkeypatch):
    sitemap_max = 900_000
    now = datetime(2026, 6, 4, tzinfo=timezone.utc)
    xml = sitemap_xml(
        [
            (sitemap_max, now - timedelta(days=1)),
            (sitemap_max - 3, now - timedelta(days=90)),
        ]
    )
    monkeypatch.setattr(habr_digest, "request_text", lambda url: xml)
    monkeypatch.setattr(habr_digest, "MIN_ARTICLE_ID_LOOKBACK", 3)
    monkeypatch.setattr(habr_digest, "MAX_ARTICLE_ID_LOOKBACK", 3)
    monkeypatch.setattr(habr_digest, "ARTICLE_IDS_PER_DAY_LOOKBACK", 1)
    monkeypatch.setattr(habr_digest, "DIRECT_ARTICLE_ID_AHEAD", 4)

    candidates = habr_digest.fetch_candidates(now - timedelta(days=1))
    ids = [item.article_id for item in candidates]

    assert str(sitemap_max + 4) in ids
    assert str(sitemap_max + 1) in ids
    assert str(sitemap_max) in ids
    assert str(sitemap_max - 3) in ids


def test_select_digest_fails_when_main_window_has_fewer_than_five_articles(monkeypatch):
    now_msk = datetime(2026, 6, 3, 7, 0, tzinfo=habr_digest.MSK)
    article = habr_digest.Article(
        article_id="900000",
        title="Only one",
        description="",
        published_msk=now_msk - timedelta(hours=1),
        views=100,
        score=1,
        comments=0,
    )
    monkeypatch.setattr(habr_digest, "fetch_candidates", lambda fetch_start_utc: [habr_digest.Candidate("900000", now_msk)])
    monkeypatch.setattr(habr_digest, "fetch_articles", lambda candidates: [article])

    try:
        habr_digest.select_digest("daily", now_msk)
    except RuntimeError as exc:
        assert "fewer than 5" in str(exc)
    else:
        raise AssertionError("select_digest must fail instead of rendering a one-item top block")
