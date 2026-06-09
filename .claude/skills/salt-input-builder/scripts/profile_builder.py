"""Profile builder. Drafts a category profile by INSPECTING real product data,
so brand/category knowledge is inferred and confirmed, never baked.

It does two things:
  1. Proposes plausibility ranges for the category's metrics, matched from the
     template's spec-column labels (tightened from observed values if given).
  2. Infers identifier decoders. SKUs are grouped by the product-LINE label you
     already have (the model/family name from the title or inventory), not by
     fragile SKU geometry. Within a line it aligns the SKUs, and for each varying
     segment it proposes a mapping ONLY when that segment maps cleanly to exactly
     one known attribute. A segment that could mean two things (because the sample
     is too small or confounded) is flagged for you, never guessed.

Output: a draft profile dict (the schema the engine runs) plus a Markdown
evidence report. Both are PROPOSALS to confirm, never final.

Honest limits: inference uses observed tokens, so confirm and widen a decoder
before trusting it on unseen tokens. If a product line is not labelled, grouping
falls back to a literal-prefix guess that must be checked. Ranges from labels are
suggestions.
"""
from __future__ import annotations
import re

METRIC_DEFAULTS = {
    "rpm":            (["rpm", "fan speed", "speed"], 100, 4000),
    "cfm":            (["cfm", "air flow", "airflow"], 5, 400),
    "static_pressure":(["static pressure", "mm h2o", "mmh2o", "air pressure"], 0.1, 20),
    "noise":          (["noise", "dba", "db(a)"], 5, 70),
    "voltage":        (["voltage", "vdc"], 1, 48),
    "current":        (["current", "ampere", "amp"], 0.01, 30),
    "power_w":        (["power", "wattage", "watt"], 1, 2000),
    "weight_kg":      (["weight (kg)", "weight kg"], 0.05, 200),
    "clock_mhz":      (["clock", "mhz", "frequency"], 100, 6000),
    "memory_gb":      (["memory", "vram", "capacity"], 1, 256),
    "fan_size_mm":    (["fan size"], 40, 240),
    "warranty_months":(["warranty"], 1, 120),
}
_VARIANT_ATTRS = ("colour", "color", "blade", "pack", "size", "type")


def _num(s):
    return [float(x) for x in re.findall(r"\d+\.?\d*", re.sub(r"\d+\.?\d*\s*%", " ", str(s or "")))]


def propose_metric_ranges(spec_labels, observed=None):
    observed = observed or {}
    ranges, unrecognised = {}, []
    for col, label in spec_labels.items():
        low = str(label).lower()
        hit = next(((m, lo, hi) for m, (kw, lo, hi) in METRIC_DEFAULTS.items() if any(k in low for k in kw)), None)
        if not hit:
            unrecognised.append(label); continue
        metric, lo, hi = hit
        src = "suggested-default"
        vals = [v for s in observed.get(label, []) for v in _num(s)]
        if vals:
            lo, hi, src = min(vals) * 0.5, max(vals) * 1.5, "from-observed-values"
        ranges[metric] = {"keywords": [low], "lo": round(lo, 3), "hi": round(hi, 3),
                          "_source": src, "_label": label}
    return ranges, unrecognised


def _family_of(p):
    return (p.get("family") or (p.get("attrs", {}) or {}).get("family"))


def _group_families(products):
    labelled, unlabelled = {}, []
    for p in products:
        fam = _family_of(p)
        (labelled.setdefault(fam, []) if fam else unlabelled).append(p)
    uncertain = []
    if unlabelled:
        for p in unlabelled:
            key = re.match(r"[0-9A-Za-z]+", p["sku"].split(".")[0]).group(0)[:6]
            labelled.setdefault(f"~{key}", []).append(p)
            uncertain.append(p["sku"])
    return labelled, uncertain


def _clean_attrs(fam, a, b):
    out = []
    attrs = set().union(*[set((p.get("attrs", {}) or {})) for p in fam]) & set(_VARIANT_ATTRS)
    for attr in sorted(attrs):
        m, ok = {}, True
        for p in fam:
            av = (p.get("attrs", {}) or {}).get(attr)
            if av is None:
                continue
            sv = p["sku"][a:b + 1]
            if sv in m and m[sv] != av:
                ok = False; break
            m[sv] = av
        if ok and len(set(m.values())) >= 2:
            out.append((attr, m))
    return out


def _emit(decoder, attr, mapping, a, b, is_suffix, skus, todos, fam_name):
    vals = sorted({s[a:b + 1] for s in skus})
    grp = "|".join(re.escape(v) for v in vals)
    if attr in ("colour", "color") and is_suffix:
        decoder["colour_source"] = "suffix"; decoder["suffix_colour"] = mapping
        return f"(?P<suffix>{grp})"
    if attr in ("colour", "color"):
        decoder["colour_source"] = "letter"; decoder["letter_colour"] = mapping
        todos.append(f"{fam_name}: colour is encoded in a letter; the engine treats letter-source as 'do not suffix-check' (safe, but it will not actively verify colour for this line).")
        return f"(?P<colour>{grp})"
    if attr == "blade":
        decoder["blade_map"] = mapping; return f"(?P<blade>{grp})"
    if attr == "pack":
        decoder["pack_map"] = dict(mapping); return f"(?P<pack>{grp})"
    if attr == "size":
        decoder["set_map"] = {k: [v, "?"] for k, v in mapping.items()}
        todos.append(f"{fam_name}: set/fan count per size not in the data; fill the '?' in set_map if the category needs it.")
        return f"(?P<size>{grp})"
    return f"(?P<{attr}>{grp})"


def _segments(skus):
    n = len(skus[0]); varying = [i for i in range(n) if len({s[i] for s in skus}) > 1]
    segs, run = [], []
    for i in range(n):
        if i in varying:
            run.append(i)
        elif run:
            segs.append((run[0], run[-1])); run = []
    if run:
        segs.append((run[0], run[-1]))
    return segs


def infer_decoders(products):
    families, uncertain = _group_families(products)
    decoders, evidence, todos = [], [], []
    if uncertain:
        todos.append(f"product line not labelled for {uncertain}; grouping is a guess - confirm or add a 'family' label.")
    for fam_name, fam in families.items():
        skus = [p["sku"] for p in fam]
        if len({len(s) for s in skus}) != 1:
            todos.append(f"{fam_name}: SKUs differ in length {sorted({len(s) for s in skus})}; cannot align positionally - define this decoder manually.")
            continue
        n = len(skus[0]); dot = skus[0].rfind(".")
        decoder = {"name": str(fam_name)}
        parts, i, ev = [], 0, []
        segset = _segments(skus)
        while i < n:
            seg = next(((a, b) for (a, b) in segset if a <= i <= b), None)
            if seg is None:
                parts.append(re.escape(skus[0][i])); i += 1; continue
            a, b = seg
            is_suffix = a > dot
            whole = _clean_attrs(fam, a, b)
            if len(whole) == 1 and (b - a + 1) <= 2:
                attr, mp = whole[0]
                parts.append(_emit(decoder, attr, mp, a, b, is_suffix, skus, todos, fam_name))
                ev.append(f"{attr}: {mp}")
            else:
                per = [(j, _clean_attrs(fam, j, j)) for j in range(a, b + 1)]
                attrs = [x[1][0] for x in per if len(x[1]) == 1]
                distinct = (len({at for at, _ in attrs}) == len(attrs) == (b - a + 1)) and bool(attrs)
                if distinct:
                    for j, ca in per:
                        attr, mp = ca[0]
                        parts.append(_emit(decoder, attr, mp, j, j, j > dot, skus, todos, fam_name))
                        ev.append(f"{attr}: {mp}")
                else:
                    vals = sorted({s[a:b + 1] for s in skus})
                    cls = r"\d" if skus[0][a].isdigit() else (r"[A-Za-z]" if skus[0][a].isalpha() else ".")
                    parts.append(f"(?:{cls}{{{b - a + 1}}})")
                    why = "could mean more than one attribute" if len(whole) > 1 else "did not match a known attribute"
                    todos.append(f"{fam_name}: segment {vals} {why}; provide more SKUs that vary these independently, or define manually.")
            i = b + 1
        rx = "".join(parts)
        try:
            re.compile(rx)
        except re.error as ex:
            todos.append(f"{fam_name}: generated regex invalid ({ex}); define manually."); continue
        decoder["sku_regex"] = rx
        if any(k in decoder for k in ("suffix_colour", "letter_colour", "blade_map", "pack_map", "set_map")):
            decoders.append(decoder)
            evidence.append({"family": str(fam_name), "skus": skus, "regex": rx, "mappings": ev})
        else:
            todos.append(f"{fam_name}: no variant mapping could be inferred from the given SKUs; provide more examples or define manually.")
    return decoders, evidence, todos


def build_profile(category, brand, spec_labels, products, observed=None):
    ranges, unrecognised = propose_metric_ranges(spec_labels, observed)
    decoders, evidence, todos = infer_decoders(products)
    profile = {"category": category, "brand": brand, "percent_guard": True,
               "metric_ranges": {k: {kk: vv for kk, vv in v.items() if not kk.startswith("_")}
                                 for k, v in ranges.items()},
               "decoders": decoders}
    L = [f"# Draft category profile: {brand} / {category}  (PROPOSAL - confirm before use)", "",
         "## Metric ranges (suggested; confirm or tighten)"]
    for m, v in ranges.items():
        L.append(f"- {m}: {v['lo']}-{v['hi']}  from label '{v['_label']}' ({v['_source']})")
    if unrecognised:
        L.append(f"- UNRECOGNISED labels (no range proposed, set manually): {unrecognised}")
    L += ["", "## Inferred decoders (evidence shown; confirm each mapping)"]
    if not evidence:
        L.append("- none could be inferred with confidence from the given data")
    for e in evidence:
        L.append(f"- {e['family']}: `{e['regex']}`  from {e['skus']}")
        for m in e["mappings"]:
            L.append(f"    - {m}")
    if todos:
        L += ["", "## TODO / could not infer (needs you)"] + [f"- {t}" for t in todos]
    return profile, "\n".join(L) + "\n"


if __name__ == "__main__":
    products = [
        {"family": "Cougar SC140", "sku": "3MSC14FA1.0001", "attrs": {"blade": "forward", "colour": "black"}},
        {"family": "Cougar SC140", "sku": "3MSC14RA1.0001", "attrs": {"blade": "reverse", "colour": "black"}},
        {"family": "Cougar SC140", "sku": "3MSC14FA1.0002", "attrs": {"blade": "forward", "colour": "white"}},
        {"family": "Cougar SC140", "sku": "3MSC14RA1.0002", "attrs": {"blade": "reverse", "colour": "white"}},
        {"family": "Cougar MHP",   "sku": "3MMHP12W1.0001", "attrs": {"colour": "white", "pack": "1"}},
        {"family": "Cougar MHP",   "sku": "3MMHP12W3.0001", "attrs": {"colour": "white", "pack": "3"}},
        {"family": "Cougar MHP",   "sku": "3MMHP12A1.0001", "attrs": {"colour": "black", "pack": "1"}},
        {"family": "Cougar MHP",   "sku": "3MMHP12A3.0001", "attrs": {"colour": "black", "pack": "3"}},
        {"family": "Cougar Apolar","sku": "3MAPR12A1.0001", "attrs": {"colour": "black", "pack": "1"}},
        {"family": "Cougar Apolar","sku": "3MAPR12A1.0002", "attrs": {"colour": "white", "pack": "1"}},
        {"family": "Cougar Apolar","sku": "3MAPR12A3.0001", "attrs": {"colour": "black", "pack": "3"}},
        {"family": "Cougar Apolar","sku": "3MAPR12A3.0002", "attrs": {"colour": "white", "pack": "3"}},
        {"family": "Cougar Unity", "sku": "3MUN24FA1.0001", "attrs": {"size": "240", "blade": "forward", "colour": "black"}},
        {"family": "Cougar Unity", "sku": "3MUN36RA1.0002", "attrs": {"size": "360", "blade": "reverse", "colour": "white"}},
    ]
    labels = {"6": "Fan speed (RPM)", "7": "Air flow (CFM)", "9": "Noise (dBA)", "5": "Bearing"}
    prof, report = build_profile("fans", "Cougar", labels, products)
    print(report)
    for d in prof["decoders"]:
        fam = [p for p in products if str(p.get("family")) == d["name"]]
        assert all(re.search(d["sku_regex"], p["sku"].upper().replace(" ", "")) for p in fam), d["name"]
    print("decoder-match self-test passed")
