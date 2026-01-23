import io
from datetime import datetime
from typing import Any, Dict

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import Image, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
import requests
from io import BytesIO



def _pct(count: int, total: int) -> str:
    if total <= 0:
        return "0%"
    return f"{round((count / total) * 100)}%"


def build_analytics_pdf(analytics: Dict[str, Dict[str, Any]], kpi_defs: Dict[str, Dict[str, Any]]) -> bytes:
    """Generate a printable Analytics PDF report (high/medium/low + benchmark + average)."""

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        topMargin=0.55 * inch,
        bottomMargin=0.55 * inch,
        leftMargin=0.6 * inch,
        rightMargin=0.6 * inch,
    )

    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        "title",
        parent=styles["Title"],
        fontName="Helvetica-Bold",
        fontSize=18,
        textColor=colors.HexColor("#005B96"),
        alignment=1,
        spaceAfter=6,
    )
    subtitle_style = ParagraphStyle(
        "subtitle",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=10,
        textColor=colors.HexColor("#374151"),
        alignment=1,
        spaceAfter=14,
    )
    section_style = ParagraphStyle(
        "section",
        parent=styles["Heading2"],
        fontName="Helvetica-Bold",
        fontSize=12,
        textColor=colors.HexColor("#005B96"),
        spaceBefore=6,
        spaceAfter=6,
    )

    story = []

    # Add logo (same as review sheets)
    try:
        logo_url = "https://customer-assets.emergentagent.com/job_beaba37a-d1bc-43b6-b0ee-0f4c332229d2/artifacts/shpi6789_IMG_0599.png"

    # Overview tiles (as a simple table)
    total_all = sum(int((analytics.get(k, {}) or {}).get("total") or 0) for k in kpi_defs.keys())
    high_all = sum(int((analytics.get(k, {}) or {}).get("high") or 0) for k in kpi_defs.keys())
    med_all = sum(int((analytics.get(k, {}) or {}).get("medium") or 0) for k in kpi_defs.keys())
    low_all = sum(int((analytics.get(k, {}) or {}).get("low") or 0) for k in kpi_defs.keys())
    above_all = sum(int((analytics.get(k, {}) or {}).get("benchmark") or 0) for k in kpi_defs.keys())

    overview_rows = [
        [
            f"Above Benchmark\n{_pct(above_all, total_all)}",
            f"High\n{_pct(high_all, total_all)}",
            f"Medium\n{_pct(med_all, total_all)}",
            f"Low\n{_pct(low_all, total_all)}",
        ]
    ]

    overview = Table(overview_rows, colWidths=[1.7 * inch, 1.7 * inch, 1.7 * inch, 1.7 * inch])
    overview.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (0, 0), colors.HexColor("#ECFDF3")),
                ("BACKGROUND", (1, 0), (1, 0), colors.HexColor("#EFF6FF")),
                ("BACKGROUND", (2, 0), (2, 0), colors.HexColor("#FEF9C3")),
                ("BACKGROUND", (3, 0), (3, 0), colors.HexColor("#FFEDD5")),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#E5E7EB")),
                ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("FONTNAME", (0, 0), (-1, -1), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, -1), 10),
                ("TOPPADDING", (0, 0), (-1, -1), 10),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 10),
            ]
        )
    )

    story.append(overview)
    story.append(Spacer(1, 12))

        response = requests.get(logo_url, timeout=10)
        logo_buffer = BytesIO(response.content)
        logo_img = Image(logo_buffer, width=0.78 * inch, height=0.78 * inch)
        logo_img.hAlign = "CENTER"
        story.append(logo_img)
        story.append(Spacer(1, 6))
    except Exception:
        pass

    story.append(Paragraph("Performance Analytics Report", title_style))
    story.append(
        Paragraph(
            f"Generated {datetime.now().strftime('%m/%d/%Y')} - Bubba Gump Shrimp Co. (Las Vegas)",
            subtitle_style,
        )
    )

    story.append(Paragraph("Metric Distributions", section_style))

    rows = [
        [
            "Metric",
            "High",
            "Medium",
            "Low",
            "Benchmark",
            "Above Bench",
            "Avg",
            "N",
        ]
    ]

    def format_value(metric: str, val: Any) -> str:
        if val is None:
            return "N/A"
        try:
            v = float(val)
        except Exception:
            return str(val)

        fmt = kpi_defs.get(metric, {}).get("format")
        if metric == "lsc_ratio":
            # lsc_ratio benchmark is 0.01 (1 in 100), but analytics stores denominators for employee values.
            # For report, show benchmark as 1 in 100.
            return f"1 in {round(v)}"
        if fmt == "currency":
            return f"${v:.2f}"
        if fmt == "number":
            return f"{v:.2f}"
        return f"{v:.2f}"

    for metric_key, meta in kpi_defs.items():
        data = analytics.get(metric_key, {})
        high = int(data.get("high") or 0)
        med = int(data.get("medium") or 0)
        low = int(data.get("low") or 0)
        n = int(data.get("total") or 0)
        avg = data.get("average")
        bench_val = data.get("benchmarkValue")

        bench_display = ""
        if metric_key == "lsc_ratio":
            bench_display = "1 in 100"
        else:
            bench_display = format_value(metric_key, bench_val)

        rows.append(
            [
                meta.get("name", metric_key),
                f"{high} ({_pct(high, n)})",
                f"{med} ({_pct(med, n)})",
                f"{low} ({_pct(low, n)})",
                bench_display,
                f"{int(data.get('benchmark') or 0)} ({_pct(int(data.get('benchmark') or 0), n)})",
                format_value(metric_key, avg),
                str(n),
            ]
        )

    table = Table(
        rows,
        colWidths=[2.0 * inch, 0.75 * inch, 0.85 * inch, 0.75 * inch, 0.9 * inch, 1.05 * inch, 0.75 * inch, 0.45 * inch],
    )
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#005B96")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, -1), 8),
                ("ALIGN", (1, 0), (-1, -1), "CENTER"),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#E5E7EB")),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F9F9F9")]),
            ]
        )
    )

    story.append(table)
    story.append(Spacer(1, 10))

    doc.build(story)
    buffer.seek(0)
    return buffer.getvalue()
