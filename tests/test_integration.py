"""Integration: mocked feed fetch -> ingest -> refresh -> site, no network."""

import json
import types

import pandas as pd

from bio_trend import rss
from bio_trend.refresh import refresh
from bio_trend.registry import JournalRegistry
from bio_trend.site import export_site
from bio_trend.taxonomy import Taxonomy


def _make_config(config_dir):
    config_dir.mkdir(parents=True, exist_ok=True)
    (config_dir / "taxonomy.json").write_text(
        json.dumps({"genome editing": ["crispr"], "immunology": ["t cell"]}), encoding="utf-8"
    )
    (config_dir / "useless_keywords.json").write_text("[]", encoding="utf-8")
    (config_dir / "journals.json").write_text(
        json.dumps({"journals": [{"key": "cell", "label": "Cell", "family": "Cell Press",
                                   "feeds": [{"url": "https://x/cell.rss"}]}]}),
        encoding="utf-8",
    )


def _fake_feed(entries):
    return types.SimpleNamespace(status=200, entries=entries, feed={})


def test_fetch_journal_dedupes_across_feeds(monkeypatch):
    entries = [
        {"title": "CRISPR screen", "prism_doi": "10.1016/j.cell.2026.05.001", "published": "2026-05-01", "link": "http://x/a"},
        {"title": "CRISPR screen dup", "prism_doi": "10.1016/j.cell.2026.05.001", "published": "2026-05-01", "link": "http://x/a2"},
        {"title": "T cell atlas", "prism_doi": "10.1016/j.cell.2026.05.003", "published": "2026-05-02", "link": "http://x/b"},
    ]
    monkeypatch.setattr(rss, "parse_feed", lambda url, agent=rss.USER_AGENT: _fake_feed(entries))
    reg = JournalRegistry.from_dicts([
        {"key": "cell", "label": "Cell", "family": "Cell Press", "feeds": [{"url": "https://x/cell.rss"}]}
    ])
    df = rss.fetch_journal(reg.journals[0])
    assert len(df) == 2  # the duplicate DOI is dropped
    assert set(df["doi"]) == {"10.1016/j.cell.2026.05.001", "10.1016/j.cell.2026.05.003"}


def test_refresh_then_export_site(tmp_path, monkeypatch):
    config_dir = tmp_path / "config"
    data_dir = tmp_path / "data"
    site_dir = tmp_path / "site"
    _make_config(config_dir)

    entries = [
        {"title": "CRISPR base editing", "prism_doi": "10.1016/j.cell.2026.05.001", "published": "2026-05-02", "link": "http://x/a", "summary": "crispr"},
        {"title": "T cell receptor map", "prism_doi": "10.1016/j.cell.2026.05.003", "published": "2026-05-03", "link": "http://x/b", "summary": "t cell"},
    ]
    monkeypatch.setattr(rss, "parse_feed", lambda url, agent=rss.USER_AGENT: _fake_feed(entries))

    summary = refresh(
        config_dir=config_dir, data_dir=data_dir, site_dir=site_dir, log=lambda *_: None,
    )
    assert summary["ingested"] == 2
    assert summary["assigned"] == 1
    assert summary["site_papers"] == 2

    # site artifacts exist and are well-formed
    manifest = json.loads((site_dir / "manifest.json").read_text())
    assert manifest["families"] == ["Cell Press"]
    assert "genome editing" in manifest["topics"] and "immunology" in manifest["topics"]
    shard = json.loads((site_dir / "papers" / "cell_2026-05.json").read_text())
    assert {r["title"] for r in shard} == {"CRISPR base editing", "T cell receptor map"}


def test_export_site_reads_citation_sidecar(tmp_path):
    config_dir = tmp_path / "config"
    data_dir = tmp_path / "data"
    _make_config(config_dir)
    cell = data_dir / "cell"
    cell.mkdir(parents=True)
    pd.DataFrame([{"title": "CRISPR", "abstract": "crispr", "journal": "Cell",
                   "family": "Cell Press", "published_date": "2026-05-01", "doi": "10.1016/j.cell.2026.05.001",
                   "link": "", "authors": "", "topic": "genome editing"}]).to_csv(
        cell / "2026-05.csv_topics.csv", index=False
    )
    (cell / "2026-05.csv_topics.csv.citations.json").write_text(json.dumps({"CRISPR": 7}))

    taxonomy = Taxonomy.load(config_dir)
    registry = JournalRegistry.load(config_dir)
    export_site(tmp_path / "site", taxonomy=taxonomy, registry=registry, data_dir=data_dir)

    shard = json.loads((tmp_path / "site" / "papers" / "cell_2026-05.json").read_text())
    assert shard[0]["citations"] == 7
