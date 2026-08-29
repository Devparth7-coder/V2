"""
VayuSutra APIx - Automated Intelligence Report Routers
"""
import io
from fastapi import APIRouter, Response
from fastapi.responses import StreamingResponse

router = APIRouter(prefix="/api/v1/reports", tags=["Reports"])


@router.get("/daily", summary="Daily intelligence report (JSON)")
def daily_report():
    from ...reports.report import generate_daily_report
    return generate_daily_report().to_dict()


@router.get("/daily/csv", summary="Daily intelligence report (CSV)")
def daily_report_csv():
    from ...reports.report import generate_daily_report, report_to_csv
    report = generate_daily_report()
    csv_text = report_to_csv(report)
    return StreamingResponse(
        io.BytesIO(csv_text.encode("utf-8")),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=vayusutra_daily_report.csv"}
    )


@router.get("/daily/json", summary="Daily intelligence report (JSON download)")
def daily_report_json():
    from ...reports.report import generate_daily_report, report_to_json
    report = generate_daily_report()
    return Response(content=report_to_json(report), media_type="application/json")


@router.get("/daily/pdf", summary="Daily intelligence report (PDF)")
def daily_report_pdf():
    from ...reports.report import generate_daily_report, report_to_pdf
    report = generate_daily_report()
    pdf_bytes = report_to_pdf(report)
    return Response(content=pdf_bytes, media_type="application/pdf",
                    headers={"Content-Disposition": "attachment; filename=vayusutra_daily_report.pdf"})
