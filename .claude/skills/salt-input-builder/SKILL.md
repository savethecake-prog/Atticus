---
name: salt-input-builder
description: >-
  Populate a spreadsheet template with fully-sourced, accuracy-verified product
  data to feed SALT (or any downstream listing generator). Use this whenever the
  user wants to fill a product template, prepare marketplace/Takealot/Amazon
  listing INPUTS, build or QA a batch of product rows from manufacturer specs,
  collect verified product attributes into a workbook, or audit an existing
  product sheet for accuracy and provenance. Trigger it for any task of the shape
  "take this template and these products and fill it from authoritative sources,
  accurately" even if the user does not say the words "skill" or "SALT". This is
  an input-fidelity tool: it never generates listings, it collects the cleanest
  possible inputs and records how trustworthy each one is.
---

# SALT input builder

A method for turning a blank product template plus a list of products into a
populated workbook where every value traces to a real source, the trustworthiness
of each row is visible, and an independent audit has re-checked the result. It
feeds SALT; it does not write listings.

The value is not the spreadsheet mechanics. It is the discipline: no value
without a source, blank-and-flag when unverifiable, and an audit run by logic
that does not trust how the data was entered. The scripts make the error-prone
mechanical parts deterministic so they do not depend on getting them right by
hand each time.

## Architecture

A brand- and product-agnostic core plus category profiles built per job.

- Core (`scripts/`): provenance ledger, template schema detection, deterministic
  build, independent audit (including agnostic cross-row checks like duplicate
  identifiers), link liveness, identity matching (`match.py` — links product
  variants to SKUs across two sheets via strong key -> exact model-token blocking
  -> colour/storage gates -> global one-to-one assignment -> abstention; it leaves
  a blank with a reason rather than assert an identifier it cannot prove), and a
  generic rule engine (`profile_engine.py`). None holds brand or category knowledge.
- Synthesis layer (the 2026-06-10 remediation, all agnostic): semantic field
  mapping via a confirmed per-category alias map (`fields.reconcile` with
  `aliases`/`required_fields` — a synonym fills its column instead of spawning a
  duplicate; a synonym of a client-owned required field is dropped); the three-state
  answer model (`answer_kind` value / `absent` "No" / unknown-blank, in `ledger`,
  `confidence`, and the gap taxonomy in `runner.needs_you`); derivation with
  provenance (`derive.py`); the house style guide and ASCII charset (`standardise.py`);
  the Excel-formatting pass (`format_xlsx.py`); the clean delivery copy
  (`delivery.py`, analysis columns stripped, dead columns dropped); tranche
  consolidation into one tab per category (`consolidate.py`); and EAN format +
  uniqueness at audit. The marker string "Not specified" is retired: unknowns are
  blank in delivery and chased via the needs-you queue.
- Category profiles: the data semantics for a category (metric ranges, identifier
  decoders, cross-field rules) are NOT shipped with the skill. They are built per
  job by inspecting the actual product and category data, confirmed by the user,
  saved, and reused only when a later product genuinely matches. See
  `references/category-profiles.md`. The Cougar-fans file under `assets/examples/`
  is an example to copy from, never a default.
- Exporters (sibling sub-skills, e.g. `salt-input-builder-takealot`): specialist,
  isolated skills that load a finished job into one retailer's upload format. A skill
  bundle can hold only one SKILL.md (claude.ai and the Skills API reject more), so the
  exporters are separate skills in this skill's family, sharing the `salt-input-builder-`
  namespace and coordinating through the exporter contract below, not nested SKILL.md
  files. The core stays agnostic; each retailer's quirks live only in its own sub-skill.
  Adding a retailer is adding a new `salt-input-builder-<retailer>` sub-skill. See
  "Exporters".

## How to run a job

Follow `references/workflow.md` in order. The phases are: activation, contract,
template schema profiling, inspect-and-profile (build the category profile from
the data, and DISCOVER the fields the product carries from its manufacturer spec
sheet and corroborating sources, not just from the template, per
`references/category-profiles.md`), sourcing, sourcing review, build, independent
audit, delivery. Read `references/provenance-and-sources.md` before sourcing.
Keep all state in files so a fresh session can resume from disk.

The intake produces a confirmed job spec (`assets/job-spec.template.yaml` is the
shape). Generate it from the brief; have the user confirm it; never make them
hand-author it.

### Commands

```bash
# 1. Detect the template's column map (then confirm with the user)
python scripts/detect_schema.py <template.xlsx> schema.json

# 1b. Discover fields from the sources and reconcile them against the template.
#     Capture the WHOLE published spec table, not a subset: fields.from_spec_table(raw)
#     turns a pasted manufacturer table into one field per row. Then
#     fields.reconcile(schema["tabs"][tab], discovered) proposes: match an existing
#     column, label a blank spare column, or append a new one. Show the proposal,
#     and only after the user confirms call fields.apply(template, schema, tab,
#     decisions) to write the headers and record any appended columns. Record the
#     source field count in schema["tabs"][tab]["source_field_count"] for the gate.

# 2. (after sourcing) validate the evidence ledger; build refuses if it fails
python -c "import sys; sys.path.insert(0,'scripts'); import ledger; \
print('\n'.join(ledger.validate(ledger.load('ledger.json'))) or 'LEDGER OK')"

# 3. Deterministic build from the ledger (scores every cell, holds back the
#    uncorroborated, writes a numeric row confidence)
python scripts/build.py <template.xlsx> schema.json ledger.json out.xlsx

# 4. Independent audit, passing the confirmed category profile for the job
python scripts/audit.py out.xlsx schema.json ledger.json audit_report.md <category-profile.yaml>

# 5. Export the per-cell confidence map SALT gates on
python scripts/runner.py confidence <jobdir>
```

Run them from the skill root with `scripts/` importable. The audit's final
argument is the confirmed category profile (one per category; for a multi-category
job, call the `audit()` function with a `profiles` map of tab to profile).

For the inspect-and-profile phase, `scripts/profile_builder.py` drafts a category
profile from the products' identifiers and the attributes you already know
(`build_profile(category, brand, spec_labels, products)`), returning the draft
plus an evidence report. It infers a decoder only where the data makes the
mapping unambiguous and flags the rest; you confirm before it is used. It is a
drafting aid, not an authority.

### Plumbing and tests

```bash
python tests/run_tests.py                 # run BEFORE trusting any new check/decoder/range
python scripts/runner.py status  <jobdir> # which artefacts exist; phase to resume from
python scripts/runner.py needs   <jobdir> # one consolidated needs-you queue
python scripts/runner.py completeness <jobdir>  # flag products thin on specs (under-capture)
python scripts/runner.py standardise <jobdir>   # propose house-style fixes for review (never auto-commits)
python scripts/runner.py summary <jobdir> # delivery summary (coverage by tier, gaps, flags)
```

The standardise gate enforces one consistent output (dimension/weight format and
units, temperature format, Yes/No casing, UK spelling, controlled brand casing)
and flags what a machine must not change silently (a value in the wrong field, a
long value duplicated across two fields, layout deviations). Because SALT
reproduces the spec table verbatim, any inconsistency on the input lands on the
live listing, so this runs before delivery. It operates as a REVIEW GATE: it
writes a proposed copy and a `standardise_report.xlsx` (every old value, new
value and reason, plus the flags) and never touches the production sheet. The
fixes reach production only via `standardise.py commit <proposed> <production>`
after a person has signed the report off.

Validate the job spec with `jobspec.validate_jobspec(spec)` before a run. Reuse a
confirmed template column-map across jobs with `schema_store` (it keys on the
header signature, so a changed template is re-flagged for confirmation). The test
harness in `tests/` consolidates every module guard and the engine fixture cases
in `tests/fixtures/`; add a case there before trusting a new rule, and a green run
is the gate for shipping any change.

## Non-negotiable rules

These exist because they target specific ways this work goes wrong.

1. **No value without a source.** Every populated cell has a ledger entry.
   Manufacturer/retailer values require a URL and the snippet they were copied
   from. Client identity fields are tagged `client`. Nothing comes from memory.
   This is enforced by `ledger.validate`, and the build refuses to run otherwise.

2. **Copy, do not retype.** The build writes the value from the snippet field.
   The audit diffs the written cell back against the snippet. Undisclosed
   transcription drift is a HARD finding. A value that is not verbatim in its
   snippet but is disclosed with a `doubt_reason` (a legacy or interpreted figure)
   is allowed and reported SOFT - see rule 3.

3. **Write and flag rather than blank; let the score carry the doubt.** Every
   value that has a source is written and scored 0-100 with a detailed reason that
   names the source(s) (`confidence.score_entry`): manufacturer is 90, manufacturer
   plus a second source 97, client identity 85, three agreeing sources 82, two 70,
   a lone uncorroborated source 40, disagreement 35. A value that fails the
   two-source bar (no manufacturer and fewer than two agreeing sources) is still
   written, but marked not-`eligible` and listed in the Check notes so the user can
   verify it or pass it through. Each data cell is shaded by its band; the row
   Confidence is the mean of its cells; the Check notes column lists every cell
   under 85 with its value and reason; a key sheet explains the colours and
   derivation; the per-cell map goes to SALT as `confidence_map.json`. The only
   thing never written is a value with no source at all. "Find enough so SALT does
   not bounce it" must never become "fill to look full" - an unsourced invention is
   the lie that reaches the customer; a low score on a real, sourced value is not.
   A value that exists but may be false - a long-published figure the manufacturer
   no longer lists, an interpreted or contested spec, a value not verbatim in the
   captured snippet - is NOT dropped either. Record a `doubt_reason` saying where it
   comes from and why it may be false; the ledger then accepts it, it is written,
   scored 30 (disputed), and disclosed in the Check notes, the audit (SOFT), and the
   SALT map. Omitting a value because it might be false is itself an error: SALT,
   not this layer, decides whether to admit it.

4. **Never construct a URL.** Only use links returned by a real search or fetch,
   and liveness-check every one before it ships. If the exact variant page cannot
   be confirmed, link the manufacturer's authoritative section for that model and
   say so.

5. **The auditor is not the author.** `audit.py` recomputes from scratch and does
   not trust the build's outputs. Run it every time.

6. **Adaptive gating never lowers the truth bar.** It changes when you interrupt
   the user, not whether an unsourced value may be written. See the "needs you"
   triggers in `references/workflow.md`.

7. **Do not re-introduce known false positives.** The engine guards them: the
   `+-10%` tolerance must not be read as the metric; range values check min/max
   not a single number; colour can live in a body letter not the suffix (the MHP
   case), so a profile says which; manufacturer self-inconsistency is a SOFT flag,
   never a silent pick. Decoders are inferred from the data and confirmed, never
   assumed. Validate any new check against good and bad fixtures before trusting
   it (`references/category-profiles.md`).

8. **No baked brand or category knowledge.** Build the category profile by
   inspecting the data and confirm it; reuse a saved profile only on genuine
   similarity. The skill must work for any brand, category, and template.

9. **Fields come from the sources, not just the template.** When the manufacturer
   lists specs the template does not name, surface them: propose the fields, and
   add columns once the user confirms (`fields.py`). A blank or unnamed column is
   not a reason to drop a real, sourced spec. The template is the output shape; the
   manufacturer's sheet decides what a product carries. Never add a field that is
   not in the sources, and never add one silently.

   Two corollaries. A column whose header MEANS the same as a discoverable spec but
   is not identically named (header "Operating temperature", source "Working temp")
   is still filled into that column; the build records a MAPPING note in the Check
   notes so the placement can be confirmed. And a column that ends up entirely blank
   across every product, including unrelabelled "Spec N" placeholders, is hidden by
   the build (idempotently, never deleted), so the deliverable carries no dead
   columns. Hiding is not filling: nothing is invented to avoid a blank.

   Completeness is enforced, not assumed. The opposite of invention is under-capture:
   a product written with a thin handful of specs when the source publishes many.
   That starves the generator and produces a low-value listing at full cost. Capture
   the complete published table (`fields.from_spec_table`), and before delivery run
   the completeness gate (`runner.py completeness`, also surfaced in the delivery
   summary). It flags any product thin against its richest sibling or against the
   recorded `source_field_count`, and any tab that set up far fewer columns than the
   source published. Treat a thin flag as a defect to fix, not noise to wave through.

## What to deliver and how to talk about it

Hand over the workbook, the audit report, the evidence ledger, and the schema
profile. State coverage, the HARD/SOFT flag counts, and residual risk plainly.

Do not claim the output is correct. Claim what is actually true: every value is
sourced and traceable, every value was independently re-checked, links resolve,
and gaps are marked. That is a strong guarantee. It is not omniscience, and a
wrong manufacturer page can still be wrong. Say so.

## Exporters (the sub-skill family)

The master (this skill) gathers and verifies inputs; SALT writes the listing content; an
exporter loads that finished work into one retailer's official upload artifact. Retailers use
different upload methods, so each gets its own specialist skill rather than one generalist
exporter.

These exporters are separate skills, not folders inside this one. A skill bundle can contain
only one SKILL.md (claude.ai and the Skills API reject multiples on upload; only Claude Code's
local filesystem loads nested skills), so the family is expressed by a shared name prefix and
the contract below, the same way the built-in plugin skills are grouped. The master and each
exporter install alongside each other and coordinate through the job contract.

Available exporters:
- `salt-input-builder-takealot` - Takealot (TAL). Edit Request template for products that
  already have a TSIN; category loadsheet (105 computer-components, 120 gaming) for new
  products. Routing, the encoded rules (title 75 / subtitle 110 / barcode 20 chars, dependent
  category dropdowns), and the field mapping live in that skill's SKILL.md;
  `assets/takealot-formats.json` there holds the distilled spec.

### The exporter contract (every exporter sub-skill honours this)

Input: a finished job (the master's `schema.json` + `ledger.json` + `confidence_map.json`)
and, optionally, the SALT-generated prose (title, subtitle, description, what's in the box).
The retailer's live template/loadsheet is supplied by the user at run time and is the source
of truth; never bundle a retailer template (they change, and a stale copy would mislead).

Output: the retailer's official artifact(s), plus a QA side-report carrying our confidence
and flags so low-confidence or disputed values are visible before submission.

Non-negotiables (inherited from the master, never relaxed by an exporter):
- Write only sourced or SALT-supplied values; leave blanks blank; never invent.
- Preserve the retailer's exact format - sheets, header rows, macros, and every data
  validation - so the file still uploads. Edit a copy of their file in place.
- Enforce the retailer's own rules by reading them from the file (e.g. data validations),
  not from a hardcoded rulebook. A value that fails a rule is flagged, not silently fixed.
- Carry confidence/flags into the QA side-report, not into the retailer's own cells.

To add a retailer: create a new `salt-input-builder-<retailer>` skill (its own SKILL.md,
scripts, a distilled format spec, and tests) that satisfies the contract, and list it above.
The master, the profiles, and the other exporters do not change.

## Extending

- New category or brand: build a category profile by inspection and confirm it
  (`references/category-profiles.md`); save it keyed by category and brand.
- New identifier scheme: add a decoder to that profile, inferred from the SKUs.
- New template: run schema detection once, confirm, and the profile is reused.
- New retailer upload method: add a `salt-input-builder-<retailer>` sub-skill that
  satisfies the exporter contract; do not generalise an existing exporter to cover it.
- The core never changes for any of this.
