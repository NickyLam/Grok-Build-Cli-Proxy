from __future__ import annotations

from grok_proxy.metrics import MetricsRegistry


def test_prometheus_render():
    m = MetricsRegistry()
    m.inc("responses_total", status="completed")
    m.set_gauge("responses_active", 2)
    m.observe_duration("responses_duration", 1.5, backend="fake")
    text = m.render_prometheus()
    assert "grok_proxy_uptime_seconds" in text
    assert "responses_total" in text
    assert "responses_active" in text
    assert 'status="completed"' in text
