"""One runnable suite for the whole skill. Run it before trusting any new check,
decoder, or range:

    cd salt-input-builder && python tests/run_tests.py

It exits non-zero if anything fails. It consolidates the per-module guards and
runs the engine fixture cases in tests/fixtures/. Network-dependent link
calibration is covered offline here (the soft-404 detector); the live calibration
is exercised separately when a job runs.
"""
import os, sys, glob

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "scripts"))

import yaml
from openpyxl import Workbook
import profile_engine, profile_builder, ledger, linkcheck

PASS, FAIL = [], []


def check(name, cond, detail=""):
    (PASS if cond else FAIL).append(name + (f"  [{detail}]" if detail and not cond else ""))


def _sheet(roles, labels, row):
    wb = Workbook(); ws = wb.active
    for c, v in row.items():
        ws.cell(1, int(c), v)
    return ws


# --- engine fixture cases ---------------------------------------------------
def test_engine_fixtures():
    for path in sorted(glob.glob(os.path.join(HERE, "fixtures", "*.yaml"))):
        for case in yaml.safe_load(open(path)):
            roles = {k: int(v) if str(v).isdigit() else v for k, v in case["roles"].items()}
            ws = _sheet(roles, case.get("labels", {}), {int(k): v for k, v in case["row"].items()})
            found = profile_engine.run_checks(ws, 1, roles, case.get("labels", {}), case["profile"])
            exp = case.get("expect", [])
            ok = len(found) == len(exp) and all(
                any(e["sev"] == sev and e["contains"] in msg for _, sev, msg in found) for e in exp
            )
            check(f"engine fixture: {case['name']}", ok, f"got {[(s, m) for _, s, m in found]}")


# --- engine number-parsing guard --------------------------------------------
def test_engine_guards():
    check("engine: tolerance (+-10%) ignored", profile_engine._nums("Up to 2000 RPM (+-10%)") == [2000.0])
    check("engine: range min/max kept", profile_engine._nums("400 (+-200) - 1200 RPM (+-10%)") == [400.0, 1200.0])


# --- conflict comparator branches -------------------------------------------
def test_conflicts():
    man = lambda v: {"value": v, "provenance": "manufacturer", "source_url": "https://m", "snippet": v}
    ret = lambda v, u="https://s": {"value": v, "provenance": "retailer", "source_url": u, "snippet": v}
    E = lambda val, cands, prov="manufacturer": {"tab": "T", "row": 2, "field": "f", "column": 5,
                                                  "value": val, "provenance": prov, "source_url": "https://m",
                                                  "snippet": val, "candidates": cands}
    sev = lambda e: (ledger.detect_conflicts([e]) or [(0, 0, 0, 0, None)])[0][4]
    check("conflict: same-tier numbers disagree -> HARD", sev(E("135 g", [ret("135 g", "https://a"), ret("120 g", "https://b")], "retailer")) == "HARD")
    check("conflict: cross-tier, chose manufacturer -> SOFT", sev(E("120 g", [man("120 g"), ret("135 g")])) == "SOFT")
    check("conflict: chose lower tier -> HARD", sev(E("135 g", [man("120 g"), ret("135 g")], "retailer")) == "HARD")
    check("conflict: wording-only differs -> SOFT", sev(E("HDB", [man("HDB"), ret("hydro dynamic")])) == "SOFT")
    check("conflict: agree after norm -> none", sev(E("120 g", [man("120 g"), ret("120g")])) is None)


# --- ledger validation of candidates ----------------------------------------
def test_ledger_validate():
    man = lambda v, s: {"value": v, "provenance": "manufacturer", "source_url": "https://m", "snippet": s}
    bad_choice = {"tab": "T", "row": 2, "field": "f", "column": 5, "value": "999",
                  "provenance": "manufacturer", "source_url": "https://m", "snippet": "999",
                  "candidates": [man("120", "120"), man("135", "135")]}
    check("validate: chosen not among candidates caught",
          any("not among its candidates" in v for v in ledger.validate([bad_choice])))
    bad_snip = {"tab": "T", "row": 2, "field": "f", "column": 5, "value": "120",
                "provenance": "manufacturer", "source_url": "https://m", "snippet": "heavy",
                "candidates": [man("120", "weight is heavy")]}
    check("validate: non-verbatim value without a doubt_reason is caught",
          any("not verbatim" in v for v in ledger.validate([bad_snip])))
    # the key new behaviour: a doubt_reason lets an existing-but-unverbatim value through
    disputed = {"tab": "T", "row": 3, "field": "tc", "column": 6, "value": "12.5 W/mK",
                "provenance": "manufacturer", "source_url": "https://m",
                "snippet": "thermal paste for high-end CPUs",
                "doubt_reason": "long-published figure; not on the current manufacturer datasheet - confirm or remove"}
    check("validate: doubt_reason lets a non-verbatim value through (no omission)",
          ledger.validate([disputed]) == [])
    import confidence as C
    s, r = C.score_entry(disputed)
    check("confidence: disputed value scored low and carries its doubt reason",
          s == 30 and "current manufacturer datasheet" in r and not C.eligible(disputed))


# --- profile builder inference ----------------------------------------------
def test_profile_builder():
    products = [
        {"family": "SC140", "sku": "3MSC14FA1.0001", "attrs": {"blade": "forward", "colour": "black"}},
        {"family": "SC140", "sku": "3MSC14RA1.0001", "attrs": {"blade": "reverse", "colour": "black"}},
        {"family": "SC140", "sku": "3MSC14FA1.0002", "attrs": {"blade": "forward", "colour": "white"}},
        {"family": "SC140", "sku": "3MSC14RA1.0002", "attrs": {"blade": "reverse", "colour": "white"}},
        {"family": "Unity", "sku": "3MUN24FA1.0001", "attrs": {"size": "240", "blade": "forward", "colour": "black"}},
        {"family": "Unity", "sku": "3MUN36RA1.0002", "attrs": {"size": "360", "blade": "reverse", "colour": "white"}},
    ]
    prof, _ = profile_builder.build_profile("fans", "Cougar", {"5": "Product colour"}, products)
    names = {d["name"] for d in prof["decoders"]}
    sc = next((d for d in prof["decoders"] if d["name"] == "SC140"), None)
    check("builder: SC140 decoder inferred", sc is not None)
    check("builder: SC140 blade map correct", bool(sc) and sc.get("blade_map") == {"F": "forward", "R": "reverse"})
    check("builder: SC140 suffix colour correct", bool(sc) and sc.get("suffix_colour") == {"1": "black", "2": "white"})
    check("builder: confounded Unity NOT guessed", "Unity" not in names)
    import re as _re
    check("builder: inferred regex matches its own SKUs",
          bool(sc) and all(_re.search(sc["sku_regex"], p["sku"]) for p in products if p["family"] == "SC140"))


# --- linkcheck soft-404 (offline) -------------------------------------------
def test_linkcheck_offline():
    notfound = "<html><head><title>404 Not Found</title></head><body>gone</body></html>"
    normal = "<html><head><title>Apolar 120 ARGB Fan</title></head><body>specs...</body></html>"
    check("linkcheck: soft-404 title detected", linkcheck._looks_like_404(notfound) is True)
    check("linkcheck: normal page not a 404", linkcheck._looks_like_404(normal) is False)


# --- duplicate identifier across rows (agnostic core audit) -----------------
def test_duplicate_sku():
    import audit
    wb = Workbook(); ws = wb.active; ws.title = "Fans"
    for c, h in {1: "Title", 2: "Spec", 3: "SKU"}.items():
        ws.cell(1, c, h)
    ws.cell(2, 1, "A"); ws.cell(2, 3, "DUP-1")
    ws.cell(3, 1, "B"); ws.cell(3, 3, "DUP-1")
    os.makedirs("/tmp/th", exist_ok=True); wb.save("/tmp/th/wb.xlsx")
    schema = {"tabs": {"Fans": {"roles": {"title": 1, "spec_start": 2, "spec_end": 2, "sku": 3},
                                "labels": {}, "header_row": 1, "first_data_row": 2, "example_rows": []}}}
    ledger.save("/tmp/th/led.json", [])
    findings = audit.audit("/tmp/th/wb.xlsx", schema, "/tmp/th/led.json", "/tmp/th/rep.md", profiles={})
    check("audit: duplicate SKU across products flagged",
          any("duplicate SKU" in m for *_, m in findings))


def test_jobspec():
    import jobspec
    good = {"job": {"name": "B1", "template": "t.xlsx", "output_dir": "out"},
            "source_policy": {"tier_order": ["manufacturer", "retailer"]},
            "authority": {"infer_brand_domain": True},
            "confidence_colours": {"manufacturer": {"fill": "C6EFCE", "font": "006100"}},
            "category_profiles": {"Fans": "profiles/fans.yaml"},
            "gates": {"mode": "adaptive"}, "deliverables": ["workbook"],
            "items": [{"tab": "Fans", "client_fields": {"sku": "X-1"}}]}
    check("jobspec: valid spec passes", jobspec.is_valid(good))
    bad = {"job": {}, "source_policy": {"tier_order": ["wholesaler"]},
           "gates": {"mode": "nope"}, "category_profiles": [], "items": "nope"}
    check("jobspec: malformed spec rejected", not jobspec.is_valid(bad))


def test_schema_store():
    import schema_store, tempfile
    d = tempfile.mkdtemp()
    schema_store.save(d, {"tabs": {"Fans": {"signature": "sig1", "roles": {"title": 1}, "labels": {}}}})
    check("schema_store: find by signature", bool(schema_store.find_by_signature(d, "sig1")))
    s2 = {"tabs": {"Fans": {"signature": "sig1"}, "Mobo": {"signature": "new"}}}
    n = schema_store.annotate(d, s2)
    check("schema_store: reuse on match, confirm on new",
          n == 1 and s2["tabs"]["Mobo"]["needs_confirmation"] and s2["tabs"]["Fans"]["reused"])


def test_runner():
    import runner
    schema = {"tabs": {"Fans": {"roles": {"title": 1, "spec_start": 2, "spec_end": 2, "sku": 3},
                                "labels": {}, "header_row": 1, "first_data_row": 2, "example_rows": []}}}
    ret = lambda v, u: {"value": v, "provenance": "retailer", "source_url": u, "snippet": v}
    entries = [{"tab": "Fans", "row": 2, "field": "noise", "column": 2, "value": "26 dBA",
                "provenance": "retailer", "source_url": "https://a", "snippet": "26 dBA",
                "candidates": [ret("26 dBA", "https://a"), ret("31 dBA", "https://b")]}]
    q = runner.needs_you(schema, entries)
    check("runner: needs_you surfaces hard conflict", any("conflict" in n for n in q))
    check("runner: delivery summary renders", "Delivery summary" in runner.delivery_summary(schema, entries))
    check("runner: status on empty dir -> contract phase", "contract" in runner.status("/tmp/no-such-job-xyz")["next"])


def test_primary_source():
    E = lambda prov, url, ok: {"tab": "T", "row": 2, "field": "f", "column": 3,
                               "value": "v", "provenance": prov, "source_url": url, "link_ok": ok}
    man = "https://maker"; ret = "https://shop"; az = "https://amazon"; ds = "https://mirror"
    # manufacturer live beats retailer live (authority)
    check("picker: manufacturer-live preferred",
          ledger.primary_source([E("manufacturer", man, True), E("retailer", ret, True)], "T", 2) == man)
    # the bug: manufacturer DEAD must lose to a live retailer
    check("picker: dead manufacturer loses to live retailer",
          ledger.primary_source([E("manufacturer", man, False), E("retailer", ret, True)], "T", 2) == ret)
    # unverified manufacturer still beats live retailer (only dead is demoted)
    check("picker: unverified manufacturer keeps authority over live retailer",
          ledger.primary_source([E("manufacturer", man, None), E("retailer", ret, True)], "T", 2) == man)
    # Aeronaut shape: amazon dead, mirror live, titanrig unverified -> live mirror
    check("picker: chooses the live link among retailers (Aeronaut case)",
          ledger.primary_source([E("retailer", az, False), E("retailer", ds, True), E("retailer", ret, None)], "T", 2) == ds)
    # all dead -> still returns the best-tier (flagged elsewhere)
    check("picker: all dead returns best tier",
          ledger.primary_source([E("retailer", ret, False), E("manufacturer", man, False)], "T", 2) == man)


def test_confidence():
    import confidence as C
    ret = lambda v, u: {"value": v, "provenance": "retailer", "source_url": u, "snippet": v}
    E = lambda val, prov, cands=None, url=None: {"value": val, "provenance": prov, "source_url": url, "snippet": val, "candidates": cands}
    check("confidence: manufacturer single = 90 and eligible",
          C.score_entry(E("x", "manufacturer", url="https://m"))[0] == 90 and C.eligible(E("x", "manufacturer", url="https://m")))
    check("confidence: single retailer = 40 and NOT eligible (2-source rule)",
          C.score_entry(E("x", "retailer", url="https://a"))[0] == 40 and not C.eligible(E("x", "retailer", url="https://a")))
    two = E("x", "retailer", cands=[ret("x", "https://a"), ret("x", "https://b")])
    check("confidence: two independent retailers = 70 and eligible", C.score_entry(two)[0] == 70 and C.eligible(two))
    same = E("x", "retailer", cands=[ret("x", "https://a/1"), ret("x", "https://a/2")])
    check("confidence: same host counts once (not eligible)", not C.eligible(same))
    dis = E("x", "retailer", cands=[ret("x", "https://a"), ret("y", "https://b")])
    check("confidence: disagreement = 35", C.score_entry(dis)[0] == 35)
    check("confidence: client identity = 85 and eligible",
          C.score_entry(E("TG-1", "client"))[0] == 85 and C.eligible(E("TG-1", "client")))
    check("confidence: bands map correctly (high/medium/low)",
          C.band(90) == "high" and C.band(70) == "medium" and C.band(40) == "low")
    check("confidence: single-source reason names the host",
          "a.com" in C.score_entry(E("x", "retailer", url="https://a.com"))[1])


def test_fields():
    import fields
    tab = {"roles": {"spec_start": 3, "spec_end": 25, "header_row": 1},
           "labels": {"3": "Electrical conductivity:", "4": "Supported application:", "5": "Components:",
                      "19": "Colour:", "20": "Operating temperature: "}}
    dec = {d["field"]: (d["action"], d["col"]) for d in fields.reconcile(tab,
           [{"field": "Electrical conductivity"}, {"field": "Thermal conductivity (W/mK)"},
            {"field": "Viscosity (Pa.s)"}, {"field": "Density (g/cm3)"}])}
    check("fields: known field maps to its existing column",
          dec["Electrical conductivity"] == ("existing", 3))
    check("fields: 'thermal conductivity' does NOT collide with 'electrical conductivity'",
          dec["Thermal conductivity (W/mK)"][0] == "relabel")
    check("fields: new fields fill blank spare columns in range",
          dec["Viscosity (Pa.s)"][0] == "relabel" and dec["Density (g/cm3)"][0] == "relabel")
    # exact vs non-identical existing match
    d2 = fields.reconcile(tab, [{"field": "Operating temperature"}, {"field": "Operating temperature (C)"}])
    by2 = {x["field"]: x for x in d2}
    check("fields: identical header match flagged exact",
          by2["Operating temperature"]["action"] == "existing" and by2["Operating temperature"]["exact"] is True)
    check("fields: non-identical header match still fills, marked not exact",
          by2["Operating temperature (C)"]["action"] == "existing" and by2["Operating temperature (C)"]["exact"] is False)


def test_hide_blank_columns():
    from openpyxl import Workbook
    import build
    wb = Workbook(); ws = wb.active
    ws.cell(1, 1, "Title"); ws.cell(2, 1, "P1"); ws.cell(3, 1, "P2")
    ws.cell(1, 3, "A"); ws.cell(1, 4, "B")
    ws.cell(2, 3, "value")  # col 3 has data, col 4 entirely blank
    t = {"roles": {"title": 1, "spec_start": 3, "spec_end": 4}, "header_row": 1}
    n = build._hide_blank_columns(ws, t)
    check("hide: one fully-blank column hidden", n == 1)
    check("hide: blank column hidden, populated column visible",
          ws.column_dimensions["D"].hidden and not ws.column_dimensions["C"].hidden)


def test_from_spec_table():
    import fields
    raw = "Power output: 750 W\nEfficiency: 80 Plus Gold\nModular: Fully modular\nFan: 120mm"
    out = fields.from_spec_table(raw)
    names = [d["field"] for d in out]
    check("from_spec_table: one field per row", len(out) == 4, str(names))
    check("from_spec_table: strips value", "Power output" in names)
    d = fields.from_spec_table({"Wattage": "750", "Fan": "120mm", "Wattage ": "dup"})
    check("from_spec_table: dedup by normalised label", len(d) == 2, str([x["field"] for x in d]))
    tab = fields.from_spec_table(["Length\t160mm", "Width\t150mm"])
    check("from_spec_table: tab-separated", [x["field"] for x in tab] == ["Length", "Width"])


def test_completeness():
    import completeness
    wb = Workbook()
    ws = wb.active; ws.title = "Fans"
    heads = ["Title", "Size", "Speed", "Airflow", "Noise", "Bearing", "Brand:", "SKU:"]
    for c, h in enumerate(heads, 1):
        ws.cell(1, c, h)
    # rich row: 5 specs; thin row: 1 spec
    ws.append(["Fan A", "120mm", "2000", "68 CFM", "28 dBA", "FDB", "Cougar", "SKU1"])
    ws.append(["Fan B", "120mm", None, None, None, None, "Cougar", "SKU2"])
    ws.append(["Example fan", "x", "y", "z", "w", "v", "Cougar", "SKU3"])  # ignored
    path = os.path.join(HERE, "_tmp_completeness.xlsx"); wb.save(path)
    schema = {"tabs": {"Fans": {}}}
    f = completeness.check(path, schema, ratio=0.6, floor=4)
    rows = {x["row"]: x for x in f if x["row"]}
    check("completeness: thin row flagged", 3 in rows, str(rows))
    check("completeness: rich row not flagged", 2 not in rows)
    check("completeness: example row ignored", all(x["product"] != "Example fan" for x in f))
    # source_field_count catches systemic thinness (rich row's 5 < ratio*10)
    schema["tabs"]["Fans"]["source_field_count"] = 10
    f2 = completeness.check(path, schema, ratio=0.6, floor=4)
    rows2 = {x["row"] for x in f2 if x["row"]}
    check("completeness: source count flags the rich row too", 2 in rows2, str(rows2))
    tabflag = [x for x in f2 if x["row"] is None]
    check("completeness: under-discovered tab flagged", len(tabflag) == 1, str(tabflag))
    os.remove(path)


# --- identity matching (Phase A: regression from the Infinity 2026-06-09 failures) ---
def test_match():
    import match
    T = [
        {"id": "OA40SBB", "brand": "Oppo", "sku": "OA40SBB", "barcode": "",
         "title": "Oppo A40 (Sparkle Black, 128 GB) (4 GB RAM)"},
        {"id": "OA40SBL", "brand": "Oppo", "sku": "OA40SBL", "barcode": "",
         "title": "Oppo A40 Starry Blue (Starry Purple, 128 GB) (4 GB RAM)"},
        {"id": "OR12FOG", "brand": "Oppo", "sku": "OR12FOG", "barcode": "",
         "title": "oppo Reno12 F 4G Dual Sim 256GB (Green, 256 GB) (8 GB RAM) +Free Oppo Jaua Watch"},
        {"id": "OR12FMG", "brand": "Oppo", "sku": "OR12FMG", "barcode": "",
         "title": "Oppo Reno12 F (Matte Grey, 256 GB) (8 GB RAM)+Free Oppo Jaua Watch"},
        {"id": "CPH2629", "brand": "Oppo", "sku": "CPH2629", "barcode": "",
         "title": "Oppo Reno12 Pro 5G (Space Brown, 512 GB) (12 GB RAM) +Free Oppo Jaua Watch"},
        {"id": "OR13BL", "brand": "Oppo", "sku": "OR13BL", "barcode": "",
         "title": "Oppo Reno 13 5G (Luminous Blue, 512 GB) (12 GB RAM)+Free Oppo Jaua Watch"},
        {"id": "AOPROG", "brand": "Oppo", "sku": "AOPROG", "barcode": "",
         "title": "Oppo A5 Pro (Olive Green, 256 GB) (8 GB RAM)"},
        {"id": "OA5MP", "brand": "Oppo", "sku": "OA5MP", "barcode": "",
         "title": "Oppo A5 (Midnight Purple, 256 GB) (8 GB RAM)"},
        {"id": "H72B", "brand": "Hisense", "sku": "H72B", "barcode": "",
         "title": "Hisense H72 with Free Bluetooth Speaker"},
        {"id": "H72BLL", "brand": "Hisense", "sku": "H72BLL", "barcode": "",
         "title": "Hisense H72 (Blue, 128 GB)"},
        {"id": "V30E", "brand": "Vivo", "sku": "6935117884578", "barcode": "6935117884578",
         "title": "vivo V30e (12 GB RAM)"},
    ]
    S = [
        {"id": "a40sb", "brand": "Oppo", "colour": "Sparkle Black", "storage": "128",
         "model": "Oppo A40 Sparkle Black 4GB RAM 128", "model_number": "CPH2669"},
        {"id": "a40sp", "brand": "Oppo", "colour": "Starry Purple", "storage": "128",
         "model": "Oppo A40 Starry Purple 4GB RAM 128", "model_number": "CPH2669"},
        {"id": "r12fog", "brand": "Oppo", "colour": "Olive Green", "storage": "256",
         "model": "Oppo Reno 12F Olive Green 8GB RAM 256", "model_number": "CPH2687"},
        {"id": "r12fmg", "brand": "Oppo", "colour": "Matte Gray", "storage": "256",
         "model": "Oppo Reno 12 F Matte Gray 8GB RAM 256", "model_number": "CPH2687"},
        {"id": "r12pro", "brand": "Oppo", "colour": "Space Brown", "storage": "512",
         "model": "Oppo Reno 12 PRO 5G 512GB 12GB Space Brown", "model_number": "CPH2629"},
        {"id": "r13", "brand": "Oppo", "colour": "Luminous Blue", "storage": "512",
         "model": "Oppo Reno 13 5G Luminous Blue 12GB 512", "model_number": "CPH2689"},
        {"id": "a5promb", "brand": "Oppo", "colour": "Mocha Brown", "storage": "256",
         "model": "Oppo A5 Pro Mocha Brown 8GB RAM 256", "model_number": "CPH2695"},
        {"id": "a5proog", "brand": "Oppo", "colour": "Olive Green", "storage": "256",
         "model": "OPPO A5 Pro Olive Green 8GB RAM 256", "model_number": "CPH2695"},
        {"id": "a5mp", "brand": "Oppo", "colour": "Midnight Purple", "storage": "256",
         "model": "OPPO A5 Midnight Purple 8GB RAM 256", "model_number": "CPH2727"},
        # two genuinely indistinguishable rows (same model, colour, storage) -> must abstain
        {"id": "h72a", "brand": "Hisense", "colour": "Blue", "storage": "128",
         "model": "Hisense H72 Blue", "model_number": "HLTE270E"},
        {"id": "h72b", "brand": "Hisense", "colour": "Blue", "storage": "128",
         "model": "Hisense H72 Blue", "model_number": "HLTE270E"},
        {"id": "v30e", "brand": "Vivo", "colour": "Green", "storage": "256",
         "model": "vivo V30e Green 12GB RAM 256", "barcode": "6935117884578", "model_number": "V2339"},
    ]
    res = {r["source_id"]: r for r in match.match(S, T)}
    want = {  # source -> expected SKU, or None for must-abstain
        "a40sb": "OA40SBB", "a40sp": "OA40SBL",        # colour variants split, not collapsed
        "r12fog": "OR12FOG", "r12fmg": "OR12FMG",      # near-dup of reno13, blocked apart
        "r12pro": "CPH2629",                            # model# in SKU (strong key)
        "r13": "OR13BL",                                # not cross-assigned to reno12f
        "a5proog": "AOPROG", "a5mp": "OA5MP",          # a5 vs a5pro blocked apart
        "a5promb": None,                                # no listed SKU -> abstain, not a wrong guess
        "h72a": None, "h72b": None,                     # same colour+storage -> indistinguishable
        "v30e": "6935117884578",                        # barcode strong key
    }
    for sid, exp in want.items():
        got = res[sid]
        if exp is None:
            check(f"match: {sid} abstains", got["status"] == "abstained", str(got))
        else:
            check(f"match: {sid} -> {exp}", got["status"] == "matched" and got["sku"] == exp, str(got))
    skus = [r["sku"] for r in res.values() if r["status"] == "matched"]
    check("match: no SKU reused across rows", len(skus) == len(set(skus)), str(skus))


def main():
    for fn in [test_engine_fixtures, test_engine_guards, test_conflicts, test_ledger_validate,
               test_profile_builder, test_linkcheck_offline, test_duplicate_sku,
               test_jobspec, test_schema_store, test_runner, test_primary_source,
               test_confidence, test_fields, test_hide_blank_columns,
               test_from_spec_table, test_completeness, test_match]:
        try:
            fn()
        except Exception as ex:  # noqa
            FAIL.append(f"{fn.__name__} raised {type(ex).__name__}: {ex}")
    print(f"\n{len(PASS)} passed, {len(FAIL)} failed")
    for p in PASS:
        print("  PASS", p)
    for f in FAIL:
        print("  FAIL", f)
    sys.exit(1 if FAIL else 0)


if __name__ == "__main__":
    main()
