"""Versioned remote configuration with deterministic cohorts and an offline-safe SDK."""

import hashlib
import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable
import httpx
from fastapi import FastAPI, HTTPException


def canonical(value: dict) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


@dataclass
class Store:
    versions: dict[str, dict] = field(default_factory=dict)
    active: str = ""
    killed: bool = False

    def publish(self, payload: dict) -> str:
        if type(payload.get("percent")) is not int or not 0 <= payload["percent"] <= 100:
            raise ValueError("percent must be an integer between 0 and 100")
        snapshot = json.loads(canonical(payload))
        version = hashlib.sha256(canonical(snapshot).encode()).hexdigest()
        self.versions[version] = snapshot
        self.active = version
        return version

    def rollback(self, version: str) -> None:
        if version not in self.versions:
            raise ValueError("unknown version")
        self.active = version

    def config(self, client_id: str) -> dict:
        payload = self.versions[self.active]
        bucket = int(hashlib.sha256(("cohort-v1:" + client_id).encode()).hexdigest()[:8], 16) % 100
        enabled = not self.killed and bucket < payload["percent"]
        return {
            "version": self.active,
            "enabled": enabled,
            "value": payload["value"] if enabled else None,
            "max_age_seconds": 5,
        }


def create_app(store: Store) -> FastAPI:
    app = FastAPI()

    @app.get("/config")
    def config(client_id: str) -> dict:
        return store.config(client_id)

    @app.post("/publish")
    def publish(payload: dict) -> dict:
        try:
            return {"version": store.publish(payload)}
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc

    @app.post("/rollback/{version}")
    def rollback(version: str) -> dict:
        try:
            store.rollback(version)
            return {"version": version}
        except ValueError as exc:
            raise HTTPException(404, str(exc)) from exc

    @app.post("/kill/{enabled}")
    def kill(enabled: bool) -> dict:
        store.killed = enabled
        return {"killed": enabled}

    return app


class SDK:
    def __init__(
        self, client: httpx.Client, client_id: str, clock: Callable[[], float] = time.monotonic
    ) -> None:
        self.client = client
        self.client_id = client_id
        self.clock = clock
        self.cached = None
        self.expires = 0.0

    def get(self) -> dict:
        try:
            response = self.client.get("/config", params={"client_id": self.client_id})
            response.raise_for_status()
            value = response.json()
            if not isinstance(value.get("enabled"), bool) or not isinstance(
                value.get("version"), str
            ):
                raise ValueError("invalid config")
            ttl = value.get("max_age_seconds", 0)
            if not isinstance(ttl, (int, float)) or not 0 <= ttl <= 5:
                raise ValueError("invalid TTL")
            self.cached = value
            self.expires = self.clock() + ttl
            return {**value, "source": "network"}
        except (httpx.HTTPError, ValueError):
            if self.cached is not None and self.clock() < self.expires:
                return {**self.cached, "source": "cache"}
            return {"enabled": False, "value": None, "version": None, "source": "fail-closed"}


def benchmark() -> dict:
    store = Store()
    old = store.publish({"percent": 50, "value": "old"})
    cohort = [store.config(f"synthetic-{i}")["enabled"] for i in range(1000)]
    assert cohort == [store.config(f"synthetic-{i}")["enabled"] for i in range(1000)]
    new = store.publish({"percent": 100, "value": "new"})
    store.rollback(old)
    assert store.config("synthetic-1")["version"] == old
    clock = [0.0]
    offline = [False]

    def serve(request: httpx.Request) -> httpx.Response:
        if offline[0]:
            raise httpx.ConnectError("injected network outage")
        return httpx.Response(200, json=store.config(request.url.params["client_id"]))

    with httpx.Client(transport=httpx.MockTransport(serve), base_url="http://config") as client:
        sdk = SDK(client, "synthetic-1", lambda: clock[0])
        first = sdk.get()
        offline[0] = True
        cached = sdk.get()
        clock[0] = 6
        closed = sdk.get()
        assert (
            cached["source"] == "cache"
            and closed["source"] == "fail-closed"
            and not closed["enabled"]
        )
        offline[0] = False
        store.killed = True
        killed = sdk.get()
        assert not killed["enabled"]
    Path("evidence/scenarios.json").write_text(
        json.dumps(
            {
                "initial": first,
                "offline_cached": cached,
                "expired": closed,
                "kill_switch": killed,
                "old_version": old,
                "new_version": new,
            },
            indent=2,
        )
    )
    return {
        "clients_evaluated": len(cohort),
        "enabled_at_50_percent": sum(cohort),
        "rollback_verified": True,
        "offline_scenarios_passed": 3,
        "kill_switch_verified": True,
    }


if __name__ == "__main__":
    print(json.dumps(benchmark(), indent=2))
