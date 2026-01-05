"""API Tests for GPU VRAM Orchestrator

Tests for FastAPI endpoints including authentication, rate limiting, and error handling.
"""

import pytest
import asyncio
import json
from httpx import AsyncClient
from unittest.mock import Mock, AsyncMock, patch
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.app import app
from src.security import APIKeyManager, RateLimiter


@pytest.fixture
def api_key():
    """Fixture for valid API key"""
    return "mk_test_key_" + "x" * 32


@pytest.fixture
def invalid_api_key():
    """Fixture for invalid API key"""
    return "invalid_key_xyz"


@pytest.mark.asyncio
class TestAPIAuthentication:
    """Test API authentication with X-API-Key header"""

    async def test_predict_with_valid_auth(self, api_key):
        """Test prediction endpoint with valid API key"""
        with patch('src.app.api_key_manager') as mock_manager:
            mock_manager.validate_key.return_value = True
            async with AsyncClient(app=app, base_url="http://test") as client:
                response = await client.post(
                    "/predict",
                    json={
                        "model_id": "test-model",
                        "data": {"values": [[1.0, 2.0, 3.0]]}
                    },
                    headers={"X-API-Key": api_key}
                )
            assert response.status_code == 200

    async def test_predict_without_auth(self):
        """Test prediction fails without API key"""
        async with AsyncClient(app=app, base_url="http://test") as client:
            response = await client.post(
                "/predict",
                json={
                    "model_id": "test-model",
                    "data": {"values": [[1.0, 2.0, 3.0]]}
                }
            )
        assert response.status_code == 401

    async def test_predict_with_invalid_auth(self, invalid_api_key):
        """Test prediction fails with invalid API key"""
        with patch('src.app.api_key_manager') as mock_manager:
            mock_manager.validate_key.return_value = False
            async with AsyncClient(app=app, base_url="http://test") as client:
                response = await client.post(
                    "/predict",
                    json={
                        "model_id": "test-model",
                        "data": {"values": [[1.0, 2.0, 3.0]]}
                    },
                    headers={"X-API-Key": invalid_api_key}
                )
            assert response.status_code == 401

    async def test_health_check_no_auth_required(self):
        """Test health endpoint does not require authentication"""
        async with AsyncClient(app=app, base_url="http://test") as client:
            response = await client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert "status" in data


@pytest.mark.asyncio
class TestAPIRateLimiting:
    """Test API rate limiting functionality"""

    async def test_rate_limit_per_minute(self, api_key):
        """Test rate limiting enforced per minute (100 requests/min)"""
        with patch('src.app.api_key_manager') as mock_manager:
            with patch('src.app.rate_limiter') as mock_limiter:
                mock_manager.validate_key.return_value = True
                
                async with AsyncClient(app=app, base_url="http://test") as client:
                    # First 100 requests should succeed
                    for i in range(100):
                        mock_limiter.check_rate_limit.return_value = True
                        response = await client.post(
                            "/predict",
                            json={
                                "model_id": f"model-{i}",
                                "data": {"values": [[float(i)]]}
                            },
                            headers={"X-API-Key": api_key}
                        )
                        assert response.status_code == 200
                    
                    # 101st request should be rate limited
                    mock_limiter.check_rate_limit.return_value = False
                    response = await client.post(
                        "/predict",
                        json={
                            "model_id": "model-101",
                            "data": {"values": [[101.0]]}
                        },
                        headers={"X-API-Key": api_key}
                    )
                    assert response.status_code == 429

    async def test_rate_limit_response_format(self, api_key):
        """Test rate limit response has correct format"""
        with patch('src.app.api_key_manager') as mock_manager:
            with patch('src.app.rate_limiter') as mock_limiter:
                mock_manager.validate_key.return_value = True
                mock_limiter.check_rate_limit.return_value = False
                
                async with AsyncClient(app=app, base_url="http://test") as client:
                    response = await client.post(
                        "/predict",
                        json={
                            "model_id": "test-model",
                            "data": {"values": [[1.0]]}
                        },
                        headers={"X-API-Key": api_key}
                    )
                
                assert response.status_code == 429
                data = response.json()
                assert "detail" in data


@pytest.mark.asyncio
class TestAPIPredictEndpoint:
    """Test /predict endpoint functionality"""

    async def test_predict_success(self, api_key):
        """Test successful prediction"""
        with patch('src.app.api_key_manager') as mock_manager:
            with patch('src.app.rate_limiter') as mock_limiter:
                with patch('src.app.orchestrator') as mock_orch:
                    mock_manager.validate_key.return_value = True
                    mock_limiter.check_rate_limit.return_value = True
                    mock_orch.predict.return_value = {
                        "prediction": [0.95, 0.05],
                        "latency_ms": 42.5,
                        "gpu_id": 0,
                        "from_cache": True
                    }
                    
                    async with AsyncClient(app=app, base_url="http://test") as client:
                        response = await client.post(
                            "/predict",
                            json={
                                "model_id": "fraud-detector",
                                "data": {"transaction": {"amount": 1500}}
                            },
                            headers={"X-API-Key": api_key}
                        )
                    
                    assert response.status_code == 200
                    data = response.json()
                    assert "prediction" in data
                    assert "latency_ms" in data

    async def test_predict_missing_model_id(self, api_key):
        """Test prediction fails when model_id is missing"""
        with patch('src.app.api_key_manager') as mock_manager:
            with patch('src.app.rate_limiter') as mock_limiter:
                mock_manager.validate_key.return_value = True
                mock_limiter.check_rate_limit.return_value = True
                
                async with AsyncClient(app=app, base_url="http://test") as client:
                    response = await client.post(
                        "/predict",
                        json={"data": {"values": [[1.0]]}},
                        headers={"X-API-Key": api_key}
                    )
                
                assert response.status_code == 422

    async def test_predict_invalid_data_format(self, api_key):
        """Test prediction fails with invalid data format"""
        with patch('src.app.api_key_manager') as mock_manager:
            with patch('src.app.rate_limiter') as mock_limiter:
                mock_manager.validate_key.return_value = True
                mock_limiter.check_rate_limit.return_value = True
                
                async with AsyncClient(app=app, base_url="http://test") as client:
                    response = await client.post(
                        "/predict",
                        json={
                            "model_id": "test-model",
                            "data": "not-a-dict"
                        },
                        headers={"X-API-Key": api_key}
                    )
                
                assert response.status_code == 422


@pytest.mark.asyncio
class TestAPIHealthEndpoint:
    """Test /health endpoint"""

    async def test_health_check_success(self):
        """Test health check returns success"""
        async with AsyncClient(app=app, base_url="http://test") as client:
            response = await client.get("/health")
        
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"

    async def test_health_check_has_version(self):
        """Test health check includes version info"""
        async with AsyncClient(app=app, base_url="http://test") as client:
            response = await client.get("/health")
        
        data = response.json()
        assert "version" in data


@pytest.mark.asyncio
class TestAPIAdminEndpoints:
    """Test admin endpoints for key management"""

    async def test_generate_key(self):
        """Test admin can generate new API key"""
        with patch('src.app.api_key_manager') as mock_manager:
            mock_manager.generate_key.return_value = "mk_new_key_xyz"
            
            async with AsyncClient(app=app, base_url="http://test") as client:
                response = await client.post(
                    "/admin/keys/generate",
                    json={"name": "test-key"}
                )
            
            # Should be 200 or require auth - depends on implementation
            assert response.status_code in [200, 401]

    async def test_list_keys_requires_auth(self):
        """Test listing keys requires admin authentication"""
        async with AsyncClient(app=app, base_url="http://test") as client:
            response = await client.get("/admin/keys/list")
        
        # Without proper auth, should fail
        assert response.status_code in [401, 403]


@pytest.mark.asyncio
class TestAPIErrorHandling:
    """Test API error handling and edge cases"""

    async def test_model_not_found(self, api_key):
        """Test prediction fails gracefully when model not found"""
        with patch('src.app.api_key_manager') as mock_manager:
            with patch('src.app.rate_limiter') as mock_limiter:
                with patch('src.app.orchestrator') as mock_orch:
                    mock_manager.validate_key.return_value = True
                    mock_limiter.check_rate_limit.return_value = True
                    mock_orch.predict.side_effect = RuntimeError("Model not found")
                    
                    async with AsyncClient(app=app, base_url="http://test") as client:
                        response = await client.post(
                            "/predict",
                            json={
                                "model_id": "nonexistent-model",
                                "data": {"values": [[1.0]]}
                            },
                            headers={"X-API-Key": api_key}
                        )
                    
                    assert response.status_code in [404, 500]

    async def test_server_error_handling(self, api_key):
        """Test API handles server errors gracefully"""
        with patch('src.app.api_key_manager') as mock_manager:
            with patch('src.app.rate_limiter') as mock_limiter:
                with patch('src.app.orchestrator') as mock_orch:
                    mock_manager.validate_key.return_value = True
                    mock_limiter.check_rate_limit.return_value = True
                    mock_orch.predict.side_effect = Exception("Server error")
                    
                    async with AsyncClient(app=app, base_url="http://test") as client:
                        response = await client.post(
                            "/predict",
                            json={
                                "model_id": "test-model",
                                "data": {"values": [[1.0]]}
                            },
                            headers={"X-API-Key": api_key}
                        )
                    
                    assert response.status_code == 500


@pytest.mark.asyncio
class TestTimeoutHandling:
    """Test request timeout handling"""

    async def test_request_timeout(self, api_key):
        """Test that long-running requests timeout properly"""
        with patch('src.app.api_key_manager') as mock_manager:
            with patch('src.app.rate_limiter') as mock_limiter:
                with patch('src.app.orchestrator') as mock_orch:
                    mock_manager.validate_key.return_value = True
                    mock_limiter.check_rate_limit.return_value = True
                    
                    # Simulate slow operation
                    async def slow_predict(*args, **kwargs):
                        await asyncio.sleep(100)
                        return {"prediction": [0.5]}
                    
                    mock_orch.predict = slow_predict
                    
                    # Set a short timeout
                    async with AsyncClient(app=app, base_url="http://test", timeout=0.1) as client:
                        try:
                            response = await client.post(
                                "/predict",
                                json={
                                    "model_id": "test-model",
                                    "data": {"values": [[1.0]]}
                                },
                                headers={"X-API-Key": api_key}
                            )
                            # If we get here, should be timeout error
                            assert response.status_code in [504, 408]
                        except Exception as e:
                            # Timeout exception is also acceptable
                            assert "timeout" in str(e).lower() or "timeout" in type(e).__name__.lower()


class TestAPIKeyManager:
    """Unit tests for APIKeyManager"""

    def test_generate_key(self):
        """Test generating API key"""
        manager = APIKeyManager()
        key = manager.generate_key(name="test")
        assert key.startswith("mk_")
        assert manager.validate_key(key)

    def test_revoke_key(self):
        """Test revoking API key"""
        manager = APIKeyManager()
        key = manager.generate_key()
        assert manager.validate_key(key)
        assert manager.revoke_key(key)
        assert not manager.validate_key(key)

    def test_key_validation(self):
        """Test key validation"""
        manager = APIKeyManager()
        key = manager.generate_key()
        assert manager.validate_key(key)
        assert not manager.validate_key("invalid_key")


class TestRateLimiter:
    """Unit tests for RateLimiter"""

    def test_rate_limiting_basic(self):
        """Test basic rate limiting"""
        limiter = RateLimiter(requests_per_minute=5)
        
        # First 5 should pass
        for i in range(5):
            assert limiter.check_rate_limit("key1")
        
        # 6th should fail
        assert not limiter.check_rate_limit("key1")

    def test_rate_limiting_reset_after_minute(self):
        """Test rate limit resets after time window"""
        limiter = RateLimiter(requests_per_minute=5)
        
        # Use up the limit
        for i in range(5):
            limiter.check_rate_limit("key2")
        
        assert not limiter.check_rate_limit("key2")
        
        # Manually reset for testing
        limiter.reset_key("key2")
        assert limiter.check_rate_limit("key2")
