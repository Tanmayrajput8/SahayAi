"""
Tests for JWT authentication — all 8 required scenarios + extras.

Seed credentials (see app/db/seed.py):
  dispatcher1 / dispatcher123  (DISPATCHER role)
  supervisor1 / supervisor123  (SUPERVISOR role)
  admin       / admin123       (ADMIN role)

Error response shape (from exceptions.py handler):
  HTTP 401/403 with dict detail → {"error": "...", "message": "..."}
"""
import sys
from pathlib import Path
from datetime import timedelta

import pytest
from fastapi.testclient import TestClient

# Ensure backend root on sys.path before any app imports
_backend = Path(__file__).resolve().parent.parent
if str(_backend) not in sys.path:
    sys.path.insert(0, str(_backend))

from app.main import app
from app.core.security import create_access_token, decode_access_token
from app.db.session import SessionLocal
from app.db.seed import seed_database

AUTH_URL = "/api/v1/auth/login"
ME_URL = "/api/v1/auth/me"
SUPERVISOR_URL = "/api/v1/auth/supervisor-only"


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def seeded_client():
    """TestClient whose lifespan is active and DB is seeded."""
    with SessionLocal() as db:
        seed_database(db)
    with TestClient(app, raise_server_exceptions=False) as c:
        yield c


def _bearer(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


# ---------------------------------------------------------------------------
# 1. Valid login — dispatcher
# ---------------------------------------------------------------------------
def test_valid_login_dispatcher(seeded_client):
    r = seeded_client.post(AUTH_URL, json={"username": "dispatcher1", "password": "dispatcher123"})
    assert r.status_code == 200, r.json()
    body = r.json()
    assert "access_token" in body
    assert body["token_type"] == "bearer"
    assert body["role"] == "dispatcher"
    assert body["username"] == "dispatcher1"
    assert body["expires_in_seconds"] > 0


# ---------------------------------------------------------------------------
# 2. Valid login — supervisor
# ---------------------------------------------------------------------------
def test_valid_login_supervisor(seeded_client):
    r = seeded_client.post(AUTH_URL, json={"username": "supervisor1", "password": "supervisor123"})
    assert r.status_code == 200, r.json()
    assert r.json()["role"] == "supervisor"


# ---------------------------------------------------------------------------
# 3. Invalid login — wrong password
# ---------------------------------------------------------------------------
def test_invalid_login_wrong_password(seeded_client):
    r = seeded_client.post(AUTH_URL, json={"username": "dispatcher1", "password": "wrong_password"})
    assert r.status_code == 401
    body = r.json()
    assert body["error"] == "invalid_credentials"


# ---------------------------------------------------------------------------
# 4. Invalid login — non-existent user
# ---------------------------------------------------------------------------
def test_invalid_login_unknown_user(seeded_client):
    r = seeded_client.post(AUTH_URL, json={"username": "ghost_user", "password": "anything"})
    assert r.status_code == 401
    assert r.json()["error"] == "invalid_credentials"


# ---------------------------------------------------------------------------
# 5. Missing JWT — protected endpoint without token
# ---------------------------------------------------------------------------
def test_missing_jwt_returns_401(seeded_client):
    r = seeded_client.get(ME_URL)  # no Authorization header
    assert r.status_code == 401
    assert r.json()["error"] == "missing_token"


# ---------------------------------------------------------------------------
# 6. Invalid JWT — garbage token
# ---------------------------------------------------------------------------
def test_invalid_jwt_returns_401(seeded_client):
    r = seeded_client.get(ME_URL, headers={"Authorization": "Bearer this.is.garbage"})
    assert r.status_code == 401
    assert r.json()["error"] == "invalid_token"


# ---------------------------------------------------------------------------
# 7. Expired JWT
# ---------------------------------------------------------------------------
def test_expired_jwt_returns_401(seeded_client):
    expired_token = create_access_token(
        data={"sub": "dispatcher1", "role": "dispatcher", "username": "dispatcher1"},
        expires_delta=timedelta(seconds=-1),
    )
    r = seeded_client.get(ME_URL, headers=_bearer(expired_token))
    assert r.status_code == 401
    assert r.json()["error"] == "invalid_token"


# ---------------------------------------------------------------------------
# 8. Authorized dispatcher — successful /me access
# ---------------------------------------------------------------------------
def test_authorized_dispatcher_can_access_me(seeded_client):
    login = seeded_client.post(AUTH_URL, json={"username": "dispatcher1", "password": "dispatcher123"})
    assert login.status_code == 200, login.json()
    token = login.json()["access_token"]

    r = seeded_client.get(ME_URL, headers=_bearer(token))
    assert r.status_code == 200
    body = r.json()
    assert body["username"] == "dispatcher1"
    assert body["role"] == "dispatcher"


# ---------------------------------------------------------------------------
# 9. Authorized supervisor — successful /me access
# ---------------------------------------------------------------------------
def test_authorized_supervisor_can_access_me(seeded_client):
    login = seeded_client.post(AUTH_URL, json={"username": "supervisor1", "password": "supervisor123"})
    assert login.status_code == 200, login.json()
    token = login.json()["access_token"]

    r = seeded_client.get(ME_URL, headers=_bearer(token))
    assert r.status_code == 200
    assert r.json()["role"] == "supervisor"


# ---------------------------------------------------------------------------
# 10. Token payload integrity — decoded claims match login response
# ---------------------------------------------------------------------------
def test_token_claims_match_login_response(seeded_client):
    login = seeded_client.post(AUTH_URL, json={"username": "admin", "password": "admin123"})
    assert login.status_code == 200, login.json()
    body = login.json()
    token = body["access_token"]

    payload = decode_access_token(token)
    assert payload["username"] == "admin"
    assert payload["role"] == "admin"
    assert "exp" in payload
    assert "sub" in payload


# ---------------------------------------------------------------------------
# 11. Role isolation — dispatcher token carries only dispatcher role
# ---------------------------------------------------------------------------
def test_dispatcher_token_has_dispatcher_role(seeded_client):
    """Dispatcher token must not carry supervisor/admin role claims."""
    login = seeded_client.post(AUTH_URL, json={"username": "dispatcher1", "password": "dispatcher123"})
    assert login.status_code == 200, login.json()
    token = login.json()["access_token"]
    payload = decode_access_token(token)
    assert payload["role"] == "dispatcher"
    assert payload["role"] != "supervisor"
    assert payload["role"] != "admin"


# ---------------------------------------------------------------------------
# 12. Wrong role — Dispatcher attempting supervisor-only action returns 403
# ---------------------------------------------------------------------------
def test_wrong_role_returns_403(seeded_client):
    """A user with DISPATCHER role must be rejected with 403 Forbidden on supervisor routes."""
    login = seeded_client.post(AUTH_URL, json={"username": "dispatcher1", "password": "dispatcher123"})
    assert login.status_code == 200, login.json()
    dispatcher_token = login.json()["access_token"]

    r = seeded_client.get(SUPERVISOR_URL, headers=_bearer(dispatcher_token))
    assert r.status_code == 403
    body = r.json()
    assert body["error"] == "forbidden"
    assert "not permitted" in body["message"]


# ---------------------------------------------------------------------------
# 13. Authorized supervisor — Can access supervisor-only route
# ---------------------------------------------------------------------------
def test_authorized_supervisor_can_access_supervisor_only(seeded_client):
    """A user with SUPERVISOR role can access supervisor-only routes."""
    login = seeded_client.post(AUTH_URL, json={"username": "supervisor1", "password": "supervisor123"})
    assert login.status_code == 200, login.json()
    supervisor_token = login.json()["access_token"]

    r = seeded_client.get(SUPERVISOR_URL, headers=_bearer(supervisor_token))
    assert r.status_code == 200
    assert r.json()["role"] == "supervisor"

