# Journal RSS Sources

RSS feed sources for every tracked biology journal. This is the human-maintained
index the pipeline ingests from: each row's **RSS URL** feeds `bio-trend ingest`
(via [`config/journals.json`](config/journals.json), the machine-readable mirror of
this table). Extend it as new feeds appear, and re-check existing links with
`bio-trend check-feeds --check`.

Scope: the three flagships (**Nature**, **Science**, **Cell**) plus their
biology-relevant sister journals. Biology is isolated at the **journal / subject
level** — most rows are bio-focused journals; the multidisciplinary flagships add a
biology **subject feed** (Nature) where available so their signal is not diluted.

## Columns

- **Family** — publisher family: `Nature` (Nature Portfolio), `Science` (AAAS), `Cell Press`.
- **Journal** — human-readable journal name.
- **Key** — stable id used for the data store (`data/<key>/<YYYY-MM>.csv`) and in `journals.json`.
- **Feed type** — `subject` (subject-filtered), `journal`/`etoc`/`current` (latest table of contents).
- **Frequency** — the journal's publication cadence; **Bio-trend polls each feed at
  this frequency** (see below).
- **RSS URL** — the feed `feedparser` fetches.
- **Bio focus** — `high` (mostly biology) or `mixed` (multidisciplinary; biology is a subset).
- **Status** — `✓` verified live · `?` unverified (confirm with `check-feeds`) · `✗` dead.

## Polling cadence

Bio-trend tracks each journal at its declared **Frequency**. `bio-trend ingest`
polls a feed only when it is *due* — i.e. at least its cadence interval has elapsed
since the last poll (recorded in `data/.ingest_state.json`):

| Frequency | Polled at most every | Typical journals |
|-----------|----------------------|------------------|
| `continuous` | every run | online-first titles (Nature Communications, Science Advances, Cell Reports) |
| `weekly` | 7 days | Nature, Science, Sci. Transl. Med., Sci. Signaling |
| `biweekly` | 14 days | Cell, Molecular Cell, Neuron, Current Biology, Developmental Cell |
| `monthly` | 30 days | the monthly Nature/Cell sister titles, Science Immunology |

Run `bio-trend ingest` (or `refresh`) on a frequent schedule — e.g. weekly — and
each journal is fetched no more often than its cadence; pass `--force` to poll every
feed regardless of when it was last seen.

> RSS feeds are a **rolling window** (latest issue / recent items only). Bio-trend
> accumulates entries into a deduplicated store (dedupe by DOI → link → title), so
> history builds up across polls.

## Nature Portfolio

Pattern: `https://www.nature.com/<code>.rss` (journal) and
`https://www.nature.com/subjects/<slug>.rss` (subject). Served without bot
challenge. Items carry title, link, description, **DOI**, authors, and ISO dates.

| Family | Journal | Key | Feed type | Frequency | RSS URL | Bio focus | Status |
|--------|---------|-----|-----------|-----------|---------|-----------|--------|
| Nature | Nature | nature | subject | weekly | https://www.nature.com/subjects/biological-sciences.rss | high | ✓ |
| Nature | Nature | nature | journal | weekly | https://www.nature.com/nature.rss | mixed | ✓ |
| Nature | Nature Methods | nmeth | journal | monthly | https://www.nature.com/nmeth.rss | high | ✓ |
| Nature | Nature Genetics | ng | journal | monthly | https://www.nature.com/ng.rss | high | ✓ |
| Nature | Nature Medicine | nm | journal | monthly | https://www.nature.com/nm.rss | high | ✓ |
| Nature | Nature Biotechnology | nbt | journal | monthly | https://www.nature.com/nbt.rss | high | ✓ |
| Nature | Nature Cell Biology | ncb | journal | monthly | https://www.nature.com/ncb.rss | high | ✓ |
| Nature | Nature Structural & Molecular Biology | nsmb | journal | monthly | https://www.nature.com/nsmb.rss | high | ✓ |
| Nature | Nature Neuroscience | neuro | journal | monthly | https://www.nature.com/neuro.rss | high | ✓ |
| Nature | Nature Communications | ncomms | journal | continuous | https://www.nature.com/ncomms.rss | mixed | ✓ |

## Science (AAAS)

Pattern: `https://www.science.org/action/showFeed?type=etoc&feed=rss&jc=<code>`.
**Cloudflare-protected** — the fetcher must send a realistic `User-Agent` or the
request returns HTTP 403. The `jc=` codes below are verified live.

| Family | Journal | Key | Feed type | Frequency | RSS URL | Bio focus | Status |
|--------|---------|-----|-----------|-----------|---------|-----------|--------|
| Science | Science | science | etoc | weekly | https://www.science.org/action/showFeed?type=etoc&feed=rss&jc=science | mixed | ✓ |
| Science | Science Advances | sciadv | etoc | continuous | https://www.science.org/action/showFeed?type=etoc&feed=rss&jc=sciadv | mixed | ✓ |
| Science | Science Translational Medicine | scitranslmed | etoc | weekly | https://www.science.org/action/showFeed?type=etoc&feed=rss&jc=stm | high | ✓ |
| Science | Science Signaling | scisignal | etoc | weekly | https://www.science.org/action/showFeed?type=etoc&feed=rss&jc=signaling | high | ✓ |
| Science | Science Immunology | sciimmunol | etoc | monthly | https://www.science.org/action/showFeed?type=etoc&feed=rss&jc=sciimmunol | high | ✓ |

## Cell Press

Pattern: `https://www.cell.com/<slug>/current.rss` (latest issue;
`/inpress.rss` exists for articles-in-press). **Cloudflare-protected** — same
`User-Agent` requirement as Science.

| Family | Journal | Key | Feed type | Frequency | RSS URL | Bio focus | Status |
|--------|---------|-----|-----------|-----------|---------|-----------|--------|
| Cell Press | Cell | cell | current | biweekly | https://www.cell.com/cell/current.rss | high | ✓ |
| Cell Press | Cell Reports | cell-reports | current | continuous | https://www.cell.com/cell-reports/current.rss | high | ✓ |
| Cell Press | Molecular Cell | molecular-cell | current | biweekly | https://www.cell.com/molecular-cell/current.rss | high | ✓ |
| Cell Press | Cell Stem Cell | cell-stem-cell | current | monthly | https://www.cell.com/cell-stem-cell/current.rss | high | ✓ |
| Cell Press | Cell Metabolism | cell-metabolism | current | monthly | https://www.cell.com/cell-metabolism/current.rss | high | ✓ |
| Cell Press | Cell Host & Microbe | cell-host-microbe | current | monthly | https://www.cell.com/cell-host-microbe/current.rss | high | ✓ |
| Cell Press | Cell Systems | cell-systems | current | monthly | https://www.cell.com/cell-systems/current.rss | high | ✓ |
| Cell Press | Cell Genomics | cell-genomics | current | monthly | https://www.cell.com/cell-genomics/current.rss | high | ✓ |
| Cell Press | Developmental Cell | developmental-cell | current | biweekly | https://www.cell.com/developmental-cell/current.rss | high | ✓ |
| Cell Press | Immunity | immunity | current | monthly | https://www.cell.com/immunity/current.rss | high | ✓ |
| Cell Press | Neuron | neuron | current | biweekly | https://www.cell.com/neuron/current.rss | high | ✓ |
| Cell Press | Current Biology | current-biology | current | biweekly | https://www.cell.com/current-biology/current.rss | high | ✓ |
| Cell Press | Cancer Cell | cancer-cell | current | monthly | https://www.cell.com/cancer-cell/current.rss | high | ✓ |

<!--
Maintenance:
  - Add a feed: add a row here AND a matching entry in config/journals.json
    (key/label/family/frequency/feeds[]). A journal may declare multiple feed rows.
  - Frequency drives polling cadence; keep it in sync between this table and
    journals.json. Allowed values: continuous | weekly | biweekly | monthly (daily).
  - Verify links: `bio-trend check-feeds --check` probes every feed and reports
    live/dead; `bio-trend check-feeds` (no flag) lists each feed's frequency.
  - Ingest: `bio-trend ingest` polls only journals that are due; `--force` polls all.
  - Science/Cell are Cloudflare-protected; the fetcher sends a browser-like
    User-Agent. If a feed 403s anyway, mark Status ✗ and open an issue.
-->
