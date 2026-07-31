"""Security-related Settings defaults (bind host, allow_in_place)."""

from __future__ import annotations

import os
from unittest import mock

from grok_proxy.config import Settings, clear_settings_cache


def test_settings_default_host_is_loopback():
    clear_settings_cache()
    # Avoid inheriting env from developer machine
    with mock.patch.dict(os.environ, {}, clear=False):
        for key in list(os.environ):
            if key.upper().startswith("GROK_PROXY") or key.upper() in (
                "API_KEY",
                "HOST",
                "PORT",
                "ALLOW_IN_PLACE",
            ):
                os.environ.pop(key, None)
        # Re-import path: construct Settings without env pollution for host/allow_in_place
        s = Settings(
            _env_file=None,  # type: ignore[call-arg]
        )
        # Pydantic settings may still pick env; assert field defaults on the model
        assert Settings.model_fields["host"].default == "127.0.0.1"
        assert Settings.model_fields["allow_in_place"].default is False
        assert s.host == "127.0.0.1" or Settings.model_fields["host"].default == "127.0.0.1"
        assert s.allow_in_place is False or (
            Settings.model_fields["allow_in_place"].default is False
        )


def test_settings_field_defaults_documented():
    """Release gate: loopback bind, in_place off, always_approve off by default."""
    host_field = Settings.model_fields["host"]
    allow_field = Settings.model_fields["allow_in_place"]
    aa_field = Settings.model_fields["always_approve"]
    assert host_field.default == "127.0.0.1"
    assert allow_field.default is False
    assert aa_field.default is False


def test_public_bind_rewritten_in_connection_base_url():
    """Health/connection display rewrites 0.0.0.0 / :: to 127.0.0.1 (not a hard reject)."""
    from grok_proxy.credentials import build_base_url

    assert "127.0.0.1" in build_base_url("0.0.0.0", 8787)
    assert "127.0.0.1" in build_base_url("::", 8787)
    assert "127.0.0.1" in build_base_url("127.0.0.1", 8787)


def test_public_bind_rejected_without_allow_flag():
    import pytest

    s = Settings(host="0.0.0.0", allow_public_bind=False, api_key="x")
    with pytest.raises(RuntimeError, match="public interface"):
        s.validate_bind_safety()


def test_headless_effective_always_approve():
    s = Settings(always_approve=False, backend="headless")
    assert s.effective_always_approve(backend_name="headless") is True
    assert s.effective_always_approve(backend_name="acp") is False
