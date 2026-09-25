import os
import secrets
from dataclasses import dataclass
from typing import Optional, Dict
from datetime import datetime, timedelta

@dataclass
class User:
    user_id: str
    username: str
    role: str = "researcher"

class AuthService:
    def __init__(self):
        # In a real system, this would be a DB. For MVP, we use a simple map.
        # We'll seed one admin user.
        self._tokens: Dict[str, Dict] = {}
        self._users = {
            "admin": User(user_id="u1", username="admin", role="admin")
        }
        # For demo purposes, we allow a simple "demo-token"
        self._demo_token = "demo-token-12345"

    def authenticate(self, username, password):
        # Demo auth: accept any password for "admin" in dev mode
        if username == "admin":
            token = secrets.token_urlsafe(32)
            expiry = datetime.utcnow() + timedelta(hours=24)
            self._tokens[token] = {"user_id": "u1", "expiry": expiry}
            return token, self._users["admin"]
        return None, None

    def validate_token(self, token: str) -> Optional[User]:
        if token == self._demo_token:
            return self._users["admin"]
        
        token_data = self._tokens.get(token)
        if not token_data:
            return None
        
        if datetime.utcnow() > token_data["expiry"]:
            del self._tokens[token]
            return None
            
        return self._users["admin"] # Simplified for MVP: all tokens map to admin

auth_service = AuthService()
