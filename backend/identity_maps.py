"""
identity_maps.py — pure-data identity constants. LOAD-BEARING.

⚠️  Q2_ALIAS_OVERRIDE below is THE identity-resolution map used by merge /
   dedup / snapshot row joining. A single edit to any variant — a typo,
   a reorder, a removed alias — silently changes how rows are deduped and
   which canonicals collapse together. Treat any change to a variant list
   as a behavior change, NOT a cosmetic change. The guard assertion at
   the bottom of this file ONLY checks DISPLAY_NICKNAMES keys; it does
   NOT validate variant lists.

This module contains ONLY constants and a guard assertion. It executes
no app logic, opens no DB connections, reads no files. It is safe to
import from anywhere — routes, scripts, tests, ad-hoc consoles — with
zero side effects.

Source of truth for:
  • Q2_ALIAS_OVERRIDE  — legal_name -> [variants treated as the same person].
                         Identity-resolution. NOT display-only.
  • DISPLAY_NICKNAMES  — legal_name -> preferred display nickname.
                         Render-boundary only.
  • ALIAS_DISPLAY_MAP  — alias of DISPLAY_NICKNAMES; public name used at
                         render sites.

Nicknames are listed EXPLICITLY. They are NOT computed from
Q2_ALIAS_OVERRIDE via any heuristic (no min(..., key=len), no first-word,
no last-element-of-list). If a legal name in DISPLAY_NICKNAMES is
misspelled it WILL fail at import — the assertion below asserts every
DISPLAY_NICKNAMES key also exists as a legal-name key in
Q2_ALIAS_OVERRIDE.
"""

from typing import Dict, List


# ---------------------------------------------------------------------------
# Q2_ALIAS_OVERRIDE — LOAD-BEARING identity-resolution map.
#
# The 10 lines below were moved here byte-for-byte from
# scripts/stage_q2_rebuild.py (lines 56..65). Do not "tidy" them.
# Format: legal_name -> [variants treated as the same person]
# ---------------------------------------------------------------------------
Q2_ALIAS_OVERRIDE: Dict[str, List[str]] = {
    "Kahiaulani Ramos":  ["Kahiaulanl Ramos", "Kahiauani Ramos", "Kahi Ramos", "Kahi"],
    "Glennice Nguyen":   ["Glennlce Nguyen",  "Lennie Nguyen",   "Lennie"],
    "Thomas Kozan":      ["TK Kozan",         "TK"],
    "Lakeisha Martin":   ["Keisha Martin",    "Keisha"],
    "Abigail Ostrowski": ["Abby Ostrowski",   "Abby"],
    "Treyanna Quick":    ["Trey Quick",       "Trey"],
    "Eric Ostgarden":    ["Ikey Ostgarden",   "Ikey"],
    "Craig Simmons":     ["Allen Simmons",    "Allen"],
}


# ---------------------------------------------------------------------------
# Render-boundary map (legal name -> preferred display nickname).
# Explicit. No heuristic. Fallback at call-sites is the legal name itself.
# ---------------------------------------------------------------------------
DISPLAY_NICKNAMES: Dict[str, str] = {
    "Kahiaulani Ramos":  "Kahi",
    "Glennice Nguyen":   "Lennie",
    "Thomas Kozan":      "TK",
    "Lakeisha Martin":   "Keisha",
    "Abigail Ostrowski": "Abby",
    "Treyanna Quick":    "Trey",
    "Eric Ostgarden":    "Ikey",
    "Craig Simmons":     "Allen",
}

# Public name used at render sites (snapshot_routes, slide generators, etc.)
ALIAS_DISPLAY_MAP: Dict[str, str] = DISPLAY_NICKNAMES


# ---------------------------------------------------------------------------
# Guard: every DISPLAY_NICKNAMES key must also be a legal-name key in
# Q2_ALIAS_OVERRIDE. Catches typos at import — never silently fall through
# to a "legal-name fallback" because someone misspelled the key here.
# NOTE: this guard does NOT validate the variant lists in Q2_ALIAS_OVERRIDE.
# ---------------------------------------------------------------------------
_unknown_legals = [
    legal for legal in DISPLAY_NICKNAMES
    if legal not in Q2_ALIAS_OVERRIDE
]
assert not _unknown_legals, (
    "identity_maps: DISPLAY_NICKNAMES has keys that are NOT legal-name keys "
    "of Q2_ALIAS_OVERRIDE — likely a typo. Offenders: "
    + ", ".join(repr(n) for n in _unknown_legals)
)
del _unknown_legals
