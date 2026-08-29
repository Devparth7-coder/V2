"""
VayuSutra APIx - Lightweight India Route Map Coordinates
Approximate airport city centroids (lat/lon) used for a lightweight SVG route map.
These are public airport location coordinates, not fabricated market data.
"""
from typing import Dict, Tuple, List

# Approximate coordinates (lat, lon) of the DGCA Top-20 endpoint airports
AIRPORT_COORDS: Dict[str, Tuple[float, float]] = {
    "DEL": (28.5562, 77.1000),   # New Delhi (IGI)
    "BOM": (19.0896, 72.8656),   # Mumbai (CSMIA)
    "BLR": (13.1986, 77.7066),   # Bengaluru (KIA)
    "CCU": (22.6547, 88.4467),   # Kolkata (NSCBI)
    "HYD": (17.2403, 78.4294),   # Hyderabad (RGIA)
    "MAA": (12.9941, 80.1709),   # Chennai (MAA)
    "GOI": (15.3808, 73.8314),   # Goa (Dabolim/GOI)
    "PNQ": (18.5793, 73.9089),   # Pune (PNQ)
}

CITY_NAMES: Dict[str, str] = {
    "DEL": "New Delhi", "BOM": "Mumbai", "BLR": "Bengaluru",
    "CCU": "Kolkata", "HYD": "Hyderabad", "MAA": "Chennai",
    "GOI": "Goa", "PNQ": "Pune",
}

# Normalized map projection (lon -> x in [0,100], lat -> y in [0,100]) using a simple
# equirectangular fit around India's extent so the SVG map looks correct.
# India lon ~ [68, 97], lat ~ [8, 36]
LON_MIN, LON_MAX = 68.0, 97.5
LAT_MIN, LAT_MAX = 7.0, 36.5


def to_map_xy(lon: float, lat: float) -> Tuple[float, float]:
    x = (lon - LON_MIN) / (LON_MAX - LON_MIN) * 100.0
    y = (LAT_MAX - lat) / (LAT_MAX - LAT_MIN) * 100.0
    return round(x, 2), round(y, 2)


def route_segments() -> List[Dict[str, object]]:
    """Return list of {route, origin, destination, x1,y1,x2,y2} for the map."""
    segments = []
    from ..config.routes import DGCA_TOP_20_ROUTES
    for r in DGCA_TOP_20_ROUTES:
        o = AIRPORT_COORDS.get(r.origin)
        d = AIRPORT_COORDS.get(r.destination)
        if not o or not d:
            continue
        x1, y1 = to_map_xy(o[1], o[0])
        x2, y2 = to_map_xy(d[1], d[0])
        segments.append({
            "route": r.route_code,
            "origin": r.origin,
            "destination": r.destination,
            "x1": x1, "y1": y1, "x2": x2, "y2": y2,
            "city_from": CITY_NAMES.get(r.origin, r.origin),
            "city_to": CITY_NAMES.get(r.destination, r.destination),
        })
    return segments
