# SALT Input Builder: migration to an agentic workflow in Claude Code

Execution plan, 8 June 2026. Audience: Polyphrōn SALT data preparation. Purpose: take the workstream we have been running by hand, conversation by conversation, and turn it into a system that onboards a new client as a config plus a run rather than a bespoke collaboration, so throughput can ramp without the truth bar slipping.

---

## 1. The thesis

The reason this migration is low risk is that the work is already a staged pipeline, and the gates that catch our mistakes are already deterministic Python rather than judgement. We did not discover that by design; we discovered it by making the mistakes. The under capture of specs (632 values against 1037), the value appended to the wrong field, the shared GEX750 SKU, the single sourced fan pack size: every one of those was caught by a mechanical check that re-derived the answer, not by a model being more careful. That is the SALT pitch turned on ourselves. Intelligence is cheap, integrity is scarce, so we let intelligence do the judgement and we let code hold the line.

So the migration is not "rewrite the work as agents". It is "keep the deterministic spine exactly as it is, and put agents around it". Concretely that means five moves:

1. The Python gates (completeness, standardise, audit, the identifier checks, the 60 test suite) become Claude Code hooks, so they run and block automatically on the relevant events rather than depending on an agent choosing to run them. A rule in a prompt is followed most of the time; a hook is followed every time.
2. The pipeline stages become specialised subagents with isolated context, which gives us the auditor-independent-of-builder property for free, because a separate subagent genuinely cannot see the builder's reasoning and must re-derive from the recorded sources.
3. Sourcing, the slowest stage, parallelises across tranches because each subagent runs in its own context.
4. A managing persona orchestrates the whole job autonomously and surfaces only the genuine human decisions, batched into one review per job, instead of the per-tranche back and forth we do now.
5. Each client becomes a manifest, a small config file that captures the things that currently live in our heads and in chat (the identity columns, the marker conventions, who owns which tab, where the identifiers come from).

---

## 2. The non-negotiables, and the mechanism that enforces each

These are the principles from the learnings document. The point of the table is that in the agentic system each one stops being a thing we hope the model remembers and becomes a thing a specific mechanism guarantees.

- Blanks over guesses. Enforced by the builder subagent's instructions plus the audit gate, which fails a row that carries a value with no source.
- Never assert an identifier you cannot prove (the GEX750 lesson). Enforced by an identifier source of truth: EANs and similar come from the distributor's master data over MCP, never from a model. A deterministic check fails any EAN that is malformed, shared across different SKUs, or unsourced.
- Placement is correctness. Enforced by the standardise gate's placement flags and by the house-format builder, which writes named fields and never appends.
- Capture the full published table, not a hand-picked subset. Enforced by the completeness gate, which learns the expected richness from the richest sibling and from the recorded source field count, and flags thin rows.
- The auditor is independent of the author. Enforced by running the audit as a separate subagent with its own context that re-derives values rather than trusting the build.
- Flag conflicts, do not silently resolve. Enforced by the builder recording both values, using the manufacturer value, and emitting a flag the orchestrator routes to the human.
- Manufacturer first, code matched. Enforced by the sourcing subagent's source tiering and by provenance recorded per cell.
- Brand and product agnostic. Enforced by source-driven field discovery (from_spec_table), so no category knowledge is hard coded.
- Provenance and confidence travel with the data. Enforced by the evidence ledger, which is the shared state the subagents pass between each other.

If a future change to the system would weaken any of these, the test suite should go red. That is the contract.

---

## 3. The three layers

The user asked for agents, skills, and a managing persona. Those are exactly the three layers, and Claude Code has a distinct construct for each.

### Skills (what the work knows how to do)

The salt-input-builder family already is a set of skills. In Claude Code the canonical home is `.claude/skills/<name>/SKILL.md`, and skills now do what the old slash commands did plus auto-invocation, so a skill can fire because a person typed its name or because the orchestrator read its description and decided it applied. The existing bundle ports across almost unchanged:

- `salt-input-builder` (master): the methodology, the house format, the field schema, the marker conventions, and the Python tooling (fields/from_spec_table, ledger, completeness, confidence, build, audit, standardise).
- `salt-input-builder-takealot`: the exporter, TSIN to Edit Request and no-TSIN to the 105 or 120 loadsheet, enforcing the Takealot limits (title 75, subtitle 110, barcode 20) and dropdown conformance.
- `salt-standardise` (can stay inside the master): the review gate, propose then commit, that we built.

Skills are the shared library. Both the orchestrator and the subagents call them. A heavy skill such as audit can be set to run in a forked context so it does not pollute the caller's window.

### Subagents (who does each stage, in isolation)

Subagents are worth their cost only where context isolation or parallelism genuinely pays. For us both pay, in specific places. The roster, each with a one-line contract of purpose, input, output, and the gate it owns or feeds:

1. **Intake and Planner.** Reads the client inventory, fixes the authoritative identity and price columns, groups products by comparable type, plans the tranche order (smaller coherent groups first), writes the job manifest and the empty ledger. Output: a plan and a manifest. Owns no gate; sets up the run.
2. **Sourcer (researcher).** For each product in a tranche, sources per product code, manufacturer first, captures the whole published spec table via from_spec_table, records provenance, snippet and confidence per cell, leaves blanks and flags. Runs in its own context, parallelised one instance per tranche. Feeds the completeness gate. This is where under capture happened, so its instruction is "exhaustive, the full table, under capture is a defect", and the gate checks it rather than trusting it.
3. **Builder.** Places every value in its correct named field in the house format, never appends, applies variant inheritance, applies the marker convention (blank for not-applicable, marker for not-found, identifiers left for the source of truth). Feeds the standardise and audit gates.
4. **Auditor.** A separate context that re-derives values from the ledger's recorded sources, cross-checks identity and price fidelity, checks EAN format and uniqueness, and confirms coverage. It must not inherit the builder's reasoning, which is exactly why it is a subagent and not a function the builder calls. Owns the audit gate.
5. **Standardiser and gatekeeper.** Runs the standardise review gate, produces the change report, holds at the human checkpoint, commits only safe fixes on sign-off. Owns the standardise gate.
6. **Exporter.** Routes by TSIN, fills the Edit Request or the correct loadsheet, enforces the Takealot rules. Owns the export validation.
7. **Reporter.** Assembles the single per-job decision report and the delivery summary, and prepares the handoff to SALT 2.0.

The tradeoff is real and worth stating: a subagent hides its working context from the main agent, so we only split where the isolation is the point. We do not, for example, split the builder and the standardiser if they share a lot of state; we can let one subagent own both. The auditor is the one split that is non-negotiable, because its value is precisely that it cannot see the build.

### The managing persona (who runs the job)

The orchestrator is the main Claude Code agent, given a persona and a constitution (CLAUDE.md). Think of it as the role we have been calling Ant: the person who takes a client job, decides the order of work, hands tasks to the right specialist, refuses to let anything move forward until the gate passes, and brings only the real decisions back to a human. It is an integrity keeper, not a doer. Its job description, which goes in CLAUDE.md:

- Own the job lifecycle from inventory to SALT handoff.
- Dispatch the subagents in sequence, parallelising sourcing across tranches.
- Treat every gate as a hard stop. A red gate is not advice, it is a wall.
- Collect every human-decision item across the whole job into one review, with a proposed default for each, and escalate once, not per tranche.
- Never do the granular work itself, and never relax a gate to make progress.

A blunt line for its constitution, in the spirit of the deck: it does not get to be confident, it gets to be checked.

CLAUDE.md carries the always-true project constitution (the non-negotiables in section 2, the 13 required fields in order, the house format, the marker conventions, the workflow). A second CLAUDE.md inside each client's job folder carries that client's specifics, and Claude Code appends rather than overwrites, so client context layers cleanly on top of the shared constitution.

### Hooks (the spine)

Hooks are the move that makes this trustworthy at volume. Each deterministic gate is wired to the event that should trigger it and is allowed to block:

- The 60 test suite runs on any change to the skill tooling and blocks a change that breaks it.
- The completeness gate runs after a tranche is built and blocks consolidation if rows are thin.
- The identifier check runs before export and blocks a malformed or shared EAN.
- The standardise gate runs before delivery and produces the change report.

The difference between a rule in CLAUDE.md and a hook is the difference between roughly followed and always enforced. Our integrity guarantees belong in hooks.

### MCP (the outside world)

Three integrations remove the manual steps we keep hitting:

- The distributor's master data (TechTraders' PIM or inventory) as the identifier source of truth. This is the proper fix for the parked EANs: the orchestrator pulls them from the authoritative source rather than asking a human or letting a model guess.
- The manufacturer-page and datasheet fetching the sourcer needs, with the retailer-mirror fallback for sites that block us (the Thermalright case).
- The handoff to SALT 2.0, and optionally the Takealot upload artifacts.

---

## 4. The scale unlock: human in the loop once per job, not per tranche

This is the part that answers the actual pain, which is that you cannot keep running this granularly. The pattern we already built, propose then review then commit, generalises. The orchestrator runs the entire pipeline autonomously up to the gates, and the only thing a human sees is one decision report per job. That report contains exactly the categories of decision we have hit in practice, each with a proposed default so the human is confirming, not authoring:

- Field matches the system was not certain of (the Endorfy alignment flags, Case type to Case form factor and the rest).
- Source conflicts (manufacturer versus retailer values), shown with both values and the proposed manufacturer choice.
- Identifier decisions (which EANs to pull from the PIM, which to park).
- Marker and blank conventions where a category is genuinely ambiguous.
- Tab ownership, the green-tab equivalent, where the client or Chris is running something and the system should not touch it.

A human signs that off once. Everything not in the report has already passed a deterministic gate and needs no attention. That is the difference between supervising every tranche and approving one report.

---

## 5. Per-client scaffolding: config, not conversation

Onboarding a client today is a conversation. It should be a manifest. A `job.yaml` per client captures what currently lives in chat and in our heads:

- Client and the marketplaces in scope.
- Brands and the manufacturer source domains for each.
- The authoritative identity and price columns in their inventory.
- The identifier source of truth (which PIM, or "park and chase").
- House-format conventions and the marker convention.
- Category-to-minimum-standard mappings where they exist.
- Tab ownership (what the client runs themselves).

Directory shape per client: an inventory in, a ledger as working state, tranche workbooks, the consolidated master, the decision report, the delivery, and the manifest. A new client is then: drop the inventory, fill the manifest, run the lifecycle. No new conversation.

---

## 6. Migration phases, with exit criteria

Phased so that each step is independently useful and the risky parts come after the spine is proven.

**Phase 0, lift and shift.** Put the skill family and the 60 test suite into a repo. Write the shared CLAUDE.md from the learnings document. Exit criteria: the 60 tests run green inside Claude Code and the skills are invocable.

**Phase 1, the spine.** Wire each deterministic gate as a hook and prove it blocks. Exit criteria: a deliberately thin tranche is rejected by the completeness hook without anyone asking it to run; a malformed EAN is blocked before export.

**Phase 2, the agents and the golden job.** Define the subagents and the orchestrator persona. Replay the Endorfy job, all 67 products, end to end through the new pipeline. Exit criteria: it reproduces the verified output we already signed off (67 SKUs, identity and price fidelity, the same coverage and flags). This is the regression that proves the agents did not change the answer.

**Phase 3, config-driven onboarding.** Build the lifecycle skills and the manifest. Exit criteria: a second client is taken from inventory to decision report using only a manifest and the lifecycle commands, with no bespoke instruction.

**Phase 4, integrations.** Connect the PIM (identifiers), the fetching, and the SALT handoff over MCP. Exit criteria: the parked-EAN problem is gone because identifiers resolve from the source of truth, and the loadsheet or Edit Request is produced without manual routing.

**Phase 5, hardening.** Turn the past jobs into eval fixtures (golden jobs the suite can replay), add run logging, and close the loop so each job's new errors update the methodology and the tests, the way the learnings document has worked manually. Exit criteria: a regression run across all golden jobs is part of the release check.

---

## 7. Risks and how the design answers them

- Agents drift from the truth bar. Answer: the gates are hooks and the test suite is the release check, so looseness fails loudly rather than shipping.
- Identifier errors multiply at volume. Answer: identifiers come from the source of truth, never a model, and the deterministic check fails malformed or shared codes. This is the GEX750 lesson built into the wall.
- Over-automation removes judgement that should stay human. Answer: the decision report keeps the genuine calls with a person, with defaults, once per job.
- Coordination and context overhead. Answer: subagents only where isolation pays, the ledger and manifest as the single shared state, clear input and output contracts per agent.
- Cost and latency as volume ramps. Answer: parallel sourcing across tranches, scoped tools per subagent, and forked contexts for heavy skills so windows stay small.

---

## 8. What I would build first

Phase 0 and the Phase 2 golden job, in that order, before anything clever. Port the skills and the tests, write the constitution, then replay Endorfy through the orchestrator and the subagents and prove it reproduces the output we already verified by hand. Everything after that is additive and safe, because we will have a baseline that says the machine gets the same answer we signed off. The temptation will be to start with the exciting part, the orchestration and the parallelism. The discipline, which is the same discipline that made the workstream trustworthy in the first place, is to make the spine provable before we make it fast.
