# Retrospective & improvement plan — Infinity job (2026-06-09)

Author: Atticus. Method: re-derived from the decision log and the actual run, not from
memory of it. The point is to feed lessons back into the method, per the constitution.
This document is framework-level (no client data); the examples are lessons, as the
GEX750/Endorfy lessons already are in CLAUDE.md.

---

## 1. What the job actually was

A *consolidation-and-mapping* job: take 12 heterogeneous client workbooks (5 brand spec
masters on a shared "Infinity" schema, 5 marketplace listing exports, 1 Xiaomi template)
and produce one workbook mirroring the Xiaomi spine + golden fields, every value sourced,
gaps marked and chased. 50 products, 4 tabs. Delivered with 0 HARD audit findings.

This is **not** the job the salt-input-builder skill was built for. The skill fills one
house-format template per product from web sources. Today's job mapped many source schemas
onto an arbitrary target schema and joined a second set of files for identity. That mismatch
is the root of most of what follows.

---

## 2. What went well (preserve — do not "fix")

- **W1. Parallel sourcer agents** isolated page-text from the orchestrator's context — the
  core agentic win. 6 brands sourced concurrently; my context stayed clean.
- **W2. Model-number keying** for the web pass — region-safe by design. Research confirms
  this was the correct instinct against regional-variant contamination.
- **W3. Abstention on identity.** Blanked the 7 unprovable SKUs; held the V60 Lite rows.
  Research (Fellegi-Sunter "possible match → review") confirms blank-over-guess is the
  textbook-correct design, not timidity.
- **W4. Independent audit caught the colour-blind join.** Auditor ≠ builder paid off.
- **W5. Decision log discipline** is what made this retrospective re-derivable at all.

---

## 3. Mistakes (got it wrong; needed correction)

| # | Sev | What | Root cause | Caught by |
|---|-----|------|-----------|-----------|
| M1 | HIGH | Xiaomi camera/fingerprint columns silently lost data | I hardcoded source header names from a **22-char-truncated** console dump instead of the real headers | spot-check anomaly ("Front camera photography: 43") |
| M2 | HIGH | SKU join put one SKU on two colour variants | treated record-linkage as a quick fuzzy match; no variant awareness | independent audit |
| M3 | HIGH | Greedy join cross-assigned near-duplicate models (Reno12F→Reno13, A5 Pro→A5) | loose token blocking + greedy assignment | join audit eyeball |
| M4 | MED | Front-camera MP omitted from first web pass → a second pass | incomplete gap taxonomy before sourcing | coverage report |
| M5 | MED | Duplicate columns on non-phone tabs | exact-key header exclusion missed "(cm)"/"CCM)" suffixes | spot-check |

The thread through M1/M3/M5: **brittle string handling and working from lossy artifacts.**
The thread through M2/M3: **identity matching was improvised, not engineered.**

## 4. Inefficiencies (waste, even where the result was correct)

- **I1 (HIGH).** Reinvented the skill's machinery — ledger, build, audit, standardise,
  reports — as ~5 bespoke, untested, path-hardcoded scripts (~700 lines), because the skill
  only supports the house 5-block output, not an arbitrary target template. This is the
  single biggest inefficiency and the reason the work isn't reusable or committed.
- **I2.** Three build→run→catch→rebuild cycles on the join alone.
- **I3.** 6 agents independently hammered GSMArena → HTTP 429 → fallback to lower-confidence
  mirrors. No shared cache, no per-host throttle.
- **I4.** Burned fetches discovering Hisense SA has no spec tables at all.
- **I5.** Hardcoded absolute machine paths → not portable.
- **I6.** No tests on the bespoke logic; correctness rested on manual spot-checks.

## 5. Bottlenecks (flow)

- **B1.** The bespoke-build detour (I1) was the critical path: because the skill didn't fit,
  every downstream stage had to be hand-rolled and debugged.
- **B2.** Each fix re-ran the whole build (cheap at 50 rows; doesn't scale).
- **B3.** Two clarification rounds; the choice popup was dismissed — this user prefers prose.

---

## 6. What the research says (sources in the two research returns)

**Entity resolution (the join).** The two failures are textbook. The prescribed fix is a
**3-stage hybrid**: deterministic key (barcode/EAN → exact model token) → attribute-gated
fuzzy scoring where **colour/storage are HARD GATES, not weights** → **global one-to-one
assignment** (`scipy.optimize.linear_sum_assignment`, Hungarian) instead of greedy →
**principled abstention** (absolute threshold + margin-to-second-best + uniqueness → blank).
Tooling: `rapidfuzz` + `scipy` + `pandas`, ~100 lines, no ML. `dedupe`/learned models are
overkill at our scale. This fixes M2 and M3 by construction.

**Spec sources (the web pass).** Device-detection DBs (DeviceAtlas, 51Degrees, WURFL) are
the wrong tool — they key on user-agent, not model number, and carry no real spec table.
The right shape is **resolve-then-fetch**:
1. `KHwang9883/MobileModels` (GitHub, offline, free, CC BY-NC-SA) maps manufacturer
   model# → marketing name → region for Oppo/Vivo/Xiaomi/Nubia (not Hisense). Using it
   *before* fetching would have auto-flagged V2440=V50 Lite and CPH2669=A3(2024).
2. Primary fetch keyed on model#: PhoneDB / a maintained gsmarena library, with
   **MobileAPI.dev** ($15/mo, real ToS) as a paid backstop.
3. A **fetch cache + per-host concurrency cap + backoff** is the actual fix for the 429s.
4. **Hisense SA**: hisense.co.za *does* publish SA-market spec pages, but not keyed by HLTE
   model# and with fields omitted → first stop the regional manufacturer page, then **chase
   the distributor** for the model#↔spec linkage. Confirms today's chase decision was right.

---

## 7. The build plan (targets the SKILL, so the next job inherits the fixes)

> **STATUS 2026-06-09: Phase A + D DELIVERED.** `scripts/match.py` (strong key ->
> exact model-token blocking -> colour/storage gates -> global one-to-one assignment
> -> abstention) and `scripts/common.py` header/lookup helpers + gap taxonomy.
> Regression test `test_match` in `tests/run_tests.py` encodes today's real failures
> (A40 collapse, A5/A5 Pro & Reno12F/Reno13 cross-assign, indistinguishable H72 abstain,
> barcode + model# strong keys). Full suite: 73 passed, 0 failed. Dependency-free
> (stdlib only) — chose not to add rapidfuzz/scipy at variant-group scale. B and C remain.

### Phase A — Reusable identity-matching module  *(fixes M2, M3, I2; low risk, high value)*
- New `scripts/match.py`: deterministic-key → attribute-gate → Hungarian assignment →
  abstention, with provenance + an explicit "abstained: reason" outcome per row.
- Regression fixtures from today's real failures: A40 Sparkle/Starry, A5 vs A5 Pro,
  Reno12F vs Reno13, the two same-colour H72s (must abstain).
- Wire into `tests/run_tests.py` as the gate.

### Phase B — Generalise the skill to arbitrary target templates  *(fixes I1, B1; the backbone)*
- A **mapping profile**: source-schema → target-schema field map with transform types
  (direct, compose, derive, constant, blank), authored via the existing `fields.reconcile`
  + user confirmation, saved per job.
- Make `build.py` / `audit.py` / `standardise.py` **schema-driven** off the confirmed target
  schema + mapping profile, not the hardcoded house 5-block.
- Result: today's 5 bespoke scripts collapse into a configured skill run.

### Phase C — Robust sourcing layer  *(fixes I3, I4, and the V2440 class)*
- `scripts/resolve.py`: vendored `MobileModels` lookup → canonical name+region +
  alias/variant flag **before** any fetch (auto-flags the V60/V50 Lite class).
- `scripts/fetch_cache.py`: keyed cache + per-host concurrency cap + exponential backoff.
- Web-viability pre-classification: brands/models with no spec table (Hisense) routed
  straight to manufacturer-regional + chase, no wasted fetches.
- Optional: MobileAPI.dev keyed backstop (paid — a user decision).

### Phase D — Robustness & hygiene  *(fixes M1, M4, M5, I5, I6)*
- A complete **gap taxonomy** computed up front: derivable / web-targetable / region-variable
  / structurally-blank — so the web pass is one complete pass, no follow-up (M4).
- Header handling: always read exact values programmatically; normalized prefix matching
  utility (M1, M5). Never transcribe from truncated output.
- Parameterised paths; no absolutes (I5).
- Coverage folded into the standard tests (I6).

---

## 8. Scope — how this is achieved

- **Where:** all changes live in `.claude/skills/salt-input-builder/` (scripts, references,
  tests, SKILL.md, workflow.md). New modules: `match.py`, `mapping_profile.py`, `resolve.py`,
  `fetch_cache.py`. Extend `build.py`/`audit.py`/`standardise.py` to be schema-driven.
- **New dependencies:** `rapidfuzz`, `scipy` (likely already present), vendored `MobileModels`
  data. Optional paid: MobileAPI.dev.
- **Sequencing (by risk × value):** A and D first (low-risk, high-value, immediately reusable);
  B as the structural backbone; C last (external deps). A+D could land in one focused build;
  B is the larger lift; C is incremental.
- **Validation:** every phase gated by tests built from today's actual failures. Then a
  **golden regression**: re-run the Infinity job through the generalised pipeline and prove it
  reproduces today's verified output with the rework removed (the Endorfy-replay pattern).
- **Decisions for the user — RESOLVED (2026-06-09):**
  1. Build scope: **A through D** (all four phases). Sequence A+D, then B, then C.
  2. Paid spec API (MobileAPI.dev): **No — defer.** No budget committed until the pipeline
     is near-perfect. Phase C ships the free cache+throttle first; revisit paid only if a
     real reliability gap remains.
  3. `MobileModels` dataset: **Do not vendor.** Build our own incremental model# → canonical
     name → region map from confirmed job data, accruing coverage over time. No licence
     entanglement; ours to commit. The resolve-before-fetch technique is what matters, not
     that specific dataset.

Nothing here is built yet. This is the design; each phase gets its own concrete plan brought
to the user before any build, under the same gates.
