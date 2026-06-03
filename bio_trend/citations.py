"""Citation counts from Crossref, tracked over time per paper.

Follows the Zotero *Citation Counts Manager* reference: Crossref's
``is-referenced-by-count`` keyed by DOI is the primary, key-less source. Every
Bio-trend article carries a DOI and Crossref is reachable where OpenAlex/S2 are
rate-limited, so Crossref is the default.

Tracking policy (to surface *rising* papers): a paper's count is snapshotted
**on first sight (addition)** and then **at most twice more, monthly, while within
three months of its publication date** — three snapshots maximum. Citations of
older papers move slowly, so one snapshot is enough; recent papers accrue a short
velocity series, and the gain across snapshots is the "rising" signal.

Storage: ``citations/<journal_key>/<year>.json`` — committed (not under the
gitignored ``data/``) so history persists across checkouts/CI:

    { "<doi>": [["YYYY-MM-DD", count], ...] }   # oldest → newest, ≤ 3 entries

Efficiency: counts come from one paginated Crossref query per *(journal, year)*
(ISSN + date filter, selecting only DOI + count) — not one call per paper.
"""

from __future__ import annotations

import datetime
import json
import time
from pathlib import Path
from typing import TYPE_CHECKING, Callable

if TYPE_CHECKING:  # pragma: no cover - typing only
    import requests

CROSSREF_WORKS = "https://api.crossref.org/works"
CROSSREF_WORK = "https://api.crossref.org/works/{doi}"
ROWS = 200
DEFAULT_THROTTLE = 0.5
DEFAULT_RETRIES = 5
DEFAULT_BACKOFF = 2.0
MAX_SNAPSHOTS = 3          # at most three updates per paper
TRACK_MONTHS = 3          # only keep updating within 3 months of publication

FETCH_FAILED = object()   # request itself failed (429/network) — do not cache

CITATIONS_DIR = Path(__file__).resolve().parent.parent / "citations"


# ---- history helpers --------------------------------------------------------
def counts_path(journal_key: str, year: str, base: Path | str = CITATIONS_DIR) -> Path:
    return Path(base) / journal_key / f"{year}.json"


def load_history(path: Path | str) -> dict[str, list]:
    path = Path(path)
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (ValueError, OSError):
        return {}


def save_history(path: Path | str, history: dict[str, list]) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(history, ensure_ascii=False, sort_keys=True), encoding="utf-8")


def latest_count(snapshots: list) -> int | None:
    return snapshots[-1][1] if snapshots else None


def citation_delta(snapshots: list) -> int:
    """Gain between the first and latest snapshot (the rising signal); 0 if <2."""
    if not snapshots or len(snapshots) < 2:
        return 0
    return snapshots[-1][1] - snapshots[0][1]


def _months_between(pub_date: str, today: datetime.date) -> int | None:
    if not isinstance(pub_date, str) or len(pub_date) < 7 or pub_date[4] != "-":
        return None
    y, m = int(pub_date[:4]), int(pub_date[5:7])
    return (today.year - y) * 12 + (today.month - m)


def is_due(snapshots: list, pub_date: str, today: datetime.date) -> bool:
    """Whether a paper should be (re)snapshotted now.

    * No snapshot yet -> due (addition).
    * Otherwise only while < MAX_SNAPSHOTS, within TRACK_MONTHS of publication, and
      not already snapshotted this calendar month.
    """
    if not snapshots:
        return True
    if len(snapshots) >= MAX_SNAPSHOTS:
        return False
    months = _months_between(pub_date, today)
    if months is None or months > TRACK_MONTHS:
        return False
    return snapshots[-1][0][:7] < today.strftime("%Y-%m")


def record_snapshot(snapshots: list, date_iso: str, count: int) -> list:
    """Append a snapshot (immutably), keeping the last MAX_SNAPSHOTS."""
    return [*snapshots, [date_iso, count]][-MAX_SNAPSHOTS:]


# ---- Crossref fetch ---------------------------------------------------------
def _session(mailto: str = "", session: "requests.Session | None" = None) -> "requests.Session":
    import requests

    sess = session or requests.Session()
    sess.headers.setdefault("User-Agent", f"bio-trend/0.1 (mailto:{mailto})" if mailto else "bio-trend/0.1")
    return sess


def count_by_doi(
    doi: str, session: "requests.Session", *,
    retries: int = DEFAULT_RETRIES, backoff: float = DEFAULT_BACKOFF, sleep=time.sleep,
) -> int | None | object:
    """Crossref ``is-referenced-by-count`` for a single DOI (reference behaviour)."""
    for attempt in range(retries + 1):
        try:
            resp = session.get(CROSSREF_WORK.format(doi=doi), timeout=30)
            if resp.status_code == 404:
                return None
            if resp.status_code == 429:
                if attempt < retries:
                    sleep(backoff * (2 ** attempt)); continue
                return FETCH_FAILED
            resp.raise_for_status()
            return resp.json().get("message", {}).get("is-referenced-by-count")
        except Exception:
            if attempt < retries:
                sleep(backoff * (2 ** attempt)); continue
            return FETCH_FAILED
    return FETCH_FAILED


def fetch_counts_for_source(
    issn: str, *, from_date: str, to_date: str, mailto: str = "",
    session: "requests.Session | None" = None, throttle: float = DEFAULT_THROTTLE,
    retries: int = DEFAULT_RETRIES, backoff: float = DEFAULT_BACKOFF, sleep=time.sleep,
    log: Callable[[str], None] = lambda *_: None,
) -> dict[str, int]:
    """``{doi: is-referenced-by-count}`` for a journal (ISSN) in a date range."""
    sess = _session(mailto, session)
    filt = f"issn:{issn},from-pub-date:{from_date},until-pub-date:{to_date},type:journal-article"
    counts: dict[str, int] = {}
    cursor = "*"
    while cursor:
        params = {"filter": filt, "rows": ROWS, "cursor": cursor,
                  "select": "DOI,is-referenced-by-count"}
        if mailto:
            params["mailto"] = mailto
        data = None
        for attempt in range(retries + 1):
            try:
                resp = sess.get(CROSSREF_WORKS, params=params, timeout=60)
                if resp.status_code == 429:
                    if attempt < retries:
                        sleep(backoff * (2 ** attempt)); continue
                    raise RuntimeError("Crossref rate-limited (429) after retries")
                resp.raise_for_status()
                data = resp.json()
                break
            except Exception:
                if attempt < retries:
                    sleep(backoff * (2 ** attempt)); continue
                raise
        message = data.get("message", {})
        items = message.get("items", [])
        for it in items:
            doi = (it.get("DOI") or "").strip().lower()
            n = it.get("is-referenced-by-count")
            if doi and isinstance(n, int):
                counts[doi] = n
        cursor = message.get("next-cursor")
        log(f"  {issn}: {len(counts)} counts so far…")
        if not items:
            break
        sleep(throttle)
    return counts
