# -*- coding: utf-8 -*-
"""
Security & Authentication Core:
- Password hashing with SHA-256 + Salt (No external C-compiler dependencies, 100% reliable on Windows)
- JWT Token encoding & decoding with HMAC-SHA256
"""

import os
import hashlib
import hmac
import base64
import json
import time
from typing import Optional, Dict, Any

# Secret key for JWT signature (In production, load from .env)
JWT_SECRET = os.getenv("JWT_SECRET_KEY", "")
if not JWT_SECRET:
    raise RuntimeError("Set JWT_SECRET_KEY in the local environment before starting the service.")
JWT_ALGORITHM = "HS256"
JWT_EXPIRATION_HOURS = 24

def hash_password(password: str, salt: Optional[str] = None) -> str:
    """Hash password using PBKDF2-HMAC-SHA256 with 100,000 iterations"""
    if not salt:
        salt = base64.b64encode(hashlib.sha256(str(time.time()).encode()).digest()[:16]).decode('utf-8')
    key = hashlib.pbkdf2_hmac('sha256', password.encode('utf-8'), salt.encode('utf-8'), 100000)
    return f"{salt}${base64.b64encode(key).decode('utf-8')}"

def verify_password(plain_password: str, stored_hash: str) -> bool:
    """Verify plain password against stored salt$hash"""
    try:
        if not stored_hash or '$' not in stored_hash:
            return False
        salt, key_b64 = stored_hash.split('$', 1)
        expected_key = hashlib.pbkdf2_hmac('sha256', plain_password.encode('utf-8'), salt.encode('utf-8'), 100000)
        return hmac.compare_digest(base64.b64encode(expected_key).decode('utf-8'), key_b64)
    except Exception:
        return False

def create_access_token(data: Dict[str, Any], expires_hours: int = JWT_EXPIRATION_HOURS) -> str:
    """Create a standard JWT token using HMAC-SHA256"""
    header = {"alg": JWT_ALGORITHM, "typ": "JWT"}
    payload = data.copy()
    payload["iat"] = int(time.time())
    payload["exp"] = int(time.time()) + (expires_hours * 3600)

    header_b64 = base64.urlsafe_b64encode(json.dumps(header).encode()).decode().rstrip('=')
    payload_b64 = base64.urlsafe_b64encode(json.dumps(payload).encode()).decode().rstrip('=')

    signature_input = f"{header_b64}.{payload_b64}".encode()
    signature = hmac.new(JWT_SECRET.encode(), signature_input, hashlib.sha256).digest()
    sig_b64 = base64.urlsafe_b64encode(signature).decode().rstrip('=')

    return f"{header_b64}.{payload_b64}.{sig_b64}"

def decode_access_token(token: str) -> Optional[Dict[str, Any]]:
    """Decode and verify JWT token"""
    try:
        parts = token.split('.')
        if len(parts) != 3:
            return None
        header_b64, payload_b64, sig_b64 = parts

        signature_input = f"{header_b64}.{payload_b64}".encode()
        expected_sig = hmac.new(JWT_SECRET.encode(), signature_input, hashlib.sha256).digest()
        actual_sig_b64 = sig_b64 + '=' * (-len(sig_b64) % 4)
        actual_sig = base64.urlsafe_b64decode(actual_sig_b64)

        if not hmac.compare_digest(expected_sig, actual_sig):
            return None

        # Decode payload
        payload_data_b64 = payload_b64 + '=' * (-len(payload_b64) % 4)
        payload = json.loads(base64.urlsafe_b64decode(payload_data_b64).decode())

        if payload.get("exp", 0) < time.time():
            return None # Expired

        return payload
    except Exception:
        return None

