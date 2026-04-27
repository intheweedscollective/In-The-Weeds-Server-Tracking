"""
Full Rankings PDF Generator — Snapshot Style.

Mirrors `png_full_rankings.py` exactly so the printed PDF and the digital
PNG share the same look:
  - Dark navy canvas + left sidebar (logo, title, legend, footer).
  - Right-side table with dark navy body rows and colored "tiles" for
    every metric cell. The 3-pt gap between tiles renders as a visible
    border per the reference template.
"""
import io
import os
from datetime import datetime
from typing import Any, Dict, List

from reportlab.lib import colors
from reportlab.lib.units import inch
from reportlab.pdfgen import canvas
from reportlab.lib.utils import ImageReader


# Locked palette — identical to png_full_rankings.REF_COLORS.
COLORS = {
    "background": "#0F172A",
    "header_bg":  "#0F172A",
    "row_bg":     "#0F172A",
    "blue":       "#0C769E",
    "green":      "#33CC33",
    "yellow":     "#FFFF00",
    "red":        "#FF0000",
    "text_white": "#FFFFFF",
    "text_dark":  "#000000",
    "trend_up":   "#33CC33",
    "trend_flat": "#9CA3AF",
}

LOGO_PATH = "/app/backend/assets/bubba_gump_logo.png"


def get_cell_color(value: float, metric_type: str = "percentage") -> str:
    """Same thresholds as png_full_rankings._ref_cell_color."""
    if metric_type == "percentage":
        if value > 100: return COLORS["blue"]
        if value >= 80: return COLORS["green"]
        if value >= 60: return COLORS["yellow"]
        return COLORS["red"]
    if metric_type == "cv":
        if value <= 0:  return COLORS["red"]
        if value > 11:  return COLORS["blue"]
        if value >= 8:  return COLORS["green"]
        return COLORS["yellow"]
    if metric_type == "rt":
        if value <= 0:  return COLORS["red"]
        if value >= 10: return COLORS["blue"]
        if value >= 5:  return COLORS["green"]
        return COLORS["yellow"]
    if metric_type == "bonus":
        if value <= 0:  return COLORS["red"]
        if value >= 5:  return COLORS["blue"]
        if value >= 3:  return COLORS["green"]
        return COLORS["yellow"]
    if metric_type == "score":
        if value >= 100: return COLORS["blue"]
        if value >= 80:  return COLORS["green"]
        if value >= 70:  return COLORS["yellow"]
        return COLORS["red"]
    return COLORS["green"]


def get_text_color_for_bg(bg_color: str) -> str:
    return COLORS["text_dark"] if bg_color == COLORS["yellow"] else COLORS["text_white"]


def _signed(val: float) -> str:
    return f"{val:+.1f}"


def build_full_rankings_pdf(
    rankings: List[Dict[str, Any]],
    quarter: str,
    year: int,
    thresholds: Dict[str, float],
) -> bytes:
    """Build the snapshot-style full rankings PDF (matches PNG layout)."""
    buffer = io.BytesIO()

    # 16:9 canvas to match the PNG.
    page_width = 16 * inch
    page_height = 9 * inch
    c = canvas.Canvas(buffer, pagesize=(page_width, page_height))

    # Dark navy canvas
    c.setFillColor(colors.HexColor(COLORS["background"]))
    c.rect(0, 0, page_width, page_height, fill=True, stroke=False)

    # ==================== LEFT SIDEBAR ====================
    sidebar_width = 3.0 * inch
    cx = sidebar_width / 2

    # ---- Logo ----
    logo_y = page_height - 1.2 * inch
    if os.path.exists(LOGO_PATH):
        try:
            logo = ImageReader(LOGO_PATH)
            iw, ih = logo.getSize()
            target_w = 1.8 * inch
            ratio = target_w / iw
            target_h = ih * ratio
            c.drawImage(logo, cx - target_w / 2, logo_y - target_h / 2,
                        width=target_w, height=target_h, mask='auto')
        except Exception:
            pass

    # ---- Title block ----
    title_y = logo_y - 1.4 * inch
    c.setFillColor(colors.HexColor(COLORS["text_white"]))
    c.setFont("Helvetica-Bold", 22)
    c.drawCentredString(cx, title_y, f"{quarter} SERVER")

    c.setFillColor(colors.HexColor(COLORS["red"]))
    c.setFont("Helvetica-Bold", 28)
    c.drawCentredString(cx, title_y - 0.42 * inch, "PERFORMANCE")

    c.setFillColor(colors.HexColor(COLORS["text_white"]))
    c.setFont("Helvetica-Bold", 22)
    c.drawCentredString(cx, title_y - 0.82 * inch, "SNAPSHOT")

    c.setFillColor(colors.HexColor(COLORS["red"]))
    c.setFont("Helvetica-Bold", 13)
    c.drawCentredString(cx, title_y - 1.15 * inch,
                        datetime.now().strftime("%B %d, %Y"))

    # ---- Legend ----
    legend_y = title_y - 1.65 * inch
    legend_items = [
        ("EXCEEDING ALL",   "EXPECTATIONS", COLORS["blue"]),
        ("MEETING",         "EXPECTATIONS", COLORS["green"]),
        ("WORK IN",         "PROGRESS",     COLORS["yellow"]),
        ("NEEDS IMMEDIATE", "IMPROVEMENT",  COLORS["red"]),
    ]
    for i, (line1, line2, color) in enumerate(legend_items):
        y_pos = legend_y - (i * 0.55 * inch)
        c.setFillColor(colors.HexColor(color))
        c.rect(0.35 * inch, y_pos - 0.05 * inch, 0.22 * inch, 0.4 * inch,
               fill=True, stroke=False)
        c.setFillColor(colors.HexColor(color))
        c.setFont("Helvetica-Bold", 9.5)
        c.drawString(0.65 * inch, y_pos + 0.2 * inch, line1)
        c.drawString(0.65 * inch, y_pos + 0.05 * inch, line2)

    # ---- Footer ----
    footer_y = 0.7 * inch
    c.setFillColor(colors.HexColor(COLORS["text_white"]))
    c.setFont("Helvetica-Bold", 9)
    c.drawCentredString(cx, footer_y + 0.35 * inch, "DON'T WAIT TO IMPACT")
    c.drawCentredString(cx, footer_y + 0.18 * inch, "THIS NUMBER.")
    c.drawCentredString(cx, footer_y - 0.08 * inch, "IF YOU HAVE QUESTIONS")
    c.drawCentredString(cx, footer_y - 0.25 * inch, "PLEASE SEE MANAGEMENT.")

    # ==================== MAIN TABLE ====================
    table_x = sidebar_width + 0.2 * inch
    table_width = page_width - sidebar_width - 0.4 * inch
    table_top = page_height - 0.3 * inch

    headers = ["Rank", "Name", "Trend", "PPA", "LBW", "GLASS",
               "LSC", "CV", "RT", "Bonus", "Score"]
    col_props = [0.06, 0.14, 0.06, 0.085, 0.085, 0.085,
                 0.085, 0.085, 0.085, 0.09, 0.09]
    col_widths = [p * table_width for p in col_props]
    # absorb rounding into last col
    col_widths[-1] += table_width - sum(col_widths)

    # ---- Header bar ----
    header_h = 0.38 * inch
    c.setFillColor(colors.HexColor(COLORS["header_bg"]))
    c.rect(table_x, table_top - header_h, table_width, header_h,
           fill=True, stroke=False)

    c.setFillColor(colors.HexColor(COLORS["text_white"]))
    c.setFont("Helvetica-Bold", 10)
    x_pos = table_x
    for header, w in zip(headers, col_widths):
        c.drawCentredString(x_pos + w / 2,
                            table_top - header_h + 0.13 * inch, header)
        x_pos += w

    # ---- Body ----
    body_top = table_top - header_h
    body_bottom = 0.3 * inch
    avail = body_top - body_bottom
    n = max(1, len(rankings))
    row_h = max(0.22 * inch, min(0.36 * inch, avail / n))

    # Dark navy body bg — cell tiles render on top with a small inset.
    c.setFillColor(colors.HexColor(COLORS["row_bg"]))
    c.rect(table_x, body_bottom, table_width, body_top - body_bottom,
           fill=True, stroke=False)

    cy = body_top
    for emp in rankings:
        cy -= row_h
        if cy < body_bottom:
            break

        pos_label   = emp.get("position_label", "")
        name        = (emp.get("name", "") or "")[:14]
        score       = emp.get("total_score", 0) or 0
        ppa_pct     = ((emp.get("ppa_points", {}).get("earned", 0) or 0) / 30) * 100
        lbw_pct     = ((emp.get("lbw_points", {}).get("earned", 0) or 0) / 25) * 100
        glass_pct   = ((emp.get("glassware_points", {}).get("earned", 0) or 0) / 20) * 100
        lsc_pct     = ((emp.get("lsc_points", {}).get("earned", 0) or 0) / 30) * 100
        cv_score    = emp.get("cv_score", 0) or 0
        rt_mentions = emp.get("review_mentions", 0) or emp.get("rt_mentions", 0) or 0
        bonus       = emp.get("bonus_points", 0) or emp.get("metric_bonus", 0) or 0

        trend_dir = (emp.get("trend") or "up").lower()
        if trend_dir in ("up", "improving", "improved"):
            trend_glyph, trend_col = "\u25B2", COLORS["trend_up"]
        elif trend_dir in ("down", "declining"):
            trend_glyph, trend_col = "\u25BC", COLORS["red"]
        else:
            trend_glyph, trend_col = "\u2014", COLORS["trend_flat"]

        row_data = [
            (pos_label,            None,                                       "center", COLORS["text_white"]),
            (name,                 None,                                       "left",   COLORS["text_white"]),
            (trend_glyph,          None,                                       "center", trend_col),
            (f"{ppa_pct:.0f}%",    get_cell_color(ppa_pct,   "percentage"),    "center", None),
            (f"{lbw_pct:.0f}%",    get_cell_color(lbw_pct,   "percentage"),    "center", None),
            (f"{glass_pct:.0f}%",  get_cell_color(glass_pct, "percentage"),    "center", None),
            (f"{lsc_pct:.0f}%",    get_cell_color(lsc_pct,   "percentage"),    "center", None),
            (_signed(cv_score),    get_cell_color(cv_score,  "cv"),            "center", None),
            (_signed(rt_mentions), get_cell_color(rt_mentions,"rt"),           "center", None),
            (_signed(bonus),       get_cell_color(bonus,     "bonus"),         "center", None),
            (f"{score:.1f}",       get_cell_color(score,     "score"),         "center", None),
        ]

        pad = 0.04 * inch  # gutter between tiles → looks like a border
        x_pos = table_x
        for (text, cell_color, align, override_text), w in zip(row_data, col_widths):
            if cell_color:
                c.setFillColor(colors.HexColor(cell_color))
                c.rect(x_pos + pad, cy + pad,
                       w - 2 * pad, row_h - 2 * pad,
                       fill=True, stroke=False)
                text_color = get_text_color_for_bg(cell_color)
            else:
                text_color = override_text or COLORS["text_white"]

            c.setFillColor(colors.HexColor(text_color))
            c.setFont("Helvetica-Bold", 9.5)
            ty = cy + row_h / 2 - 0.05 * inch
            if align == "center":
                c.drawCentredString(x_pos + w / 2, ty, str(text))
            elif align == "left":
                c.drawString(x_pos + 0.08 * inch, ty, str(text))
            else:
                c.drawRightString(x_pos + w - 0.08 * inch, ty, str(text))
            x_pos += w

    c.save()
    buffer.seek(0)
    return buffer.getvalue()
