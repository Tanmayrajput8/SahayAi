"""End-to-End Test for Citizen & Staff Multi-Role Routing and Workflows."""
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)


def test_citizen_pages():
    # 1. Citizen Emergency Intake Landing
    r1 = client.get("/")
    assert r1.status_code == 200
    assert "Report an Emergency in Pune" in r1.text
    assert "Dispatcher Login" in r1.text

    # 2. Citizen /emergency Alias
    r2 = client.get("/emergency")
    assert r2.status_code == 200
    assert "Report an Emergency in Pune" in r2.text

    # 3. Citizen Case Tracker
    r3 = client.get("/track")
    assert r3.status_code == 200
    assert "Live Emergency Tracker" in r3.text


def test_staff_pages_and_routes():
    routes = [
        ("/staff/login", "Staff Login"),
        ("/staff/dashboard", "Operations Command Overview"),
        ("/staff/cases", "Emergency Cases Registry"),
        ("/staff/cases/sample-case-id", "Emergency Case Dossier"),
        ("/staff/review", "Human-in-the-Loop Review Queue"),
        ("/staff/ambulances", "Pune Ambulance Fleet Management"),
        ("/staff/hospitals", "Emergency Hospitals"),
        ("/staff/map", "Pune Regional Fleet"),
        ("/staff/sla", "SLA Threshold Monitoring"),
        ("/staff/audit", "Immutable Audit Logging"),
        ("/staff/fairness", "Multilingual Demographic Fairness"),
    ]
    for url, expected_text in routes:
        resp = client.get(url)
        assert resp.status_code == 200, f"Route {url} failed with {resp.status_code}"
        assert expected_text in resp.text, f"Missing {expected_text} in {url}"


def test_convenience_redirects():
    r_login = client.get("/login", follow_redirects=False)
    assert r_login.status_code == 302
    assert r_login.headers["location"] == "/staff/login"

    r_dash = client.get("/dashboard", follow_redirects=False)
    assert r_dash.status_code == 302
    assert r_dash.headers["location"] == "/staff/dashboard"


def test_full_citizen_intake_to_dispatch_workflow():
    # 1. Citizen submits emergency without login
    create_resp = client.post("/api/v1/cases", json={
        "raw_text": "Severe head injury and unconscious pedestrian on FC Road Deccan Gymkhana Pune",
        "manual_location": "FC Road, Deccan Gymkhana, Pune",
        "latitude": 18.5204,
        "longitude": 73.8406,
        "language": "english",
    })
    assert create_resp.status_code == 201
    case_data = create_resp.json()
    case_id = case_data["id"]
    assert case_id is not None

    # 2. AI clinical triage
    triage_resp = client.post(f"/api/v1/cases/{case_id}/triage")
    assert triage_resp.status_code == 200
    triage_data = triage_resp.json()
    assert triage_data["priority"] in ["CRITICAL", "HIGH", "MODERATE", "LOW"]
    assert triage_data["recommended_ambulance"] in ["ALS", "BLS"]

    # 3. Clinical RAG verification
    rag_resp = client.post(f"/api/v1/rag/cases/{case_id}/verify")
    assert rag_resp.status_code == 200

    # 4. Resource matching & dispatch
    dispatch_resp = client.post(f"/api/v1/cases/{case_id}/dispatch")
    assert dispatch_resp.status_code == 200
    dispatch_data = dispatch_resp.json()
    assert dispatch_data["matched_ambulance"] is not None
    assert dispatch_data["matched_hospital"] is not None

    # 5. Citizen tracking view retrieval
    track_resp = client.get(f"/api/v1/cases/{case_id}")
    assert track_resp.status_code == 200
    track_data = track_resp.json()
    assert track_data["status"] == "DISPATCHED"


def test_staff_authentication_and_protected_access():
    # 1. Staff login with seeded credentials
    login_resp = client.post("/api/v1/auth/login", json={
        "username": "dispatcher1",
        "password": "dispatcher123",
    })
    assert login_resp.status_code == 200
    token = login_resp.json()["access_token"]
    assert token is not None

    # 2. Fetch authenticated user profile
    me_resp = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert me_resp.status_code == 200
    assert me_resp.json()["username"] == "dispatcher1"
    assert me_resp.json()["role"] == "dispatcher"
