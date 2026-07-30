from __future__ import annotations

import json
from pathlib import Path

from grok_proxy.bootstrap import bootstrap_settings
from grok_proxy.config import Settings, clear_settings_cache
from grok_proxy.credentials import (
    API_KEY_PREFIX,
    ensure_api_key,
    generate_api_key,
    install_workbuddy_model,
    load_persisted_api_key,
    write_client_config_files,
    build_connection_info,
)


def test_generate_api_key_prefix():
    key = generate_api_key()
    assert key.startswith(API_KEY_PREFIX)
    assert len(key) > len(API_KEY_PREFIX) + 16


def test_ensure_generates_and_persists(tmp_path: Path):
    key1, src1 = ensure_api_key("", state_dir=tmp_path, persist=True)
    assert src1 == "generated"
    assert key1.startswith(API_KEY_PREFIX)
    assert (tmp_path / "api_key").read_text().strip() == key1

    key2, src2 = ensure_api_key("", state_dir=tmp_path, persist=True)
    assert src2 == "file"
    assert key2 == key1


def test_env_key_wins(tmp_path: Path):
    key, src = ensure_api_key("my-fixed-key", state_dir=tmp_path, persist=True)
    assert key == "my-fixed-key"
    assert src == "env"


def test_write_client_config_and_workbuddy_shape(tmp_path: Path):
    info = build_connection_info(
        api_key="sk-gp-test",
        host="127.0.0.1",
        port=8787,
        model_id="grok-build",
        source="generated",
    )
    written = write_client_config_files(info, state_dir=tmp_path)
    client = json.loads(written["client_config"].read_text())
    assert client["base_url"] == "http://127.0.0.1:8787/v1"
    assert client["api_key"] == "sk-gp-test"
    assert client["model_id"] == "grok-build"

    wb = json.loads(written["workbuddy_model"].read_text())
    assert wb["vendor"] == "Custom"
    assert wb["url"] == "http://127.0.0.1:8787/v1"
    assert wb["apiKey"] == "sk-gp-test"
    assert wb["id"] == "grok-build"


def test_install_workbuddy_upsert(tmp_path: Path):
    models = tmp_path / "models.json"
    models.write_text(
        json.dumps(
            [
                {
                    "id": "other",
                    "name": "other",
                    "vendor": "Custom",
                    "url": "http://x/v1",
                    "apiKey": "k",
                }
            ]
        ),
        encoding="utf-8",
    )
    info = build_connection_info(
        api_key="sk-gp-abc",
        host="127.0.0.1",
        port=8787,
        model_id="grok-build",
        source="generated",
    )
    install_workbuddy_model(info, models_path=models)
    data = json.loads(models.read_text())
    assert len(data) == 2
    entry = next(e for e in data if e["id"] == "grok-build")
    assert entry["url"] == "http://127.0.0.1:8787/v1"
    assert entry["apiKey"] == "sk-gp-abc"

    # update in place
    info2 = build_connection_info(
        api_key="sk-gp-new",
        host="127.0.0.1",
        port=8787,
        model_id="grok-build",
        source="generated",
    )
    install_workbuddy_model(info2, models_path=models)
    data2 = json.loads(models.read_text())
    assert len(data2) == 2
    entry2 = next(e for e in data2 if e["id"] == "grok-build")
    assert entry2["apiKey"] == "sk-gp-new"


def test_bootstrap_settings(tmp_path: Path, monkeypatch):
    clear_settings_cache()
    monkeypatch.delenv("GROK_PROXY_API_KEY", raising=False)
    # Provide a fake models cache so bootstrap does not depend on live grok CLI
    grok_home = tmp_path / "grokhome"
    grok_home.mkdir()
    (grok_home / "models_cache.json").write_text(
        json.dumps({"models": {"grok-4.5": {"info": {"id": "grok-4.5"}}}}),
        encoding="utf-8",
    )
    monkeypatch.setenv("GROK_HOME", str(grok_home))
    s = Settings(api_key="", host="127.0.0.1", port=8787, default_model="auto", models="")
    result = bootstrap_settings(
        s,
        install_workbuddy=False,
        state_dir=tmp_path,
        print_banner=False,
    )
    assert result.settings.api_key.startswith(API_KEY_PREFIX)
    assert load_persisted_api_key(tmp_path) == result.settings.api_key
    assert (tmp_path / "workbuddy-model.json").is_file()
    assert result.settings.default_model == "grok-4.5"
    wb = json.loads((tmp_path / "workbuddy-model.json").read_text())
    assert wb["id"] == "grok-4.5"
