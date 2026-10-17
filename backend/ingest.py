"""Ingest orchestration. Takes a client and a store as arguments (dependency
injection) so tests run with in-memory fakes: no network, no AWS, no moto."""
from __future__ import annotations

from datetime import UTC, datetime, timedelta

BACKFILL = timedelta(days=30)  # first run (no cursor)
# A commit's date is when it was *made*, not pushed. A commit made at 1:50 and
# pushed at 3:10 is invisible to a 2:00 run and has a date before a 2:00 cursor,
# so `since=cursor` would miss it forever. Re-scan a window; SHA dedup makes it free.
LOOKBACK = timedelta(days=3)


def iso(dt: datetime) -> str:
    return dt.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def parse_iso(s: str) -> datetime:
    return datetime.strptime(s, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC)


def to_item(repo_full_name: str, c: dict) -> dict:
    commit = c["commit"]
    return {
        "sha": c["sha"],
        "repo": repo_full_name,
        "authored_at": commit["author"]["date"],     # UTC ISO; T5 buckets to America/New_York
        "committed_at": commit["committer"]["date"],
        "message": commit["message"].split("\n", 1)[0][:200],
    }


def run(gh, store, now: datetime) -> dict:
    cursor = store.get_cursor()
    since = iso(parse_iso(cursor) - LOOKBACK) if cursor else iso(now - BACKFILL)

    login = gh.login()
    # Forks: GitHub's profile count excludes them, so the done-check would drift.
    # pushed_at: skip untouched repos so an hourly run costs ~2 + (active repos) calls.
    # Same-format ISO-Z strings compare correctly as plain strings.
    repos = [
        r for r in gh.owned_repos()
        if not r["fork"] and (r.get("pushed_at") or "") >= since
    ]

    added = skipped = 0
    for r in repos:
        for c in gh.commits(r["owner"]["login"], r["name"], author=login, since=since):
            if store.put_commit(to_item(r["full_name"], c)):
                added += 1
            else:
                skipped += 1

    # Only advance the cursor after every repo succeeded; a crash mid-run is
    # simply retried next hour.
    store.set_cursor(iso(now))
    return {"since": since, "repos_scanned": len(repos), "added": added, "skipped": skipped}
