#!/usr/bin/env bash
# Dispatch the existing GitHub dashboard workflow. This script never handles
# brokerage data, credentials, or account identifiers.
set -euo pipefail

slot="postmarket"
notify="true"

usage() {
  echo "Usage: $0 [--slot premarket|postmarket] [--no-notify]"
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --slot)
      slot="${2:-}"
      shift 2
      ;;
    --no-notify)
      notify="false"
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      usage >&2
      exit 2
      ;;
  esac
done

if [[ "$slot" != "premarket" && "$slot" != "postmarket" ]]; then
  echo "--slot must be premarket or postmarket" >&2
  exit 2
fi

if ! command -v gh >/dev/null; then
  echo "GitHub CLI is required. Install it, then run: gh auth login" >&2
  exit 1
fi

if ! gh auth status >/dev/null 2>&1; then
  echo "GitHub CLI is not authenticated. Run: gh auth login" >&2
  exit 1
fi

gh workflow run .github/workflows/daily.yml \
  --ref main \
  --field "report_slot=$slot" \
  --field "send_notification=$notify" \
  --field "trigger_source=chatgpt_manual"

echo "Dashboard build requested ($slot). Check status with: gh run list --workflow daily.yml --limit 1"
