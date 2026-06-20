"""API authentication and multi-tenant isolation."""

from __future__ import annotations

import os
import secrets
from contextvars import ContextVar
from dataclasses import dataclass
from typing import Optional

from fastapi import HTTPException, Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

tenant_id_ctx: ContextVar[Optional[str]] = ContextVar("tenant_id", default=None)


@dataclass
class AuthConfig:
    api_key: Optional[str] = None
    enabled: bool = False

    @classmethod
    def from_env(cls) -> AuthConfig:
        key = os.environ.get("MESH_API_KEY")
        enabled = os.environ.get("MESH_AUTH_ENABLED", "").lower() in ("1", "true", "yes")
        if key:
            enabled = True
        return cls(api_key=key, enabled=enabled)

    def validate_key(self, provided: Optional[str]) -> bool:
        if not self.enabled:
            return True
        if not self.api_key or not provided:
            return False
        return secrets.compare_digest(provided, self.api_key)


def extract_api_key(request: Request) -> Optional[str]:
    auth = request.headers.get("Authorization", "")
    if auth.lower().startswith("bearer "):
        return auth[7:].strip()
    return request.headers.get("X-API-Key")


class AuthMiddleware(BaseHTTPMiddleware):
    """Require API key on /api/* when auth is enabled."""

    def __init__(self, app, config: AuthConfig):
        super().__init__(app)
        self.config = config

    async def dispatch(self, request: Request, call_next):
        tenant = request.headers.get("X-Tenant-Id")
        token = tenant_id_ctx.set(tenant)

        if request.url.path.startswith("/api/") and self.config.enabled:
            key = extract_api_key(request)
            if not self.config.validate_key(key):
                return JSONResponse(
                    status_code=401,
                    content={"detail": "Invalid or missing API key"},
                )

        try:
            return await call_next(request)
        finally:
            tenant_id_ctx.reset(token)


def get_current_tenant() -> Optional[str]:
    return tenant_id_ctx.get()
