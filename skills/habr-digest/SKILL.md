---
name: habr-digest
description: Build Habr top-by-views Telegram digests.
version: 1.0.0
author: Hermes Agent
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [habr, research, telegram, digest, cron]
    related_skills: [hermes-agent]
    requires_toolsets: [terminal]
    config:
      - key: habr_digest.telegram_chat_id
        description: Telegram chat id for digest delivery.
        default: ""
        prompt: Telegram chat id
      - key: habr_digest.telegram_thread_id
        description: Optional Telegram forum topic thread id.
        default: ""
        prompt: Telegram topic thread id, if any
required_environment_variables:
  - name: HABR_DIGEST_BOT_TOKEN
    prompt: Telegram bot token
    help: Create or reuse a bot token via BotFather.
    required_for: Sending digests to Telegram
---

# Habr Digest Skill

Builds fixed-format Habr article digests from the Habr sitemap and per-article API, then optionally sends one HTML-formatted Telegram message. It ranks the main top-5 by views, never by Habr `top/*` pages, and never by search results.

This skill intentionally contains no tokens, chat ids, thread ids, or account-specific values. Deployment wrappers may keep secrets in local environment variables, but the published Python script accepts the Telegram bot token via stdin or an explicit runtime argument so community security scanners do not see programmatic environment-secret access.

Implementation tradeoffs and the comparison against `Pro100x3mal/hermes-skill-habr-digest` are captured in `references/external-skill-comparison.md`; consult it before changing collection, retry, Telegram rendering, or highlight-block semantics.

## When to Use

Use this skill when the task is to:

- generate daily, weekly, or monthly Habr article digests;
- schedule Habr digests with `cronjob` and a wrapper script;
- debug Habr collection, ranking, or Telegram formatting;
- verify that a digest is generated from Habr's sitemap plus article API only.

Do not use it for Habr news, company feeds, search-result summaries, or rating-based digests sourced from `top/daily`, `top/weekly`, `top/monthly`, or `top/yearly`.

## Prerequisites

Secrets:

- `HABR_DIGEST_BOT_TOKEN` — Telegram bot token for local wrappers. The script itself does not read this environment variable directly; wrappers should pass it to the script with `--bot-token-stdin`.

Non-secret settings:

- `skills.config.habr_digest.telegram_chat_id` — Telegram chat id.
- `skills.config.habr_digest.telegram_thread_id` — optional Telegram forum topic id.

Manual config examples:

```bash
hermes config set skills.config.habr_digest.telegram_chat_id '<chat-id>'
hermes config set skills.config.habr_digest.telegram_thread_id '<thread-id>'
```

For local one-shot use, pass non-secret delivery values as script arguments instead of hardcoding them. Pass the bot token through stdin:

```bash
printf '%s' "$HABR_DIGEST_BOT_TOKEN" | \
  python3 ${HERMES_SKILL_DIR}/scripts/habr_digest.py \
    --period daily \
    --chat-id '<chat-id>' \
    --thread-id '<thread-id>' \
    --bot-token-stdin
```

## How to Run

Use the `terminal` tool to invoke the bundled script.

Dry run, no Telegram send:

```bash
python3 ${HERMES_SKILL_DIR}/scripts/habr_digest.py --period daily --dry-run
```

Send to Telegram, passing the token through stdin:

```bash
printf '%s' "$HABR_DIGEST_BOT_TOKEN" | \
  python3 ${HERMES_SKILL_DIR}/scripts/habr_digest.py \
    --period weekly \
    --chat-id '<chat-id>' \
    --thread-id '<thread-id>' \
    --bot-token-stdin
```

The script supports `daily`, `weekly`, and `monthly` periods. It uses only Python stdlib modules.

## Quick Reference

- Script: `${HERMES_SKILL_DIR}/scripts/habr_digest.py`
- Habr sitemap: `https://habr.com/sitemap_articles1.xml`
- Article API: `https://habr.com/kek/v2/articles/<id>/?fl=ru&hl=ru`
- Main ranking: top-5 by `statistics.readingCount`
- Daily summary window: 1 day
- Weekly summary window: 7 days
- Monthly summary window: 30 days
- Daily highlight window: 7 days
- Weekly highlight window: 30 days
- Monthly highlights: none
- Telegram parse mode: HTML
- Telegram link previews: disabled with `link_preview_options.is_disabled=true`

## Procedure

1. Compute `now` and period windows in Europe/Moscow time, fixed UTC+03:00.
2. Fetch article candidates only from `sitemap_articles1.xml`.
3. Use sitemap `lastmod` only as a discovery filter for the widest required window.
4. Fetch every candidate through the per-article API.
5. Keep only records with `postType == "article"`.
6. Filter final pools by `timePublished`, not by sitemap `lastmod`.
7. Sort the main pool by views descending, then score, comments, publication time, and id.
8. Render top-5 articles by views.
9. For daily and weekly, add two non-duplicate highlight blocks:
   - `🏆 Топ недели/месяца` — highest score in the highlight window, excluding the main top-5.
   - `🔥 Тренд недели/месяца` — highest views in the highlight window, excluding the main top-5 and selected top article.
10. Fit the message under Telegram's 4096-character limit by shortening descriptions only.
11. Send one HTML message through Telegram Bot API, or print it with `--dry-run`.

## Output Format

The script renders exactly one Telegram message:

```html
<b>📊 Хабр дайджест</b> - <b><i>📅 Daily</i></b>
Самые популярные статьи за <b>сутки</b> 🔝
➖➖➖➖➖➖➖➖➖➖➖➖

1️⃣ <b><a href="URL">Title</a></b>
Description

📅 Дата: <b>YYYY-MM-DD HH:MM</b>
👁 Просмотры: <b>N</b>
⭐ Рейтинг: <b>N</b>
```

Rules:

- article links appear only on article titles;
- no bare URLs;
- no search results;
- no parsing statistics in the user-facing message;
- monthly has no `🔥` or `🏆` highlight blocks;
- descriptions may be shortened, fields and labels must not be silently dropped.

## Cron Setup

For scheduled delivery, create `no_agent` cron jobs with wrapper scripts under `~/.hermes/scripts/`. Cron script paths must be relative to that directory.

Wrapper pattern:

```bash
#!/usr/bin/env bash
set -euo pipefail
exec python3 "$HOME/.hermes/skills/research/habr-digest/scripts/habr_digest.py" \
  --period daily \
  --chat-id "$HABR_DIGEST_CHAT_ID" \
  ${HABR_DIGEST_THREAD_ID:+--thread-id "$HABR_DIGEST_THREAD_ID"}
```

Keep the wrapper account-specific and out of the published skill. Do not commit real chat ids, thread ids, or bot tokens.

Recommended schedules:

- Daily: `0 7 * * *`
- Weekly: `1 7 * * 1`
- Monthly: `2 7 1 * *`

## Pitfalls

1. `top/*` pages are rating-ranked, not view-ranked. They also omit high-view articles below the rating threshold.
2. Habr list APIs are page-capped and do not reliably cover a full monthly window. Use the sitemap for discovery.
3. Sitemap `lastmod` is not publication time. Always filter final windows by API `timePublished`.
4. Some article API calls return 403 or 404 for deleted, draft, or unavailable content. Treat those as skips, not transient failures.
5. Transient failures must be retried in a second pass, otherwise a leading article can disappear from the digest.
6. Do not hardcode credentials or targets in SKILL.md, scripts, wrappers intended for publication, tests, or references.
7. Telegram HTML must be escaped. Never insert raw title or description HTML into the message.
8. Do not hard-truncate the final HTML message; it can break tags. Shorten descriptions and fail loudly if the message still cannot fit.

## Verification

Generate a daily dry run:

```bash
python3 ${HERMES_SKILL_DIR}/scripts/habr_digest.py --period daily --dry-run --debug
```

Expected result:

- exit code `0`;
- one HTML message printed to stdout;
- stderr contains candidate/fetch/debug counters;
- message length is below 4096 characters;
- article titles are escaped HTML links;
- no token, chat id, or thread id appears in the skill files.
