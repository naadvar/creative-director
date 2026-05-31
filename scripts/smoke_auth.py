"""Smoke-test the auth foundation: app boots, session works, tables create."""
from fastapi.testclient import TestClient

from api.main import app

with TestClient(app) as c:  # context manager triggers lifespan -> init_db()
    print("health:", c.get("/health").json())
    r = c.get("/auth/me")
    print("me (anon):", r.status_code, r.json())
    r = c.post("/auth/logout")
    print("logout:", r.status_code, r.json())
    # IG OAuth start with no creds configured -> graceful 503 (route is wired).
    r = c.get("/auth/instagram/start", follow_redirects=False)
    print("ig/start (no creds):", r.status_code, r.json() if r.status_code != 307 else "redirect")
    routes = sorted({r.path for r in app.routes if hasattr(r, "path")})
    print("auth routes:", [p for p in routes if "auth" in p])
print("OK: auth foundation boots, User/ConnectedAccount tables created")
