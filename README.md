# 📊 Habr Digest

Community skill for [Hermes Agent](https://hermes-agent.nousresearch.com) that generates fixed-format Habr digests as standard Markdown messages.

The skill collects article candidates from the Habr sitemap, fetches authoritative article metadata from the per-article Habr API, ranks the main digest by views, and prints exactly one message to stdout. Delivery is intentionally delegated to Hermes cron/gateway.

## What it does

- Generates daily, weekly, and monthly Habr article digest messages.
- Ranks the main top-5 by `statistics.readingCount` — views, not rating.
- Uses only:
  - `https://habr.com/sitemap_articles1.xml` for article discovery;
  - `https://habr.com/kek/v2/articles/<id>/?fl=ru&hl=ru` for title, date, views, score, description, and post type.
- Filters records with `postType == "article"`.
- Renders standard Markdown suitable for Hermes Telegram gateway conversion to MarkdownV2.
- Keeps all tokens, chat ids, and thread ids outside the published skill.

It intentionally does **not** use Habr `top/daily`, `top/weekly`, `top/monthly`, `top/yearly`, or search results as ranking sources. Those pages are rating-oriented and can omit high-view articles.

## Digest format

Main block for every period:

```text
📊 Хабр дайджест - 📅 Daily / 📆 Weekly / 🗓 Monthly
Самые популярные статьи за сутки / неделю / месяц
1️⃣..5️⃣ article titles, descriptions, publication date, views, rating
```

Additional editorial highlights:

- Daily:
  - `🏆 Топ недели` — highest-score article in the 7-day highlight window, excluding the main top-5.
  - `🔥 Тренд недели` — highest-view article in the 7-day highlight window, excluding articles already shown.
- Weekly:
  - `🏆 Топ месяца` — highest-score article in the 30-day highlight window, excluding the main top-5.
  - `🔥 Тренд месяца` — highest-view article in the 30-day highlight window, excluding articles already shown.
- Monthly:
  - no highlight blocks.

The message is squeezed under 3900 characters by shortening descriptions only. If it still cannot fit, the script fails instead of hard-truncating Markdown.

## Repository layout

```text
skills/habr-digest/
├── SKILL.md
├── scripts/
│   └── habr_digest.py
└── references/
    ├── external-skill-comparison.md
    └── top-vs-views.md
```

`habr_digest.py` uses only the Python standard library. No `pip install` step is required.

## Requirements

- Hermes Agent.
- Python 3.10+.
- Network access to `habr.com`.
- For scheduled Telegram delivery: configured Hermes Telegram gateway and a valid cron `--deliver` target.

The skill itself does not require a Telegram bot token. Telegram credentials belong to Hermes gateway configuration.

## Installation

### From this GitHub tap

Add the tap:

```bash
hermes skills tap add Pro100x3mal/hermes-skill-habr-digest
```

Install with the deterministic full identifier:

```bash
hermes skills install Pro100x3mal/hermes-skill-habr-digest/skills/habr-digest
```

Why not `hermes skills install habr-digest` here? Because short-name resolution for third-party taps has been observed to hang on some Hermes versions. The full identifier works reliably and is the safer published instruction.

Verify that Hermes sees it:

```bash
hermes skills list | grep habr-digest
hermes skills inspect habr-digest
```

### From Skills Hub, after community publication

Once the skill is accepted into Skills Hub community, installation should be:

```bash
hermes skills search habr-digest
hermes skills install <hub-id-for-habr-digest>
```

Use the exact id returned by `hermes skills search`, because hub identifiers can include namespace/category prefixes.

## Usage

### Generate a digest message

```bash
python3 skills/habr-digest/scripts/habr_digest.py --period daily --debug
```

Supported periods:

```text
daily
weekly
monthly
```

The script always prints the digest to stdout. Diagnostics go to stderr. The legacy `--dry-run` flag is accepted as a no-op for compatibility:

```bash
python3 skills/habr-digest/scripts/habr_digest.py --period weekly --dry-run --debug
```

### Load the skill in Hermes

In a Hermes session:

```text
/skill habr-digest
```

or ask naturally, for example:

```text
Запусти habr digest daily в 07:00 с отправкой в telegram chatID <chat-id> threadID <thread-id>.
```

### Natural-language triggers for agents

The skill is designed so an agent can treat Habr digest scheduling as a lifecycle task, not as a manual file-editing exercise.

Typical user intents:

- `create`: start a new digest job;
- `update`: change schedule, period, or delivery target;
- `pause`: temporarily stop a digest job;
- `resume`: re-enable a paused digest job;
- `remove`: permanently stop and delete a digest job.

Example trigger phrases:

```text
Create:
- Запусти habr digest daily в 07:00 с отправкой в telegram chatID <chat-id> threadID <thread-id>.
- Создай еженедельный Habr digest по понедельникам в 07:00 и отправляй в этот топик.

Update:
- Перенеси daily digest с 07:00 на 08:30.
- Обнови weekly digest: отправляй в chatID <chat-id> threadID <thread-id>.
- Смени monthly digest на расписание 2 8 1 * *.

Pause / resume:
- Поставь weekly Habr digest на паузу.
- Возобнови monthly Habr digest.

Remove:
- Останови daily Habr digest для этого топика.
- Удали weekly Habr digest из telegram chatID <chat-id> threadID <thread-id>.
```

Expected agent behavior:

1. Parse intent, period, schedule, and delivery target from the prompt.
2. Ask at most one precise follow-up question if one required field is missing.
3. Inspect existing cron jobs before creating anything.
4. Create or update a deterministic launcher under `$HERMES_HOME/scripts/`.
5. Create, edit, pause, resume, or remove the Hermes cron job in `no_agent` mode.
6. Verify the resulting job state instead of assuming success.

The user should not be asked to create launcher files manually.

## Scheduled delivery with Hermes cron

Preferred scheduled delivery is Hermes-native:

```text
Habr skill script -> stdout -> Hermes cron no_agent -> Hermes gateway delivery
```

This keeps Telegram credentials and delivery targets out of the community skill.

### Is a launcher under `$HERMES_HOME/scripts/` required?

For `no_agent` cron jobs, yes — with the current Hermes cron runner.

Hermes skills do have their own `scripts/` directory. Those files are linked skill assets that agents can inspect or run when the skill is loaded. But `hermes cron create --script ... --no-agent` is stricter: it resolves script paths under `$HERMES_HOME/scripts/` and rejects paths outside that directory, including absolute paths and symlinks that resolve elsewhere.

So the installed skill script is the real implementation:

```text
$HERMES_HOME/skills/habr-digest/scripts/habr_digest.py
```

and the cron launcher is just a small scheduler entrypoint, for example:

```text
$HERMES_HOME/scripts/habr_digest_daily__chat_<chat-id>__thread_<thread-id>.sh
```

It contains no secrets and no Telegram target.

### Launcher rule for scheduled no-agent jobs

Agents should create deterministic launcher names so different chats/topics do not collide:

```text
$HERMES_HOME/scripts/habr_digest_<period>__chat_<chat-id>__thread_<thread-id-or-root>.sh
```

Example:

```text
$HERMES_HOME/scripts/habr_digest_daily__chat_<chat-id>__thread_<thread-id>.sh
```

Launcher content example:

```bash
#!/usr/bin/env bash
set -euo pipefail

HERMES_HOME="${HERMES_HOME:-$HOME/.hermes}"
exec python3 "$HERMES_HOME/skills/habr-digest/scripts/habr_digest.py" --period daily
```

Make it executable:

```bash
chmod +x $HERMES_HOME/scripts/habr_digest_daily__chat_<chat-id>__thread_<thread-id>.sh
```

Weekly/monthly launchers are identical except for `--period weekly` and `--period monthly`.

### Cron jobs

Recommended schedules:

```text
Daily:   0 7 * * *
Weekly:  1 7 * * 1
Monthly: 2 7 1 * *
```

Recommended deterministic job-name pattern:

```text
Habr <period> digest -> telegram:<chat-id>:<thread-id-or-root>
```

Create jobs:

```bash
hermes cron create "0 7 * * *" \
  --name "Habr daily digest -> telegram:<chat-id>:<thread-id>" \
  --script "habr_digest_daily__chat_<chat-id>__thread_<thread-id>.sh" \
  --no-agent \
  --deliver "telegram:<chat-id>:<thread-id>"

hermes cron create "1 7 * * 1" \
  --name "Habr weekly digest -> telegram:<chat-id>:<thread-id>" \
  --script "habr_digest_weekly__chat_<chat-id>__thread_<thread-id>.sh" \
  --no-agent \
  --deliver "telegram:<chat-id>:<thread-id>"

hermes cron create "2 7 1 * *" \
  --name "Habr monthly digest -> telegram:<chat-id>:<thread-id>" \
  --script "habr_digest_monthly__chat_<chat-id>__thread_<thread-id>.sh" \
  --no-agent \
  --deliver "telegram:<chat-id>:<thread-id>"
```

For chats without forum topics, omit the final `:<thread-id>` from `--deliver` and use `thread_root` in the deterministic launcher/job naming.

Update an existing job instead of creating duplicates when the same digest already exists for the same period and target:

```bash
hermes cron edit <job-id> \
  --schedule "30 8 * * *" \
  --name "Habr daily digest -> telegram:<chat-id>:<thread-id>" \
  --script "habr_digest_daily__chat_<chat-id>__thread_<thread-id>.sh" \
  --no-agent \
  --deliver "telegram:<chat-id>:<thread-id>"
```

Pause, resume, and remove examples:

```bash
hermes cron pause <job-id>
hermes cron resume <job-id>
hermes cron remove <job-id>
```

Before destructive removal, inspect existing jobs first:

```bash
hermes cron list --all
```

### Telegram link previews

This skill no longer calls Telegram Bot API directly, so link preview behavior is controlled by the Hermes Telegram gateway adapter. Hermes supports disabling previews through Telegram adapter config (`disable_link_previews`). Verify the actual rendered target message after enabling scheduled delivery.

## Update

There are two different update paths here. Do not confuse them.

### 1. Update the installed skill package

Check for updates:

```bash
hermes skills check
```

Update installed hub/tap skills:

```bash
hermes skills update
```

If installed from a tap and the tap source changes, make sure the tap is still configured:

```bash
hermes skills tap list
```

### 2. Update an already configured digest job

This is not a skill-package update. It is a cron lifecycle update.

Typical natural-language requests:

```text
- Перенеси daily digest на 08:30.
- Смени weekly digest на другой telegram thread.
- Обнови monthly digest и отправляй в этот чат.
```

Expected agent action:

1. Inspect existing cron jobs.
2. Find the matching digest by `period` and target.
3. Preserve unchanged fields.
4. Rewrite launcher/job naming if target or period changes.
5. Run `hermes cron edit ...` instead of creating a duplicate job.
6. Verify the stored job definition afterward.


## Stop or uninstall

Three different operations exist here. They are not the same.

### 1. Stop one digest job temporarily

Natural-language examples:

```text
- Поставь daily Habr digest на паузу.
- Pause weekly Habr digest for this topic.
```

CLI action:

```bash
hermes cron list --all
hermes cron pause <job-id>
```

### 2. Stop one digest job permanently

Natural-language examples:

```text
- Останови daily Habr digest для этого топика.
- Удали weekly Habr digest из telegram chatID <chat-id> threadID <thread-id>.
```

CLI action:

```bash
hermes cron list --all
hermes cron remove <job-id>
```

Delete the matching launcher only if no remaining cron job references it.

### 3. Uninstall the skill package itself

Remove the installed skill:

```bash
hermes skills uninstall habr-digest
```

If you added this repository as a tap and no longer need it, remove the tap as well:

```bash
hermes skills tap remove Pro100x3mal/hermes-skill-habr-digest
```

Then remove any unreferenced local launchers, for example:

```bash
rm -f "$HERMES_HOME/scripts/habr_digest_daily__chat_<chat-id>__thread_<thread-id>.sh"
rm -f "$HERMES_HOME/scripts/habr_digest_weekly__chat_<chat-id>__thread_<thread-id>.sh"
rm -f "$HERMES_HOME/scripts/habr_digest_monthly__chat_<chat-id>__thread_<thread-id>.sh"
```

Do not remove Hermes Telegram credentials unless they were created only for this workflow.

## Validation and security checks

Recommended checks before publishing or updating the skill:

```bash
# Community skill scanner / installed-skill audit
hermes skills audit habr-digest --deep

# Python syntax check
python3 -m py_compile skills/habr-digest/scripts/habr_digest.py

# Generic Hermes supply-chain audit for installed dependencies/plugins/MCP servers
hermes security audit --fail-on moderate
```

Notes:

- `tools/skills_guard.py` / Skills Guard is the relevant community-skill scanner. Community skills are blocked on caution/dangerous findings unless policy or force flags say otherwise.
- `hermes skills audit --deep` is the installed-skill audit command. It checks installed hub skills and, with `--deep`, performs AST-level analysis on Python files.
- `hermes security audit` queries OSV.dev for known vulnerabilities in the Hermes Python environment, plugin dependency files, and pinned MCP servers. It does not replace a source review of this skill.
- This skill has no third-party Python dependencies, no secret environment variables, and no direct Telegram Bot API sender.

This repository should never contain:

- real Telegram bot tokens;
- real Telegram chat ids or topic ids;
- GitHub tokens or PATs;
- user-specific cron launchers;
- generated `__pycache__/` or `.pyc` files.

## Troubleshooting

### Habr request times out

Check direct connectivity from the host:

```bash
curl -L --connect-timeout 10 --max-time 40 \
  -A 'Mozilla/5.0 (compatible; HermesHabrDigest/1.0)' \
  https://habr.com/sitemap_articles1.xml -o "${TMPDIR:-/tmp}/habr_sitemap.xml"
```

If this times out, the digest cannot run from that host until network access to `habr.com:443` works.

### Telegram message is not delivered

Check:

- Hermes Telegram gateway is configured and running.
- The `--deliver` target is correct.
- For forum topics, the delivery target includes the topic/thread id.
- The Telegram bot configured in Hermes can post to the target chat/topic.

### Message formatting breaks

The script outputs standard Markdown. Hermes Telegram adapter converts standard Markdown to Telegram MarkdownV2. If formatting changes, test actual delivery in Telegram; do not rely only on source Markdown inspection.

### Link previews appear

This is controlled by the Hermes Telegram adapter, not by this skill. Enable/verify `disable_link_previews` in the Telegram gateway configuration and resend a test digest.

### Digest misses articles

The sitemap `lastmod` is only a discovery filter. Final windows must be filtered by API `timePublished`. Do not replace the collection path with Habr `top/*` pages or search results.

## Contributing

Before opening a PR or publishing an update:

1. Keep `SKILL.md` frontmatter valid and concise.
2. Keep scripts dependency-free unless there is a strong reason to add dependencies.
3. Run the validation commands from the security section.
4. Run at least one `--period daily --debug` when `habr.com` is reachable.
5. Verify that no credentials, deployment targets, generated caches, or personal data are committed.
6. Document any change to ranking or highlight semantics in `SKILL.md` and `references/`.

## License

MIT
