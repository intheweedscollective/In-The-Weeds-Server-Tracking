"""
Canonical Employee model — single source of truth for employee identity.

Replaces the dual-source architecture (`employees_v2` + embedded
`snapshot.employees`) that caused months of drift / ghost employee bugs.

Identity Rules
--------------
- `id` is a UUID4 string and is **immutable**. It never changes for the
  lifetime of an employee, even across renames, role changes, merges, or
  store transfers.
- `name` is the canonical full name (used for matching during POS / CV /
  RT uploads). It MAY change (legal name change, marriage, typo fix).
- `display_name` is what shows on slides / leaderboards (per the
  First-Name-Only display policy). MAY change.
- `report_name` is how the employee appears in POS export rows
  (sometimes "Last, First", sometimes "First Last"). MAY change.
- `aliases` is the union of every historical name + nickname seen for
  this employee, used by the parser to find the canonical id without
  creating a duplicate.

Lifecycle
---------
- `status="active"` — appears in current rankings, slides, exports.
- `status="terminated"` — soft-deleted. NOT in current rankings or
  current slides. STILL appears on historical snapshots they were part
  of (so quarterly reviews don't lose data).
- `status="merged"` — was a duplicate; the row points to `merged_into`
  which holds the surviving canonical id. Kept around for audit only.

Snapshot Linkage
----------------
Snapshots store `{employee_id, frozen_display_name, frozen_metrics}` —
they NEVER embed the whole employee object. Historical slides render
with `frozen_display_name` so old slides keep their original wording
even after a rename.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field, ConfigDict
import uuid


EmployeeStatus = Literal["active", "terminated", "merged"]


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class EmployeeCurrentMetrics(BaseModel):
    """Denormalized 'current quarter' metrics for fast reads.

    NOT the source of truth for historical data — snapshots are. This is
    only used to power the live `/employees` and ranking views where you
    want a quick lookup of where an employee stands *right now* without
    joining against the latest snapshot.
    """
    model_config = ConfigDict(extra="allow")

    quarter: Optional[str] = None
    year: Optional[int] = None

    # POS metrics
    guests: float = 0.0
    guest_count: float = 0.0
    net_sales: float = 0.0
    ppa: float = 0.0
    liquor_sales: float = 0.0
    beer_sales: float = 0.0
    wine_sales: float = 0.0
    food_sales: float = 0.0
    lbw: float = 0.0
    lbw_per_guest: float = 0.0
    glassware_sales: float = 0.0
    bar_glassware_sales: float = 0.0
    glassware_per_guest: float = 0.0
    loyalty_sales: float = 0.0
    lsc_count: int = 0
    guests_per_lsc: float = 0.0

    # CV / NPS
    cv_promoters: int = 0
    cv_passives: int = 0
    cv_detractors: int = 0
    cv_responses: int = 0
    cv_avg_rating: float = 0.0
    cv_score: float = 0.0
    nps_score: float = 0.0

    # Review Tracker
    rt_mentions: int = 0
    review_mentions: int = 0
    review_tracker_bonus: float = 0.0

    # Scoring outputs
    score_ppa: float = 0.0
    score_lbw: float = 0.0
    score_glass: float = 0.0
    score_lsc: float = 0.0
    bonus_ppa: float = 0.0
    bonus_lbw: float = 0.0
    bonus_glass: float = 0.0
    bonus_lsc: float = 0.0
    total_metric_bonus: float = 0.0
    weighted_score: float = 0.0
    pre_dar_score: float = 0.0
    dar_penalty: float = 0.0
    total_score: float = 0.0
    performance_tier: Optional[str] = None
    peer_rank: Optional[int] = None


class Employee(BaseModel):
    """Canonical employee record. One per real-world person, forever."""
    model_config = ConfigDict(extra="allow", populate_by_name=True)

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    name: str
    display_name: Optional[str] = None
    report_name: Optional[str] = None
    aliases: List[str] = Field(default_factory=list)

    job_title: str = "Server"
    status: EmployeeStatus = "active"
    merged_into: Optional[str] = None  # id of surviving record if status="merged"

    # Multi-store hook — stays None for single-store apps.
    store_id: Optional[str] = None

    current_metrics: EmployeeCurrentMetrics = Field(default_factory=EmployeeCurrentMetrics)

    created_at: str = Field(default_factory=_now_iso)
    updated_at: str = Field(default_factory=_now_iso)
    terminated_at: Optional[str] = None
    merged_at: Optional[str] = None

    def to_mongo(self) -> Dict[str, Any]:
        """Dict suitable for MongoDB insertion. Strips no fields by default."""
        return self.model_dump(mode="json")


class SnapshotEmployeeRow(BaseModel):
    """A snapshot's reference to a canonical Employee at a point in time.

    Stored inside `snapshots_v3.rows[]`. Holds an immutable FK plus the
    frozen display values + frozen scoring metrics for that quarter.
    """
    model_config = ConfigDict(extra="allow")

    employee_id: str
    frozen_display_name: str
    frozen_report_name: Optional[str] = None
    frozen_metrics: Dict[str, Any] = Field(default_factory=dict)
    frozen_score: float = 0.0
    frozen_tier: Optional[str] = None
    frozen_rank: Optional[int] = None
    recorded_at: str = Field(default_factory=_now_iso)


__all__ = [
    "Employee",
    "EmployeeStatus",
    "EmployeeCurrentMetrics",
    "SnapshotEmployeeRow",
]
