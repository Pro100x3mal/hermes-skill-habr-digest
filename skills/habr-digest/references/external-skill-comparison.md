# External implementation comparison notes

Source compared during session: `Pro100x3mal/hermes-skill-habr-digest`.

## Durable lessons

Best production shape for this class of digest:

- Prefer a single `no_agent` script that collects data, renders HTML, and sends via Telegram Bot API itself. Use `deliver=local`; keep cron output quiet on success and non-zero on failure.
- Use `parse_mode=HTML` and disable previews in the Bot API payload with `link_preview_options={"is_disabled": true}`. Do not rely on Telegram Markdown conversion for nested bold+italic.
- Keep config out of code: `HABR_DIGEST_BOT_TOKEN`, `HABR_DIGEST_CHAT_ID`, optional `HABR_DIGEST_THREAD_ID`. Deployment wrappers may still fix a destination topic explicitly, but those wrappers must stay out of the published skill.
- Use sitemap only for candidate IDs/URLs. Use per-article API as source of truth for title/date/views/comments/score/post type.
- Filter API payloads with `postType == "article"`; sitemap candidates can include non-article content.
- Distinguish legitimate skips from network loss: `None`/skip for filtered, 403/404 delisted/deleted content; explicit sentinel for retryable fetch failures. Retry failed IDs in a second pass with lower concurrency so leader articles are not silently dropped.
- XML parser is more robust than regex for sitemap parsing, even if regex is shorter.
- Never hard-cut an HTML Telegram message at 4096 chars; it can break tags/entities. Shrink descriptions safely, then fail loudly if still too long.

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

## Concrete pitfalls observed

- `git config` in the GitHub-auth flow does not prompt for a token; only an HTTPS operation requiring authentication (`ls-remote` on a private repo, clone, push) triggers Git credential input.
- `clarify` without `choices` creates an open-ended prompt in Telegram, not buttons. For finite user choices, always pass `choices` explicitly.
