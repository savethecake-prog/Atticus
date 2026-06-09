"""The evidence ledger is the single source of truth for what gets written.

A ledger is a list of entries, one per (tab, row, field). The build step writes
ONLY from the ledger; it never invents a value. This module defines the entry
shape and validates it. The cardinal rule it enforces: a manufacturer/retailer
value cannot exist without a source_url AND a snippet it was copied from.

Entry shape:
{
  "tab": "Fans", "row": 7, "field": "noise", "column": 10,
  "value": "26.8 dBA",
  "provenance": "manufacturer" | "retailer" | "client" | "derived",
  "source_url": "https://...",        # required for manufacturer/retailer
  "snippet": "Noise Level: 26.8 dBA", # required for manufacturer/retailer
  "note": "from client inventory",    # required for client/derived
  "captured_at": "2026-04-22",
  "link_ok": true | false | null,     # filled by linkcheck
  "candidates": [                      # OPTIONAL: every observation seen for this
    {"value": "120 g", "provenance": "manufacturer",
     "source_url": "https://...", "snippet": "Weight: 120 g"},
    {"value": "135 g", "provenance": "retailer",
     "source_url": "https://...", "snippet": "Weight 135g"}
  ]
}

When more than one source was consulted for a field, record each as a candidate
and set the top-level value/provenance/source_url/snippet to the CHOSEN one. The
comparator (detect_conflicts) then flags any disagreement before the value is
trusted. A field with a single observation needs no candidates list.
"""
from __future__ import annotations
import re
from common import TIERS, WEB_TIERS, value_supported_by_snippet, norm, load_json, save_json

REQUIRED = ("tab", "row", "field", "column", "value", "provenance")


def validate(entries):
    """Return a list of violation strings. Empty list = ledger is clean.

    Violations are hard: a non-clean ledger must not be built from.
    """
    v = []
    seen = {}
    for i, e in enumerate(entries):
        tag = f"entry#{i} ({e.get('tab')} r{e.get('row')} {e.get('field')})"
        for k in REQUIRED:
            if e.get(k) in (None, ""):
                v.append(f"{tag}: missing required field '{k}'")
        prov = e.get("provenance")
        if prov not in TIERS:
            v.append(f"{tag}: provenance '{prov}' not one of {TIERS}")
        if prov in WEB_TIERS:
            if not e.get("source_url"):
                v.append(f"{tag}: {prov} value has no source_url")
            if not e.get("snippet"):
                v.append(f"{tag}: {prov} value has no snippet")
            elif not value_supported_by_snippet(e.get("value"), e.get("snippet")) and not e.get("doubt_reason"):
                v.append(f"{tag}: value '{e.get('value')}' is not verbatim in its snippet. "
                         f"Do NOT drop it - add a 'doubt_reason' saying where the value comes from and why it "
                         f"may be false; it will be written, scored low, and disclosed for SALT to judge.")
        if prov in ("client", "derived") and not e.get("note"):
            v.append(f"{tag}: {prov} value should carry a 'note' explaining its origin")
        cands = e.get("candidates")
        if cands:
            cvals = set()
            for j, c in enumerate(cands):
                ctag = f"{tag} candidate#{j}"
                if c.get("value") in (None, ""):
                    v.append(f"{ctag}: missing value")
                cp = c.get("provenance")
                if cp not in TIERS:
                    v.append(f"{ctag}: provenance '{cp}' not one of {TIERS}")
                if cp in WEB_TIERS:
                    if not c.get("source_url"):
                        v.append(f"{ctag}: {cp} candidate has no source_url")
                    if not c.get("snippet"):
                        v.append(f"{ctag}: {cp} candidate has no snippet")
                    elif not value_supported_by_snippet(c.get("value"), c.get("snippet")) and not c.get("doubt_reason"):
                        v.append(f"{ctag}: candidate value '{c.get('value')}' is not verbatim in its snippet; "
                                 f"add a 'doubt_reason' rather than dropping it.")
                cvals.add(_vnorm(c.get("value")))
            if _vnorm(e.get("value")) not in cvals:
                v.append(f"{tag}: chosen value '{e.get('value')}' is not among its candidates")
        key = (e.get("tab"), e.get("row"), e.get("column"))
        if key in seen:
            v.append(f"{tag}: duplicate target cell, already written by entry#{seen[key]}")
        else:
            seen[key] = i
    return v


def _nums(s):
    return sorted(re.findall(r"\d+\.?\d*", str(s or "")))


def _vnorm(s):
    """Normalise a value for equality comparison: lowercase, alphanumerics only,
    so '120 g' == '120g' and '4-pin PWM' == '4 pin pwm', while genuinely
    different text still differs."""
    return re.sub(r"[^a-z0-9]", "", str(s or "").lower())


def detect_conflicts(entries):
    """Independent comparator over candidate observations. Returns a list of
    (tab, row, column, field, severity, message). It does not trust the chosen
    value; it recomputes agreement from the candidates.

    Policy:
      - chosen value not among the candidates                 -> HARD
      - chosen tier lower than a higher-tier candidate        -> HARD
      - same-tier candidates give different NUMBERS            -> HARD
      - numbers differ but a higher tier was chosen            -> SOFT (disclosed)
      - only wording differs (numbers agree or none)           -> SOFT
    """
    out = []
    AUTH = {"manufacturer": 2, "retailer": 1}

    def rank(c):
        return AUTH.get(c.get("provenance"), -1)

    for e in entries:
        cands = e.get("candidates") or []
        if len(cands) < 2:
            continue
        groups = {}
        for c in cands:
            groups.setdefault(_vnorm(c.get("value")), []).append(c)
        if len(groups) < 2:
            continue  # all observations agree after normalisation
        tab, row, col, field = e.get("tab"), e.get("row"), e.get("column"), e.get("field")
        desc = "; ".join(f"{c.get('provenance')}='{c.get('value')}' ({c.get('source_url') or c.get('note') or 'no ref'})" for c in cands)
        chosen = _vnorm(e.get("value"))
        if chosen not in groups:
            out.append((tab, row, col, field, "HARD", f"{field}: chosen value '{e.get('value')}' is not among the captured observations. {desc}"))
            continue
        best = max(cands, key=rank)
        chosen_cand = next((c for c in cands if _vnorm(c.get("value")) == chosen), None)
        numeric_conflict = len({tuple(_nums(c.get("value"))) for c in cands}) > 1 and any(_nums(c.get("value")) for c in cands)
        same_tier_num = any(
            len({tuple(_nums(c.get("value"))) for c in cands if c.get("provenance") == t}) > 1
            for t in WEB_TIERS
        )
        if chosen_cand and rank(chosen_cand) < rank(best):
            out.append((tab, row, col, field, "HARD", f"{field}: chose a {chosen_cand.get('provenance')} value over a higher-tier {best.get('provenance')} source. Justify or correct. {desc}"))
        elif numeric_conflict and same_tier_num:
            out.append((tab, row, col, field, "HARD", f"{field}: same-tier sources disagree on the number. Cannot auto-resolve. {desc}"))
        elif numeric_conflict:
            out.append((tab, row, col, field, "SOFT", f"{field}: sources give different numbers; chose '{e.get('value')}' (higher tier). {desc}"))
        else:
            out.append((tab, row, col, field, "SOFT", f"{field}: sources differ in wording (numbers agree or none); chose '{e.get('value')}'. {desc}"))
    return out


def row_tier(entries, tab, row):
    """The row's CONSERVATIVE tier for the Confidence colour: the weakest of the
    web-sourced tiers present (so a single retailer field makes the row orange).
    Client/derived fields do not downgrade a row; if a row has only those, the
    weakest of them is returned."""
    from common import tier_rank
    tiers = [e["provenance"] for e in entries if e["tab"] == tab and e["row"] == row]
    web = [t for t in tiers if t in ("manufacturer", "retailer")]
    pool = web if web else tiers
    return max(pool, key=tier_rank) if pool else None


def primary_source(entries, tab, row):
    """Best root-source URL for a row's source link.

    A dead link is never chosen while any non-dead link is available. Among
    non-dead links the manufacturer wins for authority; among the same tier a
    verified-live link beats an unverified (bot-gated) one. link_ok must already
    be set (the build liveness-checks before calling this)."""
    rows = [e for e in entries if e["tab"] == tab and e["row"] == row and e.get("source_url")]
    if not rows:
        return None
    tier = {"manufacturer": 2, "retailer": 1}

    def key(e):
        lo = e.get("link_ok")
        not_dead = 0 if lo is False else 1      # dead sinks below everything
        live_bonus = 1 if lo is True else 0     # verified-live beats unverified
        return (not_dead, tier.get(e.get("provenance"), 0), live_bonus)

    return max(rows, key=key)["source_url"]


def load(path):
    obj = load_json(path)
    return obj["entries"] if isinstance(obj, dict) else obj


def save(path, entries):
    save_json(path, {"entries": entries})
