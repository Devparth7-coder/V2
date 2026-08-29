"""
VayuSutra APIx - Data Cleaner Unit Tests
Verifies Median Absolute Deviation (MAD) outlier rejection, Multi-OTA deduplication,
and statutory tax breakdown normalization.
"""

import numpy as np
import pytest
from vayusutra_apix.pipeline.cleaner import DataCleaningPipeline
from vayusutra_apix.pipeline.validator import RawFlightQuote


def test_mad_outlier_detection():
    """Verify MAD filter correctly flags extreme statistical price anomalies."""
    cleaner = DataCleaningPipeline(mad_threshold=3.0)
    
    # Standard normal fares around 5000 INR with one extreme spike (95,000) and one ultra-low (200)
    fares = np.array([4800, 4950, 5000, 5100, 5050, 4900, 5200, 5000, 95000, 200], dtype=float)
    outlier_mask = cleaner.detect_outliers_mad(fares)

    # Index 8 (95000) must be flagged
    assert outlier_mask[8] is True or outlier_mask[8] == 1
    # Standard values around 5000 should not be flagged
    assert outlier_mask[2] is False or outlier_mask[2] == 0


def test_multi_ota_deduplication():
    """Verify that identical flights across Direct airline & OTAs retain only the Direct quote."""
    cleaner = DataCleaningPipeline()

    quotes = [
        RawFlightQuote(
            quote_id="Q-DIRECT",
            route_code="DEL-BOM",
            origin="DEL",
            destination="BOM",
            airline_code="6E",
            airline_name="IndiGo",
            flight_number="6E-201",
            source_portal="DIRECT_INDIGO",
            booking_date="2026-08-26",
            travel_date="2026-08-27",
            advance_window="T+1",
            departure_time="06:00",
            arrival_time="08:15",
            base_fare=5000.0,
            fuel_surcharge=2000.0,
            udf=420.0,
            psf=91.0,
            asf=200.0,
            gst=350.0,
            convenience_fee=0.0,
            total_fare=8061.0,
            is_direct=1,
            currency="INR",
            scraped_at="2026-08-26T10:00:00Z"
        ),
        RawFlightQuote(
            quote_id="Q-MMT",
            route_code="DEL-BOM",
            origin="DEL",
            destination="BOM",
            airline_code="6E",
            airline_name="IndiGo",
            flight_number="6E-201",
            source_portal="OTA_MAKEMYTRIP",
            booking_date="2026-08-26",
            travel_date="2026-08-27",
            advance_window="T+1",
            departure_time="06:00",
            arrival_time="08:15",
            base_fare=5000.0,
            fuel_surcharge=2000.0,
            udf=420.0,
            psf=91.0,
            asf=200.0,
            gst=350.0,
            convenience_fee=299.0,
            total_fare=8360.0,
            is_direct=0,
            currency="INR",
            scraped_at="2026-08-26T10:00:00Z"
        )
    ]

    retained, dropped = cleaner.deduplicate_multi_ota(quotes)
    assert len(retained) == 1
    assert len(dropped) == 1
    assert retained[0].quote_id == "Q-DIRECT"
    assert retained[0].is_direct == 1
    assert dropped[0].quote_id == "Q-MMT"


def test_full_cleaning_pipeline():
    """Verify end-to-end cleaning and summary telemetry generation."""
    cleaner = DataCleaningPipeline()

    raw_data = [
        {
            "quote_id": "TEST-1",
            "route_code": "DEL-BOM",
            "origin": "DEL",
            "destination": "BOM",
            "airline_code": "6E",
            "airline_name": "IndiGo",
            "flight_number": "6E-501",
            "source_portal": "DIRECT_INDIGO",
            "booking_date": "2026-08-26",
            "travel_date": "2026-08-27",
            "advance_window": "T+1",
            "departure_time": "10:00",
            "arrival_time": "12:15",
            "base_fare": 4000.0,
            "fuel_surcharge": 1500.0,
            "udf": 420.0,
            "psf": 91.0,
            "asf": 200.0,
            "gst": 275.0,
            "convenience_fee": 0.0,
            "total_fare": 6486.0,
            "is_direct": 1,
            "currency": "INR",
            "scraped_at": "2026-08-26T10:00:00Z"
        },
        {
            "quote_id": "TEST-OUTLIER",
            "route_code": "DEL-BOM",
            "origin": "DEL",
            "destination": "BOM",
            "airline_code": "6E",
            "airline_name": "IndiGo",
            "flight_number": "6E-502",
            "source_portal": "DIRECT_INDIGO",
            "booking_date": "2026-08-26",
            "travel_date": "2026-08-27",
            "advance_window": "T+1",
            "departure_time": "14:00",
            "arrival_time": "16:15",
            "base_fare": 90000.0,
            "fuel_surcharge": 10000.0,
            "udf": 420.0,
            "psf": 91.0,
            "asf": 200.0,
            "gst": 5000.0,
            "convenience_fee": 0.0,
            "total_fare": 105711.0,
            "is_direct": 1,
            "currency": "INR",
            "scraped_at": "2026-08-26T10:00:00Z"
        }
    ]

    cleaned, summary = cleaner.process_and_clean(raw_data)
    assert summary.total_raw_quotes == 2
    outlier_item = next(c for c in cleaned if c.raw_quote_id == "TEST-OUTLIER")
    valid_item = next(c for c in cleaned if c.raw_quote_id == "TEST-1")
    
    assert outlier_item.outlier_flag == 1
    assert valid_item.outlier_flag == 0
