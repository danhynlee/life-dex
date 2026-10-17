"""Minimal GitHub REST client on stdlib urllib (no third-party deps to package)."""
from __future__ import annotations

import json
import re
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable, Iterator
from typing import Any

API = "https://api.github.com"
_NEXT_RE = re.compile(r'<([^>]+)>;\s*rel="next"')

# (status, Link header, body). Injectable so tests never touch the network.
Transport = Callable[[urllib.request.Request], tuple[int, str | None, bytes]]


class GitHubError(RuntimeError):
    def __init__(self, status: int, url: str, body: str):
        # Never include request headers here: they carry the token.
        super().__init__(f"GitHub {status} for {url}: {body[:200]}")
        self.status = status


def next_link(link_header: str | None) -> str | None:
    """Return the rel="next" URL from a GitHub Link header, or None on the last page."""
    if not link_header:
        return None
    m = _NEXT_RE.search(link_header)
    return m.group(1) if m else None


def urlopen_transport(req: urllib.request.Request, timeout: float = 15) -> tuple[int, str | None, bytes]:
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, r.headers.get("Link"), r.read()
    except urllib.error.HTTPError as e:  # 4xx/5xx arrive as exceptions in urllib
        return e.code, e.headers.get("Link") if e.headers else None, e.read()


class GitHubClient:
    def __init__(self, token: str, transport: Transport = urlopen_transport):
        self._token = token
        self._transport = transport
        self.calls = 0  # logged per run to check against the rate-limit budget

    def _url(self, path: str, params: dict) -> str:
        return f"{API}{path}?{urllib.parse.urlencode(params)}" if params else f"{API}{path}"

    def _request(self, url: str) -> tuple[Any, str | None]:
        req = urllib.request.Request(url, headers={
            "Authorization": f"Bearer {self._token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "life-dex",  # GitHub rejects requests without one
        })
        status, link, body = self._transport(req)
        self.calls += 1
        if status >= 400:
            raise GitHubError(status, url, body.decode("utf-8", errors="replace"))
        return json.loads(body), link

    def get(self, path: str, **params: Any) -> Any:
        data, _ = self._request(self._url(path, params))
        return data

    def paginate(self, path: str, **params: Any) -> Iterator[dict]:
        url: str | None = self._url(path, {"per_page": 100, **params})
        while url:
            data, link = self._request(url)
            yield from data
            url = next_link(link)  # next URL already carries every query param

    def login(self) -> str:
        return self.get("/user")["login"]

    def owned_repos(self) -> list:
        return list(self.paginate("/user/repos", affiliation="owner"))

    def commits(self, owner: str, repo: str, author: str, since: str) -> list:
        """Default-branch commits by `author` since an ISO-8601 UTC timestamp."""
        try:
            return list(self.paginate(f"/repos/{owner}/{repo}/commits", author=author, since=since))
        except GitHubError as e:
            if e.status == 409:  # "Git Repository is empty"
                return []
            raise
