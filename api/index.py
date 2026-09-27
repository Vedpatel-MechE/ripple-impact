"""Vercel Python Function entry point for every RIPPLE API route."""

from __future__ import annotations

from http.server import BaseHTTPRequestHandler
import json
import os


DATABASE_URL = os.environ.get("DATABASE_URL", "").strip()
ADMIN_EMAIL = os.environ.get("RIPPLE_ADMIN_EMAIL", "").strip()
ADMIN_PASSWORD = os.environ.get("RIPPLE_ADMIN_PASSWORD", "")
STARTUP_MESSAGE = ""

if not DATABASE_URL.startswith(("postgres://", "postgresql://")):
    STARTUP_MESSAGE = "RIPPLE needs a managed Postgres DATABASE_URL before its API can start."
elif bool(ADMIN_EMAIL) != bool(ADMIN_PASSWORD):
    STARTUP_MESSAGE = "Set both RIPPLE_ADMIN_EMAIL and RIPPLE_ADMIN_PASSWORD, or leave both unset."
else:
    try:
        from server import RippleHandler, initialize_database

        initialize_database(DATABASE_URL)
    except Exception as error:  # Vercel logs keep the detail; clients receive a safe message.
        print(f"RIPPLE startup failed: {type(error).__name__}: {error}")
        STARTUP_MESSAGE = "RIPPLE could not initialize its hosted database configuration."


if STARTUP_MESSAGE:
    class handler(BaseHTTPRequestHandler):
        """Fail safely until hosted configuration is complete."""

        def _unavailable(self) -> None:
            body = json.dumps({
                "error": "service_not_configured",
                "message": STARTUP_MESSAGE,
            }).encode("utf-8")
            self.send_response(503)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.end_headers()
            self.wfile.write(body)

        do_GET = _unavailable
        do_POST = _unavailable
        do_PATCH = _unavailable
        do_DELETE = _unavailable

        def log_message(self, format: str, *args: object) -> None:
            pass
else:
    class handler(RippleHandler):
        """Attach Vercel's request server to RIPPLE's hosted database."""

        def __init__(self, request, client_address, server):
            server.db_path = DATABASE_URL
            super().__init__(request, client_address, server)
