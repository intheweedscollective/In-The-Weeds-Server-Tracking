"""
Full Rankings PNG Generator — Snapshot Style.

Output: 1920×1080 PNG (16:9) replicating the user's reference template:
  - Dark navy canvas + left sidebar (logo + Q SERVER PERFORMANCE
    SNAPSHOT title + date + 4-color legend + footer copy).
  - Right table on dark navy bg with each metric cell rendered as a
    colored "tile" (blue/green/yellow/red), separated by thin navy
    gutters that look like cell borders.
  - First three columns (Rank / Name / Trend) sit on the dark navy
    row bg with white text — no fill.
"""
from __future__ import annotations
import io
import os
from datetime import datetime
from typing import Any, Dict, List, Tuple

from PIL import Image, ImageDraw, ImageFont


SLIDE_WIDTH = 1920
SLIDE_HEIGHT = 1080
SIDEBAR_WIDTH = 500

# Colors sampled directly from the user's reference slide.
REF_COLORS = {
    "background": "#0F172A",  # Sidebar / canvas dark navy
    "header_bg":  "#0F172A",  # Header bar — same dark navy
    "row_bg":     "#0F172A",  # Body row bg — dark navy (matches reference)
    "blue":       "#0C769E",  # Exceeding Expectations
    "green":      "#33CC33",  # Meeting Expectations
    "yellow":     "#FFFF00",  # Work in Progress
    "red":        "#FF0000",  # Needs Immediate Improvement
    "text_white": "#FFFFFF",
    "text_dark":  "#000000",
    "trend_up":   "#33CC33",
    "trend_flat": "#9CA3AF",
}

LOGO_PATH = "/app/backend/assets/bubba_gump_logo.png"


# ---------------------------------------------------------------------------
# Color thresholds
# ---------------------------------------------------------------------------
def _ref_cell_color(value: float, metric_type: str) -> str:
    """Match the reference slide's coloring exactly.

    - Percentage cols (PPA/LBW/GLASS/LSC):
        >100 blue · 80-100 green · 60-80 yellow · <60 red
    - CV (NPS%/10 + promoters - 2*detractors): zero/neg = red
    - RT mentions / Bonus: zero = red
    - Score: >=100 blue · 80-100 green · 70-80 yellow · <70 red
    """
    if metric_type == "percentage":
        if value > 100: return REF_COLORS["blue"]
        if value >= 80: return REF_COLORS["green"]
        if value >= 60: return REF_COLORS["yellow"]
        return REF_COLORS["red"]
    if metric_type == "cv":
        if value <= 0:  return REF_COLORS["red"]
        if value > 11:  return REF_COLORS["blue"]
        if value >= 8:  return REF_COLORS["green"]
        return REF_COLORS["yellow"]
    if metric_type == "rt":
        if value <= 0:  return REF_COLORS["red"]
        if value >= 10: return REF_COLORS["blue"]
        if value >= 5:  return REF_COLORS["green"]
        return REF_COLORS["yellow"]
    if metric_type == "bonus":
        if value <= 0:  return REF_COLORS["red"]
        if value >= 5:  return REF_COLORS["blue"]
        if value >= 3:  return REF_COLORS["green"]
        return REF_COLORS["yellow"]
    if metric_type == "score":
        if value >= 100: return REF_COLORS["blue"]
        if value >= 80:  return REF_COLORS["green"]
        if value >= 70:  return REF_COLORS["yellow"]
        return REF_COLORS["red"]
    return REF_COLORS["green"]


def _ref_text_color(bg: str) -> str:
    # Yellow tile gets black text per reference; everything else is white.
    return REF_COLORS["text_dark"] if bg == REF_COLORS["yellow"] else REF_COLORS["text_white"]


# ---------------------------------------------------------------------------
# Font + text helpers
# ---------------------------------------------------------------------------
def _load_font(size: int, bold: bool = True) -> ImageFont.FreeTypeFont:
    name = "DejaVuSans-Bold.ttf" if bold else "DejaVuSans.ttf"
    path = f"/usr/share/fonts/truetype/dejavu/{name}"
    if os.path.exists(path):
        try:
            return ImageFont.truetype(path, size)
        except Exception:
            pass
    return ImageFont.load_default()


def _draw_text(draw, xy, text, font, fill, anchor: str = "lt"):
    draw.text(xy, str(text), font=font, fill=fill, anchor=anchor)


def _signed(val: float) -> str:
    """Render +X.X for positive, -X.X for negative (no '+-' artefacts)."""
    return f"{val:+.1f}"


# ---------------------------------------------------------------------------
# Sidebar
# ---------------------------------------------------------------------------
def _draw_sidebar(img: Image.Image, draw: ImageDraw.ImageDraw, quarter: str) -> None:
    cx = SIDEBAR_WIDTH // 2

    # ---- Logo ----
    logo_y = 165
    logo_w_target = 260
    logo_drawn = False
    if os.path.exists(LOGO_PATH):
        try:
            logo = Image.open(LOGO_PATH).convert("RGBA")
            ratio = logo_w_target / logo.width
            new_h = int(logo.height * ratio)
            logo = logo.resize((logo_w_target, new_h), Image.Resampling.LANCZOS)
            img.paste(logo, (cx - logo_w_target // 2, logo_y - new_h // 2), logo)
            logo_drawn = True
        except Exception:
            logo_drawn = False
    if not logo_drawn:
        r = 110
        draw.ellipse((cx - r, logo_y - r, cx + r, logo_y + r), fill="#1a3050")
        _draw_text(draw, (cx, logo_y - 25), "BUBBA",
                   _load_font(36, True), REF_COLORS["text_white"], anchor="mm")
        _draw_text(draw, (cx, logo_y + 10), "GUMP",
                   _load_font(48, True), REF_COLORS["red"], anchor="mm")
        _draw_text(draw, (cx, logo_y + 50), "SHRIMP CO.",
                   _load_font(20, True), REF_COLORS["text_white"], anchor="mm")

    # ---- Title ----
    title_y = 360
    _draw_text(draw, (cx, title_y), f"{quarter} SERVER",
               _load_font(40, True), REF_COLORS["text_white"], anchor="mm")
    _draw_text(draw, (cx, title_y + 55), "PERFORMANCE",
               _load_font(54, True), REF_COLORS["red"], anchor="mm")
    _draw_text(draw, (cx, title_y + 110), "SNAPSHOT",
               _load_font(40, True), REF_COLORS["text_white"], anchor="mm")
    # Date — formatted "Month DD, YYYY" per reference
    _draw_text(draw, (cx, title_y + 165),
               datetime.now().strftime("%B %d, %Y"),
               _load_font(22, True), REF_COLORS["red"], anchor="mm")

    # ---- Legend ----
    legend_y = title_y + 220
    items = [
        ("EXCEEDING ALL", "EXPECTATIONS", REF_COLORS["blue"]),
        ("MEETING",       "EXPECTATIONS", REF_COLORS["green"]),
        ("WORK IN",       "PROGRESS",     REF_COLORS["yellow"]),
        ("NEEDS IMMEDIATE","IMPROVEMENT", REF_COLORS["red"]),
    ]
    label_font = _load_font(17, True)
    swatch_x = 50
    swatch_w = 35
    swatch_h = 50
    text_x = swatch_x + swatch_w + 14
    for i, (l1, l2, color) in enumerate(items):
        y = legend_y + i * 75
        draw.rectangle((swatch_x, y, swatch_x + swatch_w, y + swatch_h), fill=color)
        _draw_text(draw, (text_x, y + 6),  l1, label_font, color, anchor="lt")
        _draw_text(draw, (text_x, y + 28), l2, label_font, color, anchor="lt")

    # ---- Footer ----
    foot_font = _load_font(18, True)
    footer_y = SLIDE_HEIGHT - 130
    for j, line in enumerate([
        "DON'T WAIT TO IMPACT",
        "THIS NUMBER.",
        "",
        "IF YOU HAVE QUESTIONS",
        "PLEASE SEE MANAGEMENT.",
    ]):
        if line:
            _draw_text(draw, (cx, footer_y + j * 24), line, foot_font,
                       REF_COLORS["text_white"], anchor="mm")


# ---------------------------------------------------------------------------
# Table
# ---------------------------------------------------------------------------
def _draw_table(
    draw: ImageDraw.ImageDraw,
    rankings: List[Dict[str, Any]],
) -> None:
    table_x = SIDEBAR_WIDTH + 30
    table_y = 60
    table_w = SLIDE_WIDTH - table_x - 40

    headers = ["Rank", "Name", "Trend", "PPA", "LBW", "GLASS",
               "LSC", "CV", "RT", "Bonus", "Score"]
    col_props = [0.06, 0.14, 0.06, 0.085, 0.085, 0.085,
                 0.085, 0.085, 0.085, 0.09, 0.09]
    col_widths = [int(p * table_w) for p in col_props]
    col_widths[-1] += table_w - sum(col_widths)

    # ---- Header bar ----
    header_h = 52
    draw.rectangle(
        (table_x, table_y, table_x + table_w, table_y + header_h),
        fill=REF_COLORS["header_bg"]
    )
    header_font = _load_font(20, True)
    x = table_x
    for header, w in zip(headers, col_widths):
        _draw_text(draw, (x + w // 2, table_y + header_h // 2),
                   header, header_font, REF_COLORS["text_white"], anchor="mm")
        x += w

    # ---- Body ----
    body_top = table_y + header_h
    body_bottom = SLIDE_HEIGHT - 30
    avail = body_bottom - body_top
    n = max(1, len(rankings))
    row_h = max(28, min(40, avail // n))

    name_font  = _load_font(max(14, row_h - 16), True)
    cell_font  = _load_font(max(13, row_h - 18), True)
    rank_font  = _load_font(max(15, row_h - 16), True)
    trend_font = _load_font(max(18, row_h - 12), True)

    # The body is dark navy (header_bg). Cell tiles draw on top with a
    # 2-3px gap on every side — that gap IS the visible border per the
    # reference design.
    draw.rectangle(
        (table_x, body_top, table_x + table_w, body_bottom),
        fill=REF_COLORS["row_bg"]
    )

    cy = body_top
    for emp in rankings:
        if cy + row_h > body_bottom:
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

        # Trend symbol — "▲" green if improving, "—" gray if flat.
        trend_dir = (emp.get("trend") or "up").lower()
        if trend_dir in ("up", "improving", "improved"):
            trend_glyph, trend_col = "\u25B2", REF_COLORS["trend_up"]
        elif trend_dir in ("down", "declining"):
            trend_glyph, trend_col = "\u25BC", REF_COLORS["red"]
        else:
            trend_glyph, trend_col = "\u2014", REF_COLORS["trend_flat"]

        cells: List[Tuple[str, str | None, str, ImageFont.FreeTypeFont, str | None]] = [
            (pos_label,                              None,                                      "center", rank_font,  REF_COLORS["text_white"]),
            (name,                                   None,                                      "left",   name_font,  REF_COLORS["text_white"]),
            (trend_glyph,                            None,                                      "center", trend_font, trend_col),
            (f"{ppa_pct:.0f}%",                      _ref_cell_color(ppa_pct,   "percentage"),  "center", cell_font,  None),
            (f"{lbw_pct:.0f}%",                      _ref_cell_color(lbw_pct,   "percentage"),  "center", cell_font,  None),
            (f"{glass_pct:.0f}%",                    _ref_cell_color(glass_pct, "percentage"),  "center", cell_font,  None),
            (f"{lsc_pct:.0f}%",                      _ref_cell_color(lsc_pct,   "percentage"),  "center", cell_font,  None),
            (_signed(cv_score),                      _ref_cell_color(cv_score,  "cv"),          "center", cell_font,  None),
            (_signed(rt_mentions),                   _ref_cell_color(rt_mentions,"rt"),         "center", cell_font,  None),
            (_signed(bonus),                         _ref_cell_color(bonus,     "bonus"),       "center", cell_font,  None),
            (f"{score:.1f}",                         _ref_cell_color(score,     "score"),       "center", cell_font,  None),
        ]

        x = table_x
        for (text, cell_color, align, font, override_text_color), w in zip(cells, col_widths):
            if cell_color:
                # Tile with 3px gap creates the visible "border" on dark navy.
                pad = 3
                draw.rectangle(
                    (x + pad, cy + pad, x + w - pad, cy + row_h - pad),
                    fill=cell_color
                )
                tcolor = _ref_text_color(cell_color)
            else:
                tcolor = override_text_color or REF_COLORS["text_white"]

            ty = cy + row_h // 2
            if align == "center":
                _draw_text(draw, (x + w // 2, ty), text, font, tcolor, anchor="mm")
            elif align == "left":
                _draw_text(draw, (x + 12, ty), text, font, tcolor, anchor="lm")
            else:
                _draw_text(draw, (x + w - 10, ty), text, font, tcolor, anchor="rm")
            x += w

        cy += row_h


def build_full_rankings_png(
    rankings: List[Dict[str, Any]],
    quarter: str,
    year: int,
    thresholds: Dict[str, float] | None = None,
) -> bytes:
    """Render the Server Performance Snapshot as a 1920×1080 PNG (16:9).

    Note: `thresholds` is accepted for API compatibility but the reference
    template drives the score color from absolute thresholds (see
    `_ref_cell_color(value, 'score')`), not the per-quarter A/B tiers.
    """
    img = Image.new("RGB", (SLIDE_WIDTH, SLIDE_HEIGHT), REF_COLORS["background"])
    draw = ImageDraw.Draw(img)

    _draw_sidebar(img, draw, quarter)
    _draw_table(draw, rankings)

    buf = io.BytesIO()
    img.save(buf, format="PNG", optimize=True)
    buf.seek(0)
    return buf.getvalue()
