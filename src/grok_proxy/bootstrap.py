from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from pathlib import Path

from grok_proxy.config import Settings, clear_settings_cache, get_settings
from grok_proxy.credentials import (
    build_connection_info,
    default_state_dir,
    ensure_api_key,
    format_startup_banner,
    install_workbuddy_model,
    write_client_config_files,
)
from grok_proxy.model_resolve import RuntimeModels, resolve_runtime_models

logger = logging.getLogger("grok_proxy")


@dataclass
class BootstrapResult:
    settings: Settings
    banner: str
    workbuddy_path: Path | None
    runtime_models: RuntimeModels


def bootstrap_settings(
    settings: Settings | None = None,
    *,
    install_workbuddy: bool | None = None,
    state_dir: Path | None = None,
    print_banner: bool = True,
) -> BootstrapResult:
    """
    Ensure API key exists (auto-generate if needed), resolve real Grok model ids,
    write client config files, optionally install WorkBuddy model entry.
    """
    state_dir = state_dir or default_state_dir()
    cfg = settings if settings is not None else get_settings()

    key, source = ensure_api_key(cfg.api_key, state_dir=state_dir, persist=True)
    cfg.api_key = key

    runtime = resolve_runtime_models(
        configured_default=cfg.default_model,
        configured_models=cfg.models,
        grok_bin=cfg.grok_bin,
    )
    cfg.default_model = runtime.default_model
    cfg.models = ",".join(runtime.available)

    # Push into env so re-loaded Settings / uvicorn child import see it
    os.environ["GROK_PROXY_API_KEY"] = key
    os.environ["GROK_PROXY_DEFAULT_MODEL"] = cfg.default_model
    os.environ["GROK_PROXY_MODELS"] = cfg.models
    clear_settings_cache()

    model_id = cfg.default_model
    info = build_connection_info(
        api_key=key,
        host=cfg.host,
        port=cfg.port,
        model_id=model_id,
        source=source,
    )
    written = write_client_config_files(info, state_dir=state_dir)

    if install_workbuddy is None:
        install_workbuddy = os.environ.get("GROK_PROXY_INSTALL_WORKBUDDY", "").strip().lower() in (
            "1",
            "true",
            "yes",
            "on",
        )

    wb_path = None
    if install_workbuddy:
        # Remove stale entry that used invalid id "grok-build"
        wb_path = install_workbuddy_model(info, remove_ids=["grok-build", "grok-build-plan"])

    banner = format_startup_banner(
        info,
        written=written,
        workbuddy_installed=wb_path,
        show_full_key=cfg.banner_show_key,
    )
    # Append model discovery note
    extra = (
        f"\n  Grok CLI models ({runtime.source}): {', '.join(runtime.available) or '(none)'}\n"
        f"  Using model id: {runtime.default_model}\n"
    )
    banner = banner.replace(
        "  Note: this API Key only guards the local proxy.",
        extra + "  Note: this API Key only guards the local proxy.",
    )

    if print_banner:
        print(banner, flush=True)
        logger.info(
            "proxy ready base_url=%s model=%s models=%s key_source=%s model_source=%s",
            info.base_url,
            info.model_id,
            runtime.available,
            source,
            runtime.source,
        )

    return BootstrapResult(
        settings=cfg,
        banner=banner,
        workbuddy_path=wb_path,
        runtime_models=runtime,
    )
