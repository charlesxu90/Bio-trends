"""``bio-trend`` command-line interface.

Subcommands:

* ``check-feeds`` — list tracked feeds; with ``--check``, probe each for liveness.
* ``ingest``      — poll RSS feeds and accumulate articles into the data store.
* ``candidates``  — extract candidate keywords (scispaCy) for the curate-topics skill.
* ``curate``      — apply the skill's decision JSON to the taxonomy config.
* ``assign``      — assign topics to a papers CSV using the current taxonomy.
* ``trends``      — compute top/emerging/fading topics per journal/family period.
* ``citations``   — fetch citation counts (DOI-first, cached) for trending papers.
* ``export-site`` — build static-site JSON for GitHub Pages.
* ``refresh``     — full pipeline: ingest -> assign -> trends -> export-site.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from bio_trend.taxonomy import DEFAULT_CONFIG_DIR, Taxonomy

OTHER_LEDGER_FILENAME = "other_keywords.json"


def _eprint(message: str) -> None:
    print(message, file=sys.stderr)


def _load_other_ledger(config_dir: Path) -> list[str]:
    path = config_dir / OTHER_LEDGER_FILENAME
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else []


def _save_other_ledger(config_dir: Path, keywords: list[str]) -> None:
    (config_dir / OTHER_LEDGER_FILENAME).write_text(
        json.dumps(sorted(set(keywords)), indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def _default_topics_path(csv_path: Path) -> Path:
    return csv_path.with_name(csv_path.name + "_topics.csv")


# ---- subcommands ------------------------------------------------------------
def cmd_check_feeds(args: argparse.Namespace) -> int:
    from bio_trend.registry import JournalRegistry

    registry = JournalRegistry.load(Path(args.config))
    pairs = registry.all_feeds()
    _eprint(f"feeds: {len(pairs)} across {len(registry.journals)} journal(s)")
    if not args.check:
        for journal, feed in pairs:
            _eprint(f"  {journal.key:20s} {journal.frequency:10s} {feed.type:8s} {feed.url}")
        return 0

    from bio_trend.rss import feed_status

    dead = 0
    for journal, feed in pairs:
        ok, status, n = feed_status(feed.url)
        mark = "OK " if ok else "DEAD"
        if not ok:
            dead += 1
        _eprint(f"  [{mark}] http={status or '-'} entries={n:<4d} {journal.key} -> {feed.url}")
    _eprint(f"check: {len(pairs) - dead}/{len(pairs)} feeds live, {dead} dead")
    return 1 if dead else 0


def cmd_ingest(args: argparse.Namespace) -> int:
    from bio_trend.ingest import ingest_all
    from bio_trend.registry import JournalRegistry

    registry = JournalRegistry.load(Path(args.config))
    only = {k.strip() for k in args.journal.split(",")} if args.journal else None
    if only:
        unknown = only - set(registry.keys)
        if unknown:
            _eprint(f"error: unknown journal key(s): {sorted(unknown)}")
            return 2
    summary = ingest_all(registry, args.data_dir, only=only, force=args.force, log=_eprint)
    total = sum(sum(v.values()) for v in summary.values())
    _eprint(f"ingest: +{total} new article(s) across {len(summary)} journal(s) -> {args.data_dir}")
    return 0


def cmd_backfill(args: argparse.Namespace) -> int:
    import os

    from bio_trend.backfill import backfill_all
    from bio_trend.registry import JournalRegistry

    registry = JournalRegistry.load(Path(args.config))
    only = {k.strip() for k in args.journal.split(",")} if args.journal else None
    if only:
        unknown = only - set(registry.keys)
        if unknown:
            _eprint(f"error: unknown journal key(s): {sorted(unknown)}")
            return 2
    try:
        years = [int(y.strip()) for y in args.years.split(",") if y.strip()]
    except ValueError:
        _eprint(f"error: --years must be comma-separated integers, got {args.years!r}")
        return 2

    mailto = args.mailto or os.environ.get("OPENALEX_MAILTO", "")
    totals = backfill_all(registry, years, args.data_dir, only=only, mailto=mailto, log=_eprint)
    grand = sum(totals.values())
    _eprint(f"backfill: +{grand} article(s) across {len(totals)} journal(s) for years {years} -> {args.data_dir}")
    return 0


def cmd_candidates(args: argparse.Namespace) -> int:
    import pandas as pd

    from bio_trend.candidates import candidate_keywords, candidates_to_dicts
    from bio_trend.curate_io import build_curation_payload

    csv_path = Path(args.csv)
    if not csv_path.exists():
        _eprint(f"error: input CSV not found: {csv_path}")
        return 2

    config_dir = Path(args.config)
    taxonomy = Taxonomy.load(config_dir)
    ledger = _load_other_ledger(config_dir)
    if ledger:
        taxonomy = taxonomy.add_noise(ledger)

    df = pd.read_csv(csv_path)
    if "title" not in df.columns:
        _eprint(f"error: CSV has no 'title' column: {csv_path}")
        return 2
    titles = df["title"].astype(str).str.lower().tolist()

    candidates = candidate_keywords(
        titles, taxonomy, model_path=args.model, threshold=args.threshold, examples=args.examples,
    )
    payload = build_curation_payload(candidates, taxonomy, journal=args.journal, period=args.period)
    payload["candidates"] = candidates_to_dicts(candidates)

    text = json.dumps(payload, indent=2, ensure_ascii=False)
    if args.output:
        Path(args.output).write_text(text + "\n", encoding="utf-8")
        _eprint(f"wrote {len(candidates)} candidates -> {args.output}")
    else:
        print(text)
    return 0


def cmd_curate(args: argparse.Namespace) -> int:
    from bio_trend.curate_io import apply_decision, parse_decision

    decision_path = Path(args.decision)
    if not decision_path.exists():
        _eprint(f"error: decision file not found: {decision_path}")
        return 2

    config_dir = Path(args.config)
    taxonomy = Taxonomy.load(config_dir)
    decisions = parse_decision(json.loads(decision_path.read_text(encoding="utf-8")))
    result = apply_decision(taxonomy, decisions)

    if args.dry_run:
        _eprint(f"dry-run: {result.summary}; other={result.other_keywords}")
        return 0

    result.taxonomy.save(config_dir)
    if result.other_keywords:
        ledger = _load_other_ledger(config_dir)
        _save_other_ledger(config_dir, [*ledger, *result.other_keywords])
    _eprint(f"applied {result.summary}; parked {len(result.other_keywords)} in 'other'")
    return 0


def cmd_assign(args: argparse.Namespace) -> int:
    from bio_trend.assign import assign_csv

    csv_path = Path(args.csv)
    if not csv_path.exists():
        _eprint(f"error: input CSV not found: {csv_path}")
        return 2

    taxonomy = Taxonomy.load(Path(args.config))
    out_path = Path(args.output) if args.output else _default_topics_path(csv_path)
    assign_csv(str(csv_path), str(out_path), taxonomy)
    _eprint(f"assigned topics -> {out_path}")
    return 0


def cmd_trends(args: argparse.Namespace) -> int:
    from bio_trend.trends import compute_all_trends, render_markdown, trend_to_dict

    data_dir = Path(args.data_dir)
    if not data_dir.exists():
        _eprint(f"error: data directory not found: {data_dir}")
        return 2

    taxonomy = Taxonomy.load(Path(args.config))
    trends = compute_all_trends(
        taxonomy, data_dir, group_by=args.group_by, bucket=args.bucket,
        top_n=args.top_n, min_prev=args.min_prev, min_count=args.min_count,
    )
    if not trends:
        _eprint(f"error: no *_topics.csv found under {data_dir} (run ingest + assign first)")
        return 2

    if args.format == "markdown":
        text = render_markdown(trends)
    else:
        text = json.dumps(
            [trend_to_dict(t, include_counts=args.include_counts) for t in trends],
            indent=2, ensure_ascii=False,
        )

    if args.output:
        out_path = Path(args.output)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(text + "\n", encoding="utf-8")
        _eprint(f"wrote trends for {len(trends)} group-period(s) -> {args.output}")
    else:
        print(text)
    return 0


def cmd_citations(args: argparse.Namespace) -> int:
    import pandas as pd
    import requests

    from bio_trend.citations import fetch_citations, items_for_topics

    csv = Path(args.topics_csv)
    if not csv.exists():
        _eprint(f"error: topics CSV not found: {csv}")
        return 2
    df = pd.read_csv(csv)

    if args.topics:
        topic_set = {t.strip() for t in args.topics.split(",") if t.strip()}
    else:
        _eprint("error: pass --topics (comma-separated) to scope citations")
        return 2

    items = items_for_topics(df, topic_set)
    if args.limit:
        items = items[: args.limit]
    _eprint(f"citations: {len(items)} papers in topics {sorted(topic_set)[:6]}...")
    cache_path = str(csv) + ".citations.json"
    fetch_citations(items, cache_path, requests.Session(), throttle=args.throttle, log=_eprint)
    _eprint(f"citations cached -> {cache_path} (re-run export-site to surface them)")
    return 0


def cmd_export_site(args: argparse.Namespace) -> int:
    from bio_trend.site import export_site

    data_dir = Path(args.data_dir)
    if not data_dir.exists():
        _eprint(f"error: data directory not found: {data_dir}")
        return 2

    taxonomy = Taxonomy.load(Path(args.config))
    manifest = export_site(
        args.out_dir, taxonomy=taxonomy, data_dir=data_dir,
        group_by=args.group_by, bucket=args.bucket,
        top_n=args.top_n, min_prev=args.min_prev, min_count=args.min_count,
        abstract_chars=args.abstract_chars, shard_years=args.shard_years or None,
    )
    papers = sum(s["count"] for s in manifest["shards"])
    _eprint(f"exported {len(manifest['shards'])} shards / {papers} papers -> {args.out_dir}")
    return 0


def cmd_refresh(args: argparse.Namespace) -> int:
    from bio_trend.refresh import refresh

    only = {k.strip() for k in args.journal.split(",")} if args.journal else None
    summary = refresh(
        config_dir=Path(args.config), data_dir=args.data_dir, site_dir=args.site_dir,
        do_ingest=not args.no_ingest, only=only, force=args.force,
        group_by=args.group_by, bucket=args.bucket,
        shard_years=args.shard_years or None, log=_eprint,
    )
    _eprint(f"refresh complete: {summary}")
    return 0


# ---- parser -----------------------------------------------------------------
def _add_trend_opts(p: argparse.ArgumentParser) -> None:
    p.add_argument("--group-by", choices=["journal", "family"], default="journal")
    p.add_argument("--bucket", choices=["month", "quarter", "year"], default="month")
    p.add_argument("--top-n", type=int, default=5)
    p.add_argument("--min-prev", type=int, default=1)
    p.add_argument("--min-count", type=int, default=3)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="bio-trend", description=__doc__)
    parser.add_argument(
        "--config", default=str(DEFAULT_CONFIG_DIR),
        help="config dir holding journals.json / taxonomy.json / useless_keywords.json",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_chk = sub.add_parser("check-feeds", help="list tracked feeds; --check probes liveness")
    p_chk.add_argument("--check", action="store_true", help="probe each feed over the network")
    p_chk.set_defaults(func=cmd_check_feeds)

    p_ing = sub.add_parser("ingest", help="poll due RSS feeds and accumulate articles")
    p_ing.add_argument("--journal", default=None, help="comma-separated journal keys (default: all)")
    p_ing.add_argument("--force", action="store_true", help="poll even journals not yet due per their frequency")
    p_ing.add_argument("--data-dir", default="data")
    p_ing.set_defaults(func=cmd_ingest)

    p_bf = sub.add_parser("backfill", help="fetch historical articles from OpenAlex into the store")
    p_bf.add_argument("--years", default=None, required=True, help="comma-separated years, e.g. 2024,2025")
    p_bf.add_argument("--journal", default=None, help="comma-separated journal keys (default: all)")
    p_bf.add_argument("--mailto", default=None, help="contact email for OpenAlex polite pool (or $OPENALEX_MAILTO)")
    p_bf.add_argument("--data-dir", default="data")
    p_bf.set_defaults(func=cmd_backfill)

    p_cand = sub.add_parser("candidates", help="extract candidate keywords for curation")
    p_cand.add_argument("csv", help="papers CSV (needs a 'title' column)")
    p_cand.add_argument("-o", "--output", help="write payload JSON here (default: stdout)")
    p_cand.add_argument("--threshold", type=int, default=5, help="min keyword count")
    p_cand.add_argument("--examples", type=int, default=3, help="example titles / keyword")
    p_cand.add_argument("--model", default=None, help="path to the scispaCy model")
    p_cand.add_argument("--journal", default=None)
    p_cand.add_argument("--period", default=None)
    p_cand.set_defaults(func=cmd_candidates)

    p_cur = sub.add_parser("curate", help="apply a curation decision to the taxonomy")
    p_cur.add_argument("decision", help="decision JSON produced by the curate-topics skill")
    p_cur.add_argument("--dry-run", action="store_true", help="report changes, write nothing")
    p_cur.set_defaults(func=cmd_curate)

    p_asg = sub.add_parser("assign", help="assign topics to a papers CSV")
    p_asg.add_argument("csv", help="papers CSV (needs 'title' and 'abstract' columns)")
    p_asg.add_argument("-o", "--output", help="output CSV (default: <csv>_topics.csv)")
    p_asg.set_defaults(func=cmd_assign)

    p_trd = sub.add_parser("trends", help="compute top/emerging/fading topics")
    p_trd.add_argument("--data-dir", default="data", help="root holding <journal_key>/ folders")
    p_trd.add_argument("-o", "--output", help="output file (default: stdout)")
    p_trd.add_argument("--format", choices=["json", "markdown"], default="json")
    p_trd.add_argument("--include-counts", action="store_true", help="embed per-topic counts (json)")
    _add_trend_opts(p_trd)
    p_trd.set_defaults(func=cmd_trends)

    p_cit = sub.add_parser("citations", help="fetch citation counts (DOI-first, cached)")
    p_cit.add_argument("topics_csv", help="a *_topics.csv file")
    p_cit.add_argument("--topics", default=None, help="comma-separated topics to scope (required)")
    p_cit.add_argument("--limit", type=int, default=None, help="cap number of papers")
    p_cit.add_argument("--throttle", type=float, default=1.1, help="seconds between API calls")
    p_cit.set_defaults(func=cmd_citations)

    p_exp = sub.add_parser("export-site", help="build static-site JSON for GitHub Pages")
    p_exp.add_argument("--data-dir", default="data")
    p_exp.add_argument("--out-dir", default="docs/data")
    p_exp.add_argument("--abstract-chars", type=int, default=300)
    p_exp.add_argument("--shard-years", type=int, default=0,
                       help="cap browsable paper shards to the most recent N years (0 = all); trends always use full history")
    _add_trend_opts(p_exp)
    p_exp.set_defaults(func=cmd_export_site)

    p_ref = sub.add_parser("refresh", help="full pipeline (ingest->assign->trends->export-site)")
    p_ref.add_argument("--no-ingest", action="store_true", help="skip polling; re-derive from existing data")
    p_ref.add_argument("--force", action="store_true", help="poll even journals not yet due per their frequency")
    p_ref.add_argument("--journal", default=None, help="comma-separated keys to ingest (default: all)")
    p_ref.add_argument("--data-dir", default="data")
    p_ref.add_argument("--site-dir", default="docs/data")
    p_ref.add_argument("--group-by", choices=["journal", "family"], default="journal")
    p_ref.add_argument("--bucket", choices=["month", "quarter", "year"], default="month")
    p_ref.add_argument("--shard-years", type=int, default=0,
                       help="cap browsable paper shards to the most recent N years (0 = all)")
    p_ref.set_defaults(func=cmd_refresh)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if getattr(args, "model", None) is None and args.command == "candidates":
        from bio_trend.candidates import DEFAULT_MODEL_PATH

        args.model = str(DEFAULT_MODEL_PATH)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
