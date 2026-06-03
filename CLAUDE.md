# CLAUDE.md — Bio-trend architecture & working rules

Bio-trend tracks biology research trends from journal **RSS feeds** (Nature,
Science, Cell families). It is the sibling of `../AI-trend/` and reuses that
project's deterministic pipeline, swapping the ingestion layer (RSS instead of
conference dumps).

## Critical environment rule

Run **everything** isolated from user site-packages, against the repo-local env:

```bash
PYTHONNOUSERSITE=1 ./env/bin/bio-trend <command>
PYTHONNOUSERSITE=1 ./env/bin/python -m pytest --cov=bio_trend
```

The core pipeline needs only `pandas`, `feedparser`, `python-dateutil` (Python
3.10+). The optional `candidates` extra pulls in the **fragile scispaCy stack**
(`scispacy==0.5.1`, `spacy<3.5`, pinned numpy); install it only when curating the
taxonomy, and prefer a 3.10 env.

## Pipeline

```
config/journals.json ─▶ rss.fetch_journal ─▶ ingest.accumulate ─▶ assign ─▶ trends ─▶ site
   (Journal-RSS.md)       (feedparser)        data/<key>/<YYYY-MM>.csv
```

- **`rss.py`** — fetch + normalise feed entries (title, link, DOI, authors,
  abstract, ISO date). Sends a browser `User-Agent` (Science/Cell are
  Cloudflare-protected and 403 a naive client).
- **`ingest.py`** — accumulate into `data/<journal_key>/<YYYY-MM>.csv`, bucketed by
  publication month, **deduped by DOI → link → title**. Idempotent. **Cadence-aware**:
  each journal declares a `frequency` (`continuous`/`weekly`/`biweekly`/`monthly`) and
  is polled only when due, tracked in `data/.ingest_state.json` (`--force` overrides).
- **`assign.py`** — deterministic case-sensitive substring match over lowercased
  `title + " " + abstract`. **Taxonomy keywords must be lowercase** to match.
- **`backfill.py`** — historical fetch from **Crossref** by ISSN (`bio-trend
  backfill --years 2024,2025`), mapped to the same record schema and merged via
  `ingest.accumulate`. Crossref abstracts are often empty for these publishers, so
  backfilled rows are usually assigned on title alone. (OpenAlex source IDs are also
  stored in config — richer abstracts — but its API is unreachable from some egress
  IPs, so Crossref is the default.)
- **`trends.py`** — top/emerging/fading per *(group, period)* where group is a
  journal (default) or family, and period is **year / quarter / month**. The site
  exports all three granularities and defaults to year.
- **`site.py`** — exports `docs/data/{manifest,trends}.json` + per-journal-month
  paper shards for the static GitHub Pages browser in `docs/`. `trends.json` is keyed
  by bucket (`{year, quarter, month}`). `max_shard_months` (`--shard-months`) caps the
  browsable shards to recent months while trends keep full history.
- **`citations.py`** — optional; DOI-first citation lookup, cached in sidecars.
- **`candidates.py` / `curate_io.py`** — the taxonomy-curation seam (scispaCy NER +
  decision apply). The reasoning is done by the `/curate-topics` skill.

## Config is the source of truth

- `config/journals.json` — tracked journals + feeds (mirrors `Journal-RSS.md`); each
  also carries `frequency` (poll cadence), `openalex` (source id) and `issn` (for
  Crossref backfill).
- `config/taxonomy.json` — biology topic → keywords (order significant).
- `config/useless_keywords.json` — noise blocklist.

Adding a journal/feed/topic is a **config edit, not a code change**.

## Data identity comes from file location

A row's journal = its folder name (`data/<key>/`); its period = the filename stem
(`2026-06`). In-file columns are for display, not identity — same discipline as
AI-trend.

## Tests

`PYTHONNOUSERSITE=1 ./env/bin/python -m pytest`. The deterministic core (assign,
trends, ingest, registry, curate_io, site, refresh, rss parsing) is covered ≥80%.
Network (`citations`) and model (`candidates`) modules are optional extras and are
exercised via mocks / left to manual runs, mirroring AI-trend.

## Gotchas

- RSS feeds only carry recent items — history is built by **repeated polling**, so
  the first `ingest` captures only what is currently live.
- DOIs are present in most feeds but not all (some Nature subject-feed entries lack
  them); dedup falls back to link, then title.
- Science `jc=` codes and Nature subject slugs were verified live via
  `check-feeds`; re-verify after any feed edit.
