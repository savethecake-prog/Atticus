"""Completeness gate: catch products that surface too few specs.

The core's other guards stop INVENTION (no unsourced values, no invented fields).
This guards the opposite, equally costly failure: a product written with far fewer
specs than it should carry, which starves the downstream generator and produces a
low-value listing. It found nothing before because the skill had no guard against
under-capture at all.

It is agnostic. The baseline is learned from the data itself - the richest sibling
product in the same tab - and, when the operator records it, the number of fields
the source spec table actually published (schema tab key 'source_field_count').
Nothing here knows what any specific product "should" have.
"""
from __future__ import annotations
from openpyxl import load_workbook

# columns that are identity, prose, or role plumbing - not spec attributes
IDROLE = ("title", "subtitle", "brand", "sku", "ean", "tsin", "barcode", "categor",
          "warrant", "what", "confidence", "concat", "check", "source", "accuracy",
          "root", "image", "price", "model code", "product code", "model number", "added-from")


def _is_example(t):
    return str(t or "").strip().lower().startswith("example")


def _spec_headers(ws):
    return {c: str(ws.cell(1, c).value or "") for c in range(1, ws.max_column + 1)
            if ws.cell(1, c).value and not any(k in str(ws.cell(1, c).value).lower() for k in IDROLE)}


def check(built_path, schema, ratio=0.6, floor=4, product_tabs=None):
    """Findings for thin rows and under-discovered tabs.

    A product row flags if its populated spec count is below ratio * the tab's
    richest row, or below an absolute floor. A tab flags if it set up far fewer
    spec columns than the source table published (when that count was recorded).
    """
    wb = load_workbook(built_path, read_only=True, data_only=True)
    tabs = product_tabs or [t for t in schema["tabs"] if t in wb.sheetnames]
    findings = []
    for tab in tabs:
        if tab not in wb.sheetnames:
            continue
        ws = wb[tab]
        spec_cols = _spec_headers(ws)
        rows = []
        for r in range(2, ws.max_row + 1):
            t = ws.cell(r, 1).value
            if t in (None, "") or _is_example(t):
                continue
            n = sum(1 for c in spec_cols if ws.cell(r, c).value not in (None, ""))
            rows.append((r, str(t), n))
        if not rows:
            continue
        richest = max(n for _, _, n in rows)
        src = schema["tabs"][tab].get("source_field_count") or 0
        # the expectation is the larger of the richest sibling and what the source
        # published; using the source count is what catches a whole batch being thin.
        baseline = max(richest, src)
        if baseline < floor:
            continue  # not a spec-bearing product tab (e.g. an instructions sheet)
        for r, t, n in rows:
            why = []
            if n < ratio * baseline:
                ref = "the source table" if src and src >= richest else f"the richest {tab} row"
                why.append(f"{n} specs vs {baseline} in {ref}")
            if n < floor:
                why.append(f"only {n} specs (floor {floor})")
            if why:
                findings.append({"tab": tab, "row": r, "product": t[:50],
                                 "spec_count": n, "severity": "SOFT", "why": "; ".join(why)})
        if src and len(spec_cols) < ratio * src:
            findings.append({"tab": tab, "row": None, "product": "(tab)",
                             "spec_count": len(spec_cols), "severity": "SOFT",
                             "why": f"{len(spec_cols)} spec columns set up vs {src} fields in the "
                                    f"source table - discovery likely incomplete; capture the full table"})
    wb.close()
    return findings


def summarise(findings):
    rows = [f for f in findings if f["row"]]
    tabsf = [f for f in findings if f["row"] is None]
    tabs = sorted({f["tab"] for f in rows})
    parts = []
    if rows:
        parts.append(f"{len(rows)} thin product rows across {len(tabs)} tab(s)")
    if tabsf:
        parts.append(f"{len(tabsf)} tab(s) under-discovered vs source")
    return "; ".join(parts) if parts else "no thin rows flagged"


if __name__ == "__main__":
    import sys, os, common
    jobdir = sys.argv[1] if len(sys.argv) > 1 else "."
    schema = common.load_json(os.path.join(jobdir, "schema.json"))
    f = check(os.path.join(jobdir, "out.xlsx"), schema)
    print("COMPLETENESS:", summarise(f))
    for x in f:
        loc = f"{x['tab']} row{x['row']}" if x["row"] else x["tab"]
        print(f"  - {loc}: {x['why']}")
