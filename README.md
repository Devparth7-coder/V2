<div align="center">

# VayuSutra
### National Airfare Intelligence & Inflation Analytics Platform

**Measure → Explain → Forecast → Simulate**

*Smart India Hackathon 2026 · Problem Statement SIH26056*
*Commissioned for MoSPI / NSO · RBI Monetary Policy Committee · DGCA*

</div>

---

## 1. Problem

India's headline Consumer Price Index (CPI, Base 2012=100) assigns an **8.59%** weight to the
*Transport and Communication* sub-group, within which domestic air travel is a high-volatility
**3.85%** share. Historically, airfare price collection relied on **manual monthly visits** to
physical airline ticketing counters. In today's digital economy:

- Over **92%** of domestic tickets are bought dynamically through airline portals (IndiGo, Air
  India, Akasa Air, SpiceJet) and OTAs (MakeMyTrip, EaseMyTrip, Cleartrip).
- Dynamic revenue management swings fares **200%–400%** across advance-booking horizons
  (T+1 emergency vs T+45 early bird), day-of-week surges, and Aviation Turbine Fuel (ATF) cycles.
- Manual monthly sampling captures static counter quotes → **lag and measurement distortion** in
  national inflation figures.

## 2. Why Existing Measurement Is Insufficient

| Limitation | Consequence |
|---|---|
| Manual, monthly, counter-level sampling | Misses daily/intraday fare dynamics |
| No advance-purchase horizon granularity | Cannot capture the T+1 spot premium that dominates volatility |
| Static basket methodology | Cannot support what-if / policy simulation |
| No data provenance or trust scoring | Cannot audit a number back to its source |
| No confidence intervals on forecasts | RBI/MPC cannot quantify forecast uncertainty |
| Point estimates without explanations | Analysts cannot answer "why did CPI move?" |

## 3. Solution

**VayuSutra** is a production-grade, high-frequency **National Airfare Intelligence & Inflation
Analytics Platform** that ingests airfare quotes, cleans and scores their trust, computes
MoSPI/ILO-compliant elementary and higher-level price indices, transmits them into the CPI,
explains the drivers, forecasts with uncertainty, detects market anomalies, runs policy what-if
scenarios, alerts, reports and answers grounded policy questions.

### 3.1 Architecture

```
DATA SOURCES (airlines · OTAs · calibrated simulator)
      │
      ▼
INGESTION LAYER (ethical scraping · rate limiting · simulator)
      │
      ▼
RAW QUOTE STORE (SQLite: raw_quotes + provenance metadata)
      │
      ▼
DATA QUALITY ENGINE (MAD/IQR · dedup · trust scoring) ──► DATA TRUST SCORE
      │
      ▼
NORMALIZED QUOTE STORE (cleaned_quotes)
      │
      ▼
ECONOMETRIC INDEX ENGINE (Jevons · Laspeyres · Paasche · Fisher · Törnqvist · Walsh)
      │
      ├────► FORECASTING ENGINE (Seasonal Naive · ETS · SARIMA · GBM · Ensemble)
      ├────► ANOMALY ENGINE (z-score · EWMA · divergence · horizon-inversion · source disagreement)
      ├────► CPI TRANSMISSION ENGINE (route-level decomposition)
      └────► SCENARIO ENGINE (policy what-if)
      │
      ▼
INTELLIGENCE API (FastAPI /api/v1)
      │
  ┌────┴────┬──────────┬───────────┬──────────┐
  ▼         ▼          ▼           ▼          ▼
DASHBOARD  ALERTS    REPORTS    AI ANALYST  EXPORT (CSV/JSON/PDF)
```

## 4. Features

1. **National Real-Time Intelligence Dashboard** — KPI cards, trend, 7-day forecast, top
   rising/falling routes, CPI contributors, anomaly feed, pressure, trust.
2. **Airfare Heatmap** — 20 routes × 5 booking horizons with fare, 24h change, volatility, status.
3. **Route Intelligence Pages** — median/Jevons fare, changes, volatility, consensus, CPI
   contribution, horizons, historical chart, forecast, anomaly history, airline comparison, provenance.
4. **Forecasting Engine** — Seasonal Naive, ETS, SARIMA, GBM, Ensemble; walk-forward validation;
   auto model selection; MAE/RMSE/MAPE/sMAPE/R²; **every forecast has a confidence interval**.
5. **Airfare Inflation Pressure Score** — transparent composite (0–100; LOW/MODERATE/HIGH/CRITICAL)
   with documented, configurable weights and driver decomposition.
6. **Market Anomaly Detection** — fare spikes/drops, route divergence, booking-horizon inversion,
   source disagreement (distinct from data-quality outliers).
7. **CPI Impact Decomposition** — route-level contribution to headline bps.
8. **Policy What-if Simulator** — airfare/demand/capacity/ATF/horizon/season shocks → projected
   index, CPI bps, pressure (labelled **MODELLED**).
9. **Data Trust Center** — weighted trust score across freshness, completeness, coverage, source
   availability, duplicate/outlier rate, validation, source agreement.
10. **Data Provenance / Audit Trail** — every quote traceable from index → route → observation →
    source → raw quote; `/api/v1/quotes/{quote_id}`.
11. **Source Consensus** — median, spread, coefficient of variation, consensus score, and
    NORMAL / WARNING / HIGH DISAGREEMENT classification (flagged, never auto-deleted).
12. **Airline / OTA Analytics** — by airline, OTA, route, horizon; market share shown **only** where
    official DGCA share exists, otherwise "Data unavailable".
13. **India Route Map** — lightweight SVG map of the 20 routes (click → route intelligence).
14. **Alert Engine** — rule CRUD + evaluation (airfare ↑, CPI impact, pressure, anomaly, forecast
    revision, data quality, source outage); dashboard channel; extensible to email/webhook.
15. **Automated Daily Intelligence Report** — CSV / JSON / PDF export, all sections labelled
    REAL / SIMULATED / MODELLED.
16. **AI Policy Analyst** — grounded, non-hallucinating Q&A over verified platform data
    (no external LLM dependency).
17. **Three User Modes** — Policy / Analyst / Aviation (same backend APIs).
18. **Advanced Temporal Analytics** — weekday/weekend, booking-horizon, route & seasonal patterns;
    significance reported only when a t-test passes (p<0.05).
19. **Validation Center** — walk-forward model comparison, error metrics, traceable datasets.
20. **API versioning & Pydantic response models** — organized routers under `/api/v1`.

## 5. Mathematical Methodology

All index math follows the **ILO Consumer Price Index Manual** and the **MoSPI Base 2012=100**
specification and is implemented deterministically in `engine/index_calculator.py`.

- **Elementary (Jevons geometric mean):** `P̄_{r,k} = exp( (1/n) Σ ln p_i )`
- **Composite route relative:** `R̄_r = Σ α_k R_{r,k}`,  α = [0.22, 0.34, 0.24, 0.14, 0.06]
- **Laspeyres:** `I_L = (Σ w_r⁰ R̄_r) × 100`
- **Paasche (elasticity ε = −0.85):** `I_P = Σ w⁰ (R̄)^{1+ε} / Σ w⁰ (R̄)^ε × 100`
- **Fisher Ideal:** `I_F = √(I_L · I_P)`
- **Törnqvist:** `exp( Σ ((w⁰+wᵗ)/2) ln R̄ ) × 100`
- **Walsh:** `Σ √(w⁰wᵗ) R̄ / Σ √(w⁰wᵗ) × 100`
- **CPI transmission:** `Transport bps = Δ% × 0.0385 × 100`; `Headline bps = Transport bps × 0.0859`
- **Outlier rejection:** MAD modified z-score (`|M|>3`) with Tukey IQR fallback.
- **Forecast evaluation:** MAE, RMSE, MAPE, sMAPE, R² via expanding-window walk-forward validation.
- **Pressure score:** documented weighted composite (weights in `analytics/pressure.py`).
- **Trust score:** documented weighted composite (weights in `data_quality/trust.py`).

## 6. Data Sources & Honesty

| Tag | Meaning |
|---|---|
| **REAL** | Official published data (e.g. MoSPI eSankhyiki CPI baseline, DGCA traffic CSVs shipped in `data/`) |
| **SIMULATED** | Quotes produced by the calibrated `MarketFeedGenerator` (the platform's live demo feed) |
| **HISTORICAL / BENCHMARK** | Backtest reference series (the backtest "DGCA yield" is a **calibrated synthetic benchmark**, not official DGCA yield — labelled as such) |
| **MODELLED** | Forecasts, scenarios, pressure and report projections |

> **Honesty rule:** the dashboard always shows "Data status: SIMULATED" while the simulator is in
> use. VayuSutra never presents synthetic quotes, forecasts, or scenarios as official live
> statistics, and never fabricates forecast accuracy, market share, or government statistics.

The two `data/*.csv` files are **real** reference datasets: `mospi_esankhyiki_cpi_actual.csv` and
`dgca_citypair_traffic_actual.csv`, exposed via `/api/v1/datasets/*`.

## 7. API Documentation

Interactive docs at `/docs` (Swagger) and `/redoc` after starting the server. 63 paths under `/api/v1`.

| Group | Endpoints |
|---|---|
| **Index** | `GET /api/v1/index/realtime` · `/index/timeseries` · `/index/superlative` · `/index/regional` |
| **Routes** | `GET /api/v1/routes` |
| **Analytics** | `GET /api/v1/analytics/heatmap` · `/pressure` · `/cpi-decomposition` · `/source-consensus` · `/source-analytics` · `/route/{code}` · `/compare?route_codes=` · `/route-map` · `/overview` · `/temporal` · `/elasticity` · `/cpi-impact` |
| **Forecast** | `GET /api/v1/forecast/national` · `/route/{code}` · `/validation` · `/models` · `GET /api/v1/model/predict` |
| **Anomalies** | `GET /api/v1/anomalies` · `/anomalies/route/{code}` |
| **Scenario** | `POST /api/v1/scenario/simulate` · `GET /api/v1/scenario/history` |
| **Data Quality** | `GET /api/v1/data-quality` · `/data-quality/components` |
| **Alerts** | `GET /api/v1/alerts` · `/alerts/rules` · `POST /api/v1/alerts/rules` · `PATCH /api/v1/alerts/rules/{id}` · `POST /api/v1/alerts/evaluate` |
| **Reports** | `GET /api/v1/reports/daily` · `/daily/csv` · `/daily/json` · `/daily/pdf` |
| **Quotes / Provenance** | `GET /api/v1/quotes` · `/quotes/{quote_id}` |
| **AI Analyst** | `POST /api/v1/ai/ask` · `GET /api/v1/ai/capabilities` |
| **Legacy (preserved)** | `/health`, `/backtest`, `/ingest/run`, `/model/*`, `/worker/*`, `/esankhyiki/*`, `/datasets/*`, `/calculator/decompose`, `/audit/provenance`, `/export/csv`, WebSocket `/ws/live-feed`, SSE `/api/v1/stream/events`, Prometheus `/metrics` |

### Example — national forecast (always with uncertainty)

```
GET /api/v1/forecast/national?horizon_days=7
```
```json
{
  "as_of_date": "2026-08-29",
  "horizon_days": 7,
  "forecast_date": "2026-09-05",
  "model": "seasonal_naive",
  "point_forecast": 117.35,
  "lower_bound": 85.28,
  "upper_bound": 149.42,
  "confidence_level": 0.95,
  "metrics": {"mae": 0.43, "rmse": 0.55, "mape": 0.29, "smape": 0.29, "r2": 0.99},
  "model_validation": {"seasonal_naive": {"mae": 0.4, "rmse": 0.5, "mape": 0.3, "smape": 0.3, "r2": 0.99}},
  "data_status": "MODELLED",
  "generated_at": "2026-08-29T16:00:00Z"
}
```

### Example — policy scenario

```
POST /api/v1/scenario/simulate
Content-Type: application/json
{"airfare_shock_pct": 10, "demand_change_pct": 5, "capacity_change_pct": -3}
```
```json
{
  "scenario_name": "Custom scenario",
  "current_index": 117.35,
  "projected_index": 136.88,
  "projected_index_change_pct": 16.64,
  "projected_transport_cpi_bps": 64.06,
  "projected_headline_cpi_bps": 5.50,
  "pressure": {"score": 42.0, "level": "MODERATE"},
  "route_level_impact": [{"route_code": "DEL-BOM", "projected_change_pct": 18.6, "weight": 0.1092}],
  "confidence_range": {"lower_index": 132.88, "upper_index": 140.88, "uncertainty_pct": 2.9},
  "data_status": "MODELLED"
}
```

### Example — AI analyst

```
POST /api/v1/ai/ask   {"question": "Which routes contributed most to CPI pressure?"}
```
```json
{
  "intent": "cpi_contributors",
  "answer": "Headline CPI impact is -7.97 bps. Top contributors: BOM-DEL -0.93 bps, DEL-BOM -0.80 bps, DEL-BLR -0.59 bps ...",
  "affected_routes": ["BOM-DEL", "DEL-BOM", "DEL-BLR"],
  "data_status": "SIMULATED",
  "note": "Answers are assembled from verified platform data ... does not hallucinate numbers."
}
```

## 8. Quickstart

### Local (Python)

```bash
pip install -r requirements.txt
python -m pytest vayusutra_apix/tests -v     # run the full test suite
uvicorn vayusutra_apix.api.main:app --host 0.0.0.0 --port 8000
```
Open **http://localhost:8000** for the dashboard, **/docs** for the API.

### Docker

```bash
docker-compose up --build -d
# or, from the vayusutra_apix/ directory
cd vayusutra_apix && docker-compose up --build -d
```

The container runs as a non-root user, mounts `./data` as a volume, and self-healthchecks
`/api/v1/health`.

### CLI

```bash
python -m vayusutra_apix.cli ingest --date 2026-08-29
python -m vayusutra_apix.cli backtest --days 35
python -m vayusutra_apix.cli nowcast --horizon 14
python -m vayusutra_apix.cli train
```

## 8b. Serverless / Vercel Deployment

The app is serverless-safe: startup is fully guarded so a read-only or stateless runtime cannot
crash it, and the database falls back to a writable path when the repo `data/` dir is read-only.

- `main.py` at the repo root exposes the ASGI `app` (canonical entrypoint).
- `vercel.json` builds `main.py` with `@vercel/python`, disables the background worker
  (`VAYUSUTRA_WORKER=0`), and seeds only `VAYUSUTRA_SEED_DAYS=8` days so cold starts are fast.
- For a normal long-running deployment (local/Docker), set `VAYUSUTRA_WORKER=1` (default) to keep
  the autonomous ingestion daemon.

If you deploy to Vercel, note:
- The background worker daemon is **off** by default in serverless (`VAYUSUTRA_WORKER=0`), so live
  tick updates come from on-demand ingestion (`POST /api/v1/ingest/run`) rather than the daemon.
- Data is file-backed in `/tmp` and persists only for the lifetime of a warm function instance;
  each cold start re-seeds a small dataset. For persistent analytics, run the Docker/local stack.

## 9. Screenshots

The dashboard is a self-contained single HTML file served at `/`. It is best captured from the
running server:
- **Overview:** KPI cards, national trend, 7-day forecast with CI band, CPI contributors,
  anomalies, top movers.
- **Heatmap:** 20×5 fare grid.
- **Route Intelligence:** per-route drill-down.
- **Simulator, Data Trust, Validation, Reports, AI Analyst** views.

Capture instructions: start the server, open `http://localhost:8000`, and screenshot each nav view.
> The in-app file preview of `index.html` has no network access, so charts render empty there —
> use the running server for full visuals.

## 10. Testing

```bash
python -m pytest vayusutra_apix/tests -v
```
- **95 tests** (37 original preserved + 58 new).
- Covers index math, cleaner, backtest, model trainer, rate limiter, service layer, **plus** new
  modules: forecasting, pressure score, CPI decomposition, scenario, consensus, data quality,
  anomaly detection, and the full v2 API (including invalid input, unknown routes, and provenance).
- Tests run against an **isolated, freshly-seeded SQLite database** for determinism.

## 11. Deployment, Configuration & Security

- Copy `.env.example` → `.env` and set `VAYUSUTRA_DB_PATH`, CORS origins, log level.
- **No secrets are committed.** `.env` and generated artifacts are gitignored.
- SQLite (WAL) is the default for simple local/demo deployment; the schema is designed so a
  PostgreSQL migration is possible later.
- In-process TTL caching avoids expensive recalculation on every dashboard request (no Redis needed).
- Structured JSON logging with per-request IDs; Prometheus `/metrics`; component health in `/health`.

## 12. Limitations

- The live demo feed is **simulated**; real connector endpoints require live credentials/TOS.
- SARIMA convergence on short series may warn; the framework falls back gracefully.
- The "DGCA yield" backtest benchmark is a **calibrated synthetic** series, not official DGCA yield.
- Forecast uncertainty widens with horizon (honest CI, not overconfident).
- AI analyst is rule-grounded (no external LLM); it is intentionally conservative.

## 13. Future Scope

- Real-time scraper connectors with authenticated airline/OTA access.
- PostgreSQL + Redis for multi-region scale.
- Email/webhook/notification channels for the alert engine.
- Additional seasonal/calendar covariates and richer ML feature sets.
- Regional CPI index publication workflows and audit certificates.

---

*MoSPI/ILO-compliant index methodology · MoSPI Base 2012=100 · RBI MPC · DGCA*
