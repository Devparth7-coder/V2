# VayuSutra APIx — Full Codebase Audit

**Repository:** `github.com/Devparth7-coder/SIH26056`
**Problem Statement:** Smart India Hackathon 2026 — SIH26056 (Airfare Price Index for CPI Augmentation)
**Audit date:** 2026-08-30

This document is the *before* audit. It was produced **before** any upgrade work began, to
preserve a faithful record of the original architecture, and to justify the upgrade plan.

---

## A. Current Architecture

A **monolithic FastAPI application** packaged as a single Python package `vayusutra_apix/`
inside a repository that also carries a duplicate top-level `index.html`, `Dockerfile`,
`docker-compose.yml`, `package.json` and `data/*.csv`.

```
repo root (SIH26056/)
├── index.html                    # duplicate of static/dashboard.html
├── Dockerfile                    # multi-stage python:3.13-slim
├── docker-compose.yml
├── package.json                  # pdf-parse, pptxgenjs, sharp (frontend helper deps, unused)
├── requirements.txt              # top-level (mirrors inner)
├── data/                         # mospi & dgca actual CSVs
└── vayusutra_apix/               # THE Python package (also an app root in Docker)
    ├── api/main.py               # single FastAPI app, ~1079 lines, ALL routes in one file
    ├── cli.py                    # argparse CLI (serve/ingest/train/nowcast/backtest/sync/worker)
    ├── config/routes.py          # DGCA Top-20 basket, horizons, airlines, taxes, CPI weights
    ├── config/db.py              # SQLite WAL connection manager + schema init
    ├── scrapers/                 # base_scraper, live_connectors, market_feed (simulator), esankhyiki
    ├── pipeline/                 # cleaner (MAD/IQR), validator (pydantic)
    ├── engine/                   # index_calculator, backtest, model_trainer, nowcast_predictor
    ├── services/                 # metrics (prometheus), scheduler (worker daemon), streaming (WS/SSE)
    ├── static/dashboard.html     # self-contained dashboard (inline CSS/JS/SVG)
    ├── tests/                    # 7 test files, 37 tests
    └── data/                     # SQLite DB + backtest CSV + model artifact .pkl
```

**Key architectural characteristics:**
- Single-process FastAPI with SQLite (WAL mode), thread-local connections, `busy_timeout`.
- A background `asyncio` worker daemon (`IngestionWorkerDaemon`) that every ~60s runs a full
  ingest → clean → index cycle and broadcasts via WebSocket/SSE.
- All statistical heavy lifting in the `engine/` package; the API layer mostly queries SQLite.
- The **market data is synthetic** — a calibrated simulator (`MarketFeedGenerator`) generates
  quotes with injected outliers, multi-OTA duplicates, and DOW/ATF/seasonal effects.
- The dashboard is a **single self-contained HTML file** with zero external dependencies
  (native SVG charts), served by the root `/` route.

---

## B. Existing Features

1. **DGCA Top-20 route basket** with normalized national volume weights (sum = 1.0).
2. **5 advance-purchase horizons** (T+1, T+7, T+15, T+30, T+45) with weights summing to 1.0.
3. **Elementary index engine**: Jevons geometric mean, price relatives.
4. **Higher-level index engine**: Laspeyres, Paasche (elasticity-based), Fisher Ideal,
   Törnqvist, Walsh, Jevons national, chained index, regional disaggregation.
5. **CPI transmission**: bps into Transport & Communication sub-group and Headline CPI.
6. **Ingestion pipeline**: token-bucket rate limiting, robots.txt compliance, multi-OTA
   deduplication, MAD modified-z-score + Tukey IQR outlier rejection, statutory tax breakdown.
7. **DGCA backtest engine**: 30-day Pearson r / MAPE / RMSE / R² validation + CSV report.
8. **ML nowcast ensemble**: Ridge L2 + GradientBoosting hybrid, autoregressive multi-step forecast
   with 95% CI, feature importances, model artifact persistence.
9. **REST API** (~30 routes) incl. realtime index, timeseries, routes, elasticity, CPI impact,
   backtest, ingest, model train/status/predict, worker control, eSankhyiki sync, dataset
   endpoints, fare decomposer calculator, superlative & regional indices, cryptographic
   provenance, CSV export.
10. **Observability**: Prometheus `/metrics`, WebSocket `/ws/live-feed`, SSE `/api/v1/stream/events`.
11. **Dashboard**: dark NSO/MoSPI executive dashboard with live ticker, SVG charts, route table.

---

## C. Existing API Endpoints

| Method | Endpoint | Purpose |
|---|---|---|
| GET | `/` | Dashboard (HTML) |
| GET | `/api/v1/health` | Health & telemetry |
| GET | `/api/v1/index/realtime` | Latest indices + CPI bps |
| GET | `/api/v1/index/timeseries` | Historical daily series |
| GET | `/api/v1/routes` | 20-route basket + latest relatives |
| GET | `/api/v1/analytics/elasticity` | Lead-time yield curves |
| GET | `/api/v1/analytics/cpi-impact` | Sensitivity stress matrix |
| GET | `/api/v1/backtest` | DGCA validation report |
| POST | `/api/v1/ingest/run` | Trigger ingest & index |
| POST | `/api/v1/model/train` | Train nowcast ensemble |
| GET | `/api/v1/model/status` | Model health |
| GET | `/api/v1/model/predict` | Forward nowcast |
| GET | `/metrics` | Prometheus metrics |
| WS | `/ws/live-feed` | Live WebSocket feed |
| GET | `/api/v1/stream/events` | SSE feed |
| GET | `/api/v1/worker/status` | Worker telemetry |
| POST | `/api/v1/worker/start\|pause\|resume\|trigger-now` | Worker controls |
| GET | `/api/v1/esankhyiki/metadata\|cpi-baseline\|augmented-cpi` | MoSPI CPI data |
| POST | `/api/v1/esankhyiki/sync` | Sync eSankhyiki |
| GET | `/api/v1/datasets/mospi-cpi\|dgca-traffic\|flight-quotes` | Dataset access |
| POST | `/api/v1/calculator/decompose` | Fare decomposer + CPI bps |
| GET | `/api/v1/index/superlative` | Superlative comparison |
| GET | `/api/v1/index/regional` | Regional disaggregation |
| GET | `/api/v1/audit/provenance` | Crypto provenance vault |
| GET | `/api/v1/export/csv` | Statutory CSV export |

---

## D. Existing Data Flow

```
MarketFeedGenerator (simulated quotes)
        │  (raw_quotes → raw_quotes table)
        ▼
DataCleaningPipeline (dedup → MAD/IQR outlier reject → tax decompose)
        │  (cleaned_quotes → cleaned_quotes table)
        ▼
IndexCalculationEngine (elementary Jevons → route composite → national superlative)
        │  (route_indices, national_indices tables)
        ▼
FastAPI queries SQLite → JSON/CSV/SSE/WS → Dashboard
```

Ground truth for validation: `DGCABacktestEngine._generate_dgca_ground_truth_yield()`
(a *calibrated synthetic benchmark*, NOT official published DGCA yield data).

---

## E. Existing Database Schema (SQLite, WAL)

Tables: `raw_quotes`, `cleaned_quotes`, `route_indices`, `national_indices`, `backtest_metrics`.

- `raw_quotes`: quote_id (PK), route_code, origin/destination, airline_code/name,
  flight_number, source_portal, booking_date, travel_date, advance_window,
  departure_time, arrival_time, base_fare, fuel_surcharge, udf, psf, asf, gst,
  convenience_fee, total_fare, is_direct, currency, scraped_at.
- `cleaned_quotes`: cleaned_id (PK), raw_quote_id (FK), route_code, advance_window,
  booking_date, travel_date, airline_code, flight_number, final_base_fare,
  final_tax_fee, final_total_fare, outlier_flag, outlier_reason,
  deduplication_kept, cleaned_at.
- `route_indices`: id, calculation_date, route_code, advance_window, sample_size,
  jevons_mean_fare, base_benchmark_fare, price_relative, composite_route_relative, created_at.
- `national_indices`: calculation_date (UNIQUE), laspeyres, paasche, fisher, jevons,
  spot_t1, daily_pct_change, bps_transport_impact, bps_headline_cpi_impact,
  observations_count, valid_quotes_count, outliers_rejected_count, created_at.
- `backtest_metrics`: metric_date, pearson_r, mape, rmse, r2, sample_days,
  total_quotes_evaluated, report_path, generated_at.

Indexes exist on `(route_code, booking_date, advance_window)`,
`(flight_number, travel_date)`, `(route_code, advance_window, booking_date, outlier_flag)`,
`(calculation_date, route_code)`, `(calculation_date)`.

---

## F. Existing Formulas

- **Jevons elementary price:** `P̄_{r,k} = exp(mean(ln p_i))`; relative `R = P̄ / P0`.
- **Composite route relative:** `R̄_r = Σ α_k · R_{r,k}`, α = [0.22, 0.34, 0.24, 0.14, 0.06].
- **Laspeyres:** `I_L = Σ w_r⁰ · R̄_r × 100`.
- **Paasche (elasticity ε=-0.85):** `I_P = Σ w⁰ (R̄)^{1+ε} / Σ w⁰ (R̄)^ε × 100`.
- **Fisher:** `I_F = √(I_L · I_P)`.
- **Törnqvist:** `exp( Σ ((w⁰+wᵗ)/2)·ln R̄ ) × 100`.
- **Walsh:** `Σ √(w⁰·wᵗ)·R̄ / Σ √(w⁰·wᵗ) × 100`.
- **Jevons national:** `exp( Σ w⁰·ln R̄ ) × 100`.
- **CPI transmission:** `Transport bps = Δ% × 0.0385 × 100`; `Headline bps = Transport bps × 0.0859`.
- **MAD modified z-score:** `M_i = 0.6745·(x−med)/MAD`, outlier if `|M|>3.0`; Tukey IQR fallback.
- **Backtest stats:** Pearson r, MAPE, RMSE, R².

---

## G. Existing Test Coverage

| File | Coverage focus |
|---|---|
| `test_rate_limiter.py` | Token-bucket, jitter, UA rotation |
| `test_cleaner.py` | MAD/IQR outliers, dedup, tax decompose |
| `test_index_math.py` | Laspeyres/Paasche/Fisher/Jevons correctness |
| `test_api.py` | All HTTP endpoints 200 + schemas |
| `test_esankhyiki.py` | eSankhyiki metadata/baseline |
| `test_model_trainer.py` | Feature engineering, ensemble fit, artifact |
| `test_service.py` | Metrics, streaming, worker status |

**37 tests, all passing** at audit time.

---

## H. Technical Debt

1. **Single monolithic `api/main.py` (~1079 lines)** — all routes inline; no router separation.
2. **No API response models** (endpoints return raw dicts) — no OpenAPI schema fidelity.
3. **`scikit-learn` used but missing from `requirements.txt`** — production install would fail.
4. **`statsmodels` absent** — SARIMA/ETS unavailable for forecasting.
5. **No data provenance / quote-level audit trail** beyond the raw row; no lineage UI.
6. **No data-trust / data-quality scoring**.
7. **No market-anomaly detection** (only data-cleaning outlier rejection exists).
8. **No scenario / what-if simulator**.
9. **No alert engine.**
10. **No route-level forecast or heatmap.**
11. **No source consensus / disagreement metrics.**
12. **No airfare inflation pressure composite index.**
13. **CPI decomposition is not route-level** (only aggregate bps + sensitivity matrix).
14. **`raw_quotes` schema lacks explicit `scraper_version`, `source_type` columns** for provenance.
15. **No in-process caching** — every dashboard request re-queries/recomputes.
16. **Secrets/security**: CORS is `*`, no `.env.example`, no rate limiting on API layer.
17. **Frontend is a single file** with no user-mode navigation, no heatmap, no drill-down pages,
    no route intelligence, no map, no report/validation/analyst views.
18. **Top-level `requirements.txt`/`index.html`/Dockerfiles duplicate the inner package** — drift risk.
19. **No structured request-ID logging / observability beyond Prometheus counters.**
20. **Model forecast is ML-only; no classical baseline (seasonal naive / ETS) comparison.**
21. **No user-facing distinction between REAL / SIMULATED / MODELLED data in the UI.**
22. **Backtest ground truth is synthetic** and is labeled "DGCA benchmark" which can read as
    fabricated official data — needs honest labeling.

---

## I. Missing Capabilities (gap vs. required target)

- National real-time intelligence dashboard (KPI cards, trend, forecast, heatmap, top rising/falling,
  source health, anomaly feed, confidence).
- Airfare heatmap (20 × 5) with filtering/sorting/drill-down.
- Route intelligence pages + route comparison.
- Forecasting framework (Seasonal Naive / ETS / SARIMA / GBM / Ensemble + walk-forward + metrics).
- Airfare Inflation Pressure Score (transparent composite).
- Market anomaly detection (z-score / EWMA / seasonal residual / divergence / horizon-inversion / source disagreement).
- Route-level CPI impact decomposition.
- Policy what-if scenario simulator.
- Data Trust Center (freshness, completeness, coverage, source health, dup/outlier rate, consensus).
- Data provenance / quote-level audit trail + drill-down.
- Source consensus & disagreement classification.
- Airline/OTA analytics (without fabricating market share).
- Interactive India route map.
- Alert engine (rules CRUD + evaluation).
- Automated daily intelligence report (CSV/JSON).
- AI Policy Analyst (grounded, non-hallucinating).
- Three user modes (Policy / Analyst / Aviation).
- Advanced temporal analytics (intraday/7/30/90d, weekday, seasonal).
- Validation Center (walk-forward, model comparison, error distribution, CI).
- API versioning organization + Pydantic response models + `.env.example` + security.
- Observability (request IDs, structured logging, component health).
- Performance (in-process caching, precomputed aggregates).

---

## J. Recommended Upgrade Plan

Preserve the econometric engine, cleaner, backtest, and all existing endpoints. Add modules in
layers, all consuming the same SQLite data model, following the proposed pipeline:

```
INGESTION → RAW QUOTE STORE → DATA QUALITY ENGINE (+ Data Trust Score)
         → NORMALIZED QUOTE STORE → INDEX ENGINE → (Forecast | Anomaly | CPI | Scenario)
         → INTELLIGENCE API → (Dashboard | Alerts | Reports | AI Analyst)
```

**Phase 1 — Foundation (dashboard redesign, heatmap, route intelligence, CPI decomposition,
Data Trust Center).**
**Phase 2 — Forecasting, anomaly detection, pressure score.**
**Phase 3 — Scenario simulator, alerts, source consensus, provenance.**
**Phase 4 — India map, automated reports, AI Policy Analyst.**
**Phase 5 — Testing, performance, security, docs, Docker hardening.**

Data-honesty rule: label everything REAL / SIMULATED / HISTORICAL / MODELLED; never present
synthetic or modelled output as official statistics.
