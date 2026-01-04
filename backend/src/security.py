"""Security Module

Comprehensive API authentication and rate limiting for ModelMesh.

Features:
- API key generation and validation
- Rate limiting (per-minute and per-hour)
- Key rotation and revocation
- Usage tracking
- Security logging
"""

import os
import secrets
import hashlib
import logging
from typing import Optional, Dict, Set
from datetime import datetime, timedelta
from fastapi import HTTPException, Security, Header, Depends
from fastapi.security import APIKeyHeader
from functools import lru_cache

logger = logging.getLogger(__name__)

# API Key header
api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


class APIKeyManager:
    """
    Manage API keys for authentication
    
    Features:
    - Key generation and validation
    - Key revocation
    - Usage tracking
    - Persistent storage
    """
    
    def __init__(self):
        """Initialize API key manager"""
        self.valid_keys: Set[str] = set()
        self.key_names: Dict[str, str] = {}
        self.key_usage: Dict[str, int] = {}
        self.key_created: Dict[str, datetime] = {}
        self._load_keys()
        logger.info(f"APIKeyManager initialized with {len(self.valid_keys)} keys")
    
    def _load_keys(self):
        """Load API keys from environment or file"""
        # Load from environment variable
        env_key = os.getenv("API_KEY")
        if env_key:
            self.valid_keys.add(env_key)
            self.key_names[env_key] = "production"
            self.key_created[env_key] = datetime.now()
            logger.info("Loaded API key from environment")
        
        # Load from file if exists
        key_file = os.getenv("API_KEY_FILE", ".api_keys")
        if os.path.exists(key_file):
            try:
                with open(key_file, 'r') as f:
                    for line in f:
                        line = line.strip()
                        if line and not line.startswith('#'):
                            self.valid_keys.add(line)
                            self.key_names[line] = "from_file"
                            self.key_created[line] = datetime.now()
                logger.info(f"Loaded {len(self.valid_keys)} keys from file: {key_file}")
            except Exception as e:
                logger.error(f"Failed to load API keys from file: {e}")
        
        # Generate default key if none exist (DEVELOPMENT ONLY)
        if not self.valid_keys:
            default_key = "dev-" + secrets.token_urlsafe(32)
            self.valid_keys.add(default_key)
            self.key_names[default_key] = "development"
            self.key_created[default_key] = datetime.now()
            logger.warning(
                f"No API keys configured. Generated development key: {default_key[:20]}..."
            )
    
    def generate_key(self, name: str = "unnamed") -> str:
        """
        Generate a new API key
        
        Format: mk_<token>
        where mk = modelmesh key
        
        Args:
            name: Friendly name for the key
        
        Returns:
            Generated API key string
        """
        token = secrets.token_urlsafe(32)
        api_key = f"mk_{token}"
        
        self.valid_keys.add(api_key)
        self.key_names[api_key] = name
        self.key_created[api_key] = datetime.now()
        self.key_usage[api_key] = 0
        
        logger.info(f"Generated new API key: {name}")
        return api_key
    
    def validate_key(self, api_key: str) -> bool:
        """
        Validate API key and record usage
        
        Args:
            api_key: API key to validate
        
        Returns:
            True if valid, False otherwise
        """
        is_valid = api_key in self.valid_keys
        
        if is_valid:
            # Track usage
            self.key_usage[api_key] = self.key_usage.get(api_key, 0) + 1
        else:
            logger.warning(f"Invalid API key attempt: {api_key[:20] if api_key else 'empty'}...")
        
        return is_valid
    
    def revoke_key(self, api_key: str) -> bool:
        """
        Revoke an API key
        
        Args:
            api_key: Key to revoke
        
        Returns:
            True if revoked, False if key not found
        """
        if api_key in self.valid_keys:
            self.valid_keys.remove(api_key)
            logger.info(f"Revoked API key: {self.key_names.get(api_key, 'unknown')}")
            return True
        return False
    
    def get_key_info(self, api_key: str) -> Optional[Dict]:
        """
        Get information about an API key
        
        Args:
            api_key: Key to get info for
        
        Returns:
            Dictionary with key info or None if not found
        """
        if api_key not in self.valid_keys:
            return None
        
        return {
            'name': self.key_names.get(api_key, 'unnamed'),
            'usage_count': self.key_usage.get(api_key, 0),
            'created_at': self.key_created.get(api_key).isoformat() if api_key in self.key_created else None,
            'valid': True,
            'age_hours': (datetime.now() - self.key_created.get(api_key, datetime.now())).total_seconds() / 3600
        }
    
    def list_keys(self) -> list:
        """
        List all API keys (masked for security)
        
        Returns:
            List of key information (without full keys)
        """
        return [
            {
                'key_prefix': key[:10] + '...',
                'name': self.key_names.get(key, 'unnamed'),
                'usage': self.key_usage.get(key, 0),
                'created_at': self.key_created.get(key).isoformat() if key in self.key_created else None
            }
            for key in sorted(self.valid_keys)
        ]


class RateLimiter:
    """
    Rate limiter using token bucket algorithm with time windows
    
    Features:
    - Per-minute rate limiting
    - Per-hour rate limiting
    - Per-API-key tracking
    - Automatic cleanup
    """
    
    def __init__(
        self,
        requests_per_minute: int = 100,
        requests_per_hour: int = 1000
    ):
        """
        Initialize rate limiter
        
        Args:
            requests_per_minute: Max requests per minute per key
            requests_per_hour: Max requests per hour per key
        """
        self.requests_per_minute = requests_per_minute
        self.requests_per_hour = requests_per_hour
        
        # Track requests using sliding window (list of timestamps)
        self.minute_buckets: Dict[str, list] = {}  # key -> [timestamps]
        self.hour_buckets: Dict[str, list] = {}
        
        logger.info(
            f"RateLimiter configured: "
            f"{requests_per_minute}/min, {requests_per_hour}/hour"
        )
    
    def check_rate_limit(self, api_key: str) -> bool:
        """
        Check if request is within rate limits
        
        Args:
            api_key: API key making the request
        
        Returns:
            True if allowed, False if rate limited
        """
        now = datetime.now()
        
        # Clean old entries
        self._cleanup_old_entries(now)
        
        # Check minute limit
        if not self._check_minute_limit(api_key, now):
            logger.warning(f"Rate limit exceeded (minute) for key: {api_key[:10]}...")
            return False
        
        # Check hour limit
        if not self._check_hour_limit(api_key, now):
            logger.warning(f"Rate limit exceeded (hour) for key: {api_key[:10]}...")
            return False
        
        # Record this request
        self._record_request(api_key, now)
        
        return True
    
    def _check_minute_limit(self, api_key: str, now: datetime) -> bool:
        """Check requests in last minute"""
        minute_ago = now - timedelta(minutes=1)
        
        if api_key not in self.minute_buckets:
            return True
        
        recent_requests = [
            ts for ts in self.minute_buckets[api_key]
            if ts > minute_ago
        ]
        
        return len(recent_requests) < self.requests_per_minute
    
    def _check_hour_limit(self, api_key: str, now: datetime) -> bool:
        """Check requests in last hour"""
        hour_ago = now - timedelta(hours=1)
        
        if api_key not in self.hour_buckets:
            return True
        
        recent_requests = [
            ts for ts in self.hour_buckets[api_key]
            if ts > hour_ago
        ]
        
        return len(recent_requests) < self.requests_per_hour
    
    def _record_request(self, api_key: str, timestamp: datetime):
        """Record a request timestamp"""
        if api_key not in self.minute_buckets:
            self.minute_buckets[api_key] = []
            self.hour_buckets[api_key] = []
        
        self.minute_buckets[api_key].append(timestamp)
        self.hour_buckets[api_key].append(timestamp)
    
    def _cleanup_old_entries(self, now: datetime):
        """Remove old entries to save memory"""
        hour_ago = now - timedelta(hours=2)  # Keep 2 hours of data
        
        for api_key in list(self.minute_buckets.keys()):
            # Clean minute bucket
            self.minute_buckets[api_key] = [
                ts for ts in self.minute_buckets[api_key]
                if ts > hour_ago
            ]
            
            # Clean hour bucket  
            self.hour_buckets[api_key] = [
                ts for ts in self.hour_buckets[api_key]
                if ts > hour_ago
            ]
            
            # Remove empty entries
            if not self.minute_buckets[api_key]:
                del self.minute_buckets[api_key]
                if api_key in self.hour_buckets:
                    del self.hour_buckets[api_key]
    
    def get_usage(self, api_key: str) -> Dict:
        """
        Get current usage statistics for an API key
        
        Args:
            api_key: API key to get usage for
        
        Returns:
            Dictionary with usage statistics
        """
        now = datetime.now()
        minute_ago = now - timedelta(minutes=1)
        hour_ago = now - timedelta(hours=1)
        
        minute_count = 0
        hour_count = 0
        
        if api_key in self.minute_buckets:
            minute_count = len([
                ts for ts in self.minute_buckets[api_key]
                if ts > minute_ago
            ])
        
        if api_key in self.hour_buckets:
            hour_count = len([
                ts for ts in self.hour_buckets[api_key]
                if ts > hour_ago
            ])
        
        return {
            'requests_last_minute': minute_count,
            'requests_last_hour': hour_count,
            'limit_per_minute': self.requests_per_minute,
            'limit_per_hour': self.requests_per_hour,
            'minute_remaining': max(0, self.requests_per_minute - minute_count),
            'hour_remaining': max(0, self.requests_per_hour - hour_count),
            'minute_percent': (minute_count / self.requests_per_minute) * 100 if self.requests_per_minute > 0 else 0
        }
    
    def get_stats(self) -> Dict:
        """
        Get overall rate limiter statistics
        
        Returns:
            Dictionary with global stats
        """
        return {
            'limits': {
                'per_minute': self.requests_per_minute,
                'per_hour': self.requests_per_hour
            },
            'tracked_keys': len(self.minute_buckets),
            'minute_buckets': len(self.minute_buckets),
            'hour_buckets': len(self.hour_buckets)
        }


# Global instances
api_key_manager = APIKeyManager()
rate_limiter = RateLimiter(
    requests_per_minute=int(os.getenv("RATE_LIMIT_PER_MINUTE", "100")),
    requests_per_hour=int(os.getenv("RATE_LIMIT_PER_HOUR", "1000"))
)


# ============================================================================
# DEPENDENCY FUNCTIONS FOR FASTAPI
# ============================================================================

async def verify_api_key(api_key: str = Security(api_key_header)) -> str:
    """
    Dependency to verify API key on protected endpoints
    
    Usage:
        @app.post("/predict")
        async def predict(
            request: PredictionRequest,
            api_key: str = Depends(verify_api_key)
        ):
            ...
    """
    if not api_key:
        raise HTTPException(
            status_code=401,
            detail="API key required. Include X-API-Key header."
        )
    
    if not api_key_manager.validate_key(api_key):
        raise HTTPException(
            status_code=403,
            detail="Invalid API key"
        )
    
    return api_key


async def check_rate_limit(api_key: str = Security(api_key_header)) -> str:
    """
    Dependency to check rate limits on protected endpoints
    
    Usage:
        @app.post("/predict")
        async def predict(
            request: PredictionRequest,
            api_key: str = Depends(verify_api_key),
            _: str = Depends(check_rate_limit)
        ):
            ...
    """
    if not api_key:
        raise HTTPException(401, "API key required")
    
    if not rate_limiter.check_rate_limit(api_key):
        usage = rate_limiter.get_usage(api_key)
        raise HTTPException(
            status_code=429,
            detail=f"Rate limit exceeded. {usage['minute_remaining']} requests remaining this minute.",
            headers={
                "X-RateLimit-Limit": str(rate_limiter.requests_per_minute),
                "X-RateLimit-Remaining": str(usage['minute_remaining']),
                "X-RateLimit-Reset": "60",
                "Retry-After": "60"
            }
        )
    
    return api_key
