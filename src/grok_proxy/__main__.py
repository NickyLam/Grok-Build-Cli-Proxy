from __future__ import annotations

import argparse
import logging
import sys

import uvicorn

from grok_proxy.bootstrap import bootstrap_settings
from grok_proxy.config import get_settings


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        prog="grok-proxy",
        description="OpenAI-compatible HTTP proxy for Grok Build CLI",
    )
    p.add_argument(
        "--host",
        default=None,
        help="Bind host (default: GROK_PROXY_HOST or 127.0.0.1)",
    )
    p.add_argument(
        "--port",
        type=int,
        default=None,
        help="Bind port (default: GROK_PROXY_PORT or 8787)",
    )
    p.add_argument(
        "--install-workbuddy",
        action="store_true",
        help="Upsert this proxy into ~/.workbuddy/models.json (Custom model)",
    )
    p.add_argument(
        "--no-install-workbuddy",
        action="store_true",
        help="Do not write WorkBuddy models.json even if env enables it",
    )
    p.add_argument(
        "--print-config-only",
        action="store_true",
        help="Generate API key + client config files and exit (do not start server)",
    )
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
    )
    args = _parse_args(argv)
    settings = get_settings()

    if args.host:
        settings.host = args.host
    if args.port is not None:
        settings.port = args.port

    install_wb: bool | None
    if args.no_install_workbuddy:
        install_wb = False
    elif args.install_workbuddy:
        install_wb = True
    else:
        install_wb = None  # follow env GROK_PROXY_INSTALL_WORKBUDDY

    result = bootstrap_settings(settings, install_workbuddy=install_wb, print_banner=True)

    if args.print_config_only:
        sys.exit(0)

    uvicorn.run(
        "grok_proxy.main:app",
        host=result.settings.host,
        port=result.settings.port,
        log_level="info",
        factory=False,
    )


if __name__ == "__main__":
    main()
