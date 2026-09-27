"""HTTP-level checks for the local RIPPLE API (no third-party packages)."""

from __future__ import annotations

import http.client
import json
from pathlib import Path
import sqlite3
import tempfile
import threading
import unittest

from server import ADMIN_EMAIL, ADMIN_PASSWORD, MAX_BODY, RippleServer, initialize_database
from api.index import handler as VercelHandler


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

    def add_signal(self, role: str, **overrides) -> dict:
        signal = {
            "role": role, "source": "Test partner", "title": role.title() + " contribution",
            "category": "education", "location": "Atlanta, GA", "details": "Test-only signal",
            "quantity": 0, "unit": "", "hours": 0, "hourlyRate": 0, "amount": 0,
        }
        signal.update(overrides)
        status, body, _ = self.request("POST", "/api/signals", {"signal": signal})
        self.assertEqual(status, 201, body)
        return body

    def assemble(self, community: dict, starter: dict) -> dict:
        status, body, _ = self.request(
            "POST", "/api/assemblies",
            {"communitySignalId": community["signal"]["id"], "starterSignalId": starter["signal"]["id"]},
            {"X-Owner-Token": starter["ownerToken"]},
        )
        self.assertEqual(status, 201, body)
        return body

    def owner_headers(self, signal: dict) -> dict:
        return {"X-Owner-Token": signal["ownerToken"]}

    def register(self, email: str = "participant@example.org", name: str = "Test Participant") -> tuple[dict, dict]:
        status, body, response_headers = self.request("POST", "/api/auth/register", {
            "displayName": name, "email": email, "password": "StrongPass123",
        })
        self.assertEqual(status, 201, body)
        cookie = response_headers["Set-Cookie"].split(";", 1)[0]
        return {"Cookie": cookie, "X-CSRF-Token": body["csrfToken"]}, body

    def login_admin(self) -> tuple[dict, dict]:
        status, body, response_headers = self.request("POST", "/api/auth/login", {
            "email": ADMIN_EMAIL, "password": ADMIN_PASSWORD,
        })
        self.assertEqual(status, 200, body)
        cookie = response_headers["Set-Cookie"].split(";", 1)[0]
        return {"Cookie": cookie, "X-CSRF-Token": body["csrfToken"]}, body

    def company_intake(self) -> dict:
        return {
            "organizationName": "Example Technology Company",
            "contactName": "Jordan Lee",
            "email": "jordan@example.org",
            "location": "Atlanta, GA",
            "deviceType": "laptops",
            "quantity": 75,
            "condition": "mixed",
            "availabilityWindow": "Available within 30 days",
            "notes": "A pilot inquiry; ownership documents would still be required.",
        }

    def recipient_intake(self) -> dict:
        return {
            "organizationName": "Example Public School",
            "contactName": "Casey Morgan",
            "email": "casey@example.edu",
            "organizationType": "public-school",
            "location": "Atlanta, GA",
            "deviceType": "laptops",
            "quantity": 30,
            "studentCount": 250,
            "useCase": "Supervised take-home learning program",
            "deadline": "Before the next semester",
            "notes": "Need and authority remain unverified in this local pilot.",
        }

    def repairer_intake(self) -> dict:
        return {
            "organizationName": "Example Repair Cooperative",
            "contactName": "Alex Rivera",
            "email": "alex@example.com",
            "location": "Atlanta, GA",
            "specialties": ["laptops", "desktops"],
            "monthlyCapacity": 100,
            "turnaroundDays": 14,
            "services": ["data-wiping", "diagnostics", "hardware-repair", "configuration"],
            "notes": "Credentials and capacity would still require review.",
        }

    def test_health_and_static_allowlist(self) -> None:
        status, body, headers = self.request("GET", "/api/health")
        self.assertEqual((status, body), (200, {"ok": True, "mode": "local", "database": "ready", "matching": "ready"}))
        self.assertEqual(headers["Cache-Control"], "no-store")
        self.assertEqual(headers["Referrer-Policy"], "no-referrer")
        self.assertNotIn("Access-Control-Allow-Origin", headers)
        status, body, headers = self.request("GET", "/")
        self.assertEqual(status, 200)
        self.assertIn(b"RIPPLE", body)
        self.assertIn(b"<main", body)
        self.assertNotIn(ADMIN_PASSWORD.encode("utf-8"), body)
        self.assertEqual(headers["Content-Type"], "text/html; charset=utf-8")
        self.assertEqual(self.request("GET", "/login.html")[0], 200)
        self.assertEqual(self.request("GET", "/network.js")[0], 200)
        self.assertEqual(self.request("GET", "/network.css")[0], 200)
        self.assertEqual(self.request("GET", "/site.js")[0], 200)
        self.assertEqual(self.request("GET", "/site.css")[0], 200)
        self.assertEqual(self.request("GET", "/auth.js")[0], 200)
        self.assertEqual(self.request("GET", "/admin.js")[0], 200)
        self.assertEqual(self.request("GET", "/auth-guard.js")[0], 200)
        self.assertEqual(self.request("GET", "/smart-cart.js")[0], 200)
        self.assertEqual(self.request("GET", "/circle.js")[0], 200)
        self.assertEqual(self.request("GET", "/smart-cart")[0], 302)
        for path in (
            "/company", "/recipient", "/repair", "/fund", "/missions", "/transparency",
            "/network.html", "/admin.html", "/smart-cart.html",
        ):
            with self.subTest(path=path):
                status, _, protected_headers = self.request("GET", path)
                self.assertEqual(status, 302)
                self.assertTrue(protected_headers["Location"].startswith("/?next="))
        self.assertEqual(self.request("GET", "/mission?mission=south-atlanta-laptop-lab")[0], 302)
        self.assertEqual(self.request("GET", "/mission?unknown=value")[0], 302)
        self.assertEqual(self.request("GET", "/planner")[0], 302)
        for path in ("/server.py", "/HANDOFF.md", "/ripple.sqlite3", "/../server.py", "/%2e%2e/server.py", "/styles.css/../server.py"):
            with self.subTest(path=path):
                self.assertEqual(self.request("GET", path)[0], 404)

    def test_vercel_rewrite_restores_nested_api_paths(self) -> None:
        rewritten = object.__new__(VercelHandler)
        rewritten.path = "/api?ripplePath=auth%2Flogin"
        self.assertEqual(rewritten._path(), ("/api/auth/login", {}))

        rewritten.path = "/api?mission=south-atlanta-laptop-lab&ripplePath=impact-missions"
        self.assertEqual(rewritten._path(), (
            "/api/impact-missions",
            {"mission": ["south-atlanta-laptop-lab"]},
        ))

        rewritten.path = "/api?__ripple_path=auth%2Fsession"
        self.assertEqual(rewritten._path(), ("/api/auth/session", {}))

    def test_authentication_and_admin_inquiry_workflow(self) -> None:
        status, anonymous, _ = self.request("GET", "/api/auth/session")
        self.assertEqual((status, anonymous), (200, {"authenticated": False}))
        self.assertEqual(self.request("GET", "/home")[0], 302)
        self.assertEqual(self.request("POST", "/api/intakes", {"kind": "company", "payload": self.company_intake()})[0], 401)

        participant_headers, registered = self.register("owner@example.org", "Asset Owner")
        self.assertEqual(registered["user"]["role"], "participant")
        status, session, _ = self.request("GET", "/api/auth/session", headers=participant_headers)
        self.assertEqual(status, 200)
        self.assertTrue(session["authenticated"])
        self.assertEqual(session["user"]["email"], "owner@example.org")
        self.assertEqual(self.request("GET", "/home", headers=participant_headers)[0], 200)
        self.assertEqual(self.request("GET", "/network.html", headers=participant_headers)[0], 200)
        self.assertEqual(
            self.request("GET", "/smart-cart.html?mission=south-atlanta-laptop-lab", headers=participant_headers)[0],
            200,
        )
        self.assertEqual(self.request("GET", "/api/admin/dashboard", headers=participant_headers)[0], 403)
        no_csrf = {"Cookie": participant_headers["Cookie"]}
        self.assertEqual(self.request("POST", "/api/intakes", {"kind": "company", "payload": self.company_intake()}, no_csrf)[0], 403)

        status, submitted, _ = self.request(
            "POST", "/api/intakes", {"kind": "company", "payload": self.company_intake()}, participant_headers,
        )
        self.assertEqual(status, 201, submitted)
        intake_id = submitted["intake"]["id"]
        mine = self.request("GET", "/api/my/intakes", headers=participant_headers)[1]
        self.assertEqual(mine["inquiries"][0]["id"], intake_id)

        admin_headers, admin = self.login_admin()
        self.assertEqual(admin["user"]["role"], "admin")
        status, dashboard, _ = self.request("GET", "/api/admin/dashboard", headers=admin_headers)
        self.assertEqual(status, 200, dashboard)
        self.assertEqual(dashboard["counts"]["total"], 1)
        self.assertEqual(dashboard["counts"]["byStatus"]["submitted"], 1)
        self.assertEqual(dashboard["inquiries"][0]["submittedBy"]["email"], "owner@example.org")

        status, updated, _ = self.request("PATCH", f"/api/admin/intakes/{intake_id}", {
            "status": "reviewing", "reviewNotes": "Ownership documents requested.",
        }, admin_headers)
        self.assertEqual(status, 200, updated)
        self.assertEqual(updated["inquiry"]["status"], "reviewing")
        dashboard = self.request("GET", "/api/admin/dashboard", headers=admin_headers)[1]
        self.assertEqual(dashboard["counts"]["byStatus"]["reviewing"], 1)
        self.assertEqual(dashboard["inquiries"][0]["reviewNotes"], "Ownership documents requested.")
        self.assertEqual(dashboard["inquiries"][0]["events"][-1]["event"], "status:reviewing")

        status, logged_out, logout_headers = self.request("POST", "/api/auth/logout", {}, admin_headers)
        self.assertEqual((status, logged_out), (200, {"authenticated": False}))
        self.assertIn("Max-Age=0", logout_headers["Set-Cookie"])
        self.assertEqual(self.request("GET", "/api/admin/dashboard", headers=admin_headers)[0], 401)

    def test_smart_cart_circle_and_sandbox_checkout(self) -> None:
        recommendation_request = {
            "missionId": "south-atlanta-laptop-lab",
            "budget": 500,
            "groupSize": 5,
            "priority": "impact",
            "prompt": "Five friends want to activate reliable laptops for local students.",
        }
        self.assertEqual(self.request("POST", "/api/smart-cart/recommendations", recommendation_request)[0], 401)
        auth, _ = self.register("circle-owner@example.org", "Ved Circle Owner")
        status, recommendations, _ = self.request(
            "POST", "/api/smart-cart/recommendations", recommendation_request, auth,
        )
        self.assertEqual(status, 200, recommendations)
        self.assertEqual([item["type"] for item in recommendations["options"]], ["starter", "balanced", "resilient"])
        self.assertTrue(all(item["goal"] <= 500 for item in recommendations["options"]))
        self.assertEqual(recommendations["planningMode"], "local-ai-planning-simulation")

        create_request = {
            **recommendation_request,
            "packageType": "balanced",
            "groupName": "Robotics Friends",
            "creatorStatement": "Technology opened doors for us, and we want to pass that access forward.",
        }
        status, created, _ = self.request("POST", "/api/smart-carts", create_request, auth)
        self.assertEqual(status, 201, created)
        circle_id = created["circle"]["id"]
        self.assertEqual(created["sharePath"], f"/circle?id={circle_id}")
        self.assertEqual(created["shareUrl"], f"/circle?id={circle_id}")
        self.assertEqual(created["circle"]["contributorCount"], 0)
        self.assertFalse(created["circle"]["paymentProcessed"])
        self.assertEqual(self.request("GET", f"/circle?id={circle_id}")[0], 200)
        self.assertEqual(self.request("GET", f"/circle.html?id={circle_id}")[0], 200)
        self.assertEqual(self.request("GET", "/circle?id=invalid")[0], 404)

        status, public, _ = self.request("GET", f"/api/smart-carts/{circle_id}")
        self.assertEqual(status, 200, public)
        self.assertEqual(public["shareUrl"], f"/circle?id={circle_id}")
        self.assertEqual(public["circle"]["groupName"], "Robotics Friends")
        contribution = {
            "displayName": "Maya",
            "amount": 50,
            "anonymous": False,
            "message": "I want more students to learn engineering.",
            "sandboxConfirmation": True,
        }
        status, checkout, _ = self.request("POST", f"/api/smart-carts/{circle_id}/checkout", contribution)
        self.assertEqual(status, 201, checkout)
        self.assertEqual(checkout["contribution"]["status"], "sandbox-authorized")
        self.assertFalse(checkout["contribution"]["paymentProcessed"])
        self.assertTrue(checkout["contribution"]["gatewayReference"].startswith("VISA-SBX-"))
        self.assertEqual(checkout["circle"]["raised"], 50)
        self.assertEqual(checkout["circle"]["contributorCount"], 1)
        self.assertIn("Maya", checkout["circle"]["contributors"][0]["displayName"])
        self.assertIn("1 friend", checkout["circle"]["socialHeadline"])

        too_much = {**contribution, "amount": checkout["circle"]["remaining"] + 1}
        self.assertEqual(self.request("POST", f"/api/smart-carts/{circle_id}/checkout", too_much)[0], 409)
        invalid_confirmation = {**contribution, "sandboxConfirmation": False}
        self.assertEqual(self.request("POST", f"/api/smart-carts/{circle_id}/checkout", invalid_confirmation)[0], 422)
        mine = self.request("GET", "/api/my/smart-carts", headers=auth)[1]
        self.assertEqual(mine["circles"][0]["id"], circle_id)

        database_bytes = self.db_path.read_bytes()
        self.assertNotIn(b"4111111111111111", database_bytes)
        with sqlite3.connect(self.db_path) as db:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM circle_contributions").fetchone()[0], 1)
            self.assertEqual(db.execute("SELECT event FROM smart_cart_events ORDER BY event_id").fetchall(), [("circle_created",), ("sandbox_contribution_authorized",)])
            with self.assertRaises(sqlite3.IntegrityError):
                db.execute("DELETE FROM smart_cart_events")

    def test_sample_impact_missions_are_honestly_labeled(self) -> None:
        status, platform, headers = self.request("GET", "/api/platform")
        self.assertEqual(status, 200, platform)
        self.assertTrue(platform["sample"])
        self.assertEqual(len(platform["missionSummaries"]), 3)
        self.assertEqual(platform["counters"]["intakesTotal"], 0)
        self.assertEqual(platform["counters"]["simulatedPledgeCount"], 0)
        self.assertIn("No donation was collected", platform["notice"])
        self.assertIn("no payment", platform["pledgeStatus"])
        self.assertEqual(headers["Cache-Control"], "no-store")
        self.assertEqual(headers["Cross-Origin-Resource-Policy"], "same-origin")

        status, listing, _ = self.request("GET", "/api/impact-missions")
        self.assertEqual(status, 200, listing)
        self.assertTrue(listing["sample"])
        self.assertEqual(len(listing["missions"]), 3)
        for mission in listing["missions"]:
            self.assertTrue(mission["sample"])
            self.assertEqual(mission["status"], "sample-planning")
            self.assertIn("not delivered impact", mission["plannedOutcome"]["label"].lower())
            self.assertEqual(mission["funding"]["activityStatus"], "simulation-only")
        mission_id = listing["missions"][0]["id"]
        status, detail, _ = self.request("GET", f"/api/impact-missions/{mission_id}")
        self.assertEqual(status, 200, detail)
        self.assertTrue(detail["sample"])
        self.assertEqual(detail["mission"]["id"], mission_id)
        self.assertEqual(detail["mission"]["funding"]["simulatedPledged"], 0)
        self.assertIn("no money", detail["notice"].lower())
        self.assertEqual(self.request("GET", "/api/impact-missions/not-a-real-mission")[0], 404)

    def test_role_intakes_validate_persist_and_count(self) -> None:
        auth, _ = self.register()
        examples = {
            "company": self.company_intake(),
            "recipient": self.recipient_intake(),
            "repairer": self.repairer_intake(),
        }
        ids = []
        for kind, payload in examples.items():
            status, body, _ = self.request("POST", "/api/intakes", {"kind": kind, "payload": payload}, auth)
            self.assertEqual(status, 201, body)
            self.assertEqual(body["intake"]["kind"], kind)
            self.assertEqual(body["intake"]["verification"], "unverified")
            self.assertIn("not a verified partnership", body["notice"])
            ids.append(body["intake"]["id"])

        invalid = [
            {"kind": "donor", "payload": self.company_intake()},
            {"kind": "company", "payload": {**self.company_intake(), "quantity": True}},
            {"kind": "company", "payload": {**self.company_intake(), "email": "not-an-email"}},
            {"kind": "company", "payload": {**self.company_intake(), "extra": "not stored"}},
            {"kind": "repairer", "payload": {**self.repairer_intake(), "services": ["diagnostics", "diagnostics"]}},
        ]
        for payload in invalid:
            with self.subTest(payload=payload):
                self.assertEqual(self.request("POST", "/api/intakes", payload, auth)[0], 422)
        self.assertEqual(self.request("POST", "/api/intakes", {"kind": "company", "payload": self.company_intake(), "extra": 1}, auth)[0], 422)

        status, platform, _ = self.request("GET", "/api/platform")
        self.assertEqual(status, 200)
        self.assertEqual(platform["counters"]["intakesTotal"], 3)
        self.assertEqual(platform["counters"]["intakesByKind"], {"company": 1, "recipient": 1, "repairer": 1})
        with sqlite3.connect(self.db_path) as db:
            rows = db.execute("SELECT id, kind, verification_status FROM role_intakes ORDER BY created_at").fetchall()
            events = db.execute("SELECT intake_id, event FROM intake_events ORDER BY event_id").fetchall()
            self.assertEqual([row[0] for row in rows], ids)
            self.assertTrue(all(row[2] == "unverified" for row in rows))
            self.assertEqual(len(events), 3)
            with self.assertRaises(sqlite3.IntegrityError):
                db.execute("UPDATE intake_events SET event = 'rewritten'")

    def test_simulated_pledges_validate_persist_and_update_totals(self) -> None:
        auth, _ = self.register()
        mission_id = "south-atlanta-laptop-lab"
        status, first, _ = self.request("POST", "/api/pledges", {
            "missionId": mission_id, "amount": 12.34, "displayName": "Taylor", "anonymous": False,
        }, auth)
        self.assertEqual(status, 201, first)
        self.assertEqual(first["pledge"]["status"], "simulated")
        self.assertTrue(first["pledge"]["sample"])
        self.assertFalse(first["pledge"]["paymentProcessed"])
        self.assertIn("No payment was requested", first["notice"])
        status, second, _ = self.request("POST", "/api/pledges", {
            "missionId": mission_id, "amount": 20, "displayName": "", "anonymous": True,
        }, auth)
        self.assertEqual(status, 201, second)
        self.assertEqual(second["pledge"]["displayName"], "Anonymous supporter")

        invalid = [
            {"missionId": "unknown", "amount": 10, "displayName": "A", "anonymous": False},
            {"missionId": mission_id, "amount": True, "displayName": "A", "anonymous": False},
            {"missionId": mission_id, "amount": 0.99, "displayName": "A", "anonymous": False},
            {"missionId": mission_id, "amount": 1.001, "displayName": "A", "anonymous": False},
            {"missionId": mission_id, "amount": 10, "displayName": "", "anonymous": False},
            {"missionId": mission_id, "amount": 10, "displayName": "A", "anonymous": False, "extra": 1},
        ]
        for payload in invalid:
            with self.subTest(payload=payload):
                self.assertEqual(self.request("POST", "/api/pledges", payload, auth)[0], 422)

        detail = self.request("GET", f"/api/impact-missions/{mission_id}")[1]
        funding = detail["mission"]["funding"]
        self.assertEqual(funding["simulatedPledged"], 32.34)
        self.assertEqual(funding["simulatedPledgeCount"], 2)
        platform = self.request("GET", "/api/platform")[1]
        self.assertEqual(platform["counters"]["simulatedPledgeAmount"], 32.34)
        self.assertEqual(platform["counters"]["simulatedPledgeCount"], 2)
        with sqlite3.connect(self.db_path) as db:
            stored = db.execute("SELECT amount_cents, display_name, anonymous, status FROM simulated_pledges ORDER BY created_at").fetchall()
            self.assertEqual(stored, [(1234, "Taylor", 0, "simulated"), (2000, "", 1, "simulated")])
            events = db.execute("SELECT event FROM pledge_events").fetchall()
            self.assertEqual(events, [("recorded_simulation",), ("recorded_simulation",)])
            with self.assertRaises(sqlite3.IntegrityError):
                db.execute("DELETE FROM pledge_events")

    def test_create_view_and_separate_token_authorities(self) -> None:
        auth, _ = self.register()
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
        status, page, share_headers = self.request("GET", share_url, headers=auth)
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

    def test_four_signal_matching_and_independent_acceptance(self) -> None:
        community = self.add_signal("community", source="Eastside Center", title="Laptops for students", quantity=20, unit="laptops")
        resource = self.add_signal("resource", source="Local employer", title="Retired laptops", quantity=24, unit="laptops")
        worker = self.add_signal("worker", source="Repair technician", title="Device inspection and setup", hours=10, hourlyRate=30)
        funding = self.add_signal("funding", source="Neighborhood fund", title="Paid repair budget", amount=300)
        status, listing, _ = self.request("GET", "/api/signals")
        self.assertEqual(status, 200)
        self.assertEqual(len(listing["signals"]), 4)
        self.assertTrue(all(item["verification"] == "unverified" for item in listing["signals"]))

        status, matches, _ = self.request("GET", "/api/opportunities")
        self.assertEqual(status, 200)
        self.assertEqual(len(matches["opportunities"]), 1)
        opportunity = matches["opportunities"][0]
        self.assertTrue(opportunity["ready"])
        self.assertEqual(opportunity["need"]["id"], community["signal"]["id"])
        self.assertEqual(opportunity["estimatedLaborCost"], 300)

        start_request = {"communitySignalId": community["signal"]["id"], "starterSignalId": worker["signal"]["id"]}
        self.assertEqual(self.request("POST", "/api/assemblies", start_request)[0], 403)
        self.assertEqual(self.request("POST", "/api/assemblies", start_request, self.owner_headers(funding))[0], 403)
        created = self.assemble(community, worker)
        self.assertEqual(created["status"], "inviting")
        self.assertNotIn("invitations", created)
        assembly_id = created["assemblyId"]
        status, public, _ = self.request("GET", "/api/assemblies")
        self.assertEqual(status, 200)
        self.assertNotIn("participants", json.dumps(public))
        self.assertNotIn("Local employer", json.dumps(public))
        self.assertNotIn("Repair technician", json.dumps(public))
        self.assertNotIn("Neighborhood fund", json.dumps(public))

        decisions = []
        participants = {"community": community, "resource": resource, "worker": worker, "funding": funding}
        for role, owner in participants.items():
            inbox_path = f"/api/signals/{owner['signal']['id']}/invitations"
            self.assertEqual(self.request("GET", inbox_path)[0], 403)
            wrong_owner = funding if role != "funding" else community
            self.assertEqual(self.request("GET", inbox_path, headers=self.owner_headers(wrong_owner))[0], 403)
            status, inbox, _ = self.request("GET", inbox_path, headers=self.owner_headers(owner))
            self.assertEqual(status, 200, inbox)
            self.assertEqual(len(inbox["invitations"]), 1)
            self.assertEqual(inbox["invitations"][0]["assemblyId"], assembly_id)
            self.assertEqual(inbox["invitations"][0]["role"], role)
            path = f"/api/invitations/{assembly_id}/{role}"
            self.assertEqual(self.request("GET", path)[0], 403)
            self.assertEqual(self.request("GET", path, headers=self.owner_headers(wrong_owner))[0], 403)
            status, details, _ = self.request("GET", path, headers=self.owner_headers(owner))
            self.assertEqual(status, 200, details)
            self.assertEqual(details["decision"], "pending")
            self.assertEqual(details["role"], role)
            self.assertEqual(self.request("POST", path, {"decision": "accepted"}, self.owner_headers(wrong_owner))[0], 403)
            status, response, _ = self.request("POST", path, {"decision": "accepted"}, self.owner_headers(owner))
            self.assertEqual(status, 200, response)
            decisions.append(response["status"])
            if len(decisions) < 4:
                self.assertEqual(response["status"], "inviting")
        self.assertEqual(decisions[-1], "confirmed")
        self.assertEqual(self.request("POST", path, {"decision": "accepted"}, self.owner_headers(owner))[0], 409)
        status, assemblies, _ = self.request("GET", "/api/assemblies")
        self.assertEqual(status, 200)
        self.assertEqual(assemblies["assemblies"][0]["status"], "confirmed")
        self.assertTrue(all(item["decision"] == "accepted" for item in assemblies["assemblies"][0]["confirmations"]))
        self.assertEqual(self.request("DELETE", f"/api/signals/{resource['signal']['id']}", headers={"X-Owner-Token": resource["ownerToken"]})[0], 409)
        stored = self.db_path.read_bytes().decode("utf-8", errors="ignore")
        for secret in [community["ownerToken"], resource["ownerToken"], worker["ownerToken"], funding["ownerToken"]]:
            self.assertNotIn(secret, stored)

    def test_matcher_rejects_gap_and_different_area(self) -> None:
        need = self.add_signal("community", quantity=10, unit="kits")
        self.add_signal("resource", quantity=9, unit="kits")
        self.add_signal("worker", hours=2, hourlyRate=40)
        self.add_signal("funding", amount=20)
        status, matches, _ = self.request("GET", "/api/opportunities")
        opportunity = matches["opportunities"][0]
        self.assertFalse(opportunity["ready"])
        self.assertEqual(opportunity["supplyGap"], 1)
        self.assertEqual(opportunity["fundingGap"], 60)
        self.assertEqual(self.request("POST", "/api/assemblies", {"communitySignalId": need["signal"]["id"], "starterSignalId": need["signal"]["id"]}, self.owner_headers(need))[0], 409)

        other = self.add_signal("resource", category="health", quantity=10, unit="kits")
        status, matches, _ = self.request("GET", "/api/opportunities")
        self.assertNotEqual(matches["opportunities"][0]["signals"]["resource"]["id"], other["signal"]["id"])

    def test_valid_owner_of_unselected_signal_cannot_start_another_assembly(self) -> None:
        need = self.add_signal("community", quantity=2, unit="laptops")
        self.add_signal("resource", quantity=2, unit="laptops")
        self.add_signal("worker", hours=1, hourlyRate=20)
        self.add_signal("funding", amount=20)
        outsider = self.add_signal("worker", category="health", hours=1, hourlyRate=20)
        status, body, _ = self.request(
            "POST", "/api/assemblies",
            {"communitySignalId": need["signal"]["id"], "starterSignalId": outsider["signal"]["id"]},
            self.owner_headers(outsider),
        )
        self.assertEqual(status, 403, body)
        self.assertEqual(self.request("GET", "/api/assemblies")[1]["assemblies"], [])

    def test_decline_reopens_reserved_signals_and_owner_can_withdraw(self) -> None:
        need = self.add_signal("community", quantity=1, unit="devices")
        self.add_signal("resource", quantity=1, unit="devices")
        self.add_signal("worker", hours=1, hourlyRate=20)
        funding = self.add_signal("funding", amount=20)
        assembly = self.assemble(need, need)
        status, declined, _ = self.request("POST", f"/api/invitations/{assembly['assemblyId']}/community", {"decision": "declined"}, self.owner_headers(need))
        self.assertEqual(status, 200)
        self.assertEqual(declined["status"], "declined")
        self.assertEqual(len(self.request("GET", "/api/signals")[1]["signals"]), 4)
        self.assertEqual(self.request("POST", f"/api/invitations/{assembly['assemblyId']}/funding", {"decision": "accepted"}, self.owner_headers(funding))[0], 409)
        owner = need["ownerToken"]
        status, withdrawn, _ = self.request("DELETE", f"/api/signals/{need['signal']['id']}", headers={"X-Owner-Token": owner})
        self.assertEqual(status, 200)
        self.assertEqual(withdrawn["status"], "withdrawn")
        self.assertEqual(self.request("DELETE", f"/api/signals/{need['signal']['id']}", headers={"X-Owner-Token": owner})[0], 409)

    def test_signal_validation_and_owner_authorization(self) -> None:
        signal = {"role": "funding", "source": "Funder", "title": "Offer", "category": "health", "location": "Anywhere", "details": "Funding", "quantity": 0, "unit": "", "hours": 0, "hourlyRate": 0, "amount": 25}
        self.assertEqual(self.request("POST", "/api/signals", {"signal": {**signal, "amount": True}})[0], 422)
        self.assertEqual(self.request("POST", "/api/signals", {"signal": {**signal, "extra": "no"}})[0], 422)
        self.assertEqual(self.request("POST", "/api/signals", {"signal": {**signal, "category": ["health"]}})[0], 422)
        created = self.add_signal("funding", amount=25)
        signal_id = created["signal"]["id"]
        self.assertEqual(self.request("DELETE", f"/api/signals/{signal_id}", headers={"X-Owner-Token": "not-a-token"})[0], 403)
        self.assertEqual(self.request("DELETE", f"/api/signals/{signal_id}", headers={"X-Owner-Token": created["ownerToken"]})[0], 200)

    def test_any_role_can_start_an_unmatched_lead(self) -> None:
        lead = self.add_signal("resource", source="Local company", title="Available tablets", quantity=12, unit="tablets")
        status, body, _ = self.request("GET", "/api/opportunities")
        self.assertEqual(status, 200)
        self.assertEqual(len(body["opportunities"]), 1)
        opportunity = body["opportunities"][0]
        self.assertEqual(opportunity["anchorRole"], "resource")
        self.assertEqual(opportunity["need"]["id"], lead["signal"]["id"])
        self.assertIn("community", opportunity["missing"])
        self.assertFalse(opportunity["ready"])

    def test_pending_assembly_expires_and_releases_offers(self) -> None:
        need = self.add_signal("community", quantity=1, unit="kits")
        self.add_signal("resource", quantity=1, unit="kits")
        worker = self.add_signal("worker", hours=1, hourlyRate=20)
        self.add_signal("funding", amount=20)
        assembly = self.assemble(need, worker)
        with sqlite3.connect(self.db_path) as db:
            db.execute("UPDATE assemblies SET expires_at = '2000-01-01T00:00:00.000Z' WHERE id_hash = ?", (assembly["assemblyId"],))
        self.assertEqual(self.request("GET", "/api/opportunities")[0], 200)
        self.assertEqual(len(self.request("GET", "/api/signals")[1]["signals"]), 4)
        status, invitation, _ = self.request("GET", f"/api/invitations/{assembly['assemblyId']}/worker", headers=self.owner_headers(worker))
        self.assertEqual(status, 200)
        self.assertEqual(invitation["status"], "expired")
        self.assertEqual(self.request("POST", f"/api/invitations/{assembly['assemblyId']}/worker", {"decision": "accepted"}, self.owner_headers(worker))[0], 409)

    def test_database_additively_migrates_prior_assembly_schema(self) -> None:
        legacy_path = Path(self.temp.name) / "legacy.sqlite3"
        with sqlite3.connect(legacy_path) as db:
            db.execute("CREATE TABLE assemblies (id_hash TEXT PRIMARY KEY, status TEXT NOT NULL CHECK (status IN ('inviting','confirmed','declined')), snapshot_json TEXT NOT NULL, created_at TEXT NOT NULL)")
            db.execute("INSERT INTO assemblies VALUES ('legacy-assembly', 'inviting', '{}', '2026-09-20T12:00:00.000Z')")
        initialize_database(legacy_path)
        with sqlite3.connect(legacy_path) as db:
            columns = {row[1] for row in db.execute("PRAGMA table_info(assemblies)").fetchall()}
            row = db.execute("SELECT status, expires_at, expired FROM assemblies WHERE id_hash = 'legacy-assembly'").fetchone()
        self.assertTrue({"expires_at", "expired"}.issubset(columns))
        self.assertEqual(row, ("inviting", "2026-09-27T12:00:00.000Z", 0))


if __name__ == "__main__":
    unittest.main()
