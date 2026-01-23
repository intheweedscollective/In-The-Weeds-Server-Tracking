import io
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

import requests
from io import BytesIO

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import (
    Image,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)


def _pct(count: int, total: int) -> str:
    if total <= 0:
        return "0%"
    return f"{round((count / total) * 100)}%"


def _fmt_currency(v: float) -> str:
    return f"${v:.2f}"


def _safe_float(v: Any) -> Optional[float]:
    try:
        if v is None:
            return None
        return float(v)
    except Exception:
        return None


def _metric_display_name(kpi_defs: Dict[str, Dict[str, Any]], key: str) -> str:
    return (kpi_defs.get(key, {}) or {}).get("name") or key


def _metric_format(kpi_defs: Dict[str, Dict[str, Any]], key: str) -> str:
    return (kpi_defs.get(key, {}) or {}).get("format") or "number"


def _metric_benchmark(kpi_defs: Dict[str, Dict[str, Any]], key: str) -> Optional[float]:
    bench = (kpi_defs.get(key, {}) or {}).get("benchmark")
    return _safe_float(bench)


def _format_value_for_metric(kpi_defs: Dict[str, Dict[str, Any]], metric_key: str, val: Any) -> str:
    if val is None:
        return "N/A"

    v = _safe_float(val)
    if v is None:
        return str(val)

    fmt = _metric_format(kpi_defs, metric_key)

    if metric_key == "lsc_ratio":
        # Stored as denominator on employee records (e.g., 34 -> "1 in 34")
        return f"1 in {round(v)}"

    if fmt == "currency":
        return _fmt_currency(v)

    return f"{v:.2f}"


def _bench_display(kpi_defs: Dict[str, Dict[str, Any]], metric_key: str) -> str:
    if metric_key == "lsc_ratio":
        return "1 in 100"

    bench = _metric_benchmark(kpi_defs, metric_key)
    if bench is None or bench == 0:
        return "N/A"

    fmt = _metric_format(kpi_defs, metric_key)
    if fmt == "currency":
        return _fmt_currency(bench)

    return f"{bench:.2f}"


def _distribution_bar(high: int, medium: int, low: int, total: int) -> Table:
    """Create a stacked bar using a 1-row table with 3 colored cells."""
    total = total or 1

    total_width = 6.8 * inch

    # Ensure each segment has a minimum width so it remains visible.
    min_w = 0.2 * inch
    high_w = max(min_w, total_width * (high / total)) if high > 0 else min_w
    med_w = max(min_w, total_width * (medium / total)) if medium > 0 else min_w
    low_w = max(min_w, total_width * (low / total)) if low > 0 else min_w

    w_sum = high_w + med_w + low_w
    scale = total_width / w_sum if w_sum else 1

    bar = Table(
        [["", "", ""]],
        colWidths=[high_w * scale, med_w * scale, low_w * scale],
        rowHeights=[0.22 * inch],
    )
    bar.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (0, 0), colors.HexColor("#22C55E")),
                ("BACKGROUND", (1, 0), (1, 0), colors.HexColor("#EAB308")),
                ("BACKGROUND", (2, 0), (2, 0), colors.HexColor("#F97316")),
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                ("TOPPADDING", (0, 0), (-1, -1), 0),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
            ]
        )
    )
    return bar


def _metric_block(
    analytics: Dict[str, Dict[str, Any]],
    kpi_defs: Dict[str, Dict[str, Any]],
    metric_key: str,
    styles: Dict[str, ParagraphStyle],
) -> List[Any]:
    data = analytics.get(metric_key, {}) or {}

    total = int(data.get("total") or 0)
    high = int(data.get("high") or 0)
    medium = int(data.get("medium") or 0)
    low = int(data.get("low") or 0)
    above = int(data.get("benchmark") or 0)
    avg = data.get("average")

    blocks: List[Any] = []

    blocks.append(Paragraph(_metric_display_name(kpi_defs, metric_key), styles["metric_title"]))
    blocks.append(
        Paragraph(
            f"Benchmark: {_bench_display(kpi_defs, metric_key)}  •  Employees: {total}",
            styles["metric_subtitle"],
        )
    )

    blocks.append(Spacer(1, 6))
    blocks.append(_distribution_bar(high, medium, low, total))
    blocks.append(Spacer(1, 6))

    counts_line = (
        f"High {high} ({_pct(high, total)})  •  "
        f"Medium {medium} ({_pct(medium, total)})  •  "
        f"Low {low} ({_pct(low, total)})"
    )
    blocks.append(Paragraph(counts_line, styles["metric_text"]))

    avg_display = _format_value_for_metric(kpi_defs, metric_key, avg)
    bench_is_na = _bench_display(kpi_defs, metric_key) == "N/A"
    above_display = f"{above} ({_pct(above, total)})" if not bench_is_na else "N/A"

    details = Table(
        [["Above Benchmark", above_display, "Team Average", avg_display]],
        colWidths=[1.6 * inch, 1.7 * inch, 1.6 * inch, 1.9 * inch],
    )
    details.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (0, 0), colors.HexColor("#ECFDF3")),
                ("BACKGROUND", (2, 0), (2, 0), colors.HexColor("#EFF6FF")),
                ("FONTNAME", (0, 0), (-1, -1), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, -1), 9),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#E5E7EB")),
                ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("TOPPADDING", (0, 0), (-1, -1), 8),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
            ]
        )
    )

    blocks.append(Spacer(1, 8))
    blocks.append(details)

    meeting_pct = _pct(above, total) if not bench_is_na else "N/A"
    blocks.append(Spacer(1, 6))
    blocks.append(Paragraph(f"Meeting benchmark: {meeting_pct}", styles["metric_text"]))

    return blocks


def build_analytics_pdf(analytics: Dict[str, Dict[str, Any]], kpi_defs: Dict[str, Dict[str, Any]]) -> bytes:
    """Generate a branded Analytics PDF report.

    - Page 1: logo + overview tiles + summary table
    - Next pages: metric detail sections (2 metrics per page)
    """

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        topMargin=0.55 * inch,
        bottomMargin=0.55 * inch,
        leftMargin=0.6 * inch,
        rightMargin=0.6 * inch,
    )

    base_styles = getSampleStyleSheet()

    title_style = ParagraphStyle(
        "title",
        parent=base_styles["Title"],
        fontName="Helvetica-Bold",
        fontSize=18,
        textColor=colors.HexColor("#005B96"),
        alignment=1,
        spaceAfter=6,
    )
    subtitle_style = ParagraphStyle(
        "subtitle",
        parent=base_styles["Normal"],
        fontName="Helvetica",
        fontSize=10,
        textColor=colors.HexColor("#374151"),
        alignment=1,
        spaceAfter=10,
    )
    section_style = ParagraphStyle(
        "section",
        parent=base_styles["Heading2"],
        fontName="Helvetica-Bold",
        fontSize=12,
        textColor=colors.HexColor("#005B96"),
        spaceBefore=6,
        spaceAfter=6,
        backColor=colors.HexColor("#EFF6FF"),
    )

    metric_title = ParagraphStyle(
        "metric_title",
        parent=base_styles["Heading3"],
        fontName="Helvetica-Bold",
        fontSize=12,
        textColor=colors.HexColor("#005B96"),
        spaceAfter=2,
    )
    metric_subtitle = ParagraphStyle(
        "metric_subtitle",
        parent=base_styles["Normal"],
        fontName="Helvetica",
        fontSize=9,
        textColor=colors.HexColor("#374151"),
        spaceAfter=4,
    )
    metric_text = ParagraphStyle(
        "metric_text",
        parent=base_styles["Normal"],
        fontName="Helvetica",
        fontSize=9,
        textColor=colors.HexColor("#111827"),
        spaceAfter=2,
    )

    local_styles = {
        "metric_title": metric_title,
        "metric_subtitle": metric_subtitle,
        "metric_text": metric_text,
    }

    story: List[Any] = []

    # Logo
    try:
        logo_url = "https://customer-assets.emergentagent.com/job_beaba37a-d1bc-43b6-b0ee-0f4c332229d2/artifacts/shpi6789_IMG_0599.png"
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

    # Overview tiles
    total_all = sum(int((analytics.get(k, {}) or {}).get("total") or 0) for k in kpi_defs.keys())
    high_all = sum(int((analytics.get(k, {}) or {}).get("high") or 0) for k in kpi_defs.keys())
    med_all = sum(int((analytics.get(k, {}) or {}).get("medium") or 0) for k in kpi_defs.keys())
    low_all = sum(int((analytics.get(k, {}) or {}).get("low") or 0) for k in kpi_defs.keys())
    above_all = sum(int((analytics.get(k, {}) or {}).get("benchmark") or 0) for k in kpi_defs.keys())

    overview_rows = [[f"Above Benchmark\n{_pct(above_all, total_all)}", f"High\n{_pct(high_all, total_all)}", f"Medium\n{_pct(med_all, total_all)}", f"Low\n{_pct(low_all, total_all)}"]]
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

    # Summary table
    story.append(Paragraph("Summary Table", section_style))

    rows = [["Metric", "High", "Medium", "Low", "Benchmark", "Above Bench", "Avg", "N"]]
    for metric_key in kpi_defs.keys():
        meta = kpi_defs.get(metric_key, {}) or {}
        data = analytics.get(metric_key, {}) or {}

        high = int(data.get("high") or 0)
        med = int(data.get("medium") or 0)
        low = int(data.get("low") or 0)
        n = int(data.get("total") or 0)
        avg = data.get("average")

        above_count = int(data.get("benchmark") or 0)
        bench_is_na = _bench_display(kpi_defs, metric_key) == "N/A"

        rows.append(
            [
                meta.get("name", metric_key),
                f"{high} ({_pct(high, n)})",
                f"{med} ({_pct(med, n)})",
                f"{low} ({_pct(low, n)})",
                _bench_display(kpi_defs, metric_key),
                f"{above_count} ({_pct(above_count, n)})" if not bench_is_na else "N/A",
                _format_value_for_metric(kpi_defs, metric_key, avg),
                str(n),
            ]
        )

    summary = Table(
        rows,
        colWidths=[2.0 * inch, 0.75 * inch, 0.85 * inch, 0.75 * inch, 0.9 * inch, 1.05 * inch, 0.75 * inch, 0.45 * inch],
    )
    summary.setStyle(
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

    story.append(summary)

    # Metric details pages (2 per page)
    metric_keys = list(kpi_defs.keys())
    pairs: List[Tuple[str, str]] = []
    i = 0
    while i < len(metric_keys):
        a = metric_keys[i]
        b = metric_keys[i + 1] if i + 1 < len(metric_keys) else ""
        pairs.append((a, b))
        i += 2

    for a, b in pairs:
        story.append(PageBreak())
        story.append(Paragraph("Metric Details", section_style))
        story.append(Spacer(1, 8))
        story.extend(_metric_block(analytics, kpi_defs, a, local_styles))
        if b:
            story.append(Spacer(1, 16))
            story.extend(_metric_block(analytics, kpi_defs, b, local_styles))

    doc.build(story)
    buffer.seek(0)
    return buffer.getvalue()
