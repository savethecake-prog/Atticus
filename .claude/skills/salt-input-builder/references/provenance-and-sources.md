# Provenance and sources

The whole point of this skill is that SALT amplifies whatever it is fed, so the
inputs must be accurate and their trustworthiness must be visible. Provenance is
the mechanism that makes that true rather than aspirational.

## The cardinal rule

A value exists only if it traces to a source. No cell is ever populated "from
the model" or from memory. Every populated cell has a ledger entry, and every
manufacturer/retailer value carries the exact snippet it was copied from. The
build copies the value from that snippet; the audit diffs the written cell back
against it. This is what makes invention and transcription error structurally
hard, not merely discouraged.

If a field cannot be sourced, it stays blank and is flagged. Blank-and-flagged
is a correct outcome. A plausible guess is not.

## Provenance tiers

- **manufacturer** (green): the brand's own official page or spec sheet. Requires
  source_url + snippet.
- **retailer** (orange): a reputable retailer listing, used only as fallback when
  no manufacturer source exists and the listing matches the product's identity.
  Requires source_url + snippet.
- **client** (light blue): the user's own inventory/PIM data, such as their SKU
  or category mapping. A manufacturer page cannot validate these because they
  are the client's to define. Requires a note saying it came from client input.
- **derived** (grey): a formula or computed cell (e.g. the CONCAT listing field).
  Requires a note.

The row's Confidence cell is coloured by the row's most conservative tier, so a
single retailer-sourced field makes the whole row read as orange. That is
deliberate: it tells you and SALT exactly how much to trust the row.

## Authority resolution

Decide which tier a source counts as, in this order:
1. Explicit `manufacturer_domains` / `reputable_retailers` lists in the job spec.
2. The brand's own official domain counts as manufacturer (infer_brand_domain).
3. An allowlisted reputable retailer counts as retailer.
4. Anything else is NOT a source. Forums, marketplaces of unknown quality,
   AI-generated content farms, and aggregators do not qualify.

Maintain the retailer allowlist conservatively. A retailer that merely mirrors a
spec is weaker evidence than the manufacturer and must be coloured as such.

## Links

Every source_url is liveness-checked before it ships (`scripts/linkcheck.py`).
Never construct or guess a URL; only use links returned by an actual search or
fetch. A dead or unverifiable link is a "needs you" item, not something to paper
over. When a model has many variants and the exact variant page cannot be
confirmed, link to the manufacturer's authoritative section for that model
rather than guessing a variant slug, and say so.

## Honest limit

This guarantees sourcing, traceability, and independent re-checking. It does not
guarantee the source is correct. Manufacturer pages can be wrong or internally
inconsistent (we have seen a spec-table weight disagree with a packing-net
weight on the same page). Those become SOFT flags for human resolution, never a
silent pick.
