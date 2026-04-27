"""
Full Rankings PNG Generator — Snapshot Style
Mirrors pdf_full_rankings.build_full_rankings_pdf as a 1920×1080 PNG for
digital signage (Yodeck etc.). Same dark navy aesthetic, sidebar branding,
color-coded legend, and Rank/Name/Trend/PPA/LBW/GLASS/LSC/CV/RT/Bonus/Score
metric table.
"""
from __future__ import annotations
import io
import os
from datetime import datetime
from typing import Any, Dict, List, Tuple

from PIL import Image, ImageDraw, ImageFont

from pdf_full_rankings import COLORS, get_cell_color, get_text_color_for_bg

SLIDE_WIDTH = 1920
SLIDE_HEIGHT = 1080
SIDEBAR_WIDTH = 360
LOGO_PATH = "/app/backend/assets/bubba_gump_logo.png"  # falls back to text logo if missing

_FONT_CANDIDATES = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/app/backend/assets/fonts/Quicksand-Bold.ttf",
    "/app/backend/assets/fonts/Quicksand-Regular.ttf",
]


def _load_font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    candidates = (
        ["DejaVuSans-Bold.ttf", "DejaVuSans.ttf"]
        if bold
        else ["DejaVuSans.ttf", "DejaVuSans-Bold.ttf"]
    )
    for name in candidates:
        for base in ("/usr/share/fonts/truetype/dejavu/", "/usr/share/fonts/truetype/"):
            path = os.path.join(base, name)
            if os.path.exists(path):
                try:
                    return ImageFont.truetype(path, size)
                except Exception:
                    continue
    # Last-ditch fallback so we always return something
    for path in _FONT_CANDIDATES:
        if os.path.exists(path):
            try:
                return ImageFont.truetype(path, size)
            except Exception:
                continue
    return ImageFont.load_default()


def _draw_text(draw, xy, text, font, fill, anchor: str = "lt"):
    draw.text(xy, str(text), font=font, fill=fill, anchor=anchor)


def _draw_sidebar(img: Image.Image, draw: ImageDraw.ImageDraw, quarter: str) -> None:
    # Sidebar bg already painted; here we add logo + title + legend + footer.
    cx = SIDEBAR_WIDTH // 2

    # Logo (image if present, otherwise stylized text fallback)
    logo_y_center = 130
    logo_drawn = False
    if os.path.exists(LOGO_PATH):
        try:
            logo = Image.open(LOGO_PATH).convert("RGBA")
            target_w = 200
            ratio = target_w / logo.width
            logo = logo.resize((target_w, int(logo.height * ratio)), Image.Resampling.LANCZOS)
            img.paste(logo, (cx - logo.width // 2, logo_y_center - logo.height // 2), logo)
            logo_drawn = True
        except Exception:
            logo_drawn = False
    if not logo_drawn:
        # Text fallback inside a circle
        r = 70
        draw.ellipse(
            (cx - r, logo_y_center - r, cx + r, logo_y_center + r),
            fill="#1a3050"
        )
        _draw_text(draw, (cx, logo_y_center - 20), "BUBBA",
                   _load_font(22, True), COLORS["text_white"], anchor="mm")
        _draw_text(draw, (cx, logo_y_center + 5), "GUMP",
                   _load_font(28, True), COLORS["red"], anchor="mm")
        _draw_text(draw, (cx, logo_y_center + 30), "SHRIMP CO.",
                   _load_font(13, True), COLORS["text_white"], anchor="mm")

    # Title block
    title_y = 280
    _draw_text(draw, (cx, title_y), f"{quarter} SERVER",
               _load_font(34, True), COLORS["text_white"], anchor="mm")
    _draw_text(draw, (cx, title_y + 50), "PERFORMANCE",
               _load_font(46, True), COLORS["red"], anchor="mm")
    _draw_text(draw, (cx, title_y + 100), "SNAPSHOT",
               _load_font(34, True), COLORS["text_white"], anchor="mm")
    _draw_text(draw, (cx, title_y + 150), datetime.now().strftime("%Y-%m-%d"),
               _load_font(20), COLORS["red"], anchor="mm")

    # Legend
    legend_y = title_y + 220
    items = [
        ("EXCEEDING ALL", "EXPECTATIONS", COLORS["blue"]),
        ("MEETING", "EXPECTATIONS", COLORS["green"]),
        ("WORK IN", "PROGRESS", COLORS["yellow"]),
        ("NEEDS IMMEDIATE", "IMPROVEMENT", COLORS["red"]),
    ]
    label_font = _load_font(15, True)
    for i, (l1, l2, color) in enumerate(items):
        y = legend_y + i * 65
        # Color swatch
        draw.rectangle((30, y, 60, y + 35), fill=color)
        # Text — black on yellow for legibility
        text_color = "#000000" if color == COLORS["yellow"] else COLORS["text_white"]
        _draw_text(draw, (75, y + 4), l1, label_font, text_color, anchor="lt")
        _draw_text(draw, (75, y + 20), l2, label_font, text_color, anchor="lt")

    # Footer
    footer_y = SLIDE_HEIGHT - 120
    foot = _load_font(15, True)
    for j, line in enumerate([
        "DON'T WAIT TO IMPACT",
        "THIS NUMBER.",
        "IF YOU HAVE QUESTIONS",
        "PLEASE SEE MANAGEMENT.",
    ]):
        _draw_text(draw, (cx, footer_y + j * 24), line, foot,
                   COLORS["text_white"], anchor="mm")


def _draw_table(
    draw: ImageDraw.ImageDraw,
    img: Image.Image,
    rankings: List[Dict[str, Any]],
) -> None:
    # Right-side table region
    table_x = SIDEBAR_WIDTH + 20
    table_y = 35
    table_w = SLIDE_WIDTH - table_x - 25

    headers = ["Rank", "Name", "Trend", "PPA", "LBW", "GLASS", "LSC", "CV", "RT", "Bonus", "Score"]
    # Proportional column widths summing to 1.0
    col_props = [0.06, 0.13, 0.05, 0.085, 0.085, 0.085, 0.085, 0.085, 0.085, 0.085, 0.085]
    col_widths = [int(p * table_w) for p in col_props]
    # Adjust last col so total matches
    col_widths[-1] += table_w - sum(col_widths)

    # Header row
    header_h = 42
    draw.rectangle(
        (table_x, table_y, table_x + table_w, table_y + header_h),
        fill=COLORS["header_bg"]
    )
    header_font = _load_font(15, True)
    x = table_x
    for header, w in zip(headers, col_widths):
        _draw_text(draw, (x + w // 2, table_y + header_h // 2),
                   header, header_font, COLORS["text_white"], anchor="mm")
        x += w

    # Body — fit all rows vertically. Min height 28px, max ~38px.
    row_count = max(1, len(rankings))
    available_h = SLIDE_HEIGHT - table_y - header_h - 35
    row_h = max(24, min(38, available_h // row_count))

    body_font = _load_font(max(11, row_h - 12), True)
    name_font = _load_font(max(11, row_h - 12), True)

    cy = table_y + header_h
    for idx, emp in enumerate(rankings):
        if cy + row_h > SLIDE_HEIGHT - 20:
            break
        # Alt row bg
        bg = COLORS["row_light"] if idx % 2 == 0 else COLORS["row_dark"]
        draw.rectangle((table_x, cy, table_x + table_w, cy + row_h), fill=bg)

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

        cells: List[Tuple[str, str | None, str]] = [
            (pos_label, None, "center"),
            (name, None, "left"),
            ("=", None, "center"),
            (f"{ppa_pct:.0f}%", get_cell_color(ppa_pct, "percentage"), "center"),
            (f"{lbw_pct:.0f}%", get_cell_color(lbw_pct, "percentage"), "center"),
            (f"{glass_pct:.0f}%", get_cell_color(glass_pct, "percentage"), "center"),
            (f"{lsc_pct:.0f}%", get_cell_color(lsc_pct, "percentage"), "center"),
            (f"+{cv_score:.1f}", get_cell_color(cv_score, "cv"), "center"),
            (f"+{rt_mentions:.1f}", get_cell_color(rt_mentions, "rt"), "center"),
            (f"+{bonus:.1f}", get_cell_color(bonus, "bonus"), "center"),
            (f"{score:.1f}", None, "right"),
        ]

        x = table_x
        for (text, cell_color, align), w in zip(cells, col_widths):
            if cell_color:
                pad = 3
                draw.rectangle(
                    (x + pad, cy + pad, x + w - pad, cy + row_h - pad),
                    fill=cell_color
                )
                tcolor = get_text_color_for_bg(cell_color)
            else:
                tcolor = COLORS["text_white"]
            ty = cy + row_h // 2
            if align == "center":
                _draw_text(draw, (x + w // 2, ty), text, body_font, tcolor, anchor="mm")
            elif align == "left":
                _draw_text(draw, (x + 8, ty), text, name_font, tcolor, anchor="lm")
            else:  # right
                _draw_text(draw, (x + w - 8, ty), text, body_font, tcolor, anchor="rm")
            x += w

        # Borders
        draw.line(
            (table_x, cy + row_h, table_x + table_w, cy + row_h),
            fill=COLORS["border"], width=1
        )
        cy += row_h

    # Vertical column dividers
    x = table_x
    for w in col_widths:
        draw.line(
            (x, table_y, x, cy),
            fill=COLORS["border"], width=1
        )
        x += w
    draw.line((x, table_y, x, cy), fill=COLORS["border"], width=1)


def build_full_rankings_png(
    rankings: List[Dict[str, Any]],
    quarter: str,
    year: int,
    thresholds: Dict[str, float] | None = None,
) -> bytes:
    """Render the Server Performance Snapshot as a 1920×1080 PNG."""
    img = Image.new("RGB", (SLIDE_WIDTH, SLIDE_HEIGHT), COLORS["background"])
    draw = ImageDraw.Draw(img)

    # Sidebar background tint to match the PDF (slightly darker)
    draw.rectangle((0, 0, SIDEBAR_WIDTH, SLIDE_HEIGHT), fill=COLORS["background"])

    _draw_sidebar(img, draw, quarter)
    _draw_table(draw, img, rankings)

    buf = io.BytesIO()
    img.save(buf, format="PNG", optimize=True)
    buf.seek(0)
    return buf.getvalue()
