# 📊 Habr Digest

Community skill for [Hermes Agent](https://hermes-agent.nousresearch.com) that generates fixed-format Telegram digests of popular Habr articles.

The skill collects article candidates from the Habr sitemap, fetches authoritative article metadata from the per-article Habr API, ranks the main digest by views, renders a single Telegram HTML message, and can send it directly through the Telegram Bot API from a `no_agent` cron job.

## What it does

- Generates daily, weekly, and monthly Habr article digests.
- Ranks the main top-5 by `statistics.readingCount` — views, not rating.
- Uses only:
  - `https://habr.com/sitemap_articles1.xml` for article discovery;
  - `https://habr.com/kek/v2/articles/<id>/?fl=ru&hl=ru` for title, date, views, score, description, and post type.
- Filters records with `postType == "article"`.
- Renders Telegram-safe HTML with article links only on titles.
- Disables Telegram link previews via `link_preview_options.is_disabled=true`.
- Keeps all tokens, chat ids, and thread ids outside the published skill. The Python script does not read secret environment variables directly; wrappers can pass the Telegram token via stdin.

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

The message is squeezed under Telegram's 4096-character limit by shortening descriptions only. If it still cannot fit, the script fails instead of hard-truncating HTML.

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
- Telegram bot token from [@BotFather](https://t.me/botfather) if you want to send messages.
- The Telegram bot must be able to post to the target chat/topic.

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

## Configuration

### Secret: Telegram bot token

For community scanner compatibility, the published Python script does not read secret environment variables directly. Pass the Telegram bot token at runtime, preferably through stdin:

```bash
printf '%s' "$HABR_DIGEST_BOT_TOKEN" | \
  python3 skills/habr-digest/scripts/habr_digest.py \
    --period daily \
    --chat-id "<telegram-chat-id>" \
    --bot-token-stdin
```

For local one-shot testing you can also pass it as an argument, but this can expose the token in shell history or process lists and is not recommended for cron:

```bash
python3 skills/habr-digest/scripts/habr_digest.py \
  --period daily \
  --chat-id "<telegram-chat-id>" \
  --bot-token "<telegram-bot-token>"
```

Do not commit real bot tokens.

### Non-secret delivery settings

Pass delivery settings as runtime arguments:

```bash
--chat-id "<telegram-chat-id>"
--thread-id "<optional-topic-id>"
```

The `thread-id` argument is optional and should be omitted for non-forum chats or General topic delivery.

The skill metadata also documents these non-secret settings for Hermes config-driven setups:

```bash
hermes config set skills.config.habr_digest.telegram_chat_id '<telegram-chat-id>'
hermes config set skills.config.habr_digest.telegram_thread_id '<optional-topic-id>'
```

## Usage

### Dry run

Generate one Telegram HTML message and print it to stdout:

```bash
python3 skills/habr-digest/scripts/habr_digest.py --period daily --dry-run --debug
```

Supported periods:

```text
daily
weekly
monthly
```

### Send one digest to Telegram

```bash
printf '%s' "$HABR_DIGEST_BOT_TOKEN" | \
  python3 skills/habr-digest/scripts/habr_digest.py \
  --period weekly \
  --chat-id "<telegram-chat-id>" \
  --thread-id "<optional-topic-id>" \
  --bot-token-stdin
```

For chats without topics:

```bash
printf '%s' "$HABR_DIGEST_BOT_TOKEN" | \
  python3 skills/habr-digest/scripts/habr_digest.py \
  --period monthly \
  --chat-id "<telegram-chat-id>" \
  --bot-token-stdin
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

## Cron setup

For scheduled delivery, use `no_agent` cron jobs with thin wrapper scripts under `~/.hermes/scripts/`. The wrapper should hold deployment-specific values and should not be committed to this repository.

Example wrapper: `~/.hermes/scripts/habr_digest_daily.sh`

```bash
#!/usr/bin/env bash
set -euo pipefail

bot_token="$(grep '^HABR_DIGEST_BOT_TOKEN=' ~/.hermes/.env | cut -d= -f2-)"

printf '%s' "$bot_token" | python3 "$HOME/.hermes/skills/habr-digest/scripts/habr_digest.py" \
  --period daily \
  --chat-id "<telegram-chat-id>" \
  --thread-id "<optional-topic-id>" \
  --bot-token-stdin
```

Recommended schedules:

```text
Daily:   0 7 * * *
Weekly:  1 7 * * 1
Monthly: 2 7 1 * *
```

Cron jobs should use:

```text
no_agent=true
deliver=local
```

The script sends to Telegram itself. On success it prints an empty line and exits `0`; on failure it writes diagnostics to stderr and exits non-zero.

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

Then delete any deployment-local wrapper scripts and cron jobs you created, for example:

```bash
rm -f ~/.hermes/scripts/habr_digest_daily.sh
rm -f ~/.hermes/scripts/habr_digest_weekly.sh
rm -f ~/.hermes/scripts/habr_digest_monthly.sh
```

Also remove or rotate `HABR_DIGEST_BOT_TOKEN` if it was created only for this skill.

## Validation and security checks

Recommended checks before publishing or updating the skill:

```bash
# Skill metadata and installed-skill audit
hermes skills audit habr-digest --deep

# Python syntax check
python3 -m py_compile skills/habr-digest/scripts/habr_digest.py

# Generic Hermes supply-chain audit for installed dependencies/plugins/MCP servers
hermes security audit --fail-on moderate
```

Notes:

- `tools/skills_guard.py` / Skills Guard is the relevant community-skill scanner. Community skills are blocked on any finding unless installed with force. This skill is structured so the published Python script does not read secret environment variables directly.
- `hermes skills audit --deep` is the installed-skill audit command. It checks installed hub skills and, with `--deep`, performs AST-level analysis on Python files.
- `hermes security audit` queries OSV.dev for known vulnerabilities in the Hermes Python environment, plugin dependency files, and pinned MCP servers. It does not replace a source review of this skill, but it is useful before publishing from a real Hermes environment.
- This skill has no third-party Python dependencies, so the main security risks are committed secrets, unsafe Telegram targets, unexpected network behavior, and script changes.

This repository should never contain:

- real Telegram bot tokens;
- real Telegram chat ids or topic ids;
- GitHub tokens or PATs;
- user-specific wrapper scripts;
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

- `HABR_DIGEST_BOT_TOKEN` is exported in the environment that runs the script.
- `--chat-id` is correct.
- `--thread-id` is a Telegram forum topic id, not a message id.
- The bot is a member/admin of the target chat as required by the chat configuration.

### Message formatting breaks

The script sends with `parse_mode=HTML`; titles and descriptions must be escaped before insertion. Do not replace HTML rendering with Telegram Markdown unless nested bold+italic and links are tested in the actual target platform.

### Digest misses articles

The sitemap `lastmod` is only a discovery filter. Final windows must be filtered by API `timePublished`. Do not replace the collection path with Habr `top/*` pages or search results.

## Contributing

Before opening a PR or publishing an update:

1. Keep `SKILL.md` frontmatter valid and concise.
2. Keep scripts dependency-free unless there is a strong reason to add dependencies.
3. Run the validation commands from the security section.
4. Run at least one `--dry-run --debug` period when `habr.com` is reachable.
5. Verify that no credentials, deployment targets, generated caches, or personal data are committed.
6. Document any change to ranking or highlight semantics in `SKILL.md` and `references/`.

## License

MIT
