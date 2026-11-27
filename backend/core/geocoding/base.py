"""
base.py
-------
Provider-agnostic geocoding interface. `main.py`'s original `geocode()`
helper called Nominatim directly and hardcoded a single top-1 result --
that's replaced by this `GeocodingProvider` protocol so a commercial
provider (Google, Mapbox, HERE, MapmyIndia) can be swapped in later by
adding one new file under `core/geocoding/`, without touching any calling
code in `api/v1/address.py`.

All providers return a list of `GeocodeCandidate`s (not just one), because
ambiguity detection (multiple plausible matches) is a first-class product
requirement, not an edge case to hide.
"""

from dataclasses import dataclass
from typing import List, Protocol


@dataclass
class GeocodeCandidate:
    latitude: float
    longitude: float
    importance: float  # 0-1 provider relevance score
    display_name: str

    def as_dict(self):
        return {
            "latitude": self.latitude,
            "longitude": self.longitude,
            "importance": round(self.importance, 3),
            "display_name": self.display_name,
        }


class GeocodeError(Exception):
    """Base class for all geocoding failures."""


class GeocodeTimeout(GeocodeError):
    """The provider did not respond within the configured timeout."""


class GeocodeNoResults(GeocodeError):
    """The provider returned zero matches for the query."""


class GeocodeProviderError(GeocodeError):
    """The provider responded with a non-success status or malformed data."""


class GeocodingProvider(Protocol):
    """Structural interface every geocoding backend must satisfy."""

    async def geocode(self, query: str, limit: int = 5) -> List[GeocodeCandidate]:
        """
        Look up `query` and return up to `limit` candidates, ranked by the
        provider's own relevance ordering (best match first). Raises
        GeocodeTimeout / GeocodeNoResults / GeocodeProviderError on failure
        -- never returns an empty list silently.
        """
        ...
