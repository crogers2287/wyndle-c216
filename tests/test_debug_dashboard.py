from dataclasses import dataclass

from fastapi.testclient import TestClient

from wyndle.debug_dashboard import create_app


@dataclass
class FakeServices:
    calls: list[tuple[str, str]]

    def snapshot(self):
        return {"state": "idle_watching", "session": {"open": False}}

    async def latest_frame(self):
        return b"\xff\xd8fake-jpeg\xff\xd9"

    async def analyze(self, prompt):
        self.calls.append(("analyze", prompt))
        return {"answer": "clear"}

    async def speak(self, text):
        self.calls.append(("speak", text))
        return "queued"

    async def ptz(self, action):
        self.calls.append(("ptz", action))
        return {"accepted": True}


def test_dashboard_health_status_and_frame():
    client = TestClient(create_app(FakeServices([])))

    assert "Wyndle local debug" in client.get("/").text
    assert client.get("/health").json()["ok"] is True
    assert client.get("/api/status").json()["runtime"]["state"] == "idle_watching"
    frame = client.get("/api/frame/latest")
    assert frame.status_code == 200
    assert frame.headers["content-type"] == "image/jpeg"
    assert frame.headers["cache-control"] == "no-store"


def test_controls_only_invoke_injected_hooks():
    services = FakeServices([])
    client = TestClient(create_app(services))

    assert client.post("/api/controls/analyze", json={"prompt": "  scene?  "}).json()["ok"]
    assert client.post("/api/controls/speak", json={"text": " hello "}).json()["result"] == "queued"
    assert client.post("/api/controls/ptz", json={"action": "left"}).status_code == 200
    assert services.calls == [("analyze", "scene?"), ("speak", "hello"), ("ptz", "left")]


def test_default_services_are_inert():
    client = TestClient(create_app())

    assert client.get("/api/status").json()["runtime"]["hooks_enabled"] is False
    assert client.get("/api/frame/latest").status_code == 404
    response = client.post("/api/controls/ptz", json={"action": "right"})
    assert response.status_code == 503
    assert "not configured" in response.json()["detail"]


def test_ptz_allowlist_is_validated_before_hook():
    services = FakeServices([])
    client = TestClient(create_app(services))

    assert client.post("/api/controls/ptz", json={"action": "spin"}).status_code == 422
    assert services.calls == []
