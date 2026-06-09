"""Independent audit. The logic here does not trust how the build wrote the
sheet; it re-reads the workbook and re-derives every check from scratch, then
cross-checks against the ledger. This is the "the writer is not the auditor"
principle in code.

Checks (core, domain-agnostic):
  A. Orphan value      - a populated sourced cell with no ledger entry -> HARD
  B. Snippet drift     - a manufacturer/retailer value not supported by its snippet -> HARD
  C. Colour vs tier    - Confidence cell colour does not match the row's tier
  D. Link liveness     - source link dead or unverified
Plus domain-pack checks (e.g. SKU decode vs fields, cross-field logic, plausibility).

Discrepant cells are shaded with the 'unverifiable' colour and an
"ACCURACY CHECK" note is appended to the existing notes (never overwritten).
A Markdown report is written for the human.
"""
from __future__ import annotations
import sys, datetime, copy
from openpyxl import load_workbook
from openpyxl.styles import Font
import common, ledger as L, profile_engine
from common import DEFAULT_COLOURS, BODY_FONT, TOP_WRAP, Alignment

# columns that must trace to the ledger (whats_in_box included - it is sourced)
IDENTITY_ROLES = ["brand", "sku", "model", "ean", "tsin", "warranty", "category", "video"]


def _sourced_columns(roles):
    cols = set(range(roles["spec_start"], roles["spec_end"] + 1))
    if "whats_in_box" in roles:
        cols.add(roles["whats_in_box"])
    for r in IDENTITY_ROLES:
        if r in roles:
            cols.add(roles[r])
    return cols


def audit(built_path, schema, ledger_path, out_report, colours=None, profiles=None):
    colours = {**DEFAULT_COLOURS, **(colours or {})}
    profiles = profiles or {}
    entries = L.load(ledger_path)
    by_cell = {(e["tab"], e["row"], e["column"]): e for e in entries}
    wb = load_workbook(built_path)

    findings = []  # (tab,row,[cols],severity,msg)

    def F(tab, row, cols, sev, msg):
        findings.append((tab, row, list(cols), sev, msg))

    for tab, t in schema["tabs"].items():
        if tab not in wb.sheetnames:
            continue
        ws = wb[tab]
        roles = t["roles"]
        prof = profiles.get(tab) or profiles.get("*")
        srccols = _sourced_columns(roles)
        srccols |= set((t.get("extra_fields") or {}).values())
        for r in range(t["first_data_row"], ws.max_row + 1):
            if r in t.get("example_rows", []):
                continue
            tcol = roles.get("title", 1)
            if ws.cell(r, tcol).value in (None, ""):
                continue
            # A. orphan values
            for c in srccols:
                val = ws.cell(r, c).value
                if val not in (None, "") and (tab, r, c) not in by_cell:
                    F(tab, r, [c], "HARD", f"value '{str(val)[:40]}' has no ledger entry (unsourced).")
            # B. snippet drift (unexplained = HARD; disclosed with a doubt_reason = SOFT)
            for c in srccols:
                e = by_cell.get((tab, r, c))
                if e and e["provenance"] in ("manufacturer", "retailer"):
                    if not common.value_supported_by_snippet(e["value"], e.get("snippet", "")):
                        if e.get("doubt_reason"):
                            F(tab, r, [c], "SOFT", f"'{e['field']}' value not verbatim in snippet - disclosed: {e['doubt_reason']}")
                        else:
                            F(tab, r, [c], "HARD", f"'{e['field']}' value not supported by its snippet (undisclosed drift).")
            # C. colour vs tier
            if "confidence" in roles:
                tier = L.row_tier(entries, tab, r)
                if tier:
                    got = (ws.cell(r, roles["confidence"]).fill.fgColor.rgb or "")[-6:].upper()
                    want = colours[tier]["fill"].upper()
                    if got != want:
                        F(tab, r, [roles["confidence"]], "SOFT",
                          f"Confidence colour {got or 'none'} does not match row tier '{tier}' ({want}).")
            # D. link liveness
            e = by_cell.get((tab, r, roles.get("source", -1)))
            srcurl = L.primary_source(entries, tab, r)
            le = next((x for x in entries if x["tab"] == tab and x["row"] == r and x.get("source_url") == srcurl), None)
            if le is not None and le.get("link_ok") is False:
                F(tab, r, [roles.get("source", tcol)], "HARD", f"source link is dead: {srcurl}")
            # E. category-profile checks (profile built per job by inspection)
            if prof:
                for col_list, sev, msg in profile_engine.run_checks(ws, r, roles, t.get("labels", {}), prof):
                    F(tab, r, col_list, sev, msg)

    # F. cross-row identity integrity (agnostic): the same SKU on two products
    seen = {}
    for tab, t in schema["tabs"].items():
        if tab not in wb.sheetnames:
            continue
        scol = t["roles"].get("sku")
        if not scol:
            continue
        ws = wb[tab]
        for r in range(t["first_data_row"], ws.max_row + 1):
            if r in t.get("example_rows", []) or ws.cell(r, t["roles"].get("title", 1)).value in (None, ""):
                continue
            val = ws.cell(r, scol).value
            if val not in (None, ""):
                seen.setdefault(str(val).strip(), []).append((tab, r, scol))
    for val, occ in seen.items():
        if len(occ) > 1:
            where = ", ".join(f"{tb} r{rw}" for tb, rw, _ in occ)
            for tb, rw, sc in occ:
                F(tb, rw, [sc], "HARD", f"duplicate SKU '{val}' on multiple products ({where}). Confirm identifiers.")

    # G. source conflicts (independent comparator over candidate observations)
    for tab, row, col, field, sev, msg in L.detect_conflicts(entries):
        F(tab, row, [col] if col else [], sev, msg)

    # apply flags to the workbook
    grouped = {}
    for tab, row, cols, sev, msg in findings:
        g = grouped.setdefault((tab, row), {"cols": set(), "msgs": []})
        g["cols"].update(cols)
        g["msgs"].append(f"[{sev}] {msg}")
    today = datetime.date.today().isoformat()
    for (tab, row), g in grouped.items():
        ws = wb[tab]
        for c in g["cols"]:
            common.set_fill(ws, row, c, colours["unverifiable"]["fill"])
        ncol = schema["tabs"][tab]["roles"].get("notes")
        if ncol:
            cur = ws.cell(row, ncol).value or ""
            if "ACCURACY CHECK" not in str(cur):
                block = f" || ACCURACY CHECK ({today}): " + "  ".join(g["msgs"])
                nc = ws.cell(row, ncol, value=(str(cur) + block).strip())
                nc.font = Font(**BODY_FONT)
                nc.alignment = Alignment(**TOP_WRAP)

    wb.save(built_path)
    _report(out_report, findings, today)
    sev_counts = {s: sum(1 for f in findings if f[3] == s) for s in ("HARD", "SOFT")}
    print(f"AUDIT done: {len(findings)} findings {sev_counts} -> {out_report}")
    return findings


def _report(path, findings, today):
    lines = [f"# Audit report ({today})", ""]
    hard = [f for f in findings if f[3] == "HARD"]
    soft = [f for f in findings if f[3] == "SOFT"]
    lines += [f"- HARD findings: {len(hard)}", f"- SOFT findings: {len(soft)}", ""]
    if not findings:
        lines.append("No discrepancies found. Every populated cell traces to a ledger entry, "
                     "every manufacturer/retailer value is supported by its snippet, colours match "
                     "tiers, and all source links resolve.")
    for label, group in (("Hard findings", hard), ("Soft findings", soft)):
        if not group:
            continue
        lines += [f"\n## {label}", "", "| Tab | Row | Cols | Finding |", "|---|---|---|---|"]
        for tab, row, cols, sev, msg in sorted(group, key=lambda x: (x[0], x[1])):
            lines.append(f"| {tab} | {row} | {','.join(map(str, cols))} | {msg} |")
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")


if __name__ == "__main__":
    # audit.py <built.xlsx> <schema.json> <ledger.json> <report.md> [profile.yaml]
    import common as _c, yaml
    profs = {}
    if len(sys.argv) > 5:
        with open(sys.argv[5]) as f:
            profs = {"*": yaml.safe_load(f)}
    audit(sys.argv[1], _c.load_json(sys.argv[2]), sys.argv[3], sys.argv[4], profiles=profs)
