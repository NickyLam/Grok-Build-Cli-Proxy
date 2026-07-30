from __future__ import annotations

import json
from pathlib import Path

from grok_proxy.model_resolve import (
    RuntimeModels,
    load_models_from_cache,
    resolve_request_model,
    resolve_runtime_models,
)


def test_load_models_from_cache(tmp_path: Path):
    cache = tmp_path / "models_cache.json"
    cache.write_text(
        json.dumps(
            {
                "models": {
                    "grok-4.5": {"info": {"id": "grok-4.5", "hidden": False}},
                    "hidden-x": {"info": {"id": "hidden-x", "hidden": True}},
                }
            }
        ),
        encoding="utf-8",
    )
    rt = load_models_from_cache(cache)
    assert rt is not None
    assert rt.default_model == "grok-4.5"
    assert "grok-4.5" in rt.available
    assert "hidden-x" not in rt.available


def test_resolve_request_aliases():
    rt = RuntimeModels(default_model="grok-4.5", available=["grok-4.5"], source="test")
    assert resolve_request_model("grok-build", rt) == "grok-4.5"
    assert resolve_request_model("auto", rt) == "grok-4.5"
    assert resolve_request_model(None, rt) == "grok-4.5"
    assert resolve_request_model("grok-4.5", rt) == "grok-4.5"


def test_resolve_runtime_treats_grok_build_as_auto(monkeypatch, tmp_path: Path):
    cache = tmp_path / "models_cache.json"
    cache.write_text(
        json.dumps({"models": {"grok-4.5": {"info": {"id": "grok-4.5"}}}}),
        encoding="utf-8",
    )
    monkeypatch.setenv("GROK_HOME", str(tmp_path))
    # Put cache at GROK_HOME/models_cache.json — load uses _grok_home()/models_cache.json
    rt = resolve_runtime_models(
        configured_default="grok-build",
        configured_models="grok-build",
        grok_bin="grok-that-does-not-exist-xyz",
    )
    assert rt.default_model == "grok-4.5"
    assert "grok-4.5" in rt.available
