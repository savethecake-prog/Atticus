# Workflow and gates

Read this when running a job. The phases are ordered; do not skip ahead. State
lives in files (job spec, schema profile, evidence ledger, audit report) so a
fresh session can resume from disk, not from memory.

## Phases

1. **Activation.** The user provides a blank template workbook and a brief.
   Do not start populating anything yet.

2. **Contract.** Run a short intake interview (use the popup modal for choices).
   Fill in `assets/job-spec.template.yaml` from the answers and the detected
   schema, then show it to the user and get explicit sign-off. The user
   confirms or corrects; they never hand-author it. Save as `jobspec.yaml`.

3. **Schema profiling.** Run `scripts/detect_schema.py <template> <out.json>`.
   Show the detected column map and anything in each tab's `uncertain` list.
   Get the user to confirm or correct. Save the profile. On a later batch with
   the same template, reuse the saved profile; only re-confirm if the stored
   `template_signature` no longer matches.

4. **Inspect and profile.** Before sourcing, group the products by category (and
   by brand where identifiers differ) and inspect a sample of the real data.
   Build a category profile per group: metric ranges, identifier decoders
   inferred from the observed SKUs, and cross-field rules. Confirm it with the
   user, stating the evidence for each decoder. Save it, and reuse a prior
   profile only on genuine similarity. See `references/category-profiles.md`.
   The skill holds no brand or category knowledge; this phase supplies it.

   In the same phase, DISCOVER the fields the product carries by reading its
   manufacturer spec sheet and corroborating sources. Capture the COMPLETE
   published spec table, every row the manufacturer lists, not a hand-picked core
   set. Hand-picking a thin subset is the main way listings come out low-value, so
   paste the whole table into `fields.from_spec_table(raw)` to get one field per
   row, then `fields.reconcile` it against the tab (match an existing column, label
   a blank spare, or append a new one), present the proposal, and after the user
   confirms call `fields.apply`. Record how many fields the source published in
   `schema["tabs"][tab]["source_field_count"]` so the completeness gate can tell
   later whether capture fell short. This is how a template with blank columns
   still ends up carrying every spec the manufacturer publishes. Never invent a
   field that is not in the sources, and never stop at a convenient subset.

5. **Sourcing.** For each item, search and fetch authoritative pages. Record an
   evidence-ledger entry per field: value, provenance tier, source URL, and the
   exact snippet the value was copied from. Leave gaps explicit; do not fill
   them. Identity fields (the client's own SKU, category) are provenance
   `client`. Resolve authority per the job spec (brand domain = manufacturer,
   allowlisted retailers = retailer, anything else is not a source). When more
   than one source is consulted for a field, record each as a candidate
   observation on the entry and set the chosen value as the top-level one; the
   comparator then flags any disagreement (see phase 8). Capturing candidates is
   not optional housekeeping: for any field with no manufacturer source it is what
   lets a value clear the two-source bar at build time. One retailer is not enough.

6. **Sourcing review.** Validate the ledger with `scripts/ledger.py`. Present
   coverage, the gaps, and the "needs you" queue (see triggers below). The user
   resolves ambiguities and approves any retailer fallbacks. Do not proceed
   past unresolved HARD items.

7. **Build.** Run `scripts/build.py`. It refuses to run on an invalid ledger,
   writes every sourced value copied from its snippet, and scores each cell 0-100
   with a detailed reason naming the source (`confidence.py`). Weak values (no
   manufacturer and fewer than two agreeing sources) are written but flagged, not
   blanked: only a value with no source at all is left empty. It shades each data
   cell by its band, writes the row's mean score into the Confidence column, lists
   every sub-85 cell with its value and reason in the Check notes column, adds a
   "Confidence key" sheet, preserves the CONCAT column, and writes a
   liveness-checked source link per row. Export the per-cell map for SALT with
   `runner.py confidence <jobdir>`.

8. **Independent audit.** Run `scripts/audit.py`, passing the confirmed category
   profile(s). It re-derives every check from the ledger and the sheet (it does
   not trust the build), runs the profile's checks plus agnostic cross-row checks
   (e.g. duplicate identifiers across products) and the source-conflict
   comparator (same-tier disagreement, or a lower tier chosen over a higher one),
   shades discrepancies, appends ACCURACY CHECK notes, and writes the Markdown
   report. Surface HARD findings.

9. **Delivery.** Hand over the workbook, the audit report, the evidence ledger,
   the schema profile, and the category profile(s). State coverage, the
   HARD/SOFT flag counts, and the residual risk plainly. Do not claim the data is
   correct; claim it is fully sourced, traceable, independently checked, and that
   gaps are marked.

## Adaptive gating

Gating decides WHEN to interrupt the user, never WHETHER an unsourced value can
be written. Anything unverifiable is always left blank, flagged, and queued, in
every mode. In `adaptive` mode the run proceeds and accumulates a "needs you"
queue, then pauses once to clear it rather than stopping per item. If the queue
is empty, run straight through to delivery.

### "Needs you" queue triggers (pause and ask)
- A required field has no manufacturer source and no acceptable retailer source.
- Two same-tier sources disagree, or a single source contradicts itself.
- A title-versus-identifier conflict that changes which product it is.
- A suspected error in the client's own input (e.g. a duplicate SKU across two
  products). Flag it; never silently correct it.
- Schema detection is low-confidence, or the template no longer matches its
  saved signature.
- A source link fails its liveness check at build time.

Everything else (a clear single manufacturer source; a retailer that agrees and
matches identity when fallback is allowed) proceeds without interruption.
