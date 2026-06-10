# Build spec — SALT input-builder remediation (2026-06-10)

Author: Atticus. Trigger: Chris's review of the Endorfy Batch-03 delivery (the Gaming chair
as the worked example), plus a full re-survey of the current persona, agents, tooling and
docs. Method: re-derived from the artifacts and the code, not from memory of either.

This is a **design spec**, not a build. Nothing here is implemented yet. Formal validation is
deferred to fresh data; the Endorfy chair is a diagnostic reference and an internal acceptance
golden, not the test set. Each workstream still carries a verifiable success criterion so the
build can be checked as it lands.

It is written in Karpathy's discipline: assumptions stated, the simplest sufficient approach
chosen, changes surgical (touch only what is broken), and every item given a checkable goal.
Where a simpler reading of the problem exists, it is named and preferred.

---

## 0. North star — what this system is for

The job is to ingest products and templates that vary **wildly** — across products, across
categories, and across clients, each presenting their data and their template differently — and
synthesise them into one standardised, correct input that SALT reproduces verbatim onto a live
listing.

Two facts set the bar. SALT reproduces the input verbatim, so the input *is* the listing. And
**every incorrect input costs $3.99 per failed product** — the cost function we are minimising at
scale. A "failed product" is the unit: a row that causes SALT to produce a wrong or rejected
listing.

The response to that cost is **excellence, not fear.** The expensive failure is not only the wrong
value that ships — it is equally the *correct value we left blank because we were timid*.
Over-blanking fails the product just as surely; it merely fails it quietly. So the design
**maximises correct fills** — map every synonym, derive every obvious value, capture the whole
published table — and reserves a blank for the genuinely unknowable alone. "Blanks over guesses"
never meant "blanks over the sourced answer."

Three commitments follow, and every workstream serves them:

- **Agnostic by construction.** The core holds no brand, category, or template knowledge; all of it
  lives in per-job configuration (schema profile, category profile, alias/mapping map) built by
  inspection and confirmed once. A new client or category is *config, not code, not conversation.*
- **Correctness-maximising.** Map, derive, and source aggressively; blank is the last resort, never
  the default. This is precisely what the three-state model buys: *value*, sourced-*"No"*, and only
  then *unknown*.
- **Refuse to ship a likely failure.** A deterministic per-product **SALT-readiness verdict**
  re-derives each row and will not pass one that would cost us $3.99 — composing the completeness,
  audit, identifier and style gates into one ship/hold decision. That is how the cost becomes a
  design target instead of a worry: the gate is the wall.

Elegance here is the single general pipeline. Excellence is the readiness bar, quantified.

---

## 1. The locked decisions (from the user, this session)

These are settled and bind the build. They are not re-opened here.

- **Absence rendering — three states.** A field is one of: *value present* → the value; *feature
  provably absent* (not in the complete captured table) → **"No"** (sourced by absence, flagged
  if the table's completeness is uncertain); *genuinely unpublished* → **blank in the delivery
  copy** (a working-copy marker is allowed, the delivered cell is blank).
- **Ownership / override.** The client (TechTraders export) stays authoritative for **Category,
  identity (SKU/EAN/TSIN), and price**. Everything descriptive — Title, What's in the Box,
  colour, specs, dimensions, weights — is mapped to the manufacturer-canonical value where we
  understand the fields to be the same; **flag for human-in-the-loop where we are unsure**, never
  force.
- **Mapping + derivation.** Map synonym fields onto the target schema; derive obvious values
  (colour-from-title, net/gross → product/packaging, total-height-from-dimensions) **with recorded
  provenance and a confidence score**. No silent invention; uncertain matches and derivations are
  surfaced, not forced.
- **Style guide adopted.** No-space units (`520mm`), `x` for dimensions, angles/temperatures
  spelled out (`100 to 125 degrees`), an ASCII-safe charset, Oxford comma with a final `, &`, `&`
  between two items, `1 x` quantities, socket-noise like `AM3(+)` **flagged, not auto-stripped**.
- **Excel formatting — the written spec.** Row height 30; columns A and B width 45, all others
  16; every cell wrap + vertical-centre; header row horizontal-centre + bold; body left; all
  borders on the data range.
- **What's in the Box was invented.** Treat as a fidelity breach: re-source from the
  manufacturer's box-contents / "Set includes", blank where unpublished, never infer.

---

## 2. The two findings that reframe the work

The deep survey turned up two things that matter more than any single defect, because they
explain why a careful pipeline still shipped the chair wrong.

### Finding A — the method is split three ways and the agents follow the weakest copy

There are three statements of "the method" in this repo and they disagree:

| Source | Marker model | Synonym mapping | Binds whom |
|---|---|---|---|
| `CLAUDE.md` §3 | **two-state**, `"Not specified"` written into the cell | not mentioned | **the agents** (they inherit slices of CLAUDE.md) |
| `SKILL.md` / scripts | write-and-flag, three confidence bands, **hide blank columns**, `fields.reconcile` | rule 9 corollary maps a synonym into its column | the Python tools |
| `references/workflow.md` | two-state (sourced-value vs blank-and-flagged), **no marker string at all** | reconcile in phase 4 | the documented flow |

The subagents inherit a **named slice of CLAUDE.md and nothing else** — verified directly:
`builder.md:9` "Inherit CLAUDE.md. Your slice is section 2, section 3 and section 7";
`builder.md:14` "blank for not-applicable required fields; 'Not specified' for
applicable-but-not-found". No agent file references `SKILL.md` or `workflow.md`. So the agent's
behavioural floor is the **two-state, marker-in-the-cell, append-tolerant** convention — the
oldest and weakest of the three — even though the scripts implement the richer model. The chair's
"Not specified" cells, its duplicate columns, and its missing "No"s are the predictable output of
that binding.

**Implication:** the first fix is not an algorithm, it is **coherence**. One authoritative method,
and the deterministic scripts (not agent prose) own placement, marker and mapping so behaviour
cannot drift back to the weak floor.

### Finding B — the Phase A+D modules are written but unwired

`match.py` (266 lines), `common.classify_gap` + `GAP_KINDS`, and `common.header_map` / `lookup`
/ `nkey` / `norm_value` have **no caller in the pipeline**. `build.py` and `fields.py` never
import them. They pass their unit tests in isolation; they do nothing to a real job. The previous
"Phase A + D delivered" claim was true at the unit level and false at the integration level.

**Implication, and a lesson fed back into the method:** *delivered* must mean **wired and proven
end-to-end**, not unit-green. The auditor must re-derive through the actual pipeline, not trust a
green unit suite. Several capabilities this spec calls "build" are really "wire what already
exists" — cheaper and lower-risk than a rebuild, and the honest description.

---

## 3. Disposition per subsystem — keep / improve / build

The temptation is to rebuild the mapping engine. The simpler truth, given Findings A and B, is
that the architecture is sound and mostly **under-bound and under-wired**. Dispositions:

| Subsystem | Call | Why |
|---|---|---|
| Atticus persona / decide-do split / agent roster / tool scoping | **KEEP** | Sound. The orchestration design is not the problem; its binding to the weak method is. |
| Ledger model, validation, conflict comparator | **KEEP** | Correct and tested. Extended (not replaced) for the "absent" state — see W0. |
| Confidence bands | **KEEP + extend** | Band model is good; it lacks a "sourced negative" branch. Add one, don't replace. |
| Independent auditor (`audit.py`), propose→review→commit standardise gate | **KEEP** | The two safeguards that work. Audit gains EAN integrity + must re-derive end-to-end. |
| `detect_schema`, `schema_store`, `jobspec`, `profile_engine`, `profile_builder`, `linkcheck` | **KEEP** | Each does one job correctly. No change required by this build. |
| Takealot routing + read-rules-from-live-file | **KEEP** | Right design. Writers remain stubs — out of scope (§8). |
| `fields.reconcile` (token-Jaccard auto-append) | **IMPROVE** | The duplicate-column engine. Replace the auto-append with a confirmed per-category alias map; flag-not-append on miss. (W1) |
| `build.py` marker/fill logic | **IMPROVE** | Add three-state fill; marker → blank in delivery so hide-blank works again. (W2) |
| `completeness.py` | **IMPROVE** | Blind to a lone-product category — exactly why the chair passed at 17 specs/93%. Fix the baseline. (W9) |
| `standardise.py` | **IMPROVE** | Add the style guide + charset; split marker rendering. (W5) |
| `sourcer` instruction + `from_spec_table` | **IMPROVE** | Must capture the logistics block + linked PDFs, not just the on-page table. (W4) |
| The three method docs + agent bindings | **IMPROVE** | Unify into one doctrine; bind agents to it; wire the dead modules. (W10) |
| Three-state data model (the "absent"/negative state) | **BUILD** | Does not exist; several capabilities depend on it. The keystone. (W0) |
| Derivation transformers | **BUILD** | The `derived` provenance slot exists end-to-end; the transformers that fill it do not. (W3) |
| Excel-formatting pass | **BUILD** | No formatting capability exists anywhere in the system. (W6) |
| Tranche consolidation / merge | **BUILD** | No code merges same-category tranches; the source of "Keyboards (again)". (W7) |
| What's-in-the-Box sourcing rule | **BUILD** | No field-specific sourcing instruction; the invention gap. (W8) |
| EAN format + uniqueness check | **BUILD** | `audit.py` dedupes SKU only; CLAUDE.md §9 calls for EAN. (W9) |

No subsystem is marked REBUILD. The honest shape of this work is *unify, wire, extend, and add six
genuinely-missing passes.*

---

## 4. Workstreams

Each: goal · approach (simplest sufficient) · files · success criterion · dependencies.

### W0 — Three-state data model *(keystone; everything depends on it)*
- **Goal:** represent *value present* / *sourced-absent (No)* / *unknown* as first-class states.
- **Approach:** add an `answer_kind ∈ {value, absent, unknown}` field to the ledger entry
  (default `value`), not a new provenance tier — keep `TIERS` as the source axis. An `absent`
  entry carries its source (the complete table), a note ("not present in the complete published
  spec table"), and a completeness-confidence; `confidence.score_entry` gains an `absent` branch.
  Wire `common.classify_gap` so `runner.needs_you` distinguishes derivable / web-targetable /
  structural-absent / unknown instead of flattening every blank into one count.
- **Files:** `ledger.py`, `confidence.py`, `common.py` (wire `classify_gap`), `runner.py`.
- **Success:** the chair's six honest negatives carry `answer_kind=absent` and render "No";
  net/gross blanks surface as *web-targetable → chase*, not as undifferentiated gaps.
- **Depends:** none.

### W1 — Semantic field mapping *(fixes the duplicate columns, the Product type↔Category clash)*
- **Goal:** map a manufacturer field onto the target column that means the same thing; never
  append a silent duplicate.
- **Approach:** reconcile order becomes (1) exact/normalised header match; (2) **per-category
  confirmed alias map** stored in the category profile (`{target_field: [synonyms]}`, confirmed
  once, reused only on genuine match); (3) `common.lookup` as the runtime mapper; (4) on miss →
  **flag for HITL, never append**. `Product type` is recognised as the same axis as `Category`
  (client-owned) → mapped or flagged, never a second column. No ML, no fuzzy library — a confirmed
  data map plus the existing string primitives.
- **Files:** `fields.py` (`reconcile`), category profile (alias map), wire `common.header_map`/`lookup`.
- **Success:** zero duplicate synonym columns on the chair and CPU coolers; `Tilt function↔Tilt
  mechanism`, `Colour↔Product colour`, `Gas lift safety class↔Gas lift` collapse correctly;
  uncertain matches appear in the decision report, not in the sheet.
- **Depends:** none (composes with W0 for the marker side).

### W2 — Three-state fill + marker hygiene
- **Goal:** write values; render "No" for sourced-absent; leave unknown blank in delivery.
- **Approach:** `build.py` reads `answer_kind`: `value`→value, `absent`→"No" (or the field's
  negative form; flag if completeness uncertain), `unknown`→working-copy marker, **blank in the
  delivery copy**. Blank-in-delivery re-enables `_hide_blank_columns` (a "No" is real data and
  stays; an unknown blank hides the dead column).
- **Files:** `build.py`, delivery-copy step.
- **Success:** the chair's delivery copy contains no "Not specified" text; dead columns hidden;
  absent features show "No".
- **Depends:** W0.

### W3 — Derivation transformers *(slot exists; the code does not)*
- **Goal:** fill obvious values from other sourced fields, with provenance.
- **Approach:** a small `derive.py` with explicit, listed transforms — net→Product weight,
  gross→Packaging weight, package-size→Packaging dimensions, colour-from-title (reuse
  `match.parse_colour_storage`), total-height from the product-dimensions H. Each emits a
  `derived`-tier ledger entry with a note + confidence (the slot already scores `derived`=70 and
  marks it eligible). A value that lands identically in three height-ish fields, or any derived
  value, is **flagged HITL**, not silently triplicated.
- **Files:** new `derive.py`, `ledger.py` entries, `build.py` integration.
- **Success:** chair net/gross, colour, and total-height present, each marked `derived` with a
  source note; beats Copilot's first pass (which left packaging blank).
- **Depends:** W0 (uses provenance), W1 (writes into the mapped column).

### W4 — Sourcing completeness: logistics block + datasheet
- **Goal:** stop net/gross under-capture at the source.
- **Approach:** the sourcer instruction and `from_spec_table` must capture the **logistics /
  packaging block and any linked PDF/datasheet**, not only the on-page accordion; `from_spec_table`
  accepts multiple blocks / pasted PDF text. The gap taxonomy (W0) marks packaging dims/weight as
  *expected for boxed goods* so a blank there is a chase signal, not silence. Net/gross→template
  mapping moves from CLAUDE.md §5 prose into the binding method (W10) and the derivation list (W3).
- **Files:** `sourcer.md`, `fields.from_spec_table`, `workflow.md`, the gap taxonomy.
- **Success:** the chair's packaging data is captured at source (provable in the ledger), not only
  reconstructable by derivation.
- **Depends:** W0 (taxonomy).

### W5 — Style guide + charset
- **Goal:** one consistent, SALT-safe rendering of every value.
- **Approach:** encode the adopted rules in `standardise.py`: no-space units, `x` dims, spell-out
  angles/° , ASCII-safe charset (smart→straight quotes, `×`→`x`, drop ™®©, `°`→ degrees),
  Oxford comma + final `, &`, `&` between two items, `1 x`, socket-noise **flagged not stripped**;
  prose fields get the list-style rules. Ship a short human-readable `STYLE_GUIDE.md`. Marker →
  blank in the delivery copy is handled here too (overlaps W2; one owner).
- **Files:** `standardise.py`, new `STYLE_GUIDE.md`, `standardiser.md`.
- **Success:** the chair renders in the house style end-to-end; one open sub-decision parked for
  ratification — whether operating-temperature keeps `°C` or spells out "degrees Celsius".
- **Depends:** none.

### W6 — Excel-formatting pass *(new)*
- **Goal:** a standardised, legible workbook.
- **Approach:** a new `format_xlsx.py` applied to the **delivery copy only**: row height 30;
  columns A & B = 45, others = 16; wrap + vertical-centre everywhere; header row centre + bold;
  body left; all-borders on the data range. Idempotent, value-touching nothing.
- **Files:** new `format_xlsx.py`, delivery step.
- **Success:** the delivered workbook matches the formatting spec exactly and reproducibly.
- **Depends:** W7 (format after consolidation).

### W7 — Tranche consolidation / merge *(new)*
- **Goal:** one tab per category, no lost rows, no duplicate tabs.
- **Approach:** a consolidation step that groups tranche outputs by **category identity** (not by
  exact schema), unions the columns (CLAUDE.md §7 "union, nothing dropped"), and merges rows into
  the single category tab. Kills "Keyboards (again)".
- **Files:** new consolidation step (orchestrator-owned), schema union helper.
- **Success:** the full Endorfy workbook has exactly one tab per category, columns unioned, every
  source SKU present once.
- **Depends:** W1 (so the union maps synonyms rather than stacking duplicates).

### W8 — What's-in-the-Box fidelity
- **Goal:** never invent box contents.
- **Approach:** a field-specific sourcing instruction — source from the manufacturer's box-contents
  / "Set includes"; blank if unpublished; never infer; render `1 x Item` newline list. The auditor
  treats it as a fidelity-checked field: an unsourced box-contents value is a HARD finding (the ten
  red-flagged cells were invented).
- **Files:** `sourcer.md`, `builder.md`, `audit.py`.
- **Success:** the ten red cells are re-sourced or blanked; the audit flags any box-contents value
  lacking a ledger source.
- **Depends:** none.

### W9 — Completeness blind-spot + EAN integrity
- **Goal:** catch a thin lone product, and catch a bad barcode.
- **Approach:** `completeness.py` baseline becomes `max(richest sibling, source_field_count,
  category-expected-field count)` so a single-product tab is still measured against what the source
  published, not against itself. `audit.py` gains an EAN check-digit + uniqueness pass (C7); fold
  the duplicated `_sourced_columns` / `_sourced_cols` into one helper while in the file (only
  because the change is already touching it — not a standalone refactor).
- **Files:** `completeness.py`, `audit.py`.
- **Success:** a lone thin product (the chair, had it been thin) is flagged; a malformed or shared
  EAN is caught before export.
- **Depends:** none.

### W10 — Method unification, agent binding, wiring *(the coherence fix; do early)*
- **Goal:** one method, the scripts authoritative, the dead modules live.
- **Approach:** reconcile CLAUDE.md §3 ↔ SKILL.md rules 3/9 ↔ `workflow.md` into **one doctrine**
  (three-state, write-and-flag, marker-in-working-only, synonym-mapping, completeness). Make the
  deterministic scripts the authority for placement/marker/mapping; **bind `builder`/`sourcer`/
  `standardiser` to the skill** (reference the authoritative rules, or have the orchestrator drive
  the scripts) so agent prose cannot diverge. Wire `match.py`, `classify_gap`, and `header_map`/
  `lookup` into the real pipeline and cover each with an **integration** check, not a unit one.
- **Files:** `CLAUDE.md`, `SKILL.md`, `references/workflow.md`, the three agent files, `build.py`/
  `fields.py` (wiring).
- **Success:** an agent cannot produce a two-state/duplicate-column result; the previously-dead
  modules are invoked on a real run and proven by an end-to-end re-derivation.
- **Depends:** conceptually first; lands alongside W0–W2.

---

## 5. Sequencing and "ready for testing"

Ordered by dependency × risk, smaller coherent pieces first:

1. **W0 + W10** — the data model and the coherence fix. Nothing else is safe to build on a split
   method and a missing state.
2. **W1 → W2 → W3 → W5** — the chair-critical core: map, fill three-state, derive, style.
3. **W4, W6, W7, W8, W9** — sourcing completeness, formatting, consolidation, box fidelity,
   integrity.

Every change lands behind **propose → review → commit**; nothing reaches a delivery file without
sign-off. **"Ready for testing" means:** all workstreams built *and wired* (Finding B's lesson),
and the Endorfy chair reproduced as an internal acceptance golden — it maps every field with zero
duplicate columns, renders the three states correctly, carries net/gross with provenance, and
matches the style and formatting specs. That golden is a readiness check, **not** the test. The
formal validation runs on the **fresh data** the user will supply, against these same criteria, so
the result is not overfit to the one chair. The fresh-data set should deliberately span **multiple
categories and at least two client templates**, because the real bar is generality across wild
variance, not one product done well. And the last thing before any delivery is the per-product
**SALT-readiness verdict** (§0): a re-derived ship/hold decision so a row that would cost us $3.99
is held and surfaced, never shipped.

---

## 6. What this build deliberately does NOT do *(Karpathy: no speculative scope)*

- No paid spec API and no vendored datasets (the resolve-before-fetch idea stays; the dataset does
  not — consistent with the 2026-06-09 decisions).
- No ML / learned matcher. A confirmed per-category alias map plus the existing string primitives
  is sufficient at this scale.
- No Takealot writer build. The two artifact writers stay stubs until the input side is fixed;
  exporting a still-broken input is the wrong order.
- No refactor for its own sake. The three duplicated normalisers and the unused `import copy` are
  noted; only the one duplication already in a touched file (W9) is folded in. The rest is left.
- No new tranche-orchestration cleverness; consolidation is the one missing step, nothing more.

---

## 7. Lessons fed back into the method

- **Delivered = wired + integration-proven**, never unit-green alone. The auditor re-derives
  through the real pipeline.
- **One authoritative method.** Three disagreeing copies is how the weak one wins. The agents bind
  to the doctrine, and the deterministic scripts hold the line so prose cannot drift.
- **A blank is honest only when the value is truly unknown.** A value sitting under a synonym, or
  derivable from a sourced field, or a feature provably absent, is not an honest blank — it is a
  missed map, a missed derivation, or a missed "No". "Blanks over guesses" never meant "blanks over
  the sourced answer."

---

## 8. Decision for the user

One call before build: **approve this sequence (W0+W10 → core → the rest), or redirect.** The two
parked sub-decisions (operating-temperature `°C` vs spelled-out; final confirmation of the formatting
widths against your written spec) ride along to the standardise/format commit gate and do not block
the start.

---

## Build status — 2026-06-10 (delivered, pending end-to-end proof)

All ten workstreams built and unit-tested. Suite: **118 passed, 0 failed** (was 73); every module
imports clean.

- **W0** three-state model (`ledger`/`confidence`/`common.ANSWER_KINDS`; gap taxonomy wired in `runner.needs_you`).
- **W1** semantic mapping (`fields.reconcile` alias map + required-field drop + uncertain flag).
- **W2** clean delivery copy (`delivery.py`).
- **W3** derivation with provenance (`derive.py`).
- **W5** house style guide + ASCII charset (`standardise.py`).
- **W6** Excel-formatting pass (`format_xlsx.py`).
- **W7** tranche consolidation, one tab per category (`consolidate.py`).
- **W8** What's-in-the-Box fidelity (sourcer instruction + the audit orphan check already makes an
  unsourced box-contents value HARD).
- **W9** completeness lone-product flag + EAN format/uniqueness (`completeness.py`, `audit.py`).
- **W10** method unified: `CLAUDE.md` section 3 rewritten to three states; `builder`/`sourcer`/
  `standardiser` rebound; `SKILL.md` updated.

**Honest caveats (Finding B's own lesson: delivered = wired + integration-proven).** What is proven
is unit-level and import-level. NOT yet proven end-to-end: a full pipeline run reproducing the chair's
golden target. The per-job invocation of `derive`, the alias map, `consolidate`, `delivery` and
`format_xlsx` is the orchestrator's at run time (the agentic design drives the scripts). `match.py` is
documented as the identity-join step but is invoked situationally, not auto-wired into `build`. The
end-to-end proof is the fresh production-content test, against the §0/§5 criteria.
