def test_root_health_endpoint(client):
    """Verify GET /health returns 200 and {'status': 'ok'}."""
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data == {"status": "ok"}


def test_v1_health_endpoint(client):
    """Verify GET /api/v1/health returns 200, status='ok', and DB connectivity status."""
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert "version" in data
    assert "database" in data
    assert data["database"] == "connected"


def test_root_index_endpoint(client):
    """Verify GET / returns 200 and the SahayAI Emergency dashboard web interface."""
    response = client.get("/")
    assert response.status_code == 200
    assert "<!DOCTYPE html>" in response.text or "SahayAI" in response.text


def test_api_info_endpoint(client):
    """Verify GET /api and GET /?format=json return 200 and system metadata."""
    response = client.get("/api")
    assert response.status_code == 200
    data = response.json()
    assert "name" in data
    assert "health" in data
    assert data["health"] == "/health"

    json_root = client.get("/?format=json")
    assert json_root.status_code == 200
    assert json_root.json()["name"] == data["name"]

