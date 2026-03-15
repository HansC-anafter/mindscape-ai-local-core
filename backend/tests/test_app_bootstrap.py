"""Tests verifying application bootstrap modularity and modern lifecycle."""
import pytest
from fastapi.testclient import TestClient

@pytest.mark.integration
def test_app_lifespan_manager():
    """P3: Validates that the application can boot using modern TestClient context manager.
    NOTE: This is a heavy integration test. It runs migrations, connects to Redis, OCR checks, etc.
    """
    from backend.app.main import app
    # Under the FastAPI TestClient, treating it as a context manager invokes lifespan
    with TestClient(app) as client:
        response = client.get("/health")
        assert response.status_code == 200

def test_cors_origin_regex():
    """P2: Validates the generated CORS regex accurately covers chrome extensions."""
    import re
    from backend.app.app_bootstrap.cors import get_cors_origin_regex
    
    regex = get_cors_origin_regex()
    assert regex is not None, "A regex must be provided for extensions"
    compiled = re.compile(regex)
    assert compiled.match("chrome-extension://abcdefghijklmnop")
    assert not compiled.match("http://malicious.com")

def test_routes_baseline():
    """P4: Validates strict route count baseline to prevent silent route drops."""
    from backend.app.main import app
    
    with TestClient(app) as client:
        response = client.get("/debug/routes")
        assert response.status_code == 200
        data = response.json()
        
        # Exact match required to detect both dropped routes and duplicate registrations.
        # This will need to be updated as new features are added.
        expected_route_count = 942  
        assert data["total_routes"] == expected_route_count, f"Route baseline breached. Expected {expected_route_count}, got {data['total_routes']}"
