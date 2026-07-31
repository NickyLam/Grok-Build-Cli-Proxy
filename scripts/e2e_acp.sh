#!/usr/bin/env bash
# Live ACP handshake (+ optional short prompt) via scripts/probe_acp.py
# Usage:
#   ./scripts/e2e_acp.sh
#   E2E_LIVE_PROMPT=1 ./scripts/e2e_acp.sh
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
GROK_BIN="${GROK_BIN:-grok}"

echo "== e2e_acp =="
if ! command -v "$GROK_BIN" >/dev/null 2>&1; then
  echo "  FAIL  grok not on PATH (set GROK_BIN)"
  exit 1
fi

echo "  info  grok=$GROK_BIN ($(command -v "$GROK_BIN"))"

if [[ "${E2E_LIVE_PROMPT:-0}" == "1" ]]; then
  uv run python scripts/probe_acp.py --grok-bin "$GROK_BIN" --cwd "$ROOT" \
    --prompt "Reply with exactly the single word: pong" --timeout 180
else
  uv run python scripts/probe_acp.py --grok-bin "$GROK_BIN" --cwd "$ROOT"
  echo "  SKIP  live prompt (set E2E_LIVE_PROMPT=1)"
fi

echo "  PASS  ACP probe"
if [[ "${E2E_LIVE_PROMPT:-0}" == "1" ]]; then
  echo "  info  pytest live (optional): RUN_GROK_E2E=1 uv run pytest -m grok_e2e -q"
fi
