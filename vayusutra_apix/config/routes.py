"""
VayuSutra APIx - DGCA Route Basket & Metainformation Specification
Compliant with Ministry of Statistics and Programme Implementation (MoSPI),
National Statistical Office (NSO), Reserve Bank of India (RBI), and DGCA standards.
"""

from dataclasses import dataclass
from typing import Dict, List, Optional


@dataclass(frozen=True)
class RouteDefinition:
    """Metainformation for a DGCA Top-20 Domestic City-Pair Route."""
    route_code: str          # e.g., "DEL-BOM"
    origin: str              # e.g., "DEL"
    destination: str         # e.g., "BOM"
    origin_city: str         # e.g., "New Delhi"
    destination_city: str    # e.g., "Mumbai"
    weight: float            # DGCA national volume weight (sums strictly to 1.0)
    distance_km: int         # Aerial distance in kilometers
    is_metro_metro: bool     # Metro-to-metro corridor classification
    base_fare_benchmark: float  # Base period benchmark fare (INR) for Base Index = 100.0


@dataclass(frozen=True)
class AdvanceWindowDefinition:
    """Metainformation for Advance Purchase Horizons."""
    window_id: str           # e.g., "T+1"
    days_advance: int        # Days from booking date to travel date
    name: str                # Horizon descriptive name
    weight: float            # Composite aggregation weight (sums strictly to 1.0)
    description: str         # Economic booking context


@dataclass(frozen=True)
class AirlineDefinition:
    """Airline carrier metainformation and domestic market share."""
    code: str                # IATA code (e.g. "6E")
    name: str                # Full airline name
    market_share: float      # DGCA domestic passenger market share
    category: str            # LCC (Low-Cost Carrier) or FSC (Full-Service Carrier)
    base_multiplier: float   # Tiering price multiplier (e.g. 1.15 for FSC)


# ---------------------------------------------------------------------------
# 1. DGCA TOP 20 DOMESTIC CITY-PAIRS (Normalized so weights sum strictly to 1.0000)
# ---------------------------------------------------------------------------
DGCA_TOP_20_ROUTES: List[RouteDefinition] = [
    RouteDefinition(
        route_code="DEL-BOM", origin="DEL", destination="BOM",
        origin_city="New Delhi", destination_city="Mumbai",
        weight=0.1092, distance_km=1148, is_metro_metro=True,
        base_fare_benchmark=4850.0
    ),
    RouteDefinition(
        route_code="BOM-DEL", origin="BOM", destination="DEL",
        origin_city="Mumbai", destination_city="New Delhi",
        weight=0.1073, distance_km=1148, is_metro_metro=True,
        base_fare_benchmark=4850.0
    ),
    RouteDefinition(
        route_code="DEL-BLR", origin="DEL", destination="BLR",
        origin_city="New Delhi", destination_city="Bengaluru",
        weight=0.0805, distance_km=1708, is_metro_metro=True,
        base_fare_benchmark=5650.0
    ),
    RouteDefinition(
        route_code="BLR-DEL", origin="BLR", destination="DEL",
        origin_city="Bengaluru", destination_city="New Delhi",
        weight=0.0785, distance_km=1708, is_metro_metro=True,
        base_fare_benchmark=5650.0
    ),
    RouteDefinition(
        route_code="BOM-BLR", origin="BOM", destination="BLR",
        origin_city="Mumbai", destination_city="Bengaluru",
        weight=0.0584, distance_km=842, is_metro_metro=True,
        base_fare_benchmark=3950.0
    ),
    RouteDefinition(
        route_code="BLR-BOM", origin="BLR", destination="BOM",
        origin_city="Bengaluru", destination_city="Mumbai",
        weight=0.0575, distance_km=842, is_metro_metro=True,
        base_fare_benchmark=3950.0
    ),
    RouteDefinition(
        route_code="DEL-CCU", origin="DEL", destination="CCU",
        origin_city="New Delhi", destination_city="Kolkata",
        weight=0.0498, distance_km=1305, is_metro_metro=True,
        base_fare_benchmark=4950.0
    ),
    RouteDefinition(
        route_code="CCU-DEL", origin="CCU", destination="DEL",
        origin_city="Kolkata", destination_city="New Delhi",
        weight=0.0489, distance_km=1305, is_metro_metro=True,
        base_fare_benchmark=4950.0
    ),
    RouteDefinition(
        route_code="DEL-HYD", origin="DEL", destination="HYD",
        origin_city="New Delhi", destination_city="Hyderabad",
        weight=0.0460, distance_km=1253, is_metro_metro=True,
        base_fare_benchmark=4650.0
    ),
    RouteDefinition(
        route_code="HYD-DEL", origin="HYD", destination="DEL",
        origin_city="Hyderabad", destination_city="New Delhi",
        weight=0.0450, distance_km=1253, is_metro_metro=True,
        base_fare_benchmark=4650.0
    ),
    RouteDefinition(
        route_code="BLR-HYD", origin="BLR", destination="HYD",
        origin_city="Bengaluru", destination_city="Hyderabad",
        weight=0.0402, distance_km=501, is_metro_metro=True,
        base_fare_benchmark=3250.0
    ),
    RouteDefinition(
        route_code="HYD-BLR", origin="HYD", destination="BLR",
        origin_city="Hyderabad", destination_city="Bengaluru",
        weight=0.0393, distance_km=501, is_metro_metro=True,
        base_fare_benchmark=3250.0
    ),
    RouteDefinition(
        route_code="MAA-DEL", origin="MAA", destination="DEL",
        origin_city="Chennai", destination_city="New Delhi",
        weight=0.0364, distance_km=1756, is_metro_metro=True,
        base_fare_benchmark=5750.0
    ),
    RouteDefinition(
        route_code="DEL-MAA", origin="DEL", destination="MAA",
        origin_city="New Delhi", destination_city="Chennai",
        weight=0.0354, distance_km=1756, is_metro_metro=True,
        base_fare_benchmark=5750.0
    ),
    RouteDefinition(
        route_code="BOM-GOI", origin="BOM", destination="GOI",
        origin_city="Mumbai", destination_city="Goa",
        weight=0.0335, distance_km=435, is_metro_metro=False,
        base_fare_benchmark=3100.0
    ),
    RouteDefinition(
        route_code="GOI-BOM", origin="GOI", destination="BOM",
        origin_city="Goa", destination_city="Mumbai",
        weight=0.0326, distance_km=435, is_metro_metro=False,
        base_fare_benchmark=3100.0
    ),
    RouteDefinition(
        route_code="DEL-PNQ", origin="DEL", destination="PNQ",
        origin_city="New Delhi", destination_city="Pune",
        weight=0.0278, distance_km=1173, is_metro_metro=False,
        base_fare_benchmark=4550.0
    ),
    RouteDefinition(
        route_code="PNQ-DEL", origin="PNQ", destination="DEL",
        origin_city="Pune", destination_city="New Delhi",
        weight=0.0268, distance_km=1173, is_metro_metro=False,
        base_fare_benchmark=4550.0
    ),
    RouteDefinition(
        route_code="BOM-CCU", origin="BOM", destination="CCU",
        origin_city="Mumbai", destination_city="Kolkata",
        weight=0.0239, distance_km=1654, is_metro_metro=True,
        base_fare_benchmark=5450.0
    ),
    RouteDefinition(
        route_code="CCU-BOM", origin="CCU", destination="BOM",
        origin_city="Kolkata", destination_city="Mumbai",
        weight=0.0230, distance_km=1654, is_metro_metro=True,
        base_fare_benchmark=5450.0
    ),
]

# ---------------------------------------------------------------------------
# 2. ADVANCE PURCHASE HORIZONS (5 Windows, Weights sum strictly to 1.0000)
# ---------------------------------------------------------------------------
ADVANCE_PURCHASE_WINDOWS: List[AdvanceWindowDefinition] = [
    AdvanceWindowDefinition(
        window_id="T+1", days_advance=1, name="Spot / Emergency",
        weight=0.2200, description="Emergency and immediate spot bookings (<24h to departure)"
    ),
    AdvanceWindowDefinition(
        window_id="T+7", days_advance=7, name="Urgent Business",
        weight=0.3400, description="Short-notice corporate and urgent business travel"
    ),
    AdvanceWindowDefinition(
        window_id="T+15", days_advance=15, name="Standard Planned",
        weight=0.2400, description="Standard corporate and pre-planned individual travel"
    ),
    AdvanceWindowDefinition(
        window_id="T+30", days_advance=30, name="Planned Leisure",
        weight=0.1400, description="Leisure, holiday, and vacation family bookings"
    ),
    AdvanceWindowDefinition(
        window_id="T+45", days_advance=45, name="Early Bird",
        weight=0.0600, description="Advance promotional and discounted baseline bookings"
    ),
]

# ---------------------------------------------------------------------------
# 3. DOMESTIC AIRLINE MARKET SHARE DISTRIBUTION (DGCA)
# ---------------------------------------------------------------------------
AIRLINE_MARKET_SHARES: List[AirlineDefinition] = [
    AirlineDefinition(code="6E", name="IndiGo", market_share=0.625, category="LCC", base_multiplier=1.00),
    AirlineDefinition(code="AI", name="Air India", market_share=0.145, category="FSC", base_multiplier=1.16),
    AirlineDefinition(code="IX", name="Air India Express", market_share=0.075, category="LCC", base_multiplier=0.98),
    AirlineDefinition(code="QP", name="Akasa Air", market_share=0.048, category="LCC", base_multiplier=0.95),
    AirlineDefinition(code="SG", name="SpiceJet", market_share=0.032, category="LCC", base_multiplier=0.94),
    AirlineDefinition(code="OTHER", name="Alliance/Regional", market_share=0.075, category="Regional", base_multiplier=1.02),
]

# ---------------------------------------------------------------------------
# 4. STATUTORY TAXES, FEES & SURCHARGES SPECIFICATION
# ---------------------------------------------------------------------------
TAX_RULES = {
    "gst_rate_economy": 0.05,            # 5% GST on Economy (Base + Fuel Surcharge)
    "gst_rate_business": 0.12,           # 12% GST on Business Class
    "aviation_security_fee_asf": 200.0,  # ASF standard Rs. 200 per passenger
    "passenger_service_fee_psf": 91.0,   # PSF average Rs. 91 per passenger
    "metro_udf_avg": 420.0,              # Metro User Development Fee avg Rs. 420
    "non_metro_udf_avg": 260.0,          # Non-Metro User Development Fee avg Rs. 260
    "ota_convenience_fee_min": 249.0,    # Min OTA convenience fee
    "ota_convenience_fee_max": 349.0,    # Max OTA convenience fee
    "ota_convenience_fee_avg": 299.0,    # Avg OTA convenience fee
    "direct_convenience_fee": 0.0,       # Direct airline web booking fee / waiver
}

# ---------------------------------------------------------------------------
# 5. CPI BASKET LINKAGE PARAMETERS (MoSPI / NSO CPI Base 2012=100)
# ---------------------------------------------------------------------------
CPI_WEIGHTS = {
    # Transport & Communication sub-group national weight in Headline All-India CPI
    "transport_and_communication_cpi_weight": 0.0859,  # 8.59%
    # Airfare component weight within the Transport & Communication sub-group
    "airfare_share_within_transport": 0.0385,          # 3.85%
    # Effective Headline CPI weight for Air Travel (0.0859 * 0.0385 = ~0.3307%)
    "effective_headline_cpi_weight": 0.0859 * 0.0385,  # 0.00330715
    # Price elasticity of domestic air passenger demand (substitution parameter for Paasche)
    "demand_price_elasticity": -0.85,
}

# Pre-computed map for fast lookup
ROUTE_LOOKUP: Dict[str, RouteDefinition] = {r.route_code: r for r in DGCA_TOP_20_ROUTES}
WINDOW_LOOKUP: Dict[str, AdvanceWindowDefinition] = {w.window_id: w for w in ADVANCE_PURCHASE_WINDOWS}
AIRLINE_LOOKUP: Dict[str, AirlineDefinition] = {a.code: a for a in AIRLINE_MARKET_SHARES}

# Advance purchase window benchmark multipliers for base period calculation
ADVANCE_BENCHMARK_MULTIPLIERS = {
    "T+1": 2.45,
    "T+7": 1.60,
    "T+15": 1.18,
    "T+30": 1.00,
    "T+45": 0.92,
}

# Baseline period composite benchmarks (P0) for each route and advance window
# Incorporates baseline base fare + statutory airport taxes and standard GST
BASE_PERIOD_BENCHMARKS: Dict[str, Dict[str, float]] = {}
for r in DGCA_TOP_20_ROUTES:
    BASE_PERIOD_BENCHMARKS[r.route_code] = {}
    for w in ADVANCE_PURCHASE_WINDOWS:
        mult = ADVANCE_BENCHMARK_MULTIPLIERS[w.window_id]
        base_plus_fuel = r.base_fare_benchmark * mult
        asf = TAX_RULES["aviation_security_fee_asf"]
        psf = TAX_RULES["passenger_service_fee_psf"]
        udf = TAX_RULES["metro_udf_avg"] if r.is_metro_metro else TAX_RULES["non_metro_udf_avg"]
        gst = base_plus_fuel * TAX_RULES["gst_rate_economy"]
        gross_benchmark = round(base_plus_fuel + asf + psf + udf + gst, 2)
        BASE_PERIOD_BENCHMARKS[r.route_code][w.window_id] = gross_benchmark


def get_route_by_code(code: str) -> Optional[RouteDefinition]:
    """Retrieve route metadata by route code (e.g., 'DEL-BOM')."""
    return ROUTE_LOOKUP.get(code.upper())


def get_all_route_codes() -> List[str]:
    """Return list of all 20 DGCA route codes."""
    return [r.route_code for r in DGCA_TOP_20_ROUTES]


def validate_basket_weights() -> bool:
    """
    Ensure DGCA route weights and advance window weights strictly sum to 1.0 within float tolerance.
    """
    route_sum = sum(r.weight for r in DGCA_TOP_20_ROUTES)
    window_sum = sum(w.weight for w in ADVANCE_PURCHASE_WINDOWS)
    
    assert abs(route_sum - 1.0) < 1e-6, f"Route weights sum to {route_sum}, expected 1.0000"
    assert abs(window_sum - 1.0) < 1e-6, f"Window weights sum to {window_sum}, expected 1.0000"
    return True


# Run validation upon import
validate_basket_weights()
