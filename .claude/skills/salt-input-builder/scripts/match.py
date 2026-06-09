"""Identity matching: link product variants to their SKU across two sheets,
abstaining (blank + reason) rather than asserting an identifier it cannot prove.

Built from two real failures (Infinity job, 2026-06-09):
  - a colour-blind join put one SKU on two colour variants (A40 Sparkle/Starry);
  - a greedy join cross-assigned near-duplicate models (Reno12F -> Reno13 SKU,
    A5 Pro -> A5 SKU).

The fix the entity-resolution literature prescribes, at our scale:
  1. STRONG KEY first   - exact barcode/EAN, then manufacturer model# inside a SKU.
  2. BLOCK exactly      - by model token, so A5 and A5 Pro / Reno12F and Reno13
                          never share a candidate pool.
  3. HARD GATES         - colour and storage CONFLICT makes a pair ineligible
                          (a veto, not a low weight). This stops variant collapse.
  4. GLOBAL ASSIGNMENT  - optimal one-to-one within a block (not greedy), so no
                          SKU is reused and local picks can't go globally wrong.
  5. ABSTENTION         - below an absolute threshold, OR too close to the
                          second-best eligible candidate, OR contended-and-lost
                          -> leave blank with a reason (Fellegi-Sunter "possible
                          match -> review", mapped to blank-and-flag).

Dependency-free on purpose: stdlib only (difflib + token sets for scoring,
exact search for the tiny per-block assignment). rapidfuzz/scipy would be drop-in
upgrades for the scorer/assignment but are unjustified at variant-group scale.
"""
from __future__ import annotations
import re, difflib
from itertools import permutations

# ---- tuning (conservative on identity: prefer a blank to a wrong SKU) --------
ABS_THRESHOLD = 0.50   # best eligible similarity must clear this
MARGIN = 0.15          # top must beat 2nd-best eligible by at least this

_STOP = {"with", "free", "dual", "sim", "gb", "ram", "rom", "the", "and",
         "smartphone", "smart", "phone", "android", "5g", "4g", "lte", "jaua",
         "watch", "smartwatch", "tablet", "pad", "earbuds", "+free"}


def _norm(s):
    return re.sub(r"\s+", " ", str(s or "").replace(" ", " ")).strip().lower()


def _tokens(text):
    return [t for t in re.sub(r"[^a-z0-9]", " ", _norm(text)).split() if t]


def parse_colour_storage(title):
    """Pull colour tokens and storage GB from a listing title, e.g.
    'Oppo A40 (Sparkle Black, 128 GB) (4 GB RAM)' -> ({'sparkle','black'}, '128')."""
    t = _norm(title)
    colour, stor = set(), ""
    m = re.search(r"\(([^,)]+),\s*(\d+)\s*gb\)", t)
    if m:
        colour = {w for w in re.sub(r"[^a-z ]", " ", m.group(1)).split() if len(w) > 2}
        stor = m.group(2)
    if not colour:  # fall back: colour words anywhere minus storage noise
        colour = {w for w in _tokens(t)
                  if w in _COLOUR_WORDS}
    return colour, stor


_COLOUR_WORDS = {
    "black", "white", "blue", "green", "gold", "purple", "grey", "gray", "red",
    "silver", "brown", "pink", "titanium", "sparkle", "starry", "phantom",
    "mocha", "olive", "midnight", "rosewood", "stellar", "plum", "luminous",
    "space", "galactic", "twilight", "breeze", "platinum", "glimmer", "nebula",
}


def _colour_set(raw):
    return {w for w in re.sub(r"[^a-z ]", " ", _norm(raw)).split() if len(w) > 2}


def _model_token(text, brand, colour_set, storage):
    """Block key: a SPACE-COLLAPSED model signature with brand, colour, storage and
    marketing words removed, in original order. Collapsing spaces makes the source's
    'Reno 12F' and the listing's 'Reno12 F' resolve to the same key ('reno12f'),
    while 'a5' != 'a5pro' and 'reno12f' != 'reno13' stay in separate blocks."""
    text = re.sub(r"\(.*?\)", " ", str(text or ""))   # drop "(Colour, 128 GB)" / "(8 GB RAM)"
    # drop brand, the parsed colour, AND any known colour word (titles carry colour
    # words outside the parenthetical too, e.g. "A40 Starry Blue (Starry Purple,...)")
    drop = set(_tokens(brand)) | set(colour_set) | _COLOUR_WORDS | _STOP
    toks = []
    for t in _tokens(text):
        if t in drop:
            continue
        if storage and t == storage:
            continue
        if re.fullmatch(r"\d+gb", t):
            continue
        toks.append(t)
    return "".join(toks)


def _similarity(a, b):
    """0..1 blend of token-set Jaccard and sequence ratio on the model remainder."""
    ta, tb = set(_tokens(a)), set(_tokens(b))
    jac = len(ta & tb) / len(ta | tb) if (ta or tb) else 0.0
    seq = difflib.SequenceMatcher(None, _norm(a), _norm(b)).ratio()
    return 0.6 * jac + 0.4 * seq


def _best_assignment(pairs, sources, targets):
    """Max-total-score one-to-one assignment over eligible pairs. Blocks are tiny
    (variant groups), so exact search is fine. Returns {src_i: tgt_j}."""
    best = {"score": -1.0, "assign": {}}
    tgt = list(targets)

    def rec(si, used, score, assign):
        if si == len(sources):
            if score > best["score"]:
                best["score"] = score
                best["assign"] = dict(assign)
            return
        s = sources[si]
        # option: leave this source unassigned
        rec(si + 1, used, score, assign)
        for tj in tgt:
            if tj in used:
                continue
            if (s, tj) in pairs:
                assign[s] = tj
                rec(si + 1, used | {tj}, score + pairs[(s, tj)], assign)
                del assign[s]

    rec(0, set(), 0.0, {})
    return best["assign"]


def _strong_key(src, targets, used):
    """Exact barcode, then manufacturer model# appearing as a SKU. Returns target id or None."""
    bc = re.sub(r"\D", "", src.get("barcode", "") or "")
    if len(bc) >= 12:
        for t in targets:
            if t["id"] in used:
                continue
            tb = re.sub(r"\D", "", t.get("barcode", "") or "")
            if tb and tb == bc:
                return t["id"], "barcode"
    mn = re.sub(r"[^a-z0-9]", "", _norm(src.get("model_number", "")))
    if len(mn) >= 5:
        for t in targets:
            if t["id"] in used:
                continue
            if mn == re.sub(r"[^a-z0-9]", "", _norm(t.get("sku", ""))):
                return t["id"], f"model#={t.get('sku')}"
    return None


def match(sources, targets, *, abs_threshold=ABS_THRESHOLD, margin=MARGIN):
    """Match each source row to a target SKU or abstain.

    source row: {id, brand, model (name/title), colour, storage, barcode, model_number}
    target row: {id, brand, title, sku, barcode}
    Returns a list aligned to `sources`:
      {source_id, status: 'matched'|'abstained', sku, target_id, score, method, reason}
    """
    # pre-parse targets
    T = []
    for t in targets:
        col, stor = parse_colour_storage(t.get("title", ""))
        T.append({**t, "_colour": col, "_storage": stor,
                  "_mtok": _model_token(t.get("title", ""), t.get("brand", ""), col, stor)})
    results = {}
    used = set()

    # 1) strong keys (global, order-independent)
    pending = []
    for s in sources:
        hit = _strong_key(s, T, used)
        if hit:
            tid, method = hit
            used.add(tid)
            tgt = next(t for t in T if t["id"] == tid)
            results[s["id"]] = dict(source_id=s["id"], status="matched", sku=tgt.get("sku"),
                                    target_id=tid, score=1.0, method=method, reason="")
        else:
            pending.append(s)

    # 2) block remaining by (brand, model token)
    blocks = {}
    for s in pending:
        col = _colour_set(s.get("colour", ""))
        stor = _norm(s.get("storage", ""))
        s = {**s, "_colour": col, "_storage": stor,
             "_mtok": _model_token(s.get("model", ""), s.get("brand", ""), col, stor)}
        blocks.setdefault((_norm(s.get("brand", "")), s["_mtok"]), {"src": [], "tgt": None})["src"].append(s)
    # attach available targets to each block by same key
    avail_t = [t for t in T if t["id"] not in used]
    for key, blk in blocks.items():
        brand, mtok = key
        blk["tgt"] = [t for t in avail_t if _norm(t.get("brand", "")) == brand and t["_mtok"] == mtok]

    for (brand, mtok), blk in blocks.items():
        srcs, tgts = blk["src"], blk["tgt"]
        # indistinguishable source rows: same model + colour + storage -> cannot be
        # assigned individually (can't prove which row is which). Abstain them all.
        sig_count = {}
        for s in srcs:
            sig = (frozenset(s["_colour"]), s["_storage"])
            sig_count[sig] = sig_count.get(sig, 0) + 1
        ambiguous = {id(s) for s in srcs
                     if sig_count[(frozenset(s["_colour"]), s["_storage"])] > 1}
        live = [s for s in srcs if id(s) not in ambiguous]
        for s in srcs:
            if id(s) in ambiguous:
                results[s["id"]] = dict(source_id=s["id"], status="abstained", sku=None,
                                        target_id=None, score=0.0, method="abstain",
                                        reason="indistinguishable source rows (same colour+storage); cannot assign individually")
        srcs = live
        # eligibility + score per (src, tgt): colour/storage conflict = ineligible (gate)
        elig = {}  # (sidx, tid) -> score
        cand = {s["id"]: [] for s in srcs}
        for si, s in enumerate(srcs):
            for t in tgts:
                if s["_colour"] and t["_colour"] and not (s["_colour"] & t["_colour"]):
                    continue  # colour conflict -> veto
                if s["_storage"] and t["_storage"] and s["_storage"] != t["_storage"]:
                    continue  # storage conflict -> veto
                # Structural score: same block already means the model matches, so the
                # raw title text (full of "+Free ... Jaua Watch" noise) is not the signal.
                # Score on agreement of the discriminators instead.
                sc = 0.6                                            # block member (model matches)
                if s["_colour"] and t["_colour"] and (s["_colour"] & t["_colour"]):
                    sc += 0.3                                       # colour agrees
                if s["_storage"] and t["_storage"] and s["_storage"] == t["_storage"]:
                    sc += 0.1                                       # storage agrees
                elig[(si, t["id"])] = sc
                cand[s["id"]].append((sc, t["id"]))

        assign = _best_assignment(elig, list(range(len(srcs))), [t["id"] for t in tgts])

        for si, s in enumerate(srcs):
            ranked = sorted(cand[s["id"]], reverse=True)
            tid = assign.get(si)
            reason = ""
            if not ranked:
                status, sku, score = "abstained", None, 0.0
                reason = "no eligible candidate (colour/storage conflict or no listing)"
            elif tid is None:
                status, sku, score = "abstained", None, ranked[0][0]
                reason = "lost contention for the shared candidate"
            else:
                top = ranked[0]
                second = ranked[1][0] if len(ranked) > 1 else None
                score = elig[(si, tid)]
                if top[1] != tid:
                    status, sku, score = "abstained", None, score
                    reason = "global optimum diverged from this row's best -> ambiguous"
                elif top[0] < abs_threshold:
                    status, sku, score = "abstained", None, top[0]
                    reason = f"best score {top[0]:.2f} < {abs_threshold:.2f}"
                elif second is not None and (top[0] - second) < margin:
                    status, sku, score = "abstained", None, top[0]
                    reason = f"top {top[0]:.2f} within {margin} of 2nd {second:.2f} -> ambiguous"
                else:
                    tgt = next(t for t in tgts if t["id"] == tid)
                    status, sku = "matched", tgt.get("sku")
                    used.add(tid)
            results[s["id"]] = dict(source_id=s["id"], status=status, sku=sku,
                                    target_id=tid if status == "matched" else None,
                                    score=round(score, 3),
                                    method="key+gate+assign" if status == "matched" else "abstain",
                                    reason=reason)

    return [results[s["id"]] for s in sources]
