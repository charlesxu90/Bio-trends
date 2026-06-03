---
name: track-journals
description: Keep Bio-trend's journal feeds current — verify liveness, discover new biology sister journals, then poll and ingest.
---

# track-journals

The watch loop for tracked biology journals. Run commands as
`PYTHONNOUSERSITE=1 ./env/bin/bio-trend ...` from the repo root.

## Procedure

1. **Verify feeds** — `bio-trend check-feeds --check`. For each DEAD feed, try to
   find a working URL (the journal may have changed its RSS path); if found, update
   `Journal-RSS.md` + `config/journals.json`. If not, mark `Status ✗` and note it.

2. **Discover new biology sister journals** (optional, periodic): for each family
   (Nature Portfolio, Science, Cell Press), check whether a notable biology journal
   is missing from `config/journals.json`. If so, follow the `add-journal` skill to
   register and verify its feed. Prefer biology-focused (`bio_focus: high`) titles.

3. **Ingest** — `bio-trend ingest` (all journals) or `--journal <keys>` for a subset.
   This is the step that captures the current rolling window; run it on a schedule
   so history accumulates.

4. **Refresh derived outputs** — `bio-trend refresh --no-ingest` (assign → trends →
   export-site) if you ingested separately, or just `bio-trend refresh` to do both.

5. **Commit / PR** — if `Journal-RSS.md`, `config/`, or `docs/` changed, open a PR
   summarising new articles, journals added, and dead feeds.

## Principles

- Only liveness checks and new-journal discovery touch the network/web; ingestion,
  assignment, trends, and site export are deterministic CLI tools.
- RSS is a rolling window — regular polling is what builds the month-over-month
  history that trends depend on. Don't expect back-history from a single run.
