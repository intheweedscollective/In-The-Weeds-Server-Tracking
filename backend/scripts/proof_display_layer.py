"""
Proof script for the display-layer rollout. READ-ONLY.

Exercises both name-render boundaries on the LIVE Q2P6W2 snapshot:
  (1) _hydrate_snapshot_employees overlay — read time
  (2) freeze-site _resolve_legal_and_display equivalent — write time

Specifically uses the spellings that were leaking unmapped:
  Kahiaulanl Ramos, Glennlce Nguyen, Trey Quick  (raw POS variants)
plus the operator-requested control:
  Ethan Dever (no nickname; must fall back to legal name)
"""
import asyncio
import os
import sys
from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient

load_dotenv("/app/backend/.env")
sys.path.insert(0, "/app/backend")

from identity_maps import ALIAS_DISPLAY_MAP  # noqa: E402
from snapshot_routes import (  # noqa: E402
    _build_canonical_display_map,
    _hydrate_snapshot_employees,
)


async def main():
    db = AsyncIOMotorClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]

    print("=" * 96)
    print("FREEZE-SITE PROOF — raw POS spellings → canonical legal → nickname → frozen_display_name")
    print("=" * 96)

    canonical_display, _, _ = await _build_canonical_display_map(db)

    # Simulate freeze-time input: a `scored` emp dict whose `name` is the
    # raw POS spelling. This is exactly what merge_snapshot_data emits.
    cases = [
        # legal POS spelling -> expected nickname
        ("Kahiaulanl Ramos",  "Kahiaulani Ramos", "Kahi"),
        ("Glennlce Nguyen",   "Glennice Nguyen",  "Lennie"),
        ("Trey Quick",        "Treyanna Quick",   "Trey"),
        ("Thomas Kozan",      "Thomas Kozan",     "TK"),
        ("Ethan Dever",       "Ethan Dever",      "Ethan Dever"),  # unmapped — fallback to legal
    ]

    print(f"{'raw_pos_name':22}  {'canonical_legal':22}  {'nickname':12}  {'frozen_display_name':22}  {'frozen_report_name':22}  {'frozen_legal_name':22}")
    print("-" * 130)

    for raw, expected_legal, expected_nick in cases:
        # Mimic the freeze site exactly.
        scored = {"name": raw, "id": None}
        key = (raw or "").strip().lower()
        legal = (
            canonical_display.get(scored.get("id") or "")
            or canonical_display.get(key)
            or raw
        )
        nickname = ALIAS_DISPLAY_MAP.get(legal, legal)
        frozen_display_name = nickname
        frozen_report_name = legal
        frozen_legal_name = legal

        # Assertions to make any regression scream.
        assert legal == expected_legal, f"{raw}: legal {legal!r} != {expected_legal!r}"
        assert nickname == expected_nick, f"{raw}: nickname {nickname!r} != {expected_nick!r}"
        assert frozen_report_name == expected_legal
        assert frozen_legal_name == expected_legal

        print(f"{raw:22}  {legal:22}  {nickname:12}  {frozen_display_name:22}  {frozen_report_name:22}  {frozen_legal_name:22}")

    print()
    print("=" * 96)
    print("HYDRATOR (READ TIME) PROOF — Q2P6W2 live snapshot rendered through _hydrate_snapshot_employees")
    print("=" * 96)
    live = await db.snapshot_workflow.find_one({"name": "Q2P6W2"})
    hyd = await _hydrate_snapshot_employees(db, live)
    by_name = {(e.get("name") or "").lower().strip(): e for e in hyd}

    targets = ["Thomas Kozan", "Ethan Dever", "Lakeisha Martin", "Kahiaulani Ramos",
               "Glennice Nguyen", "Treyanna Quick", "Bruce Diesel Rabago"]
    print(f"{'emp.name (legal)':22}  {'emp.legal_name':22}  {'emp.display_name':12}  card renders → {'getDisplayFirstName':22}")
    print("-" * 110)
    for t in targets:
        e = by_name.get(t.lower())
        if not e:
            print(f"  {t:22}  (MISSING)")
            continue
        # Replicate frontend getDisplayFirstName logic
        first_word = (e.get("display_name") or e.get("name") or "Unknown").strip().split()[0]
        print(f"  {e.get('name',''):22}  {e.get('legal_name',''):22}  {e.get('display_name',''):12}  "
              f"               → {first_word}")
    print()


asyncio.run(main())
