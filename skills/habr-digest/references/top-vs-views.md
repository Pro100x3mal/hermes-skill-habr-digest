# Habr top pages are not a view-ranking source

Use this note when someone suggests replacing sitemap + article API collection with `top/daily`, `top/weekly`, `top/monthly`, or `top/yearly`.

## Rule

The digest ranks articles by `statistics.readingCount` from the per-article API. Habr `top/*` pages are not a valid source for that ranking.

## Why

- `top/*` pages are rating-oriented collections, not complete view rankings.
- Page order does not match descending `readingCount`.
- Rating thresholds can omit high-view but mid-rated articles.
- The digest must include candidates from the whole time window, then sort by `readingCount` locally.

## Correct collection path

1. Discover recent article ids from `https://habr.com/sitemap_articles1.xml`.
2. Use sitemap `lastmod` only to reduce the candidate set.
3. Fetch each candidate from `https://habr.com/kek/v2/articles/<id>/?fl=ru&hl=ru`.
4. Keep `postType == "article"`.
5. Filter by API `timePublished` for the requested window.
6. Sort by `statistics.readingCount`.

## Security note

Do not store real Telegram bot tokens, chat ids, thread ids, account names, or other deployment data in this reference file. Runtime values belong in `.env`, Hermes skill config, wrapper-local environment variables, or command-line arguments.
