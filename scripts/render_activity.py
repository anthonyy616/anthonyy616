"""Render the "Recent Activity" section of README.md.

Fetches public events for ``anthonyy616`` from the public GitHub REST API
(no token required, single request) and rewrites the content between the
activity markers in README.md.

Designed to run in GitHub Actions (ubuntu-latest, python3 preinstalled).
Stdlib only: urllib, json, datetime, pathlib.
"""

from __future__ import annotations

import json
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

README_PATH = Path("README.md")
START_MARKER = "<!-- START_SECTION:activity -->"
END_MARKER = "<!-- END_SECTION:activity -->"
USER = "anthonyy616"
API_URL = f"https://api.github.com/users/{USER}/events/public?per_page=30"
MAX_ITEMS = 6


def fetch_events() -> list[dict]:
    """Fetch recent public events for the user."""
    request = urllib.request.Request(
        API_URL,
        headers={
            "Accept": "application/vnd.github+json",
            "User-Agent": f"{USER}-profile-activity",
        },
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.load(response)


def sanitize(text: str) -> str:
    """Strip markdown/code constructs from user-controlled strings."""
    for char in ("`", "[", "]", "\n", "\r"):
        text = text.replace(char, "'")
    return text


def repo_link(repo: str) -> str:
    return f"[{repo}](https://github.com/{repo})"


def describe(event: dict) -> str | None:
    """Return a one-line markdown description for a supported event type."""
    kind = event.get("type", "")
    repo = event.get("repo", {}).get("name", "")
    payload = event.get("payload", {}) or {}

    if kind == "PushEvent":
        commits = payload.get("size", 1)
        ref = (payload.get("ref") or "").split("/")[-1]
        branch = f" to `{sanitize(ref)}`" if ref else ""
        return f"pushed {commits} commit(s){branch} to {repo_link(repo)}"
    if kind == "PullRequestEvent":
        pr = payload.get("pull_request", {}) or {}
        title = sanitize(pr.get("title") or "")
        url = pr.get("html_url") or f"https://github.com/{repo}/pulls"
        return f"{payload.get('action', 'updated')} PR [{title}]({url})"
    if kind == "IssuesEvent":
        issue = payload.get("issue", {}) or {}
        title = sanitize(issue.get("title") or "")
        url = issue.get("html_url") or f"https://github.com/{repo}/issues"
        return f"{payload.get('action', 'updated')} issue [{title}]({url})"
    if kind == "WatchEvent":
        return f"starred {repo_link(repo)}"
    if kind == "ForkEvent":
        return f"forked {repo_link(repo)}"
    if kind == "CreateEvent":
        ref_type = payload.get("ref_type", "repository")
        ref = payload.get("ref")
        detail = f"`{sanitize(ref)}`" if ref else "repository"
        return f"created {ref_type} {detail} in {repo_link(repo)}"
    if kind == "ReleaseEvent":
        release = payload.get("release", {}) or {}
        tag = sanitize(release.get("tag_name") or "")
        url = release.get("html_url") or f"https://github.com/{repo}/releases"
        return f"published release [{tag}]({url})"
    if kind == "PublicEvent":
        return f"open-sourced {repo_link(repo)}"
    # Unsupported event types are skipped rather than shown as noise.
    return None


def days_ago(iso_timestamp: str) -> str:
    """Humanize an ISO-8601 UTC timestamp."""
    try:
        created = datetime.fromisoformat(iso_timestamp.replace("Z", "+00:00"))
    except (ValueError, AttributeError):
        return "recently"
    days = (datetime.now(timezone.utc) - created).days
    if days <= 0:
        return "today"
    if days == 1:
        return "yesterday"
    if days < 14:
        return f"{days}d ago"
    return f"{days // 7}w ago"


def build_section(events: list[dict]) -> str | None:
    """Build the markdown block injected between the markers."""
    items: list[str] = []
    for event in events:
        description = describe(event)
        if description:
            items.append(f"- **{days_ago(event.get('created_at', ''))}** — {description}")
        if len(items) >= MAX_ITEMS:
            break
    if not items:
        return None
    refreshed = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    header = f"*Last refreshed {refreshed} by [GitHub Actions](.github/workflows/activity.yml).*"
    return "\n".join([header, *items])


def main() -> int:
    try:
        events = fetch_events()
    except Exception as error:  # noqa: BLE001 - fail open, keep README untouched
        print(f"warning: could not fetch activity ({error}); README left unchanged")
        return 0

    section = build_section(events)
    if section is None:
        print("warning: no renderable activity found; README left unchanged")
        return 0

    content = README_PATH.read_text(encoding="utf-8")
    try:
        start = content.index(START_MARKER) + len(START_MARKER)
        end = content.index(END_MARKER)
    except ValueError:
        print("warning: activity markers missing from README.md")
        return 1

    updated = content[:start] + "\n\n" + section + "\n\n" + content[end:]
    README_PATH.write_text(updated, encoding="utf-8")
    print(f"rendered activity section ({len(events)} events fetched)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
