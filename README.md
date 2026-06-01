# 📊 Habr Digest

Community skill for [Hermes Agent](https://hermes-agent.nousresearch.com).

Cron-driven digests of the **top-5 Habr articles by view count** for three
periods — 📅 Daily, 📆 Weekly, 🗓 Monthly — posted as a single Telegram
message. Data comes strictly from the Habr sitemap + per-article API.

## Quick Start

```bash
# 1. Set env vars
export HABR_DIGEST_BOT_TOKEN="<bot-token-from-BotFather>"
export HABR_DIGEST_CHAT_ID="-1001234567890"
# export HABR_DIGEST_THREAD_ID="826"   # optional, for forum topics

# 2. Run
python3 skills/social-media/habr-digest/scripts/habr_digest.py --period daily --dry-run
```

Full setup instructions in [SKILL.md](skills/social-media/habr-digest/SKILL.md).

## Install

```bash
hermes skills tap add Pro100x3mal/hermes-skill-habr-digest
hermes skills install habr-digest
```

## Requirements

- Python 3.x (stdlib only — no pip deps)
- Telegram bot token (from [@BotFather](https://t.me/botfather))
- The bot must be a member/admin of the target chat

## License

MIT
