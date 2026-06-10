"""Derivation with provenance (W3).

The north star: a correct value we could have computed but left blank is a failed
product too. Where a target field is empty but the answer is computable from data
we already hold, derive it - and record HOW, as a `derived`-tier ledger entry that
carries a note and is scored (70) and disclosed, never silently asserted.

This module holds ONLY transforms that are safe and explainable:
  - colour from the product title (reuses the identity matcher's colour parser);
  - the total-height axis of the product dimensions, picked by the PUBLISHED axis
    order (e.g. "H x W x L"), never guessed.

The net/gross <-> Product/Packaging weight & dimensions relationship is NOT here:
those are real published source fields, mapped to their column by the alias map
(fields.reconcile), so they keep a manufacturer provenance rather than a derived
one. Derivation is only for values that are computed, not merely re-labelled.
"""
from __future__ import annotations
import re


def colour_from_title(title):
    """(colour, note) derived from a product title, or None when the title states
    no colour. Reuses match.parse_colour_storage so the rule is the same one used
    to split variants. The colour spec field, where present, is authoritative; this
    is the fallback, and it is flagged for confirmation."""
    try:
        import match
        words, _storage = match.parse_colour_storage(title or "")
    except Exception:
        words = set()
    if words:
        colour = " ".join(w.capitalize() for w in sorted(words))
        return colour, "colour derived from the product title; confirm against the colour spec"
    return None


def height_from_dimensions(dim_value, axis_order):
    """(value, note) for a total-height field, taken from the height axis of a
    'A x B x C' dimension string using the PUBLISHED axis order (e.g. 'HWL').
    Returns None if the order does not name H or the dimensions are too few - the
    axis is never guessed."""
    nums = re.findall(r"\d+(?:\.\d+)?", str(dim_value or ""))
    order = (axis_order or "").upper()
    if "H" not in order or len(nums) <= order.index("H"):
        return None
    h = nums[order.index("H")]
    unit = "mm" if "mm" in str(dim_value).lower() else ""
    return f"{h}{unit}", f"derived as the height axis of the product dimensions (published order {order})"


def make_entry(tab, row, column, field, value, note, source_url=None):
    """A `derived`-tier ledger entry: it carries its note (required for derived),
    is scored 70, and is disclosed in the audit and the SALT map like any value."""
    e = {"tab": tab, "row": row, "column": column, "field": field, "value": value,
         "provenance": "derived", "answer_kind": "value", "note": note}
    if source_url:
        e["source_url"] = source_url
    return e
