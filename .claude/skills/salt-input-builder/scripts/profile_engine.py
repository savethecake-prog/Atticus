"""Generic rule engine. Brand- and product-agnostic by construction: it knows
HOW to run plausibility ranges, identifier decoders, and cross-field rules, but
it holds NO knowledge of any specific brand or category. All of that arrives in
a `profile` dict that is built per job by inspecting the actual product and
category data and confirmed by the user (see references/category-profiles.md).

run_checks(ws, row, roles, labels, profile) -> list of (cols, severity, msg)

The false-positive guards live here because they are engine-level, not brand
knowledge: tolerance-aware number parsing and range handling.
"""
from __future__ import annotations
import re


def _nums(text, percent_guard=True):
    """Numeric tokens, ignoring tolerances so a value's real min/max is read.
    Strips '(+-200)', '(+-10%)', bare '+-10%' / '±200', and any 'NN%'."""
    s = str(text or "")
    if percent_guard:
        s = re.sub(r"\(\s*(?:\+/?-|\u00b1)[^)]*\)", " ", s)
        s = re.sub(r"(?:\+/?-|\u00b1)\s*\d+\.?\d*\s*%?", " ", s)
        s = re.sub(r"\d+\.?\d*\s*%", " ", s)
    return [float(x) for x in re.findall(r"\d+\.?\d*", s)]


def _find_col(roles, labels, keywords):
    for c in range(roles["spec_start"], roles["spec_end"] + 1):
        lab = str(labels.get(str(c), "")).lower()
        if any(k in lab for k in keywords):
            return c
    for k in keywords:
        if k in roles:
            return roles[k]
    return None


def _cell(ws, r, c):
    return "" if c is None else (ws.cell(r, c).value or "")


def run_checks(ws, row, roles, labels, profile):
    p = profile or {}
    pg = p.get("percent_guard", True)
    out = []
    title = str(_cell(ws, row, roles.get("title", 1)))
    sku = str(_cell(ws, row, roles.get("sku"))).upper().replace(" ", "")

    # plausibility (tolerance- and range-aware)
    for name, spec in p.get("metric_ranges", {}).items():
        col = _find_col(roles, labels, spec["keywords"])
        if not col:
            continue
        vals = _nums(_cell(ws, row, col), pg)
        if vals and (min(vals) < spec["lo"] or max(vals) > spec["hi"]):
            out.append(([col], "SOFT",
                        f"{name} value '{_cell(ws, row, col)}' outside plausible {spec['lo']}-{spec['hi']}."))

    # identifier decoders (patterns supplied by the profile, not baked here)
    for d in p.get("decoders", []):
        m = re.search(d["sku_regex"], sku)
        if not m:
            continue
        gd = m.groupdict()
        if d.get("colour_source") == "suffix" and "suffix" in gd:
            exp = d.get("suffix_colour", {}).get(gd["suffix"])
            col = _find_col(roles, labels, d.get("colour_label_keywords", ["colour", "color"]))
            if exp and col:
                got = str(_cell(ws, row, col)).lower()
                if got and exp not in got:
                    out.append(([roles.get("title", 1), col], "HARD",
                                f"SKU '{sku}' suffix means {exp}, but colour reads '{got}'. Confirm colour."))
        if "blade" in gd and d.get("blade_map"):
            exp = d["blade_map"].get(gd["blade"])
            col = _find_col(roles, labels, d.get("blade_label_keywords", ["type", "blade"]))
            if exp and col:
                got = str(_cell(ws, row, col)).lower()
                if got and exp not in got:
                    out.append(([roles.get("title", 1), col], "HARD",
                                f"SKU '{sku}' is {exp}-blade, but field reads '{got}'."))
        if "size" in gd and d.get("set_map"):
            size, fans = d["set_map"].get(gd["size"], [None, None])
            col = _find_col(roles, labels, d.get("fancount_label_keywords", ["quantity", "pack"]))
            if fans and col and fans not in str(_cell(ws, row, col)):
                out.append(([col], "SOFT", f"SKU '{sku}' is a {size} set ({fans}); quantity field disagrees."))
        if "pack" in gd and d.get("pack_map"):
            exp_pack = d["pack_map"].get(gd["pack"])
            tm = re.search(r"x\s*(\d)", title.lower())
            if exp_pack and tm and tm.group(1) != exp_pack:
                out.append(([roles.get("title", 1)], "HARD",
                            f"SKU '{sku}' denotes a {exp_pack}-pack, but title says x{tm.group(1)}. Confirm quantity."))

    # cross-field: an implied-count map (e.g. radiator 240 -> 2 fans)
    cf = p.get("implies_count")
    if cf:
        sz_col = _find_col(roles, labels, cf.get("from_keywords", []))
        ct_col = _find_col(roles, labels, cf.get("count_keywords", []))
        if sz_col and ct_col:
            txt = str(_cell(ws, row, sz_col)) + " " + title
            for key, count in cf.get("map", {}).items():
                if str(key) in txt:
                    cv = _nums(_cell(ws, row, ct_col))
                    if cv and int(count) not in [int(x) for x in cv]:
                        out.append(([ct_col], "SOFT", f"{key} implies {count}; count field disagrees."))
                    break

    # cross-field: keyed compatibility map (e.g. socket -> chipset family)
    comp = p.get("compatibility")
    if comp:
        a_col = _find_col(roles, labels, comp.get("a_keywords", []))
        b_col = _find_col(roles, labels, comp.get("b_keywords", []))
        if a_col and b_col:
            a = str(_cell(ws, row, a_col)).upper()
            b = str(_cell(ws, row, b_col)).upper()
            for key, allowed in comp.get("map", {}).items():
                if key.upper() in a and b and not any(x.upper() in b for x in allowed):
                    out.append(([a_col, b_col], "SOFT",
                                f"'{a}' and '{b}' look inconsistent per the profile. Verify."))
    return out


if __name__ == "__main__":
    assert _nums("Up to 2000 RPM (+-10%)") == [2000.0]
    assert _nums("400 (+-200) - 1200 RPM (+-10%)") == [400.0, 1200.0]
    print("engine guard self-test passed")
