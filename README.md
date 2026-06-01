# 📊 Habr Digest

Community skill for [Hermes Agent](https://hermes-agent.nousresearch.com).

Cron-driven digests of the **top-5 Habr articles by view count** for three
periods — 📅 Daily, 📆 Weekly, 🗓 Monthly — posted as a single Telegram
HTML message. Data comes strictly from the Habr sitemap + per-article API;
Habr `top/*` pages and search results are not used as ranking sources.

The digest also supports the editorial highlight variant:

- `🏆 Топ недели/месяца` — highest-score article in the highlight window,
  excluding the main top-5;
- `🔥 Тренд недели/месяца` — highest-view article not already shown.

## Quick Start

```bash
# Dry run: generate one HTML Telegram message, do not send
python3 skills/habr-digest/scripts/habr_digest.py --period daily --dry-run --debug

# Send: token from env, chat/thread from runtime arguments
export HABR_DIGEST_BOT_TOKEN="<bot-token>"
python3 skills/habr-digest/scripts/habr_digest.py \
  --period weekly \
  --chat-id "<telegram-chat-id>" \
  --thread-id "<optional-topic-id>"
```

Full setup instructions: [SKILL.md](skills/habr-digest/SKILL.md).

## Install

```bash
hermes skills tap add Pro100x3mal/hermes-skill-habr-digest
hermes skills install habr-digest
```

## Requirements

- Python 3.x (stdlib only — no pip deps)
- Telegram bot token from [@BotFather](https://t.me/botfather)
- The bot must be able to post to the target chat/topic

## Security

Do not commit real Telegram bot tokens, chat ids, thread ids, GitHub tokens,
or wrapper scripts containing deployment-specific values.

## License

MIT
