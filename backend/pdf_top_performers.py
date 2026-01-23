import io
from datetime import datetime
from typing import Any, Dict, List

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle


def build_top_performers_pdf(
    employees: List[Dict[str, Any]],
    kpi_definitions: Dict[str, Dict[str, Any]],
) -> bytes:
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        topMargin=0.5 * inch,
        bottomMargin=0.5 * inch,
        leftMargin=0.6 * inch,
        rightMargin=0.6 * inch,
    )

    styles = getSampleStyleSheet()

    title_style = ParagraphStyle(
        "title",
        parent=styles["Title"],
        fontName="Helvetica-Bold",
        fontSize=20,
        textColor=colors.HexColor("#D12E2E"),
        alignment=1,
        spaceAfter=10,
    )

    subtitle_style = ParagraphStyle(
        "subtitle",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=10,
        textColor=colors.HexColor("#374151"),
        alignment=1,
        spaceAfter=16,
    )

    section_style = ParagraphStyle(
        "section",
        parent=styles["Heading2"],
        fontName="Helvetica-Bold",
        fontSize=12,
        textColor=colors.HexColor("#005B96"),
        spaceBefore=10,
        spaceAfter=6,
    )

    story: List[Any] = []
    story.append(Paragraph("Top Performers Report", title_style))
    story.append(
        Paragraph(
            f"Generated {datetime.now().strftime('%m/%d/%Y')} - Bubba Gump Shrimp Co. (Las Vegas)",
            subtitle_style,
        )
    )

    # Top 10 overall (cumulative score)
    overall = [e for e in employees if e.get("cumulative_score") is not None]
    overall.sort(key=lambda x: float(x.get("cumulative_score") or 0), reverse=True)
    overall = overall[:10]

    story.append(Paragraph("Top 10 Overall (Cumulative Score)", section_style))
    overall_rows = [["Rank", "Employee", "Position", "Cumulative Score"]]
    for idx, e in enumerate(overall, start=1):
        overall_rows.append(
            [
                str(idx),
                e.get("name", ""),
                e.get("position", ""),
                f"{float(e.get('cumulative_score') or 0):.2f}",
            ]
        )

    overall_table = Table(
        overall_rows,
        colWidths=[0.6 * inch, 2.2 * inch, 2.2 * inch, 1.4 * inch],
    )
    overall_table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#D12E2E")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, -1), 9),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#E5E7EB")),
                (
                    "ROWBACKGROUNDS",
                    (0, 1),
                    (-1, -1),
                    [colors.white, colors.HexColor("#F9F9F9")],
                ),
            ]
        )
    )
    story.append(overall_table)
    story.append(Spacer(1, 12))

    metric_keys = ["ppa", "gpg", "pplbw", "lsc_ratio", "metric_bonus_points", "cumulative_score"]

    for key in metric_keys:
        meta = kpi_definitions.get(key, {})
        metric_name = meta.get("name", key)

        vals = [e for e in employees if e.get(key) is not None]
        if key == "lsc_ratio":
            vals.sort(key=lambda x: float(x.get(key) or 0))
        else:
            vals.sort(key=lambda x: float(x.get(key) or 0), reverse=True)
        vals = vals[:10]

        story.append(Paragraph(f"Top 10 - {metric_name}", section_style))
        rows = [["Rank", "Employee", "Position", "Value"]]

        for idx, e in enumerate(vals, start=1):
            v = e.get(key)
            if v is None:
                v_str = ""
            else:
                if meta.get("format") == "currency":
                    v_str = f"${float(v):.2f}"
                elif meta.get("format") == "ratio":
                    v_str = f"1 in {round(float(v))}"
                else:
                    v_str = f"{float(v):.2f}" if isinstance(v, (int, float)) else str(v)

            rows.append([str(idx), e.get("name", ""), e.get("position", ""), v_str])

        table = Table(rows, colWidths=[0.6 * inch, 2.2 * inch, 2.2 * inch, 1.4 * inch])
        table.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#005B96")),
                    ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                    ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                    ("FONTSIZE", (0, 0), (-1, -1), 9),
                    ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#E5E7EB")),
                    (
                        "ROWBACKGROUNDS",
                        (0, 1),
                        (-1, -1),
                        [colors.white, colors.HexColor("#F9F9F9")],
                    ),
                ]
            )
        )
        story.append(table)
        story.append(Spacer(1, 10))

    doc.build(story)
    buffer.seek(0)
    return buffer.getvalue()
