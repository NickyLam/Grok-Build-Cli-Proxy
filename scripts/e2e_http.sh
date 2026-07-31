#!/usr/bin/env bash
# HTTP smoke against a running grok-proxy.
# Usage:
#   uv run grok-proxy   # other terminal
#   ./scripts/e2e_http.sh
# Optional live model call:
#   E2E_LIVE_PROMPT=1 ./scripts/e2e_http.sh
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
BASE="${GROK_PROXY_BASE_URL:-http://127.0.0.1:8787}"
BASE_V1="${BASE%/}/v1"
KEY_FILE="${GROK_PROXY_API_KEY_FILE:-$HOME/.grok-proxy/api_key}"
KEY="${GROK_PROXY_API_KEY:-}"
if [[ -z "$KEY" && -f "$KEY_FILE" ]]; then
  KEY="$(tr -d '[:space:]' <"$KEY_FILE")"
fi
CWD="${E2E_CWD:-$ROOT}"
MODEL="${GROK_PROXY_MODEL:-}"

pass=0
fail=0

ok() { echo "  PASS  $1"; pass=$((pass + 1)); }
bad() { echo "  FAIL  $1 — $2"; fail=$((fail + 1)); }

need_jq() {
  command -v jq >/dev/null || { echo "jq required"; exit 2; }
}

need_jq
echo "== e2e_http =="
echo "base=$BASE cwd=$CWD"

# health (no auth)
code=$(curl -s -o /tmp/gp_health.json -w "%{http_code}" "$BASE/health" || true)
if [[ "$code" == "200" ]]; then
  ok "GET /health"
else
  bad "GET /health" "http $code (is grok-proxy running?)"
  echo "Start with: uv run grok-proxy"
  exit 1
fi

code=$(curl -s -o /tmp/gp_ready.json -w "%{http_code}" "$BASE/ready" || true)
[[ "$code" == "200" ]] && ok "GET /ready" || bad "GET /ready" "http $code"

if [[ -z "$KEY" ]]; then
  bad "auth key" "set GROK_PROXY_API_KEY or create $KEY_FILE"
  echo "Summary: $pass passed, $fail failed"
  exit 1
fi

auth=(-H "Authorization: Bearer $KEY" -H "Content-Type: application/json")

code=$(curl -s -o /tmp/gp_models.json -w "%{http_code}" "${auth[@]}" "$BASE_V1/models" || true)
if [[ "$code" == "200" ]]; then
  ok "GET /v1/models"
  if [[ -z "$MODEL" ]]; then
    MODEL=$(jq -r '.data[0].id // empty' /tmp/gp_models.json)
  fi
else
  bad "GET /v1/models" "http $code"
fi
MODEL="${MODEL:-grok-4.5}"
echo "model=$MODEL"

code=$(curl -s -o /tmp/gp_conn.json -w "%{http_code}" "${auth[@]}" "$BASE_V1/connection" || true)
[[ "$code" == "200" ]] && ok "GET /v1/connection" || bad "GET /v1/connection" "http $code"

# responses create (optional live)
if [[ "${E2E_LIVE_PROMPT:-0}" == "1" ]]; then
  code=$(curl -s -o /tmp/gp_resp.json -w "%{http_code}" "${auth[@]}" \
    -d "{\"model\":\"$MODEL\",\"input\":\"Reply with exactly: pong\",\"x_grok\":{\"cwd\":\"$CWD\",\"workspace_mode\":\"read_only\",\"timeout_sec\":120}}" \
    "$BASE_V1/responses" || true)
  if [[ "$code" == "200" ]]; then
    rid=$(jq -r '.id // empty' /tmp/gp_resp.json)
    st=$(jq -r '.status // empty' /tmp/gp_resp.json)
    ok "POST /v1/responses ($rid status=$st)"
    if [[ -n "$rid" ]]; then
      code=$(curl -s -o /tmp/gp_get.json -w "%{http_code}" "${auth[@]}" "$BASE_V1/responses/$rid" || true)
      [[ "$code" == "200" ]] && ok "GET /v1/responses/{id}" || bad "GET /v1/responses/{id}" "http $code"
    fi
  else
    bad "POST /v1/responses" "http $code body=$(head -c 200 /tmp/gp_resp.json 2>/dev/null || true)"
  fi

  code=$(curl -s -o /tmp/gp_chat.json -w "%{http_code}" "${auth[@]}" \
    -d "{\"model\":\"$MODEL\",\"messages\":[{\"role\":\"user\",\"content\":\"Reply with exactly: pong\"}],\"cwd\":\"$CWD\",\"stream\":false}" \
    "$BASE_V1/chat/completions" || true)
  if [[ "$code" == "200" ]]; then
    ok "POST /v1/chat/completions"
  else
    bad "POST /v1/chat/completions" "http $code"
  fi
else
  echo "  SKIP  live prompt (set E2E_LIVE_PROMPT=1 to enable)"
fi

# permissions list always works
code=$(curl -s -o /tmp/gp_perms.json -w "%{http_code}" "${auth[@]}" \
  "$BASE_V1/permissions?status=pending&limit=5" || true)
[[ "$code" == "200" ]] && ok "GET /v1/permissions" || bad "GET /v1/permissions" "http $code"

code=$(curl -s -o /tmp/gp_metrics.txt -w "%{http_code}" "$BASE/metrics" || true)
[[ "$code" == "200" ]] && ok "GET /metrics" || bad "GET /metrics" "http $code"

echo "Summary: $pass passed, $fail failed"
[[ "$fail" -eq 0 ]]
