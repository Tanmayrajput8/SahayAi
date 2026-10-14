from fastapi import APIRouter
from app.core.exceptions import AppException

# Auxiliary router with intentional error triggers for testing error handlers
error_router = APIRouter(prefix="/test-errors")


@error_router.get("/trigger-500")
def trigger_unhandled():
    raise RuntimeError("Intentional secret internal failure database leak simulation")


@error_router.get("/trigger-custom")
def trigger_custom():
    raise AppException(
        message="Simulated dispatch failure",
        error_code="dispatch_failed",
        status_code=400,
    )


def test_not_found_returns_clean_json_404(client):
    """Verify invalid endpoint returns clean JSON 404 conforming to error schema."""
    response = client.get("/invalid-nonexistent-endpoint-xyz")
    assert response.status_code == 404
    data = response.json()
    assert "error" in data
    assert "message" in data
    assert data["error"] == "not_found"
    assert "not found" in data["message"].lower()
    # Confirm no HTML or python traceback is exposed
    assert "Traceback" not in response.text
    assert "<html" not in response.text.lower()


def test_unhandled_exception_does_not_expose_stack_trace(app, client):
    """Verify 500 error does not leak traceback or internal secrets to user."""
    # Temporarily mount test error route to trigger an unhandled error
    app.include_router(error_router)

    response = client.get("/test-errors/trigger-500")
    assert response.status_code == 500
    data = response.json()
    assert data["error"] == "internal_server_error"
    assert "unexpected error" in data["message"].lower()

    # CRITICAL: Verify internal error message/traceback is NOT in response body
    assert "Intentional secret internal failure" not in response.text
    assert "Traceback" not in response.text
    assert "RuntimeError" not in response.text


def test_custom_app_exception_returns_clean_json(app, client):
    """Verify custom AppException outputs standard error format."""
    app.include_router(error_router)

    response = client.get("/test-errors/trigger-custom")
    assert response.status_code == 400
    data = response.json()
    assert data["error"] == "dispatch_failed"
    assert data["message"] == "Simulated dispatch failure"
