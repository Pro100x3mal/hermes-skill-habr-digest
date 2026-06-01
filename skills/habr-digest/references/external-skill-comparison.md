# External implementation comparison notes

Source compared during development: an earlier `Pro100x3mal/hermes-skill-habr-digest` implementation.

## Durable lessons

Best community-ready shape for this class of digest:

- Keep the published skill generator-only: collect Habr data, render one standard-Markdown message, print it to stdout.
- Let Hermes cron/gateway deliver stdout to Telegram. Telegram bot credentials and delivery targets belong to Hermes gateway/cron configuration, not to the community skill.
- Avoid direct Telegram Bot API sending in the published skill. It duplicates Hermes delivery, complicates credential handling, and triggers community security-scanner heuristics around secret exfiltration.
- Use standard Markdown, not raw Telegram MarkdownV2. Hermes Telegram adapter converts standard Markdown to MarkdownV2 during delivery.
- For `cron --script --no-agent`, current Hermes requires the cron script path to resolve under `$HERMES_HOME/scripts/`. Skill-local `scripts/` files are linked assets for the agent, not direct no-agent cron script targets. A tiny launcher in `$HERMES_HOME/scripts/` is therefore expected for scheduled runs; it must contain no secrets or delivery targets.
- Use sitemap only for candidate IDs/URLs. Use per-article API as source of truth for title/date/views/comments/score/post type.
- Filter API payloads with `postType == "article"`; sitemap candidates can include non-article content.
- Distinguish legitimate skips from network loss: `None`/skip for filtered, 403/404 delisted/deleted content; explicit sentinel for retryable fetch failures. Retry failed IDs in a second pass with lower concurrency so leader articles are not silently dropped.
- XML parser is more robust than regex for sitemap parsing, even if regex is shorter.
- Never hard-cut the final message. Shrink descriptions safely, then fail loudly if still too long.

## Business-logic fork to decide explicitly

There are two valid digest semantics, but they must not be mixed accidentally:

### Strict original spec

- top-5 by views for period;
- show comments;
- Daily trend = absolute max views in 7-day window;
- Weekly trend = absolute max views in 30-day window;
- no rating/top block.

### Editorial Top variant

- top-5 by views for period;
- show rating/score instead of comments;
- add `🏆 Топ недели/месяца` by `statistics.score`;
- define whether highlight blocks exclude articles already shown in top-5;
- if Trend excludes top-5/Top, document it as "best unseen by views", not absolute trend.

The current skill uses the Editorial Top variant: rating is shown, `🏆` is score-ranked, and `🔥` excludes articles already shown in the top-5 and Top block.

## Concrete pitfalls observed

- `git config` in the GitHub-auth flow does not prompt for a token; only an HTTPS operation requiring authentication (`ls-remote` on a private repo, clone, push) triggers Git credential input.
- `clarify` without `choices` creates an open-ended prompt in Telegram, not buttons. For finite user choices, always pass `choices` explicitly.
- `web_extract` may summarize raw GitHub Markdown and distort examples. Verify published files with `curl -fsSL https://raw.githubusercontent.com/...`, not with summarized extraction.
