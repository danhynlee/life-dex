from datetime import datetime, timedelta, timezone

import ingest

NOW = datetime(2026, 10, 15, 6, 0, tzinfo=timezone.utc)


def commit(sha, date="2026-10-14T12:00:00Z"):
    return {"sha": sha, "commit": {
        "author": {"date": date}, "committer": {"date": date},
        "message": f"msg {sha}\n\nlong body",
    }}


def repo(name, pushed="2026-10-14T12:00:00Z", fork=False):
    return {"name": name, "full_name": f"danny/{name}", "owner": {"login": "danny"},
            "fork": fork, "pushed_at": pushed}


class FakeGH:
    def __init__(self, repos, commits):
        self.repos, self.commits_by_repo, self.calls = repos, commits, []

    def login(self):
        return "danny"

    def owned_repos(self):
        return self.repos

    def commits(self, owner, name, author, since):
        self.calls.append((name, since))
        return [c for c in self.commits_by_repo.get(name, [])
                if c["commit"]["committer"]["date"] >= since]


class FakeStore:
    def __init__(self):
        self.items, self.cursor = {}, None

    def put_commit(self, item):
        if item["sha"] in self.items:
            return False
        self.items[item["sha"]] = item
        return True

    def get_cursor(self):
        return self.cursor

    def set_cursor(self, ts):
        self.cursor = ts


def test_first_run_backfills_30_days():
    gh = FakeGH([repo("a")], {"a": [commit("s1"), commit("old", "2026-09-01T00:00:00Z")]})
    store = FakeStore()
    out = ingest.run(gh, store, NOW)
    assert out["since"] == "2026-09-15T06:00:00Z"
    assert set(store.items) == {"s1"}
    assert store.cursor == "2026-10-15T06:00:00Z"


def test_rerun_adds_zero():
    gh = FakeGH([repo("a")], {"a": [commit("s1"), commit("s2")]})
    store = FakeStore()
    ingest.run(gh, store, NOW)
    out = ingest.run(gh, store, NOW + timedelta(hours=1))
    assert out["added"] == 0 and out["skipped"] == 2


def test_late_push_is_caught_by_lookback():
    gh = FakeGH([repo("a")], {"a": []})
    store = FakeStore()
    ingest.run(gh, store, NOW)
    # Committed 30 min before the last run, but only pushed afterwards.
    gh.commits_by_repo["a"] = [commit("late", "2026-10-15T05:30:00Z")]
    gh.repos = [repo("a", pushed="2026-10-15T06:40:00Z")]
    out = ingest.run(gh, store, NOW + timedelta(hours=1))
    assert out["since"] == "2026-10-12T06:00:00Z"
    assert out["added"] == 1


def test_skips_forks_and_stale_repos():
    gh = FakeGH([repo("a"), repo("fork", fork=True), repo("stale", pushed="2025-01-01T00:00:00Z"),
                 repo("never", pushed=None)], {})
    ingest.run(gh, FakeStore(), NOW)
    assert [name for name, _ in gh.calls] == ["a"]


def test_same_sha_in_two_repos_stored_once():
    gh = FakeGH([repo("a"), repo("b")], {"a": [commit("dup")], "b": [commit("dup")]})
    store = FakeStore()
    out = ingest.run(gh, store, NOW)
    assert (out["added"], out["skipped"]) == (1, 1)


def test_to_item_keeps_first_line_only():
    item = ingest.to_item("danny/a", commit("s1"))
    assert item == {"sha": "s1", "repo": "danny/a", "authored_at": "2026-10-14T12:00:00Z",
                    "committed_at": "2026-10-14T12:00:00Z", "message": "msg s1"}
