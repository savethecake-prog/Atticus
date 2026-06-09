# SALT input builder workstream (Claude Code)

Prepares accuracy-verified product data as INPUT for the SALT listing engine, run as an agentic workflow.

## The orchestrator, and the decide-do split

The main agent is a persona, Atticus, defined at the top of `CLAUDE.md`. Because Claude Code loads `CLAUDE.md` at the root of every request, Atticus is always on; he is not a subagent you invoke. The full character and psychology dossier is in `docs/PERSONA.md`.

The governing rule is one line: Atticus decides, the agents do. Atticus is the surgeon, the subagents are instruments. Every steering decision (the plan, conflict resolution, gate interpretation, what to escalate, whether to advance, loop or stop) is his alone. The agents execute one bounded task each, reason only within their craft, and return a structured result with flags. They never decide and never advance the job, and they never call each other; the call tree is flat, Atticus to an instrument and back. Context isolation is for the labour, not the judgement: an agent does its heavy work in its own window and hands back a tight verdict that Atticus reasons over.

Atticus keeps a decision log per job at `clients/<client>/decision_log.md` so the steering itself carries provenance. He escalates the genuine decisions to the user once per job, with a proposed default for each, not per tranche.

## Layout
- `CLAUDE.md` the Atticus persona, the operating loop, the decide-do boundary, and the full constitution every agent inherits.
- `.claude/skills/salt-input-builder/` the master skill: methodology plus the Python tooling (fields/from_spec_table, ledger, completeness, confidence, build, audit, standardise) and the 60-test suite.
- `.claude/skills/salt-input-builder-takealot/` the Takealot exporter sub-skill.
- `.claude/agents/` the seven instruments: intake, sourcer, builder, auditor, standardiser, exporter, reporter. Each is execute-and-surface, not decide.
- `.claude/hooks/` the deterministic gate script and the persona-reassert script.
- `.claude/settings.example.json` example hook wiring. Copy to `settings.json` and confirm against the docs before relying on it.
- `docs/` the constitution source, the migration plan, and the persona dossier.
- `clients/` one folder per client; a client is a manifest plus a run, not a conversation. See `clients/_TEMPLATE/`.

## Hooks: how the persona stays live

The character is loaded in three layers so it steers every query without paying the full dossier cost every turn.

- `CLAUDE.md` is the resident baseline: the condensed operating persona plus the constitution, loaded at the root of every request by the platform. This is the floor that holds even if the hooks misfire.
- `persona_load.sh` (SessionStart) pulls the full `docs/PERSONA.md` dossier into context once, at session open, to set the deep anchor. Paid once, not per turn.
- `persona_reassert.sh` (UserPromptSubmit) re-injects the condensed core on every turn after. Its job is recency and durability, not novelty.

One honest caveat. The once-per-session full pull persists only until the first compaction in a long session; when the window fills, early bulk content like the dossier is summarised away. That is exactly why the per-turn condensed reassert matters: it is the part that survives a compaction, so it is the durable carrier of the persona, not merely a reminder of the first pass. The full pull gives depth at the start; the condensed pass gives endurance.

`gates.sh` runs the deterministic gates so they block automatically rather than depending on the agent choosing to check.

Wire all three via `.claude/settings.example.json`. The exact hook event names and the context-injection contract change over time, so confirm them against the current Claude Code hooks documentation before wiring. In particular, confirm that SessionStart stdout is injected as session context rather than merely executed.


## Phase status
- Phase 0 (this scaffold): skills ported, persona at root, agents re-scoped to execute-and-surface, hooks and decision-log convention added, tests green. DONE.
- Phase 1: wire the gate and persona-reassert scripts as Claude Code hooks so they fire automatically. Confirm the current hook event schema first.
- Phase 2: replay the Endorfy golden job end to end and prove it reproduces the verified output.
- Phase 3: config-driven onboarding from a manifest. Phase 4: MCP integrations (distributor PIM for identifiers, fetching, SALT handoff). Phase 5: hardening and the learnings feedback loop.

## Run the gates
`bash .claude/hooks/gates.sh` runs the test suite. The per-job gates (completeness, standardise) run via the skill's `runner.py`.
