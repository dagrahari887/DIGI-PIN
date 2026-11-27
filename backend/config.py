"""
config.py
---------
Environment-driven settings. Deliberately plain `os.environ` reads (not
`pydantic-settings`) to avoid an extra dependency for something this
simple. No secret ever has a hardcoded default -- anything sensitive
defaults to empty/disabled and the app degrades to an explicit dev-mode
warning rather than silently using a placeholder secret.

Copy `.env.example` to `.env` and fill in real values for anything beyond
local development.
"""

import os
from dataclasses import dataclass, field
from typing import List


def _split_csv(value: str) -> List[str]:
    return [v.strip() for v in value.split(",") if v.strip()]


@dataclass
class Settings:
    # --- API keys / tenancy -------------------------------------------------
    # Format: "tenant_id:key,tenant_id:key". Empty in dev -> auth is
    # bypassed with a loud warning logged once at startup (see main.py).
    api_keys_raw: str = field(default_factory=lambda: os.environ.get("API_KEYS", ""))

    # --- CORS -----------------------------------------------------------------
    cors_allow_origins: List[str] = field(
        default_factory=lambda: _split_csv(os.environ.get("CORS_ALLOW_ORIGINS", "*"))
    )

    # --- Geocoding --------------------------------------------------------
    geocoding_provider: str = field(
        default_factory=lambda: os.environ.get("GEOCODING_PROVIDER", "nominatim")
    )
    geocode_timeout_seconds: float = field(
        default_factory=lambda: float(os.environ.get("GEOCODE_TIMEOUT_SECONDS", "10.0"))
    )

    # --- Rate limiting (in-memory; swap for Redis in production) ----------
    rate_limit_requests_per_minute: int = field(
        default_factory=lambda: int(os.environ.get("RATE_LIMIT_RPM", "60"))
    )

    # --- Logging ------------------------------------------------------------
    log_level: str = field(default_factory=lambda: os.environ.get("LOG_LEVEL", "INFO"))
    log_full_address_text: bool = field(
        default_factory=lambda: os.environ.get("LOG_FULL_ADDRESS_TEXT", "false").lower() == "true"
    )

    def api_keys(self) -> dict:
        """Returns {api_key: tenant_id}."""
        keys = {}
        for pair in _split_csv(self.api_keys_raw):
            if ":" not in pair:
                continue
            tenant_id, key = pair.split(":", 1)
            keys[key.strip()] = tenant_id.strip()
        return keys

    def auth_enabled(self) -> bool:
        return bool(self.api_keys())


settings = Settings()
