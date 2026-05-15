"""
Run the EmployeeValidator suite and print a human-readable report.

Usage:
    python scripts/run_validation_suite.py            # full report
    python scripts/run_validation_suite.py --json     # raw JSON
    python scripts/run_validation_suite.py --gate     # exit 1 on P0 issues
"""

from __future__ import annotations

import asyncio
import json
import os
import sys

from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.validation_service import EmployeeValidator


def _section(title: str, items, *, severity: str = ""):
    sev = f" [{severity}]" if severity else ""
    print(f"\n{title}{sev} — {len(items)} issue(s)")
    if not items:
        print("  ✓ clean")
        return
    for it in items[:10]:
        print(f"  - {it}")
    if len(items) > 10:
        print(f"  …and {len(items) - 10} more")


async def main() -> int:
    load_dotenv()
    client = AsyncIOMotorClient(os.environ["MONGO_URL"])
    db = client[os.environ.get("DB_NAME", "staff_score_db")]

    v = EmployeeValidator(db)
    report = await v.run_all()

    if "--json" in sys.argv:
        print(json.dumps(report, indent=2, default=str))
        client.close()
        return 0

    print("=" * 70)
    print("Employee data-integrity report")
    print("=" * 70)

    _section("[P0] duplicate_canonical_ids", report["duplicate_canonical_ids"], severity="P0")
    _section("[P0] orphaned_snapshot_refs", report["orphaned_snapshot_refs"], severity="P0")
    _section("[P0] employees_missing_id", report["employees_missing_id"], severity="P0")
    _section("[P0] blocklist_violations", report["blocklist_violations"], severity="P0")

    _section("[P1] duplicate_active_names", report["duplicate_active_names"], severity="P1")
    _section("[P1] inactive_in_current_snap", report["inactive_in_current_snap"], severity="P1")
    _section("[P1] metric_drift", report["metric_drift"], severity="P1")

    _section("[P2] legacy_only_employees", report["legacy_only_employees"], severity="P2")
    _section("[P2] snapshot_only_employees", report["snapshot_only_employees"], severity="P2")

    print("\n" + "=" * 70)
    summary = report["summary"]
    print(
        f"Summary  →  P0: {summary['p0_issues']}  |  "
        f"P1: {summary['p1_issues']}  |  P2: {summary['p2_issues']}"
    )
    print(f"Deploy gate: {summary['deploy_gate']}")
    print("=" * 70)

    client.close()

    if "--gate" in sys.argv and summary["deploy_gate"] != "PASS":
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
