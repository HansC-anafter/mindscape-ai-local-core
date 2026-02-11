"""
Security components for My Agent Console
Implements local-first security with encryption and authentication
"""

import os
import secrets
from datetime import datetime, timedelta, timezone


def _utc_now():
    """Return timezone-aware UTC now."""
    return datetime.now(timezone.utc)
from typing import Optional, Dict, Any
from jose import jwt
from jose.exceptions import JWTError
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
import base64


class LocalAuthManager:
    """Local authentication manager for single-user setup"""

    def __init__(self):
        self.secret_key = os.getenv("LOCAL_AUTH_SECRET", "dev-secret-key-change-in-production")
        self.algorithm = "HS256"
        self.access_token_expire_minutes = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "30"))

    def create_access_token(self, data: Dict[str, Any], expires_delta: Optional[timedelta] = None) -> str:
        """Create JWT access token"""
        to_encode = data.copy()
        if expires_delta:
            expire = _utc_now() + expires_delta
        else:
            expire = _utc_now() + timedelta(minutes=self.access_token_expire_minutes)

        to_encode.update({"exp": expire, "type": "access"})
        encoded_jwt = jwt.encode(to_encode, self.secret_key, algorithm=self.algorithm)
        return encoded_jwt

    def verify_token(self, token: str) -> Optional[Dict[str, Any]]:
        """Verify and decode JWT token"""
        try:
            payload = jwt.decode(token, self.secret_key, algorithms=[self.algorithm])
            return payload
        except JWTError:
            return None


class SecurityMonitor:
    """Security monitoring and alerting"""

    def __init__(self):
        self.failed_attempts = {}
        self.rate_limits = {}
        self.max_failed_attempts = int(os.getenv("MAX_FAILED_ATTEMPTS", "5"))
        self.rate_limit_window = int(os.getenv("RATE_LIMIT_WINDOW_MINUTES", "15"))
        # Increased for development (React dev mode causes double renders)
        self.max_requests_per_window = int(os.getenv("MAX_REQUESTS_PER_WINDOW", "200"))

    def check_rate_limit(self, ip_address: str) -> bool:
        """Check if IP is rate limited"""
        # Disable rate limiting in development environment
        env = os.getenv("ENVIRONMENT", "").lower()
        if env == "development":
            return False

        # Disable rate limiting for localhost and Docker internal networks
        if ip_address in ["127.0.0.1", "localhost", "::1", "unknown"]:
            return False

        # Disable rate limiting for Docker bridge network IPs (172.x.x.x, 10.x.x.x)
        if ip_address.startswith("172.") or ip_address.startswith("10."):
            return False

        current_time = _utc_now()
        window_start = current_time - timedelta(minutes=self.rate_limit_window)

        if ip_address not in self.rate_limits:
            self.rate_limits[ip_address] = []

        # Clean old requests
        self.rate_limits[ip_address] = [
            t for t in self.rate_limits[ip_address] if t > window_start
        ]

        if len(self.rate_limits[ip_address]) >= self.max_requests_per_window:
            return True

        self.rate_limits[ip_address].append(current_time)
        return False

    def reset_rate_limit(self, ip_address: str = None):
        """Reset rate limit for specific IP or all IPs"""
        if ip_address:
            if ip_address in self.rate_limits:
                del self.rate_limits[ip_address]
        else:
            self.rate_limits.clear()

    def check_auth_failure(self, ip_address: str) -> bool:
        """Check if IP should be blocked due to failed auth attempts"""
        current_time = _utc_now()
        attempts = self.failed_attempts.get(ip_address, [])

        # Clean old attempts
        attempts = [t for t in attempts if current_time - t < timedelta(minutes=30)]

        if len(attempts) >= self.max_failed_attempts:
            return True

        self.failed_attempts[ip_address] = attempts
        return False

    def record_auth_failure(self, ip_address: str):
        """Record failed authentication attempt"""
        current_time = _utc_now()
        if ip_address not in self.failed_attempts:
            self.failed_attempts[ip_address] = []
        self.failed_attempts[ip_address].append(current_time)


# Global instances
auth_manager = LocalAuthManager()
security_monitor = SecurityMonitor()
