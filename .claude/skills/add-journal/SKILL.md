---
name: add-journal
description: Add a biology journal RSS feed to Bio-trend from a feed URL (or journal homepage), then ingest and refresh.
---

# add-journal

Natural-language front door: the user gives a journal name or an RSS feed URL; you
register it and run the pipeline. Run all commands as
`PYTHONNOUSERSITE=1 ./env/bin/bio-trend ...` from the repo root.

## Procedure

1. **Find the feed URL** (if only a journal name/homepage was given). Known patterns:
   - Nature Portfolio: `https://www.nature.com/<code>.rss` (journal) or
     `https://www.nature.com/subjects/<slug>.rss` (subject).
   - Cell Press: `https://www.cell.com/<slug>/current.rss` (and `/inpress.rss`).
   - Science (AAAS): `https://www.science.org/action/showFeed?type=etoc&feed=rss&jc=<code>`.
   Use WebFetch/WebSearch to confirm the exact code/slug if unsure.

2. **Register it** — add a row to `Journal-RSS.md` (Family, Journal, Key, Feed type,
   RSS URL, Bio focus, Status `?`) **and** a matching entry to `config/journals.json`
   (`key`, `label`, `family`, `feeds: [{url, type, bio_focus}]`). A journal may have
   multiple feeds.

3. **Verify** — `bio-trend check-feeds --check`. If the new feed is live, update its
   `Status` to `✓`; if it 403s/dead, mark `✗` and stop (report the problem).

4. **Ingest + refresh** — `bio-trend ingest --journal <key>` then `bio-trend refresh`.

5. **Smoke-check + PR** — confirm `data/<key>/` has a CSV and the new journal appears
   in `docs/data/manifest.json`. Open a PR summarising the added feed.

## Notes

- `bio_focus`: `high` for biology-dedicated journals, `mixed` for multidisciplinary
  flagships (where you may prefer a biology subject feed).
- RSS is a rolling window — the first ingest only captures currently-live items;
  history accrues over subsequent monthly runs.
