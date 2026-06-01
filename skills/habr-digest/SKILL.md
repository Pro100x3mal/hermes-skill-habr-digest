---
name: habr-digest
description: Build Habr top-by-views digest messages.
version: 1.1.0
author: Hermes Agent
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [habr, research, telegram, digest, cron]
    related_skills: [hermes-agent]
    requires_toolsets: [terminal]
---

# Habr Digest Skill

Builds fixed-format Habr article digests from the Habr sitemap and per-article API, then prints one standard-Markdown message to stdout. Delivery is intentionally handled by Hermes cron/gateway, not by this skill.

This skill ranks the main top-5 by views, never by Habr `top/*` pages, and never by search results. It contains no Telegram tokens, chat ids, thread ids, or account-specific values.

Implementation tradeoffs and the comparison against the earlier external implementation are captured in `references/external-skill-comparison.md`; consult it before changing collection, retry, rendering, or highlight-block semantics.

## When to Use

Use this skill when the task is to:

- generate daily, weekly, or monthly Habr article digest messages;
- schedule Habr digests with Hermes cron;
- debug Habr collection, ranking, or Telegram formatting;
- verify that a digest is generated from Habr's sitemap plus article API only.

Do not use it for Habr news, company feeds, search-result summaries, or rating-based digests sourced from `top/daily`, `top/weekly`, `top/monthly`, or `top/yearly`.

## Prerequisites

Runtime requirements:

- Python 3.10+.
- Network access to `https://habr.com`.
- For scheduled Telegram delivery: a configured Hermes Telegram gateway/home or explicit cron delivery target.

The skill itself requires no secrets and declares no `required_environment_variables`. Telegram credentials belong to Hermes gateway configuration, not to this skill.

## How to Run

Use the `terminal` tool to invoke the bundled script.

Generate a daily message:

```bash
python3 ${HERMES_SKILL_DIR}/scripts/habr_digest.py --period daily --debug
```

Supported periods:

```text
daily
weekly
monthly
```

The script always writes the user-facing digest to stdout. Diagnostics go to stderr. The legacy `--dry-run` flag is accepted as a no-op for compatibility.

## Quick Reference

- Script: `${HERMES_SKILL_DIR}/scripts/habr_digest.py`
- Habr sitemap: `https://habr.com/sitemap_articles1.xml`
- Article API: `https://habr.com/kek/v2/articles/<id>/?fl=ru&hl=ru`
- Output: one standard-Markdown message on stdout
- Main ranking: top-5 by `statistics.readingCount`
- Daily summary window: 1 day
- Weekly summary window: 7 days
- Monthly summary window: 30 days
- Daily highlight window: 7 days
- Weekly highlight window: 30 days
- Monthly highlights: none
- Target message length: ≤ 3900 characters before Hermes delivery

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
10. Fit the message under the target length by shortening descriptions only.
11. Print the message to stdout; let Hermes cron/gateway deliver it.

## Output Format

The script renders exactly one standard-Markdown message:

```markdown
**📊 Хабр дайджест** - *📅 Daily*
Самые популярные статьи за **сутки** 🔝
➖➖➖➖➖➖➖➖➖➖➖➖

1️⃣ [Title](https://habr.com/ru/articles/123456/)
Description

📅 Дата: **YYYY-MM-DD HH:MM**
👁 Просмотры: **N**
⭐ Рейтинг: **N**
```

Rules:

- article links appear only on article titles;
- no bare URLs;
- no search results;
- no parsing statistics in the user-facing message;
- monthly has no `🔥` or `🏆` highlight blocks;
- descriptions may be shortened, fields and labels must not be silently dropped.

## Cron Setup

Preferred scheduled delivery is Hermes-native:

1. The skill script generates stdout.
2. Hermes cron runs a no-agent job.
3. Hermes gateway delivers stdout to Telegram.

Current Hermes cron behavior matters: `cron --script` executes only files under `$HERMES_HOME/scripts/`. Scripts inside an installed skill directory are linked skill assets for agents, but they are not directly executable by `cron --script --no-agent`. Absolute paths and symlinks outside `$HERMES_HOME/scripts/` are rejected by the cron runner.

Therefore scheduled no-agent runs need a tiny launcher under `$HERMES_HOME/scripts/`. The launcher contains no secrets and no Telegram target; it only calls the installed skill script.

Launcher pattern:

```bash
#!/usr/bin/env bash
set -euo pipefail

HERMES_HOME="${HERMES_HOME:-$HOME/.hermes}"
exec python3 "$HERMES_HOME/skills/habr-digest/scripts/habr_digest.py" --period daily
```

Cron delivery example:

```bash
hermes cron create "0 7 * * *" \
  --name "Habr daily digest" \
  --script "habr_digest_daily.sh" \
  --no-agent \
  --deliver "telegram:<chat-id>:<thread-id>"
```

For chats without topics, omit the final `:<thread-id>`.

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
6. Do not hardcode credentials or targets in SKILL.md, scripts, tests, references, or public examples.
7. The output is standard Markdown because Hermes Telegram gateway converts it to Telegram MarkdownV2. Do not replace it with raw Telegram MarkdownV2 unless actual gateway delivery is tested.
8. Do not hard-truncate the final message; it can break links or formatting. Shorten descriptions and fail loudly if the message still cannot fit.
9. Direct Telegram Bot API sending does not belong in this community skill. Use Hermes gateway delivery instead.

## Verification

Generate a daily message:

```bash
python3 ${HERMES_SKILL_DIR}/scripts/habr_digest.py --period daily --debug
```

Expected result:

- exit code `0`;
- one Markdown message printed to stdout;
- stderr contains candidate/fetch/debug counters;
- message length is below 3900 characters;
- article titles are Markdown links;
- no token, chat id, or thread id appears in the skill files.

For Telegram delivery verification, send through Hermes gateway/cron and inspect the rendered target message. Do not assume source Markdown equals Telegram rendering.
