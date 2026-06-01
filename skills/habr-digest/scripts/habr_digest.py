#!/usr/bin/env python3
"""Generate Habr top-by-views digests as stdout.

This script is intentionally generator-only: it fetches Habr data, ranks articles,
and prints one standard-Markdown message. Delivery is handled by Hermes cron /
gateway, not by this skill. That keeps Telegram credentials and targets in Hermes
configuration instead of the published community skill.
"""
from __future__ import annotations

import argparse
import html
import json
import re
import sys
import time
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Iterable

MSK = timezone(timedelta(hours=3))
SITEMAP_URL = "https://habr.com/sitemap_articles1.xml"
ARTICLE_API = "https://habr.com/kek/v2/articles/{article_id}/?fl=ru&hl=ru"
ARTICLE_URL = "https://habr.com/ru/articles/{article_id}/"
USER_AGENT = "Mozilla/5.0 (compatible; HermesHabrDigest/1.0)"
HTTP_TIMEOUT = 20
MAX_RETRIES = 4
WORKERS = 64
RETRY_WORKERS = 16
MESSAGE_LIMIT = 3900
SEP = "➖➖➖➖➖➖➖➖➖➖➖➖"
RANKS = ["1️⃣", "2️⃣", "3️⃣", "4️⃣", "5️⃣"]
NS = {"sm": "http://www.sitemaps.org/schemas/sitemap/0.9"}
ARTICLE_ID_RE = re.compile(r"/articles/(\d+)/?")


PERIODS = {
    "daily": {
        "kind": "📅 Daily",
        "period_word": "сутки",
        "summary_days": 1,
        "highlight_days": 7,
        "trend_label": "Тренд недели",
        "top_label": "Топ недели",
    },
    "weekly": {
        "kind": "📆 Weekly",
        "period_word": "неделю",
        "summary_days": 7,
        "highlight_days": 30,
        "trend_label": "Тренд месяца",
        "top_label": "Топ месяца",
    },
    "monthly": {
        "kind": "🗓 Monthly",
        "period_word": "месяц",
        "summary_days": 30,
        "highlight_days": None,
        "trend_label": None,
        "top_label": None,
    },
}


@dataclass(frozen=True)
class Candidate:
    article_id: str
    lastmod: datetime


@dataclass(frozen=True)
class Article:
    article_id: str
    title: str
    description: str
    published_msk: datetime
    views: int
    score: int
    comments: int

    @property
    def url(self) -> str:
        return ARTICLE_URL.format(article_id=self.article_id)


FETCH_FAILED = object()


def log(message: str) -> None:
    print(f"[habr-digest] {message}", file=sys.stderr, flush=True)


def parse_iso(value: str) -> datetime:
    dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def to_msk(value: str) -> datetime:
    return parse_iso(value).astimezone(MSK)


def request_bytes(url: str) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    last_error: BaseException | None = None
    for attempt in range(MAX_RETRIES):
        try:
            with urllib.request.urlopen(req, timeout=HTTP_TIMEOUT) as response:
                return response.read()
        except urllib.error.HTTPError as exc:
            if exc.code in (403, 404):
                raise
            last_error = exc
        except Exception as exc:  # noqa: BLE001 - retry transient network errors
            last_error = exc
        if attempt < MAX_RETRIES - 1:
            time.sleep((2**attempt) * 0.5)
    assert last_error is not None
    raise last_error


def request_text(url: str) -> str:
    return request_bytes(url).decode("utf-8", "replace")


def request_json(url: str) -> dict:
    data = json.loads(request_bytes(url).decode("utf-8"))
    if not isinstance(data, dict):
        raise RuntimeError(f"expected JSON object from {url}")
    return data


def strip_html(raw: str | None) -> str:
    if not raw:
        return ""
    text = re.sub(r"<[^>]+>", " ", raw)
    text = html.unescape(text)
    return re.sub(r"\s+", " ", text).strip()


def clip(text: str, limit: int) -> str:
    text = re.sub(r"\s+", " ", text).strip()
    if limit <= 0:
        return ""
    if len(text) <= limit:
        return text
    return text[: max(0, limit - 1)].rstrip(" ,.;:-") + "…"


def md_link_text(value: str) -> str:
    """Make text safe for a simple [text](url) Markdown link display part."""
    value = re.sub(r"\s+", " ", value).strip()
    # Hermes Telegram adapter handles escaping, but its link regex needs balanced
    # brackets in the display text. Preserve meaning without raw bracket syntax.
    return value.replace("[", "(").replace("]", ")")


def fetch_candidates(fetch_start_utc: datetime) -> list[Candidate]:
    root = ET.fromstring(request_text(SITEMAP_URL))
    candidates: list[Candidate] = []
    for node in root.findall("sm:url", NS):
        loc = (node.findtext("sm:loc", namespaces=NS) or "").strip()
        match = ARTICLE_ID_RE.search(loc)
        if not match:
            continue
        lastmod_raw = (node.findtext("sm:lastmod", namespaces=NS) or "").strip()
        if not lastmod_raw:
            continue
        lastmod = parse_iso(lastmod_raw)
        if lastmod >= fetch_start_utc:
            candidates.append(Candidate(match.group(1), lastmod))
    by_id = {item.article_id: item for item in candidates}
    return sorted(by_id.values(), key=lambda item: (item.lastmod, int(item.article_id)), reverse=True)


def fetch_article(candidate: Candidate) -> Article | None | object:
    try:
        payload = request_json(ARTICLE_API.format(article_id=candidate.article_id))
    except urllib.error.HTTPError as exc:
        if exc.code in (403, 404):
            return None
        return FETCH_FAILED
    except Exception:  # noqa: BLE001
        return FETCH_FAILED

    if payload.get("postType") != "article":
        return None

    published_raw = payload.get("timePublished")
    title = strip_html(payload.get("titleHtml"))
    if not published_raw or not title:
        return None

    try:
        published_msk = to_msk(str(published_raw))
    except ValueError:
        return None

    stats = payload.get("statistics") or {}
    meta = payload.get("metadata") or {}
    description = strip_html(meta.get("metaDescription"))
    if not description:
        description = strip_html((payload.get("leadData") or {}).get("textHtml"))
    if not description:
        description = strip_html(payload.get("textHtml"))

    return Article(
        article_id=candidate.article_id,
        title=title,
        description=description,
        published_msk=published_msk,
        views=int(stats.get("readingCount") or 0),
        score=int(stats.get("score") or 0),
        comments=int(stats.get("commentsCount") or 0),
    )


def fetch_pass(candidates: Iterable[Candidate], workers: int) -> tuple[list[Article], list[Candidate]]:
    articles: list[Article] = []
    failed: list[Candidate] = []
    candidate_list = list(candidates)
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(fetch_article, item): item for item in candidate_list}
        for future in as_completed(futures):
            result = future.result()
            if result is FETCH_FAILED:
                failed.append(futures[future])
            elif isinstance(result, Article):
                articles.append(result)
    return articles, failed


def fetch_articles(candidates: list[Candidate]) -> list[Article]:
    articles, failed = fetch_pass(candidates, WORKERS)
    for attempt in range(2):
        if not failed:
            break
        log(f"retry pass {attempt + 1}: {len(failed)} transient failures")
        time.sleep(2)
        more, failed = fetch_pass(failed, RETRY_WORKERS)
        articles.extend(more)
    if failed:
        sample = ", ".join(item.article_id for item in failed[:10])
        log(f"warning: {len(failed)} unrecovered article fetches: {sample}")
    if not articles:
        raise RuntimeError("no article API records fetched")
    return articles


def rank_articles(items: Iterable[Article]) -> list[Article]:
    return sorted(
        items,
        key=lambda item: (
            -item.views,
            -item.score,
            -item.comments,
            -item.published_msk.timestamp(),
            int(item.article_id),
        ),
    )


def rank_by_score(items: Iterable[Article]) -> list[Article]:
    return sorted(
        items,
        key=lambda item: (
            -item.score,
            -item.views,
            -item.comments,
            -item.published_msk.timestamp(),
            int(item.article_id),
        ),
    )


def fmt_dt(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%d %H:%M")


def render_article(rank: str, article: Article, desc_limit: int) -> str:
    parts = [f"{rank} [{md_link_text(article.title)}]({article.url})"]
    description = clip(article.description, desc_limit)
    if description:
        parts.append(description)
    parts.extend([
        "",
        f"📅 Дата: **{fmt_dt(article.published_msk)}**",
        f"👁 Просмотры: **{article.views}**",
        f"⭐ Рейтинг: **{article.score}**",
    ])
    return "\n".join(parts)


def render_highlight(icon: str, label: str, article: Article, desc_limit: int) -> str:
    parts = [
        f"{icon} **{label}**",
        f"[{md_link_text(article.title)}]({article.url})",
    ]
    description = clip(article.description, desc_limit)
    if description:
        parts.append(description)
    parts.extend([
        "",
        f"📅 Дата: **{fmt_dt(article.published_msk)}**",
        f"👁 Просмотры: **{article.views}**",
        f"⭐ Рейтинг: **{article.score}**",
    ])
    return "\n".join(parts)


def build_message(
    *,
    period: str,
    top5: list[Article],
    trend: Article | None,
    top: Article | None,
    desc_limit: int,
) -> str:
    cfg = PERIODS[period]
    blocks = [
        f"**📊 Хабр дайджест** - *{cfg['kind']}*",
        f"Самые популярные статьи за **{cfg['period_word']}** 🔝",
        SEP,
        "",
    ]
    for index, article in enumerate(top5):
        blocks.append(render_article(RANKS[index], article, desc_limit))
        blocks.append("")
    if top is not None and cfg["top_label"]:
        blocks.extend([SEP, "", render_highlight("🏆", str(cfg["top_label"]), top, desc_limit), ""])
    if trend is not None and cfg["trend_label"]:
        blocks.extend([SEP, "", render_highlight("🔥", str(cfg["trend_label"]), trend, desc_limit), ""])
    while blocks and blocks[-1] == "":
        blocks.pop()
    return "\n".join(blocks)


def fit_message(period: str, top5: list[Article], trend: Article | None, top: Article | None) -> str:
    for desc_limit in (220, 180, 140, 100, 70, 40, 0):
        message = build_message(period=period, top5=top5, trend=trend, top=top, desc_limit=desc_limit)
        if len(message) <= MESSAGE_LIMIT:
            return message
    raise RuntimeError("message does not fit Telegram delivery limit even without descriptions")


def select_digest(period: str, now_msk: datetime) -> tuple[list[Article], Article | None, Article | None]:
    cfg = PERIODS[period]
    summary_days = int(cfg["summary_days"])
    highlight_days = cfg["highlight_days"]
    fetch_days = max(summary_days, int(highlight_days or 0))
    fetch_start_utc = (now_msk - timedelta(days=fetch_days)).astimezone(timezone.utc)
    summary_start = now_msk - timedelta(days=summary_days)

    log(f"period={period} now_msk={now_msk.isoformat()} fetch_days={fetch_days}")
    candidates = fetch_candidates(fetch_start_utc)
    log(f"candidates from sitemap: {len(candidates)}")
    if not candidates:
        raise RuntimeError("sitemap produced no candidates")

    articles = fetch_articles(candidates)
    log(f"articles fetched: {len(articles)}")

    summary_pool = [item for item in articles if summary_start <= item.published_msk <= now_msk]
    top5 = rank_articles(summary_pool)[:5]
    if not top5:
        raise RuntimeError(f"no articles in {period} summary window")

    top = None
    trend = None
    if highlight_days:
        highlight_start = now_msk - timedelta(days=int(highlight_days))
        window = [item for item in articles if highlight_start <= item.published_msk <= now_msk]
        excluded = {item.article_id for item in top5}
        top_pool = [item for item in window if item.article_id not in excluded]
        top_ranked = rank_by_score(top_pool)
        if top_ranked:
            top = top_ranked[0]
            excluded.add(top.article_id)
        trend_pool = [item for item in window if item.article_id not in excluded]
        trend_ranked = rank_articles(trend_pool)
        if trend_ranked:
            trend = trend_ranked[0]

    return top5, trend, top


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate one Habr digest message as stdout.")
    parser.add_argument("--period", required=True, choices=sorted(PERIODS))
    parser.add_argument("--dry-run", action="store_true", help="compatibility no-op; output is always stdout")
    parser.add_argument("--debug", action="store_true", help="print selected article diagnostics to stderr")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    top5, trend, top = select_digest(args.period, datetime.now(MSK))
    if args.debug:
        for index, article in enumerate(top5, 1):
            log(f"top{index}: views={article.views} score={article.score} comments={article.comments} id={article.article_id} title={article.title[:70]}")
        if top:
            log(f"top-highlight: score={top.score} views={top.views} id={top.article_id} title={top.title[:70]}")
        if trend:
            log(f"trend-highlight: views={trend.views} score={trend.score} id={trend.article_id} title={trend.title[:70]}")
    message = fit_message(args.period, top5, trend, top)
    log(f"message length: {len(message)}")
    print(message)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:  # noqa: BLE001
        log(f"fatal: {exc}")
        raise SystemExit(1)
