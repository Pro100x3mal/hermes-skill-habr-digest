---
name: habr-digest
description: Build Habr top-by-views digest messages.
version: 1.2.2
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
- Habr sitemap: `https://habr.com/sitemap_articles1.xml` used as an article-ID seed, not as a publication-time or completeness filter
- Article API: `https://habr.com/kek/v2/articles/<id>/?fl=ru&hl=ru`
- Output: one standard-Markdown message on stdout
- Main ranking: top-5 by `statistics.readingCount`
- Daily summary window: rolling 1 day from run time
- Weekly summary window: rolling 7 days from run time
- Monthly summary window: rolling 30 days from run time
- Daily highlight window: rolling 7 days from run time
- Weekly highlight window: rolling 30 days from run time
- Monthly highlights: none
- Target message length: ≤ 3900 characters before Hermes delivery

## Procedure

1. Compute `now` and period windows in Europe/Moscow time, fixed UTC+03:00.
2. Fetch article candidates from `sitemap_articles1.xml` as a recent article-ID seed.
3. Add a direct API scan above the newest sitemap ID so delayed sitemap refreshes do not hide already-published articles.
4. Do not use sitemap `lastmod` as a completeness/publication filter.
5. Fetch every candidate through the per-article API.
6. Keep only records with `postType == "article"`.
7. Filter final pools by API `timePublished`, not by sitemap `lastmod`.
8. Sort the main pool by views descending, then score, comments, publication time, and id.
9. Render exactly top-5 articles by views; fail hard if the main window has fewer than 5 articles.
10. For daily and weekly, add two non-duplicate highlight blocks:
   - `🏆 Топ недели/месяца` — highest score in the highlight window, excluding the main top-5.
   - `🔥 Тренд недели/месяца` — highest views in the highlight window, excluding the main top-5 and selected top article.
11. Fit the message under the target length by shortening descriptions only.
12. Print the message to stdout; let Hermes cron/gateway deliver it.

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

Current Hermes cron behavior matters in two separate ways:

1. `cron --script` executes only files under `$HERMES_HOME/scripts/`. Scripts inside an installed skill directory are linked skill assets for agents, but they are not directly executable by `cron --script --no-agent`. Absolute paths and symlinks outside `$HERMES_HOME/scripts/` are rejected by the cron runner.
2. `cron --script` does not provide a per-job argv mechanism. This skill's bundled script requires `--period daily|weekly|monthly`.

Therefore scheduled no-agent runs need a tiny launcher under `$HERMES_HOME/scripts/`. The launcher is not part of the skill's own internal structure and exists only to adapt Hermes cron's current script-runner constraints. It contains no secrets and no Telegram target; it only calls the installed skill script with the needed `--period` value.

Separate from script launching, Hermes cron delivery itself can wrap the final stdout with a header/footer. That wrapper is applied after this skill prints its message, so the skill cannot remove it from inside `habr_digest.py`. If clean delivery is required, disable the global Hermes setting `cron.wrap_response`.

### Natural-language lifecycle workflow for agents

When a user asks in natural language to schedule, change, pause, resume, or stop this skill — for example, "Запусти habr digest daily в 07:00 с отправкой в telegram chatID ... threadID ..." — the agent should treat it as an orchestration task and complete it end-to-end.

Supported intents:

- `create`: start a new daily/weekly/monthly digest;
- `update`: change an existing digest's schedule, target, or period;
- `pause`: temporarily stop an existing digest without deleting it;
- `resume`: re-enable a paused digest;
- `remove`: permanently stop and delete an existing digest.

Intent triggers from natural language:

- `create`: "запусти", "создай", "настрой", "добавь", "schedule", "start";
- `update`: "измени", "обнови", "перенеси", "смени время", "change schedule", "retarget";
- `pause`: "поставь на паузу", "pause", "temporarily stop";
- `resume`: "возобнови", "resume", "enable again";
- `remove`: "останови", "удали", "убери", "stop digest", "delete cron".

Required fields to resolve:

- `period`: one of `daily`, `weekly`, `monthly`;
- `schedule`: a concrete Hermes cron schedule string for `create` and schedule-changing `update`;
- `deliver`: Telegram target in the form `telegram:<chat-id>` or `telegram:<chat-id>:<thread-id>` when the target matters.

Resolution rules:

1. Parse intent first, then parse `period`, `schedule`, and Telegram target from the user's prompt.
2. If one required field is missing, ask one precise follow-up question only for that field.
3. Prefer explicit Telegram IDs from the user. If the user only says "send to this chat" or equivalent, the agent may use the current origin target.
4. If the user asks to change only one property, preserve the existing values for the other properties.
5. If the request clearly refers to an already running digest for the same `period` and Telegram target, treat it as `update`, not `create`.
6. If multiple existing jobs match the user's request and the intended one is not obvious, ask one precise disambiguation question.

Deterministic naming:

- Launcher path pattern:
  - `habr_digest_<period>__chat_<chat-id>__thread_<thread-id-or-root>.sh`
- Recommended job name pattern:
  - `Habr <period> digest -> telegram:<chat-id>:<thread-id-or-root>`

Create/update workflow:

1. Inspect existing cron jobs before writing anything.
2. Match candidate jobs by `period` plus Telegram target. Prefer an exact match on launcher script and `deliver` target.
3. Build a deterministic launcher path under `$HERMES_HOME/scripts/` using the resolved period and delivery target so different chats/topics do not collide.
4. Write the launcher so it only executes the installed skill script with the resolved `--period` value.
5. Mark the launcher executable.
6. If an exact job already exists for the same `period` and Telegram target, update that job instead of creating a duplicate.
7. If a matching job exists but the request changes target or period, update the job and rewrite the launcher name/path so the runtime state stays deterministic.
8. Create or update the Hermes cron job in `no_agent` mode with that launcher and the resolved `deliver` target.
9. Verify success by checking the stored cron job definition after creation/update.

Pause/resume/remove workflow:

1. Inspect existing cron jobs first.
2. Match the target job by `period` and Telegram target when available; otherwise fall back to the deterministic launcher/job naming pattern.
3. For `pause`, pause the matched job.
4. For `resume`, resume the matched job.
5. For `remove`, remove the matched job and delete the matching launcher only if no remaining cron job references it.
6. Verify the final state after the lifecycle action.

The launcher creation is an implementation detail. The user should not be asked to create or edit launcher files manually.

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
  --name "Habr daily digest -> telegram:<chat-id>:<thread-id>" \
  --script "habr_digest_daily__chat_<chat-id>__thread_<thread-id>.sh" \
  --no-agent \
  --deliver "telegram:<chat-id>:<thread-id>"
```

For chats without topics, omit the final `:<thread-id>`.

Launcher naming example:

```text
$HERMES_HOME/scripts/habr_digest_daily__chat_<chat-id>__thread_<thread-id-or-root>.sh
```

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
10. Telegram link-preview suppression is a gateway/platform concern, not a skill concern. In Hermes, the Telegram adapter only disables previews when `telegram.disable_link_previews: true` is set in gateway config. The skill's Markdown output alone cannot force cron delivery to suppress previews.

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
