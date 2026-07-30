from __future__ import annotations

import json
import logging
import os
import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger("grok_proxy")

# Friendly / outdated ids clients may send → map to CLI default when unknown.
MODEL_ALIASES = frozenset(
    {
        "grok-build",
        "grok-build-plan",
        "grok",
        "default",
        "auto",
    }
)

FALLBACK_MODEL = "grok-4.5"


@dataclass
class RuntimeModels:
    default_model: str
    available: list[str] = field(default_factory=list)
    source: str = "fallback"  # cache | cli | config | fallback


def _grok_home() -> Path:
    env = os.environ.get("GROK_HOME", "").strip()
    if env:
        return Path(env).expanduser()
    return Path.home() / ".grok"


def load_models_from_cache(cache_path: Path | None = None) -> RuntimeModels | None:
    path = cache_path or (_grok_home() / "models_cache.json")
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        logger.warning("Failed to read models cache %s: %s", path, e)
        return None

    models_obj = data.get("models") or {}
    if not isinstance(models_obj, dict) or not models_obj:
        return None

    available: list[str] = []
    default: str | None = None
    for mid, meta in models_obj.items():
        if not isinstance(mid, str):
            continue
        available.append(mid)
        info = (meta or {}).get("info") if isinstance(meta, dict) else None
        if isinstance(info, dict) and info.get("hidden"):
            continue
    # Prefer non-hidden list order; default = first non-hidden or first key
    non_hidden: list[str] = []
    for mid, meta in models_obj.items():
        info = (meta or {}).get("info") if isinstance(meta, dict) else {}
        if isinstance(info, dict) and info.get("hidden"):
            continue
        non_hidden.append(mid)
    available = non_hidden or list(models_obj.keys())
    default = available[0] if available else None
    if not default:
        return None
    return RuntimeModels(default_model=default, available=available, source="cache")


def load_models_from_cli(grok_bin: str = "grok", timeout: float = 15.0) -> RuntimeModels | None:
    try:
        proc = subprocess.run(
            [grok_bin, "models"],
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError) as e:
        logger.debug("grok models failed: %s", e)
        return None

    text = (proc.stdout or "") + "\n" + (proc.stderr or "")
    if proc.returncode != 0 and not text.strip():
        return None

    default: str | None = None
    m = re.search(r"Default model:\s*(\S+)", text)
    if m:
        default = m.group(1).strip()

    available: list[str] = []
    for line in text.splitlines():
        # lines like "  * grok-4.5 (default)" or "  - grok-4.5"
        mm = re.match(r"^\s*[\*\-•]\s+(\S+)", line)
        if mm:
            mid = mm.group(1).strip()
            mid = mid.rstrip(",")
            if mid and mid not in available:
                available.append(mid)

    if default and default not in available:
        available.insert(0, default)
    if not default and available:
        default = available[0]
    if not default:
        return None
    return RuntimeModels(default_model=default, available=available, source="cli")


def resolve_runtime_models(
    *,
    configured_default: str | None = None,
    configured_models: str | None = None,
    grok_bin: str = "grok",
    prefer_cli: bool = False,
) -> RuntimeModels:
    """
    Resolve which model ids this proxy should advertise and use by default.

    Priority for available list:
      1. GROK_PROXY_MODELS if non-empty (explicit)
      2. grok models CLI (if prefer_cli) else models_cache.json then CLI
      3. fallback grok-4.5
    """
    configured_default = (configured_default or "").strip()
    configured_list = [
        m.strip() for m in (configured_models or "").split(",") if m.strip()
    ]
    # Treat legacy default "grok-build" as unset so we auto-detect real CLI models
    if configured_default in MODEL_ALIASES:
        configured_default = ""
    if configured_list == ["grok-build"] or all(m in MODEL_ALIASES for m in configured_list):
        configured_list = []

    discovered: RuntimeModels | None = None
    if prefer_cli:
        discovered = load_models_from_cli(grok_bin) or load_models_from_cache()
    else:
        discovered = load_models_from_cache() or load_models_from_cli(grok_bin)

    if configured_list:
        default = configured_default or (
            configured_list[0]
            if configured_list
            else (discovered.default_model if discovered else FALLBACK_MODEL)
        )
        # If configured default is alias / empty, use first configured or discovered
        if not configured_default and discovered:
            default = discovered.default_model if discovered.default_model in configured_list else configured_list[0]
        elif configured_default:
            default = configured_default
        return RuntimeModels(
            default_model=default,
            available=configured_list,
            source="config",
        )

    if discovered:
        default = configured_default or discovered.default_model
        if default not in discovered.available:
            # User forced a specific id; keep it but advertise discovered list + this id
            available = list(discovered.available)
            if default not in available:
                available.insert(0, default)
            return RuntimeModels(default_model=default, available=available, source=discovered.source)
        return RuntimeModels(
            default_model=default,
            available=discovered.available,
            source=discovered.source,
        )

    default = configured_default or FALLBACK_MODEL
    return RuntimeModels(default_model=default, available=[default], source="fallback")


def resolve_request_model(
    requested: str | None,
    runtime: RuntimeModels,
) -> str:
    """
    Map an incoming OpenAI `model` field to a Grok CLI model id.
    Unknown aliases like grok-build → runtime.default_model.
    """
    name = (requested or "").strip()
    if not name or name in MODEL_ALIASES:
        return runtime.default_model
    if name in runtime.available:
        return name
    # Soft alias: any grok-build* → default
    if name.startswith("grok-build"):
        logger.info("Remapping model %r → %r (CLI alias)", name, runtime.default_model)
        return runtime.default_model
    # Pass through (CLI will error if truly invalid)
    return name
