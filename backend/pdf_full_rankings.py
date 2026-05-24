"""
Full Rankings PDF Generator — Mirrors `png_full_rankings.py`.
"""
import io
import os
from datetime import datetime
from typing import Any, Dict, List

from reportlab.lib import colors
from reportlab.lib.units import inch
from reportlab.pdfgen import canvas
from reportlab.lib.utils import ImageReader


COLORS = {
    "background":  "#0F172A",
    "header_bg":   "#0F172A",
    "blue":        "#0C769E",
    "green":       "#33CC33",
    "yellow":      "#FFFF00",
    "red":         "#FF0000",
    "text_white":  "#FFFFFF",
    "text_dark":   "#000000",
    "name_bg":     "#FFFFFF",
    "grid":        "#FFFFFF",
    "border":      "#000000",
    "trend_up":    "#16A34A",
    "trend_flat":  "#6B7280",
}

LOGO_PATH = "/app/backend/assets/bubba_gump_logo.png"


def _rt_value(mentions: float) -> float:
    return min(0.33 * (mentions or 0), 20.0)


def get_cell_color(value: float, metric_type: str = "percentage") -> str:
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


def _signed(val: float) -> str:
    if val == 0:
        return "0.0"
    return f"{val:+.1f}"


def _draw_tile(c: canvas.Canvas, x: float, y: float, w: float, h: float,
               fill_hex: str, radius: float = 0.04 * inch) -> None:
    c.setFillColor(colors.HexColor(fill_hex))
    c.setStrokeColor(colors.HexColor(COLORS["border"]))
    c.setLineWidth(0.6)
    c.roundRect(x, y, w, h, radius, fill=True, stroke=True)


def build_full_rankings_pdf(
    rankings: List[Dict[str, Any]],
    quarter: str,
    year: int,
    thresholds: Dict[str, float],
) -> bytes:
    buffer = io.BytesIO()
    page_width = 16 * inch
    page_height = 9 * inch
    c = canvas.Canvas(buffer, pagesize=(page_width, page_height))

    # Solid dark navy background
    c.setFillColor(colors.HexColor(COLORS["background"]))
    c.rect(0, 0, page_width, page_height, fill=True, stroke=False)

    # ==================== LEFT SIDEBAR ====================
    sidebar_width = 4.0 * inch
    cx = sidebar_width / 2

    logo_y = page_height - 1.6 * inch
    if os.path.exists(LOGO_PATH):
        try:
            logo = ImageReader(LOGO_PATH)
            iw, ih = logo.getSize()
            target_w = 2.9 * inch
            ratio = target_w / iw
            target_h = ih * ratio
            c.drawImage(logo, cx - target_w / 2, logo_y - target_h / 2,
                        width=target_w, height=target_h, mask='auto')
        except Exception:
            pass

    title_y = logo_y - 1.65 * inch
    c.setFillColor(colors.HexColor(COLORS["text_white"]))
    c.setFont("Helvetica-Bold", 32)
    c.drawCentredString(cx, title_y, f"{quarter} SERVER")

    c.setFillColor(colors.HexColor(COLORS["red"]))
    c.setFont("Helvetica-Bold", 42)
    c.drawCentredString(cx, title_y - 0.55 * inch, "PERFORMANCE")

    c.setFillColor(colors.HexColor(COLORS["text_white"]))
    c.setFont("Helvetica-Bold", 32)
    c.drawCentredString(cx, title_y - 1.1 * inch, "SNAPSHOT")

    c.setFillColor(colors.HexColor(COLORS["red"]))
    c.setFont("Helvetica-Bold", 16)
    c.drawCentredString(cx, title_y - 1.5 * inch,
                        datetime.now().strftime("%B %d, %Y"))

    legend_y = title_y - 2.1 * inch
    legend_items = [
        ("EXCEEDING ALL",   "EXPECTATIONS", COLORS["blue"]),
        ("MEETING",         "EXPECTATIONS", COLORS["green"]),
        ("WORK IN",         "PROGRESS",     COLORS["yellow"]),
        ("NEEDS IMMEDIATE", "IMPROVEMENT",  COLORS["red"]),
    ]
    for i, (line1, line2, color) in enumerate(legend_items):
        y_pos = legend_y - (i * 0.7 * inch)
        c.setFillColor(colors.HexColor(color))
        c.rect(0.45 * inch, y_pos - 0.05 * inch, 0.36 * inch, 0.55 * inch,
               fill=True, stroke=False)
        c.setFillColor(colors.HexColor(color))
        c.setFont("Helvetica-Bold", 17)
        c.drawString(0.95 * inch, y_pos + 0.32 * inch, line1)
        c.drawString(0.95 * inch, y_pos + 0.1 * inch, line2)

    footer_y = 0.85 * inch
    c.setFillColor(colors.HexColor(COLORS["text_white"]))
    c.setFont("Helvetica-Bold", 16)
    c.drawCentredString(cx, footer_y + 0.5 * inch, "DON'T WAIT TO IMPACT")
    c.drawCentredString(cx, footer_y + 0.27 * inch, "THIS NUMBER.")
    c.drawCentredString(cx, footer_y - 0.08 * inch, "IF YOU HAVE QUESTIONS")
    c.drawCentredString(cx, footer_y - 0.31 * inch, "PLEASE SEE MANAGEMENT.")

    # ==================== MAIN TABLE ====================
    table_x = sidebar_width + 0.2 * inch
    table_width = page_width - sidebar_width - 0.4 * inch
    table_top = page_height - 0.3 * inch

    headers = ["Rank", "Name", "Trend", "PPA", "LBW", "GLASS",
               "LSC", "CV", "RT", "Metric Bonus", "Score"]
    col_props = [0.06, 0.13, 0.06, 0.085, 0.085, 0.085,
                 0.085, 0.085, 0.085, 0.105, 0.085]
    col_widths = [p * table_width for p in col_props]
    col_widths[-1] += table_width - sum(col_widths)

    header_h = 0.36 * inch
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

    body_top = table_top - header_h
    body_bottom = 0.3 * inch
    avail = body_top - body_bottom
    n = max(1, len(rankings))
    row_h = max(0.22 * inch, min(0.36 * inch, avail / n))

    pad = 0.025 * inch
    radius = 0.04 * inch

    cy = body_top
    for emp in rankings:
        cy -= row_h
        if cy < body_bottom:
            break

        pos_label   = emp.get("position_label", "")
        name        = (emp.get("name", "") or "")[:14]
        score       = emp.get("total_score", 0) or 0
        ppa_pct     = emp.get("ppa_percentage") or (
            ((emp.get("ppa_points", {}).get("earned", 0) or 0) / 30) * 100)
        lbw_pct     = emp.get("lbw_percentage") or (
            ((emp.get("lbw_points", {}).get("earned", 0) or 0) / 25) * 100)
        glass_pct   = emp.get("glassware_percentage") or (
            ((emp.get("glassware_points", {}).get("earned", 0) or 0) / 20) * 100)
        lsc_pct     = emp.get("lsc_percentage") or (
            ((emp.get("lsc_points", {}).get("earned", 0) or 0) / 30) * 100)
        cv_score    = emp.get("cv_score", 0) or 0
        mentions    = emp.get("review_mentions", 0) or emp.get("rt_mentions", 0) or 0
        rt_value    = _rt_value(mentions)
        metric_bonus = emp.get("metric_bonus", 0) or 0

        trend_dir = (emp.get("trend") or "up").lower()
        if trend_dir in ("up", "improving", "improved"):
            trend_shape, trend_col = "up", COLORS["trend_up"]
        elif trend_dir in ("down", "declining"):
            trend_shape, trend_col = "down", COLORS["red"]
        else:
            trend_shape, trend_col = "flat", COLORS["trend_flat"]

        # NOTE: trend cell renders as a polygon, not text — Helvetica
        # doesn't ship U+25B2/U+25BC/U+2014, so glyphs came out as
        # tofu boxes on screenshots. See `png_full_rankings.py` for
        # the matching fix on the PNG export path.

        row_data = [
            (pos_label,            None,                                      "center", COLORS["text_dark"], True),
            (name,                 None,                                      "left",   COLORS["text_dark"], True),
            (f"__TREND__:{trend_shape}", None,                                  "center", trend_col,           True),
            (f"{ppa_pct:.0f}%",    get_cell_color(ppa_pct,    "percentage"),  "center", None,                False),
            (f"{lbw_pct:.0f}%",    get_cell_color(lbw_pct,    "percentage"),  "center", None,                False),
            (f"{glass_pct:.0f}%",  get_cell_color(glass_pct,  "percentage"),  "center", None,                False),
            (f"{lsc_pct:.0f}%",    get_cell_color(lsc_pct,    "percentage"),  "center", None,                False),
            (_signed(cv_score),    get_cell_color(cv_score,   "cv"),          "center", None,                False),
            (_signed(rt_value),    get_cell_color(rt_value,   "rt"),          "center", None,                False),
            (_signed(metric_bonus),get_cell_color(metric_bonus,"bonus"),      "center", None,                False),
            (f"{score:.1f}",       get_cell_color(score,      "score"),       "center", None,                False),
        ]

        x_pos = table_x
        for (text, fill_hex, align, override_text, is_white), w in zip(row_data, col_widths):
            # White gutter block behind every cell.
            c.setFillColor(colors.HexColor(COLORS["grid"]))
            c.rect(x_pos, cy, w, row_h, fill=True, stroke=False)

            tile_x = x_pos + pad
            tile_y = cy + pad
            tile_w = w - 2 * pad
            tile_h = row_h - 2 * pad

            if is_white:
                _draw_tile(c, tile_x, tile_y, tile_w, tile_h,
                           COLORS["name_bg"], radius)
                text_color = override_text or COLORS["text_dark"]
            else:
                _draw_tile(c, tile_x, tile_y, tile_w, tile_h, fill_hex, radius)
                text_color = COLORS["text_dark"]  # All grid numbers BLACK per spec.

            c.setFillColor(colors.HexColor(text_color))
            c.setFont("Helvetica-Bold", 9.5)
            ty = cy + row_h / 2 - 0.05 * inch
            if isinstance(text, str) and text.startswith("__TREND__:"):
                # Polygon-drawn trend indicator: doesn't depend on font
                # glyph availability. Same approach as PNG generator.
                shape = text.split(":", 1)[1]
                cx = x_pos + w / 2
                cy_mid = cy + row_h / 2
                size = min(row_h, 0.18 * inch)
                half = size / 2
                c.setFillColor(colors.HexColor(override_text or COLORS["trend_up"]))
                if shape == "up":
                    p = c.beginPath()
                    p.moveTo(cx, cy_mid + half)
                    p.lineTo(cx - half, cy_mid - half)
                    p.lineTo(cx + half, cy_mid - half)
                    p.close()
                    c.drawPath(p, stroke=0, fill=1)
                elif shape == "down":
                    p = c.beginPath()
                    p.moveTo(cx, cy_mid - half)
                    p.lineTo(cx - half, cy_mid + half)
                    p.lineTo(cx + half, cy_mid + half)
                    p.close()
                    c.drawPath(p, stroke=0, fill=1)
                else:  # flat
                    bar_h = max(1.5, size / 5)
                    c.rect(cx - half, cy_mid - bar_h / 2, size, bar_h, fill=1, stroke=0)
            elif align == "center":
                c.drawCentredString(x_pos + w / 2, ty, str(text))
            elif align == "left":
                c.drawString(x_pos + 0.08 * inch, ty, str(text))
            else:
                c.drawRightString(x_pos + w - 0.08 * inch, ty, str(text))
            x_pos += w

    c.save()
    buffer.seek(0)
    return buffer.getvalue()
