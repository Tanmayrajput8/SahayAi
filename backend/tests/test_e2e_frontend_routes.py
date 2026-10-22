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


def test_full_lifecycle_under_review_to_dispatched_arrived_completed():
    """
    Validates complete workflow:
    Citizen reports emergency -> AI triage -> UNDER_REVIEW ->
    Staff opens case & reviews AI/deterministic -> CLICK DISPATCH ->
    Backend assigns ambulance -> Database updated -> Audit recorded ->
    DISPATCHED/EN ROUTE -> Citizen page updates (Ambulance + ETA + map + Hospital) ->
    ARRIVED -> COMPLETED.
    """
    # 1. Citizen reports emergency
    create_resp = client.post("/api/v1/cases", json={
        "raw_text": "Pedestrian hit near bus stop in Pune, leg fracture, bleeding",
        "manual_location": "bus stop Pune",
        "latitude": 18.5204,
        "longitude": 73.8567,
        "language": "english",
    })
    assert create_resp.status_code == 201
    case_id = create_resp.json()["id"]

    # 2. AI clinical triage extraction
    triage_resp = client.post(f"/api/v1/cases/{case_id}/triage")
    assert triage_resp.status_code == 200

    # 3. Place case UNDER_REVIEW (as occurs when automated intake flags uncertainty or review)
    client.patch(f"/api/v1/cases/{case_id}/status", json={
        "status": "UNDER_REVIEW",
        "notes": "Queued for supervisor dispatcher review",
    })

    # 4. Staff opens same case
    staff_view = client.get(f"/api/v1/cases/{case_id}")
    assert staff_view.status_code == 200
    staff_case = staff_view.json()
    assert staff_case["status"] == "UNDER_REVIEW"

    # 5. Staff reviews AI + deterministic result & confidence
    conf_resp = client.get(f"/api/v1/review/{case_id}/confidence")
    assert conf_resp.status_code == 200

    # 6. Staff CLICKS "DISPATCH" (manual authorization)
    dispatch_resp = client.post(f"/api/v1/cases/{case_id}/dispatch?manual=true&dispatcher_id=dispatcher1")
    assert dispatch_resp.status_code == 200
    disp_result = dispatch_resp.json()
    assert disp_result["is_dispatched"] is True
    assert disp_result["matched_ambulance"] is not None
    assert disp_result["matched_hospital"] is not None
    amb_num = disp_result["matched_ambulance"]["vehicle_number"]

    # 7. Database updated -> Case status is DISPATCHED
    # 8. Staff page & Citizen page reflect DISPATCHED / EN ROUTE
    # 9. Citizen page receives assigned ambulance, ETA, and hospital
    updated_case = client.get(f"/api/v1/cases/{case_id}").json()
    assert updated_case["status"] == "DISPATCHED"
    assert updated_case["assigned_ambulance"]["vehicle_number"] == amb_num
    assert updated_case["assigned_hospital"] is not None
    assert updated_case["eta_minutes"] is not None

    # 10. Audit recorded
    timeline_resp = client.get(f"/api/v1/audit/cases/{case_id}/timeline")
    assert timeline_resp.status_code == 200
    timeline = timeline_resp.json()
    dispatch_actions = [e["action"] for e in timeline]
    assert any("DISPATCH" in a for a in dispatch_actions)

    # 11. ARRIVED at scene
    arrived_resp = client.patch(f"/api/v1/cases/{case_id}/status", json={
        "status": "ARRIVED",
        "notes": "Ambulance arrived at incident scene",
    })
    assert arrived_resp.status_code == 200
    assert arrived_resp.json()["status"] == "ARRIVED"

    # 12. COMPLETED / RESOLVED
    resolved_resp = client.patch(f"/api/v1/cases/{case_id}/status", json={
        "status": "RESOLVED",
        "notes": "Patient transferred to hospital emergency department",
    })
    assert resolved_resp.status_code == 200
    assert resolved_resp.json()["status"] == "RESOLVED"
