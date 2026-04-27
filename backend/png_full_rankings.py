"""
Full Rankings PNG Generator — Snapshot Style (replica of the reference
slide).

Output: 1920×1920 PNG with:
  - Dark navy bg + wide left sidebar (logo + Q SERVER PERFORMANCE
    SNAPSHOT title + date + 4-color legend + footer)
  - Right-side data table with white/light-gray alternating rows, dark
    navy header bar, and FULLY-FILLED color-coded cells (blue/green/
    yellow/red) per the legend.
  - Score column colored by tier threshold (A=green, B=yellow, C=red).
"""
from __future__ import annotations
import io
import os
from datetime import datetime
from typing import Any, Dict, List, Tuple

from PIL import Image, ImageDraw, ImageFont


def _ref_cell_color(value: float, metric_type: str, has_detractors: bool = False) -> str:
    """Color thresholds per the user's spec:
       - >100% benchmark = blue (exceeding)
       - 80-100% = green (meeting)
       - 60-80% = yellow (work in progress)
       - <60% = red (needs immediate improvement)

    For CV/RT/Bonus columns: red is reserved for ZERO or NEGATIVE net
    score. Any positive net feedback (even if some detractors offset it)
    is at least yellow — the score itself reflects the offset, the color
    just signals "they got positive feedback overall"."""
    if metric_type == "percentage":
        if value > 100: return REF_COLORS["blue"]
        if value >= 80: return REF_COLORS["green"]
        if value >= 60: return REF_COLORS["yellow"]
        return REF_COLORS["red"]
    if metric_type == "cv":
        # Net combined score: NPS%/10 + promoters - 2*detractors
        if value <= 0:    return REF_COLORS["red"]   # no positive feedback or net negative
        if value > 11:    return REF_COLORS["blue"]   # exceeding benchmark
        if value >= 8:    return REF_COLORS["green"]  # ~75%+ of bench
        return REF_COLORS["yellow"]                    # any positive feedback
    if metric_type == "rt":
        if value <= 0:    return REF_COLORS["red"]
        if value >= 10:   return REF_COLORS["blue"]
        if value >= 5:    return REF_COLORS["green"]
        return REF_COLORS["yellow"]
    if metric_type == "bonus":
        if value <= 0:    return REF_COLORS["red"]
        if value >= 5:    return REF_COLORS["blue"]
        if value >= 3:    return REF_COLORS["green"]
        return REF_COLORS["yellow"]
    return REF_COLORS["green"]


def _ref_text_color(bg: str) -> str:
    # Yellow gets black text per reference
    return "#000000" if bg == REF_COLORS["yellow"] else REF_COLORS["text_white"]


SLIDE_WIDTH = 1920
SLIDE_HEIGHT = 1080
SIDEBAR_WIDTH = 500

# Colors sampled directly from the user's reference slide.
REF_COLORS = {
    "background": "#0F172A",  # Sidebar/canvas dark navy
    "header_bg": "#0F172A",   # Header bar — same dark navy as sidebar
    "blue":   "#0C769E",      # Exceeding Expectations
    "green":  "#33CC33",      # Meeting Expectations
    "yellow": "#FFFF00",      # Work in Progress
    "red":    "#FF0000",      # Needs Immediate Improvement
    "text_white": "#FFFFFF",
    "text_red":   "#FF0000",
}

# Row backgrounds — light, NOT navy. Match the reference style.
ROW_LIGHT = "#FFFFFF"
ROW_DARK = "#F0F2F5"
TEXT_DARK = "#0F172A"

LOGO_PATH = "/app/backend/assets/bubba_gump_logo.png"


def _load_font(size: int, bold: bool = True) -> ImageFont.FreeTypeFont:
    candidates = (
        ["DejaVuSans-Bold.ttf"] if bold else ["DejaVuSans.ttf"]
    )
    for name in candidates:
        path = f"/usr/share/fonts/truetype/dejavu/{name}"
        if os.path.exists(path):
            try:
                return ImageFont.truetype(path, size)
            except Exception:
                pass
    # Fallback
    for path in (
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    ):
        if os.path.exists(path):
            try:
                return ImageFont.truetype(path, size)
            except Exception:
                pass
    return ImageFont.load_default()


def _draw_text(draw, xy, text, font, fill, anchor: str = "lt"):
    draw.text(xy, str(text), font=font, fill=fill, anchor=anchor)


def _score_color(score: float, a_min: float, b_min: float) -> str:
    if score >= a_min:
        return REF_COLORS["green"]
    if score >= b_min:
        return REF_COLORS["yellow"]
    return REF_COLORS["red"]


def _draw_sidebar(img: Image.Image, draw: ImageDraw.ImageDraw, quarter: str) -> None:
    cx = SIDEBAR_WIDTH // 2

    # ---- Logo (large, top of sidebar) ----
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

    # ---- Title (Q1 SERVER / PERFORMANCE / SNAPSHOT / date) ----
    title_y = 360
    _draw_text(draw, (cx, title_y), f"{quarter} SERVER",
               _load_font(40, True), REF_COLORS["text_white"], anchor="mm")
    _draw_text(draw, (cx, title_y + 55), "PERFORMANCE",
               _load_font(54, True), REF_COLORS["red"], anchor="mm")
    _draw_text(draw, (cx, title_y + 110), "SNAPSHOT",
               _load_font(40, True), REF_COLORS["text_white"], anchor="mm")
    _draw_text(draw, (cx, title_y + 165), datetime.now().strftime("%Y-%m-%d"),
               _load_font(22, True), REF_COLORS["red"], anchor="mm")

    # ---- Legend ----
    legend_y = title_y + 220
    items = [
        ("EXCEEDING ALL", "EXPECTATIONS", REF_COLORS["blue"]),
        ("MEETING", "EXPECTATIONS", REF_COLORS["green"]),
        ("WORK IN", "PROGRESS", REF_COLORS["yellow"]),
        ("NEEDS IMMEDIATE", "IMPROVEMENT", REF_COLORS["red"]),
    ]
    label_font = _load_font(17, True)
    swatch_x = 50
    swatch_w = 35
    swatch_h = 50
    text_x = swatch_x + swatch_w + 14
    for i, (l1, l2, color) in enumerate(items):
        y = legend_y + i * 75
        draw.rectangle((swatch_x, y, swatch_x + swatch_w, y + swatch_h), fill=color)
        # Match reference: titles colored to match swatch
        title_color = color
        _draw_text(draw, (text_x, y + 6), l1, label_font, title_color, anchor="lt")
        _draw_text(draw, (text_x, y + 28), l2, label_font, title_color, anchor="lt")

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


def _draw_table(
    draw: ImageDraw.ImageDraw,
    rankings: List[Dict[str, Any]],
    a_min: float,
    b_min: float,
) -> None:
    # ---- Geometry ----
    table_x = SIDEBAR_WIDTH + 30
    table_y = 60
    table_w = SLIDE_WIDTH - table_x - 40

    headers = ["Rank", "Name", "Trend", "PPA", "LBW", "GLASS",
               "LSC", "CV", "RT", "Bonus", "Score"]
    # Proportional column widths summing to 1.0 — Name col wider for legibility
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

    name_font = _load_font(max(14, row_h - 16), True)
    cell_font = _load_font(max(13, row_h - 18), True)
    rank_font = _load_font(max(15, row_h - 16), True)

    cy = body_top
    for idx, emp in enumerate(rankings):
        if cy + row_h > body_bottom:
            break

        # Alt row background — LIGHT (not navy). Matches reference.
        bg = ROW_LIGHT if idx % 2 == 0 else ROW_DARK
        draw.rectangle(
            (table_x, cy, table_x + table_w, cy + row_h),
            fill=bg
        )

        pos_label = emp.get("position_label", "")
        name = (emp.get("name", "") or "")[:14]
        score = emp.get("total_score", 0) or 0

        # Same percentage math as the PDF generator
        ppa_pct = ((emp.get("ppa_points", {}).get("earned", 0) or 0) / 30) * 100
        lbw_pct = ((emp.get("lbw_points", {}).get("earned", 0) or 0) / 25) * 100
        glass_pct = ((emp.get("glassware_points", {}).get("earned", 0) or 0) / 20) * 100
        lsc_pct = ((emp.get("lsc_points", {}).get("earned", 0) or 0) / 30) * 100
        cv_score = emp.get("cv_score", 0) or 0
        rt_mentions = emp.get("review_mentions", 0) or emp.get("rt_mentions", 0) or 0
        bonus = emp.get("bonus_points", 0) or emp.get("metric_bonus", 0) or 0
        cv_detractors = emp.get("cv_detractors", 0) or 0

        score_color = _score_color(score, a_min, b_min)

        cells: List[Tuple[str, str | None, str, ImageFont.FreeTypeFont]] = [
            (pos_label, None, "center", rank_font),
            (name, None, "left", name_font),
            ("=", None, "center", cell_font),
            (f"{ppa_pct:.0f}%", _ref_cell_color(ppa_pct, "percentage"), "center", cell_font),
            (f"{lbw_pct:.0f}%", _ref_cell_color(lbw_pct, "percentage"), "center", cell_font),
            (f"{glass_pct:.0f}%", _ref_cell_color(glass_pct, "percentage"), "center", cell_font),
            (f"{lsc_pct:.0f}%", _ref_cell_color(lsc_pct, "percentage"), "center", cell_font),
            (f"+{cv_score:.1f}", _ref_cell_color(cv_score, "cv", cv_detractors > 0), "center", cell_font),
            (f"+{rt_mentions:.1f}", _ref_cell_color(rt_mentions, "rt"), "center", cell_font),
            (f"+{bonus:.1f}", _ref_cell_color(bonus, "bonus"), "center", cell_font),
            (f"{score:.1f}", score_color, "center", cell_font),
        ]

        x = table_x
        for (text, cell_color, align, font), w in zip(cells, col_widths):
            if cell_color:
                # 2px gap on all sides — matches reference's slight bezel
                pad = 2
                draw.rectangle(
                    (x + pad, cy + pad, x + w - pad, cy + row_h - pad),
                    fill=cell_color
                )
                tcolor = _ref_text_color(cell_color)
            else:
                # Black text on the light row bg for first 3 columns
                tcolor = TEXT_DARK
            ty = cy + row_h // 2
            if align == "center":
                _draw_text(draw, (x + w // 2, ty), text, font, tcolor, anchor="mm")
            elif align == "left":
                _draw_text(draw, (x + 10, ty), text, font, tcolor, anchor="lm")
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
    """Render the Server Performance Snapshot as a 1920×1080 PNG (16:9)."""
    a_min = (thresholds or {}).get("a_min", 85)
    b_min = (thresholds or {}).get("b_min", 70)

    img = Image.new("RGB", (SLIDE_WIDTH, SLIDE_HEIGHT), REF_COLORS["background"])
    draw = ImageDraw.Draw(img)

    _draw_sidebar(img, draw, quarter)
    _draw_table(draw, rankings, a_min, b_min)

    buf = io.BytesIO()
    img.save(buf, format="PNG", optimize=True)
    buf.seek(0)
    return buf.getvalue()
