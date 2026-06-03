"""Pre-build compact JSON for the static GitHub Pages site.

Adapted from AI-trend's ``site.py``. GitHub Pages is static, so the browser cannot
read the CSVs directly. This module exports:

* ``trends.json`` — per journal-period top/emerging/fading + topic counts.
* ``papers/<key>_<period>.json`` — one shard per journal-month, loaded on demand.
* ``manifest.json`` — journals, families, available shards, periods, and the topics
  that actually occur (drives the site's filters).

Journal/period identity comes from the **file location** via the registry.
"""

from __future__ import annotations

import ast
import json
from pathlib import Path
from typing import TYPE_CHECKING

from bio_trend.ingest import DEFAULT_DATA_DIR
from bio_trend.registry import JournalRegistry
from bio_trend.taxonomy import Taxonomy
from bio_trend.trends import (
    BUCKET_MONTH,
    BUCKET_YEAR,
    BUCKETS,
    DEFAULT_MIN_COUNT,
    DEFAULT_MIN_PREV,
    DEFAULT_TOP_N,
    GROUP_JOURNAL,
    TOPICS_GLOB,
    compute_all_trends,
    month_of,
    trend_to_dict,
)

if TYPE_CHECKING:  # pragma: no cover - typing only
    pass

DEFAULT_SITE_DATA_DIR = Path(__file__).resolve().parent.parent / "docs" / "data"
DEFAULT_ABSTRACT_CHARS = 300


def parse_authors(raw: object) -> list[str]:
    """Turn the CSV ``authors`` cell (``"'A', 'B'"``) into a clean list."""
    if not isinstance(raw, str) or not raw.strip():
        return []
    try:
        value = ast.literal_eval("[" + raw + "]")
        return [str(a).strip() for a in value if str(a).strip()]
    except (ValueError, SyntaxError):
        return [raw.strip()]


def _text(value: object) -> str:
    return value.strip() if isinstance(value, str) else ""


def build_paper_record(
    row: dict,
    journal: str,
    family: str,
    period: str,
    abstract_chars: int = DEFAULT_ABSTRACT_CHARS,
    citations: dict | None = None,
) -> dict:
    topics = [t for t in str(row.get("topic", "")).split(";") if t and t != "nan"]
    abstract = _text(row.get("abstract"))
    if len(abstract) > abstract_chars:
        abstract = abstract[:abstract_chars].rstrip() + "…"
    title = _text(row.get("title"))
    record = {
        "title": title,
        "authors": parse_authors(row.get("authors")),
        "topics": topics,
        "journal": journal,
        "family": family,
        "period": period,
        "published": _text(row.get("published_date")),
        "doi": _text(row.get("doi")),
        "link": _text(row.get("link")),
        "abstract": abstract,
    }
    if citations is not None:
        cited = citations.get(title)
        if cited is not None:
            record["citations"] = cited
    return record


def _recover_citations_from_shard(shard_path: Path) -> dict:
    """Recover ``{title: citations}`` from a prior shard (sidecars are gitignored)."""
    if not shard_path.exists():
        return {}
    try:
        records = json.loads(shard_path.read_text(encoding="utf-8"))
    except (ValueError, OSError):
        return {}
    return {
        r["title"]: r["citations"]
        for r in records
        if r.get("title") and r.get("citations") is not None
    }


def export_site(
    out_dir: Path | str = DEFAULT_SITE_DATA_DIR,
    *,
    taxonomy: Taxonomy | None = None,
    registry: JournalRegistry | None = None,
    data_dir: Path | str = DEFAULT_DATA_DIR,
    group_by: str = GROUP_JOURNAL,
    bucket: str = BUCKET_MONTH,
    top_n: int = DEFAULT_TOP_N,
    min_prev: int = DEFAULT_MIN_PREV,
    min_count: int = DEFAULT_MIN_COUNT,
    abstract_chars: int = DEFAULT_ABSTRACT_CHARS,
    max_shard_months: int | None = None,
) -> dict:
    """Write the site's JSON data files and return the manifest.

    ``max_shard_months`` caps the *browsable* paper shards to the most recent N
    months (globally), keeping the static site light when a large historical
    backfill is present. Trends are always computed over the full history,
    regardless of this cap. ``None`` (default) emits a shard for every month.
    """
    import pandas as pd

    taxonomy = taxonomy or Taxonomy.load()
    registry = registry or JournalRegistry.load()
    out_dir = Path(out_dir)
    (out_dir / "papers").mkdir(parents=True, exist_ok=True)
    data_dir = Path(data_dir)

    # Trends at every granularity (year / quarter / month) so the site can toggle.
    trends_by_bucket = {
        b: [
            trend_to_dict(t, include_counts=True)
            for t in compute_all_trends(
                taxonomy, data_dir, group_by=group_by, bucket=b,
                top_n=top_n, min_prev=min_prev, min_count=min_count,
            )
        ]
        for b in BUCKETS
    }
    (out_dir / "trends.json").write_text(
        json.dumps(trends_by_bucket, ensure_ascii=False), encoding="utf-8"
    )

    key_to_label = registry.key_to_label
    key_to_family = registry.key_to_family
    shards: list[dict] = []
    seen_topics: set[str] = set()

    # Collect every (journal, month) topics file, then optionally keep only the
    # most recent N months as browsable shards (trends already used all of it).
    found: list[tuple[str, str, str, str, Path]] = []  # (key, label, family, month, path)
    for key_dir in sorted(p for p in data_dir.iterdir() if p.is_dir()) if data_dir.exists() else []:
        key = key_dir.name
        label = key_to_label.get(key)
        if label is None:
            continue
        family = key_to_family.get(key, label)
        for topics_path in sorted(key_dir.glob(TOPICS_GLOB)):
            month = month_of(topics_path)
            if month is not None:
                found.append((key, label, family, month, topics_path))

    keep_months: set[str] | None = None
    if max_shard_months:
        all_months = sorted({m for _, _, _, m, _ in found})
        keep_months = set(all_months[-max_shard_months:])

    # Full-corpus totals (every month, not just browsable shards) for the hero.
    total_articles = 0
    for _, _, _, _, path in found:
        with open(path, encoding="utf-8") as fh:
            total_articles += max(0, sum(1 for _ in fh) - 1)  # minus header

    for key, label, family, month, topics_path in found:
        if keep_months is not None and month not in keep_months:
            continue
        df = pd.read_csv(topics_path)
        rel = f"papers/{key}_{month}.json"
        cite_path = Path(str(topics_path) + ".citations.json")
        side_cites = json.loads(cite_path.read_text(encoding="utf-8")) if cite_path.exists() else {}
        prev_cites = _recover_citations_from_shard(out_dir / rel)
        citations = {**prev_cites, **side_cites} or None
        records = [
            build_paper_record(row, label, family, month, abstract_chars, citations)
            for row in df.to_dict("records")
        ]
        for record in records:
            seen_topics.update(record["topics"])
        (out_dir / rel).write_text(json.dumps(records, ensure_ascii=False), encoding="utf-8")
        shards.append({
            "journal": key, "label": label, "family": family,
            "period": month, "count": len(records), "file": rel,
        })

    manifest = {
        "journals": [
            {"key": j.key, "label": j.label, "family": j.family} for j in registry.journals
        ],
        "families": sorted({j.family for j in registry.journals}),
        "topics": sorted(seen_topics),
        "periods": sorted({s["period"] for s in shards}),
        "years": sorted({s["period"][:4] for s in shards}),
        "buckets": list(BUCKETS),
        # full-corpus coverage (all years analysed for trends, not just browsable shards)
        "total_articles": total_articles,
        "taxonomy_topics": len(taxonomy.topics),
        "trend_years": sorted({t["period"] for t in trends_by_bucket[BUCKET_YEAR]}),
        "shards": shards,
    }
    (out_dir / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False), encoding="utf-8"
    )
    return manifest
