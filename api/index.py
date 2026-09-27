"""Vercel Python Function entry point for every RIPPLE API route."""

from __future__ import annotations

import json
import os

from server import RippleHandler, initialize_database


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
        initialize_database(DATABASE_URL)
    except Exception as error:  # Vercel logs keep detail; clients receive a safe message.
        print(f"RIPPLE startup failed: {type(error).__name__}: {error}")
        STARTUP_MESSAGE = "RIPPLE could not initialize its hosted database configuration."


class handler(RippleHandler):
    """Top-level Vercel handler with safe startup failure and path restoration."""

    def __init__(self, request, client_address, server):
        server.db_path = DATABASE_URL
        super().__init__(request, client_address, server)

    def _path(self):
        path, query = super()._path()
        forwarded = query.pop("__ripple_path", [])
        if len(forwarded) == 1:
            suffix = forwarded[0].strip("/")
            path = "/api" + ("/" + suffix if suffix else "")
        return path, query

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

    def do_GET(self) -> None:
        if STARTUP_MESSAGE:
            self._unavailable()
            return
        super().do_GET()

    def do_POST(self) -> None:
        if STARTUP_MESSAGE:
            self._unavailable()
            return
        super().do_POST()

    def do_PATCH(self) -> None:
        if STARTUP_MESSAGE:
            self._unavailable()
            return
        super().do_PATCH()

    def do_DELETE(self) -> None:
        if STARTUP_MESSAGE:
            self._unavailable()
            return
        super().do_DELETE()
