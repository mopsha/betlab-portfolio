#!/usr/bin/env bash
# Start the page-sync routine right after a run, so the page updates within
# minutes. Needs the routine's API token as the ROUTINE_TOKEN secret; without
# it this is a no-op and the page waits for the routine's scheduled sync.
# A rejected call fails the workflow on purpose: GitHub then emails you, so a
# broken sync (say, a revoked token) can't go unnoticed.
set -euo pipefail

if [ -z "${ROUTINE_TOKEN:-}" ]; then
  echo "ROUTINE_TOKEN not set: the page updates at the routine's scheduled time"
  exit 0
fi

code=$(curl -sS -X POST "https://api.anthropic.com/v1/claude_code/routines/trig_01AsDvmu7oHR6WcVyBvNSJLH/fire" \
  -H "Authorization: Bearer ${ROUTINE_TOKEN}" \
  -H "anthropic-beta: experimental-cc-routine-2026-04-01" \
  -H "anthropic-version: 2023-06-01" \
  -H "Content-Type: application/json" \
  -d '{}' -o /tmp/fire_response.json -w "%{http_code}")

if [ "${code}" -ge 200 ] && [ "${code}" -lt 300 ]; then
  echo "page sync started: HTTP ${code}"
else
  echo "page sync FAILED: HTTP ${code}"
  head -c 300 /tmp/fire_response.json; echo
  echo "If the token was revoked or regenerated, generate a new one on the routine's API trigger"
  echo "and run: gh secret set ROUTINE_TOKEN --repo mopsha/betlab"
  exit 1
fi
