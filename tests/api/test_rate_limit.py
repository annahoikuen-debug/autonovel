import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from src.api.middleware.rate_limit import RateLimitMiddleware

@pytest.fixture
def client():
    app = FastAPI()
    # Set a low rate limit for testing: 5 requests per minute
    app.add_middleware(RateLimitMiddleware, requests_per_minute=5)

    @app.post("/api/generate", status_code=202)
    def generate():
        return {"job_id": "test_job"}

    return TestClient(app)

def test_rate_limit_allows_n_requests(client):
    test_payload = {"title": "Test"}
    # Make 5 requests (should be allowed)
    for i in range(5):
        resp = client.post("/api/generate", json=test_payload)
        assert resp.status_code == 202, f"Request {i+1} failed with {resp.status_code}"

    # 6th request should be rate limited.
    # `BaseHTTPMiddleware.dispatch` runs OUTSIDE Starlette's ExceptionMiddleware,
    # so raising HTTPException there would surface as a 500, not a 429.
    # The middleware therefore returns an explicit 429 Response, so the
    # assertion must be on the RESPONSE (status + Retry-After header).
    resp = client.post("/api/generate", json=test_payload)
    assert resp.status_code == 429
    assert resp.headers["Retry-After"] == "60"
    assert "Too Many Requests" in resp.text
