#!/usr/bin/env bash
# Run all local E2E smokes that apply.
# Usage:
#   ./scripts/e2e_all.sh
#   E2E_LIVE_PROMPT=1 ./scripts/e2e_all.sh
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
chmod +x scripts/e2e_*.sh scripts/probe_acp.py 2>/dev/null || true

echo "######## MCP ########"
./scripts/e2e_mcp.sh

echo
echo "######## ACP ########"
./scripts/e2e_acp.sh || {
  echo "ACP probe failed (is grok agent stdio available?)"
  exit 1
}

echo
echo "######## HTTP ########"
if curl -sf "${GROK_PROXY_BASE_URL:-http://127.0.0.1:8787}/health" >/dev/null 2>&1; then
  ./scripts/e2e_http.sh
else
  echo "  SKIP  HTTP (proxy not running on 127.0.0.1:8787)"
  echo "        start: uv run grok-proxy"
  echo "        then:  ./scripts/e2e_http.sh"
fi

echo
echo "######## unit/integration ########"
uv run pytest -q -m "not grok_e2e"

echo
echo "All applicable E2E steps finished."
