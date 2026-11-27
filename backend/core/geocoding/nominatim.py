"""
nominatim.py
------------
OpenStreetMap Nominatim implementation of `GeocodingProvider`. This is a
direct evolution of the original `main.py:geocode()` helper: same URL,
same User-Agent policy compliance, same underlying HTTP call -- but now
returns multiple ranked candidates instead of silently taking result[0],
and distinguishes timeout / no-results / bad-response failure modes so
callers can react appropriately (e.g. retry vs. surface to the customer).

Kept free/keyless for development, per the original project's tech-stack
rationale. For production-scale traffic, Nominatim's usage policy caps
requests (~1/sec) and prohibits heavy automated use -- swap this module
for `GoogleProvider` / `MapboxProvider` etc. behind the same interface
when that becomes necessary; nothing else in the codebase needs to change.
"""

import httpx

from .base import (
    GeocodeCandidate,
    GeocodeNoResults,
    GeocodeProviderError,
    GeocodeTimeout,
)

NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
NOMINATIM_HEADERS = {"User-Agent": "ai-digipin-address-intelligence/2.0"}
DEFAULT_TIMEOUT_SECONDS = 10.0


class NominatimProvider:
    def __init__(self, timeout: float = DEFAULT_TIMEOUT_SECONDS):
        self.timeout = timeout

    async def geocode(self, query: str, limit: int = 5):
        params = {
            "q": f"{query}, India",
            "format": "jsonv2",
            "limit": limit,
            "addressdetails": 0,
        }
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.get(
                    NOMINATIM_URL, params=params, headers=NOMINATIM_HEADERS
                )
        except httpx.TimeoutException as exc:
            raise GeocodeTimeout(
                f"Nominatim did not respond within {self.timeout}s."
            ) from exc
        except httpx.HTTPError as exc:
            raise GeocodeProviderError(f"Nominatim request failed: {exc}") from exc

        if response.status_code != 200:
            raise GeocodeProviderError(
                f"Nominatim returned status {response.status_code}."
            )

        try:
            results = response.json()
        except ValueError as exc:
            raise GeocodeProviderError("Nominatim returned malformed JSON.") from exc

        if not results:
            raise GeocodeNoResults(f"No geocoding match found for '{query}'.")

        candidates = []
        for item in results:
            try:
                candidates.append(
                    GeocodeCandidate(
                        latitude=float(item["lat"]),
                        longitude=float(item["lon"]),
                        importance=float(item.get("importance", 0.3)),
                        display_name=item.get("display_name", ""),
                    )
                )
            except (KeyError, TypeError, ValueError):
                continue  # skip a malformed row rather than fail the whole batch

        if not candidates:
            raise GeocodeNoResults(f"No usable geocoding match found for '{query}'.")

        return candidates
