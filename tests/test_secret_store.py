import os

import pytest

from code_agent.security.secrets import WindowsSecretStore


@pytest.mark.skipif(os.name != "nt", reason="DPAPI 只在 Windows 上可用")
def test_dpapi_store_round_trip_and_delete(tmp_path):
    path = tmp_path / "secret.dpapi"
    store = WindowsSecretStore(path)
    store.save("dummy-test-key-not-real")
    assert path.exists()
    assert b"dummy-test-key-not-real" not in path.read_bytes()
    assert store.load() == "dummy-test-key-not-real"
    store.delete()
    assert store.load() is None
