"""
deps.py
-------
FastAPI dependencies for B2B readiness: API-key auth (tenant-aware) and a
simple in-memory rate limiter.

Both are intentionally minimal, honest implementations rather than a
fully-featured auth/rate-limit system:
  - Auth: a static `X-API-Key` header mapped to a tenant ID via the
    `API_KEYS` env var. No sessions, no OAuth -- appropriate for
    server-to-server B2B integration, not a public consumer product.
  - Rate limiting: a per-process in-memory token bucket. This resets on
    restart and does NOT work across multiple server instances -- it's a
    structural placeholder that demonstrates where a shared store (Redis)
    plugs in for real multi-instance deployments, documented in the
    README's production roadmap rather than pretended away here.

If no API keys are configured (`API_KEYS` unset), auth is bypassed and a
warning is logged once at startup -- this keeps local development frictionless
without ever silently disabling auth in an environment that configured it.
"""

import time
from collections import defaultdict
from dataclasses import dataclass
from typing import Optional

from fastapi import Header, HTTPException, Request

from config import settings
from logging_config import get_logger

logger = get_logger("api.deps")


@dataclass
class TenantContext:
    tenant_id: str
    api_key: Optional[str]


async def get_tenant(x_api_key: Optional[str] = Header(default=None, alias="X-API-Key")) -> TenantContext:
    if not settings.auth_enabled():
        return TenantContext(tenant_id="dev", api_key=None)

    keys = settings.api_keys()
    if not x_api_key or x_api_key not in keys:
        raise HTTPException(status_code=401, detail="Missing or invalid X-API-Key header.")

    return TenantContext(tenant_id=keys[x_api_key], api_key=x_api_key)


# ---------------------------------------------------------------------------
# In-memory rate limiter (per-process; swap for Redis/API-gateway limiting
# before running multiple instances in production)
# ---------------------------------------------------------------------------

_request_log: dict = defaultdict(list)  # tenant_id -> [timestamps]
_WINDOW_SECONDS = 60


async def enforce_rate_limit(request: Request, tenant: TenantContext = None) -> None:
    """Call from an endpoint (or wire as a dependency) to apply a simple
    sliding-window rate limit per tenant."""
    tenant_id = tenant.tenant_id if tenant else "anonymous"
    now = time.monotonic()
    window_start = now - _WINDOW_SECONDS

    log = _request_log[tenant_id]
    while log and log[0] < window_start:
        log.pop(0)

    if len(log) >= settings.rate_limit_requests_per_minute:
        raise HTTPException(
            status_code=429,
            detail=f"Rate limit exceeded ({settings.rate_limit_requests_per_minute} requests/minute).",
        )

    log.append(now)
