# OpenAI Python SDK

## Install

```bash
pip install openai
# or in this repo:
uv add openai
```

## Minimal client

```python
from pathlib import Path
import json
from openai import OpenAI

cfg = json.loads(Path.home().joinpath(".grok-proxy/client-config.json").read_text())
client = OpenAI(base_url=cfg["base_url"], api_key=cfg["api_key"])

resp = client.chat.completions.create(
    model=cfg["model"],  # real id e.g. grok-4.5
    messages=[
        {"role": "user", "content": "List top-level files and summarize the project in 2 sentences."}
    ],
    extra_body={
        "cwd": "/path/to/repo",
        "max_turns": 15,
        "x_grok": {"workspace_mode": "read_only"},
    },
)
print(resp.choices[0].message.content)
print("session:", getattr(resp, "grok", None) or resp.model_extra)
```

> Pydantic/OpenAI models may put proxy extensions under `model_extra` depending on SDK version. Prefer inspecting the raw JSON if `grok` is missing:

```python
raw = resp.model_dump()
print(raw.get("grok"))
```

## Streaming

```python
stream = client.chat.completions.create(
    model=cfg["model"],
    messages=[{"role": "user", "content": "Say hello briefly."}],
    stream=True,
    extra_body={"cwd": "/path/to/repo"},
)
for chunk in stream:
    delta = chunk.choices[0].delta.content or ""
    print(delta, end="", flush=True)
```

Stream chunks are produced from the **orchestrator event journal** (v0.2), so `grok.response_id` appears on terminal chunks when present.

## Multi-turn via session_id

```python
r1 = client.chat.completions.create(
    model=cfg["model"],
    messages=[{"role": "user", "content": "Remember codeword: orchid"}],
    extra_body={"cwd": "/path/to/repo"},
)
# Extract session from raw payload
payload = r1.model_dump()
sid = (payload.get("grok") or {}).get("session_id")

r2 = client.chat.completions.create(
    model=cfg["model"],
    messages=[{"role": "user", "content": "What was the codeword?"}],
    extra_body={"cwd": "/path/to/repo", "session_id": sid},
)
print(r2.choices[0].message.content)
```

`session_id` must reuse the **same cwd** when `GROK_PROXY_STRICT_SESSION_CWD=true` (default).

## Responses API (httpx)

OpenAI SDK Responses client may work if pointed at `/v1`; for maximum control use HTTP:

```python
import httpx

base = cfg["base_url"].rstrip("/")
headers = {"Authorization": f"Bearer {cfg['api_key']}"}
with httpx.Client(base_url=base, headers=headers, timeout=600.0) as http:
    r = http.post(
        "/responses",
        json={
            "input": "Summarize architecture",
            "x_grok": {"cwd": "/path/to/repo", "workspace_mode": "read_only"},
        },
    )
    r.raise_for_status()
    print(r.json()["status"], r.json().get("x_grok", {}).get("text"))
```

## Troubleshooting

| Symptom | Fix |
|---------|-----|
| `unknown model id` | Use id from `GET /v1/models` or `grok models`; alias `grok-build` is remapped |
| `401` | Check `api_key` from `~/.grok-proxy/api_key` |
| `403 cwd_forbidden` | Expand `GROK_PROXY_CWD_ALLOWLIST` or key allowlist |
| Hang with no output | Headless is forced always-approve; ACP may wait on permissions |
