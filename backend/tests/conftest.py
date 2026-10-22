import sys
from pathlib import Path
import pytest
from fastapi.testclient import TestClient

# Ensure backend root is on sys.path
backend_path = Path(__file__).resolve().parent.parent
if str(backend_path) not in sys.path:
    sys.path.insert(0, str(backend_path))

from app.core.config import settings
settings.GEOCODING_PROVIDER = "mock"
settings.SPEECH_PROVIDER = "mock"
settings.LLM_PROVIDER = "mock"


from app.main import create_application


@pytest.fixture(scope="session")
def app():
    return create_application()


@pytest.fixture(scope="session")
def client(app):
    with TestClient(app, raise_server_exceptions=False) as c:
        yield c
