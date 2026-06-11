# Decision log — compact formatting standard + agent restructure (2026-06-11)

Source: Ant × Chris catch-up 2026-06-11 (transcript) + Christopher's "Structured
ecommerce data schema" workbook (PRODUCT_CATEGORY-DB + Examples tabs). Both
ingested and analysed before any change. Feedback on the Xiaomi tranche: "very
close", with formatting and architecture adjustments required.

## Decisions taken (Atticus escalated once, user decided)

- **A — Adopt Christopher's compact measurement standard as the new house format.**
  Decided: YES (user: "essential"). Measurements are compacted (internal spaces
  removed) so each value is one machine-readable chunk for SALT's schema ingestion.
  Evidence: transcript 00:13:02–00:15:45; schema DB row 17 "Flatten so no spacing".
  Consequence: rewrites CLAUDE.md §6, the standardiser value transform, fixtures.

- **B — Re-architect the standardiser to be schema-driven (field_id → rule table).**
  Decided: YES, staged — high-traffic fields first, expand outward. Evidence:
  transcript 00:18:46 "calling a database to check is far superior to rules in a
  skill"; the workbook is that database.

- **C — Restructure agents to the writer / tester / auditor split.**
  Decided: YES, as a separate piece after the formatting fix lands. Tester is a
  Python harness; the interpreting agent only feeds results back (never writes);
  auditor loses its Write capability; outputs consolidate to one report. Evidence:
  transcript 00:30:56, 00:54:22; "byte-for-byte"/"verbatim" feedback convention.

- **D — Per-field glyph/spacing ambiguity (× vs x, commas, units).**
  Decided: use lowercase `x` as the single separator; apply ONE uniform
  compact-and-standardise rule across the differing artifacts rather than chasing a
  per-field map from Christopher. (Comma policy and per-field units that genuinely
  differ — e.g. cm-native fields, storage speeds with thousands separators — are
  deferred to Stage 2's schema-driven table, not forced globally in Stage 1.)

## Sequencing
A → B (staged) → C. All 139 tests stay green at every step. Work on a fresh branch.

## Stage 1 scope (this branch: claude/compact-formatting-standard-stage1)
- Dimensions: compact to `WxHxDmm`, lowercase `x`, no spaces (cm/m still scaled to mm
  for the required dimension fields, per house format).
- Weight threshold: `<1kg → grams` (no decimals; <0.5 down, ≥0.5 up); `≥1kg → kg`;
  `≥1000g → kg`.
- Compact attached-unit measurements (Hz, GHz/MHz/KHz, Gbps/Mbps, GB/MB/KB/TB, W,
  mAh, nm, ms, DPI, cd/m²) and unitless `NxN` resolutions.
- Temperatures/angles stay spelled out (aligns with the schema's own examples).
- Deferred to Stage 2: full per-field rule table, comma policy, cm-native units,
  char-length and enum/glyph validation (⎓, ², U+0027 apostrophe, MT/s ban).

## Stage 2 backlog (schema-driven validator)
- Key rules on field_id, not loose header substrings. Current `SKIP_VALUE`
  substring "video" wrongly skips GPU fields ("Video memory capacity", "Video base
  clock") so they are never compacted — a field_id table removes this collision.
- Comma policy per field (contrast ratio: none; storage speeds: thousands separators).
- cm-native fields (GPU length/height/width, monitor physical dims) must NOT be
  scaled to mm — keep their unit, only compact. Stage 1 still scales multi-axis cm
  to mm; schema units will override this per field.
- Char-length, enum (single-select), and required-glyph validation: ⎓ in charging
  ports, ² in mm², U+0027 apostrophe (not U+2019) and sentence case in What's-in-box,
  MT/s banned (use MHz). Source workbook vendored at
  references/schema/ecommerce_schema_2026-06-11.xlsx.

## Flagged to Christopher (not silently absorbed)
- Schema DB row 17 labels dimensions "in centimetres (mm)" — contradictory; unit is mm.
- Examples rows 286–301 (coolers, case fans) carry field names only — no rules yet.
- Xiaomi contrast ratio is a genuine unknown → receipt and vendor-ratify, not a format bug.

## Captured workstream priority (not part of this change)
Endorfy and Quinton (Cougar + components) first; Xiaomi third (transcript 00:39:27).
