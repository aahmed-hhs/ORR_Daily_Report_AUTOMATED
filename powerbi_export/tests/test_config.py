from pathlib import Path

from powerbi_export import config


def test_loads_default_config():
    s = config.load(Path(__file__).resolve().parents[1] / "config.yaml")
    assert s.cdp_url.startswith("http://")
    assert s.exports and s.exports[0].name == "daily_metrics"
    assert s.exports[0].format == "xlsx"
