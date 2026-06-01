# Why `top/*` cannot be used for a top-by-views digest

Evidence base (collected against the live Habr site). Read this if someone asks
again "why not just use the ready-made top/monthly|weekly|yearly collections".

## In one line

`top/*` sorts by **rating** (`statistics.score` = upvotes − downvotes), while
the digest spec is top by **views** (`statistics.readingCount`). Different
metrics, different order → `top/*` yields the wrong top-5. It also drops
articles below a rating threshold, losing high-view-but-mid-rated articles.

## How this was verified

### 1. The parametric API `?sort=rating&period=monthly` returns garbage
A direct call to `kek/v2/articles/?sort=rating&period=monthly&...` returned
articles with `score=0` and `views≤234` — this is NOT the real top/monthly
collection; the parameter combination does not reproduce the site's feed. Do
not rely on this path.

### 2. The reliable method — intercept the SSR page
`https://habr.com/ru/articles/top/monthly/` is server-rendered and carries an
embedded JSON state with per-article statistics. Extract it like so:

```bash
curl -s 'https://habr.com/ru/articles/top/monthly/' \
  -H 'User-Agent: Mozilla/5.0' -H 'Accept-Language: ru' -o /tmp/topm.html
# the HTML contains "period":"monthly", "score":NNN, "readingCount":NNN
python3 - <<'PY'
import re
html=open('/tmp/topm.html').read()
arts=re.findall(r'"titleHtml":"(.*?)".{0,4000}?"readingCount":(\d+),"score":(-?\d+)', html)
rows=[(int(s),int(v),t[:46]) for t,v,s in arts]
print("page order (score-ranked):")
for s,v,t in rows[:7]: print(f"score={s:>4} views={v:>7} {t}")
print("same, re-sorted by views:")
for s,v,t in sorted(rows,key=lambda r:r[1],reverse=True)[:7]:
    print(f"views={v:>7} score={s:>4} {t}")
PY
```

### 3. What the run showed
- Articles on page 1 of top/monthly had `score` 150–600 — i.e. a rating
  threshold.
- The page order by views is NOT descending (65k, 45k, 36k, 18k, 50k…) — so the
  sort is not by views.
- The #1 by views (≈200,500) was NOT first on the page.
- Our pipeline (sitemap → API → sort by readingCount) produced the same #1 by
  views (200,537); the top/monthly page showed 200,547 for the same article.
  The ~10-view difference is just request timing. **Conclusion: our view
  parsing is correct; the problem with `top/*` is the sort metric, not the
  data.**

## The only use of `top/*` (for the future)
A per-period top page fits in ~18–50 articles instead of ~6500. IF the criterion
ever changes to "by rating", `top/*` would cut the run from minutes to seconds.
Under the current "by views" criterion it is not applicable.
