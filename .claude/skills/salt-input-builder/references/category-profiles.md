# Category profiles (brand and product agnostic)

This skill ships with NO baked-in brand or category knowledge. It does not
"know" fans or motherboards or Cougar or Thermalright. That knowledge is built
per job by inspecting the actual product and category data, confirmed by the
user, saved, and reused only when a later product genuinely matches it. The
generic engine (`scripts/profile_engine.py`) runs whatever profile it is given.

There are two separate things called a "profile". Do not conflate them.

1. **Template schema profile** (`detect_schema.py`): the workbook column map -
   which column is the title, the spec block, the SKU, the notes, and so on.
   This comes from the template's own headers and is per template. The template
   only fixes the output shape: the fields a product should actually carry are
   discovered from its manufacturer spec sheet during inspection and added to the
   tab with `fields.py` once confirmed. A blank or unnamed template column is not a
   reason to leave a real, sourced spec out.

2. **Category profile** (this document): the data semantics for a product
   category - which metrics it has and their plausible ranges, how its
   identifiers decode, and its cross-field rules. This is per product category,
   and per brand for the decoder patterns. It is built by inspection.

## Build the category profile AFTER inspecting the data

Do not pre-assume a category's fields. Inspect first:

1. Group the job's products by category (and by brand where identifiers differ).
2. For each group, inspect a sample of real products and their category: what
   attributes does this category actually carry, what units, what identifier
   pattern do the SKUs follow, what cross-field invariants hold (e.g. a 240
   radiator carries two fans).
3. Propose a category profile: metric ranges, decoder patterns INFERRED from the
   observed SKUs and their attributes, and cross-field rules. Infer; never
   assume. A decoder that cannot be confirmed from the data is not added.
4. Show it to the user and get confirmation. Decoders especially: state the
   evidence ("these four SKUs end .0001 on black units and .0002 on white").
5. Save the confirmed profile keyed by category (and brand).

## Drafting with profile_builder

`scripts/profile_builder.py` automates the first pass of step 3.
`build_profile(category, brand, spec_labels, products)` takes the template's spec
labels and the products (each with its SKU and the attributes you already know,
e.g. colour, pack, blade, size, and ideally a product-line `family` label) and
returns a draft profile plus a Markdown evidence report. It groups SKUs by the
line label, aligns them, and proposes a decoder mapping ONLY where a segment maps
to exactly one attribute across the examples; anything confounded or thin is
flagged, not guessed. It is a drafting aid. Read the evidence, confirm each
mapping, widen patterns beyond the observed tokens where needed, then save.

## Reuse only on genuine similarity

On a later batch, reuse an existing category profile only when the product
matches it: same category and the same identifier scheme. A new category, or the
same category from a brand whose SKUs decode differently, gets its own profile.
Shared similarity is the only thing that justifies reuse; when in doubt, build a
fresh profile and confirm it. Over-reusing a profile across products that merely
look alike is how silent errors enter.

## Profile schema (the engine's whole contract)

```yaml
category: "<category>"
brand: "<brand or 'mixed'>"
percent_guard: true            # tolerance-aware number parsing
metric_ranges:                 # plausibility per metric, matched by header keyword
  <metric>: {keywords: [...], lo: <n>, hi: <n>}
decoders:                      # identifier decoders, inferred + confirmed
  - name: <id>
    sku_regex: '<regex with named groups: blade, suffix, size, pack, variant>'
    blade_map: {<token>: forward|reverse}
    colour_source: suffix|letter      # where colour lives; 'letter' avoids the MHP trap
    suffix_colour: {<suffix>: <colour>}
    set_map: {<token>: [<size>, <count>]}
    pack_map: {<digit>: <pack-count>}
    <role>_label_keywords: [...]      # how to find the field to compare against
implies_count:                 # e.g. radiator size -> fan count
  from_keywords: [...]
  count_keywords: [...]
  map: {"<key>": <count>}
compatibility:                 # e.g. socket -> chipset family
  a_keywords: [...]
  b_keywords: [...]
  map: {"<key>": [<allowed>, ...]}
```

Every block is optional. A profile only needs what its category actually has.
See `assets/examples/category-profile.cougar-fans.example.yaml` for a worked
example, which exists to copy from, not to use as a default.

## Validate new checks against fixtures

Before trusting a new decoder or range, run it against known-good and known-bad
examples. We have already paid for two false positives (the `+-10%` tolerance
read as a value, and a suffix colour rule misapplied to MHP). The engine guards
both, but any new rule must be checked the same way before it ships.
