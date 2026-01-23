import io
from datetime import datetime
from typing import Any, Dict

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle


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
                format_value(metric_key, avg),
                str(n),
            ]
        )

    table = Table(
        rows,
        colWidths=[2.2 * inch, 0.8 * inch, 0.9 * inch, 0.8 * inch, 1.0 * inch, 0.8 * inch, 0.45 * inch],
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
