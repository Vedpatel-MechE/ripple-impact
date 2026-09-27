"""RIPPLE's local-only mission API and static preview server.

This stores user-entered drafts, not verified partners, funds, or outcomes.
Run with ``python3 server.py`` and open http://127.0.0.1:4174/.
"""

from __future__ import annotations

import argparse
from copy import deepcopy
from decimal import Decimal, InvalidOperation
import hashlib
import hmac
import json
import math
import os
from pathlib import Path
import re
import secrets
import sqlite3
import time
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from http.cookies import SimpleCookie
from urllib.parse import parse_qs, quote, unquote, urlsplit

from ripple_database import backend_name, connect as database_connect, is_postgres_target


ROOT = Path(__file__).resolve().parent
DEFAULT_DB = ROOT / "ripple.sqlite3"
DATABASE_URL = os.environ.get("DATABASE_URL", "").strip()
IS_VERCEL = os.environ.get("VERCEL") == "1"
MAX_BODY = 32 * 1024
MAX_OPEN_SIGNALS = 500
STATIC_FILES = {
    "/": ("login.html", "text/html; charset=utf-8"),
    "/login": ("login.html", "text/html; charset=utf-8"),
    "/home": ("network.html", "text/html; charset=utf-8"),
    "/admin": ("admin.html", "text/html; charset=utf-8"),
    "/smart-cart": ("smart-cart.html", "text/html; charset=utf-8"),
    "/circle": ("circle.html", "text/html; charset=utf-8"),
    "/company": ("company.html", "text/html; charset=utf-8"),
    "/recipient": ("recipient.html", "text/html; charset=utf-8"),
    "/repair": ("repair.html", "text/html; charset=utf-8"),
    "/fund": ("fund.html", "text/html; charset=utf-8"),
    "/missions": ("missions.html", "text/html; charset=utf-8"),
    "/mission": ("mission.html", "text/html; charset=utf-8"),
    "/transparency": ("transparency.html", "text/html; charset=utf-8"),
    "/company.html": ("company.html", "text/html; charset=utf-8"),
    "/recipient.html": ("recipient.html", "text/html; charset=utf-8"),
    "/repair.html": ("repair.html", "text/html; charset=utf-8"),
    "/fund.html": ("fund.html", "text/html; charset=utf-8"),
    "/missions.html": ("missions.html", "text/html; charset=utf-8"),
    "/mission.html": ("mission.html", "text/html; charset=utf-8"),
    "/transparency.html": ("transparency.html", "text/html; charset=utf-8"),
    "/index.html": ("index.html", "text/html; charset=utf-8"),
    "/planner": ("index.html", "text/html; charset=utf-8"),
    "/network": ("network.html", "text/html; charset=utf-8"),
    "/network.css": ("network.css", "text/css; charset=utf-8"),
    "/network.js": ("network.js", "text/javascript; charset=utf-8"),
    "/site.css": ("site.css", "text/css; charset=utf-8"),
    "/site.js": ("site.js", "text/javascript; charset=utf-8"),
    "/auth.js": ("auth.js", "text/javascript; charset=utf-8"),
    "/admin.js": ("admin.js", "text/javascript; charset=utf-8"),
    "/auth-guard.js": ("auth-guard.js", "text/javascript; charset=utf-8"),
    "/smart-cart.js": ("smart-cart.js", "text/javascript; charset=utf-8"),
    "/circle.js": ("circle.js", "text/javascript; charset=utf-8"),
    "/styles.css": ("styles.css", "text/css; charset=utf-8"),
    "/engine.js": ("engine.js", "text/javascript; charset=utf-8"),
    "/app.js": ("app.js", "text/javascript; charset=utf-8"),
}
PROTECTED_PAGES = {
    "/home", "/company", "/recipient", "/repair", "/fund", "/missions", "/smart-cart",
    "/mission", "/transparency", "/network", "/planner", "/index.html",
    "/company.html", "/recipient.html", "/repair.html", "/fund.html",
    "/missions.html", "/mission.html", "/transparency.html",
}
SESSION_COOKIE = "__Host-ripple_session" if IS_VERCEL else "ripple_session"
SESSION_HOURS = 12
AUTH_EMAIL_MAX = 254
AUTH_NAME_MAX = 80
AUTH_PASSWORD_MAX = 128
ADMIN_EMAIL = os.environ.get("RIPPLE_ADMIN_EMAIL", "" if IS_VERCEL else "admin@ripple.local").strip().lower()
ADMIN_PASSWORD = os.environ.get("RIPPLE_ADMIN_PASSWORD", "" if IS_VERCEL else "RippleAdmin!2026")
INQUIRY_STATUSES = {"submitted", "reviewing", "needs-information", "approved", "declined"}
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

# These are deliberately fictional walkthroughs, not completed projects or
# evidence that money or equipment moved.  Keeping the sample flag on every
# record lets the UI remain honest while still demonstrating the full product.
IMPACT_MISSIONS = {
    "south-atlanta-laptop-lab": {
        "id": "south-atlanta-laptop-lab",
        "sample": True,
        "status": "sample-planning",
        "title": "A take-home laptop lab for South Atlanta students",
        "summary": "An illustrative mission showing how retired business laptops could become learning-ready devices.",
        "location": "Atlanta, GA",
        "device": {"type": "laptops", "quantity": 60, "condition": "Mixed; inspection required"},
        "source": {"name": "Sample technology employer", "commitment": "60 retired laptops proposed"},
        "recipient": {"name": "Sample public high school", "type": "Public school", "need": "Take-home coursework and digital projects"},
        "repair": {
            "partner": "Sample local refurbisher",
            "scope": ["Inventory", "NIST-aligned data sanitization", "Battery and hardware checks", "Operating-system setup"],
            "estimatedDays": 14,
        },
        "funding": {
            "goal": 7200,
            "currency": "USD",
            "covers": ["Paid technician labor", "Replacement parts", "Chargers", "Packing and delivery"],
        },
        "plannedOutcome": {"devices": 60, "label": "Planned devices—not delivered impact"},
        "stages": ["Asset confirmation", "Recipient acceptance", "Activation funding", "Repair and QA", "Delivery evidence"],
    },
    "clayton-tablet-library": {
        "id": "clayton-tablet-library",
        "sample": True,
        "status": "sample-planning",
        "title": "Tablets for an after-school learning library",
        "summary": "An illustrative mission for activating a smaller batch of repairable tablets for supervised student use.",
        "location": "Clayton County, GA",
        "device": {"type": "tablets", "quantity": 40, "condition": "Used; lock and battery checks required"},
        "source": {"name": "Sample regional company", "commitment": "40 retired tablets proposed"},
        "recipient": {"name": "Sample youth charity", "type": "Nonprofit", "need": "After-school reading and tutoring sessions"},
        "repair": {
            "partner": "Sample mobile-device repair cooperative",
            "scope": ["Activation-lock screening", "Secure reset", "Battery checks", "Protective-case installation"],
            "estimatedDays": 10,
        },
        "funding": {
            "goal": 4400,
            "currency": "USD",
            "covers": ["Paid technician labor", "Batteries", "Protective cases", "Local delivery"],
        },
        "plannedOutcome": {"devices": 40, "label": "Planned devices—not delivered impact"},
        "stages": ["Asset confirmation", "Recipient acceptance", "Activation funding", "Repair and QA", "Delivery evidence"],
    },
    "westside-desktop-classroom": {
        "id": "westside-desktop-classroom",
        "sample": True,
        "status": "sample-planning",
        "title": "A refurbished desktop classroom for a community program",
        "summary": "An illustrative mission combining desktops and monitors into complete learning stations.",
        "location": "Westside Atlanta, GA",
        "device": {"type": "desktop-and-monitor sets", "quantity": 25, "condition": "Used; component testing required"},
        "source": {"name": "Sample professional-services firm", "commitment": "25 desktop and monitor sets proposed"},
        "recipient": {"name": "Sample workforce charity", "type": "Nonprofit", "need": "Digital-skills classes for young adults"},
        "repair": {
            "partner": "Sample electronics reuse workshop",
            "scope": ["Drive sanitization", "Memory and storage tests", "Peripheral matching", "Accessibility-ready setup"],
            "estimatedDays": 18,
        },
        "funding": {
            "goal": 3750,
            "currency": "USD",
            "covers": ["Paid technician labor", "Storage replacements", "Keyboards and mice", "Transportation"],
        },
        "plannedOutcome": {"devices": 25, "label": "Planned stations—not delivered impact"},
        "stages": ["Asset confirmation", "Recipient acceptance", "Activation funding", "Repair and QA", "Delivery evidence"],
    },
}

INTAKE_KINDS = {"company", "recipient", "repairer"}
DEVICE_TYPES = {"laptops", "tablets", "desktops", "monitors", "mixed"}
COMPANY_CONDITIONS = {"working", "mixed", "repair-needed", "unknown"}
RECIPIENT_TYPES = {"public-school", "school-district", "nonprofit", "library", "community-program"}
REPAIR_SERVICES = {"data-wiping", "diagnostics", "hardware-repair", "configuration", "delivery", "recycling"}
MAX_ROLE_INTAKES = 2_000
MAX_SIMULATED_PLEDGES = 10_000
MAX_SMART_CARTS = 1_000
MAX_CIRCLE_CONTRIBUTIONS = 10_000
SMART_CART_PRIORITIES = {"impact", "affordability", "speed", "reliability"}
SMART_CART_PACKAGES = {"starter", "balanced", "resilient"}
EMAIL_PATTERN = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")


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


def _future_timestamp(*, hours: int) -> str:
    return (datetime.now(timezone.utc) + timedelta(hours=hours)).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _password_hash(password: str, salt_hex: str) -> str:
    return hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), bytes.fromhex(salt_hex), 260_000
    ).hex()


def _new_password_record(password: str) -> tuple[str, str]:
    salt = secrets.token_hex(16)
    return salt, _password_hash(password, salt)


def _password_matches(password: str, salt_hex: str, expected_hash: str) -> bool:
    return hmac.compare_digest(_password_hash(password, salt_hex), expected_hash)


def validate_auth_email(value: object) -> str:
    if type(value) is not str:
        raise ValidationError("email must be a valid email address")
    email = value.strip().lower()
    if len(email) > AUTH_EMAIL_MAX or not EMAIL_PATTERN.fullmatch(email):
        raise ValidationError("email must be a valid email address")
    return email


def validate_auth_password(value: object) -> str:
    if type(value) is not str or not 10 <= len(value) <= AUTH_PASSWORD_MAX:
        raise ValidationError("password must contain 10 to 128 characters")
    if not any(character.isalpha() for character in value) or not any(character.isdigit() for character in value):
        raise ValidationError("password must include at least one letter and one number")
    return value


def validate_display_name(value: object) -> str:
    if type(value) is not str:
        raise ValidationError("displayName must be text")
    cleaned = value.strip()
    if not cleaned or len(cleaned) > AUTH_NAME_MAX or any(ord(character) < 32 for character in cleaned):
        raise ValidationError(f"displayName must contain 1 to {AUTH_NAME_MAX} visible characters")
    return cleaned


def _connect(db_target: Path | str):
    return database_connect(db_target)


def _initialize_sqlite_database(db_path: Path) -> None:
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
            CREATE TABLE IF NOT EXISTS users (
                id TEXT PRIMARY KEY,
                email TEXT NOT NULL UNIQUE,
                display_name TEXT NOT NULL,
                password_salt TEXT NOT NULL,
                password_hash TEXT NOT NULL,
                role TEXT NOT NULL CHECK (role IN ('participant', 'admin')),
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS sessions (
                token_hash TEXT PRIMARY KEY,
                user_id TEXT NOT NULL REFERENCES users(id),
                csrf_token TEXT NOT NULL,
                created_at TEXT NOT NULL,
                expires_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS auth_events (
                event_id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT NOT NULL REFERENCES users(id),
                event TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS smart_carts (
                id TEXT PRIMARY KEY,
                creator_user_id TEXT NOT NULL REFERENCES users(id),
                mission_slug TEXT NOT NULL,
                group_name TEXT NOT NULL,
                creator_statement TEXT NOT NULL,
                priority TEXT NOT NULL CHECK (priority IN ('impact', 'affordability', 'speed', 'reliability')),
                package_type TEXT NOT NULL CHECK (package_type IN ('starter', 'balanced', 'resilient')),
                package_json TEXT NOT NULL,
                goal_cents INTEGER NOT NULL CHECK (goal_cents BETWEEN 10000 AND 5000000),
                status TEXT NOT NULL DEFAULT 'open' CHECK (status IN ('open', 'funded', 'closed')),
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS circle_contributions (
                id TEXT PRIMARY KEY,
                cart_id TEXT NOT NULL REFERENCES smart_carts(id),
                display_name TEXT NOT NULL,
                anonymous INTEGER NOT NULL CHECK (anonymous IN (0, 1)),
                amount_cents INTEGER NOT NULL CHECK (amount_cents BETWEEN 100 AND 5000000),
                message TEXT NOT NULL DEFAULT '',
                payment_status TEXT NOT NULL CHECK (payment_status = 'sandbox-authorized'),
                gateway_reference TEXT NOT NULL UNIQUE,
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS smart_cart_events (
                event_id INTEGER PRIMARY KEY AUTOINCREMENT,
                cart_id TEXT NOT NULL REFERENCES smart_carts(id),
                event TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS role_intakes (
                id TEXT PRIMARY KEY,
                kind TEXT NOT NULL CHECK (kind IN ('company', 'recipient', 'repairer')),
                payload_json TEXT NOT NULL,
                verification_status TEXT NOT NULL DEFAULT 'unverified'
                    CHECK (verification_status = 'unverified'),
                created_at TEXT NOT NULL,
                user_id TEXT REFERENCES users(id),
                workflow_status TEXT NOT NULL DEFAULT 'submitted'
                    CHECK (workflow_status IN ('submitted', 'reviewing', 'needs-information', 'approved', 'declined')),
                review_notes TEXT NOT NULL DEFAULT '',
                updated_at TEXT NOT NULL DEFAULT ''
            );
            CREATE TABLE IF NOT EXISTS intake_events (
                event_id INTEGER PRIMARY KEY AUTOINCREMENT,
                intake_id TEXT NOT NULL REFERENCES role_intakes(id),
                event TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS simulated_pledges (
                id TEXT PRIMARY KEY,
                mission_slug TEXT NOT NULL,
                amount_cents INTEGER NOT NULL CHECK (amount_cents BETWEEN 100 AND 10000000),
                display_name TEXT NOT NULL,
                anonymous INTEGER NOT NULL CHECK (anonymous IN (0, 1)),
                status TEXT NOT NULL DEFAULT 'simulated' CHECK (status = 'simulated'),
                created_at TEXT NOT NULL,
                user_id TEXT REFERENCES users(id)
            );
            CREATE TABLE IF NOT EXISTS pledge_events (
                event_id INTEGER PRIMARY KEY AUTOINCREMENT,
                pledge_id TEXT NOT NULL REFERENCES simulated_pledges(id),
                event TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS request_limits (
                key_hash TEXT PRIMARY KEY,
                event_count INTEGER NOT NULL CHECK (event_count >= 1),
                window_started INTEGER NOT NULL
            );
            CREATE TRIGGER IF NOT EXISTS intake_events_no_update
            BEFORE UPDATE ON intake_events BEGIN
                SELECT RAISE(ABORT, 'intake events are immutable');
            END;
            CREATE TRIGGER IF NOT EXISTS intake_events_no_delete
            BEFORE DELETE ON intake_events BEGIN
                SELECT RAISE(ABORT, 'intake events are immutable');
            END;
            CREATE TRIGGER IF NOT EXISTS pledge_events_no_update
            BEFORE UPDATE ON pledge_events BEGIN
                SELECT RAISE(ABORT, 'pledge events are immutable');
            END;
            CREATE TRIGGER IF NOT EXISTS pledge_events_no_delete
            BEFORE DELETE ON pledge_events BEGIN
                SELECT RAISE(ABORT, 'pledge events are immutable');
            END;
            CREATE TRIGGER IF NOT EXISTS auth_events_no_update
            BEFORE UPDATE ON auth_events BEGIN
                SELECT RAISE(ABORT, 'auth events are immutable');
            END;
            CREATE TRIGGER IF NOT EXISTS auth_events_no_delete
            BEFORE DELETE ON auth_events BEGIN
                SELECT RAISE(ABORT, 'auth events are immutable');
            END;
            CREATE TRIGGER IF NOT EXISTS smart_cart_events_no_update
            BEFORE UPDATE ON smart_cart_events BEGIN
                SELECT RAISE(ABORT, 'smart cart events are immutable');
            END;
            CREATE TRIGGER IF NOT EXISTS smart_cart_events_no_delete
            BEFORE DELETE ON smart_cart_events BEGIN
                SELECT RAISE(ABORT, 'smart cart events are immutable');
            END;
            """
        )
        assembly_columns = {row["name"] for row in db.execute("PRAGMA table_info(assemblies)").fetchall()}
        if "expires_at" not in assembly_columns:
            db.execute("ALTER TABLE assemblies ADD COLUMN expires_at TEXT NOT NULL DEFAULT ''")
        if "expired" not in assembly_columns:
            db.execute("ALTER TABLE assemblies ADD COLUMN expired INTEGER NOT NULL DEFAULT 0 CHECK (expired IN (0, 1))")
        intake_columns = {row["name"] for row in db.execute("PRAGMA table_info(role_intakes)").fetchall()}
        if "user_id" not in intake_columns:
            db.execute("ALTER TABLE role_intakes ADD COLUMN user_id TEXT REFERENCES users(id)")
        if "workflow_status" not in intake_columns:
            db.execute("ALTER TABLE role_intakes ADD COLUMN workflow_status TEXT NOT NULL DEFAULT 'submitted'")
        if "review_notes" not in intake_columns:
            db.execute("ALTER TABLE role_intakes ADD COLUMN review_notes TEXT NOT NULL DEFAULT ''")
        if "updated_at" not in intake_columns:
            db.execute("ALTER TABLE role_intakes ADD COLUMN updated_at TEXT NOT NULL DEFAULT ''")
        pledge_columns = {row["name"] for row in db.execute("PRAGMA table_info(simulated_pledges)").fetchall()}
        if "user_id" not in pledge_columns:
            db.execute("ALTER TABLE simulated_pledges ADD COLUMN user_id TEXT REFERENCES users(id)")
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
        _ensure_admin(db)


def _ensure_admin(db) -> None:
    if not ADMIN_EMAIL or not ADMIN_PASSWORD:
        return
    try:
        email = validate_auth_email(ADMIN_EMAIL)
        password = validate_auth_password(ADMIN_PASSWORD)
    except ValidationError as error:
        raise RuntimeError(f"Invalid RIPPLE administrator environment configuration: {error}") from error
    existing = db.execute(
        "SELECT id, password_salt, password_hash, role FROM users WHERE email = ?", (email,)
    ).fetchone()
    if existing is not None and _password_matches(password, existing["password_salt"], existing["password_hash"]):
        if existing["role"] != "admin":
            db.execute("UPDATE users SET role = 'admin' WHERE id = ?", (existing["id"],))
        return
    admin_salt, admin_hash = _new_password_record(password)
    if existing is None:
        db.execute(
            "INSERT INTO users (id, email, display_name, password_salt, password_hash, role, created_at) "
            "VALUES (?, ?, 'RIPPLE Admin', ?, ?, 'admin', ?)",
            (secrets.token_urlsafe(18), email, admin_salt, admin_hash, _timestamp()),
        )
    else:
        db.execute(
            "UPDATE users SET password_salt = ?, password_hash = ?, role = 'admin' WHERE id = ?",
            (admin_salt, admin_hash, existing["id"]),
        )


def _initialize_postgres_database(database_url: str) -> None:
    schema = (ROOT / "schema_postgres.sql").read_text(encoding="utf-8")
    with _connect(database_url) as db:
        db.execute("SELECT pg_advisory_xact_lock(hashtext('ripple-schema-v1'))")
        db.executescript(schema)
        _ensure_admin(db)


def initialize_database(db_target: Path | str) -> None:
    if is_postgres_target(db_target):
        _initialize_postgres_database(str(db_target))
        return
    _initialize_sqlite_database(Path(db_target))


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


def _validated_text(payload: dict, key: str, maximum: int, *, allow_blank: bool = False) -> str:
    value = payload[key]
    if type(value) is not str or len(value) > maximum or any(ord(char) < 32 and char not in "\t\n" for char in value):
        raise ValidationError(f"{key} must be text of at most {maximum} characters")
    cleaned = value.strip()
    if not allow_blank and not cleaned:
        raise ValidationError(f"{key} cannot be blank")
    return cleaned


def _validated_int(payload: dict, key: str, minimum: int, maximum: int) -> int:
    value = payload[key]
    if type(value) is not int or not minimum <= value <= maximum:
        raise ValidationError(f"{key} must be a whole number from {minimum} to {maximum}")
    return value


def _validated_choice(payload: dict, key: str, choices: set[str]) -> str:
    value = payload[key]
    if type(value) is not str or value not in choices:
        raise ValidationError(f"{key} must be one of: {', '.join(sorted(choices))}")
    return value


def _validated_choices(payload: dict, key: str, choices: set[str]) -> list[str]:
    value = payload[key]
    if type(value) is not list or not value or len(value) > len(choices):
        raise ValidationError(f"{key} must be a nonempty list")
    if any(type(item) is not str or item not in choices for item in value):
        raise ValidationError(f"{key} contains an unsupported choice")
    if len(set(value)) != len(value):
        raise ValidationError(f"{key} cannot contain duplicates")
    return value


def validate_intake(kind: object, value: object) -> tuple[str, dict]:
    """Validate one of the three deliberately narrow pilot intake contracts."""
    if type(kind) is not str or kind not in INTAKE_KINDS:
        raise ValidationError("kind must be company, recipient, or repairer")
    common = {"organizationName", "contactName", "email", "location", "notes"}
    fields = {
        "company": common | {"deviceType", "quantity", "condition", "availabilityWindow"},
        "recipient": common | {"organizationType", "deviceType", "quantity", "studentCount", "useCase", "deadline"},
        "repairer": common | {"specialties", "monthlyCapacity", "turnaroundDays", "services"},
    }[kind]
    payload = _exact_keys(value, fields, f"{kind} payload")
    normalized = {
        "organizationName": _validated_text(payload, "organizationName", 120),
        "contactName": _validated_text(payload, "contactName", 90),
        "email": _validated_text(payload, "email", 254),
        "location": _validated_text(payload, "location", 120),
        "notes": _validated_text(payload, "notes", 600, allow_blank=True),
    }
    if not EMAIL_PATTERN.fullmatch(normalized["email"]):
        raise ValidationError("email must be a valid email address")
    if kind == "company":
        normalized.update({
            "deviceType": _validated_choice(payload, "deviceType", DEVICE_TYPES),
            "quantity": _validated_int(payload, "quantity", 1, 100_000),
            "condition": _validated_choice(payload, "condition", COMPANY_CONDITIONS),
            "availabilityWindow": _validated_text(payload, "availabilityWindow", 120),
        })
    elif kind == "recipient":
        normalized.update({
            "organizationType": _validated_choice(payload, "organizationType", RECIPIENT_TYPES),
            "deviceType": _validated_choice(payload, "deviceType", DEVICE_TYPES),
            "quantity": _validated_int(payload, "quantity", 1, 100_000),
            "studentCount": _validated_int(payload, "studentCount", 1, 1_000_000),
            "useCase": _validated_text(payload, "useCase", 500),
            "deadline": _validated_text(payload, "deadline", 120),
        })
    else:
        normalized.update({
            "specialties": _validated_choices(payload, "specialties", DEVICE_TYPES),
            "monthlyCapacity": _validated_int(payload, "monthlyCapacity", 1, 100_000),
            "turnaroundDays": _validated_int(payload, "turnaroundDays", 1, 365),
            "services": _validated_choices(payload, "services", REPAIR_SERVICES),
        })
    return kind, normalized


def validate_pledge(value: object) -> dict:
    pledge = _exact_keys(value, {"missionId", "amount", "displayName", "anonymous"}, "request")
    mission_id = pledge["missionId"]
    if type(mission_id) is not str or mission_id not in IMPACT_MISSIONS:
        raise ValidationError("missionId must identify an available sample mission")
    if type(pledge["anonymous"]) is not bool:
        raise ValidationError("anonymous must be true or false")
    display_name = _validated_text(pledge, "displayName", 60, allow_blank=pledge["anonymous"])
    amount = pledge["amount"]
    if type(amount) not in (int, float) or not math.isfinite(amount):
        raise ValidationError("amount must be a finite number from 1 to 100000 with at most two decimal places")
    try:
        decimal_amount = Decimal(str(amount))
        cents = int(decimal_amount * 100)
    except (InvalidOperation, ValueError, OverflowError):
        raise ValidationError("amount must be a finite number from 1 to 100000 with at most two decimal places")
    if decimal_amount < Decimal("1") or decimal_amount > Decimal("100000") or Decimal(cents) / 100 != decimal_amount:
        raise ValidationError("amount must be a finite number from 1 to 100000 with at most two decimal places")
    return {
        "missionId": mission_id,
        "amountCents": cents,
        "displayName": display_name,
        "anonymous": pledge["anonymous"],
    }


def _pledge_totals(db: sqlite3.Connection) -> dict[str, dict[str, int]]:
    totals = {mission_id: {"count": 0, "cents": 0} for mission_id in IMPACT_MISSIONS}
    rows = db.execute(
        "SELECT mission_slug, COUNT(*) AS pledge_count, COALESCE(SUM(amount_cents), 0) AS pledged_cents "
        "FROM simulated_pledges GROUP BY mission_slug"
    ).fetchall()
    for row in rows:
        if row["mission_slug"] in totals:
            totals[row["mission_slug"]] = {"count": row["pledge_count"], "cents": row["pledged_cents"]}
    return totals


def _impact_mission(mission_id: str, totals: dict[str, dict[str, int]]) -> dict:
    mission = deepcopy(IMPACT_MISSIONS[mission_id])
    activity = totals[mission_id]
    goal_cents = mission["funding"]["goal"] * 100
    pledged_cents = activity["cents"]
    mission["funding"].update({
        "simulatedPledged": pledged_cents / 100,
        "simulatedPledgeCount": activity["count"],
        "remaining": max(0, goal_cents - pledged_cents) / 100,
        "progressPercent": round(min(100, pledged_cents * 100 / goal_cents), 1),
        "activityStatus": "simulation-only",
    })
    return mission


def _impact_summary(mission: dict) -> dict:
    return {key: mission[key] for key in ("id", "sample", "status", "title", "summary", "location", "device", "recipient", "funding", "plannedOutcome")}


def _public_user(row: sqlite3.Row | dict) -> dict:
    return {
        "id": row["id"],
        "email": row["email"],
        "displayName": row["display_name"],
        "role": row["role"],
    }


def _intake_summary(kind: str, payload: dict) -> str:
    if kind == "company":
        return f"{payload['quantity']} {payload['deviceType']} in {payload['location']}"
    if kind == "recipient":
        return f"{payload['quantity']} {payload['deviceType']} requested in {payload['location']}"
    return f"{payload['monthlyCapacity']} devices/month capacity in {payload['location']}"


def validate_smart_cart_request(value: object, *, include_package: bool) -> dict:
    expected = {"missionId", "budget", "groupSize", "priority", "prompt"}
    if include_package:
        expected |= {"packageType", "groupName", "creatorStatement"}
    request = _exact_keys(value, expected, "request")
    mission_id = request["missionId"]
    if type(mission_id) is not str or mission_id not in IMPACT_MISSIONS:
        raise ValidationError("missionId must identify an available sample mission")
    budget = request["budget"]
    if type(budget) not in (int, float) or isinstance(budget, bool) or not math.isfinite(budget) or not 250 <= budget <= 25_000:
        raise ValidationError("budget must be a number from 250 to 25000")
    if Decimal(str(budget)).quantize(Decimal("0.01")) != Decimal(str(budget)):
        raise ValidationError("budget can have at most two decimal places")
    group_size = request["groupSize"]
    if type(group_size) is not int or not 2 <= group_size <= 50:
        raise ValidationError("groupSize must be a whole number from 2 to 50")
    priority = request["priority"]
    if type(priority) is not str or priority not in SMART_CART_PRIORITIES:
        raise ValidationError("priority must be impact, affordability, speed, or reliability")
    prompt = request["prompt"]
    if type(prompt) is not str or not 10 <= len(prompt.strip()) <= 500 or any(ord(char) < 32 and char not in "\t\n" for char in prompt):
        raise ValidationError("prompt must contain 10 to 500 visible characters")
    normalized = {
        "missionId": mission_id,
        "budgetCents": int(Decimal(str(budget)) * 100),
        "groupSize": group_size,
        "priority": priority,
        "prompt": prompt.strip(),
    }
    if include_package:
        package_type = request["packageType"]
        if type(package_type) is not str or package_type not in SMART_CART_PACKAGES:
            raise ValidationError("packageType must be starter, balanced, or resilient")
        normalized.update({
            "packageType": package_type,
            "groupName": _validated_text(request, "groupName", 80),
            "creatorStatement": _validated_text(request, "creatorStatement", 280, allow_blank=True),
        })
    return normalized


def _money_breakdown(total_cents: int, package_type: str) -> list[dict]:
    ratios = {
        "starter": [("Diagnostics + secure wiping", 28), ("Repair labor", 34), ("Parts + chargers", 23), ("Delivery", 10), ("QA evidence", 5)],
        "balanced": [("Diagnostics + secure wiping", 22), ("Repair labor", 32), ("Parts + chargers", 31), ("Delivery", 10), ("QA evidence", 5)],
        "resilient": [("Diagnostics + secure wiping", 18), ("Repair labor", 28), ("Batteries + reliability parts", 39), ("Protected delivery", 9), ("QA + contingency", 6)],
    }[package_type]
    lines = []
    assigned = 0
    for index, (label, percent) in enumerate(ratios):
        amount = total_cents - assigned if index == len(ratios) - 1 else round(total_cents * percent / 100)
        assigned += amount
        lines.append({"label": label, "amount": amount / 100, "amountCents": amount})
    return lines


def _smart_cart_options(request: dict) -> list[dict]:
    mission = IMPACT_MISSIONS[request["missionId"]]
    maximum_devices = mission["device"]["quantity"]
    base_cents = round(mission["funding"]["goal"] * 100 / maximum_devices)
    budget_cents = request["budgetCents"]
    profiles = {
        "starter": {"title": "Start the ripple", "share": 0.62, "multiplier": 0.9, "tag": "Lowest group commitment"},
        "balanced": {"title": "Complete the strongest package", "share": 0.94, "multiplier": 1.0, "tag": "Recommended"},
        "resilient": {"title": "Build for longer use", "share": 0.98, "multiplier": 1.18, "tag": "Reliability first"},
    }
    preference = request["priority"]
    preference_copy = {
        "impact": "maximizes usable devices within the group budget",
        "affordability": "keeps the contribution per person easy to join",
        "speed": "funds a compact scope that can move through repair quickly",
        "reliability": "adds more room for batteries, parts, and quality assurance",
    }[preference]
    options = []
    for package_type in ("starter", "balanced", "resilient"):
        profile = profiles[package_type]
        per_device = round(base_cents * profile["multiplier"])
        working_budget = round(budget_cents * profile["share"])
        devices = max(1, min(maximum_devices, working_budget // per_device))
        total_cents = min(budget_cents, max(25_000, devices * per_device))
        per_person_cents = math.ceil(total_cents / request["groupSize"])
        options.append({
            "type": package_type,
            "title": profile["title"],
            "tag": profile["tag"],
            "targetDevices": devices,
            "goal": total_cents / 100,
            "goalCents": total_cents,
            "perPerson": per_person_cents / 100,
            "breakdown": _money_breakdown(total_cents, package_type),
            "explanation": f"This option {preference_copy}. It plans for {devices} {mission['device']['type']} and an average contribution of ${per_person_cents / 100:,.2f} across {request['groupSize']} friends.",
            "assumptions": "Planning estimate based on the sample mission budget; final scope still requires partner approval.",
        })
    return options


def _circle_public(db: sqlite3.Connection, row: sqlite3.Row) -> dict:
    package = json.loads(row["package_json"])
    mission = IMPACT_MISSIONS[row["mission_slug"]]
    contributions = db.execute(
        "SELECT display_name, anonymous, amount_cents, message, created_at FROM circle_contributions "
        "WHERE cart_id = ? AND payment_status = 'sandbox-authorized' ORDER BY created_at",
        (row["id"],),
    ).fetchall()
    raised_cents = sum(item["amount_cents"] for item in contributions)
    remaining_cents = max(0, row["goal_cents"] - raised_cents)
    creator = db.execute("SELECT display_name FROM users WHERE id = ?", (row["creator_user_id"],)).fetchone()
    contributor_count = len(contributions)
    creator_name = creator["display_name"] if creator else "A RIPPLE member"
    public_contributors = [{
        "displayName": "Anonymous friend" if item["anonymous"] else item["display_name"],
        "amount": item["amount_cents"] / 100,
        "message": item["message"],
        "createdAt": item["created_at"],
    } for item in contributions]
    if contributor_count:
        social_headline = f"{creator_name} and {contributor_count} friend{'s' if contributor_count != 1 else ''} have contributed ${raised_cents / 100:,.0f} toward {package['targetDevices']} student-ready devices."
    else:
        social_headline = f"{creator_name} started a circle to activate {package['targetDevices']} student-ready devices."
    motivations = [item["message"] for item in public_contributors if item["message"]][:3]
    group_story = social_headline
    if motivations:
        group_story += " The group is coming together around " + "; ".join(motivation.rstrip(".") for motivation in motivations) + "."
    return {
        "id": row["id"], "groupName": row["group_name"], "creatorName": creator_name,
        "creatorStatement": row["creator_statement"], "priority": row["priority"],
        "status": row["status"], "sample": True, "mission": _impact_summary(_impact_mission(row["mission_slug"], _pledge_totals(db))),
        "package": package, "goal": row["goal_cents"] / 100, "raised": raised_cents / 100,
        "remaining": remaining_cents / 100, "progressPercent": round(min(100, raised_cents * 100 / row["goal_cents"]), 1),
        "contributorCount": contributor_count, "contributors": public_contributors,
        "socialHeadline": social_headline, "groupStory": group_story,
        "createdAt": row["created_at"], "updatedAt": row["updated_at"],
        "paymentMode": "visa-sandbox-simulation", "paymentProcessed": False,
    }


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

    def __init__(self, port: int = 4174, db_path: Path | str | None = None):
        selected = db_path if db_path is not None else (DATABASE_URL or DEFAULT_DB)
        self.db_path = str(selected) if is_postgres_target(selected) else Path(selected).resolve()
        initialize_database(self.db_path)
        super().__init__(("127.0.0.1", port), RippleHandler)


class RippleHandler(BaseHTTPRequestHandler):
    server: RippleServer
    protocol_version = "HTTP/1.1"

    def log_message(self, format: str, *args: object) -> None:
        # GET view tokens travel in query strings; never print request lines.
        pass

    def _headers(self, status: int, content_type: str, content_length: int, extra_headers: dict[str, str] | None = None) -> None:
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
        for name, value in (extra_headers or {}).items():
            self.send_header(name, value)
        self.end_headers()

    def _json(self, status: int, payload: dict, extra_headers: dict[str, str] | None = None) -> None:
        body = json.dumps(payload, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
        self._headers(status, "application/json; charset=utf-8", len(body), extra_headers)
        self.wfile.write(body)

    def _error(self, status: int, code: str, message: str) -> None:
        self._json(status, {"error": code, "message": message})

    def _redirect(self, location: str) -> None:
        body = b""
        self._headers(302, "text/plain; charset=utf-8", len(body), {"Location": location})

    def _cookie_token(self) -> str:
        raw = self.headers.get("Cookie", "")
        if not raw:
            return ""
        try:
            cookie = SimpleCookie(raw)
        except Exception:
            return ""
        morsel = cookie.get(SESSION_COOKIE)
        return morsel.value if morsel else ""

    def _session(self) -> dict | None:
        token = self._cookie_token()
        if not TOKEN_PATTERN.fullmatch(token):
            return None
        now = _timestamp()
        with _connect(self.server.db_path) as db:
            row = db.execute(
                "SELECT s.csrf_token, s.expires_at, u.* FROM sessions s "
                "JOIN users u ON u.id = s.user_id WHERE s.token_hash = ?",
                (_hash(token),),
            ).fetchone()
            if row is None or row["expires_at"] <= now:
                if row is not None:
                    db.execute("DELETE FROM sessions WHERE token_hash = ?", (_hash(token),))
                return None
        return {"user": _public_user(row), "csrfToken": row["csrf_token"], "expiresAt": row["expires_at"]}

    def _require_session(self, *, admin: bool = False, csrf: bool = False) -> dict | None:
        session = self._session()
        if session is None:
            self._error(401, "authentication_required", "Sign in to continue")
            return None
        if admin and session["user"]["role"] != "admin":
            self._error(403, "admin_required", "An administrator account is required")
            return None
        if csrf and not hmac.compare_digest(self.headers.get("X-CSRF-Token", ""), session["csrfToken"]):
            self._error(403, "csrf", "Refresh the page and try again")
            return None
        return session

    def _create_session(self, db: sqlite3.Connection, user_id: str, event: str) -> tuple[str, str, str]:
        token = secrets.token_urlsafe(32)
        csrf_token = secrets.token_urlsafe(24)
        created_at = _timestamp()
        expires_at = _future_timestamp(hours=SESSION_HOURS)
        db.execute(
            "INSERT INTO sessions (token_hash, user_id, csrf_token, created_at, expires_at) VALUES (?, ?, ?, ?, ?)",
            (_hash(token), user_id, csrf_token, created_at, expires_at),
        )
        db.execute(
            "INSERT INTO auth_events (user_id, event, created_at) VALUES (?, ?, ?)",
            (user_id, event, created_at),
        )
        return token, csrf_token, expires_at

    def _session_cookie(self, token: str, *, clear: bool = False) -> str:
        max_age = 0 if clear else SESSION_HOURS * 3600
        value = "" if clear else token
        secure = "; Secure" if IS_VERCEL or self.headers.get("X-Forwarded-Proto", "").split(",", 1)[0].strip() == "https" else ""
        return f"{SESSION_COOKIE}={value}; Path=/; HttpOnly; SameSite=Strict; Max-Age={max_age}{secure}"

    def _allowed_origins(self) -> set[str]:
        origins: set[str] = set()
        port = getattr(self.server, "server_port", 4174)
        origins.update({f"http://127.0.0.1:{port}", f"http://localhost:{port}"})
        configured = os.environ.get("RIPPLE_ALLOWED_ORIGINS", os.environ.get("RIPPLE_ALLOWED_ORIGIN", ""))
        for value in configured.split(","):
            candidate = value.strip().rstrip("/")
            if candidate.startswith("https://") or candidate.startswith("http://"):
                origins.add(candidate)
        for key in ("VERCEL_URL", "VERCEL_BRANCH_URL", "VERCEL_PROJECT_PRODUCTION_URL"):
            host = os.environ.get(key, "").strip().strip("/")
            if host:
                origins.add("https://" + host)
        return origins

    def _allowed_origin(self) -> bool:
        host = self.headers.get("Host", "").strip().lower()
        origins = self._allowed_origins()
        allowed_hosts = {urlsplit(origin).netloc.lower() for origin in origins}
        if host not in allowed_hosts:
            self._error(403, "bad_host", "This host is not configured for RIPPLE")
            return False
        origin = self.headers.get("Origin", "").strip().rstrip("/")
        if origin and origin not in origins:
            self._error(403, "bad_origin", "Cross-origin requests are not accepted")
            return False
        return True

    def _rate_limit(self, action: str, *, maximum: int, window_seconds: int = 600) -> bool:
        forwarded = self.headers.get("X-Forwarded-For", "").split(",", 1)[0].strip()
        address = forwarded or (self.client_address[0] if self.client_address else "unknown")
        key_hash = hashlib.sha256(f"{action}:{address}".encode("utf-8")).hexdigest()
        now = int(time.time())
        cutoff = now - window_seconds
        with _connect(self.server.db_path) as db:
            row = db.execute(
                "INSERT INTO request_limits (key_hash, event_count, window_started) VALUES (?, 1, ?) "
                "ON CONFLICT (key_hash) DO UPDATE SET "
                "event_count = CASE WHEN request_limits.window_started <= ? THEN 1 ELSE request_limits.event_count + 1 END, "
                "window_started = CASE WHEN request_limits.window_started <= ? THEN excluded.window_started ELSE request_limits.window_started END "
                "RETURNING event_count",
                (key_hash, now, cutoff, cutoff),
            ).fetchone()
        if row is not None and row["event_count"] > maximum:
            self._json(429, {"error": "rate_limit", "message": "Too many attempts. Wait a few minutes and try again."},
                       {"Retry-After": str(window_seconds)})
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
            self._error(413, "too_large", "Request JSON must be 32 KB or smaller")
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
            self._json(200, {"ok": True, "mode": "hosted" if IS_VERCEL else "local", "database": "ready", "matching": "ready"})
            return
        if path == "/api/auth/session" and not query:
            session = self._session()
            if session is None:
                self._json(200, {"authenticated": False})
            else:
                self._json(200, {"authenticated": True, **session})
            return
        if path == "/api/my/intakes" and not query:
            session = self._require_session()
            if session is None:
                return
            with _connect(self.server.db_path) as db:
                rows = db.execute(
                    "SELECT id, kind, workflow_status, verification_status, created_at, updated_at "
                    "FROM role_intakes WHERE user_id = ? ORDER BY created_at DESC",
                    (session["user"]["id"],),
                ).fetchall()
            self._json(200, {
                "inquiries": [{
                    "id": row["id"], "kind": row["kind"], "status": row["workflow_status"],
                    "verification": row["verification_status"], "createdAt": row["created_at"],
                    "updatedAt": row["updated_at"] or row["created_at"],
                } for row in rows]
            })
            return
        if path == "/api/admin/dashboard" and not query:
            session = self._require_session(admin=True)
            if session is None:
                return
            with _connect(self.server.db_path) as db:
                rows = db.execute(
                    "SELECT i.*, u.email, u.display_name FROM role_intakes i "
                    "LEFT JOIN users u ON u.id = i.user_id ORDER BY i.created_at DESC"
                ).fetchall()
                inquiries = []
                for row in rows:
                    payload = json.loads(row["payload_json"])
                    events = db.execute(
                        "SELECT event, created_at FROM intake_events WHERE intake_id = ? ORDER BY event_id",
                        (row["id"],),
                    ).fetchall()
                    inquiries.append({
                        "id": row["id"],
                        "kind": row["kind"],
                        "status": row["workflow_status"],
                        "verification": row["verification_status"],
                        "summary": _intake_summary(row["kind"], payload),
                        "organizationName": payload["organizationName"],
                        "contactName": payload["contactName"],
                        "email": payload["email"],
                        "location": payload["location"],
                        "payload": payload,
                        "reviewNotes": row["review_notes"],
                        "submittedBy": {
                            "displayName": row["display_name"] or "Legacy local submission",
                            "email": row["email"] or "Unavailable",
                        },
                        "createdAt": row["created_at"],
                        "updatedAt": row["updated_at"] or row["created_at"],
                        "events": [{"event": event["event"], "createdAt": event["created_at"]} for event in events],
                    })
                kind_counts = {kind: 0 for kind in sorted(INTAKE_KINDS)}
                status_counts = {status: 0 for status in sorted(INQUIRY_STATUSES)}
                for inquiry in inquiries:
                    kind_counts[inquiry["kind"]] += 1
                    status_counts[inquiry["status"]] += 1
                user_count = db.execute("SELECT COUNT(*) FROM users WHERE role = 'participant'").fetchone()[0]
            self._json(200, {
                "counts": {"total": len(inquiries), "byKind": kind_counts, "byStatus": status_counts, "participants": user_count},
                "inquiries": inquiries,
                "viewer": session["user"],
            })
            return
        smart_cart_match = re.fullmatch(r"/api/smart-carts/([^/]+)", path)
        if smart_cart_match and not query and SIGNAL_ID_PATTERN.fullmatch(smart_cart_match.group(1)):
            with _connect(self.server.db_path) as db:
                row = db.execute("SELECT * FROM smart_carts WHERE id = ?", (smart_cart_match.group(1),)).fetchone()
                if row is None:
                    self._error(404, "not_found", "Circle not found")
                    return
                circle = _circle_public(db, row)
            self._json(200, {
                "circle": circle,
                "notice": "Sandbox demonstration only. No card is charged and no charitable funds are collected or transferred.",
            })
            return
        if path == "/api/my/smart-carts" and not query:
            session = self._require_session()
            if session is None:
                return
            with _connect(self.server.db_path) as db:
                rows = db.execute(
                    "SELECT * FROM smart_carts WHERE creator_user_id = ? ORDER BY created_at DESC LIMIT 50",
                    (session["user"]["id"],),
                ).fetchall()
                circles = [_circle_public(db, row) for row in rows]
            self._json(200, {"circles": circles})
            return
        if path == "/api/platform" and not query:
            with _connect(self.server.db_path) as db:
                intake_counts = {"company": 0, "recipient": 0, "repairer": 0}
                for row in db.execute("SELECT kind, COUNT(*) AS count FROM role_intakes GROUP BY kind").fetchall():
                    intake_counts[row["kind"]] = row["count"]
                totals = _pledge_totals(db)
            missions = [_impact_mission(mission_id, totals) for mission_id in IMPACT_MISSIONS]
            pledge_count = sum(item["count"] for item in totals.values())
            pledge_cents = sum(item["cents"] for item in totals.values())
            self._json(200, {
                "sample": True,
                "notice": "Sample missions and simulated pledge activity for product demonstration. No donation was collected and no delivery or impact is claimed.",
                "missionSummaries": [_impact_summary(mission) for mission in missions],
                "counters": {
                    "intakesTotal": sum(intake_counts.values()),
                    "intakesByKind": intake_counts,
                    "simulatedPledgeCount": pledge_count,
                    "simulatedPledgeAmount": pledge_cents / 100,
                    "currency": "USD",
                },
                "intakeStatus": "User-submitted pilot inquiries; unverified and not public partner commitments.",
                "pledgeStatus": "Simulation only; no payment was requested, charged, collected, or transferred.",
            })
            return
        if path == "/api/impact-missions" and not query:
            with _connect(self.server.db_path) as db:
                totals = _pledge_totals(db)
            missions = [_impact_summary(_impact_mission(mission_id, totals)) for mission_id in IMPACT_MISSIONS]
            self._json(200, {
                "sample": True,
                "notice": "Fictional sample missions. Funding activity is simulated; no delivery or impact is claimed.",
                "missions": missions,
            })
            return
        mission_match = re.fullmatch(r"/api/impact-missions/([a-z0-9-]+)", path)
        if mission_match and not query:
            mission_id = mission_match.group(1)
            if mission_id not in IMPACT_MISSIONS:
                self._error(404, "not_found", "Sample impact mission not found")
                return
            with _connect(self.server.db_path) as db:
                totals = _pledge_totals(db)
            self._json(200, {
                "sample": True,
                "notice": "Fictional sample mission. Pledges are simulated; no money, equipment, delivery, or impact is claimed.",
                "mission": _impact_mission(mission_id, totals),
            })
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
        current_session = self._session()
        if path in ("/", "/login") and not query and current_session is not None:
            self._redirect("/admin" if current_session["user"]["role"] == "admin" else "/home")
            return
        if path == "/admin":
            if current_session is None:
                self._redirect("/?next=/admin")
                return
            if current_session["user"]["role"] != "admin":
                self._redirect("/home")
                return
        if path in PROTECTED_PAGES and current_session is None:
            destination = path
            if query:
                destination += "?" + urlsplit(self.path).query
            self._redirect("/?next=" + quote(destination, safe=""))
            return
        share_query = (
            path in ("/", "/index.html")
            and set(query) == {"mission", "view"}
            and len(query["mission"]) == 1
            and len(query["view"]) == 1
            and bool(ID_PATTERN.fullmatch(query["mission"][0]))
            and bool(TOKEN_PATTERN.fullmatch(query["view"][0]))
        )
        mission_query = (
            path in ("/mission", "/mission.html")
            and set(query) == {"mission"}
            and len(query["mission"]) == 1
            and bool(re.fullmatch(r"[a-z0-9-]{1,80}", query["mission"][0]))
        )
        login_query = path in ("/", "/login") and set(query) == {"next"} and len(query["next"]) == 1
        circle_query = (
            path == "/circle" and set(query) == {"id"} and len(query["id"]) == 1
            and bool(SIGNAL_ID_PATTERN.fullmatch(query["id"][0]))
        )
        if share_query and current_session is None:
            self._redirect("/?next=" + quote(self.path, safe=""))
            return
        if static and (not query or share_query or mission_query or login_query or circle_query):
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
        if path in {"/api/auth/register", "/api/auth/login"} and not self._rate_limit("auth", maximum=12):
            return
        if re.fullmatch(r"/api/smart-carts/[^/]+/checkout", path) and not self._rate_limit("circle-checkout", maximum=30):
            return
        body = self._read_json()
        if body is None:
            return
        if path == "/api/auth/register":
            try:
                _exact_keys(body, {"displayName", "email", "password"}, "request")
                display_name = validate_display_name(body["displayName"])
                email = validate_auth_email(body["email"])
                password = validate_auth_password(body["password"])
            except ValidationError as error:
                self._error(422, "validation", str(error))
                return
            user_id = secrets.token_urlsafe(18)
            salt, password_hash = _new_password_record(password)
            created_at = _timestamp()
            try:
                with _connect(self.server.db_path) as db:
                    db.execute("BEGIN IMMEDIATE")
                    db.execute(
                        "INSERT INTO users (id, email, display_name, password_salt, password_hash, role, created_at) "
                        "VALUES (?, ?, ?, ?, ?, 'participant', ?)",
                        (user_id, email, display_name, salt, password_hash, created_at),
                    )
                    token, csrf_token, expires_at = self._create_session(db, user_id, "registered")
            except sqlite3.IntegrityError:
                self._error(409, "account_exists", "An account already exists for this email address")
                return
            self._json(201, {
                "authenticated": True,
                "user": {"id": user_id, "email": email, "displayName": display_name, "role": "participant"},
                "csrfToken": csrf_token,
                "expiresAt": expires_at,
            }, {"Set-Cookie": self._session_cookie(token)})
            return
        if path == "/api/auth/login":
            try:
                _exact_keys(body, {"email", "password"}, "request")
                email = validate_auth_email(body["email"])
                password = body["password"]
                if type(password) is not str or not 1 <= len(password) <= AUTH_PASSWORD_MAX:
                    raise ValidationError("password is invalid")
            except ValidationError as error:
                self._error(422, "validation", str(error))
                return
            with _connect(self.server.db_path) as db:
                row = db.execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()
                if row is None:
                    dummy_salt = "0" * 32
                    _password_hash(password, dummy_salt)
                    valid = False
                else:
                    valid = hmac.compare_digest(_password_hash(password, row["password_salt"]), row["password_hash"])
                if not valid:
                    self._error(401, "invalid_credentials", "Email or password is incorrect")
                    return
                db.execute("BEGIN IMMEDIATE")
                db.execute("DELETE FROM sessions WHERE expires_at <= ? OR user_id = ?", (_timestamp(), row["id"]))
                token, csrf_token, expires_at = self._create_session(db, row["id"], "logged_in")
            self._json(200, {
                "authenticated": True,
                "user": _public_user(row),
                "csrfToken": csrf_token,
                "expiresAt": expires_at,
            }, {"Set-Cookie": self._session_cookie(token)})
            return
        if path == "/api/auth/logout":
            try:
                _exact_keys(body, set(), "request")
            except ValidationError as error:
                self._error(422, "validation", str(error))
                return
            session = self._require_session(csrf=True)
            if session is None:
                return
            with _connect(self.server.db_path) as db:
                db.execute("DELETE FROM sessions WHERE token_hash = ?", (_hash(self._cookie_token()),))
                db.execute(
                    "INSERT INTO auth_events (user_id, event, created_at) VALUES (?, 'logged_out', ?)",
                    (session["user"]["id"], _timestamp()),
                )
            self._json(200, {"authenticated": False}, {"Set-Cookie": self._session_cookie("", clear=True)})
            return
        if path == "/api/smart-cart/recommendations":
            session = self._require_session(csrf=True)
            if session is None:
                return
            try:
                request = validate_smart_cart_request(body, include_package=False)
            except ValidationError as error:
                self._error(422, "validation", str(error))
                return
            options = _smart_cart_options(request)
            mission = IMPACT_MISSIONS[request["missionId"]]
            self._json(200, {
                "options": options,
                "mission": {"id": mission["id"], "title": mission["title"], "location": mission["location"]},
                "brief": f"RIPPLE translated your group goal into three transparent ways to support {mission['title'].lower()}.",
                "planningMode": "local-ai-planning-simulation",
                "notice": "Prototype recommendations use sample mission data and a transparent local planning engine. Partner approval is still required.",
            })
            return
        if path == "/api/smart-carts":
            session = self._require_session(csrf=True)
            if session is None:
                return
            try:
                request = validate_smart_cart_request(body, include_package=True)
            except ValidationError as error:
                self._error(422, "validation", str(error))
                return
            selected = next(option for option in _smart_cart_options(request) if option["type"] == request["packageType"])
            selected.update({
                "missionId": request["missionId"], "groupSize": request["groupSize"],
                "originalBudget": request["budgetCents"] / 100, "priority": request["priority"],
                "planningPrompt": request["prompt"],
            })
            cart_id = secrets.token_urlsafe(18)
            timestamp = _timestamp()
            with _connect(self.server.db_path) as db:
                db.execute("BEGIN IMMEDIATE")
                count = db.execute("SELECT COUNT(*) FROM smart_carts").fetchone()[0]
                if count >= MAX_SMART_CARTS:
                    self._error(429, "circle_limit", "This local pilot has reached its Circle limit")
                    return
                db.execute(
                    "INSERT INTO smart_carts "
                    "(id, creator_user_id, mission_slug, group_name, creator_statement, priority, package_type, package_json, goal_cents, status, created_at, updated_at) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'open', ?, ?)",
                    (cart_id, session["user"]["id"], request["missionId"], request["groupName"],
                     request["creatorStatement"], request["priority"], request["packageType"],
                     json.dumps(selected, separators=(",", ":"), ensure_ascii=False), selected["goalCents"], timestamp, timestamp),
                )
                db.execute(
                    "INSERT INTO smart_cart_events (cart_id, event, created_at) VALUES (?, 'circle_created', ?)",
                    (cart_id, timestamp),
                )
                row = db.execute("SELECT * FROM smart_carts WHERE id = ?", (cart_id,)).fetchone()
                circle = _circle_public(db, row)
            self._json(201, {
                "circle": circle, "sharePath": f"/circle?id={cart_id}",
                "notice": "Shareable sandbox Circle created. No payment or charitable commitment has occurred.",
            })
            return
        checkout_match = re.fullmatch(r"/api/smart-carts/([^/]+)/checkout", path)
        if checkout_match and SIGNAL_ID_PATTERN.fullmatch(checkout_match.group(1)):
            try:
                _exact_keys(body, {"displayName", "amount", "anonymous", "message", "sandboxConfirmation"}, "request")
                if body["sandboxConfirmation"] is not True:
                    raise ValidationError("sandboxConfirmation must be accepted")
                if type(body["anonymous"]) is not bool:
                    raise ValidationError("anonymous must be true or false")
                display_name = _validated_text(body, "displayName", 60, allow_blank=body["anonymous"])
                message = _validated_text(body, "message", 180, allow_blank=True)
                amount = body["amount"]
                if type(amount) not in (int, float) or isinstance(amount, bool) or not math.isfinite(amount):
                    raise ValidationError("amount must be a number from 1 to 50000")
                decimal_amount = Decimal(str(amount))
                amount_cents = int(decimal_amount * 100)
                if not Decimal("1") <= decimal_amount <= Decimal("50000") or Decimal(amount_cents) / 100 != decimal_amount:
                    raise ValidationError("amount must be a number from 1 to 50000 with at most two decimal places")
            except (ValidationError, InvalidOperation, ValueError, OverflowError) as error:
                self._error(422, "validation", str(error))
                return
            cart_id = checkout_match.group(1)
            contribution_id = secrets.token_urlsafe(18)
            gateway_reference = "VISA-SBX-" + secrets.token_hex(6).upper()
            timestamp = _timestamp()
            with _connect(self.server.db_path) as db:
                db.execute("BEGIN IMMEDIATE")
                lock = " FOR UPDATE" if backend_name(db) == "postgres" else ""
                row = db.execute("SELECT * FROM smart_carts WHERE id = ?" + lock, (cart_id,)).fetchone()
                if row is None:
                    self._error(404, "not_found", "Circle not found")
                    return
                if row["status"] != "open":
                    self._error(409, "circle_closed", "This Circle is no longer accepting sandbox contributions")
                    return
                count = db.execute("SELECT COUNT(*) FROM circle_contributions").fetchone()[0]
                if count >= MAX_CIRCLE_CONTRIBUTIONS:
                    self._error(429, "contribution_limit", "This local pilot has reached its contribution limit")
                    return
                raised_cents = db.execute(
                    "SELECT COALESCE(SUM(amount_cents), 0) FROM circle_contributions WHERE cart_id = ? AND payment_status = 'sandbox-authorized'",
                    (cart_id,),
                ).fetchone()[0]
                remaining_cents = row["goal_cents"] - raised_cents
                if amount_cents > remaining_cents:
                    self._error(409, "amount_exceeds_remaining", f"The most this Circle can accept is ${remaining_cents / 100:,.2f}")
                    return
                stored_name = "" if body["anonymous"] else display_name
                db.execute(
                    "INSERT INTO circle_contributions "
                    "(id, cart_id, display_name, anonymous, amount_cents, message, payment_status, gateway_reference, created_at) "
                    "VALUES (?, ?, ?, ?, ?, ?, 'sandbox-authorized', ?, ?)",
                    (contribution_id, cart_id, stored_name, int(body["anonymous"]), amount_cents, message, gateway_reference, timestamp),
                )
                new_status = "funded" if amount_cents == remaining_cents else "open"
                db.execute("UPDATE smart_carts SET status = ?, updated_at = ? WHERE id = ?", (new_status, timestamp, cart_id))
                event = "circle_funded" if new_status == "funded" else "sandbox_contribution_authorized"
                db.execute("INSERT INTO smart_cart_events (cart_id, event, created_at) VALUES (?, ?, ?)", (cart_id, event, timestamp))
                updated_row = db.execute("SELECT * FROM smart_carts WHERE id = ?", (cart_id,)).fetchone()
                circle = _circle_public(db, updated_row)
            self._json(201, {
                "contribution": {
                    "id": contribution_id, "amount": amount_cents / 100, "status": "sandbox-authorized",
                    "gatewayReference": gateway_reference, "paymentProcessed": False, "createdAt": timestamp,
                },
                "circle": circle,
                "notice": "Sandbox authorization recorded. No card was charged and no money moved.",
            })
            return
        if path == "/api/intakes":
            session = self._require_session(csrf=True)
            if session is None:
                return
            try:
                _exact_keys(body, {"kind", "payload"}, "request")
                kind, payload = validate_intake(body["kind"], body["payload"])
            except ValidationError as error:
                self._error(422, "validation", str(error))
                return
            intake_id = secrets.token_urlsafe(18)
            timestamp = _timestamp()
            with _connect(self.server.db_path) as db:
                db.execute("BEGIN IMMEDIATE")
                count = db.execute("SELECT COUNT(*) FROM role_intakes").fetchone()[0]
                if count >= MAX_ROLE_INTAKES:
                    self._error(429, "intake_limit", "This local pilot has reached its intake limit")
                    return
                db.execute(
                    "INSERT INTO role_intakes "
                    "(id, kind, payload_json, verification_status, created_at, user_id, workflow_status, review_notes, updated_at) "
                    "VALUES (?, ?, ?, 'unverified', ?, ?, 'submitted', '', ?)",
                    (intake_id, kind, json.dumps(payload, separators=(",", ":"), ensure_ascii=False), timestamp,
                     session["user"]["id"], timestamp),
                )
                db.execute(
                    "INSERT INTO intake_events (intake_id, event, created_at) VALUES (?, 'submitted_unverified', ?)",
                    (intake_id, timestamp),
                )
            self._json(201, {
                "intake": {
                    "id": intake_id,
                    "kind": kind,
                    "status": "submitted",
                    "verification": "unverified",
                    "createdAt": timestamp,
                },
                "notice": "Pilot inquiry saved locally. It is not a verified partnership, accepted mission, or public listing.",
            })
            return
        if path == "/api/pledges":
            session = self._require_session(csrf=True)
            if session is None:
                return
            try:
                pledge = validate_pledge(body)
            except ValidationError as error:
                self._error(422, "validation", str(error))
                return
            pledge_id = secrets.token_urlsafe(18)
            timestamp = _timestamp()
            stored_name = "" if pledge["anonymous"] else pledge["displayName"]
            with _connect(self.server.db_path) as db:
                db.execute("BEGIN IMMEDIATE")
                count = db.execute("SELECT COUNT(*) FROM simulated_pledges").fetchone()[0]
                if count >= MAX_SIMULATED_PLEDGES:
                    self._error(429, "pledge_limit", "This local demo has reached its simulated-pledge limit")
                    return
                db.execute(
                    "INSERT INTO simulated_pledges "
                    "(id, mission_slug, amount_cents, display_name, anonymous, status, created_at, user_id) "
                    "VALUES (?, ?, ?, ?, ?, 'simulated', ?, ?)",
                    (pledge_id, pledge["missionId"], pledge["amountCents"], stored_name,
                     int(pledge["anonymous"]), timestamp, session["user"]["id"]),
                )
                db.execute(
                    "INSERT INTO pledge_events (pledge_id, event, created_at) VALUES (?, 'recorded_simulation', ?)",
                    (pledge_id, timestamp),
                )
            self._json(201, {
                "pledge": {
                    "id": pledge_id,
                    "missionId": pledge["missionId"],
                    "amount": pledge["amountCents"] / 100,
                    "displayName": "Anonymous supporter" if pledge["anonymous"] else pledge["displayName"],
                    "anonymous": pledge["anonymous"],
                    "status": "simulated",
                    "sample": True,
                    "paymentProcessed": False,
                    "createdAt": timestamp,
                },
                "notice": "Demo pledge recorded for the prototype only. No payment was requested, charged, collected, or transferred.",
            })
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

    def do_PATCH(self) -> None:
        if not self._allowed_origin():
            return
        path, query = self._path()
        match = re.fullmatch(r"/api/admin/intakes/([^/]+)", path)
        if not match or query or not SIGNAL_ID_PATTERN.fullmatch(match.group(1)):
            self._error(404, "not_found", "Route not found")
            return
        session = self._require_session(admin=True, csrf=True)
        if session is None:
            return
        body = self._read_json()
        if body is None:
            return
        try:
            _exact_keys(body, {"status", "reviewNotes"}, "request")
            status = body["status"]
            if type(status) is not str or status not in INQUIRY_STATUSES:
                raise ValidationError("status is not a supported inquiry state")
            review_notes = body["reviewNotes"]
            if type(review_notes) is not str or len(review_notes) > 1_000 or any(
                ord(character) < 32 and character not in "\t\n" for character in review_notes
            ):
                raise ValidationError("reviewNotes must be text of at most 1000 characters")
            review_notes = review_notes.strip()
        except ValidationError as error:
            self._error(422, "validation", str(error))
            return
        intake_id = match.group(1)
        timestamp = _timestamp()
        with _connect(self.server.db_path) as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT workflow_status FROM role_intakes WHERE id = ?", (intake_id,)).fetchone()
            if row is None:
                self._error(404, "not_found", "Inquiry not found")
                return
            db.execute(
                "UPDATE role_intakes SET workflow_status = ?, review_notes = ?, updated_at = ? WHERE id = ?",
                (status, review_notes, timestamp, intake_id),
            )
            event = f"status:{status}" if status != row["workflow_status"] else "review_updated"
            db.execute(
                "INSERT INTO intake_events (intake_id, event, created_at) VALUES (?, ?, ?)",
                (intake_id, event, timestamp),
            )
        self._json(200, {
            "inquiry": {"id": intake_id, "status": status, "reviewNotes": review_notes, "updatedAt": timestamp},
            "reviewedBy": session["user"],
        })

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
