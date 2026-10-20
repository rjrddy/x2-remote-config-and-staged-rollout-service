import httpx
import pytest
from fastapi.testclient import TestClient
from main import SDK, Store, create_app


def test_api_rollback_and_kill_switch():
    store = Store()
    version = store.publish({"percent": 100, "value": "old"})
    with TestClient(create_app(store)) as client:
        new = client.post("/publish", json={"percent": 100, "value": "new"}).json()["version"]
        assert new != version
        assert client.post("/rollback/" + version).status_code == 200
        assert client.get("/config?client_id=x").json()["value"] == "old"
        client.post("/kill/true")
        assert not client.get("/config?client_id=x").json()["enabled"]


def test_expired_or_malformed_config_fails_closed():
    with httpx.Client(
        transport=httpx.MockTransport(lambda _: httpx.Response(200, json={"enabled": "yes"})),
        base_url="http://x",
    ) as client:
        assert SDK(client, "x").get()["source"] == "fail-closed"
    with pytest.raises(ValueError):
        Store().publish({"percent": 101, "value": 1})


def test_cohort_stable_across_value_change():
    store = Store()
    store.publish({"percent": 50, "value": "a"})
    before = [store.config(str(i))["enabled"] for i in range(100)]
    store.publish({"percent": 50, "value": "b"})
    assert before == [store.config(str(i))["enabled"] for i in range(100)]
