import json

import pytest

from github_client import GitHubClient, GitHubError, next_link

TOKEN = "github_pat_SECRET"


@pytest.mark.parametrize("header, expected", [
    (None, None),
    ("", None),
    ('<https://api.github.com/x?page=2>; rel="next", <https://api.github.com/x?page=5>; rel="last"',
     "https://api.github.com/x?page=2"),
    ('<https://api.github.com/x?page=1>; rel="prev", <https://api.github.com/x?page=3>; rel="next"',
     "https://api.github.com/x?page=3"),
    ('<https://api.github.com/x?page=1>; rel="first", <https://api.github.com/x?page=4>; rel="prev"', None),
])
def test_next_link(header, expected):
    assert next_link(header) == expected


def fake_transport(pages):
    """pages: {url: (status, link, body_obj)}; records requests made."""
    seen = []

    def transport(req):
        seen.append(req)
        status, link, body = pages[req.full_url]
        return status, link, json.dumps(body).encode()

    return transport, seen


def test_paginate_follows_link_header():
    p1 = "https://api.github.com/user/repos?per_page=100&affiliation=owner"
    p2 = "https://api.github.com/user/repos?per_page=100&affiliation=owner&page=2"
    transport, seen = fake_transport({
        p1: (200, f'<{p2}>; rel="next"', [{"id": 1}, {"id": 2}]),
        p2: (200, None, [{"id": 3}]),
    })
    gh = GitHubClient(TOKEN, transport)
    assert [r["id"] for r in gh.owned_repos()] == [1, 2, 3]
    assert gh.calls == 2
    assert seen[0].get_header("Authorization") == f"Bearer {TOKEN}"
    assert seen[0].get_header("User-agent") == "life-dex"


def test_empty_repo_409_returns_no_commits():
    url = "https://api.github.com/repos/danny/empty/commits?per_page=100&author=danny&since=2026-10-01T00%3A00%3A00Z"
    transport, _ = fake_transport({url: (409, None, {"message": "Git Repository is empty."})})
    gh = GitHubClient(TOKEN, transport)
    assert gh.commits("danny", "empty", author="danny", since="2026-10-01T00:00:00Z") == []


def test_401_raises_without_leaking_token():
    transport, _ = fake_transport({"https://api.github.com/user": (401, None, {"message": "Bad credentials"})})
    gh = GitHubClient(TOKEN, transport)
    with pytest.raises(GitHubError) as exc:
        gh.login()
    assert exc.value.status == 401
    assert TOKEN not in str(exc.value)
