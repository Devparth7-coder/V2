"""
VayuSutra APIx - Pydantic Data Validation Schemas
Validates structural integrity, statutory constraints, and type adherence for airline quotes and index calculations.
"""

import datetime
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field, field_validator


class RawFlightQuote(BaseModel):
    """Schema for raw flight quotes ingested from scrapers or market feeds."""
    quote_id: str = Field(..., description="Unique alphanumeric identifier for the quote")
    route_code: str = Field(..., description="IATA route code pair, e.g. DEL-BOM")
    origin: str = Field(..., min_length=3, max_length=3, description="Origin 3-letter IATA code")
    destination: str = Field(..., min_length=3, max_length=3, description="Destination 3-letter IATA code")
    airline_code: str = Field(..., min_length=2, max_length=5, description="Carrier IATA/ICAO code")
    airline_name: str = Field(..., description="Carrier brand name")
    flight_number: str = Field(..., description="Official flight identifier, e.g. 6E-201")
    source_portal: str = Field(..., description="Ingestion source: DIRECT_INDIGO, OTA_MAKEMYTRIP, etc.")
    booking_date: str = Field(..., description="Date of quote capture (YYYY-MM-DD)")
    travel_date: str = Field(..., description="Date of travel (YYYY-MM-DD)")
    advance_window: str = Field(..., description="Purchase horizon: T+1, T+7, T+15, T+30, T+45")
    departure_time: str = Field(..., description="Local scheduled departure time (HH:MM)")
    arrival_time: str = Field(..., description="Local scheduled arrival time (HH:MM)")
    base_fare: float = Field(..., ge=0.0, description="Base airline tariff in INR")
    fuel_surcharge: float = Field(default=0.0, ge=0.0, description="Aviation Turbine Fuel surcharge in INR")
    udf: float = Field(default=0.0, ge=0.0, description="User Development Fee in INR")
    psf: float = Field(default=0.0, ge=0.0, description="Passenger Service Fee in INR")
    asf: float = Field(default=0.0, ge=0.0, description="Aviation Security Fee in INR")
    gst: float = Field(default=0.0, ge=0.0, description="Goods and Services Tax in INR")
    convenience_fee: float = Field(default=0.0, ge=0.0, description="Booking convenience fee in INR")
    total_fare: float = Field(..., gt=0.0, description="Total gross passenger fare payable in INR")
    is_direct: int = Field(default=1, ge=0, le=1, description="1 if direct airline portal, 0 if OTA")
    currency: str = Field(default="INR", description="Three-letter ISO currency code")
    scraped_at: str = Field(default_factory=lambda: datetime.datetime.now(datetime.timezone.utc).isoformat())

    @field_validator("advance_window")
    @classmethod
    def validate_window(cls, v: str) -> str:
        valid_windows = {"T+1", "T+7", "T+15", "T+30", "T+45"}
        if v not in valid_windows:
            raise ValueError(f"Invalid advance window '{v}', must be one of {valid_windows}")
        return v


class CleanedFlightQuote(BaseModel):
    """Schema for validated, deduplicated, and outlier-filtered quotes."""
    cleaned_id: str
    raw_quote_id: str
    route_code: str
    advance_window: str
    booking_date: str
    travel_date: str
    airline_code: str
    flight_number: str
    final_base_fare: float
    final_tax_fee: float
    final_total_fare: float
    outlier_flag: int = 0
    outlier_reason: Optional[str] = None
    deduplication_kept: int = 1
    cleaned_at: str


class RouteIndexResult(BaseModel):
    """Elementary aggregate price relative result for a specific route and advance window."""
    calculation_date: str
    route_code: str
    advance_window: str
    sample_size: int
    jevons_mean_fare: float
    base_benchmark_fare: float
    price_relative: float
    composite_route_relative: float


class NationalIndexResult(BaseModel):
    """Higher-level National Airfare Price Index and CPI Transmission Output."""
    calculation_date: str
    laspeyres_index: float
    paasche_index: float
    fisher_index: float
    jevons_index: float
    spot_t1_index: float
    daily_pct_change: float
    bps_transport_impact: float
    bps_headline_cpi_impact: float
    observations_count: int
    valid_quotes_count: int
    outliers_rejected_count: int


class BacktestMetricsResult(BaseModel):
    """DGCA Statistical Validation Backtest Report Schema."""
    metric_date: str
    pearson_r: float
    mape: float
    rmse: float
    r2: float
    sample_days: int
    total_quotes_evaluated: int
    validation_status: str
    report_path: str
    summary_message: str
