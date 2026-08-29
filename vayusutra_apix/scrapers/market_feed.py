"""
VayuSutra APIx - High-Fidelity Econometric Market Simulator
Generates dynamic airline quotes with calibrated advance yield curves, day-of-week surges,
carrier tiering, seasonal ATF fuel drift, and statistical outliers for rigorous validation.
"""

import datetime
import math
import random
import uuid
from dataclasses import dataclass
from typing import Dict, List, Any, Optional

from ..config.routes import (
    DGCA_TOP_20_ROUTES,
    ADVANCE_PURCHASE_WINDOWS,
    AIRLINE_MARKET_SHARES,
    TAX_RULES,
    RouteDefinition,
    AdvanceWindowDefinition,
    AirlineDefinition,
)


@dataclass
class SimulationConfig:
    """Configurable parameters for synthetic econometric feed generation."""
    seed: Optional[int] = 42
    anomaly_rate: float = 0.015       # 1.5% intentional statistical outliers
    multi_ota_ratio: float = 0.65     # 65% of flights appear on both Direct & OTAs
    atf_trend_drift: float = 0.0012   # Fuel drift per day across time series
    enable_noise: bool = True


class MarketFeedGenerator:
    """
    Simulates high-frequency transaction quotes across India's domestic aviation network.
    """

    def __init__(self, config: Optional[SimulationConfig] = None):
        self.config = config or SimulationConfig()
        if self.config.seed is not None:
            random.seed(self.config.seed)

    def _get_advance_multiplier(self, window_id: str) -> float:
        """
        Calibrated non-linear yield curve based on DGCA empirical pricing distributions.
        """
        if window_id == "T+1":
            return random.uniform(2.20, 3.15)
        elif window_id == "T+7":
            return random.uniform(1.45, 1.85)
        elif window_id == "T+15":
            return random.uniform(1.10, 1.28)
        elif window_id == "T+30":
            return random.uniform(0.96, 1.06)
        elif window_id == "T+45":
            return random.uniform(0.88, 0.96)
        return 1.00

    def _get_day_of_week_multiplier(self, travel_date: datetime.date) -> float:
        """
        Day-of-week demand surges in Indian domestic aviation.
        0=Mon, 1=Tue, 2=Wed, 3=Thu, 4=Fri, 5=Sat, 6=Sun
        """
        weekday = travel_date.weekday()
        if weekday == 4:  # Friday evening surge
            return random.uniform(1.15, 1.24)
        elif weekday == 6:  # Sunday return surge
            return random.uniform(1.18, 1.28)
        elif weekday in (1, 2):  # Tuesday / Wednesday low-trough
            return random.uniform(0.90, 0.93)
        elif weekday == 0:  # Monday morning business
            return random.uniform(1.02, 1.08)
        else:
            return random.uniform(0.98, 1.03)

    def _get_carrier_multiplier(self, airline: AirlineDefinition) -> float:
        """Carrier tiering: Full-Service (AI) vs Low-Cost (6E, QP, SG)."""
        if airline.category == "FSC":
            return random.uniform(1.12, 1.20)
        elif airline.code == "6E":
            return random.uniform(0.99, 1.02)
        elif airline.code in ("QP", "SG"):
            return random.uniform(0.92, 0.97)
        elif airline.code == "IX":
            return random.uniform(0.96, 1.01)
        return random.uniform(0.98, 1.02)

    def _calculate_tax_components(self, base_and_fuel: float, is_ota: bool = False) -> Dict[str, float]:
        """Statutory tax breakdown adhering to MoSPI / DGCA airline accounting standards."""
        asf = TAX_RULES["aviation_security_fee_asf"]
        psf = TAX_RULES["passenger_service_fee_psf"]
        udf = TAX_RULES["metro_udf_avg"]
        gst = round(base_and_fuel * TAX_RULES["gst_rate_economy"], 2)
        
        convenience_fee = round(
            random.uniform(TAX_RULES["ota_convenience_fee_min"], TAX_RULES["ota_convenience_fee_max"])
            if is_ota else TAX_RULES["direct_convenience_fee"], 2
        )

        base_fare = round(base_and_fuel * 0.65, 2)
        fuel_surcharge = round(base_and_fuel * 0.35, 2)
        total_fare = round(base_fare + fuel_surcharge + udf + psf + asf + gst + convenience_fee, 2)

        return {
            "base_fare": base_fare,
            "fuel_surcharge": fuel_surcharge,
            "udf": udf,
            "psf": psf,
            "asf": asf,
            "gst": gst,
            "convenience_fee": convenience_fee,
            "total_fare": total_fare,
        }

    def generate_quotes_for_date(
        self,
        booking_date: datetime.date,
        day_index: int = 0
    ) -> List[Dict[str, Any]]:
        """
        Generates simulated flight quotes for all 20 DGCA routes across all 5 advance purchase windows.
        """
        all_quotes: List[Dict[str, Any]] = []
        macro_atf_drift = 1.0 + (day_index * self.config.atf_trend_drift) + (0.02 * math.sin(day_index / 5.0))

        for route in DGCA_TOP_20_ROUTES:
            for window in ADVANCE_PURCHASE_WINDOWS:
                travel_date = booking_date + datetime.timedelta(days=window.days_advance)
                dow_mult = self._get_day_of_week_multiplier(travel_date)
                adv_mult = self._get_advance_multiplier(window.window_id)

                # Generate 3 to 6 carrier flight offerings per route-window combination
                flight_schedules = [
                    ("6E", "IndiGo", f"6E-{random.randint(100, 999)}", "06:15", "08:30"),
                    ("6E", "IndiGo", f"6E-{random.randint(100, 999)}", "14:20", "16:40"),
                    ("6E", "IndiGo", f"6E-{random.randint(100, 999)}", "19:45", "22:00"),
                    ("AI", "Air India", f"AI-{random.randint(400, 899)}", "08:00", "10:15"),
                    ("AI", "Air India", f"AI-{random.randint(400, 899)}", "17:30", "19:45"),
                    ("QP", "Akasa Air", f"QP-{random.randint(1100, 1499)}", "10:30", "12:45"),
                    ("SG", "SpiceJet", f"SG-{random.randint(100, 599)}", "12:15", "14:30"),
                ]

                # Select a random subset representing active departures
                sampled_flights = random.sample(flight_schedules, k=random.randint(4, len(flight_schedules)))

                for ccode, cname, flt_num, dep, arr in sampled_flights:
                    airline_def = next((a for a in AIRLINE_MARKET_SHARES if a.code == ccode), AIRLINE_MARKET_SHARES[0])
                    carrier_mult = self._get_carrier_multiplier(airline_def)

                    # Dynamic Base Price Formulation
                    base_price = (
                        route.base_fare_benchmark *
                        adv_mult *
                        dow_mult *
                        carrier_mult *
                        macro_atf_drift *
                        random.uniform(0.97, 1.03)
                    )

                    # 1. Direct Portal Quote
                    taxes = self._calculate_tax_components(base_price, is_ota=False)
                    
                    # Statistical Outlier Injection
                    is_anomaly = random.random() < self.config.anomaly_rate
                    if is_anomaly:
                        anomaly_type = random.choice(["HYPER_HIGH", "NEAR_ZERO", "CORRUPTED_ZERO"])
                        if anomaly_type == "HYPER_HIGH":
                            taxes["total_fare"] = round(taxes["total_fare"] * random.uniform(4.5, 7.5), 2)
                            taxes["base_fare"] = round(taxes["base_fare"] * 5.0, 2)
                        elif anomaly_type == "NEAR_ZERO":
                            taxes["total_fare"] = 149.00
                            taxes["base_fare"] = 10.00
                        else:
                            taxes["total_fare"] = 99999.00
                            taxes["base_fare"] = 85000.00

                    quote_id = f"Q-{booking_date.strftime('%Y%m%d')}-{route.route_code}-{window.window_id}-{uuid.uuid4().hex[:8]}"
                    direct_quote = {
                        "quote_id": quote_id,
                        "route_code": route.route_code,
                        "origin": route.origin,
                        "destination": route.destination,
                        "airline_code": ccode,
                        "airline_name": cname,
                        "flight_number": flt_num,
                        "source_portal": f"DIRECT_{cname.upper().replace(' ', '')}",
                        "booking_date": booking_date.isoformat(),
                        "travel_date": travel_date.isoformat(),
                        "advance_window": window.window_id,
                        "departure_time": dep,
                        "arrival_time": arr,
                        "is_direct": 1,
                        "currency": "INR",
                        "scraped_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
                        **taxes
                    }
                    all_quotes.append(direct_quote)

                    # 2. Duplicate OTA Quotes (Testing Multi-OTA Deduplication Pipeline)
                    if random.random() < self.config.multi_ota_ratio and not is_anomaly:
                        ota_portals = ["OTA_MAKEMYTRIP", "OTA_EASEMYTRIP", "OTA_CLEARTRIP"]
                        chosen_ota = random.choice(ota_portals)
                        ota_tax = self._calculate_tax_components(base_price * random.uniform(0.99, 1.02), is_ota=True)
                        ota_quote = {
                            "quote_id": f"OTA-{booking_date.strftime('%Y%m%d')}-{route.route_code}-{window.window_id}-{uuid.uuid4().hex[:8]}",
                            "route_code": route.route_code,
                            "origin": route.origin,
                            "destination": route.destination,
                            "airline_code": ccode,
                            "airline_name": cname,
                            "flight_number": flt_num,
                            "source_portal": chosen_ota,
                            "booking_date": booking_date.isoformat(),
                            "travel_date": travel_date.isoformat(),
                            "advance_window": window.window_id,
                            "departure_time": dep,
                            "arrival_time": arr,
                            "is_direct": 0,
                            "currency": "INR",
                            "scraped_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
                            **ota_tax
                        }
                        all_quotes.append(ota_quote)

        return all_quotes

    def generate_multi_day_dataset(
        self,
        start_date: datetime.date,
        num_days: int = 35
    ) -> List[Dict[str, Any]]:
        """Generates continuous daily panels across the specified multi-day window."""
        master_quotes: List[Dict[str, Any]] = []
        for d in range(num_days):
            current_date = start_date + datetime.timedelta(days=d)
            daily_quotes = self.generate_quotes_for_date(current_date, day_index=d)
            master_quotes.extend(daily_quotes)
        return master_quotes
