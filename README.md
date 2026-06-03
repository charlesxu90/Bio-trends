# Bio Trends in Journals

Track what biology is *actually* publishing. **Bio-trend** ingests recent articles
from the flagship biology journals and their sister titles via **RSS**, auto-labels
each with research topics, and surfaces the **top**, **emerging**, and **fading**
areas month over month — with the papers behind every trend a click away.

It is the biology sibling of [AI-trend](../AI-trend/) and reuses its
proven, deterministic pipeline; only the ingestion layer is different (RSS feeds
instead of conference paper dumps).

Families: **Nature · Science · Cell Press** (flagships + key biology sister journals).
Feed catalog: **[Journal-RSS.md](Journal-RSS.md)**.

## What it does

- **Topic trends** — top / emerging / fading topics per journal (or family) per
  month, computed from article counts and month-over-month change.
- **Browse articles** — filter by family / journal / month / topic, search titles,
  abstracts, and authors; sort by recency or citations.
- **Citations** — optional Semantic Scholar / OpenAlex counts, looked up by DOI.
- **Static site** — a fast GitHub Pages browser, rebuilt from the data.

The only non-deterministic step is **topic curation** (deciding which keywords map
to which topic); everything else is pure, reproducible Python.

## How it works

```
Journal-RSS.md ──▶ ingest (poll feeds) ──▶ assign topics ──▶ trends ──▶ static site
(config/journals.json) (data/<key>/<YYYY-MM>.csv)  (substring   (docs/, GitHub Pages)
                        accumulate + dedup by DOI    match vs
                                                     biology taxonomy)
```

RSS feeds are a **rolling window** (latest issue / recent items). Bio-trend polls
them regularly and **accumulates** into a deduplicated per-journal-month store, so
trends build up over time. Running the pipeline with no new items just re-derives
the outputs — safe to run anytime.

**Polling cadence.** Each journal declares a publication **frequency** in
[`Journal-RSS.md`](Journal-RSS.md) / `config/journals.json`
(`continuous` · `weekly` · `biweekly` · `monthly`). `ingest` polls a feed only when
it is *due* — at least its cadence interval since the last poll (tracked in
`data/.ingest_state.json`). So you can run `ingest`/`refresh` on a frequent schedule
(e.g. weekly) and each journal is fetched no more often than it actually publishes;
`--force` overrides the due-check.

## Usage

All commands run from the repo root, isolated from user site-packages:

```bash
PYTHONNOUSERSITE=1 ./env/bin/bio-trend <command>
```

| Command | What it does |
|---|---|
| `check-feeds [--check]` | List tracked feeds (with frequency); `--check` probes each over the network |
| `ingest [--journal KEY] [--force]` | Poll feeds that are *due* per their frequency; accumulate into `data/<key>/<YYYY-MM>.csv` |
| `assign <csv>` | Assign biology topics to a papers CSV (deterministic) |
| `trends [--bucket month\|quarter] [--group-by journal\|family]` | Compute top/emerging/fading |
| `candidates <csv>` | Extract candidate keywords (scispaCy) for taxonomy curation |
| `curate <decision.json>` | Apply a curation decision to the taxonomy |
| `citations <csv> --topics t1,t2` | Fetch citation counts (DOI-first, cached) |
| `export-site` | Rebuild the GitHub Pages data (`docs/data/`) |
| `refresh [--no-ingest]` | Full pipeline: ingest → assign → trends → export-site |

Natural-language front doors (Claude Code skills): **`/add-journal`** (paste a feed
URL), **`/curate-topics`** (biology taxonomy curation), **`/track-journals`**
(verify feeds, discover new bio sister journals, poll & ingest).

### Setup (Python 3.10)

```bash
conda create -y -p ./env python=3.10
PYTHONNOUSERSITE=1 ./env/bin/pip install -e .
# optional extras:
#   '.[curate]'    scispaCy NER for candidate keyword extraction
#   '.[citations]' requests, for Semantic Scholar / OpenAlex citation counts
#   '.[dev]'       pytest + coverage
```

### Quick start

```bash
PYTHONNOUSERSITE=1 ./env/bin/bio-trend check-feeds --check   # confirm feeds are live
PYTHONNOUSERSITE=1 ./env/bin/bio-trend refresh               # ingest → assign → trends → site
python -m http.server --directory docs                       # preview the site
```

## Monthly automation

`.github/workflows/refresh.yml` runs on a monthly cron (and `workflow_dispatch`):
`check-feeds` → `refresh` → open a PR. Merging republishes the site (Pages deploys
from `main` / `/docs`). A `scripts/monthly_refresh.sh` + `monthly_prompt.md` pair is
provided for running the agentic pipeline locally via `claude -p`.

## Adding a journal or feed

1. Add a row to **[Journal-RSS.md](Journal-RSS.md)** and a matching entry to
   `config/journals.json` (`key` / `label` / `family` / `feeds[]`).
2. `bio-trend check-feeds --check` to confirm it's live.
3. `bio-trend refresh`.

See **[CLAUDE.md](CLAUDE.md)** for architecture and the environment rule.
