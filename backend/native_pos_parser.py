"""
Native POS PDF Parser
=====================

Deterministic extraction of Server Sales Reports (Bubba Gump POS format).

Strategy:
  1. Use PyMuPDF (fitz) to read the PDF as natively-encoded text — works for
     the common case where the PDF is digitally generated (not scanned).
  2. Build per-page rows by clustering word bounding-box Y-coordinates.
  3. For each known label row (Food, Liquor, Beer, Wine, Loyalty, Bar
     Glassware, Totals), bucket numeric tokens into the correct table column
     using X-coordinate bands derived from the column header positions.
  4. Reconstruct numeric values that PDF font kerning split across two
     "words" (e.g. "8,138" + "61" -> 8138.61, "697" "00" -> 697.00).
  5. If the column-band extraction fails for a page (some pages render with
     all rows squashed onto one Y-line), fall back to a regex parse of the
     full page text.
  6. Fall back to AI OCR (existing pipeline) only if BOTH deterministic
     strategies fail to recover the key fields.

This module is a drop-in replacement for the AI-OCR-based extraction —
output schema matches `pos_ocr.extract_pos_data_from_pdf_bytes`.
"""

from __future__ import annotations

import logging
import re
from collections import defaultdict
from typing import Any

import fitz

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Layout constants
# ---------------------------------------------------------------------------

# X-coordinate bands for the 6 columns in the Sales-By-Category table.
# Derived empirically from the BGLV Server Sales Report layout (8.5"x11"
# portrait, table starts ~80px from left).
COL_BANDS = [
    ("netsls",   80, 145),   # Net Sales - the column we mostly care about
    ("taxes",   145, 210),
    ("vdsur",   210, 260),   # Voids/Surcharges/Orders
    ("grssls",  260, 320),   # Gross Sales (less Add Chgs)
    ("checkavg",320, 370),
    ("guestavg",370, 430),   # Guest Avg = PPA (only meaningful on Totals row)
]

# Map of label-text-prefix -> internal key. Order matters: longer first.
LABEL_KEYS = [
    ("bar glassware", "glassware"),
    ("loyalty", "loyalty"),
    ("totals", "totals"),
    ("liquor", "liquor"),
    ("food", "food"),
    ("beer", "beer"),
    ("wine", "wine"),
]

# Label rows that look similar but should NEVER be matched (nested labels)
EXCLUDE_FROM_LABELS = (
    "stingray food", "banquet", "reef refresh", "defer", "non revenue",
    "room revenue", "aquarium", "shark voyage", "ferris", "carousel",
    "other rides", "games", "photos", "parking", "valet", "third party",
)


# ---------------------------------------------------------------------------
# Numeric helpers
# ---------------------------------------------------------------------------

def _smart_float(token: str) -> float | None:
    """Parse a single numeric token. Handles both '9,762.61' and '9.762.61'.

    The latter shows up because some pages render commas as periods. If a
    token contains 2+ dots we treat all but the last as thousands separators.
    """
    t = token.replace(",", "")
    if t.count(".") >= 2:
        parts = t.split(".")
        t = "".join(parts[:-1]) + "." + parts[-1]
    try:
        return float(t)
    except ValueError:
        return None


def _join_column_tokens(tokens: list[str]) -> float | None:
    """Combine the 1-2-3 tokens that fall into the same column band.

    PDFs often split a "697.00" into ["697", "00"] when the period glyph
    fails to extract. We join them with '.'. Single-token whole numbers >= 100
    with no decimal are also treated as cents-shifted (e.g. "69700" -> 697.00).
    """
    if not tokens:
        return None

    if len(tokens) == 1:
        t = tokens[0]
        v = _smart_float(t)
        if v is None:
            return None
        # Implicit-cents heuristic: a long all-digit token is almost certainly
        # missing its decimal. The Server Sales Report only ever has dollar
        # amounts with 2 decimals, so this is safe.
        if "." not in t and "," not in t and len(t) >= 3 and v >= 100:
            return round(v / 100.0, 2)
        return v

    if len(tokens) == 2:
        a, b = tokens
        if "." not in a and "." not in b:
            return _smart_float(f"{a}.{b}")
        return _smart_float(a + b)

    return _smart_float("".join(tokens))


def _is_numeric(s: str) -> bool:
    return bool(re.match(r"^[\d,.]+$", s)) and any(c.isdigit() for c in s)


# ---------------------------------------------------------------------------
# Row extraction (column-band strategy)
# ---------------------------------------------------------------------------

def _cluster_rows(words: list[tuple], y_tol: float = 4.0) -> list[list[tuple]]:
    """Group word tuples by Y-coordinate (PyMuPDF format)."""
    words = sorted(words, key=lambda w: (w[1], w[0]))
    rows: list[list[tuple]] = []
    cur: list[tuple] = []
    last_y: float | None = None
    for w in words:
        y = w[1]
        if last_y is None or abs(y - last_y) <= y_tol:
            cur.append(w)
        else:
            rows.append(cur)
            cur = [w]
        last_y = y
    if cur:
        rows.append(cur)
    for r in rows:
        r.sort(key=lambda w: w[0])
    return rows


def _parse_metric_row(row: list[tuple]) -> dict[str, float]:
    """Bucket numeric words into column bands, then merge tokens per column.

    Refuses to extract from "wide rows" (where the entire page collapses
    onto one Y-line) — caller should fall back to regex parsing in that case.
    """
    numeric_count = sum(1 for w in row if _is_numeric(w[4]))
    if numeric_count > 14:
        # Page rendered all categories on one line — column bands are unreliable.
        return {}

    cols: dict[str, list[str]] = defaultdict(list)
    for w in row:
        x, _, _, _, t, *_ = w
        if not _is_numeric(t):
            continue
        for cname, lo, hi in COL_BANDS:
            if lo <= x < hi:
                cols[cname].append(t)
                break
    return {c: v for c, v in ((c, _join_column_tokens(toks)) for c, toks in cols.items()) if v is not None}


# ---------------------------------------------------------------------------
# Regex fallback (for pages where rows render on a single Y-line)
# ---------------------------------------------------------------------------

def _grab_label_value(label: str, full_text: str) -> float | None:
    """Find `label` followed by 1-2 numeric tokens and return the joined value.

    The Server Sales Report renders in two distinct layouts depending on
    the page's font kerning quirks:
      * Layout A (most pages, normal): label followed by 6 numeric tokens
        across 6 columns: `Food 10,034.61 827.34 73.71 ...`
      * Layout B (broken pages): the page text is reordered column-first,
        so each label is followed by ONLY its column-1 (Net Sls) value:
        `Food 10,034.61 Liquor 846.00 Beer 598.00 ...`

    Either way, the 1-2 tokens immediately after the label give us the Net
    Sls value, which is the field we care about most. Two-token splits like
    `Food 8,138 61` (period dropped by glyph extraction) are joined as
    "8138.61".
    """
    pat = rf"\b{re.escape(label)}\b[\s.\-]+([\d.,]+)(?:\s+([\d.,]+))?"
    for m in re.finditer(pat, full_text, flags=re.IGNORECASE):
        a = m.group(1)
        b = m.group(2)
        if not _is_numeric(a):
            continue
        # Only join with b if b is numeric AND a has no decimal AND together
        # they look like a split value
        if b and _is_numeric(b) and "." not in a and "." not in b and len(b) <= 2:
            v = _join_column_tokens([a, b])
        else:
            v = _join_column_tokens([a])
        if v is not None and v > 0:
            return v
    return None


def _grab_totals_row(full_text: str) -> dict[str, float] | None:
    """Find the Totals row and return all 6 columns when possible."""
    # Match Totals followed by 6 numeric tokens (worst-case: 12 if all split)
    pat = r"\bTotals\b\s+((?:[\d.,]+\s+){5,11}[\d.,]+)"
    m = re.search(pat, full_text, flags=re.IGNORECASE)
    if not m:
        return None
    raw = m.group(1).split()
    nums: list[float] = []
    i = 0
    # Greedy join: pair consecutive split tokens like ["8,138","61"] → 8138.61
    while i < len(raw):
        a = raw[i]
        if i + 1 < len(raw):
            b = raw[i + 1]
            if _is_numeric(a) and _is_numeric(b) and "." not in a and "." not in b and len(b) <= 2:
                v = _join_column_tokens([a, b])
                if v is not None:
                    nums.append(v)
                    i += 2
                    continue
        v = _join_column_tokens([a])
        if v is not None:
            nums.append(v)
        i += 1
    if len(nums) < 6:
        return None
    # Take last 6 (in case there were stray dashes captured)
    nums = nums[:6]
    return {
        "netsls": nums[0], "taxes": nums[1], "vdsur": nums[2],
        "grssls": nums[3], "checkavg": nums[4], "guestavg": nums[5],
    }


# ---------------------------------------------------------------------------
# Page parser
# ---------------------------------------------------------------------------

def _extract_name(rows: list[list[tuple]]) -> str | None:
    """Server name = the last alphabetic-only row before any data row."""
    skip_substrings = (
        "bglv", "gump", "bubba", "page ", "printed", "vegas blvd",
        "89109", "sales report", "04/", "19.6", "19 6", "sales by",
        "category", "net s", "taxes", "grs s", "check", "guest avg",
        "vd/sur", "add chgs",
    )
    data_idx = None
    for i, r in enumerate(rows):
        line = " ".join(w[4] for w in r).lower()
        if any(line.startswith(lab) or f" {lab} " in f" {line} " for lab, _ in LABEL_KEYS):
            data_idx = i
            break
    if data_idx is None:
        return None
    for j in range(data_idx - 1, -1, -1):
        cand = " ".join(w[4] for w in rows[j]).strip()
        cand_low = cand.lower()
        if not cand or any(s in cand_low for s in skip_substrings):
            continue
        if any(c.isalpha() for c in cand) and not any(c.isdigit() for c in cand):
            # Strip any leading/trailing non-alpha punctuation (bullets, dashes)
            cleaned = re.sub(r"^[^A-Za-z]+", "", cand).strip()
            cleaned = re.sub(r"[^A-Za-z\s'\-.]+$", "", cleaned).strip()
            return cleaned or cand
    return None


def _extract_guest_count(rows: list[list[tuple]]) -> int | None:
    for r in rows:
        line = " ".join(w[4] for w in r).lower()
        if "total guests" in line:
            for w in reversed(r):
                t = w[4]
                if t.isdigit():
                    return int(t)
    return None


def _parse_page(page) -> dict[str, Any] | None:
    words = page.get_text("words")
    if not words:
        return None

    rows = _cluster_rows(words)
    name = _extract_name(rows)
    guest_count = _extract_guest_count(rows)

    metrics: dict[str, dict[str, float]] = {}
    for r in rows:
        line = " ".join(w[4] for w in r).lower().strip()
        if not line:
            continue
        if any(s in line for s in EXCLUDE_FROM_LABELS):
            # Skip nested labels like "Stingray Food"
            continue
        for label, key in LABEL_KEYS:
            if line.startswith(label):
                metrics[key] = _parse_metric_row(r)
                break

    # If the page collapsed everything to one row (bad font kerning), key
    # metrics will be missing or wrong. Fall back to regex on raw text.
    page_text = page.get_text("text") or ""
    page_text_clean = re.sub(r"\s+", " ", page_text.replace("\n", " "))

    def _val(metric_key: str, col: str = "netsls") -> float:
        return (metrics.get(metric_key) or {}).get(col) or 0

    food = _val("food")
    liquor = _val("liquor")
    beer = _val("beer")
    wine = _val("wine")
    glass = _val("glassware")
    loyalty_cols = metrics.get("loyalty") or {}
    loyalty = max(loyalty_cols.get("vdsur") or 0, loyalty_cols.get("grssls") or 0)
    totals_cols = metrics.get("totals") or {}
    net_sales = totals_cols.get("netsls") or 0
    ppa = totals_cols.get("guestavg") or 0

    # Regex fallback: fill in any field that came up zero/missing using the
    # raw page text. Each label-grab is independent so we can mix-and-match
    # column-band hits with regex hits.
    label_to_key = [
        ("Food", "food"), ("Liquor", "liquor"), ("Beer", "beer"),
        ("Wine", "wine"), ("Bar Glassware", "glassware"),
    ]
    fixups = {"food": food, "liquor": liquor, "beer": beer, "wine": wine, "glassware": glass}
    for label_text, key in label_to_key:
        if fixups[key]:
            continue
        v = _grab_label_value(label_text, page_text_clean)
        if v is not None:
            fixups[key] = v
    food, liquor, beer, wine, glass = (
        fixups["food"], fixups["liquor"], fixups["beer"],
        fixups["wine"], fixups["glassware"],
    )

    # Loyalty fallback: try to grab the value from layout B too. In layout B
    # the loyalty value at the start of the row IS the Net Sls — but the user
    # cares about the loyalty *card* total which can sit in either Vd/Sur or
    # Grs Sls. If we can't get the structured row, accept Net Sls as a proxy.
    if not loyalty:
        v = _grab_label_value("Loyalty", page_text_clean)
        if v is not None:
            loyalty = v

    # Totals fallback
    if not net_sales or not ppa:
        tot = _grab_totals_row(page_text_clean)
        if tot:
            net_sales = net_sales or tot.get("netsls") or 0
            ppa = ppa or tot.get("guestavg") or 0

    # If still missing PPA but have net_sales + guest_count, derive it
    if not ppa and net_sales and guest_count:
        ppa = round(net_sales / guest_count, 2)
    # If still missing net_sales but have category sums, derive it
    if not net_sales:
        net_sales = food + liquor + beer + wine + glass + loyalty

    if not name and not net_sales and not guest_count:
        # Page contains no usable data
        return None

    return {
        "name": name or "Unknown",
        "guest_count": guest_count or 0,
        "net_sales": round(net_sales, 2),
        "ppa": round(ppa, 2),
        "food_sales": round(food, 2),
        "liquor_sales": round(liquor, 2),
        "beer_sales": round(beer, 2),
        "wine_sales": round(wine, 2),
        "lbw_total": round(liquor + beer + wine, 2),
        "bar_glassware_sales": round(glass, 2),
        "loyalty_sales": round(loyalty, 2),
        "_source": "native_pdf",
    }


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def extract_pos_data_from_pdf_bytes_native(pdf_bytes: bytes) -> dict[str, Any]:
    """
    Returns the same shape as `pos_ocr.validate_extracted_data` so it can be
    used as a drop-in replacement.

    Output:
      {
        "success": bool,
        "employees": [ { ... }, ... ],
        "total_extracted": int,
        "extraction_notes": str,
        "extraction_method": "native_pdf"
      }
    """
    try:
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    except Exception as e:
        logger.error(f"Failed to open PDF with PyMuPDF: {e}")
        return {
            "success": False,
            "employees": [],
            "total_extracted": 0,
            "extraction_notes": f"PyMuPDF open failed: {e}",
            "extraction_method": "native_pdf",
        }

    employees: list[dict[str, Any]] = []
    failures = 0
    for i, page in enumerate(doc):
        try:
            emp = _parse_page(page)
            if emp:
                employees.append(emp)
            else:
                failures += 1
        except Exception as e:
            logger.warning(f"Native parse failed on page {i+1}: {e}")
            failures += 1

    doc.close()

    return {
        "success": len(employees) > 0,
        "employees": employees,
        "total_extracted": len(employees),
        "extraction_notes": (
            f"Native extraction processed {len(employees)} employees" +
            (f" ({failures} pages skipped)" if failures else "")
        ),
        "extraction_method": "native_pdf",
    }


def is_pdf_native_extractable(pdf_bytes: bytes) -> bool:
    """Quick check whether a PDF has selectable text on at least one page."""
    try:
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        for page in doc:
            text = page.get_text("text") or ""
            # Heuristic: any page with 50+ alpha chars => likely native text
            if sum(1 for c in text if c.isalpha()) >= 50:
                doc.close()
                return True
        doc.close()
    except Exception:
        pass
    return False
