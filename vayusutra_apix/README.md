# VayuSutra — National Airfare Intelligence & Inflation Analytics Platform

> Full documentation lives in the repository root **`README.md`**. This file documents the
> Python package-specific layout and usage for the FastAPI service.

## What this package is

`vayusutra_apix` is the FastAPI + SQLite application behind VayuSutra. It contains the
econometric index engine, data pipeline, forecasting, anomaly detection, pressure scoring,
CPI decomposition, scenario simulator, alerts, reports, provenance, and the AI Policy Analyst.

## Layout

```
vayusutra_apix/
├── api/            main.py (legacy routes + middleware) + routers/ (v2 domain routers)
├── config/         routes.py (DGCA basket), db.py (SQLite), schema_v2.py (migrations)
├── scrapers/       base_scraper, live_connectors, market_feed (simulator), esankhyiki
├── pipeline/       cleaner (MAD/IQR), validator (pydantic)
├── engine/         index_calculator, backtest, model_trainer, nowcast_predictor
├── forecasting/    Seasonal Naive / ETS / SARIMA / GBM / Ensemble + walk-forward validation
├── anomaly/        market anomaly detection
├── analytics/      pressure, cpi-decomposition, heatmap, consensus, route intelligence,
│                   source analytics, temporal
├── scenario/       policy what-if simulator
├── alerts/         alert rules + evaluation
├── reports/        daily intelligence report (CSV/JSON/PDF)
├── data_quality/   trust center
├── services/       cache, observability, logging, streaming, scheduler, metrics, ai_analyst, india_map
├── static/         dashboard.html
└── tests/          pytest suite (isolated DB via conftest.py)
```

## Run

```bash
pip install -r requirements.txt
python -m pytest tests -v
uvicorn vayusutra_apix.api.main:app --host 0.0.0.0 --port 8000
```

## Configuration

Set environment variables (see root `.env.example`):

| Variable | Purpose |
|---|---|
| `VAYUSUTRA_DB_PATH` | Override SQLite path |
| `VAYUSUTRA_CORS_ORIGINS` | Comma-separated CORS origins |
| `LOG_LEVEL` | Structured-log verbosity |

## CLI

```bash
python -m vayusutra_apix.cli ingest --date 2026-08-29
python -m vayusutra_apix.cli backtest --days 35
python -m vayusutra_apix.cli nowcast --horizon 14
python -m vayusutra_apix.cli train
python -m vayusutra_apix.cli worker --interval 60
```

## Docker

```bash
docker-compose up --build -d
```
