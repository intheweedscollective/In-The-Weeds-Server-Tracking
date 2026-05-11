"""
One-shot: sync every employee in the current Q2 2026 snapshot back into
employees_v2 so the slide / printable / rankings pages stop showing zeros
for employees whose data only lives on the snapshot.

Reads MONGO_URL / DB_NAME from environment. Verifies before + after.
"""

import asyncio
import os
import re as _re
from datetime import datetime, timezone

from motor.motor_asyncio import AsyncIOMotorClient


SYNC_FIELDS = (
    # POS metrics
    "guest_count", "guests", "net_sales", "ppa",
    "lbw", "lbw_per_guest",
    "glassware_sales", "bar_glassware_sales", "glassware_per_guest",
    "lsc_count", "loyalty_sales", "guests_per_lsc",
    "food_sales", "liquor_sales", "beer_sales", "wine_sales",
    # CV / NPS
    "cv_promoters", "cv_passives", "cv_detractors",
    "cv_score", "cv_responses", "cv_avg_rating", "cv_raw_points",
    "nps_score", "nps_score_pts", "nps_contribution",
    # Review Tracker
    "rt_mentions", "review_mentions", "review_tracker_bonus",
    # Calculated scores / tier
    "score_ppa", "score_lbw", "score_glass", "score_lsc",
    "bonus_ppa", "bonus_lbw", "bonus_glass", "bonus_lsc",
    "total_metric_bonus", "metric_bonus",
    "weighted_score", "pre_dar_score", "total_score",
    "performance_tier", "peer_rank",
    "display_name", "report_name", "job_title",
)


async def main():
    client = AsyncIOMotorClient(os.environ["MONGO_URL"])
    db = client[os.environ.get("DB_NAME", "staff_score_db")]

    quarter = "Q2"
    year = 2026

    snap = await db.snapshot_workflow.find_one(
        {"is_current": True, "quarter": quarter, "year": year}
    )
    if not snap:
        snap = await db.snapshot_workflow.find_one(
            {"status": "completed", "quarter": quarter, "year": year},
            sort=[("completed_at", -1)],
        )
    if not snap:
        print(f"No snapshot found for {quarter} {year}")
        return

    print(f"Source snapshot: {snap.get('name')} | {snap.get('employee_count', len(snap.get('employees', [])))} employees")

    employees = snap.get("employees", []) or []
    if not employees:
        print("Snapshot has no employees — nothing to sync.")
        return

    # BEFORE: how many V2 rows have zero CV / RT for this quarter?
    zero_cv = await db.employees_v2.count_documents(
        {"year": year, "quarter": quarter, "cv_score": {"$in": [0, 0.0, None]}}
    )
    zero_rt = await db.employees_v2.count_documents(
        {"year": year, "quarter": quarter, "rt_mentions": {"$in": [0, None]}}
    )
    print(f"[BEFORE] employees_v2 rows with cv_score=0: {zero_cv}, rt_mentions=0: {zero_rt}")

    synced = 0
    for emp in employees:
        name = (emp.get("name") or emp.get("display_name") or "").strip()
        if not name:
            continue

        update = {k: emp[k] for k in SYNC_FIELDS if k in emp and emp[k] is not None}
        update["quarter"] = quarter
        update["year"] = year
        update["updated_at"] = datetime.now(timezone.utc).isoformat()

        # Prefer match by id, fall back to case-insensitive name + quarter + year.
        emp_id = emp.get("id")
        matched = False
        if emp_id:
            r = await db.employees_v2.update_one({"id": emp_id}, {"$set": update})
            if r.matched_count:
                matched = True

        if not matched:
            r = await db.employees_v2.update_one(
                {
                    "name": {"$regex": f"^{_re.escape(name)}$", "$options": "i"},
                    "quarter": quarter,
                    "year": year,
                },
                {"$set": update, "$setOnInsert": {"id": emp_id or "", "name": name}},
                upsert=True,
            )
            matched = bool(r.matched_count or r.upserted_id)

        if matched:
            synced += 1

    print(f"Synced {synced} / {len(employees)} employees back into employees_v2.")

    # AFTER: same zero-count check.
    zero_cv2 = await db.employees_v2.count_documents(
        {"year": year, "quarter": quarter, "cv_score": {"$in": [0, 0.0, None]}}
    )
    zero_rt2 = await db.employees_v2.count_documents(
        {"year": year, "quarter": quarter, "rt_mentions": {"$in": [0, None]}}
    )
    print(f"[AFTER]  employees_v2 rows with cv_score=0: {zero_cv2}, rt_mentions=0: {zero_rt2}")

    # Spot check: a few names the user flagged
    print()
    for check in ["Diane Peterson", "Matt Spath", "Starwars Mckinnon-Herrera", "Julian Taveras"]:
        v2 = await db.employees_v2.find_one(
            {"name": {"$regex": f"^{_re.escape(check)}$", "$options": "i"}, "year": year, "quarter": quarter},
            {"_id": 0, "name": 1, "cv_score": 1, "rt_mentions": 1, "review_tracker_bonus": 1, "nps_score": 1},
        )
        if v2:
            print(f"  {v2.get('name'):28s} | nps={v2.get('nps_score')} cv={v2.get('cv_score')} rt={v2.get('rt_mentions')} rt_bonus={v2.get('review_tracker_bonus')}")

    client.close()


if __name__ == "__main__":
    asyncio.run(main())
