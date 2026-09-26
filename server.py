"""RIPPLE's local-only mission API and static preview server.

This stores user-entered drafts, not verified partners, funds, or outcomes.
Run with ``python3 server.py`` and open http://127.0.0.1:4174/.
"""

from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import math
import os
from pathlib import Path
import re
import secrets
import sqlite3
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, unquote, urlsplit


ROOT = Path(__file__).resolve().parent
DEFAULT_DB = ROOT / "ripple.sqlite3"
MAX_BODY = 32 * 1024
MAX_OPEN_SIGNALS = 500
STATIC_FILES = {
    "/": ("network.html", "text/html; charset=utf-8"),
    "/index.html": ("index.html", "text/html; charset=utf-8"),
    "/planner": ("index.html", "text/html; charset=utf-8"),
    "/network": ("network.html", "text/html; charset=utf-8"),
    "/network.css": ("network.css", "text/css; charset=utf-8"),
    "/network.js": ("network.js", "text/javascript; charset=utf-8"),
    "/styles.css": ("styles.css", "text/css; charset=utf-8"),
    "/engine.js": ("engine.js", "text/javascript; charset=utf-8"),
    "/app.js": ("app.js", "text/javascript; charset=utf-8"),
}
TEMPLATES = {"devices", "food", "tutoring", "custom"}
ROLES = {"asset", "skills", "funding", "anchor"}
PRIORITIES = {"balance", "access", "work", "durability"}
ROUTE_IDS = {
    "devices": {"direct", "repair", "crew"},
    "food": {"pickup", "coldchain", "kitchen"},
    "tutoring": {"dropin", "cohort", "peer"},
    "custom": set(),
}
TEXT_FIELDS = {
    "missionName": 90,
    "assetName": 90,
    "fundingLabel": 90,
    "skillLabel": 90,
    "anchorName": 90,
    "needText": 240,
    "location": 90,
}
NUMBER_FIELDS = {
    "quantity": (1, 100_000, True),
    "quality": (0, 100, False),
    "pickupDays": (1, 365, True),
    "budget": (1, 100_000_000, False),
    "skilledHours": (1, 100_000, False),
    "hourlyRate": (1, 10_000, False),
    "needCount": (1, 100_000, True),
}
STATE_FIELDS = (
    {"template", "role", "priority", "routeId", "parts", "proof", "edited", "fullExample"}
    | set(TEXT_FIELDS)
    | set(NUMBER_FIELDS)
)
ID_PATTERN = re.compile(r"^[A-Za-z0-9_-]{20,48}$")
TOKEN_PATTERN = re.compile(r"^[A-Za-z0-9_-]{30,80}$")
SIGNAL_ID_PATTERN = re.compile(r"^[A-Za-z0-9_-]{20,48}$")
SIGNAL_ROLES = {"resource", "worker", "funding", "community"}
SIGNAL_CATEGORIES = {"education", "health", "climate", "community", "workforce", "other"}
SIGNAL_TEXT_FIELDS = {"source": 90, "title": 100, "category": 20, "location": 90, "details": 260, "unit": 40}
SIGNAL_NUMBER_FIELDS = {
    "quantity": (0, 100_000), "hours": (0, 100_000),
    "hourlyRate": (0, 10_000), "amount": (0, 100_000_000),
}


class ValidationError(ValueError):
    pass


def _exact_keys(value: object, expected: set[str], name: str) -> dict:
    if type(value) is not dict or set(value) != expected:
        raise ValidationError(f"{name} must contain exactly: {', '.join(sorted(expected))}")
    return value


def validate_state(value: object) -> dict:
    """Reject unknown fields and malformed data before it reaches persistent storage."""
    state = _exact_keys(value, STATE_FIELDS, "state")
    if type(state["template"]) is not str or state["template"] not in TEMPLATES:
        raise ValidationError("template must be devices, food, tutoring, or custom")
    if type(state["role"]) is not str or state["role"] not in ROLES:
        raise ValidationError("role is invalid")
    if type(state["priority"]) is not str or state["priority"] not in PRIORITIES:
        raise ValidationError("priority is invalid")
    route = state["routeId"]
    if route is not None and (type(route) is not str or route not in ROUTE_IDS[state["template"]]):
        raise ValidationError("routeId is invalid for this template")
    for key, maximum in TEXT_FIELDS.items():
        text = state[key]
        if type(text) is not str or not text.strip() or len(text) > maximum or any(ord(c) < 32 and c not in "\t\n" for c in text):
            raise ValidationError(f"{key} must be nonempty text of at most {maximum} characters")
    for key, (minimum, maximum, integral) in NUMBER_FIELDS.items():
        number = state[key]
        if type(number) not in (int, float) or not math.isfinite(number) or not minimum <= number <= maximum:
            raise ValidationError(f"{key} must be a finite number from {minimum} to {maximum}")
        if integral and int(number) != number:
            raise ValidationError(f"{key} must be a whole number")
    parts = _exact_keys(state["parts"], ROLES, "parts")
    proof = _exact_keys(state["proof"], {"delivered", "followup"}, "proof")
    for key, value in parts.items():
        if type(value) is not bool:
            raise ValidationError(f"parts.{key} must be true or false")
    for key, value in proof.items():
        if type(value) is not bool:
            raise ValidationError(f"proof.{key} must be true or false")
    for key in ("edited", "fullExample"):
        if type(state[key]) is not bool:
            raise ValidationError(f"{key} must be true or false")
    return state


def _hash(secret: str) -> str:
    return hashlib.sha256(secret.encode("ascii")).hexdigest()


def _owns_token(token: str, expected_hash: str | None) -> bool:
    return bool(expected_hash and TOKEN_PATTERN.fullmatch(token)
                and hmac.compare_digest(_hash(token), expected_hash))


def _timestamp() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _connect(db_path: Path) -> sqlite3.Connection:
    connection = sqlite3.connect(db_path, timeout=10)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    connection.execute("PRAGMA busy_timeout = 10000")
    return connection


def initialize_database(db_path: Path) -> None:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    # Create the file owner-only before SQLite opens it; no mission data belongs
    # in a web-served directory listing or a source-control commit.
    try:
        fd = os.open(db_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except FileExistsError:
        pass
    else:
        os.close(fd)
    with _connect(db_path) as db:
        db.executescript(
            """
            CREATE TABLE IF NOT EXISTS missions (
                id_hash TEXT PRIMARY KEY,
                view_token_hash TEXT NOT NULL,
                edit_token_hash TEXT NOT NULL,
                state_json TEXT NOT NULL,
                version INTEGER NOT NULL CHECK (version >= 1),
                updated_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS revisions (
                id_hash TEXT NOT NULL REFERENCES missions(id_hash),
                version INTEGER NOT NULL CHECK (version >= 1),
                state_json TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                PRIMARY KEY (id_hash, version)
            );
            CREATE TRIGGER IF NOT EXISTS revisions_no_update
            BEFORE UPDATE ON revisions BEGIN
                SELECT RAISE(ABORT, 'revisions are immutable');
            END;
            CREATE TRIGGER IF NOT EXISTS revisions_no_delete
            BEFORE DELETE ON revisions BEGIN
                SELECT RAISE(ABORT, 'revisions are immutable');
            END;
            CREATE TABLE IF NOT EXISTS signals (
                id_hash TEXT PRIMARY KEY,
                owner_token_hash TEXT NOT NULL,
                payload_json TEXT NOT NULL,
                status TEXT NOT NULL CHECK (status IN ('open', 'reserved', 'withdrawn')),
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS signal_events (
                event_id INTEGER PRIMARY KEY AUTOINCREMENT,
                id_hash TEXT NOT NULL REFERENCES signals(id_hash),
                event TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS assemblies (
                id_hash TEXT PRIMARY KEY,
                status TEXT NOT NULL CHECK (status IN ('inviting', 'confirmed', 'declined')),
                snapshot_json TEXT NOT NULL,
                created_at TEXT NOT NULL,
                expires_at TEXT NOT NULL DEFAULT '',
                expired INTEGER NOT NULL DEFAULT 0 CHECK (expired IN (0, 1))
            );
            CREATE TABLE IF NOT EXISTS assembly_participants (
                assembly_id_hash TEXT NOT NULL REFERENCES assemblies(id_hash),
                role TEXT NOT NULL,
                signal_id_hash TEXT NOT NULL REFERENCES signals(id_hash),
                invite_token_hash TEXT NOT NULL,
                decision TEXT NOT NULL CHECK (decision IN ('pending', 'accepted', 'declined')),
                decided_at TEXT,
                PRIMARY KEY (assembly_id_hash, role)
            );
            CREATE TABLE IF NOT EXISTS assembly_events (
                event_id INTEGER PRIMARY KEY AUTOINCREMENT,
                assembly_id_hash TEXT NOT NULL REFERENCES assemblies(id_hash),
                role TEXT NOT NULL,
                event TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
            CREATE TRIGGER IF NOT EXISTS signal_events_no_update
            BEFORE UPDATE ON signal_events BEGIN
                SELECT RAISE(ABORT, 'signal events are immutable');
            END;
            CREATE TRIGGER IF NOT EXISTS signal_events_no_delete
            BEFORE DELETE ON signal_events BEGIN
                SELECT RAISE(ABORT, 'signal events are immutable');
            END;
            CREATE TRIGGER IF NOT EXISTS assembly_events_no_update
            BEFORE UPDATE ON assembly_events BEGIN
                SELECT RAISE(ABORT, 'assembly events are immutable');
            END;
            CREATE TRIGGER IF NOT EXISTS assembly_events_no_delete
            BEFORE DELETE ON assembly_events BEGIN
                SELECT RAISE(ABORT, 'assembly events are immutable');
            END;
            CREATE TRIGGER IF NOT EXISTS assembly_decision_once
            BEFORE UPDATE OF decision ON assembly_participants
            WHEN OLD.decision != 'pending' BEGIN
                SELECT RAISE(ABORT, 'participant decisions are final');
            END;
            """
        )
        assembly_columns = {row["name"] for row in db.execute("PRAGMA table_info(assemblies)").fetchall()}
        if "expires_at" not in assembly_columns:
            db.execute("ALTER TABLE assemblies ADD COLUMN expires_at TEXT NOT NULL DEFAULT ''")
        if "expired" not in assembly_columns:
            db.execute("ALTER TABLE assemblies ADD COLUMN expired INTEGER NOT NULL DEFAULT 0 CHECK (expired IN (0, 1))")
        rows = db.execute("SELECT id_hash, created_at FROM assemblies WHERE expires_at = ''").fetchall()
        for row in rows:
            try:
                created = datetime.fromisoformat(row["created_at"].replace("Z", "+00:00"))
            except ValueError:
                created = datetime.now(timezone.utc)
            expires_at = (created + timedelta(days=7)).isoformat(timespec="milliseconds").replace("+00:00", "Z")
            db.execute("UPDATE assemblies SET expires_at = ? WHERE id_hash = ?", (expires_at, row["id_hash"]))
        db.executescript(
            """
            CREATE TRIGGER IF NOT EXISTS assembly_expired_once
            BEFORE UPDATE OF expired ON assemblies
            WHEN OLD.expired = 1 AND NEW.expired != 1 BEGIN
                SELECT RAISE(ABORT, 'expired invitations cannot be reactivated');
            END;
            """
        )


def validate_signal(value: object) -> dict:
    expected = {"role", *SIGNAL_TEXT_FIELDS, *SIGNAL_NUMBER_FIELDS}
    signal = _exact_keys(value, expected, "signal")
    if type(signal["role"]) is not str or signal["role"] not in SIGNAL_ROLES:
        raise ValidationError("role must be resource, worker, funding, or community")
    for key, maximum in SIGNAL_TEXT_FIELDS.items():
        text = signal[key]
        if type(text) is not str or len(text) > maximum or any(ord(c) < 32 and c not in "\t\n" for c in text):
            raise ValidationError(f"{key} must be text of at most {maximum} characters")
        if key != "unit" and not text.strip():
            raise ValidationError(f"{key} cannot be blank")
    if type(signal["category"]) is not str or signal["category"] not in SIGNAL_CATEGORIES:
        raise ValidationError("category is invalid")
    for key, (minimum, maximum) in SIGNAL_NUMBER_FIELDS.items():
        number = signal[key]
        if type(number) not in (int, float) or not math.isfinite(number) or not minimum <= number <= maximum:
            raise ValidationError(f"{key} must be a finite number from {minimum} to {maximum}")
        if int(number) != number:
            raise ValidationError(f"{key} must be a whole number")
    role = signal["role"]
    if role in {"resource", "community"} and (signal["quantity"] < 1 or not signal["unit"].strip()):
        raise ValidationError("resources and community needs require a quantity and unit")
    if role == "worker" and (signal["hours"] < 1 or signal["hourlyRate"] < 1):
        raise ValidationError("a skilled-work offer requires hours and an hourly rate")
    if role == "funding" and signal["amount"] < 1:
        raise ValidationError("a funding offer must be greater than zero")
    return signal


def _signal_public(signal_id: str, payload: dict, status: str, created_at: str) -> dict:
    return {"id": signal_id, **payload, "status": status, "verification": "unverified", "createdAt": created_at}


def _compatible_location(first: str, second: str) -> bool:
    a, b = first.strip().casefold(), second.strip().casefold()
    return a == b or a in {"anywhere", "remote"} or b in {"anywhere", "remote"}


def _build_opportunities(db: sqlite3.Connection) -> list[dict]:
    rows = db.execute("SELECT id_hash, payload_json, status, created_at FROM signals WHERE status = 'open' ORDER BY created_at").fetchall()
    records = []
    for row in rows:
        payload = json.loads(row["payload_json"])
        records.append({"id": row["id_hash"], "payload": payload, "createdAt": row["created_at"]})

    def peers(role: str, community: dict) -> list[dict]:
        return [item for item in records if item["payload"]["role"] == role
                and item["payload"]["category"] == community["category"]
                and _compatible_location(item["payload"]["location"], community["location"])]

    opportunities = []
    for need in records:
        community = need["payload"]
        if community["role"] != "community":
            continue
        resources = [item for item in peers("resource", community) if item["payload"]["unit"].strip().casefold() == community["unit"].strip().casefold()]
        resources.sort(key=lambda item: (item["payload"]["quantity"] >= community["quantity"], -item["payload"]["quantity"] if item["payload"]["quantity"] >= community["quantity"] else item["payload"]["quantity"], item["createdAt"]), reverse=True)
        workers = peers("worker", community)
        workers.sort(key=lambda item: (item["payload"]["hours"] * item["payload"]["hourlyRate"], item["payload"]["hours"], item["createdAt"]))
        worker = workers[0] if workers else None
        funders = peers("funding", community)
        estimated_cost = worker["payload"]["hours"] * worker["payload"]["hourlyRate"] if worker else 0
        funders.sort(key=lambda item: (item["payload"]["amount"] >= estimated_cost, -item["payload"]["amount"] if item["payload"]["amount"] >= estimated_cost else item["payload"]["amount"], item["createdAt"]), reverse=True)
        selected = {
            "community": need,
            "resource": resources[0] if resources else None,
            "worker": worker,
            "funding": funders[0] if funders else None,
        }
        missing = [role for role, item in selected.items() if item is None]
        resource = selected["resource"]
        worker = selected["worker"]
        fund = selected["funding"]
        shortfall = 0
        if worker and fund:
            shortfall = max(0, worker["payload"]["hours"] * worker["payload"]["hourlyRate"] - fund["payload"]["amount"])
        supplied = resource["payload"]["quantity"] if resource else 0
        supply_gap = max(0, community["quantity"] - supplied)
        ready = not missing and not shortfall and not supply_gap
        ids = [selected[role]["id"] if selected[role] else "-" for role in ("community", "resource", "worker", "funding")]
        opportunities.append({
            "id": hashlib.sha256("|".join(ids).encode("ascii")).hexdigest()[:24],
            "need": _signal_public(need["id"], community, "open", need["createdAt"]),
            "signals": {role: _signal_public(item["id"], item["payload"], "open", item["createdAt"]) if item else None
                        for role, item in selected.items()},
            "missing": missing,
            "supplyGap": supply_gap,
            "fundingGap": shortfall,
            "estimatedLaborCost": worker["payload"]["hours"] * worker["payload"]["hourlyRate"] if worker else 0,
            "ready": ready,
            "anchorRole": "community",
        })
    matched_ids = {item["id"] for opportunity in opportunities for item in opportunity["signals"].values() if item}
    for record in records:
        role = record["payload"]["role"]
        if role == "community" or record["id"] in matched_ids:
            continue
        signal = _signal_public(record["id"], record["payload"], "open", record["createdAt"])
        selected = {key: (signal if key == role else None) for key in ("community", "resource", "worker", "funding")}
        opportunities.append({
            "id": hashlib.sha256((record["id"] + "|unmatched").encode("ascii")).hexdigest()[:24],
            "need": signal,
            "signals": selected,
            "missing": [key for key, item in selected.items() if item is None],
            "supplyGap": 0,
            "fundingGap": 0,
            "estimatedLaborCost": 0,
            "ready": False,
            "anchorRole": role,
        })
    return opportunities


def _assembly_public(db: sqlite3.Connection, row: sqlite3.Row) -> dict:
    snapshot = json.loads(row["snapshot_json"])
    participants = db.execute(
        "SELECT role, decision FROM assembly_participants WHERE assembly_id_hash = ? ORDER BY role",
        (row["id_hash"],),
    ).fetchall()
    return {
        "id": row["id_hash"], "status": "expired" if row["expired"] else row["status"], "createdAt": row["created_at"], "expiresAt": row["expires_at"],
        "mission": {"title": snapshot.get("title", "Untitled mission"), "location": snapshot.get("location", "Location not set")},
        "confirmations": [{"role": item["role"], "decision": item["decision"]} for item in participants],
    }


def _expire_stale_assemblies(db: sqlite3.Connection) -> None:
    """Release unconfirmed offers after a week; invitation links then stop working."""
    now = _timestamp()
    db.execute("BEGIN IMMEDIATE")
    stale = db.execute("SELECT id_hash FROM assemblies WHERE status = 'inviting' AND expired = 0 AND expires_at <= ?", (now,)).fetchall()
    for row in stale:
        assembly_id = row["id_hash"]
        db.execute("UPDATE assemblies SET expired = 1 WHERE id_hash = ?", (assembly_id,))
        db.execute("UPDATE signals SET status = 'open' WHERE id_hash IN (SELECT signal_id_hash FROM assembly_participants WHERE assembly_id_hash = ?)", (assembly_id,))
        db.execute("INSERT INTO assembly_events (assembly_id_hash, role, event, created_at) VALUES (?, 'system', 'expired', ?)", (assembly_id, now))
    db.commit()


class RippleServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True

    def __init__(self, port: int = 4174, db_path: Path = DEFAULT_DB):
        self.db_path = Path(db_path).resolve()
        initialize_database(self.db_path)
        super().__init__(("127.0.0.1", port), RippleHandler)


class RippleHandler(BaseHTTPRequestHandler):
    server: RippleServer
    protocol_version = "HTTP/1.1"

    def log_message(self, format: str, *args: object) -> None:
        # GET view tokens travel in query strings; never print request lines.
        pass

    def _headers(self, status: int, content_type: str, content_length: int) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(content_length))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Cross-Origin-Resource-Policy", "same-origin")
        self.send_header(
            "Content-Security-Policy",
            "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; "
            "img-src 'self' data:; connect-src 'self'; object-src 'none'; "
            "base-uri 'none'; frame-ancestors 'none'; form-action 'self'",
        )
        self.end_headers()

    def _json(self, status: int, payload: dict) -> None:
        body = json.dumps(payload, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
        self._headers(status, "application/json; charset=utf-8", len(body))
        self.wfile.write(body)

    def _error(self, status: int, code: str, message: str) -> None:
        self._json(status, {"error": code, "message": message})

    def _allowed_origin(self) -> bool:
        expected = {f"127.0.0.1:{self.server.server_port}", f"localhost:{self.server.server_port}"}
        host = self.headers.get("Host", "")
        if host not in expected:
            self._error(403, "bad_host", "Use the localhost RIPPLE address")
            return False
        origin = self.headers.get("Origin")
        if origin and origin not in {"http://" + item for item in expected}:
            self._error(403, "bad_origin", "Cross-origin requests are not accepted")
            return False
        return True

    def _read_json(self) -> dict | None:
        if self.headers.get("Transfer-Encoding"):
            self.close_connection = True
            self._error(400, "bad_body", "Chunked request bodies are not supported")
            return None
        if self.headers.get("Content-Type", "").split(";", 1)[0].strip().lower() != "application/json":
            self.close_connection = True
            self._error(415, "content_type", "Send application/json")
            return None
        raw_length = self.headers.get("Content-Length")
        try:
            length = int(raw_length) if raw_length is not None else -1
        except ValueError:
            length = -1
        if length <= 0:
            self.close_connection = True
            self._error(400, "bad_body", "A JSON body is required")
            return None
        if length > MAX_BODY:
            self.close_connection = True
            self._error(413, "too_large", "Mission JSON must be 32 KB or smaller")
            return None
        try:
            raw = self.rfile.read(length).decode("utf-8")

            def unique_keys(pairs: list[tuple[str, object]]) -> dict:
                result = {}
                for key, value in pairs:
                    if key in result:
                        raise ValidationError("Duplicate JSON keys are not accepted")
                    result[key] = value
                return result

            parsed = json.loads(
                raw,
                object_pairs_hook=unique_keys,
                parse_constant=lambda constant: (_ for _ in ()).throw(ValidationError("Non-finite numbers are not accepted")),
            )
        except (UnicodeDecodeError, json.JSONDecodeError, ValidationError, ValueError, RecursionError):
            self._error(400, "bad_json", "Send valid UTF-8 JSON without duplicate keys")
            return None
        if type(parsed) is not dict:
            self._error(400, "bad_json", "JSON body must be an object")
            return None
        return parsed

    def _path(self) -> tuple[str, dict[str, list[str]]]:
        parsed = urlsplit(self.path)
        return unquote(parsed.path), parse_qs(parsed.query, keep_blank_values=True)

    def _mission_path(self, path: str) -> tuple[str, bool] | None:
        match = re.fullmatch(r"/api/missions/([^/]+)(/revisions)?", path)
        if not match or not ID_PATTERN.fullmatch(match.group(1)):
            return None
        return match.group(1), bool(match.group(2))

    def _signal_path(self, path: str) -> str | None:
        match = re.fullmatch(r"/api/signals/([^/]+)", path)
        return match.group(1) if match and SIGNAL_ID_PATTERN.fullmatch(match.group(1)) else None

    def _signal_invitations_path(self, path: str) -> str | None:
        match = re.fullmatch(r"/api/signals/([^/]+)/invitations", path)
        return match.group(1) if match and SIGNAL_ID_PATTERN.fullmatch(match.group(1)) else None

    def _invitation_path(self, path: str) -> tuple[str, str] | None:
        match = re.fullmatch(r"/api/invitations/([^/]+)/(resource|worker|funding|community)", path)
        if not match or not SIGNAL_ID_PATTERN.fullmatch(match.group(1)):
            return None
        return match.group(1), match.group(2)

    def _authorized_row(self, mission_id: str, token: str, kind: str):
        if not TOKEN_PATTERN.fullmatch(token):
            self._error(403, "forbidden", "A valid access token is required")
            return None
        with _connect(self.server.db_path) as db:
            row = db.execute("SELECT * FROM missions WHERE id_hash = ?", (_hash(mission_id),)).fetchone()
        if row is None:
            self._error(404, "not_found", "Mission not found")
            return None
        if not hmac.compare_digest(_hash(token), row[f"{kind}_token_hash"]):
            self._error(403, "forbidden", "A valid access token is required")
            return None
        return row

    def do_GET(self) -> None:
        if not self._allowed_origin():
            return
        path, query = self._path()
        if path == "/api/health" and not query:
            with _connect(self.server.db_path) as db:
                db.execute("SELECT 1").fetchone()
            self._json(200, {"ok": True, "mode": "local", "database": "ready", "matching": "ready"})
            return
        if path == "/api/signals" and not query:
            with _connect(self.server.db_path) as db:
                _expire_stale_assemblies(db)
                rows = db.execute("SELECT id_hash, payload_json, status, created_at FROM signals WHERE status = 'open' ORDER BY created_at DESC LIMIT ?", (MAX_OPEN_SIGNALS,)).fetchall()
            self._json(200, {"signals": [_signal_public(row["id_hash"], json.loads(row["payload_json"]), row["status"], row["created_at"]) for row in rows]})
            return
        if path == "/api/opportunities" and not query:
            with _connect(self.server.db_path) as db:
                _expire_stale_assemblies(db)
                opportunities = _build_opportunities(db)
            self._json(200, {"opportunities": opportunities})
            return
        if path == "/api/assemblies" and not query:
            with _connect(self.server.db_path) as db:
                _expire_stale_assemblies(db)
                rows = db.execute("SELECT * FROM assemblies ORDER BY created_at DESC LIMIT 50").fetchall()
                assemblies = [_assembly_public(db, row) for row in rows]
            self._json(200, {"assemblies": assemblies})
            return
        signal_id = self._signal_invitations_path(path)
        if signal_id and not query:
            owner_token = self.headers.get("X-Owner-Token", "")
            if not TOKEN_PATTERN.fullmatch(owner_token):
                self._error(403, "forbidden", "A valid listing owner token is required")
                return
            with _connect(self.server.db_path) as db:
                _expire_stale_assemblies(db)
                signal = db.execute("SELECT owner_token_hash FROM signals WHERE id_hash = ?", (signal_id,)).fetchone()
                if signal is None or not _owns_token(owner_token, signal["owner_token_hash"]):
                    self._error(403, "forbidden", "A valid listing owner token is required")
                    return
                rows = db.execute(
                    "SELECT a.id_hash, a.status, a.expired, a.expires_at, a.snapshot_json, p.role, p.decision "
                    "FROM assembly_participants p JOIN assemblies a ON a.id_hash = p.assembly_id_hash "
                    "WHERE p.signal_id_hash = ? ORDER BY a.created_at DESC LIMIT 50", (signal_id,),
                ).fetchall()
                invitations = []
                for row in rows:
                    snapshot = json.loads(row["snapshot_json"])
                    invitations.append({
                        "assemblyId": row["id_hash"], "role": row["role"], "decision": row["decision"],
                        "status": "expired" if row["expired"] else row["status"], "expiresAt": row["expires_at"],
                        "title": snapshot["title"], "location": snapshot["location"],
                    })
            self._json(200, {"invitations": invitations})
            return
        invitation_path = self._invitation_path(path)
        if invitation_path:
            assembly_id, role = invitation_path
            owner_token = self.headers.get("X-Owner-Token", "")
            if query or self.headers.get("X-Invite-Token") or not TOKEN_PATTERN.fullmatch(owner_token):
                self._error(403, "forbidden", "A valid listing owner token is required")
                return
            with _connect(self.server.db_path) as db:
                _expire_stale_assemblies(db)
                row = db.execute(
                    "SELECT a.*, p.decision, s.owner_token_hash "
                    "FROM assemblies a JOIN assembly_participants p ON p.assembly_id_hash = a.id_hash "
                    "JOIN signals s ON s.id_hash = p.signal_id_hash "
                    "WHERE a.id_hash = ? AND p.role = ?", (assembly_id, role),
                ).fetchone()
                if row is None or not _owns_token(owner_token, row["owner_token_hash"]):
                    self._error(403, "forbidden", "A valid listing owner token is required")
                    return
                snapshot = json.loads(row["snapshot_json"])
            self._json(200, {"role": role, "decision": row["decision"], "mission": snapshot,
                             "status": "expired" if row["expired"] else row["status"], "expiresAt": row["expires_at"]})
            return
        mission_path = self._mission_path(path)
        if mission_path:
            mission_id, revisions = mission_path
            tokens = query.get("viewToken", [])
            if len(tokens) != 1 or len(query) != 1:
                self._error(403, "forbidden", "A view token is required")
                return
            row = self._authorized_row(mission_id, tokens[0], "view")
            if row is None:
                return
            if revisions:
                with _connect(self.server.db_path) as db:
                    entries = db.execute(
                        "SELECT version, updated_at FROM revisions WHERE id_hash = ? ORDER BY version DESC",
                        (_hash(mission_id),),
                    ).fetchall()
                self._json(200, {"revisions": [{"version": item["version"], "updatedAt": item["updated_at"]} for item in entries]})
            else:
                self._json(200, {"id": mission_id, "state": json.loads(row["state_json"]), "version": row["version"], "updatedAt": row["updated_at"]})
            return
        static = STATIC_FILES.get(path)
        share_query = (
            path in ("/", "/index.html")
            and set(query) == {"mission", "view"}
            and len(query["mission"]) == 1
            and len(query["view"]) == 1
            and bool(ID_PATTERN.fullmatch(query["mission"][0]))
            and bool(TOKEN_PATTERN.fullmatch(query["view"][0]))
        )
        if static and (not query or share_query):
            if share_query:
                static = STATIC_FILES["/index.html"]
            filename, content_type = static
            file_path = (ROOT / filename).resolve()
            if file_path.parent != ROOT or not file_path.is_file():
                self._error(404, "not_found", "File not found")
                return
            body = file_path.read_bytes()
            self._headers(200, content_type, len(body))
            self.wfile.write(body)
            return
        self._error(404, "not_found", "Route not found")

    def do_POST(self) -> None:
        if not self._allowed_origin():
            return
        path, query = self._path()
        if query:
            self._error(404, "not_found", "Route not found")
            return
        body = self._read_json()
        if body is None:
            return
        if path == "/api/signals":
            try:
                _exact_keys(body, {"signal"}, "request")
                payload = validate_signal(body["signal"])
            except ValidationError as error:
                self._error(422, "validation", str(error))
                return
            signal_id = secrets.token_urlsafe(24)
            owner_token = secrets.token_urlsafe(32)
            timestamp = _timestamp()
            with _connect(self.server.db_path) as db:
                db.execute("BEGIN IMMEDIATE")
                count = db.execute("SELECT COUNT(*) FROM signals WHERE status = 'open'").fetchone()[0]
                if count >= MAX_OPEN_SIGNALS:
                    self._error(429, "signal_limit", "This local pilot has reached its open-signal limit")
                    return
                db.execute("INSERT INTO signals VALUES (?, ?, ?, 'open', ?)", (signal_id, _hash(owner_token), json.dumps(payload, separators=(",", ":"), ensure_ascii=False), timestamp))
                db.execute("INSERT INTO signal_events (id_hash, event, created_at) VALUES (?, 'listed', ?)", (signal_id, timestamp))
            self._json(201, {"signal": _signal_public(signal_id, payload, "open", timestamp), "ownerToken": owner_token})
            return
        if path == "/api/assemblies":
            try:
                _exact_keys(body, {"communitySignalId", "starterSignalId"}, "request")
                community_id = body["communitySignalId"]
                if type(community_id) is not str or not SIGNAL_ID_PATTERN.fullmatch(community_id):
                    raise ValidationError("communitySignalId is invalid")
                starter_id = body["starterSignalId"]
                if type(starter_id) is not str or not SIGNAL_ID_PATTERN.fullmatch(starter_id):
                    raise ValidationError("starterSignalId is invalid")
            except ValidationError as error:
                self._error(422, "validation", str(error))
                return
            owner_token = self.headers.get("X-Owner-Token", "")
            if not TOKEN_PATTERN.fullmatch(owner_token):
                self._error(403, "forbidden", "A valid listing owner token is required")
                return
            assembly_id = secrets.token_urlsafe(24)
            timestamp = _timestamp()
            expires_at = (datetime.now(timezone.utc) + timedelta(days=7)).isoformat(timespec="milliseconds").replace("+00:00", "Z")
            with _connect(self.server.db_path) as db:
                _expire_stale_assemblies(db)
                db.execute("BEGIN IMMEDIATE")
                opportunity = next((item for item in _build_opportunities(db) if item["need"]["id"] == community_id), None)
                if opportunity is None:
                    self._error(404, "not_found", "This community need is no longer open")
                    return
                selected = opportunity["signals"]
                selected_ids = {item["id"] for item in selected.values() if item is not None}
                if starter_id not in selected_ids:
                    self._error(403, "forbidden", "Only a selected listing owner can start invitations")
                    return
                starter = db.execute("SELECT owner_token_hash FROM signals WHERE id_hash = ?", (starter_id,)).fetchone()
                if starter is None or not _owns_token(owner_token, starter["owner_token_hash"]):
                    self._error(403, "forbidden", "A valid listing owner token is required")
                    return
                if not opportunity["ready"]:
                    self._json(409, {"error": "not_ready", "message": "The mission still has a capacity or funding gap", "opportunity": opportunity})
                    return
                signal_ids = [selected[role]["id"] for role in ("community", "resource", "worker", "funding")]
                payloads = {role: selected[role] for role in ("community", "resource", "worker", "funding")}
                snapshot = {
                    "title": selected["community"]["title"],
                    "category": selected["community"]["category"],
                    "location": selected["community"]["location"],
                    "participants": {role: {key: value for key, value in item.items() if key not in {"id", "status", "verification", "createdAt"}} for role, item in payloads.items()},
                    "estimatedLaborCost": opportunity["estimatedLaborCost"],
                    "note": "A planning estimate only. No money or goods have moved.",
                }
                db.execute("INSERT INTO assemblies (id_hash, status, snapshot_json, created_at, expires_at) VALUES (?, 'inviting', ?, ?, ?)", (assembly_id, json.dumps(snapshot, separators=(",", ":"), ensure_ascii=False), timestamp, expires_at))
                for role in ("community", "resource", "worker", "funding"):
                    # Retain the legacy non-null column so existing databases keep working.
                    # Invitation access now depends only on the listing owner's token.
                    unused_invite_hash = _hash(secrets.token_urlsafe(32))
                    db.execute("INSERT INTO assembly_participants VALUES (?, ?, ?, ?, 'pending', NULL)", (assembly_id, role, selected[role]["id"], unused_invite_hash))
                    db.execute("INSERT INTO assembly_events (assembly_id_hash, role, event, created_at) VALUES (?, ?, 'invited', ?)", (assembly_id, role, timestamp))
                for signal_id in signal_ids:
                    changed = db.execute("UPDATE signals SET status = 'reserved' WHERE id_hash = ? AND status = 'open'", (signal_id,)).rowcount
                    if changed != 1:
                        db.rollback()
                        self._error(409, "signal_taken", "One of these offers was just reserved; refresh and try again")
                        return
            self._json(201, {"assemblyId": assembly_id, "status": "inviting", "expiresAt": expires_at})
            return
        if path.startswith("/api/invitations/"):
            invitation = self._invitation_path(path)
            if invitation is None:
                self._error(404, "not_found", "Invitation not found")
                return
            assembly_id, role = invitation
            try:
                _exact_keys(body, {"decision"}, "request")
                if type(body["decision"]) is not str or body["decision"] not in {"accepted", "declined"}:
                    raise ValidationError("decision must be accepted or declined")
            except ValidationError as error:
                self._error(422, "validation", str(error))
                return
            owner_token = self.headers.get("X-Owner-Token", "")
            if self.headers.get("X-Invite-Token") or not TOKEN_PATTERN.fullmatch(owner_token):
                self._error(403, "forbidden", "A valid listing owner token is required")
                return
            timestamp = _timestamp()
            with _connect(self.server.db_path) as db:
                _expire_stale_assemblies(db)
                db.execute("BEGIN IMMEDIATE")
                row = db.execute(
                    "SELECT a.status, a.expired, p.decision, s.owner_token_hash FROM assemblies a "
                    "JOIN assembly_participants p ON p.assembly_id_hash = a.id_hash "
                    "JOIN signals s ON s.id_hash = p.signal_id_hash "
                    "WHERE a.id_hash = ? AND p.role = ?", (assembly_id, role),
                ).fetchone()
                if row is None or not _owns_token(owner_token, row["owner_token_hash"]):
                    self._error(403, "forbidden", "A valid listing owner token is required")
                    return
                if row["status"] != "inviting" or row["expired"]:
                    self._error(409, "invitation_inactive", "This invitation is no longer active")
                    return
                if row["decision"] != "pending":
                    self._error(409, "already_decided", "This invitation already has a final decision")
                    return
                decision = body["decision"]
                db.execute("UPDATE assembly_participants SET decision = ?, decided_at = ? WHERE assembly_id_hash = ? AND role = ?", (decision, timestamp, assembly_id, role))
                db.execute("INSERT INTO assembly_events (assembly_id_hash, role, event, created_at) VALUES (?, ?, ?, ?)", (assembly_id, role, decision, timestamp))
                decisions = [item[0] for item in db.execute("SELECT decision FROM assembly_participants WHERE assembly_id_hash = ?", (assembly_id,)).fetchall()]
                new_status = "declined" if "declined" in decisions else "confirmed" if all(item == "accepted" for item in decisions) else "inviting"
                db.execute("UPDATE assemblies SET status = ? WHERE id_hash = ?", (new_status, assembly_id))
                if new_status == "declined":
                    db.execute("UPDATE signals SET status = 'open' WHERE id_hash IN (SELECT signal_id_hash FROM assembly_participants WHERE assembly_id_hash = ?)", (assembly_id,))
            self._json(200, {"status": new_status, "decision": decision})
            return
        if path != "/api/missions":
            self._error(404, "not_found", "Route not found")
            return
        try:
            _exact_keys(body, {"state"}, "request")
            state = validate_state(body["state"])
        except ValidationError as error:
            self._error(422, "validation", str(error))
            return
        state_json = json.dumps(state, separators=(",", ":"), ensure_ascii=False, allow_nan=False)
        timestamp = _timestamp()
        for _ in range(3):
            mission_id = secrets.token_urlsafe(24)
            view_token = secrets.token_urlsafe(32)
            edit_token = secrets.token_urlsafe(32)
            id_hash = _hash(mission_id)
            try:
                with _connect(self.server.db_path) as db:
                    db.execute(
                        "INSERT INTO missions VALUES (?, ?, ?, ?, ?, ?)",
                        (id_hash, _hash(view_token), _hash(edit_token), state_json, 1, timestamp),
                    )
                    db.execute(
                        "INSERT INTO revisions VALUES (?, ?, ?, ?)",
                        (id_hash, 1, state_json, timestamp),
                    )
            except sqlite3.IntegrityError:
                continue
            self._json(201, {"id": mission_id, "viewToken": view_token, "editToken": edit_token, "version": 1, "updatedAt": timestamp})
            return
        self._error(500, "create_failed", "Could not create a mission")

    def do_DELETE(self) -> None:
        if not self._allowed_origin():
            return
        path, query = self._path()
        signal_id = self._signal_path(path)
        if signal_id is None or query:
            self._error(404, "not_found", "Route not found")
            return
        owner_token = self.headers.get("X-Owner-Token", "")
        if not TOKEN_PATTERN.fullmatch(owner_token):
            self._error(403, "forbidden", "The signal owner token is required")
            return
        timestamp = _timestamp()
        with _connect(self.server.db_path) as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT owner_token_hash, status FROM signals WHERE id_hash = ?", (signal_id,)).fetchone()
            if row is None:
                self._error(404, "not_found", "Signal not found")
                return
            if not hmac.compare_digest(_hash(owner_token), row["owner_token_hash"]):
                self._error(403, "forbidden", "The signal owner token is required")
                return
            if row["status"] != "open":
                self._error(409, "reserved", "A reserved offer cannot be withdrawn until the mission is resolved")
                return
            db.execute("UPDATE signals SET status = 'withdrawn' WHERE id_hash = ?", (signal_id,))
            db.execute("INSERT INTO signal_events (id_hash, event, created_at) VALUES (?, 'withdrawn', ?)", (signal_id, timestamp))
        self._json(200, {"id": signal_id, "status": "withdrawn", "withdrawnAt": timestamp})

    def do_PUT(self) -> None:
        if not self._allowed_origin():
            return
        path, query = self._path()
        match = self._mission_path(path)
        if not match or match[1] or query:
            self._error(404, "not_found", "Route not found")
            return
        mission_id = match[0]
        edit_token = self.headers.get("X-Edit-Token", "")
        if not TOKEN_PATTERN.fullmatch(edit_token):
            self._error(403, "forbidden", "An edit token is required")
            return
        body = self._read_json()
        if body is None:
            return
        try:
            _exact_keys(body, {"state", "version"}, "request")
            state = validate_state(body["state"])
            version = body["version"]
            if type(version) is not int or version < 1:
                raise ValidationError("version must be a positive whole number")
        except ValidationError as error:
            self._error(422, "validation", str(error))
            return
        state_json = json.dumps(state, separators=(",", ":"), ensure_ascii=False, allow_nan=False)
        timestamp = _timestamp()
        id_hash = _hash(mission_id)
        with _connect(self.server.db_path) as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT edit_token_hash, version FROM missions WHERE id_hash = ?", (id_hash,)).fetchone()
            if row is None:
                self._error(404, "not_found", "Mission not found")
                return
            if not hmac.compare_digest(_hash(edit_token), row["edit_token_hash"]):
                self._error(403, "forbidden", "An edit token is required")
                return
            if version != row["version"]:
                self._error(409, "version_conflict", "This mission changed elsewhere; reload before saving")
                return
            next_version = version + 1
            db.execute(
                "UPDATE missions SET state_json = ?, version = ?, updated_at = ? WHERE id_hash = ?",
                (state_json, next_version, timestamp, id_hash),
            )
            db.execute(
                "INSERT INTO revisions VALUES (?, ?, ?, ?)",
                (id_hash, next_version, state_json, timestamp),
            )
        self._json(200, {"id": mission_id, "version": next_version, "updatedAt": timestamp})


def main() -> None:
    parser = argparse.ArgumentParser(description="Run RIPPLE locally on 127.0.0.1 only")
    parser.add_argument("--port", type=int, default=4174, help="local HTTP port (default: 4174)")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB, help="SQLite database path")
    args = parser.parse_args()
    server = RippleServer(port=args.port, db_path=args.db)
    print(f"RIPPLE local server: http://127.0.0.1:{server.server_port}/")
    print(f"Mission database: {server.db_path}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
