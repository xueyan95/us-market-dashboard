#!/usr/bin/env python3
"""Export explicitly public research issues from the private companion repository."""
import datetime
import json
import os
import urllib.error
import urllib.request
from pathlib import Path

from research_inputs import public_entries


HERE = Path(__file__).resolve().parent
OUTPUT = HERE / "research_inputs.json"
REPO = os.environ.get("RESEARCH_REPO", "xueyan95/us-market-research-notes")
TOKEN = os.environ.get("RESEARCH_NOTES_TOKEN", "")


def fetch_issues():
    issues = []
    for page in range(1, 6):
        # The body schema is the source of truth. Fetching all issues avoids a
        # hidden dependency on a repository label existing before first use.
        url = f"https://api.github.com/repos/{REPO}/issues?state=all&per_page=100&page={page}"
        req = urllib.request.Request(url, headers={
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {TOKEN}",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "us-market-dashboard-research-sync",
        })
        with urllib.request.urlopen(req, timeout=30) as response:
            batch = json.loads(response.read().decode("utf-8"))
        issues.extend(item for item in batch if "pull_request" not in item)
        if len(batch) < 100:
            break
    return issues


def main():
    payload = {"as_of": datetime.datetime.now(datetime.timezone.utc).isoformat(),
               "source_repo": REPO, "available": False, "entries": []}
    if not TOKEN:
        payload["reason"] = "RESEARCH_NOTES_TOKEN is not configured"
    else:
        try:
            payload["entries"] = public_entries(fetch_issues())
            payload["available"] = True
        except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError) as exc:
            payload["reason"] = f"Research sync failed: {exc}"
    OUTPUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"研究输入同步：available={payload['available']} public={len(payload['entries'])}")


if __name__ == "__main__":
    main()
