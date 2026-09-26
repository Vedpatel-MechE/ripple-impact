"""HTTP-level checks for the local RIPPLE API (no third-party packages)."""

from __future__ import annotations

import http.client
import json
from pathlib import Path
import sqlite3
import tempfile
import threading
import unittest

from server import MAX_BODY, RippleServer


def sample_state() -> dict:
    return {
        "template": "devices",
        "role": "asset",
        "priority": "balance",
        "routeId": None,
        "missionName": "Second life for retired laptops",
        "assetName": "retired laptops",
        "quantity": 40,
        "quality": 75,
        "pickupDays": 30,
        "fundingLabel": "Activation fund",
        "budget": 5000,
        "skillLabel": "Device repair technician",
        "skilledHours": 120,
        "hourlyRate": 25,
        "anchorName": "Neighborhood school",
        "needCount": 45,
        "needText": "Students need computers at home.",
        "location": "Atlanta, GA",
        "parts": {"asset": True, "skills": False, "funding": False, "anchor": False},
        "proof": {"delivered": False, "followup": False},
        "edited": False,
        "fullExample": False,
    }


class RippleAPITests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp.name) / "test.sqlite3"
        self.server = RippleServer(port=0, db_path=self.db_path)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=3)
        self.temp.cleanup()

    def request(self, method: str, path: str, payload=None, headers=None, raw: bytes | None = None):
        connection = http.client.HTTPConnection("127.0.0.1", self.server.server_port, timeout=5)
        request_headers = dict(headers or {})
        if raw is not None:
            body = raw
            request_headers.setdefault("Content-Type", "application/json")
        elif payload is not None:
            body = json.dumps(payload, separators=(",", ":")).encode("utf-8")
            request_headers.setdefault("Content-Type", "application/json")
        else:
            body = None
        connection.request(method, path, body=body, headers=request_headers)
        response = connection.getresponse()
        data = response.read()
        result_headers = dict(response.getheaders())
        connection.close()
        try:
            parsed = json.loads(data)
        except (UnicodeDecodeError, json.JSONDecodeError):
            parsed = data
        return response.status, parsed, result_headers

    def create(self, state: dict | None = None) -> dict:
        status, body, _ = self.request("POST", "/api/missions", {"state": state or sample_state()})
        self.assertEqual(status, 201, body)
        return body

    def test_health_and_static_allowlist(self) -> None:
        status, body, headers = self.request("GET", "/api/health")
        self.assertEqual((status, body), (200, {"ok": True, "mode": "local"}))
        self.assertEqual(headers["Cache-Control"], "no-store")
        self.assertEqual(headers["Referrer-Policy"], "no-referrer")
        self.assertNotIn("Access-Control-Allow-Origin", headers)
        status, body, headers = self.request("GET", "/")
        self.assertEqual(status, 200)
        self.assertIn(b"RIPPLE", body)
        self.assertEqual(headers["Content-Type"], "text/html; charset=utf-8")
        for path in ("/server.py", "/HANDOFF.md", "/ripple.sqlite3", "/../server.py", "/%2e%2e/server.py", "/styles.css/../server.py"):
            with self.subTest(path=path):
                self.assertEqual(self.request("GET", path)[0], 404)

    def test_create_view_and_separate_token_authorities(self) -> None:
        created = self.create()
        self.assertEqual(created["version"], 1)
        self.assertGreaterEqual(len(created["id"]), 20)
        self.assertNotEqual(created["viewToken"], created["editToken"])
        path = f"/api/missions/{created['id']}"
        status, body, _ = self.request("GET", f"{path}?viewToken={created['viewToken']}")
        self.assertEqual(status, 200)
        self.assertEqual(body["state"], sample_state())
        self.assertNotIn("viewToken", body)
        self.assertNotIn("editToken", body)
        self.assertEqual(self.request("GET", path)[0], 403)
        self.assertEqual(self.request("GET", f"{path}?viewToken={created['editToken']}")[0], 403)
        self.assertEqual(self.request("GET", f"{path}?viewToken=not-the-token")[0], 403)
        self.assertEqual(self.request("GET", f"{path}/revisions?viewToken={created['editToken']}")[0], 403)
        self.assertEqual(self.request("GET", "/api/missions")[0], 404)
        share_url = f"/?mission={created['id']}&view={created['viewToken']}"
        status, page, share_headers = self.request("GET", share_url)
        self.assertEqual(status, 200)
        self.assertIn(b"RIPPLE", page)
        self.assertEqual(share_headers["Referrer-Policy"], "no-referrer")
        self.assertEqual(share_headers["Cache-Control"], "no-store")
        self.assertNotIn(created["viewToken"].encode("ascii"), page)
        self.assertEqual(self.request("GET", "/?mission=unknown&view=wrong")[0], 404)
        database_bytes = self.db_path.read_bytes()
        for raw_secret in (created["id"], created["viewToken"], created["editToken"]):
            self.assertNotIn(raw_secret.encode("ascii"), database_bytes)

    def test_update_conflict_and_immutable_revisions(self) -> None:
        created = self.create()
        state = sample_state()
        state["skillLabel"] = "Local paid technician"
        state["parts"]["skills"] = True
        path = f"/api/missions/{created['id']}"
        headers = {"X-Edit-Token": created["editToken"]}
        status, updated, _ = self.request("PUT", path, {"state": state, "version": 1}, headers)
        self.assertEqual(status, 200)
        self.assertEqual(updated["version"], 2)
        self.assertEqual(self.request("PUT", path, {"state": state, "version": 1}, headers)[0], 409)
        self.assertEqual(self.request("PUT", path, {"state": state, "version": 2})[0], 403)
        self.assertEqual(self.request("PUT", path, {"state": state, "version": 2}, {"X-Edit-Token": created["viewToken"]})[0], 403)
        view_path = f"{path}?viewToken={created['viewToken']}"
        status, current, _ = self.request("GET", view_path)
        self.assertEqual(status, 200)
        self.assertEqual(current["version"], 2)
        self.assertEqual(current["state"]["skillLabel"], "Local paid technician")
        status, revisions, _ = self.request("GET", f"{path}/revisions?viewToken={created['viewToken']}")
        self.assertEqual(status, 200)
        self.assertEqual([item["version"] for item in revisions["revisions"]], [2, 1])
        with sqlite3.connect(self.db_path) as db:
            rows = db.execute("SELECT version, state_json FROM revisions ORDER BY version").fetchall()
        self.assertEqual(json.loads(rows[0][1])["skillLabel"], "Device repair technician")
        self.assertEqual(json.loads(rows[1][1])["skillLabel"], "Local paid technician")

    def test_validation_rejects_bad_or_unknown_state(self) -> None:
        invalid_states = []
        state = sample_state(); state["budget"] = True; invalid_states.append(state)
        state = sample_state(); state["quantity"] = 100_001; invalid_states.append(state)
        state = sample_state(); state["needCount"] = 1.5; invalid_states.append(state)
        state = sample_state(); state["template"] = ["devices"]; invalid_states.append(state)
        state = sample_state(); state["routeId"] = "not-a-route"; invalid_states.append(state)
        state = sample_state(); state["parts"]["asset"] = "true"; invalid_states.append(state)
        state = sample_state(); state["anchorName"] = " "; invalid_states.append(state)
        state = sample_state(); state["unexpected"] = "stored"; invalid_states.append(state)
        for state in invalid_states:
            with self.subTest(state=state):
                status, body, _ = self.request("POST", "/api/missions", {"state": state})
                self.assertEqual(status, 422, body)
        status, _, _ = self.request("POST", "/api/missions", {"state": sample_state(), "extra": 1})
        self.assertEqual(status, 422)

    def test_payload_and_json_limits(self) -> None:
        self.assertEqual(self.request("POST", "/api/missions", raw=b"x" * (MAX_BODY + 1))[0], 413)
        self.assertEqual(self.request("POST", "/api/missions", raw=b'{"state":{},"state":{}}')[0], 400)
        self.assertEqual(self.request("POST", "/api/missions", raw=b'{"state":NaN}')[0], 400)
        self.assertEqual(self.request("POST", "/api/missions", raw=b"not json")[0], 400)
        self.assertEqual(self.request("POST", "/api/missions", raw=b'{}', headers={"Content-Type": "text/plain"})[0], 415)

    def test_cross_origin_write_rejected(self) -> None:
        state = sample_state()
        status, _, _ = self.request("POST", "/api/missions", {"state": state}, {"Origin": "https://untrusted.example"})
        self.assertEqual(status, 403)

    def test_custom_mission_is_saved_without_invented_forecast(self) -> None:
        state = sample_state()
        state["template"] = "custom"
        state["routeId"] = None
        state["missionName"] = "Reuse empty storefronts"
        created = self.create(state)
        status, fetched, _ = self.request("GET", f"/api/missions/{created['id']}?viewToken={created['viewToken']}")
        self.assertEqual(status, 200)
        self.assertEqual(fetched["state"]["missionName"], "Reuse empty storefronts")
        self.assertNotIn("forecast", fetched)


if __name__ == "__main__":
    unittest.main()
