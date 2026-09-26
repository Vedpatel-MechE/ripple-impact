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
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, unquote, urlsplit


ROOT = Path(__file__).resolve().parent
DEFAULT_DB = ROOT / "ripple.sqlite3"
MAX_BODY = 32 * 1024
STATIC_FILES = {
    "/": ("index.html", "text/html; charset=utf-8"),
    "/index.html": ("index.html", "text/html; charset=utf-8"),
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
            """
        )


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
            self._json(200, {"ok": True, "mode": "local"})
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
        if path != "/api/missions" or query:
            self._error(404, "not_found", "Route not found")
            return
        body = self._read_json()
        if body is None:
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
