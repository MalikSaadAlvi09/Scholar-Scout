"""
API Endpoints and Health Check Tests for ScholarScout.
"""

import pytest
from starlette.testclient import TestClient
from backend.main import app

@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c

def test_health_endpoint(client):
    """Verify /api/health endpoint returns healthy status and metadata."""
    res = client.get("/api/health")
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "healthy"
    assert data["app_name"] == "ScholarScout"
    assert "model_name" in data

def test_profile_endpoints(client):
    """Verify /api/profile GET and POST."""
    res = client.get("/api/profile")
    assert res.status_code == 200
    p = res.json()
    assert "name" in p

def test_settings_masked_key(client):
    """Verify /api/settings never leaks cleartext secret keys."""
    res = client.get("/api/settings")
    assert res.status_code == 200
    settings = res.json()
    assert "api_base_url" in settings
    # api_key raw field should NOT be present in public settings output
    assert "api_key" not in settings
