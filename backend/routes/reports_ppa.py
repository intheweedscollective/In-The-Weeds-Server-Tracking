"""
PPA Ranking Report
==================

Operator-facing report (2026-06): every active employee sorted by
PPA, top to bottom, with rank, tier, and +/- vs the LOCATION average
(the mean PPA of all active employees in the current quarter).

Two endpoints:
  GET /api/v2/reports/ppa-ranking       → JSON for the on-screen card
  GET /api/v2/reports/ppa-ranking/pdf   → branded printable PDF

Both use the same `_fetch_active_employees` helper as the slide
generators, so the report stays in sync with snapshot-frozen data.
"""

from io import BytesIO
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Response

from reportlab.lib.pagesizes import letter
from reportlab.lib import colors
from reportlab.lib.units import inch
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_CENTER, TA_RIGHT
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak,
)


reports_router = APIRouter(prefix="/v2/reports", tags=["Reports"])


def get_db():
    """Get database instance from shared module"""
    from database import get_database
    return get_database()


# ---------------------------------------------------------------------------
# Shared helper: build the ranking rows
# ---------------------------------------------------------------------------

async def _build_ppa_ranking(
    quarter: Optional[str],
    year: Optional[int],
) -> Dict[str, Any]:
    """Return the active-quarter PPA ranking (employees sorted high→low)
    along with the location average and metadata. If quarter/year are
    omitted, resolves from `snapshot_workflow.is_current=True`."""
    db = get_db()

    if not quarter or not year:
        active_snap = await db.snapshot_workflow.find_one(
            {"is_current": True},
            {"_id": 0, "quarter": 1, "year": 1, "name": 1, "id": 1},
        )
        if not active_snap:
            raise HTTPException(
                status_code=404,
                detail="No active snapshot — cannot resolve quarter for PPA ranking.",
            )
        quarter = active_snap["quarter"]
        year = active_snap["year"]
        snap_name = active_snap.get("name")
    else:
        snap_name = None

    from routes.yodeck_slides import _fetch_active_employees
    employees = await _fetch_active_employees(db, year, quarter, limit=5000)
    if not employees:
        return {
            "quarter": quarter,
            "year": year,
            "snapshot_name": snap_name,
            "location_average_ppa": 0.0,
            "rows": [],
            "count": 0,
        }

    # Filter to rows that actually have a PPA value — a 0/None PPA is
    # treated as "no data" so it doesn't pollute the location average
    # nor sit at the bottom of the report as a fake last place.
    scored = [
        e for e in employees
        if isinstance(e.get("ppa"), (int, float)) and (e.get("ppa") or 0) > 0
    ]

    # Location average: arithmetic mean of all employees' PPA values
    # for the active quarter. Per operator: "use all of the PPA
    # available" — every scored employee in the snapshot contributes
    # equally (no weighting by guest count). Keeps the comparison
    # intuitive: "vs the average employee's PPA at our store."
    if scored:
        location_avg = sum((e["ppa"] or 0) for e in scored) / len(scored)
    else:
        location_avg = 0.0

    # Sort high → low, ties broken alphabetically so the order is
    # deterministic across reloads.
    scored.sort(
        key=lambda e: (-(e.get("ppa") or 0), (e.get("name") or "").lower()),
    )

    rows: List[Dict[str, Any]] = []
    for i, e in enumerate(scored, start=1):
        ppa = float(e.get("ppa") or 0)
        diff = round(ppa - location_avg, 2)
        rows.append({
            "rank":          i,
            "employee_id":   e.get("id"),
            "name":          e.get("name") or e.get("display_name"),
            "tier":          e.get("tier_label") or "",
            "ppa":           round(ppa, 2),
            "vs_location":   diff,
            "vs_location_pct": round((diff / location_avg * 100), 1) if location_avg > 0 else 0.0,
            "guests":        e.get("guests") or e.get("guest_count") or 0,
            "score_ppa":     round(float(e.get("score_ppa") or 0), 1),
        })

    return {
        "quarter": quarter,
        "year": year,
        "snapshot_name": snap_name,
        "location_average_ppa": round(location_avg, 2),
        "rows": rows,
        "count": len(rows),
    }


# ---------------------------------------------------------------------------
# JSON endpoint — feeds the on-screen card
# ---------------------------------------------------------------------------

@reports_router.get("/ppa-ranking")
async def get_ppa_ranking(
    quarter: Optional[str] = None,
    year: Optional[int] = None,
):
    """Return a sorted PPA ranking for the active (or specified) quarter.
    Default quarter/year resolves from the current active snapshot so
    the operator never has to pass them explicitly."""
    return await _build_ppa_ranking(quarter, year)


# ---------------------------------------------------------------------------
# PDF endpoint — branded printable
# ---------------------------------------------------------------------------

# Brand palette — matches the Yodeck slide system (deep navy + amber accent).
BRAND_NAVY    = colors.HexColor("#0F172A")
BRAND_PANEL   = colors.HexColor("#1E293B")
BRAND_AMBER   = colors.HexColor("#F59E0B")
BRAND_EMERALD = colors.HexColor("#10B981")
BRAND_ROSE    = colors.HexColor("#F43F5E")
BRAND_INK     = colors.HexColor("#E2E8F0")
BRAND_MUTED   = colors.HexColor("#94A3B8")


def _build_pdf(data: Dict[str, Any]) -> bytes:
    """Render the PPA ranking as a branded PDF with header, location
    average callout, and a striped data table."""
    buf = BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=letter,
        leftMargin=0.5 * inch,
        rightMargin=0.5 * inch,
        topMargin=0.5 * inch,
        bottomMargin=0.5 * inch,
        title=f"PPA Ranking — {data['quarter']} {data['year']}",
        author="In the Weeds Collective",
    )

    styles = getSampleStyleSheet()
    title = ParagraphStyle(
        "title", parent=styles["Heading1"],
        fontName="Helvetica-Bold", fontSize=22,
        textColor=BRAND_INK, alignment=TA_CENTER, spaceAfter=4,
    )
    subtitle = ParagraphStyle(
        "subtitle", parent=styles["Normal"],
        fontName="Helvetica", fontSize=11,
        textColor=BRAND_MUTED, alignment=TA_CENTER, spaceAfter=14,
    )
    callout = ParagraphStyle(
        "callout", parent=styles["Normal"],
        fontName="Helvetica-Bold", fontSize=13,
        textColor=BRAND_AMBER, alignment=TA_CENTER, spaceAfter=14,
    )

    story: List[Any] = []
    story.append(Paragraph("PPA Ranking", title))
    story.append(Paragraph(
        f"{data['quarter']} {data['year']} "
        f"&nbsp;·&nbsp; In the Weeds Collective",
        subtitle,
    ))
    story.append(Paragraph(
        f"Location average PPA: ${data['location_average_ppa']:.2f}"
        f" &nbsp;·&nbsp; {data['count']} servers ranked",
        callout,
    ))

    # Table data
    header = ["#", "Name", "Tier", "PPA", "vs Location", "%"]
    table_rows: List[List[Any]] = [header]
    for r in data["rows"]:
        diff = r["vs_location"]
        sign = "+" if diff > 0 else ("" if diff == 0 else "−")
        diff_text = f"{sign}${abs(diff):.2f}"
        pct = r["vs_location_pct"]
        pct_sign = "+" if pct > 0 else ("" if pct == 0 else "−")
        pct_text = f"{pct_sign}{abs(pct):.1f}%"
        table_rows.append([
            str(r["rank"]),
            r["name"] or "—",
            r["tier"] or "—",
            f"${r['ppa']:.2f}",
            diff_text,
            pct_text,
        ])

    tbl = Table(
        table_rows,
        colWidths=[0.5 * inch, 2.6 * inch, 1.2 * inch,
                   1.0 * inch, 1.2 * inch, 0.9 * inch],
        repeatRows=1,
    )

    style = TableStyle([
        # Header
        ("BACKGROUND",   (0, 0), (-1, 0), BRAND_NAVY),
        ("TEXTCOLOR",    (0, 0), (-1, 0), BRAND_AMBER),
        ("FONTNAME",     (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE",     (0, 0), (-1, 0), 10),
        ("ALIGN",        (0, 0), (-1, 0), "CENTER"),
        ("BOTTOMPADDING", (0, 0), (-1, 0), 8),
        ("TOPPADDING",    (0, 0), (-1, 0), 8),

        # Body
        ("FONTNAME",  (0, 1), (-1, -1), "Helvetica"),
        ("FONTSIZE",  (0, 1), (-1, -1), 9.5),
        ("TEXTCOLOR", (0, 1), (-1, -1), BRAND_INK),
        ("ALIGN",     (0, 1), (0, -1),  "CENTER"),  # rank
        ("ALIGN",     (1, 1), (1, -1),  "LEFT"),    # name
        ("ALIGN",     (2, 1), (2, -1),  "CENTER"),  # tier
        ("ALIGN",     (3, 1), (-1, -1), "RIGHT"),   # numeric cols
        ("ROWBACKGROUNDS", (0, 1), (-1, -1),
            [BRAND_PANEL, colors.HexColor("#0B1220")]),
        ("LINEBELOW", (0, 0), (-1, 0), 1.2, BRAND_AMBER),
        ("LINEBELOW", (0, -1), (-1, -1), 0.5, BRAND_NAVY),
        ("BOTTOMPADDING", (0, 1), (-1, -1), 6),
        ("TOPPADDING",    (0, 1), (-1, -1), 6),
    ])

    # Colorise the "vs Location" and "%" cells per sign so the eye
    # picks out top/bottom performers without reading the numbers.
    for i, r in enumerate(data["rows"], start=1):
        if r["vs_location"] > 0:
            style.add("TEXTCOLOR", (4, i), (5, i), BRAND_EMERALD)
        elif r["vs_location"] < 0:
            style.add("TEXTCOLOR", (4, i), (5, i), BRAND_ROSE)
        else:
            style.add("TEXTCOLOR", (4, i), (5, i), BRAND_MUTED)

    tbl.setStyle(style)
    story.append(tbl)

    # Footer note
    story.append(Spacer(1, 0.2 * inch))
    story.append(Paragraph(
        "Generated by In the Weeds Collective &nbsp;·&nbsp; "
        f"Active snapshot: {data.get('snapshot_name') or '—'}",
        ParagraphStyle(
            "footer", parent=styles["Normal"],
            fontName="Helvetica-Oblique", fontSize=8,
            textColor=BRAND_MUTED, alignment=TA_CENTER,
        ),
    ))

    # Render the navy page background by drawing a filled rect under
    # every page. Done via onFirstPage/onLaterPages hooks.
    def _draw_bg(canv, _doc):
        canv.saveState()
        canv.setFillColor(BRAND_NAVY)
        canv.rect(0, 0, letter[0], letter[1], fill=1, stroke=0)
        canv.restoreState()

    doc.build(story, onFirstPage=_draw_bg, onLaterPages=_draw_bg)
    return buf.getvalue()


@reports_router.get("/ppa-ranking/pdf")
async def get_ppa_ranking_pdf(
    quarter: Optional[str] = None,
    year: Optional[int] = None,
):
    """Return the PPA ranking as a branded PDF."""
    data = await _build_ppa_ranking(quarter, year)
    pdf_bytes = _build_pdf(data)
    filename = f"ppa_ranking_{data['quarter']}_{data['year']}.pdf"
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@reports_router.get("/ppa-ranking/slide")
async def get_ppa_ranking_slide(
    quarter: Optional[str] = None,
    year: Optional[int] = None,
):
    """Return the PPA ranking as a 1920x1080 Yodeck slide (PNG)."""
    data = await _build_ppa_ranking(quarter, year)
    from yodeck_slides import generate_ppa_ranking_slide
    png_bytes = generate_ppa_ranking_slide(
        rows=data["rows"],
        location_avg=data["location_average_ppa"],
        quarter=data["quarter"],
        year=data["year"],
    )
    filename = f"ppa_ranking_{data['quarter']}_{data['year']}.png"
    return Response(
        content=png_bytes,
        media_type="image/png",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
