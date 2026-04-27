"""
Full Rankings PNG Generator — Snapshot Style.

Output: 1920×1080 PNG (16:9) replicating the user's reference template:
  - Diamond-pattern background image fills the entire slide.
  - Left sidebar: logo + Q SERVER PERFORMANCE SNAPSHOT title + date +
    4-color legend + footer copy (drawn directly on the bg image).
  - Right table:
      * Header row: dark navy with white text.
      * Rank / Name / Trend cells: WHITE fill with dark text
        (per the reference — these columns are NOT dark navy).
      * Metric cells: colored tiles with rounded corners; each cell
        outlined with a thin black border for definition; cells are
        separated by white grid divider lines.
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

# Colors sampled from the user's reference slide.
REF_COLORS = {
    "background":  "#0F172A",   # Fallback canvas if bg image missing.
    "header_bg":   "#0F172A",   # Header bar — solid dark navy.
    "blue":        "#0C769E",
    "green":       "#33CC33",
    "yellow":      "#FFFF00",
    "red":         "#FF0000",
    "text_white":  "#FFFFFF",
    "text_dark":   "#000000",
    "name_bg":     "#FFFFFF",   # Rank / Name / Trend cell fill.
    "grid":        "#FFFFFF",   # White grid divider lines.
    "border":      "#000000",   # Thin black tile outline for definition.
    "trend_up":    "#16A34A",
    "trend_flat":  "#6B7280",
}

LOGO_PATH = "/app/backend/assets/bubba_gump_logo.png"
BG_IMAGE_PATH = "/app/backend/assets/snapshot_bg.jpg"


# ---------------------------------------------------------------------------
# Color thresholds
# ---------------------------------------------------------------------------
def _ref_cell_color(value: float, metric_type: str) -> str:
    """Reference-template thresholds.

    - Percentage cols: >100 blue · 80-100 green · 60-80 yellow · <60 red
    - CV (NPS%/10 + promoters - 2*detractors): zero/neg = red
    - RT mentions / Bonus: zero = red
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


def _ref_text_color(bg: str) -> str:
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
    """Render +X.X for positive, -X.X for negative, 0.0 for zero (no '+0.0')."""
    if val == 0:
        return "0.0"
    return f"{val:+.1f}"


def _make_canvas() -> Image.Image:
    """Build the slide canvas with the diamond-pattern bg image."""
    if os.path.exists(BG_IMAGE_PATH):
        try:
            bg = Image.open(BG_IMAGE_PATH).convert("RGB")
            bg = bg.resize((SLIDE_WIDTH, SLIDE_HEIGHT), Image.Resampling.LANCZOS)
            return bg
        except Exception:
            pass
    return Image.new("RGB", (SLIDE_WIDTH, SLIDE_HEIGHT), REF_COLORS["background"])


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
        _draw_text(draw, (cx, logo_y), "BUBBA GUMP",
                   _load_font(36, True), REF_COLORS["text_white"], anchor="mm")

    # ---- Title ----
    title_y = 360
    _draw_text(draw, (cx, title_y), f"{quarter} SERVER",
               _load_font(36, True), REF_COLORS["text_white"], anchor="mm")
    _draw_text(draw, (cx, title_y + 50), "PERFORMANCE",
               _load_font(44, True), REF_COLORS["red"], anchor="mm")
    _draw_text(draw, (cx, title_y + 100), "SNAPSHOT",
               _load_font(36, True), REF_COLORS["text_white"], anchor="mm")
    # Date — smaller / lighter, matching reference proportions
    _draw_text(draw, (cx, title_y + 145),
               datetime.now().strftime("%B %d, %Y"),
               _load_font(18, True), REF_COLORS["red"], anchor="mm")

    # ---- Legend ----
    legend_y = title_y + 215
    items = [
        ("EXCEEDING ALL",   "EXPECTATIONS", REF_COLORS["blue"]),
        ("MEETING",         "EXPECTATIONS", REF_COLORS["green"]),
        ("WORK IN",         "PROGRESS",     REF_COLORS["yellow"]),
        ("NEEDS IMMEDIATE", "IMPROVEMENT",  REF_COLORS["red"]),
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
def _draw_tile(draw: ImageDraw.ImageDraw, box: Tuple[int, int, int, int],
               fill: str, radius: int = 4) -> None:
    """Draw a rounded-corner colored tile with a thin black border."""
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
               "LSC", "CV", "RT", "Bonus", "Score"]
    col_props = [0.06, 0.13, 0.06, 0.085, 0.085, 0.085,
                 0.085, 0.085, 0.085, 0.095, 0.095]
    col_widths = [int(p * table_w) for p in col_props]
    col_widths[-1] += table_w - sum(col_widths)

    # ---- Header bar ----
    header_h = 48
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
        ppa_pct     = ((emp.get("ppa_points", {}).get("earned", 0) or 0) / 30) * 100
        lbw_pct     = ((emp.get("lbw_points", {}).get("earned", 0) or 0) / 25) * 100
        glass_pct   = ((emp.get("glassware_points", {}).get("earned", 0) or 0) / 20) * 100
        lsc_pct     = ((emp.get("lsc_points", {}).get("earned", 0) or 0) / 30) * 100
        cv_score    = emp.get("cv_score", 0) or 0
        rt_mentions = emp.get("review_mentions", 0) or emp.get("rt_mentions", 0) or 0
        bonus       = emp.get("bonus_points", 0) or emp.get("metric_bonus", 0) or 0

        trend_dir = (emp.get("trend") or "up").lower()
        if trend_dir in ("up", "improving", "improved"):
            trend_glyph, trend_col = "\u25B2", REF_COLORS["trend_up"]
        elif trend_dir in ("down", "declining"):
            trend_glyph, trend_col = "\u25BC", REF_COLORS["red"]
        else:
            trend_glyph, trend_col = "\u2014", REF_COLORS["trend_flat"]

        # (text, fill_color or None, align, font, override_text_color or None,
        #  white_bg flag)
        cells: List[Tuple[str, str | None, str, ImageFont.FreeTypeFont, str | None, bool]] = [
            (pos_label,            None,                                       "center", rank_font,  REF_COLORS["text_dark"], True),
            (name,                 None,                                       "left",   name_font,  REF_COLORS["text_dark"], True),
            (trend_glyph,          None,                                       "center", trend_font, trend_col,                True),
            (f"{ppa_pct:.0f}%",    _ref_cell_color(ppa_pct,    "percentage"),  "center", cell_font,  None,                     False),
            (f"{lbw_pct:.0f}%",    _ref_cell_color(lbw_pct,    "percentage"),  "center", cell_font,  None,                     False),
            (f"{glass_pct:.0f}%",  _ref_cell_color(glass_pct,  "percentage"),  "center", cell_font,  None,                     False),
            (f"{lsc_pct:.0f}%",    _ref_cell_color(lsc_pct,    "percentage"),  "center", cell_font,  None,                     False),
            (_signed(cv_score),    _ref_cell_color(cv_score,   "cv"),          "center", cell_font,  None,                     False),
            (_signed(rt_mentions), _ref_cell_color(rt_mentions,"rt"),          "center", cell_font,  None,                     False),
            (_signed(bonus),       _ref_cell_color(bonus,      "bonus"),       "center", cell_font,  None,                     False),
            (f"{score:.1f}",       _ref_cell_color(score,      "score"),       "center", cell_font,  None,                     False),
        ]

        # White grid gutter — between cells the slide bg will show through;
        # we render each cell tile inset so 2px on every side acts as a grid
        # divider, and we paint it WHITE first to override the bg pattern.
        gutter_pad = 2

        x = table_x
        for (text, fill_color, align, font, override_text, is_white_bg), w in zip(cells, col_widths):
            # White grid block behind every cell (creates the white grid look)
            draw.rectangle((x, cy, x + w, cy + row_h),
                           fill=REF_COLORS["grid"])

            # Inner tile area
            box = (x + gutter_pad, cy + gutter_pad,
                   x + w - gutter_pad, cy + row_h - gutter_pad)

            if is_white_bg:
                # Rank/Name/Trend: white fill + thin black outline.
                _draw_tile(draw, box, REF_COLORS["name_bg"], radius=4)
                tcolor = override_text or REF_COLORS["text_dark"]
            else:
                _draw_tile(draw, box, fill_color, radius=4)
                tcolor = _ref_text_color(fill_color)

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
    img = _make_canvas()
    draw = ImageDraw.Draw(img)

    _draw_sidebar(img, draw, quarter)
    _draw_table(draw, rankings)

    buf = io.BytesIO()
    img.save(buf, format="PNG", optimize=True)
    buf.seek(0)
    return buf.getvalue()
