import pytest


@pytest.fixture(autouse=True)
def isolated_logs(tmp_path, monkeypatch):
    from sts2_bridge import trace

    log_root = tmp_path / "logs"
    monkeypatch.setattr(trace, "LOG_ROOT", log_root)
    return log_root
