"""
Full Rankings PNG Generator — Pixel-accurate clone of the user's reference
"Q1 Server Performance Snapshot" slide.

Output: 1920×1080 (16:9) PNG with:
  - Solid dark-navy canvas + left brand panel.
  - Right table (header dark navy, body dark navy) with Rank/Name/Trend
    cells filled WHITE and metric cells filled with category colors.
  - All grid numbers rendered in BLACK text per spec.
"""
from __future__ import annotations
import io
import os
from datetime import datetime
from typing import Any, Dict, List, Tuple

from PIL import Image, ImageDraw, ImageFont


SLIDE_WIDTH = 1920
SLIDE_HEIGHT = 1080
SIDEBAR_WIDTH = 660

REF_COLORS = {
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


# RT formula: 0.5 pts per name mention, capped at 15.
def _rt_value(mentions: float) -> float:
    return min(0.3 * (mentions or 0), 20.0)


# ---------------------------------------------------------------------------
# Color thresholds
# ---------------------------------------------------------------------------
def _ref_cell_color(value: float, metric_type: str) -> str:
    """Reference-template thresholds.

    - Percentage cols: >100 blue · 80-100 green · 60-80 yellow · <60 red
    - CV: zero/neg = red · >11 blue · ≥8 green · else yellow
    - RT (already capped 0-15): 0/neg red · ≥10 blue · ≥5 green · else yellow
    - Metric Bonus: 0/neg red · ≥5 blue · ≥3 green · else yellow
    - Score: ≥100 blue · 80-100 green · 70-80 yellow · <70 red
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


# ---------------------------------------------------------------------------
# Font + text helpers
# ---------------------------------------------------------------------------
def _load_font(size: int, bold: bool = True) -> ImageFont.FreeTypeFont:
    # Try multiple paths in order — first one that exists wins.
    candidates_bold = [
        "/root/.venv/lib/python3.11/site-packages/matplotlib/mpl-data/fonts/ttf/DejaVuSans-Bold.ttf",
        "/app/backend/assets/fonts/Poppins-SemiBold.ttf",
        "/app/backend/assets/fonts/Aptos-Narrow-Bold.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    ]
    candidates_regular = [
        "/root/.venv/lib/python3.11/site-packages/matplotlib/mpl-data/fonts/ttf/DejaVuSans.ttf",
        "/app/backend/assets/fonts/Poppins-Regular.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    ]
    for path in (candidates_bold if bold else candidates_regular):
        if os.path.exists(path):
            try:
                return ImageFont.truetype(path, size)
            except Exception:
                continue
    return ImageFont.load_default()


def _draw_text(draw, xy, text, font, fill, anchor: str = "lt"):
    draw.text(xy, str(text), font=font, fill=fill, anchor=anchor)


def _signed(val: float) -> str:
    if val == 0:
        return "0.0"
    return f"{val:+.1f}"


# ---------------------------------------------------------------------------
# Sidebar
# ---------------------------------------------------------------------------
def _draw_sidebar(img: Image.Image, draw: ImageDraw.ImageDraw, quarter: str) -> None:
    cx = SIDEBAR_WIDTH // 2

    # ---- Logo ----
    # Pushed up to create a comfortable gap between the bottom of the
    # logo and the first title line. Without this, large logos overlap
    # the "Q2 SERVER" heading.
    logo_y = 135
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
        r = 130
        draw.ellipse((cx - r, logo_y - r, cx + r, logo_y + r), fill="#1a3050")
        _draw_text(draw, (cx, logo_y), "BUBBA GUMP",
                   _load_font(48, True), REF_COLORS["text_white"], anchor="mm")

    # ---- Title (LARGE — fills sidebar like the reference) ----
    title_y = 335
    _draw_text(draw, (cx, title_y), f"{quarter} SERVER",
               _load_font(58, True), REF_COLORS["text_white"], anchor="mm")
    _draw_text(draw, (cx, title_y + 72), "PERFORMANCE",
               _load_font(64, True), REF_COLORS["red"], anchor="mm")
    _draw_text(draw, (cx, title_y + 144), "SNAPSHOT",
               _load_font(58, True), REF_COLORS["text_white"], anchor="mm")
    _draw_text(draw, (cx, title_y + 206),
               datetime.now().strftime("%B %d, %Y"),
               _load_font(30, True), REF_COLORS["red"], anchor="mm")

    # ---- Legend (centered as a block within the sidebar) ----
    legend_y = title_y + 280
    items = [
        ("EXCEEDING ALL",   "EXPECTATIONS", REF_COLORS["blue"]),
        ("MEETING",         "EXPECTATIONS", REF_COLORS["green"]),
        ("WORK IN",         "PROGRESS",     REF_COLORS["yellow"]),
        ("NEEDS IMMEDIATE", "IMPROVEMENT",  REF_COLORS["red"]),
    ]
    label_font = _load_font(24, True)
    swatch_w = 46
    swatch_h = 60
    gap = 18
    max_text_w = 0
    for l1, l2, _ in items:
        for line in (l1, l2):
            tw = draw.textlength(line, font=label_font)
            if tw > max_text_w:
                max_text_w = int(tw)
    block_w = swatch_w + gap + max_text_w
    swatch_x = cx - block_w // 2
    text_x = swatch_x + swatch_w + gap
    row_pitch = 70
    for i, (l1, l2, color) in enumerate(items):
        y = legend_y + i * row_pitch
        draw.rectangle((swatch_x, y, swatch_x + swatch_w, y + swatch_h), fill=color)
        _draw_text(draw, (text_x, y + 8),  l1, label_font, color, anchor="lt")
        _draw_text(draw, (text_x, y + 34), l2, label_font, color, anchor="lt")

    # ---- Footer ----
    # Two single-line messages, auto-shrunk to fit the sidebar width so
    # they never wrap. Sidebar width minus a 32px lateral margin.
    sidebar_max_w = SIDEBAR_WIDTH - 32
    footer_lines = [
        "DON'T WAIT TO IMPACT THIS NUMBER.",
        "",
        "IF YOU HAVE QUESTIONS, PLEASE SEE MANAGEMENT.",
    ]

    def _fit_font(text: str, start_size: int, min_size: int) -> ImageFont.ImageFont:
        """Return the largest bold font ≤ start_size whose text fits."""
        for sz in range(start_size, min_size - 1, -1):
            f = _load_font(sz, True)
            if draw.textlength(text, font=f) <= sidebar_max_w:
                return f
        return _load_font(min_size, True)

    # Pick a single font size that fits the LONGER of the two real
    # lines so both render at identical scale.
    target_size = 26
    fitted_font = None
    for sz in range(target_size, 15, -1):
        f = _load_font(sz, True)
        ok = all(draw.textlength(line, font=f) <= sidebar_max_w
                 for line in footer_lines if line)
        if ok:
            fitted_font = f
            break
    if fitted_font is None:
        fitted_font = _load_font(16, True)

    line_pitch = 36
    footer_h = len(footer_lines) * line_pitch
    footer_y = SLIDE_HEIGHT - footer_h - 40
    for j, line in enumerate(footer_lines):
        if line:
            _draw_text(draw, (cx, footer_y + j * line_pitch), line, fitted_font,
                       REF_COLORS["text_white"], anchor="mm")


# ---------------------------------------------------------------------------
# Table
# ---------------------------------------------------------------------------
def _draw_tile(draw: ImageDraw.ImageDraw, box: Tuple[int, int, int, int],
               fill: str, radius: int = 4) -> None:
    """Rounded-corner colored tile with thin black border for definition."""
    draw.rounded_rectangle(box, radius=radius, fill=fill,
                           outline=REF_COLORS["border"], width=1)


def _draw_table(
    draw: ImageDraw.ImageDraw,
    rankings: List[Dict[str, Any]],
) -> None:
    table_x = SIDEBAR_WIDTH + 30
    table_y = 60
    table_w = SLIDE_WIDTH - table_x - 40

    headers = ["Rank", "Name", "Trend", "PPA", "LBW", "GLASS",
               "LSC", "CV", "RT", "Metric Bonus", "Score"]
    col_props = [0.06, 0.13, 0.06, 0.085, 0.085, 0.085,
                 0.085, 0.085, 0.085, 0.105, 0.085]
    col_widths = [int(p * table_w) for p in col_props]
    col_widths[-1] += table_w - sum(col_widths)

    # ---- Header bar ----
    header_h = 50
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

    cy = body_top
    for emp in rankings:
        if cy + row_h > body_bottom:
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
        # RT formula: 0.5 pts per name mention, capped at 15.
        mentions    = emp.get("review_mentions", 0) or emp.get("rt_mentions", 0) or 0
        rt_value    = _rt_value(mentions)
        # Metric Bonus = bonus generated only by exceeding POS-metric benchmarks.
        metric_bonus = emp.get("metric_bonus", 0) or 0

        trend_dir = (emp.get("trend") or "up").lower()
        if trend_dir in ("up", "improving", "improved"):
            trend_glyph, trend_col = "\u25B2", REF_COLORS["trend_up"]
        elif trend_dir in ("down", "declining"):
            trend_glyph, trend_col = "\u25BC", REF_COLORS["red"]
        else:
            trend_glyph, trend_col = "\u2014", REF_COLORS["trend_flat"]

        # (text, fill_color or None for white-bg, align, font, override_text, is_white_bg)
        cells: List[Tuple[str, str | None, str, ImageFont.FreeTypeFont, str | None, bool]] = [
            (pos_label,            None,                                       "center", rank_font,  REF_COLORS["text_dark"], True),
            (name,                 None,                                       "left",   name_font,  REF_COLORS["text_dark"], True),
            (trend_glyph,          None,                                       "center", trend_font, trend_col,                True),
            (f"{ppa_pct:.0f}%",    _ref_cell_color(ppa_pct,    "percentage"),  "center", cell_font,  None,                     False),
            (f"{lbw_pct:.0f}%",    _ref_cell_color(lbw_pct,    "percentage"),  "center", cell_font,  None,                     False),
            (f"{glass_pct:.0f}%",  _ref_cell_color(glass_pct,  "percentage"),  "center", cell_font,  None,                     False),
            (f"{lsc_pct:.0f}%",    _ref_cell_color(lsc_pct,    "percentage"),  "center", cell_font,  None,                     False),
            (_signed(cv_score),    _ref_cell_color(cv_score,   "cv"),          "center", cell_font,  None,                     False),
            (_signed(rt_value),    _ref_cell_color(rt_value,   "rt"),          "center", cell_font,  None,                     False),
            (_signed(metric_bonus),_ref_cell_color(metric_bonus,"bonus"),      "center", cell_font,  None,                     False),
            (f"{score:.1f}",       _ref_cell_color(score,      "score"),       "center", cell_font,  None,                     False),
        ]

        gutter_pad = 2

        x = table_x
        for (text, fill_color, align, font, override_text, is_white_bg), w in zip(cells, col_widths):
            # White grid block behind every cell
            draw.rectangle((x, cy, x + w, cy + row_h),
                           fill=REF_COLORS["grid"])

            box = (x + gutter_pad, cy + gutter_pad,
                   x + w - gutter_pad, cy + row_h - gutter_pad)

            if is_white_bg:
                _draw_tile(draw, box, REF_COLORS["name_bg"], radius=4)
                tcolor = override_text or REF_COLORS["text_dark"]
            else:
                _draw_tile(draw, box, fill_color, radius=4)
                # Per spec: ALL numbers in the grid render in BLACK text.
                tcolor = REF_COLORS["text_dark"]

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
    """Render the Server Performance Snapshot as a 1920×1080 PNG (16:9)."""
    img = Image.new("RGB", (SLIDE_WIDTH, SLIDE_HEIGHT), REF_COLORS["background"])
    draw = ImageDraw.Draw(img)

    _draw_sidebar(img, draw, quarter)
    _draw_table(draw, rankings)

    buf = io.BytesIO()
    img.save(buf, format="PNG", optimize=True)
    buf.seek(0)
    return buf.getvalue()
