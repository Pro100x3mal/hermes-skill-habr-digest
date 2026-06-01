#!/usr/bin/env python3
"""
Habr digest — top-5 Habr articles by views over a period, plus highlight blocks.

Article ID/URL list comes from the Habr sitemap
(https://habr.com/sitemap_articles1.xml) — NOT from search results and NOT from
the top/daily|weekly|monthly collections. Views / score / date / title /
description come strictly from the per-article API:
https://habr.com/kek/v2/articles/<id>/?fl=ru&hl=ru

Periods are computed in Europe/Moscow relative to launch time.

Configuration (no hardcoded chat/thread/token):
    HABR_DIGEST_BOT_TOKEN   (required) — Telegram bot token
    HABR_DIGEST_CHAT_ID     (required) — target chat id (e.g. -1001234567890)
    HABR_DIGEST_THREAD_ID   (optional) — forum topic thread id; omit for General

Usage:
    habr_digest.py --period daily|weekly|monthly [--dry-run] [--debug]

Cron (no_agent) behaviour: on success prints an empty line (quiet) and sends the
digest itself via the Bot API. On error: writes to stderr and exits non-zero.
"""
import argparse
import html
import json
import os
import re
import sys
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone

# ---- Environment / constants ----
MSK = timezone(timedelta(hours=3))            # Europe/Moscow (fixed +03:00, no DST)
SITEMAP_URL = "https://habr.com/sitemap_articles1.xml"
ARTICLE_API = "https://habr.com/kek/v2/articles/{id}/?fl=ru&hl=ru"
ARTICLE_URL = "https://habr.com/ru/articles/{id}/"
UA = "Mozilla/5.0 (compatible; HabrDigest/1.0)"

TELEGRAM_API = "https://api.telegram.org/bot{token}/sendMessage"

ENV_TOKEN = "HABR_DIGEST_BOT_TOKEN"
ENV_CHAT = "HABR_DIGEST_CHAT_ID"
ENV_THREAD = "HABR_DIGEST_THREAD_ID"

WORKERS = 32
HTTP_TIMEOUT = 20
MAX_RETRIES = 4
TG_LIMIT = 4096

# period -> (summary_days, trend_days|None, kind, period_word, trend_label, top_label)
PERIODS = {
    "daily":   (1,  7,    "📅 Daily",   "сутки",  "Тренд недели", "Топ недели"),
    "weekly":  (7,  30,   "📆 Weekly",  "неделю", "Тренд месяца", "Топ месяца"),
    "monthly": (30, None, "🗓 Monthly", "месяц",  None,           None),
}
RANK = ["1️⃣", "2️⃣", "3️⃣", "4️⃣", "5️⃣"]


def log(msg):
    print(f"[habr-digest] {msg}", file=sys.stderr, flush=True)


def http_get(url, want_json=False):
    """GET with retries and exponential backoff."""
    last = None
    for attempt in range(MAX_RETRIES):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=HTTP_TIMEOUT) as r:
                raw = r.read()
            return json.loads(raw) if want_json else raw.decode("utf-8", "replace")
        except Exception as e:  # noqa
            last = e
            code = getattr(e, "code", None)
            # 404 (deleted) / 403 (delisted: AUTHOR_INACTIVE / IN_DRAFTS) —
            # retrying is pointless, the article is permanently unavailable.
            if code in (403, 404):
                raise
            sleep = (2 ** attempt) * 0.5 + (0.1 * attempt)
            time.sleep(sleep)
    raise last


# ---- Step 1: sitemap -> candidate IDs filtered by lastmod ----
def fetch_candidate_ids(fetch_start):
    """
    Return article ids whose lastmod >= fetch_start.
    lastmod >= timePublished always holds, so filtering by lastmod is a safe
    superset for the desired publication-date window.
    """
    xml = http_get(SITEMAP_URL)
    # Each <url> carries <loc>...</loc> and <lastmod>...</lastmod> in order.
    pairs = re.findall(
        r"<loc>(https://habr\.com/[^<]*?/articles/(\d+)/)</loc>\s*"
        r"<changefreq>[^<]*</changefreq>\s*<priority>[^<]*</priority>\s*"
        r"<lastmod>([^<]+)</lastmod>",
        xml,
    )
    ids = []
    for _loc, aid, lastmod in pairs:
        try:
            lm = datetime.fromisoformat(lastmod)
        except ValueError:
            continue
        if lm.tzinfo is None:
            lm = lm.replace(tzinfo=timezone.utc)
        if lm >= fetch_start:
            ids.append(aid)
    # dedup, preserving order
    seen = set()
    out = []
    for a in ids:
        if a not in seen:
            seen.add(a)
            out.append(a)
    return out


# ---- Step 2: per-article API ----
def clean_text(raw_html, limit=220):
    if not raw_html:
        return ""
    txt = re.sub(r"<[^>]+>", "", raw_html)
    txt = html.unescape(txt)
    txt = re.sub(r"\s+", " ", txt).strip()
    if len(txt) > limit:
        txt = txt[:limit].rstrip() + "…"
    return txt


FETCH_FAILED = object()  # sentinel: network failure (vs None = filtered out)


def fetch_article(aid):
    """Fetch one article.
    Returns a dict (article), None (filtered: news / missing data) or
    FETCH_FAILED (network failure after all retries — must be retried in a
    second pass so a leader article is never silently lost).
    """
    try:
        d = http_get(ARTICLE_API.format(id=aid), want_json=True)
    except Exception as e:
        # 403 / 404 — legitimate skip (article delisted/deleted), not a network
        # failure: do not retry, do not count as a loss.
        if getattr(e, "code", None) in (403, 404):
            return None
        return FETCH_FAILED
    if not isinstance(d, dict):
        return FETCH_FAILED
    # Articles only. Drop news (corporate news etc.).
    if d.get("postType") != "article":
        return None
    tp = d.get("timePublished")
    if not tp:
        return None
    try:
        pub = datetime.fromisoformat(tp)
    except ValueError:
        return None
    if pub.tzinfo is None:
        pub = pub.replace(tzinfo=timezone.utc)
    stats = d.get("statistics") or {}
    title = html.unescape(re.sub(r"<[^>]+>", "", d.get("titleHtml") or "")).strip()
    if not title:
        return None
    meta = d.get("metadata") or {}
    desc = clean_text(meta.get("metaDescription"))
    if not desc:
        desc = clean_text((d.get("leadData") or {}).get("textHtml"))
    return {
        "id": aid,
        "title": title,
        "desc": desc,
        "views": int(stats.get("readingCount") or 0),
        "comments": int(stats.get("commentsCount") or 0),
        "score": int(stats.get("score") or 0),
        "pub": pub,                      # aware UTC
        "pub_msk": pub.astimezone(MSK),
        "url": ARTICLE_URL.format(id=aid),
    }


def _fetch_pass(ids, workers):
    """One pass: returns (articles, failed_ids)."""
    out, failed = [], []
    with ThreadPoolExecutor(max_workers=workers) as ex:
        futs = {ex.submit(fetch_article, a): a for a in ids}
        for f in as_completed(futs):
            r = f.result()
            if r is FETCH_FAILED:
                failed.append(futs[f])
            elif r:
                out.append(r)
    return out, failed


def fetch_all(ids):
    """Concurrent fetch with a retry pass for failures. Ensures network
    failures are not silently dropped — otherwise a top article by views/score
    could fall out of the result non-deterministically."""
    out, failed = _fetch_pass(ids, WORKERS)
    # Retry passes for failed ids — smaller pool (gentler on rate limits).
    for attempt in range(2):
        if not failed:
            break
        log(f"retry pass {attempt+1}: {len(failed)} failed ids, refetch with smaller pool")
        time.sleep(2)
        more, failed = _fetch_pass(failed, max(4, WORKERS // 4))
        out.extend(more)
    if failed:
        log(f"WARNING: {len(failed)} articles unrecoverable after retries: {failed[:20]}")
    return out


# ---- Step 3: render ----
def esc(s):
    return html.escape(s, quote=False)


def fmt_dt(dt_msk):
    return dt_msk.strftime("%Y-%m-%d %H:%M")


def render_item(rank, art):
    title = f'<b><a href="{art["url"]}">{esc(art["title"])}</a></b>'
    parts = [f"{rank} {title}"]
    if art["desc"]:
        parts.append(esc(art["desc"]))
    parts.append("")  # spacer
    parts.append(f"📅 Дата: <b>{fmt_dt(art['pub_msk'])}</b>")
    parts.append(f"👁 Просмотры: <b>{art['views']}</b>")
    parts.append(f"⭐ Рейтинг: <b>{art['score']}</b>")
    return "\n".join(parts)


def render_highlight(icon, label, art):
    """Render a highlight block (Trend / Top) with the given icon and label."""
    title = f'<b><a href="{art["url"]}">{esc(art["title"])}</a></b>'
    parts = [f"{icon} <b>{esc(label)}</b>", title]
    if art["desc"]:
        parts.append(esc(art["desc"]))
    parts.append("")
    parts.append(f"📅 Дата: <b>{fmt_dt(art['pub_msk'])}</b>")
    parts.append(f"👁 Просмотры: <b>{art['views']}</b>")
    parts.append(f"⭐ Рейтинг: <b>{art['score']}</b>")
    return "\n".join(parts)


SEP = "➖➖➖➖➖➖➖➖➖➖➖➖"


def build_message(top5, trend, top, kind, period_word, trend_label, top_label, desc_limit=None):
    head = f"<b>📊 Хабр дайджест</b> - <b><i>{esc(kind)}</i></b>"
    sub = f"Самые популярные статьи за <b>{esc(period_word)}</b> 🔝"
    blocks = [head, sub, SEP, ""]
    for i, art in enumerate(top5):
        a = dict(art)
        if desc_limit is not None:
            a["desc"] = clean_text_keep(a["desc"], desc_limit)
        blocks.append(render_item(RANK[i], a))
        blocks.append("")  # spacer between articles
    if trend and trend_label:
        blocks.append(SEP)
        blocks.append("")
        a = dict(trend)
        if desc_limit is not None:
            a["desc"] = clean_text_keep(a["desc"], desc_limit)
        blocks.append(render_highlight("🔥", trend_label, a))
        blocks.append("")
    if top and top_label:
        blocks.append(SEP)
        blocks.append("")
        a = dict(top)
        if desc_limit is not None:
            a["desc"] = clean_text_keep(a["desc"], desc_limit)
        blocks.append(render_highlight("🏆", top_label, a))
    # drop trailing empty block(s)
    while blocks and blocks[-1] == "":
        blocks.pop()
    return "\n".join(blocks)


def clean_text_keep(txt, limit):
    if not txt:
        return ""
    if len(txt) <= limit:
        return txt
    return txt[:limit].rstrip() + "…"


# ---- Step 4: send ----
def get_config():
    """Read token / chat / thread from environment. Fails loudly if missing."""
    token = os.environ.get(ENV_TOKEN, "").strip()
    chat = os.environ.get(ENV_CHAT, "").strip()
    thread = os.environ.get(ENV_THREAD, "").strip()
    missing = [n for n, v in ((ENV_TOKEN, token), (ENV_CHAT, chat)) if not v]
    if missing:
        raise RuntimeError(f"missing required env vars: {', '.join(missing)}")
    return token, chat, (int(thread) if thread else None)


def send_telegram(text):
    token, chat, thread = get_config()
    payload = {
        "chat_id": chat,
        "text": text,
        "parse_mode": "HTML",
        "link_preview_options": {"is_disabled": True},
    }
    if thread is not None:
        payload["message_thread_id"] = thread
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        TELEGRAM_API.format(token=token),
        data=data,
        headers={"Content-Type": "application/json", "User-Agent": UA},
    )
    with urllib.request.urlopen(req, timeout=HTTP_TIMEOUT) as r:
        resp = json.loads(r.read())
    if not resp.get("ok"):
        raise RuntimeError(f"Telegram API error: {resp}")
    return resp


def fit_message(top5, trend, top, kind, period_word, trend_label, top_label):
    """Guarantee the message fits one Telegram message (<TG_LIMIT) by shrinking
    descriptions in cascading steps."""
    msg = None
    for limit in (220, 180, 140, 100, 70, 40, 0):
        lim = None if limit == 220 else limit
        msg = build_message(top5, trend, top, kind, period_word,
                            trend_label, top_label, desc_limit=lim)
        if len(msg) <= TG_LIMIT:
            return msg
    return msg[:TG_LIMIT]  # hard cut as last resort


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--period", required=True, choices=list(PERIODS))
    ap.add_argument("--dry-run", action="store_true", help="print to stdout, do not send")
    ap.add_argument("--debug", action="store_true")
    args = ap.parse_args()

    summary_days, trend_days, kind, period_word, trend_label, top_label = PERIODS[args.period]
    now = datetime.now(MSK)
    summary_start = now - timedelta(days=summary_days)
    fetch_days = max(summary_days, trend_days or 0)
    fetch_start = (now - timedelta(days=fetch_days)).astimezone(timezone.utc)

    log(f"period={args.period} now_msk={now.isoformat()} fetch_days={fetch_days}")
    ids = fetch_candidate_ids(fetch_start)
    log(f"candidates from sitemap: {len(ids)}")
    if not ids:
        raise RuntimeError("sitemap returned no candidates")

    arts = fetch_all(ids)
    log(f"articles fetched (postType=article): {len(arts)}")

    # Summary: published within [summary_start, now]
    summary_pool = [a for a in arts if summary_start <= a["pub_msk"] <= now]
    summary_pool.sort(key=lambda a: a["views"], reverse=True)
    top5 = summary_pool[:5]
    if not top5:
        raise RuntimeError(f"no articles for period {args.period}")

    # Variant A: pick Top (by score) FIRST, then Trend (by views) excluding Top.
    # This guarantees 🏆 Top shows the absolute maximum score, even if that same
    # article also leads by views (in which case Trend takes the 2nd by views).
    trend = None
    top = None
    if trend_days:
        trend_start = now - timedelta(days=trend_days)
        window = [a for a in arts if trend_start <= a["pub_msk"] <= now]
        top_ids = {a["id"] for a in top5}
        # Top: most-rated article in the trend window, excluding the top-5
        top_pool = [a for a in window if a["id"] not in top_ids]
        top_pool.sort(key=lambda a: a["score"], reverse=True)
        if top_pool:
            top = top_pool[0]
        # Trend: most-viewed article, excluding top-5 and Top
        exclude = set(top_ids)
        if top:
            exclude.add(top["id"])
        trend_pool = [a for a in window if a["id"] not in exclude]
        trend_pool.sort(key=lambda a: a["views"], reverse=True)
        if trend_pool:
            trend = trend_pool[0]

    if args.debug:
        for i, a in enumerate(top5):
            log(f"  {i+1}. views={a['views']:>6} score={a['score']:>5} | {a['pub_msk']:%Y-%m-%d %H:%M} | {a['title'][:55]}")
        if trend:
            log(f"  TREND views={trend['views']} score={trend['score']} | {trend['title'][:55]}")
        if top:
            log(f"  TOP   score={top['score']} views={top['views']} | {top['title'][:55]}")

    msg = fit_message(top5, trend, top, kind, period_word, trend_label, top_label)
    log(f"message length: {len(msg)}")

    if args.dry_run:
        print(msg)
        return

    send_telegram(msg)
    log("sent OK")
    print("")  # quiet success for no_agent cron


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        log(f"FATAL: {e}")
        sys.exit(1)
