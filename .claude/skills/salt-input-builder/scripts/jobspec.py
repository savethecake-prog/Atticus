"""Validate a job spec (the confirmed contract) before a run starts, so a
malformed contract fails fast with a clear message instead of part-way through.

validate_jobspec(spec) -> list of strings, each prefixed ERROR or WARN.
is_valid(spec) -> True if there are no ERRORs.
"""
from __future__ import annotations
import re

TIERS = ("manufacturer", "retailer", "client", "derived", "unverifiable")
GATE_MODES = ("adaptive", "all", "final_only")
_HEX = re.compile(r"^[0-9A-Fa-f]{6}$")


def validate_jobspec(spec):
    out = []
    E = lambda m: out.append("ERROR: " + m)
    W = lambda m: out.append("WARN: " + m)
    if not isinstance(spec, dict):
        return ["ERROR: job spec is not a mapping"]

    job = spec.get("job")
    if not isinstance(job, dict):
        E("missing 'job' block")
    else:
        if not job.get("template"):
            E("job.template is empty (path to the blank workbook is required)")
        if not job.get("output_dir"):
            W("job.output_dir is empty")
        if not job.get("name"):
            W("job.name is empty")

    sp = spec.get("source_policy", {})
    if not isinstance(sp, dict):
        E("source_policy must be a mapping")
    else:
        order = sp.get("tier_order", [])
        if not isinstance(order, list) or any(t not in ("manufacturer", "retailer") for t in order):
            E("source_policy.tier_order must be a list drawn from [manufacturer, retailer]")

    auth = spec.get("authority", {})
    if not isinstance(auth, dict):
        E("authority must be a mapping")
    else:
        for k in ("manufacturer_domains", "reputable_retailers"):
            if k in auth and not isinstance(auth[k], list):
                E(f"authority.{k} must be a list")
        if not auth.get("infer_brand_domain") and not auth.get("manufacturer_domains"):
            W("no manufacturer authority: infer_brand_domain is off and manufacturer_domains is empty")

    cc = spec.get("confidence_colours", {})
    if cc and not isinstance(cc, dict):
        E("confidence_colours must be a mapping")
    elif isinstance(cc, dict):
        for tier, pair in cc.items():
            if tier not in TIERS:
                W(f"confidence_colours has unknown tier '{tier}'")
            if not isinstance(pair, dict) or not _HEX.match(str(pair.get("fill", ""))) or not _HEX.match(str(pair.get("font", ""))):
                E(f"confidence_colours.{tier} needs 6-hex 'fill' and 'font'")

    cp = spec.get("category_profiles", {})
    if not isinstance(cp, dict):
        E("category_profiles must be a mapping of tab/category -> profile path")
    else:
        for k, v in cp.items():
            if not isinstance(v, str):
                E(f"category_profiles['{k}'] must be a path string")

    gates = spec.get("gates", {})
    if not isinstance(gates, dict) or gates.get("mode") not in GATE_MODES:
        E(f"gates.mode must be one of {GATE_MODES}")

    if not isinstance(spec.get("deliverables", []), list):
        E("deliverables must be a list")

    items = spec.get("items", [])
    if not isinstance(items, list):
        E("items must be a list")
    else:
        for i, it in enumerate(items):
            if not isinstance(it, dict) or not it.get("tab"):
                E(f"items[{i}] needs a 'tab'")
            cf = (it or {}).get("client_fields", {})
            if not isinstance(cf, dict) or not (cf.get("sku") or cf.get("brand")):
                W(f"items[{i}] has no client sku/brand identity")
    return out


def is_valid(spec):
    return not any(v.startswith("ERROR") for v in validate_jobspec(spec))


if __name__ == "__main__":
    good = {"job": {"name": "B1", "template": "t.xlsx", "output_dir": "out"},
            "source_policy": {"tier_order": ["manufacturer", "retailer"]},
            "authority": {"infer_brand_domain": True, "manufacturer_domains": [], "reputable_retailers": []},
            "confidence_colours": {"manufacturer": {"fill": "C6EFCE", "font": "006100"}},
            "category_profiles": {"Fans": "profiles/fans.yaml"},
            "gates": {"mode": "adaptive"}, "deliverables": ["workbook"],
            "items": [{"tab": "Fans", "client_fields": {"sku": "X-1"}}]}
    assert is_valid(good), validate_jobspec(good)
    bad = {"job": {}, "source_policy": {"tier_order": ["wholesaler"]},
           "gates": {"mode": "whenever"}, "category_profiles": [], "items": "nope"}
    vs = validate_jobspec(bad)
    assert not is_valid(bad) and len([v for v in vs if v.startswith("ERROR")]) >= 5, vs
    print("jobspec self-test passed")
