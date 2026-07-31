from __future__ import annotations

import json
import logging
import os
import secrets
import stat
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path

logger = logging.getLogger("grok_proxy")

# Prefix helps humans recognize this is a local proxy key, not an xAI key.
API_KEY_PREFIX = "sk-gp-"


def default_state_dir() -> Path:
    override = os.environ.get("GROK_PROXY_HOME", "").strip()
    if override:
        return Path(override).expanduser().resolve()
    return Path.home() / ".grok-proxy"


@dataclass
class StoredCredentials:
    api_key: str
    host: str
    port: int
    model_id: str
    base_url: str
    generated_at: str
    source: str  # "env" | "generated" | "file"


def _key_file(state_dir: Path) -> Path:
    return state_dir / "api_key"


def _credentials_json(state_dir: Path) -> Path:
    return state_dir / "credentials.json"


def generate_api_key() -> str:
    return API_KEY_PREFIX + secrets.token_urlsafe(32)


def _chmod_private(path: Path) -> None:
    try:
        path.chmod(stat.S_IRUSR | stat.S_IWUSR)  # 0o600
    except OSError:
        pass


def load_persisted_api_key(state_dir: Path | None = None) -> str | None:
    state_dir = state_dir or default_state_dir()
    key_path = _key_file(state_dir)
    if key_path.is_file():
        text = key_path.read_text(encoding="utf-8").strip()
        if text:
            return text
    cred_path = _credentials_json(state_dir)
    if cred_path.is_file():
        try:
            data = json.loads(cred_path.read_text(encoding="utf-8"))
            key = str(data.get("api_key") or "").strip()
            if key:
                return key
        except (json.JSONDecodeError, OSError):
            pass
    return None


def persist_api_key(api_key: str, state_dir: Path | None = None) -> Path:
    state_dir = state_dir or default_state_dir()
    state_dir.mkdir(parents=True, exist_ok=True)
    try:
        state_dir.chmod(stat.S_IRWXU)  # 0o700
    except OSError:
        pass
    key_path = _key_file(state_dir)
    key_path.write_text(api_key + "\n", encoding="utf-8")
    _chmod_private(key_path)
    return key_path


def ensure_api_key(
    configured: str,
    *,
    state_dir: Path | None = None,
    persist: bool = True,
) -> tuple[str, str]:
    """
    Resolve API key: env/config > persisted file > generate new.

    Returns:
        (api_key, source) where source is env|file|generated
    """
    state_dir = state_dir or default_state_dir()
    configured = (configured or "").strip()
    if configured:
        if persist:
            # Keep file in sync when user supplies env key (optional convenience)
            pass
        return configured, "env"

    existing = load_persisted_api_key(state_dir)
    if existing:
        return existing, "file"

    key = generate_api_key()
    if persist:
        persist_api_key(key, state_dir)
        logger.info("Generated new API key and saved to %s", _key_file(state_dir))
    return key, "generated"


def build_base_url(host: str, port: int, *, public_host: str | None = None) -> str:
    """Client-facing base URL (always http for local proxy)."""
    h = public_host or host
    if h in ("0.0.0.0", "::"):
        h = "127.0.0.1"
    return f"http://{h}:{port}/v1"


def build_connection_info(
    *,
    api_key: str,
    host: str,
    port: int,
    model_id: str,
    source: str,
    public_host: str | None = None,
) -> StoredCredentials:
    base_url = build_base_url(host, port, public_host=public_host)
    return StoredCredentials(
        api_key=api_key,
        host=host,
        port=port,
        model_id=model_id,
        base_url=base_url,
        generated_at=datetime.now(UTC).isoformat(),
        source=source,
    )


def write_client_config_files(
    info: StoredCredentials,
    state_dir: Path | None = None,
) -> dict[str, Path]:
    """Write credentials.json, client-config.json, workbuddy-model.json for easy copy."""
    state_dir = state_dir or default_state_dir()
    state_dir.mkdir(parents=True, exist_ok=True)

    written: dict[str, Path] = {}

    cred_path = _credentials_json(state_dir)
    cred_path.write_text(
        json.dumps(asdict(info), indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    _chmod_private(cred_path)
    written["credentials"] = cred_path

    # Generic OpenAI-compatible client config (any agent)
    client = {
        "provider": "openai-compatible",
        "base_url": info.base_url,
        "api_key": info.api_key,
        "model": info.model_id,
        "model_id": info.model_id,
        "notes": (
            "Use with OpenAI SDKs / WorkBuddy Custom models. "
            "Grok auth uses local `grok login` or XAI_API_KEY; this api_key is proxy-only."
        ),
    }
    client_path = state_dir / "client-config.json"
    client_path.write_text(json.dumps(client, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    _chmod_private(client_path)
    written["client_config"] = client_path

    # WorkBuddy models.json entry shape (matches ~/.workbuddy/models.json)
    workbuddy_entry = {
        "id": info.model_id,
        "name": info.model_id,
        "vendor": "Custom",
        "url": info.base_url,
        "apiKey": info.api_key,
        "supportsToolCall": False,
        "supportsImages": False,
        "supportsReasoning": False,
        "useCustomProtocol": False,
    }
    wb_path = state_dir / "workbuddy-model.json"
    wb_path.write_text(
        json.dumps(workbuddy_entry, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    _chmod_private(wb_path)
    written["workbuddy_model"] = wb_path

    # Keep plain api_key file too
    written["api_key"] = persist_api_key(info.api_key, state_dir)

    return written


def workbuddy_models_path() -> Path:
    return Path.home() / ".workbuddy" / "models.json"


def install_workbuddy_model(
    info: StoredCredentials,
    *,
    models_path: Path | None = None,
    remove_ids: list[str] | None = None,
) -> Path | None:
    """
    Upsert this proxy as a Custom model in WorkBuddy models.json.
    Returns path written, or None if WorkBuddy dir does not exist.

    remove_ids: drop stale entries (e.g. old invalid "grok-build" id).
    """
    path = models_path or workbuddy_models_path()
    if not path.parent.is_dir():
        logger.warning(
            "WorkBuddy config dir not found (%s); skip auto-install. "
            "Copy %s manually.",
            path.parent,
            default_state_dir() / "workbuddy-model.json",
        )
        return None

    entries: list[dict] = []
    if path.is_file():
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(raw, list):
                entries = [e for e in raw if isinstance(e, dict)]
        except json.JSONDecodeError:
            logger.warning("Could not parse %s; creating new list", path)

    drop = set(remove_ids or [])
    # Also drop prior proxy entries that pointed at our base_url but wrong id
    if drop:
        entries = [
            e
            for e in entries
            if e.get("id") not in drop and e.get("name") not in drop
        ]

    entry = {
        "id": info.model_id,
        "name": info.model_id,
        "vendor": "Custom",
        "url": info.base_url,
        "apiKey": info.api_key,
        "supportsToolCall": False,
        "supportsImages": False,
        "supportsReasoning": False,
        "useCustomProtocol": False,
    }

    replaced = False
    for i, e in enumerate(entries):
        same_id = e.get("id") == info.model_id or e.get("name") == info.model_id
        same_proxy = (
            isinstance(e.get("url"), str)
            and e.get("url").rstrip("/") == info.base_url.rstrip("/")
            and e.get("vendor") == "Custom"
        )
        if same_id or same_proxy:
            entries[i] = {**e, **entry}
            replaced = True
            break
    if not replaced:
        entries.append(entry)

    # Backup once
    if path.is_file():
        bak = path.with_suffix(".json.bak")
        try:
            bak.write_text(path.read_text(encoding="utf-8"), encoding="utf-8")
        except OSError:
            pass

    path.write_text(json.dumps(entries, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    _chmod_private(path)
    logger.info("%s WorkBuddy model %r in %s", "Updated" if replaced else "Added", info.model_id, path)
    return path


def format_startup_banner(
    info: StoredCredentials,
    *,
    written: dict[str, Path] | None = None,
    workbuddy_installed: Path | None = None,
) -> str:
    lines = [
        "",
        "=" * 60,
        "  Grok Build CLI Proxy is ready (OpenAI-compatible)",
        "=" * 60,
        f"  Base URL : {info.base_url}",
        f"  API Key  : {info.api_key}",
        f"  Model ID : {info.model_id}",
        f"  Key source: {info.source}",
        "",
        "  WorkBuddy / any OpenAI-compatible client:",
        f"    url    = {info.base_url}",
        f"    apiKey = {info.api_key}",
        f"    model  = {info.model_id}",
        "",
        "  WorkBuddy models.json entry:",
        "  " + json.dumps(
            {
                "id": info.model_id,
                "name": info.model_id,
                "vendor": "Custom",
                "url": info.base_url,
                "apiKey": info.api_key,
                "supportsToolCall": False,
                "supportsImages": False,
                "supportsReasoning": False,
                "useCustomProtocol": False,
            },
            ensure_ascii=False,
        ),
    ]
    if written:
        lines.append("")
        lines.append("  Saved local config:")
        for name, p in written.items():
            lines.append(f"    - {name}: {p}")
    if workbuddy_installed:
        lines.append("")
        lines.append(f"  Installed into WorkBuddy: {workbuddy_installed}")
        lines.append("  Restart / refresh WorkBuddy models if needed.")
    else:
        lines.append("")
        lines.append("  Tip: start with --install-workbuddy to write ~/.workbuddy/models.json")
    lines.extend(
        [
            "",
            "  Note: this API Key only guards the local proxy.",
            "  Grok itself uses `grok login` (subscription) or XAI_API_KEY.",
            "=" * 60,
            "",
        ]
    )
    return "\n".join(lines)
