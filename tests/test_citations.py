"""Citation tracking policy: snapshot on addition + monthly within 3 months, max 3."""

import datetime

from bio_trend.citations import citation_delta, is_due, latest_count, record_snapshot

TODAY = datetime.date(2026, 6, 15)


def test_is_due_on_addition():
    assert is_due([], "2024-01-01", TODAY) is True  # never seen -> snapshot


def test_is_due_caps_at_three():
    snaps = [["2026-04-01", 1], ["2026-05-01", 2], ["2026-06-01", 3]]
    assert is_due(snaps, "2026-04-01", TODAY) is False


def test_is_due_only_within_three_months_of_publication():
    # published 5 months ago -> beyond tracking window, no further updates
    assert is_due([["2026-01-10", 1]], "2026-01-01", TODAY) is False
    # published 2 months ago, last snapshot in a prior month -> due
    assert is_due([["2026-05-10", 1]], "2026-04-01", TODAY) is True


def test_is_due_at_most_once_per_month():
    # already snapshotted this month -> not due again
    assert is_due([["2026-06-02", 1]], "2026-05-01", TODAY) is False


def test_record_snapshot_caps_and_orders():
    s = []
    for d, n in [("2026-04-01", 1), ("2026-05-01", 4), ("2026-06-01", 9), ("2026-07-01", 12)]:
        s = record_snapshot(s, d, n)
    assert len(s) == 3                      # keeps the most recent three
    assert s[-1] == ["2026-07-01", 12]
    assert latest_count(s) == 12


def test_citation_delta_is_rising_signal():
    assert citation_delta([["2026-04-01", 2], ["2026-06-01", 9]]) == 7
    assert citation_delta([["2026-04-01", 5]]) == 0   # single snapshot -> no velocity
    assert citation_delta([]) == 0
