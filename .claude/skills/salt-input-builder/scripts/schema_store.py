"""Schema-profile store. A confirmed template column-map is keyed by its header
signature so the same template is recognised next time instead of re-detected and
re-confirmed. A signature mismatch means the template changed: re-confirm.

This is the TEMPLATE schema (column map), not the category/data profile.
"""
from __future__ import annotations
import os
from common import load_json, save_json

INDEX = "schema_index.json"


def _path(store_dir):
    return os.path.join(store_dir, INDEX)


def save(store_dir, schema):
    """Store each tab's confirmed roles/labels under its signature."""
    os.makedirs(store_dir, exist_ok=True)
    idx = {}
    if os.path.exists(_path(store_dir)):
        idx = load_json(_path(store_dir))
    for tab, t in schema.get("tabs", {}).items():
        sig = t.get("signature")
        if sig:
            idx[sig] = {"tab": tab, "roles": t.get("roles"), "labels": t.get("labels", {})}
    save_json(_path(store_dir), idx)
    return idx


def find_by_signature(store_dir, signature):
    if not signature or not os.path.exists(_path(store_dir)):
        return None
    return load_json(_path(store_dir)).get(signature)


def annotate(store_dir, schema):
    """Tag each tab reused (signature seen before) or needs_confirmation."""
    reused = 0
    for tab, t in schema.get("tabs", {}).items():
        hit = find_by_signature(store_dir, t.get("signature"))
        t["reused"] = bool(hit)
        t["needs_confirmation"] = not bool(hit)
        reused += bool(hit)
    return reused


if __name__ == "__main__":
    import tempfile
    d = tempfile.mkdtemp()
    sch = {"tabs": {"Fans": {"signature": "abc123", "roles": {"title": 1}, "labels": {"2": "RPM"}}}}
    save(d, sch)
    assert find_by_signature(d, "abc123")["roles"] == {"title": 1}
    sch2 = {"tabs": {"Fans": {"signature": "abc123"}, "Mobo": {"signature": "zzz999"}}}
    assert annotate(d, sch2) == 1
    assert sch2["tabs"]["Fans"]["reused"] and sch2["tabs"]["Mobo"]["needs_confirmation"]
    print("schema_store self-test passed")
