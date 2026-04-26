"""
QR Leaderboard Slide Generator
==============================

Generates a 16:9 (1920x1080) PNG slide of the QR Tracker leaderboard for
download / digital signage. Matches the visual language of the existing
Server Performance Snapshot slide:

  * Dark slate background with the Bubba Gump branding panel on the left
  * Color-coded rank badges (gold/silver/bronze for 1-2-3)
  * Per-platform columns (Yelp / Google / TripAdvisor / Total)
  * Heatmap-style value cells (red→yellow→green based on relative performance)
  * Footer with the quarter date
"""

from __future__ import annotations

import io
import os
from typing import Any

from PIL import Image, ImageDraw, ImageFont

# --- Theme ----------------------------------------------------------------

BG = (15, 23, 42)           # slate-900
BG_PANEL = (30, 41, 59)     # slate-800
HEADER_BG = (51, 65, 85)    # slate-700
ROW_ALT = (22, 31, 49)
TEXT = (241, 245, 249)
TEXT_DIM = (148, 163, 184)
GRID = (51, 65, 85)
GOLD = (251, 191, 36)
SILVER = (203, 213, 225)
BRONZE = (180, 83, 9)
RED = (239, 68, 68)
YELLOW_500 = (234, 179, 8)
GREEN_500 = (34, 197, 94)
EMERALD = (16, 185, 129)
BLUE_500 = (59, 130, 246)
VIOLET = (139, 92, 246)


def _font(size: int, bold: bool = False) -> ImageFont.ImageFont:
    """Load DejaVu (always present in the container)."""
    try:
        path = (
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
            if bold else
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
        )
        return ImageFont.truetype(path, size)
    except Exception:
        return ImageFont.load_default()


def _draw_centered(draw: ImageDraw.ImageDraw, text: str, x: float, y: float,
                   font: ImageFont.ImageFont, fill: tuple) -> None:
    bbox = draw.textbbox((0, 0), text, font=font)
    w = bbox[2] - bbox[0]
    h = bbox[3] - bbox[1]
    draw.text((x - w / 2, y - h / 2), text, font=font, fill=fill)


def _heat_color(value: int, max_value: int) -> tuple:
    """Red (low) -> Yellow (mid) -> Green (high) heatmap."""
    if max_value <= 0:
        return TEXT_DIM
    ratio = max(0.0, min(1.0, value / max_value))
    if ratio <= 0.05:
        return RED
    if ratio < 0.4:
        return (220, 100, 60)
    if ratio < 0.7:
        return YELLOW_500
    return GREEN_500


def generate_qr_leaderboard_slide(
    employees: list[dict[str, Any]],
    quarter: str = "Q2",
    year: int = 2026,
    title: str | None = None,
) -> bytes:
    """
    Render the QR leaderboard to a 1920x1080 PNG.

    `employees` should be a list of dicts with keys:
        name, yelp_clicks, google_clicks, tripadvisor_clicks
    Will be ranked by total clicks descending.
    """
    width, height = 1920, 1080
    img = Image.new("RGB", (width, height), BG)
    draw = ImageDraw.Draw(img)

    # Sort defensively
    def total(e):
        return (e.get("yelp_clicks") or 0) + (e.get("google_clicks") or 0) + (e.get("tripadvisor_clicks") or 0)

    employees = sorted(employees, key=total, reverse=True)

    # ----- Left brand panel ------------------------------------------------
    panel_w = 460
    draw.rectangle([(0, 0), (panel_w, height)], fill=BG_PANEL)

    # Logo (try to load the standard asset; fall back to text)
    logo_path = "/app/backend/assets/bubba_gump_logo.png"
    logo_y = 70
    if os.path.exists(logo_path):
        try:
            logo = Image.open(logo_path).convert("RGBA")
            logo.thumbnail((280, 280))
            img.paste(logo, ((panel_w - logo.width) // 2, logo_y), logo)
            logo_y += logo.height + 30
        except Exception:
            logo_y = 80
    else:
        logo_y = 80

    # Title block
    title_text = title or "QR REVIEW\nLEADERBOARD"
    f_title = _font(54, bold=True)
    y = logo_y + 40
    for line in title_text.split("\n"):
        _draw_centered(draw, line, panel_w / 2, y, f_title, GOLD)
        y += 65

    f_period = _font(32, bold=True)
    _draw_centered(draw, f"{quarter} {year}", panel_w / 2, y + 30, f_period, TEXT)

    # Legend
    f_legend_label = _font(20, bold=True)
    f_legend = _font(18)
    legend_y = height - 280
    legend_items = [
        (GOLD, "1st - Champion"),
        (SILVER, "2nd - Runner Up"),
        (BRONZE, "3rd - Third Place"),
        (GREEN_500, "Top 5 - Honor Roll"),
    ]
    _draw_centered(draw, "RANK LEGEND", panel_w / 2, legend_y, f_legend_label, GOLD)
    for i, (color, label) in enumerate(legend_items):
        cy = legend_y + 40 + i * 36
        # color square
        draw.rectangle([panel_w / 2 - 130, cy - 12, panel_w / 2 - 100, cy + 12], fill=color)
        # label
        draw.text((panel_w / 2 - 90, cy - 10), label, font=f_legend, fill=TEXT)

    # ----- Right side: title + table ---------------------------------------
    table_x = panel_w + 60
    table_y = 70
    table_w = width - table_x - 60

    f_header = _font(44, bold=True)
    draw.text((table_x, table_y), "Top Reviewers by QR Scans", font=f_header, fill=TEXT)
    draw.text((table_x, table_y + 60), f"Live data — {quarter} {year}", font=_font(22), fill=TEXT_DIM)

    # Column layout (after header)
    col_x = {
        "rank": table_x + 10,
        "name": table_x + 90,
        "yelp": table_x + table_w - 460,
        "google": table_x + table_w - 340,
        "tripadvisor": table_x + table_w - 220,
        "total": table_x + table_w - 90,
    }

    head_y = table_y + 130
    f_col = _font(22, bold=True)
    draw.rectangle([(table_x, head_y - 8), (table_x + table_w, head_y + 36)], fill=HEADER_BG)
    draw.text((col_x["rank"], head_y), "Rank", font=f_col, fill=TEXT)
    draw.text((col_x["name"], head_y), "Employee", font=f_col, fill=TEXT)
    _draw_centered(draw, "Yelp",        col_x["yelp"],        head_y + 14, f_col, RED)
    _draw_centered(draw, "Google",      col_x["google"],      head_y + 14, f_col, BLUE_500)
    _draw_centered(draw, "TripAdvisor", col_x["tripadvisor"], head_y + 14, f_col, EMERALD)
    _draw_centered(draw, "Total",       col_x["total"],       head_y + 14, f_col, VIOLET)

    # Rows — show top 12
    visible = employees[:12]
    if not visible:
        # Nothing to render
        f_empty = _font(28)
        draw.text((table_x + 40, head_y + 80), "No QR scan data yet — generate codes for your team to start tracking.",
                  font=f_empty, fill=TEXT_DIM)
        out = io.BytesIO()
        img.save(out, format="PNG", optimize=True)
        return out.getvalue()

    max_total = max(total(e) for e in visible) or 1
    row_h = 64
    row_y = head_y + 56
    f_row_name = _font(26, bold=True)
    f_row_num = _font(28, bold=True)
    f_row_total = _font(34, bold=True)
    f_rank_badge = _font(28, bold=True)

    for i, emp in enumerate(visible):
        cy = row_y + i * row_h
        # row alternating bg
        if i % 2 == 0:
            draw.rectangle([(table_x, cy - 6), (table_x + table_w, cy + row_h - 14)], fill=ROW_ALT)

        rank = i + 1
        rank_color = GOLD if rank == 1 else SILVER if rank == 2 else BRONZE if rank == 3 else (
            GREEN_500 if rank <= 5 else TEXT_DIM)

        # rank badge
        badge_r = 22
        bx = col_x["rank"] + 8
        by = cy + 16
        draw.ellipse([bx - badge_r, by - badge_r, bx + badge_r, by + badge_r], fill=rank_color)
        _draw_centered(draw, str(rank), bx, by, f_rank_badge,
                       (15, 23, 42) if rank in (1, 2, 4, 5) else TEXT)

        # name
        name = (emp.get("name") or "—").strip()
        if len(name) > 28:
            name = name[:27] + "…"
        draw.text((col_x["name"], cy + 6), name, font=f_row_name, fill=TEXT)

        # platform values (heatmap-tinted)
        yelp = int(emp.get("yelp_clicks") or 0)
        google = int(emp.get("google_clicks") or 0)
        ta = int(emp.get("tripadvisor_clicks") or 0)
        tot = yelp + google + ta

        _draw_centered(draw, str(yelp),   col_x["yelp"],   cy + 18, f_row_num, _heat_color(yelp, max_total))
        _draw_centered(draw, str(google), col_x["google"], cy + 18, f_row_num, _heat_color(google, max_total))
        _draw_centered(draw, str(ta),     col_x["tripadvisor"], cy + 18, f_row_num, _heat_color(ta, max_total))

        # total — pill-style on right
        pill_w, pill_h = 110, 44
        px = col_x["total"] - pill_w / 2
        py = cy + 18 - pill_h / 2
        draw.rounded_rectangle([(px, py), (px + pill_w, py + pill_h)],
                               radius=12, fill=(VIOLET[0] // 3, VIOLET[1] // 3, VIOLET[2] // 3))
        _draw_centered(draw, str(tot), col_x["total"], cy + 18, f_row_total, VIOLET)

    # Footer
    footer_y = height - 60
    draw.line([(table_x, footer_y - 20), (table_x + table_w, footer_y - 20)], fill=GRID, width=1)
    draw.text((table_x, footer_y - 5),
              "Drop a review — every scan ranks your favorite server.",
              font=_font(20), fill=TEXT_DIM)

    out = io.BytesIO()
    img.save(out, format="PNG", optimize=True)
    return out.getvalue()
