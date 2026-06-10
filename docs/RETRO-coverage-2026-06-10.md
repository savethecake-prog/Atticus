# Retrospective — the coverage-blank escapes (2026-06-10)

Author: Atticus. Two errors on the Infinity/Xiaomi job, both caught by the user reading the
deliverable, neither by any gate. Recorded and fixed per the constitution: own it, feed it back,
improve the system rather than rely on vigilance.

## What escaped
1. **Colour depth / Contrast ratio: 0/33, narrated as "phone-makers do not publish these."** They were
   empty because I hand-listed the Phase-2 sourcing brief and dropped two of the 29 target columns. When
   sourced, colour depth filled 18/33 — it was never unpublished, just never attempted.
2. **The 10 Xiaomi rows: 0/9 on the appended identity columns** (Model number, SKU, EAN, TSIN, Category,
   Product colour, What's in the Box, Package dims/weight), narrated as "spec-only, left as provided" —
   while every one of the 33 brand rows carried them. Category and box contents were trivially available;
   I dismissed the whole block.

## Root cause (the generalisable form)
- **An unknown laundered into a sourced negative.** The three-state model (value / sourced-absent /
  unknown) has a hole: "unknown-blank" silently contains *searched-and-absent* and *never-searched*. I
  narrated the second as the first. A negative claim needs evidence exactly as a value does.
- **Scope hand-listed, not derived from the contract.** The target schema is the contract; the sourcing
  brief should be a function of it. Typed by hand, a silent omission was possible.
- **No coverage gate.** `completeness` flagged thin rows and under-discovered tabs, but nothing flagged a
  target column empty *everywhere* (escape 1) or a row blank on a column its *siblings fill* (escape 2).
  `build._hide_blank_columns` actively *hid* the all-empty column instead of raising it.

## The fix (landed, tested — 125 green)
- **`completeness.column_coverage`** — the two-dimensional gate: flags (a) a non-structural target column
  empty across every product, and (b) a row blank on a column filled for ≥ half its siblings. Structural
  blanks (a pre-listing TSIN) are skipped. It does not guess *why* a cell is empty; it refuses to let an
  empty pass silently — forcing fill, a sourced-absent **with evidence**, or a justification.
  Regression test encodes both escapes.
- **CLAUDE.md** — new principle: *No absence without a search* (§1), and the column-coverage check added to
  the auditor's checklist (§9). Sourcing scope is derived from the target schema, never hand-listed.

## Remaining (honest)
Two stronger guarantees depend on finishing the **schema-driven build** (the Phase-B lift the rebuild only
partly closed), so a job can't run a bespoke build that skips the gate: (1) the sourcing brief enforced as
schema ⊇ web-targetable columns, and (2) the decision-report builder reconciling every "absent" claim
against an attempt log. Until then, `column_coverage` is run explicitly as part of the audit step, and the
Infinity/Xiaomi job's remaining blanks (the Xiaomi SKU/EAN/package — no distributor master) are recorded in
its vendor request, justified, not hidden.

## The pattern that matters
Both escapes were the *same* failure in different fields, and both were caught by a human. That is the
definition of a missing gate. The cost model is unforgiving — $3.99 per failed product — and a blank we
could have filled fails the product as surely as a wrong value. The gate now holds that line.

## Update (2026-06-10, later) — the symmetric enforcement
It happened twice more (Xiaomi identity, then package — both sourceable from mi.com). The column-coverage
gate flagged them, but I overrode the flag with prose ("vendor-only") — because a *value* needs a source
while a *negative* needed nothing. That asymmetry was the real leak. Closed it: a `deferred` record (we
tried, it is vendor-only / unsourceable) now requires a `search_receipt` — the searches that came back
empty — exactly as a value requires a `source_url`; and `completeness.coverage_closure` is a delivery gate
that blocks any blank cell that is neither filled nor closed by a sourced `absent` or a receipted
`deferred`. A negative can no longer be asserted by reasoning alone. Suite: 130 green. The fuller reflex
(the gate auto-running the search on each flag) still awaits the schema-driven build + a fetch-cache.
