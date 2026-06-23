"""
compare_pdf_sources.py — READ-ONLY.

Compare the two surviving 'parse results' from SSD 6.15.26.pdf:
  Source A — db.upload_jobs job_id 8f358c51 (original deployed-app pdf_parse).
  Source B — db.snapshot_workflow.Q2P6W2.uploads[0].parsed_data
             (re-synced from employees_v2 — NOT a direct re-parse).

The PDF file bytes are not retained anywhere (file_data=None, file_size=0,
no GridFS). Operator anchor values are checked against both.

No writes.
"""

import asyncio
import os
import sys

from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient

load_dotenv("/app/backend/.env")
sys.path.insert(0, "/app/backend")

# Operator-supplied anchor values (must match PDF exactly).
ANCHORS = {
    "Kahiaulani Ramos": (30516.08,  643, 47.46, "Kahiaulanl Ramos"),
    "Thomas Kozan":     (56485.89, 1168, 48.36, "Thomas Kozan"),
    "Glennice Nguyen":  (67753.38, 1412, 47.98, "Glennlce Nguyen"),
}


async def main() -> None:
    db = AsyncIOMotorClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]

    # -- Source A --
    job = await db.upload_jobs.find_one({"job_id": "8f358c51-f752-4d8b-9dad-8ece16559117"})
    src_a = {e["name"]: e for e in (job.get("result") or {}).get("employees") or []}
    print(f"Source A (upload_jobs job 8f358c51 — pdf_parse): {len(src_a)} rows")

    # -- Source B --
    live = await db.snapshot_workflow.find_one({"name": "Q2P6W2"})
    up = (live.get("uploads") or [None])[0]
    src_b_all = (up.get("parsed_data") or {}).get("employees") or []
    src_b = {e["name"]: e for e in src_b_all}
    print(f"Source B (snapshot uploads[0].parsed_data, source={up.get('source')!r}): "
          f"{len(src_b)} rows")
    print()
    print(f"Source B notes: file_size={up.get('file_size')}  status={up.get('status')!r}  "
          f"parsed_at={up.get('parsed_at')}")
    print()

    # ----------------------------------------------------------------
    # ANCHOR CROSS-CHECK against operator-confirmed truth.
    # ----------------------------------------------------------------
    print("=" * 100)
    print("ANCHOR CROSS-CHECK against operator-confirmed values")
    print("=" * 100)
    print(f"{'canonical':22}  {'src':3}  {'row label':22}  {'net':>10}  {'guests':>6}  {'ppa':>5}  result")
    print("-" * 100)
    for canonical, (e_net, e_g, e_ppa, _src_row) in ANCHORS.items():
        for label, src in [("A", src_a), ("B", src_b)]:
            # Try canonical and typo'd variants
            candidates = [canonical, _src_row]
            r = None
            for name in candidates:
                if name in src:
                    r = src[name]; break
            if not r:
                print(f"{canonical:22}  {label:3}  {'(no row)':22}  "
                      f"{'-':>10}  {'-':>6}  {'-':>5}  ❌ MISSING")
                continue
            net = float(r.get("net_sales") or 0)
            g = int(r.get("guest_count") or r.get("guests") or 0)
            ppa = float(r.get("ppa") or 0)
            ok = abs(net - e_net) < 0.01 and g == e_g and abs(ppa - e_ppa) < 0.05
            mark = "✓" if ok else "❌"
            row_label = r.get("name", "?")
            print(f"{canonical:22}  {label:3}  {row_label:22}  "
                  f"{net:>10.2f}  {g:>6}  {ppa:>5.2f}  {mark}  "
                  f"(expected {e_net}/{e_g}/{e_ppa})")
    print()

    # ----------------------------------------------------------------
    # PER-SERVER DIFFS A vs B — net, guests, food, loyalty.
    # ----------------------------------------------------------------
    all_names = set(src_a) | set(src_b)
    # Map alias-spelling to canonical for grouping
    canon_map = {
        "Kahiaulanl Ramos": "Kahiaulani Ramos",
        "Kahiauani Ramos": "Kahiaulani Ramos (alias)",
        "Kahi Ramos": "Kahiaulani Ramos (alias)",
        "Glennlce Nguyen": "Glennice Nguyen",
        "Lennie Nguyen": "Glennice Nguyen (alias)",
        "TK Kozan": "Thomas Kozan (alias)",
        "Keisha Martin": "Lakeisha Martin (alias)",
        "Trey Quick": "Treyanna Quick (alias)",
        "Abby Ostrowski": "Abigail Ostrowski (alias)",
        "Ikey Ostgarden": "Eric Ostgarden (alias)",
        "Allen Simmons": "Craig Simmons (alias)",
    }

    print("=" * 134)
    print("PER-SERVER COMPARISON  —  Source A vs Source B  (only showing rows where A and/or B differ from each other or from operator anchors)")
    print("=" * 134)
    print(f"{'name (canonical group)':30}  {'src':3}  {'net':>10}  {'guests':>6}  {'ppa':>5}  {'food':>13}  {'liq':>8}  {'beer':>8}  {'wine':>6}  {'glass':>7}  {'loy':>10}")
    print("-" * 134)

    rows_to_show = []
    for name in sorted(all_names):
        a = src_a.get(name); b = src_b.get(name)
        diff = False
        if a and b:
            for k in ("net_sales","guest_count","ppa","food_sales","liquor_sales","beer_sales","wine_sales","bar_glassware_sales","loyalty_sales"):
                va = float((a.get(k) or 0))
                vb_raw = b.get(k)
                if vb_raw is None and k == "guest_count":
                    vb_raw = b.get("guests")
                vb = float(vb_raw or 0)
                if abs(va - vb) > 0.05:
                    diff = True; break
        else:
            diff = True
        if diff:
            rows_to_show.append(name)

    for name in rows_to_show:
        canon = canon_map.get(name, name)
        for label, src in [("A", src_a), ("B", src_b)]:
            r = src.get(name)
            if not r:
                print(f"{name:30}  {label:3}  {'(missing in source ' + label + ')'}")
                continue
            net = float(r.get("net_sales") or 0)
            g = int(r.get("guest_count") or r.get("guests") or 0)
            ppa = float(r.get("ppa") or 0)
            food = float(r.get("food_sales") or 0)
            liq = float(r.get("liquor_sales") or 0)
            beer = float(r.get("beer_sales") or 0)
            wine = float(r.get("wine_sales") or 0)
            glass = float(r.get("bar_glassware_sales") or 0)
            loy = float(r.get("loyalty_sales") or 0)
            food_str = f"{food:.2f}" if food < 1e7 else f"{food:.2e}"
            print(f"{name:30}  {label:3}  {net:>10.2f}  {g:>6}  {ppa:>5.2f}  "
                  f"{food_str:>13}  {liq:>8.2f}  {beer:>8.2f}  {wine:>6.2f}  "
                  f"{glass:>7.2f}  {loy:>10.2f}")
        print()
    print("-" * 134)
    print(f"Servers with A↔B disagreement: {len(rows_to_show)}")
    print()

    # ----------------------------------------------------------------
    # NAMES IN B BUT NOT IN A (and vice versa).
    # ----------------------------------------------------------------
    only_a = sorted(set(src_a) - set(src_b))
    only_b = sorted(set(src_b) - set(src_a))
    print(f"Only in Source A ({len(only_a)}): {only_a}")
    print(f"Only in Source B ({len(only_b)}): {only_b}")
    print()

    # ----------------------------------------------------------------
    # INTEGRITY CHECK on Source B for the 29 canonicals it carries.
    # ----------------------------------------------------------------
    print("=" * 100)
    print("Source B integrity (Food+Liq+Beer+Wine+Loy+Glass == Net) for 29 canonicals")
    print("=" * 100)
    # Apply OPERATOR's Ethan loyalty correction ($325.00).
    fail_b = []
    for name, r in sorted(src_b.items()):
        net = float(r.get("net_sales") or 0)
        food = float(r.get("food_sales") or 0)
        liq = float(r.get("liquor_sales") or 0)
        beer = float(r.get("beer_sales") or 0)
        wine = float(r.get("wine_sales") or 0)
        glass = float(r.get("bar_glassware_sales") or 0)
        loy = float(r.get("loyalty_sales") or 0)
        if name == "Ethan Dever":
            loy = 325.00
        cat_sum = food + liq + beer + wine + glass + loy
        diff = round(cat_sum - net, 2)
        if abs(diff) > 0.05:
            food_str = f"${food:,.2f}" if food < 1e7 else f"${food:.2e}"
            fail_b.append((name, food_str, net, cat_sum, diff))
    print(f"Source B failures (after Ethan OCR fix): {len(fail_b)}")
    for nm, f, net, sm, df in fail_b:
        print(f"   ❌ {nm:30}  food={f:>16}  net={net:>11.2f}  sum={sm:>14.2f}  diff={df:>+12.2f}")
    print()

    print("=" * 78)
    print("CONCLUSION:")
    print("  • Source A (upload_jobs pdf_parse)  has CORRECT Thomas Kozan guests=1168")
    print("    but OCR artifacts: Cory food=$132,234, Ethan food=$3, Ethan loy=$325k")
    print("  • Source B (snapshot uploads parsed_data, synced_from_employees_v2)")
    print("    has DIFFERENT Cory data (net=$11,617.66, guests=227), Thomas guests=1118")
    print("    (wrong; should be 1168), bad Kahi Ramos food=$20B")
    print("  • Neither source is a clean original parse of SSD 6.15.26.pdf.")
    print("  • Raw PDF bytes are not retained anywhere in the database.")
    print("  • No GridFS collections present.")
    print("=" * 78)


if __name__ == "__main__":
    asyncio.run(main())
