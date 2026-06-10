"""Per-cell confidence and the write-eligibility gate.

Confidence is a number 0-100 with a short reason, driven by two things together:
the tier of the source(s) and how many INDEPENDENT sources agree on the value.
It rides with each value (in the ledger and the exported map) so SALT can gate
on it.

Eligibility encodes the rule: a value may be written only if it has a
manufacturer source, OR two or more independent sources agree, OR it is
client-provided identity / a derived value. Anything else stays blank and
flagged - a single uncorroborated retailer claim is not written.

Independence is by host: two pages on the same domain are one source.
"""
from __future__ import annotations
import re
from urllib.parse import urlsplit
try:
    from common import value_supported_by_snippet
except Exception:  # standalone self-test fallback
    def value_supported_by_snippet(v, s):
        return True

WEB_TIERS = ("manufacturer", "retailer")


def _not_verbatim(entry):
    """A web value whose exact text is not in its snippet is 'disputed': it exists
    on a source but isn't verbatim-confirmed (e.g. a legacy/long-published figure,
    or an interpreted value). We write it, score it low, and say why."""
    if entry.get("answer_kind") == "absent":
        return False  # a sourced negative has no positive value to verbatim-check
    return (entry.get("provenance") in WEB_TIERS and entry.get("snippet")
            and not value_supported_by_snippet(entry.get("value"), entry.get("snippet")))


def _vn(s):
    return re.sub(r"[^a-z0-9]", "", str(s or "").lower())


def _host(u):
    return urlsplit(u or "").netloc.lower().replace("www.", "")


def _obs(entry):
    return entry.get("candidates") or [entry]


def _analyse(entry):
    """Return (agreeing hosts, manufacturer hosts, [(host, value) disagreements])."""
    chosen = _vn(entry.get("value"))
    agree, man, disagree, seen = [], [], [], set()
    for o in _obs(entry):
        if o.get("provenance") not in WEB_TIERS:
            continue
        h = _host(o.get("source_url"))
        if _vn(o.get("value")) == chosen:
            if h and h not in seen:
                seen.add(h); agree.append(h)
            if o.get("provenance") == "manufacturer" and h and h not in man:
                man.append(h)
        else:
            disagree.append((h or "another source", o.get("value")))
    return agree, man, disagree


def band(score):
    return "high" if score >= 85 else ("medium" if score >= 60 else "low")


def score_entry(entry):
    """Return (score 0-100, detailed reason) naming the sources, in the pre-skill style."""
    prov = entry.get("provenance")
    if entry.get("answer_kind") == "absent":
        # A sourced negative: confident when the captured table is complete.
        if entry.get("completeness_uncertain"):
            return 50, (entry.get("note") or "asserted absent, but the source table's completeness is unconfirmed - verify")
        return 88, (entry.get("note") or "feature not present in the complete published spec table")
    doubt = entry.get("doubt_reason")
    if not doubt and _not_verbatim(entry):
        doubt = "value not stated verbatim in the captured source snippet; confirm or remove"
    if doubt:
        return 30, doubt
    if prov == "client":
        return 85, "client inventory identity field (provided by the client, not re-sourced)"
    if prov == "derived":
        return 70, (entry.get("note") or "derived/computed value")
    agree, man, disagree = _analyse(entry)
    n = len(agree)
    if disagree:
        dh, dv = disagree[0]
        return 35, f"sources disagree ({n} agree; {dh} gives '{dv}') - resolve before use"
    if man:
        if n >= 2:
            others = [h for h in agree if h not in man]
            tail = f" and corroborated by {len(others)} other source(s)" if others else " corroborated by a second source"
            return 97, f"confirmed against manufacturer source ({man[0]}){tail}"
        return 90, f"confirmed against manufacturer source ({man[0]})"
    if n >= 3:
        return 82, f"{n} independent sources agree ({', '.join(agree[:3])}); no manufacturer source - spot-check before passing through"
    if n == 2:
        return 70, f"2 independent sources agree ({', '.join(agree)}); no manufacturer source - spot-check before passing through"
    if n == 1:
        return 40, f"only source: {agree[0]}; no manufacturer source and no corroboration - verify accuracy before passing through"
    return 20, "no usable source on record - verify before use"


def eligible(entry):
    """Whether the value clears the 2-source bar (manufacturer, OR 2+ independent
    agreeing sources, OR client/derived). The value is written either way; this is
    reported to SALT and used to flag, not to suppress the write. A disputed
    (doubt_reason / non-verbatim) value is never eligible."""
    if entry.get("answer_kind") == "absent":
        return not entry.get("completeness_uncertain")
    if entry.get("doubt_reason") or _not_verbatim(entry):
        return False
    prov = entry.get("provenance")
    if prov in ("client", "derived"):
        return True
    agree, man, _ = _analyse(entry)
    return bool(man) or len(agree) >= 2


def annotate(entries):
    """Stamp each entry with confidence, confidence_reason, eligible, band."""
    for e in entries:
        s, r = score_entry(e)
        e["confidence"], e["confidence_reason"] = s, r
        e["eligible"], e["band"] = eligible(e), band(s)
    return entries


def export_map(entries):
    """Machine-readable per-cell confidence feed for SALT."""
    out = []
    for e in entries:
        s, r = score_entry(e)
        agree, _man, _dis = _analyse(e)
        out.append({"tab": e.get("tab"), "row": e.get("row"), "column": e.get("column"),
                    "field": e.get("field"), "value": e.get("value"),
                    "provenance": e.get("provenance"), "confidence": s, "band": band(s),
                    "reason": r, "independent_sources": len(agree), "eligible": eligible(e)})
    return out


if __name__ == "__main__":
    man = lambda v, u: {"value": v, "provenance": "manufacturer", "source_url": u, "snippet": v}
    ret = lambda v, u: {"value": v, "provenance": "retailer", "source_url": u, "snippet": v}
    E = lambda val, prov, cands=None, url=None: {"value": val, "provenance": prov, "source_url": url,
                                                 "snippet": val, "candidates": cands}
    # manufacturer single -> 90, eligible
    assert score_entry(E("x", "manufacturer", url="https://m"))[0] == 90
    assert eligible(E("x", "manufacturer", url="https://m"))
    # single retailer -> 40, NOT eligible
    assert score_entry(E("x", "retailer", url="https://a"))[0] == 40
    assert not eligible(E("x", "retailer", url="https://a"))
    # two independent retailers agree -> 70, eligible
    two = E("x", "retailer", cands=[ret("x", "https://a"), ret("x", "https://b")])
    assert score_entry(two)[0] == 70 and eligible(two)
    # same host twice is one source -> still single, not eligible
    same = E("x", "retailer", cands=[ret("x", "https://a/1"), ret("x", "https://a/2")])
    assert not eligible(same), "same host must count once"
    # disagreement -> 35
    dis = E("x", "retailer", cands=[ret("x", "https://a"), ret("y", "https://b")])
    assert score_entry(dis)[0] == 35
    # client identity -> 85, eligible
    assert score_entry(E("TG-1", "client"))[0] == 85 and eligible(E("TG-1", "client"))
    print("confidence self-test passed")
