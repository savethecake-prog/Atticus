# SALT input builder: build constitution

The always-true operating knowledge for the SALT input preparation workstream. Intended as the repo CLAUDE.md and the rules every agent inherits. Concise on purpose: every line is a durable decision, not background. The full error log lives in SALT_input_builder_LEARNINGS.md; this consolidates it and adds everything learned since.

---

## 0. The one fact that drives everything

SALT reproduces the input spec table verbatim. Its first integrity gate is specs-in equals specs-out, so whatever is on the input row prints to the live listing, including any error or formatting inconsistency. Each listing costs money and is client facing on Takealot. Therefore input fidelity is the entire job. We are not writing listings, we are handing SALT something we can stand behind.

A real example we traced: a chair's recline value sitting in the "Max seat tilting angle" input field passed straight through into the published listing. The value was present, it was just in the wrong field. Placement is correctness.

---

## 1. Non-negotiable principles

- Blanks over guesses. An unsourced field is left empty or marked, never invented.
- No value without a source. Every spec traces to a live page; manufacturer first, code-matched retailer mirror only where the manufacturer does not publish or cannot be fetched, and record which.
- Never assert an identifier you cannot prove (the GEX750 shared-SKU lesson). Identifiers come from the source of truth, never from a model.
- Placement is correctness. A value in the wrong named field is a wrong value. Never append to the end of a row.
- Capture the full published table, not a hand-picked subset. Under-capture is a defect, not a style choice (the 632-versus-1037 lesson).
- Flag conflicts, do not silently resolve. Record both values, use the manufacturer value, surface the discrepancy.
- The auditor re-derives, independent of the builder.
- Brand and product agnostic. Field sets are inferred from the source and confirmed, never hard-coded.
- Provenance and confidence travel with the data.
- Nothing from model memory. Product facts are sourced fresh every time.

---

## 2. The output contract (house format)

Column order on every tab:

1. Title
2. What's in the Box
3. Category spec columns (headers carry a trailing ": ")
4. The thirteen required fields, in this exact order: Operating temperature, Product colour, Product dimensions, Product weight, Packaging dimensions, Packaging weight, Brand, SKU, Model number, EAN, TSIN, Warranty, Category. All carry a trailing ": " except Category, which is bare.
5. Commercial columns trailing after Category where present (Status, Qty, PL2 ExVAT (R), RRP (R)).

The delivered copy carries no analysis columns (Confidence, Check notes, Source). Those live in the working ledger, not the handoff.

The thirteen required fields are the Takealot required set and must be present on every category, every batch.

---

## 3. Blank, marker, and identifier conventions

- Required field not applicable to the category: leave blank. SALT drops empty not-applicable fields (for example operating temperature on a desk, a mouse, a chair). A blank here is correct, not a gap.
- Required field applicable but not found: mark "Not specified". This is the to-chase signal.
- Identifiers (EAN, TSIN) missing: leave blank, never a prose marker. A barcode field with text in it is worse than empty. A blank TSIN is expected for a new product, because no-TSIN products route to the loadsheet rather than an Edit Request.
- Variants: inherit the base specs explicitly, change only what differs (colour, keycaps), leave variant-specific identifiers for confirmation.

---

## 4. What SALT does to the input (so the prep accounts for it)

- It reproduces the spec table verbatim. Format the input the way it should read on the listing.
- It drops required fields that are blank and not applicable.
- Keywords are SALT-generated and localised (currently South Africa), not an input field. Do not source or supply keywords.
- Title and subtitle limits (title 75, subtitle 110 characters) are generation and upload limits, not input fields. Observed generated subtitles have run over 110; that is a generation-side issue to raise with the SALT team, not something the input controls.

The handoff: we deliver the clean input sheet, the SALT team runs it through Musashi SALT 2.0, and SALT returns the listing content.

---

## 5. Sourcing rules

- Source per product code, manufacturer first, capture the whole published spec table.
- Datasheet to field mapping: Net weight maps to Product weight, Gross weight maps to Packaging weight, Package size maps to Packaging dimensions.
- Genuinely unpublished cases stay marked with the reason rather than guessed: the syringe or container dimensions of pastes and putties (only package size is ever published), operating temperature where a datasheet omits it (for example Duronaut, Thermal Putty), and the Minus Pad Basic weights and packaging.
- Some manufacturer datasheets surface in search and some do not, and retailer pages do not carry net, gross or package figures. Do not burn effort hammering pages that do not hold the data. Source what is provable, mark the rest, raise it.
- Identifiers come from the distributor's master data (the source of truth), not from web-scraping variant barcodes, which is exactly where a wrong barcode lands on the wrong variant. Model number can be derived from the product title where the title states it, flagged as title-derived for confirmation.

---

## 6. The standardiser review gate

Runs before delivery. It proposes fixes and writes a change report; it never writes to production until a person signs off (propose, review, commit).

- Auto-fixes, value-preserving only: dimensions to "W x D x H mm" (cm and m scaled to mm), weights to "N kg" or "N g", temperature to "-X to +Y °C", Yes/No casing, UK spelling, controlled brand casing.
- Flag-only, never auto-changed: placement (a recline value in a seat-tilt field, a long value duplicated across two fields), layout (column A is not Title, analysis columns present), and a unitless value in a dimension or size field.
- Hard lessons that keep the flags trustworthy: the unitless-dimension check fires only in dimension or size headers, never on resolutions, slot counts or connector names that happen to contain an "x"; the not-found markers are excluded from duplicate-value detection or they spam placement flags; duplicate flags are deduped to one per column pair; prose fields and long cells get spelling only, never numeric reformatting. A review gate that cries wolf is ignored, so every flag must be real.

---

## 7. Aligning a category to a minimum standard

When a category has an agreed minimum standard (the Batch-02 sets for PC cases, CPU coolers, fans, chairs), align to it without losing data:

- Apply only certain renames (for example GPU clearance to Max GPU length).
- Add any standard field the category lacks and mark it.
- Keep every existing extra field; the result is a union, nothing is dropped.
- Flag uncertain matches for human confirmation rather than forcing them, because a forced uncertain rename writes a value into the wrong field, which is the failure we are guarding against.

---

## 8. Marketplace export (Takealot)

- A product with a TSIN routes to the Edit Request. A product without a TSIN routes to the category loadsheet (105 computer components, 120 gaming).
- The global category lookup gives the loadsheet; main and lowest category come from the Category Tree Lookup; values are constrained by the Lookup tabs (Brand, Materials, CPU Type, Card Series, Country of Origin on 105; Game Designers, Game Genres on 120).
- Limits: title 75, subtitle 110, barcode 20 characters.

---

## 9. Verification discipline (the auditor's checklist)

Run at the end of a job, re-deriving rather than trusting the build:

- Coverage: the SKU set in equals the SKU set out, none missing, none extra, none duplicated.
- Data preservation: every source value appears in the output for the correct product, none lost or moved to the wrong field.
- Identity and price fidelity: zero mismatches on SKU, TSIN, brand, quantity, cost, RRP.
- EAN format and uniqueness: valid, not shared across different SKUs.
- Governance: every row carries provenance and confidence in the ledger.
- Gate re-run: completeness and standardise come back clean.

Proven shape from the Endorfy job: 67 SKUs, 1606 source values, zero lost, zero misplaced.

---

## 10. Boundaries and the human decisions

- Green tabs (anything the client or the SALT team is running) are never edited. Issues on them are raised separately, not silently fixed.
- The decisions that genuinely need a human, batched into one review per job with a proposed default for each: uncertain field matches, source conflicts, which identifiers to pull versus park, ambiguous marker conventions, and tab ownership. Everything not in that review has already passed a deterministic gate.

---

## 11. The workflow

Read the inventory and fix the authoritative identity and price columns. Group products by comparable type and order the tranches, smaller coherent groups first. For each tranche, source per code (full table, manufacturer first), build into the house format placing every value in its named field, leave blanks and markers per the conventions, run the completeness gate. Consolidate. Run the standardiser review gate. Verify against the inventory. Deliver the input sheet. The SALT team runs Musashi SALT 2.0 and returns the listing content.
