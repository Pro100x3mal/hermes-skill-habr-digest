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

```bash
hermes skills tap add Pro100x3mal/hermes-skill-habr-digest
hermes skills install habr-digest
```

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
Create cron jobs for the Habr digest using the habr-digest skill.
```

## Scheduled delivery with Hermes cron

Preferred scheduled delivery is Hermes-native:

```text
Habr skill script -> stdout -> Hermes cron no_agent -> Hermes gateway delivery
```

This keeps Telegram credentials and delivery targets out of the community skill.

### Is a launcher under `~/.hermes/scripts/` required?

For `no_agent` cron jobs, yes — with the current Hermes cron runner.

Hermes skills do have their own `scripts/` directory. Those files are linked skill assets that agents can inspect or run when the skill is loaded. But `hermes cron create --script ... --no-agent` is stricter: it resolves script paths under `$HERMES_HOME/scripts/` and rejects paths outside that directory, including absolute paths and symlinks that resolve elsewhere.

So the installed skill script is the real implementation:

```text
$HERMES_HOME/skills/habr-digest/scripts/habr_digest.py
```

and the cron launcher is just a small scheduler entrypoint:

```text
$HERMES_HOME/scripts/habr_digest_daily.sh
```

It contains no secrets and no Telegram target.

### Daily launcher example

Create `$HERMES_HOME/scripts/habr_digest_daily.sh`:

```bash
#!/usr/bin/env bash
set -euo pipefail

HERMES_HOME="${HERMES_HOME:-$HOME/.hermes}"
exec python3 "$HERMES_HOME/skills/habr-digest/scripts/habr_digest.py" --period daily
```

Make it executable:

```bash
chmod +x ~/.hermes/scripts/habr_digest_daily.sh
```

Weekly/monthly launchers are identical except for `--period weekly` and `--period monthly`.

### Cron jobs

Recommended schedules:

```text
Daily:   0 7 * * *
Weekly:  1 7 * * 1
Monthly: 2 7 1 * *
```

Create jobs:

```bash
hermes cron create "0 7 * * *" \
  --name "Habr daily digest" \
  --script "habr_digest_daily.sh" \
  --no-agent \
  --deliver "telegram:<chat-id>:<thread-id>"

hermes cron create "1 7 * * 1" \
  --name "Habr weekly digest" \
  --script "habr_digest_weekly.sh" \
  --no-agent \
  --deliver "telegram:<chat-id>:<thread-id>"

hermes cron create "2 7 1 * *" \
  --name "Habr monthly digest" \
  --script "habr_digest_monthly.sh" \
  --no-agent \
  --deliver "telegram:<chat-id>:<thread-id>"
```

For chats without forum topics, omit the final `:<thread-id>`.

### Telegram link previews

This skill no longer calls Telegram Bot API directly, so link preview behavior is controlled by the Hermes Telegram gateway adapter. Hermes supports disabling previews through Telegram adapter config (`disable_link_previews`). Verify the actual rendered target message after enabling scheduled delivery.

## Update

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

## Uninstall

Remove the installed skill:

```bash
hermes skills uninstall habr-digest
```

If you added this repository as a tap and no longer need it, remove the tap as well:

```bash
hermes skills tap remove Pro100x3mal/hermes-skill-habr-digest
```

Then remove local launchers and cron jobs you created, for example:

```bash
rm -f ~/.hermes/scripts/habr_digest_daily.sh
rm -f ~/.hermes/scripts/habr_digest_weekly.sh
rm -f ~/.hermes/scripts/habr_digest_monthly.sh
hermes cron list
hermes cron remove <job-id>
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
  https://habr.com/sitemap_articles1.xml -o /tmp/habr_sitemap.xml
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
