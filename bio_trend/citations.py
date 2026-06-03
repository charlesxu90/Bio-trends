"""Citation counts from Semantic Scholar / OpenAlex, hardened and cached.

Adapted from AI-trend's ``citations.py``. The key improvement for Bio-trend: RSS
feed entries carry **DOIs**, so we look citations up by DOI directly (exact, no
fuzzy title matching) whenever a DOI is present, and only fall back to
title-verified search otherwise.

The cache is keyed by article **title** (so :mod:`bio_trend.site` can join it onto
paper records) and is resumable: titles already cached are skipped. ``0`` (zero
citations) is distinct from ``None`` (verified no-match); a failed request is left
uncached so it retries next run.

Optional extra: ``pip install -e '.[citations]'`` (needs ``requests``).
"""

from __future__ import annotations

import json
import os
import re
import time
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:  # pragma: no cover - typing only
    import requests

S2_SEARCH = "https://api.semanticscholar.org/graph/v1/paper/search"
S2_BY_DOI = "https://api.semanticscholar.org/graph/v1/paper/DOI:{doi}"
DEFAULT_THROTTLE = 1.1
DEFAULT_RETRIES = 4
DEFAULT_BACKOFF = 2.0

FETCH_FAILED = object()  # request itself failed (429/network) — do NOT cache
MAX_CONSECUTIVE_FAILURES = 10
TITLE_MATCH_JACCARD = 0.85


def _headers() -> dict[str, str]:
    headers = {"User-Agent": "bio-trend/0.1"}
    key = os.environ.get("S2_API_KEY", "").strip()
    if key:
        headers["x-api-key"] = key
    return headers


def _normalize_title(title: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", str(title).lower()).strip()


def titles_match(query: str, candidate: str) -> bool:
    """True if two titles refer to the same paper (exact-normalised or high Jaccard)."""
    nq, nc = _normalize_title(query), _normalize_title(candidate)
    if not nq or not nc:
        return False
    if nq == nc:
        return True
    tq, tc = set(nq.split()), set(nc.split())
    union = tq | tc
    return bool(union) and len(tq & tc) / len(union) >= TITLE_MATCH_JACCARD


def _get(session, url, params, *, retries, backoff, sleep):
    for attempt in range(retries + 1):
        try:
            resp = session.get(url, params=params, timeout=30, headers=_headers())
            if resp.status_code == 429:
                if attempt < retries:
                    sleep(backoff * (2 ** attempt))
                    continue
                return None
            if resp.status_code == 404:
                return {}  # DOI lookup: not found (distinct from request failure)
            resp.raise_for_status()
            return resp.json()
        except Exception:
            if attempt < retries:
                sleep(backoff * (2 ** attempt))
                continue
            return None
    return None


def search_by_doi(
    doi: str, session: "requests.Session", *,
    retries: int = DEFAULT_RETRIES, backoff: float = DEFAULT_BACKOFF, sleep=time.sleep,
) -> int | None | object:
    """Citation count for an exact DOI. Returns int, None (not found), or FETCH_FAILED."""
    data = _get(session, S2_BY_DOI.format(doi=doi), {"fields": "citationCount"},
                retries=retries, backoff=backoff, sleep=sleep)
    if data is None:
        return FETCH_FAILED
    if not data:  # 404
        return None
    return data.get("citationCount")


def search_by_title(
    title: str, session: "requests.Session", *, limit: int = 5,
    retries: int = DEFAULT_RETRIES, backoff: float = DEFAULT_BACKOFF, sleep=time.sleep,
) -> int | None | object:
    """Title-verified citation count. Returns int, None (no match), or FETCH_FAILED."""
    data = _get(session, S2_SEARCH,
                {"query": title.replace("-", " "), "fields": "title,citationCount", "limit": limit},
                retries=retries, backoff=backoff, sleep=sleep)
    if data is None:
        return FETCH_FAILED
    for result in data.get("data") or []:
        if titles_match(title, result.get("title", "")):
            return result.get("citationCount")
    return None


def load_cache(path: Path | str) -> dict[str, int | None]:
    path = Path(path)
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


def save_cache(path: Path | str, cache: dict) -> None:
    Path(path).write_text(json.dumps(cache, ensure_ascii=False, indent=0), encoding="utf-8")


def items_for_topics(df, topics) -> list[tuple[str, str]]:
    """``(title, doi)`` pairs for papers whose ``topic`` matches any of ``topics``."""
    topic_set = set(topics)
    out: list[tuple[str, str]] = []
    dois = df["doi"].fillna("") if "doi" in df.columns else [""] * len(df)
    for title, doi, cell in zip(df["title"], dois, df["topic"].fillna("")):
        labels = {t for t in str(cell).split(";") if t}
        if labels & topic_set:
            out.append((str(title), str(doi)))
    return out


def fetch_citations(
    items: list[tuple[str, str]],
    cache_path: Path | str,
    session: "requests.Session",
    *,
    throttle: float = DEFAULT_THROTTLE,
    sleep=time.sleep,
    log=lambda *_: None,
) -> dict[str, int | None]:
    """Fetch citations for ``(title, doi)`` items (DOI-first), resumable via cache."""
    cache = load_cache(cache_path)
    pending = [(t, d) for t, d in items if t not in cache]
    log(f"citations: {len(pending)} to fetch ({len(items) - len(pending)} cached)")
    consecutive_failures = 0
    for i, (title, doi) in enumerate(pending, 1):
        result = search_by_doi(doi, session, sleep=sleep) if doi else FETCH_FAILED
        if result is FETCH_FAILED and not doi:
            result = search_by_title(title, session, sleep=sleep)
        elif result is FETCH_FAILED and doi:
            # DOI request failed outright; try a title search before giving up
            result = search_by_title(title, session, sleep=sleep)

        if result is FETCH_FAILED:
            consecutive_failures += 1
            if consecutive_failures >= MAX_CONSECUTIVE_FAILURES:
                log(f"citations: aborting after {consecutive_failures} consecutive failures "
                    f"(rate-limited?); {i - 1}/{len(pending)} attempted — re-run to resume")
                break
            if i < len(pending):
                sleep(throttle)
            continue
        consecutive_failures = 0
        cache[title] = result  # int | None (verified no-match)
        if i % 25 == 0 or i == len(pending):
            save_cache(cache_path, cache)
            log(f"citations: {i}/{len(pending)}")
        if i < len(pending):
            sleep(throttle)
    save_cache(cache_path, cache)
    return cache
