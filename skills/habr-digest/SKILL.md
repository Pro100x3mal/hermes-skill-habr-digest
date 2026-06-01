---
name: habr-digest
description: "Use when building or maintaining a \"📊 Хабр дайджест\" — cron-driven digests of the top-5 Habr articles by views (daily/weekly/monthly) posted to a Telegram topic. Data comes from the Habr sitemap + per-article API, never from search results or the top/* collections."
version: 2.0.0
author: Pro100x3mal
license: MIT
platforms: [linux]
required_environment_variables:
  - name: HABR_DIGEST_BOT_TOKEN
    prompt: "Telegram bot token"
    help: "From @BotFather. The bot must be a member/admin of the target chat."
    required_for: "Posting the digest to Telegram"
  - name: HABR_DIGEST_CHAT_ID
    prompt: "Target chat id (e.g. -1001234567890)"
    help: "Numeric chat/channel id where the digest is posted."
    required_for: "Posting the digest to Telegram"
metadata:
  hermes:
    tags: [habr, digest, telegram, cron, sitemap, no-agent]
    related_skills: [tasks-board, telegram-content-pipeline]
    config:
      - key: HABR_DIGEST_THREAD_ID
        description: "Optional Telegram forum topic thread id. Omit to post to General."
        default: ""
        prompt: "Forum topic thread id (leave empty for General)"
---

# 📊 Хабр дайджест

## Overview

Autonomous digests of the **top-5 Habr articles by view count** for a period,
posted as a single Telegram message. Three periods: 📅 Daily, 📆 Weekly,
🗓 Monthly. Each period is a separate `no_agent` cron job that runs
`scripts/habr_digest.py --period <p>`. The script collects the data and sends
the message itself via the Telegram Bot API — the agent is not involved at
runtime.

**Hard data-collection rules (do not break):**
- Do NOT use search results.
- Do NOT use the `top/daily|weekly|monthly|yearly` collections.
- The ID/URL list comes ONLY from the Habr **sitemap**.
- Views / score / date / title / description come ONLY from the **per-article
  API**.

## Configuration (no hardcoded values)

The script reads everything from the environment — nothing is baked into the
code:

| Variable | Required | Meaning |
|---|---|---|
| `HABR_DIGEST_BOT_TOKEN` | yes | Telegram bot token |
| `HABR_DIGEST_CHAT_ID` | yes | Target chat id (e.g. `-1001234567890`) |
| `HABR_DIGEST_THREAD_ID` | no | Forum topic thread id; omit to post to General |

The bot must be a member of the target chat (and an admin if posting to a forum
topic). Keep the token in a secrets file (e.g. `~/.hermes/.env`) and export the
three variables in the cron wrapper — see "Cron jobs" below.

## When to Use

- Initial setup of the digest (create 3 cron jobs + 3 Tasks cards).
- Editing collection / render / period / schedule logic.
- Diagnosing "the digest didn't arrive" or "the formatting broke".

Don't use for: a one-off manual Habr top (just run the script with `--dry-run`).

## Architecture (verified against the live API)

### ID source — sitemap
```
https://habr.com/sitemap_articles1.xml
```
~25,000 recent URLs, date-sorted, ~9 months of coverage. Each `<url>`:
`<loc>https://habr.com/ru/.../articles/<id>/</loc>` + `<lastmod>`.
Take the `id` of every article with `lastmod >= fetch_start`. This is the
**only** role of the sitemap — to provide the ID list.

> Why NOT `/kek/v2/articles/?sort=date`: it has a hard cap of ~1000 articles
> (`page=21` → HTTP 400, only ~20 days deep), not enough for the monthly
> period. The sitemap has no such cap.

### Per-article data — direct API
```
https://habr.com/kek/v2/articles/<id>/?fl=ru&hl=ru
```
- `statistics.readingCount` — views
- `statistics.score` — rating (upvotes − downvotes); shown in the digest
- `statistics.commentsCount` — comments (collected but NOT shown)
- `timePublished` (UTC ISO) — date (rendered in Europe/Moscow)
- `titleHtml` — title; article URL = `https://habr.com/ru/articles/<id>/`
- `metadata.metaDescription` — description (fallback: cleaned `leadData.textHtml`)
- `postType` — **filter: keep only `article`, drop `news`**

### Periods (Europe/Moscow, relative to launch time)
| Period | Top-5 summary | 🔥 Trend (by views) | 🏆 Top (by score) | fetch window |
|---|---|---|---|---|
| daily | 1 day | Trend of week (7d) | Top of week (7d) | 7 days |
| weekly | 7 days | Trend of month (30d) | Top of month (30d) | 30 days |
| monthly | 30 days | none | none | 30 days |

- Top-5 — by **views** (`readingCount`).
- 🏆 **Top** — the #1 by **score** in the trend window, **excluding** the top-5.
  Selected FIRST.
- 🔥 **Trend** — the #1 by **views** in the same window, **excluding** the top-5
  and Top.
- Selection order (variant A): Top first, then Trend. This way 🏆 Top always
  shows the absolute maximum score, even when the same article also leads by
  views (then Trend takes the 2nd by views).
- Both highlight blocks (Trend + Top) appear only for daily/weekly; monthly has
  neither.

## Running the script

```bash
python3 "${HERMES_SKILL_DIR}/scripts/habr_digest.py" --period daily
```
Flags:
- `--period daily|weekly|monthly` (required)
- `--dry-run` — print to stdout, do not send (for testing)
- `--debug` — log the top/trend selection to stderr

Cron (`no_agent`) behaviour: on success prints an empty line (quiet) and sends
the digest; on error writes to stderr and exits non-zero (cron raises an alert).

## Telegram delivery

The script calls the Bot API `sendMessage`:
- `chat_id` from `HABR_DIGEST_CHAT_ID`, `message_thread_id` from
  `HABR_DIGEST_THREAD_ID` (omitted if unset)
- `parse_mode=HTML`
- `link_preview_options={"is_disabled": true}` — disables link previews
- token from `HABR_DIGEST_BOT_TOKEN`
- length is squeezed under the 4096 limit (descriptions trimmed in steps)

## Message format (HTML)

```
<b>📊 Хабр дайджест</b> - <b><i>📅 Daily</i></b>
Самые популярные статьи за <b>сутки</b> 🔝
➖➖➖➖➖➖➖➖➖➖➖➖

1️⃣ <b><a href="URL">Title</a></b>
Short description

📅 Дата: <b>YYYY-MM-DD HH:MM</b>
👁 Просмотры: <b>N</b>
⭐ Рейтинг: <b>N</b>

... 2️⃣ … 5️⃣ …
➖➖➖➖➖➖➖➖➖➖➖➖

🔥 <b>Тренд недели</b>
<b><a href="URL">Title</a></b>
Short description

📅 Дата: <b>…</b>
👁 Просмотры: <b>N</b>
⭐ Рейтинг: <b>N</b>
➖➖➖➖➖➖➖➖➖➖➖➖

🏆 <b>Топ недели</b>
<b><a href="URL">Title</a></b>
Short description

📅 Дата: <b>…</b>
👁 Просмотры: <b>N</b>
⭐ Рейтинг: <b>N</b>
```

Rules: digest title — bold; kind — bold+italic; the period word, date, views,
score, article titles and block labels — bold; ranks `1️⃣..5️⃣` (NOT `#1`). The
🔥 Trend and 🏆 Top blocks appear only for daily/weekly. No bare URLs, no `🔗`
blocks, no comments, no extra data.

## Cron jobs

All three are `no_agent=True`, `deliver=local` (the script sends to Telegram
itself); no `enabled_toolsets` needed. If the host runs in Europe/Moscow, the
cron times match the computed periods.

A `no_agent` cron requires the `script` to live in `~/.hermes/scripts/` (an
absolute path under `skills/` is rejected with `Script path must be relative to
~/.hermes/scripts/`). So the cron jobs point at thin wrappers in
`~/.hermes/scripts/` — `habr_digest_daily.sh` / `..._weekly.sh` /
`..._monthly.sh` — each of which exports the config and execs the real script.

Wrapper template (this file holds the real secrets/IDs and is NOT part of the
published skill):

```bash
#!/usr/bin/env bash
set -euo pipefail
# Load the bot token from your secrets file
export HABR_DIGEST_BOT_TOKEN="$(grep '^TELEGRAM_BOT_TOKEN=' ~/.hermes/.env | cut -d= -f2-)"
export HABR_DIGEST_CHAT_ID="-1001234567890"   # your chat id
export HABR_DIGEST_THREAD_ID="12345"          # optional forum topic thread id
exec python3 ~/.hermes/skills/social-media/habr-digest/scripts/habr_digest.py --period daily
```

| Period | schedule | cron script |
|---|---|---|
| 📅 Daily | `0 7 * * *` | `habr_digest_daily.sh` |
| 📆 Weekly | `1 7 * * 1` | `habr_digest_weekly.sh` |
| 🗓 Monthly | `2 7 1 * *` | `habr_digest_monthly.sh` |

## Why NOT `top/*` (proven experimentally)

The ban on `top/daily|weekly|monthly|yearly` is correctness, not formality:
**`top/*` ranks by RATING (`score` = upvotes − downvotes), while the spec
requires top by VIEWS (`readingCount`).** Different metrics, different order.
`top/*` also drops articles below a rating threshold (≈150 on page 1 of
top/monthly) — high-view but mid-rated articles never appear and would be lost.
The only correct path for "by views" is to collect all articles for the period
(sitemap → per-article API) and sort by `readingCount`. See
`references/top-vs-views-evidence.md` for the full evidence.

## Common Pitfalls

1. **`/kek/v2/articles/?sort=date` cap** — `page>20` (perPage=50) returns HTTP
   400, only ~20 days deep. The monthly top-by-views would lose older "viral"
   articles. Always take IDs from the sitemap.
2. **`news=false` does NOT exclude corporate news** — the list still contains
   `postType=news`. Filter strictly on `postType == "article"` from the
   per-article API.
3. **monthly is heavy** — the `lastmod` filter yields a superset (~6000+ items:
   old articles with fresh comments are included). A real monthly run is ≈4 min
   at 32 workers, ~230 MB RAM. The cron timeout must allow for that. daily is
   light (~30s, ~1000 items).
4. **Habr rate limiting** — large runs may hit 429/timeouts; the script uses
   retry + exponential backoff (4 attempts). 403/404 are NOT retried (the
   article is unavailable, not a failure — see pitfall 7).
5. **Empty `metaDescription`** — fall back to `leadData.textHtml` (tags
   stripped).
6. **Link previews** — `link_preview_options.is_disabled=true` is mandatory,
   otherwise Telegram attaches a preview of the first link.
7. **Silent article loss skews the highlight blocks.** A weekly/monthly run
   fetches ~6400 articles; some requests fail consistently (rate limit, timeout,
   HTTP 403 for delisted articles). The script distinguishes `None` (filtered)
   from `FETCH_FAILED` (network error) and retries failed IDs in a second pass
   with a smaller pool, so a leader article is never silently dropped. **403/404
   is a legitimate skip, not a loss**: do not retry it, or the retry pass loops
   forever on the unavailable articles.
   - **What those 403s are (verified, NOT regional blocking).** The response
     body is JSON with an `errorCode`: `AUTHOR_INACTIVE` (author banned/
     deactivated) or `IN_DRAFTS` (article moved back to drafts). This is a
     server-side publication state — the article is hidden site-wide (gone from
     feed/search/RSS). **There is no bypass:** browser UA, Accept-Language,
     Referer, `fl=en`, the HTML page, the `m.habr.com` host and RSS all return
     403/404. And no bypass is needed — it's delisted content that does not
     belong in a "popular" digest. Skipping it is correct, not a loss. It's
     ~0.4% of the window and only old articles that surface in the 30-day window
     because of fresh comments bumping `lastmod`.
8. **Length > 4096** — the message won't send. The script trims descriptions in
   a cascade; do not add extra lines to the template.
9. **Timezone** — periods and date output are Europe/Moscow (fixed +03:00, no
   DST).
10. **`message_thread_id` ≠ message id.** Before creating the cron, validate the
    topic with a test `sendMessage` using that `message_thread_id`: if Telegram
    answers `400 Bad Request: message thread not found`, the number is not the
    topic's thread_id (a common mix-up: passing a message id). A forum topic's
    thread_id = the message_id of the service `forum_topic_created` event. Get
    it from a `t.me/c/<chat>/<thread>/<msg>` link (middle number = thread_id) or
    by creating the topic via `createForumTopic`. Never point a cron at an
    unvalidated topic — every run would fail.
11. **List-API order = the `publicationIds` key** (NOT `articleIds`, which does
    not exist in the response). `/kek/v2/articles/?...` returns `publicationRefs`
    (an id→data dict, order NOT preserved) and `publicationIds` (the ordered id
    list). Iterating `refs.keys()` for "first N in order" is a bug. Not critical
    for this pipeline (we sort by `readingCount` ourselves), but use
    `publicationIds` for any "what does the API return in order" check.
12. **Trend vs Top conflict (variant A).** When one article leads both views and
    score, the blocks compete for it. Rule: **pick 🏆 Top (by `score`) first,
    then 🔥 Trend (by `views`) excluding Top.** This way Top always shows the
    absolute maximum score (otherwise it would show the 2nd-best score and look
    illogical — Top's score < Trend's score). On a tie, Trend takes the 2nd by
    views.

## Verification Checklist

- [ ] `HABR_DIGEST_BOT_TOKEN` and `HABR_DIGEST_CHAT_ID` are set in the
      environment (and `HABR_DIGEST_THREAD_ID` if posting to a topic)
- [ ] `python3 scripts/habr_digest.py --period daily --dry-run --debug` yields a
      top-5 + trend, length < 4096
- [ ] No `postType=news` articles in the output
- [ ] IDs come from the sitemap, stats from `/kek/v2/articles/<id>/`
- [ ] 3 cron jobs created (daily/weekly/monthly) with correct schedules and
      `script = habr_digest_<period>.sh` in `~/.hermes/scripts/`
- [ ] Test send arrived in the target chat/topic with link previews disabled
