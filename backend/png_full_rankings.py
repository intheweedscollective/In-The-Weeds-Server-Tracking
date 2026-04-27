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

from pdf_full_rankings import COLORS, get_cell_color, get_text_color_for_bg

SLIDE_WIDTH = 1920
SLIDE_HEIGHT = 1920
SIDEBAR_WIDTH = 460

# Row backgrounds — light, NOT navy. Match the reference style.
ROW_LIGHT = "#FFFFFF"
ROW_DARK = "#EAEEF3"
TEXT_DARK = "#0D1E31"

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
        return COLORS["green"]
    if score >= b_min:
        return COLORS["yellow"]
    return COLORS["red"]


def _draw_sidebar(img: Image.Image, draw: ImageDraw.ImageDraw, quarter: str) -> None:
    cx = SIDEBAR_WIDTH // 2

    # ---- Logo (much larger now, matching reference) ----
    logo_y = 280
    logo_w_target = 320
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
        # Stylized circle fallback
        r = 150
        draw.ellipse((cx - r, logo_y - r, cx + r, logo_y + r), fill="#1a3050")
        _draw_text(draw, (cx, logo_y - 35), "BUBBA",
                   _load_font(50, True), COLORS["text_white"], anchor="mm")
        _draw_text(draw, (cx, logo_y + 15), "GUMP",
                   _load_font(64, True), COLORS["red"], anchor="mm")
        _draw_text(draw, (cx, logo_y + 70), "SHRIMP CO.",
                   _load_font(28, True), COLORS["text_white"], anchor="mm")

    # ---- Title (Q1 SERVER / PERFORMANCE / SNAPSHOT / date) ----
    title_y = 540
    _draw_text(draw, (cx, title_y), f"{quarter} SERVER",
               _load_font(54, True), COLORS["text_white"], anchor="mm")
    _draw_text(draw, (cx, title_y + 80), "PERFORMANCE",
               _load_font(72, True), COLORS["red"], anchor="mm")
    _draw_text(draw, (cx, title_y + 160), "SNAPSHOT",
               _load_font(54, True), COLORS["text_white"], anchor="mm")
    _draw_text(draw, (cx, title_y + 235), datetime.now().strftime("%Y-%m-%d"),
               _load_font(30, True), COLORS["red"], anchor="mm")

    # ---- Legend ----
    legend_y = title_y + 340
    items = [
        ("EXCEEDING ALL", "EXPECTATIONS", COLORS["blue"]),
        ("MEETING", "EXPECTATIONS", COLORS["green"]),
        ("WORK IN", "PROGRESS", COLORS["yellow"]),
        ("NEEDS IMMEDIATE", "IMPROVEMENT", COLORS["red"]),
    ]
    label_font = _load_font(22, True)
    swatch_x = 50
    swatch_w = 50
    swatch_h = 64
    text_x = swatch_x + swatch_w + 18
    for i, (l1, l2, color) in enumerate(items):
        y = legend_y + i * 110
        draw.rectangle((swatch_x, y, swatch_x + swatch_w, y + swatch_h), fill=color)
        # Match reference: titles colored to match swatch
        title_color = color if color != COLORS["yellow"] else "#F2D900"
        _draw_text(draw, (text_x, y + 6), l1, label_font, title_color, anchor="lt")
        _draw_text(draw, (text_x, y + 36), l2, label_font, title_color, anchor="lt")

    # ---- Footer ----
    foot_font = _load_font(22, True)
    footer_y = SLIDE_HEIGHT - 200
    for j, line in enumerate([
        "DON'T WAIT TO IMPACT",
        "THIS NUMBER.",
        "",
        "IF YOU HAVE QUESTIONS",
        "PLEASE SEE MANAGEMENT.",
    ]):
        if line:
            _draw_text(draw, (cx, footer_y + j * 32), line, foot_font,
                       COLORS["text_white"], anchor="mm")


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
    header_h = 70
    draw.rectangle(
        (table_x, table_y, table_x + table_w, table_y + header_h),
        fill=COLORS["header_bg"]
    )
    header_font = _load_font(26, True)
    x = table_x
    for header, w in zip(headers, col_widths):
        _draw_text(draw, (x + w // 2, table_y + header_h // 2),
                   header, header_font, COLORS["text_white"], anchor="mm")
        x += w

    # ---- Body ----
    body_top = table_y + header_h
    body_bottom = SLIDE_HEIGHT - 60
    avail = body_bottom - body_top
    n = max(1, len(rankings))
    row_h = max(46, min(72, avail // n))

    name_font = _load_font(max(20, row_h - 28), True)
    cell_font = _load_font(max(20, row_h - 30), True)
    rank_font = _load_font(max(22, row_h - 28), True)

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

        score_color = _score_color(score, a_min, b_min)

        cells: List[Tuple[str, str | None, str, ImageFont.FreeTypeFont]] = [
            (pos_label, None, "center", rank_font),
            (name, None, "left", name_font),
            ("=", None, "center", cell_font),
            (f"{ppa_pct:.0f}%", get_cell_color(ppa_pct, "percentage"), "center", cell_font),
            (f"{lbw_pct:.0f}%", get_cell_color(lbw_pct, "percentage"), "center", cell_font),
            (f"{glass_pct:.0f}%", get_cell_color(glass_pct, "percentage"), "center", cell_font),
            (f"{lsc_pct:.0f}%", get_cell_color(lsc_pct, "percentage"), "center", cell_font),
            (f"+{cv_score:.1f}", get_cell_color(cv_score, "cv"), "center", cell_font),
            (f"+{rt_mentions:.1f}", get_cell_color(rt_mentions, "rt"), "center", cell_font),
            (f"+{bonus:.1f}", get_cell_color(bonus, "bonus"), "center", cell_font),
            (f"{score:.1f}", score_color, "center", cell_font),
        ]

        x = table_x
        for (text, cell_color, align, font), w in zip(cells, col_widths):
            if cell_color:
                pad = 3
                draw.rectangle(
                    (x + pad, cy + pad, x + w - pad, cy + row_h - pad),
                    fill=cell_color
                )
                tcolor = get_text_color_for_bg(cell_color)
            else:
                # Black text on the light row bg for first 3 columns
                tcolor = TEXT_DARK
            ty = cy + row_h // 2
            if align == "center":
                _draw_text(draw, (x + w // 2, ty), text, font, tcolor, anchor="mm")
            elif align == "left":
                _draw_text(draw, (x + 12, ty), text, font, tcolor, anchor="lm")
            else:
                _draw_text(draw, (x + w - 12, ty), text, font, tcolor, anchor="rm")
            x += w

        cy += row_h


def build_full_rankings_png(
    rankings: List[Dict[str, Any]],
    quarter: str,
    year: int,
    thresholds: Dict[str, float] | None = None,
) -> bytes:
    """Render the Server Performance Snapshot as a 1920×1920 PNG."""
    a_min = (thresholds or {}).get("a_min", 85)
    b_min = (thresholds or {}).get("b_min", 70)

    img = Image.new("RGB", (SLIDE_WIDTH, SLIDE_HEIGHT), COLORS["background"])
    draw = ImageDraw.Draw(img)

    _draw_sidebar(img, draw, quarter)
    _draw_table(draw, rankings, a_min, b_min)

    buf = io.BytesIO()
    img.save(buf, format="PNG", optimize=True)
    buf.seek(0)
    return buf.getvalue()
