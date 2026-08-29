"""
VayuSutra APIx - Automated Daily Intelligence Report
Aggregates national index, movement, CPI transmission, top rising/falling routes, volatility,
anomalies, forecast, pressure, data quality and methodology into a structured report with
CSV / JSON export. Every section is tagged REAL / SIMULATED / MODELLED.
"""
import csv
import datetime
import io
from dataclasses import dataclass, field
from typing import Dict, List, Any

from ..config.db import get_db_connection
from ..config.routes import CPI_WEIGHTS, DGCA_TOP_20_ROUTES


@dataclass
class DailyIntelligenceReport:
    generated_at: str
    data_status: str = "MIXED (REAL / SIMULATED / MODELLED as labelled)"
    sections: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {"generated_at": self.generated_at, "data_status": self.data_status,
                **self.sections}


def _top_movers(conn, n: int = 5) -> Dict[str, Any]:
    from ..analytics.cpi_decomposition import compute_cpi_decomposition_from_db
    dec = compute_cpi_decomposition_from_db()
    up = [c.to_dict() for c in dec.contributions if c.contribution_bps >= 0][:n]
    down = [c.to_dict() for c in sorted(dec.contributions, key=lambda c: c.contribution_bps) if c.contribution_bps < 0][:n]
    return {"top_rising": up, "top_falling": down}


def _volatility(conn) -> float:
    rows = conn.execute("SELECT daily_pct_change FROM national_indices WHERE daily_pct_change IS NOT NULL ORDER BY calculation_date DESC LIMIT 10").fetchall()
    import numpy as np
    vals = [r["daily_pct_change"] for r in rows]
    return float(np.std(vals)) if len(vals) > 1 else 0.0


def generate_daily_report() -> DailyIntelligenceReport:
    conn = get_db_connection()
    row = conn.execute("SELECT * FROM national_indices ORDER BY calculation_date DESC LIMIT 1").fetchone()

    from ..analytics.pressure import compute_pressure_from_db
    from ..data_quality.trust import compute_trust_report_from_db
    from ..forecasting.service import get_national_forecast, run_model_validation
    from ..anomaly.detector import get_anomalies_from_db

    sections: Dict[str, Any] = {}

    # 1. National index
    if row:
        sections["national_index"] = {
            "calculation_date": row["calculation_date"],
            "laspeyres_index": row["laspeyres_index"],
            "fisher_index": row["fisher_index"],
            "daily_pct_change": row["daily_pct_change"],
            "bps_headline_cpi_impact": row["bps_headline_cpi_impact"],
            "data_status": "SIMULATED",
        }
    else:
        sections["national_index"] = {"data_status": "NO DATA"}

    # 2. Movement & volatility
    sections["market_movement"] = {
        "top_movers": _top_movers(conn),
        "volatility": round(_volatility(conn), 4),
        "data_status": "SIMULATED",
    }

    # 3. CPI decomposition
    from ..analytics.cpi_decomposition import compute_cpi_decomposition_from_db
    dec = compute_cpi_decomposition_from_db()
    sections["cpi_decomposition"] = {
        "headline_cpi_impact_bps": round(dec.headline_impact_bps, 4),
        "contributors_top": [c.to_dict() for c in dec.contributions[:5]],
        "data_status": "SIMULATED",
    }

    # 4. Pressure
    pressure = compute_pressure_from_db()
    sections["pressure_score"] = {
        "score": pressure.score, "level": pressure.level,
        "components": pressure.components.sub_scores(pressure.weights),
        "data_status": "MODELLED",
    }

    # 5. Forecast
    try:
        fc = get_national_forecast(7)
        sections["forecast_7d"] = {
            "model": fc.model, "point_forecast": fc.point_forecast,
            "lower_bound": fc.lower_bound, "upper_bound": fc.upper_bound,
            "metrics": fc.metrics, "data_status": "MODELLED",
        }
    except Exception as e:
        sections["forecast_7d"] = {"data_status": "UNAVAILABLE", "reason": str(e)}

    # 6. Validation
    sections["model_validation"] = {**run_model_validation(), "data_status": "MODELLED"}

    # 7. Data quality
    dq = compute_trust_report_from_db()
    sections["data_quality"] = dq.to_dict()

    # 8. Anomalies
    sections["anomalies"] = {"count": len(get_anomalies_from_db(limit=20)),
                             "items": get_anomalies_from_db(limit=5),
                             "data_status": "SIMULATED"}

    # 9. Methodology
    sections["methodology"] = {
        "index_method": "Jevons elementary + Laspeyres/Paasche/Fisher higher-level",
        "cpi_link": f"Airfare weight {CPI_WEIGHTS['airfare_share_within_transport']*100:.2f}% of "
                    f"Transport ({CPI_WEIGHTS['transport_and_communication_cpi_weight']*100:.2f}% of headline)",
        "route_basket": len(DGCA_TOP_20_ROUTES),
        "compliance": "ILO CPI Manual / MoSPI Base 2012=100",
    }

    return DailyIntelligenceReport(
        generated_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),
        sections=sections,
    )


def report_to_csv(report: DailyIntelligenceReport) -> str:
    out = io.StringIO()
    w = csv.writer(out)
    w.writerow(["VayuSutra APIx Daily Intelligence Report", report.generated_at])
    w.writerow(["data_status", report.data_status])
    w.writerow([])
    _flatten(report.sections, w)
    return out.getvalue()


def _flatten(d: Dict[str, Any], w, prefix: str = "") -> None:
    for k, v in d.items():
        key = f"{prefix}{k}"
        if isinstance(v, dict):
            _flatten(v, w, f"{key}.")
        elif isinstance(v, list):
            for i, item in enumerate(v):
                if isinstance(item, dict):
                    _flatten(item, w, f"{key}[{i}].")
                else:
                    w.writerow([key, item])
        else:
            w.writerow([key, v])


def report_to_json(report: DailyIntelligenceReport) -> str:
    import json
    return json.dumps(report.to_dict(), indent=2, default=str)


def report_to_pdf(report: DailyIntelligenceReport) -> bytes:
    """Render a compact PDF version of the daily report (REAL/SIMULATED/MODELLED labelled)."""
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import mm
    from reportlab.lib import colors
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    import io

    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, topMargin=15 * mm, bottomMargin=15 * mm)
    styles = getSampleStyleSheet()
    title = ParagraphStyle("TitleX", parent=styles["Title"], fontSize=15, spaceAfter=6)
    h2 = ParagraphStyle("H2X", parent=styles["Heading2"], fontSize=11, spaceAfter=4)
    small = ParagraphStyle("Small", parent=styles["BodyText"], fontSize=8, leading=10)

    story = [Paragraph("VayuSutra APIx - Daily Intelligence Report", title),
             Paragraph(f"Generated {report.generated_at}<br/>Data status: {report.data_status}", small),
             Spacer(1, 6)]

    ni = report.sections.get("national_index", {})
    rows = [["Metric", "Value"]]
    for k in ["calculation_date", "laspeyres_index", "fisher_index", "daily_pct_change", "bps_headline_cpi_impact"]:
        if k in ni:
            rows.append([k.replace("_", " ").title(), str(ni[k])])
    story.append(Paragraph("National Index", h2))
    story.append(Table(rows, colWidths=[70 * mm, 100 * mm], style=TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.whitesmoke),
        ("GRID", (0, 0), (-1, -1), 0.4, colors.grey)])))

    dec = report.sections.get("cpi_decomposition", {})
    story.append(Paragraph("CPI Decomposition", h2))
    crows = [["Route", "bps"]]
    for c in dec.get("contributors_top", [])[:6]:
        crows.append([c.get("route_code", ""), f"{c.get('contribution_bps',0):.2f}"])
    story.append(Table(crows, style=TableStyle([("GRID", (0, 0), (-1, -1), 0.4, colors.grey)])))

    story.append(Spacer(1, 6))
    story.append(Paragraph("Forecast (7d)", h2))
    fc = report.sections.get("forecast_7d", {})
    story.append(Paragraph(
        f"Model: {fc.get('model','')} | Point: {fc.get('point_forecast','')} | "
        f"CI [{fc.get('lower_bound','')} - {fc.get('upper_bound','')}] | MODELLED", small))

    story.append(Spacer(1, 6))
    story.append(Paragraph("Data Quality & Pressure", h2))
    dq = report.sections.get("data_quality", {})
    pr = report.sections.get("pressure_score", {})
    story.append(Paragraph(
        f"Data Trust: {dq.get('trust_score','')} ({dq.get('level','')}) | "
        f"Pressure: {pr.get('score','')} ({pr.get('level','')}) | Anomalies: "
        f"{report.sections.get('anomalies',{}).get('count','')}", small))

    doc.build(story)
    return buf.getvalue()
