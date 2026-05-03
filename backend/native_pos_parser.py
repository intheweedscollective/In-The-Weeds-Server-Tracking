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


def _normalize_glyph_token(token: str) -> str:
    """Fix common font-glyph mis-encodings that appear in the BGLV Server
    Sales Report PDF. Applied ONLY to tokens that look like they *should*
    be numeric (i.e. contain at least one digit or match a known artifact).
    Known substitutions:
      * lowercase 'so' -> '50'   (seen as "2.857 so", "1.760 so")
      * isolated 'o'   -> '0'
      * isolated 'l'   -> '1'
    """
    if token.lower() == "so":
        return "50"
    # If the token has at least one digit, fix letter-for-digit confusions
    if any(c.isdigit() for c in token):
        fixed = token
        fixed = fixed.replace("O", "0").replace("o", "0")
        fixed = fixed.replace("l", "1")
        return fixed
    return token


def _join_column_tokens(tokens: list[str]) -> float | None:
    """Combine the 1-N tokens that fall into the same column band.

    PDFs sometimes split a "697.00" into ["697", "00"] when the period glyph
    fails to extract, or "1,685.50" into ["1.685", "50"], or "1,707.25" into
    ["1", "707", "25"]. We detect a trailing 2-digit cents token and
    concatenate the stripped integer portion, preserving the decimal.
    """
    if not tokens:
        return None

    if len(tokens) == 1:
        t = _normalize_glyph_token(tokens[0])
        v = _smart_float(t)
        if v is None:
            return None
        # Pattern "4.10300" or "1.13750": one period, >=4 digits after it.
        # The period is a thousands separator (was originally a comma) and
        # the last 2 digits are cents. Reconstruct as X,XXX.YY.
        if t.count(".") == 1:
            left, right = t.replace(",", "").split(".")
            if left.isdigit() and right.isdigit() and len(right) >= 4:
                try:
                    return float(f"{int(left + right[:-2])}.{right[-2:]}")
                except ValueError:
                    pass
        # Implicit-cents heuristic: a long all-digit token is almost certainly
        # missing its decimal. The Server Sales Report only ever has dollar
        # amounts with 2 decimals, so this is safe.
        if "." not in t and "," not in t and len(t) >= 3 and v >= 100:
            return round(v / 100.0, 2)
        return v

    # Normalize glyph artifacts across all tokens before combining
    tokens = [_normalize_glyph_token(t) for t in tokens]
    last = tokens[-1]
    # Case A: trailing token is exactly 2 digits = cents. Everything before it
    # is the integer portion (stripped of thousands-separator , and . noise).
    if last.isdigit() and len(last) == 2:
        int_part = "".join(t.replace(",", "").replace(".", "") for t in tokens[:-1])
        if int_part.isdigit():
            try:
                return float(f"{int_part}.{last}")
            except ValueError:
                pass

    # Case B: trailing token contains a period (e.g. "838.42") — it IS the
    # decimal portion. Anything before is the high-order digits.
    if "." in last and _is_numeric(last):
        int_prefix = "".join(t.replace(",", "").replace(".", "") for t in tokens[:-1])
        try:
            tail_val = float(last.replace(",", ""))
        except ValueError:
            tail_val = None
        if tail_val is not None:
            if int_prefix.isdigit() and int_prefix:
                try:
                    return float(f"{int_prefix}{last.replace(',', '')}")
                except ValueError:
                    return tail_val
            return tail_val

    # Fallback: try smart_float of the raw concatenated string
    joined = "".join(tokens).replace(",", "")
    return _smart_float(joined)


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
    """Find `label` followed by 1-3 numeric tokens and return the joined value.

    The Server Sales Report renders in two distinct layouts depending on
    the page's font kerning quirks:
      * Layout A (most pages, normal): label followed by 6 numeric tokens
        across 6 columns: `Food 10,034.61 827.34 73.71 ...`
      * Layout B (broken pages): the page text is reordered column-first,
        so each label is followed by ONLY its column-1 (Net Sls) value:
        `Food 10,034.61 Liquor 846.00 Beer 598.00 ...`

    Either way, the 1-3 tokens immediately after the label give us the Net
    Sls value, which is the field we care about most. Two-token splits like
    `Food 8,138 61` (period dropped by glyph extraction) are joined as
    "8138.61". Three-token splits like "13 567 98" → 13567.98. Also accepts
    the OCR artifact "so" as a trailing cents-token (= "50").
    """
    # Token = one or more digits/commas/periods, or the literal "so" glyph.
    token_re = r"(?:[\d.,]+|so)"
    pat = rf"\b{re.escape(label)}\b[\s.\-]+({token_re})(?:\s+({token_re}))?(?:\s+({token_re}))?"
    for m in re.finditer(pat, full_text, flags=re.IGNORECASE):
        toks = [g for g in m.groups() if g]
        # Only keep tokens that have a digit OR are the known 'so' glyph
        toks = [
            t for t in toks
            if any(c.isdigit() for c in t) or t.lower() == "so"
        ]
        # If the first token isn't numeric (just "so" alone), skip this match.
        if not toks or not any(c.isdigit() for c in toks[0]):
            continue
        v = _join_column_tokens(toks)
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
            # Reject tiny glyph-artifact rows (e.g. stray "av", "so", "EOC").
            # A real server name has either a space (first + last) OR at
            # least 4 alphabetic characters.
            alpha_count = sum(1 for c in cleaned if c.isalpha())
            if " " not in cleaned and alpha_count < 4:
                continue
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
    # Category labels that should NEVER co-appear in the same row. If two of
    # them land in the same cluster, the row is skewed/merged (PyMuPDF
    # sometimes zigzags tokens across two physically-distinct rows) and its
    # numeric tokens cannot be trusted. Skip those rows so the regex fallback
    # (which uses clean column-ordered text) fills the values instead.
    CATEGORY_LABELS = ("food", "liquor", "beer", "wine", "bar glassware", "loyalty", "totals")
    def _is_merged(line: str, matched_label: str) -> bool:
        # Count distinct category-label tokens that appear as whole-word
        # matches in this row's text. More than one = merged row.
        hits = 0
        for cand in CATEGORY_LABELS:
            if re.search(rf"\b{re.escape(cand)}\b", line):
                hits += 1
                if hits >= 2:
                    return True
        return False

    for r in rows:
        line = " ".join(w[4] for w in r).lower().strip()
        if not line:
            continue
        if any(s in line for s in EXCLUDE_FROM_LABELS):
            # Skip nested labels like "Stingray Food"
            continue
        for label, key in LABEL_KEYS:
            if line.startswith(label):
                if _is_merged(line, label):
                    # Row contains 2+ category labels — likely skewed/zigzagged.
                    # Leave metrics[key] unset; regex fallback will handle it.
                    break
                metrics[key] = _parse_metric_row(r)
                break

    # If the page collapsed everything to one row (bad font kerning), key
    # metrics will be missing or wrong. Fall back to regex on raw text.
    page_text = page.get_text("text") or ""
    # Normalize common label-glyph mis-encodings before regex matching.
    # Seen in the wild: "L,quor" (comma instead of 'i'), "Aquanum" for
    # "Aquarium" (not a target label but harmless to normalize), etc.
    page_text = re.sub(r"\bL,quor\b", "Liquor", page_text, flags=re.IGNORECASE)
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

    # Plausibility bounds: a single category's Net Sls on a per-server weekly
    # report can't exceed $100k. Anything larger is column-overflow garbage
    # (two columns of digits concatenated). Null those out so the regex
    # fallback below re-derives the correct value from clean text.
    CATEGORY_MAX = 100_000.0
    if food > CATEGORY_MAX:
        food = 0
    if liquor > CATEGORY_MAX:
        liquor = 0
    if beer > CATEGORY_MAX:
        beer = 0
    if wine > CATEGORY_MAX:
        wine = 0
    if glass > CATEGORY_MAX:
        glass = 0

    # Regex fallback: fill in any field that came up zero/missing using the
    # raw page text. Each label-grab is independent so we can mix-and-match
    # column-band hits with regex hits.
    #
    # "Implausibly tiny" rule: if the column-band path produced a non-zero
    # but very small value (< $10) on a page with meaningful guest traffic,
    # it was almost certainly a tokenization artifact where a glyph like
    # "so"/"o" landed outside the column band and only the integer prefix
    # (e.g. "2.857") was captured. Treat those as broken and let the regex
    # fallback — which sees clean column-ordered text — supply the value.
    IMPLAUSIBLY_TINY = 10.0
    label_to_key = [
        ("Food", "food"), ("Liquor", "liquor"), ("Beer", "beer"),
        ("Wine", "wine"), ("Bar Glassware", "glassware"),
    ]
    fixups = {"food": food, "liquor": liquor, "beer": beer, "wine": wine, "glassware": glass}
    for label_text, key in label_to_key:
        current = fixups[key]
        # Skip regex only if we have a value that clears the tiny threshold.
        # Wine is routinely <$10 for low-volume servers so it's exempt.
        if current and (current >= IMPLAUSIBLY_TINY or key == "wine"):
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
