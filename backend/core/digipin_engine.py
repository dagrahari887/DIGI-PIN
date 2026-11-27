"""
digipin_engine.py
------------------
Implements the Department of Posts / IIT Hyderabad DIGIPIN specification:
a recursive 4x4 grid subdivision of the Indian landmass bounding box that
narrows down to a ~4m x 4m cell after 10 levels of recursion, producing a
10-character alphanumeric code.

The core idea: start with a big rectangle (the whole DIGIPIN bounding box).
Split it into a 4x4 grid of 16 sub-rectangles. Find which sub-rectangle
contains the point. Record the symbol for that cell. Then treat that
sub-rectangle as the new bounding box and repeat, 10 times total.

Because each level narrows both latitude and longitude ranges by a factor
of 4, and we do this 10 times, the final cell is roughly:
    (38.5 - 2.5)  / 4**10 degrees latitude  ~= 3.4 meters
    (99.5 - 63.5) / 4**10 degrees longitude ~= 3.1 meters
i.e. approximately a 4m x 4m footprint, which is where the "4m grid"
precision claim comes from.

Decoding simply replays the same recursion: at each level, look up which
row/col the symbol maps to and shrink the bounding box accordingly. After
10 levels, the remaining tiny bounding box IS the DIGIPIN cell.
"""

from dataclasses import dataclass

# ---------------------------------------------------------------------------
# Official DIGIPIN bounding box: covers the Indian landmass with margin.
# ---------------------------------------------------------------------------
MIN_LAT = 2.5
MAX_LAT = 38.5
MIN_LON = 63.5
MAX_LON = 99.5

# ---------------------------------------------------------------------------
# The 4x4 symbol grid. Row 0 = northernmost band, Row 3 = southernmost band.
# Col 0 = westernmost band, Col 3 = easternmost band.
# This exact layout (and the resulting code) is what the Dept. of Posts
# reference implementation produces.
# ---------------------------------------------------------------------------
DIGIPIN_GRID = [
    ["F", "C", "9", "8"],
    ["J", "3", "2", "7"],
    ["K", "4", "5", "6"],
    ["L", "M", "P", "T"],
]

# Reverse lookup: symbol -> (row, col)
_SYMBOL_TO_ROWCOL = {
    symbol: (r, c)
    for r, row in enumerate(DIGIPIN_GRID)
    for c, symbol in enumerate(row)
}

TOTAL_LEVELS = 10


class DigipinError(ValueError):
    """Raised when a DIGIPIN cannot be encoded or decoded."""


@dataclass
class BoundingBox:
    min_lat: float
    max_lat: float
    min_lon: float
    max_lon: float

    @property
    def center(self):
        return (
            (self.min_lat + self.max_lat) / 2,
            (self.min_lon + self.max_lon) / 2,
        )

    def as_dict(self):
        return {
            "min_lat": round(self.min_lat, 8),
            "max_lat": round(self.max_lat, 8),
            "min_lon": round(self.min_lon, 8),
            "max_lon": round(self.max_lon, 8),
        }


def _format_code(raw: str) -> str:
    """Insert the two DIGIPIN separators: XXX-XXX-XXXX."""
    return f"{raw[0:3]}-{raw[3:6]}-{raw[6:10]}"


def encode(lat: float, lon: float) -> str:
    """
    Encode a WGS84 lat/lon pair into a formatted 10-character DIGIPIN,
    e.g. "39J-49L-L8T4".
    """
    if not (MIN_LAT <= lat <= MAX_LAT):
        raise DigipinError(
            f"Latitude {lat} is outside the DIGIPIN coverage area "
            f"({MIN_LAT} to {MAX_LAT})."
        )
    if not (MIN_LON <= lon <= MAX_LON):
        raise DigipinError(
            f"Longitude {lon} is outside the DIGIPIN coverage area "
            f"({MIN_LON} to {MAX_LON})."
        )

    min_lat, max_lat = MIN_LAT, MAX_LAT
    min_lon, max_lon = MIN_LON, MAX_LON
    code_chars = []

    for _ in range(TOTAL_LEVELS):
        lat_step = (max_lat - min_lat) / 4
        lon_step = (max_lon - min_lon) / 4

        # Row 0 is the NORTH band, so we count down from max_lat.
        row = 3 - min(int((lat - min_lat) / lat_step), 3)
        col = min(int((lon - min_lon) / lon_step), 3)

        code_chars.append(DIGIPIN_GRID[row][col])

        # Shrink the bounding box to the chosen cell for the next level.
        new_max_lat = max_lat - row * lat_step
        new_min_lat = new_max_lat - lat_step
        new_min_lon = min_lon + col * lon_step
        new_max_lon = new_min_lon + lon_step

        min_lat, max_lat = new_min_lat, new_max_lat
        min_lon, max_lon = new_min_lon, new_max_lon

    return _format_code("".join(code_chars))


def decode(digipin: str) -> BoundingBox:
    """
    Decode a DIGIPIN (with or without dashes) back into the bounding box
    of its 4m x 4m grid cell.
    """
    raw = digipin.replace("-", "").strip().upper()
    if len(raw) != TOTAL_LEVELS:
        raise DigipinError(
            f"A DIGIPIN must contain {TOTAL_LEVELS} characters, got {len(raw)}."
        )

    min_lat, max_lat = MIN_LAT, MAX_LAT
    min_lon, max_lon = MIN_LON, MAX_LON

    for char in raw:
        if char not in _SYMBOL_TO_ROWCOL:
            raise DigipinError(f"'{char}' is not a valid DIGIPIN symbol.")

        row, col = _SYMBOL_TO_ROWCOL[char]
        lat_step = (max_lat - min_lat) / 4
        lon_step = (max_lon - min_lon) / 4

        new_max_lat = max_lat - row * lat_step
        new_min_lat = new_max_lat - lat_step
        new_min_lon = min_lon + col * lon_step
        new_max_lon = new_min_lon + lon_step

        min_lat, max_lat = new_min_lat, new_max_lat
        min_lon, max_lon = new_min_lon, new_max_lon

    return BoundingBox(min_lat, max_lat, min_lon, max_lon)


if __name__ == "__main__":
    # Quick self-test: encode a point, decode it back, and confirm the
    # original point falls inside the reconstructed bounding box.
    test_lat, test_lon = 28.6139, 77.2090  # New Delhi (Connaught Place area)
    code = encode(test_lat, test_lon)
    box = decode(code)
    print(f"Point:   ({test_lat}, {test_lon})")
    print(f"DIGIPIN: {code}")
    print(f"Cell:    {box.as_dict()}")
    assert box.min_lat <= test_lat <= box.max_lat
    assert box.min_lon <= test_lon <= box.max_lon
    print("Round-trip OK.")
