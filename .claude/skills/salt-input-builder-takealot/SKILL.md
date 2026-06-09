---
name: salt-input-builder-takealot
description: >-
  Takealot (TAL) exporter. Use this AFTER salt-input-builder has produced a verified job,
  when the user wants to load that work into Takealot's official upload artifacts: the Edit
  Request template for products that already have a TSIN, or the category loadsheet (105
  computer-components, 120 gaming) for new products. Trigger for "export to Takealot", "fill
  the Takealot loadsheet", "edit request", "TAL upload sheet", or routing products to the
  right Takealot artifact and enforcing Takealot's rules (title 75, subtitle 110, barcode 20
  characters, dropdown conformance). The Takealot member of the salt-input-builder family.
license: Proprietary. LICENSE.txt has complete terms
---

# salt-input-builder : Takealot exporter

A sub-skill in the salt-input-builder family. The master skill (`salt-input-builder`) gathers
and verifies product inputs; SALT writes the listing content; this skill loads the finished
work into Takealot's official upload artifacts. Read this only when the export target is
Takealot.

This skill honours the exporter contract documented in the salt-input-builder master skill.
Nothing here lowers the core truth bar: only sourced or SALT-supplied values are written,
blanks stay blank, and Takealot's own file format and validations are preserved exactly.

## When to use which artifact (routing)

One test per product: does it already have a TSIN?

- Has a TSIN (already listed) -> Edit Request template. One row per product; fill only the
  fields being changed; a blank cell means "keep the existing value".
- No TSIN (new product) -> the category loadsheet, chosen by CAT2:
  - `105` computer-components (PSU, CPU coolers, fans, motherboard, GPU, cases, ...)
  - `120` gaming (gaming furniture and accessories, e.g. gaming chairs and desks)

Decide 105 vs 120 by matching the product's category against each loadsheet's
`Category Tree Lookup` tab. Never guess the category string: it is copied verbatim from that
tab, and the exact Main/Lowest pair is confirmed with the operator, not invented.

## The two formats (stable facts; full detail in assets/takealot-formats.json)

### Edit Request template (TSIN products)
- Sheet `Template (Fill this in)`: header row 3, descriptions row 4, data from row 5.
- 24 columns. `TSIN` (col 2) is the only required field. Max 250 rows per request.
- Free-type fields: Title, Subtitle, Description, What's in the Box, Brand.
- `Warranty Type` and `Warranty Period` are dropdown-validated (reject if off-list).
- Attribute edits: cols 17/19/21 = attribute name, 18/20/22 = attribute value. The name is
  the loadsheet's attribute label verbatim, e.g. `Colours [0]`, `Materials [0]`. The pair
  block is duplicable for more attributes.
- Main/Lowest Category, if changed, are copied from the relevant loadsheet's Category Tree.
- Save as: `Seller Display Name - Seller ID - Edit Request - Request Date.xlsx`.

### Loadsheet (new products) - 105 and 120
- Sheet `Loadsheet`: machine field names on row 1, human labels on row 3, helper/echo on rows
  4-6, data from row 7.
- ~213 columns (105) / ~174 (120). The first ~16 are standard; the rest are category-specific
  `Attribute.*` columns.
- Rules are encoded as data validations on the sheet, not as prose. Read them at run time.
  The fixed ones: Title (col G) max 75 chars, Subtitle (col H) max 110, Barcode (col F) max
  20. Main Category (col D) is a list; Lowest Category (col E) is a dependent list driven by D.
  105 carries 186 validations, 120 carries 145.
- Dropdown sources live on hidden `Lookup` plus category tabs: 105 has `CPU Type`,
  `Materials`, `Card Series`, `Country of Origin`; 120 has `Game Designers`, `Game Genres`;
  both have `Brand Look up`.

### Standard loadsheet columns (consistent across categories)
1 Product/Variant; 2 SKU (your own); 3 Variant ProductCode; 4 Main Category; 5 Lowest
Category; 6 Barcode (EAN/GTIN); 7 Title; 8 Subtitle; 9 Description (Key Selling Features);
10 What's in the Box; 11 Brand; 12-14 Colour (main/secondary/name); 15 Model Number;
16 Main Material/Fabric. Columns 17+ are category-specific attributes.

## Mapping from the core job

Direct fills from the verified inputs: SKU, Barcode/EAN, Brand, Colour (derived where a SKU
suffix convention applies), Model Number, Main Material, and each sourced spec -> its specific
`Attribute.*` column (matched by label/machine name read from the live template).

Not ours, SALT generates these: Title, Subtitle, Description, What's in the Box. Per the
partner flow, we hand over a loadsheet pre-filled with verified structured data and leave the
prose fields for SALT 2.0; SALT returns the content; those four fields are then dropped in.

## Gaps the exporter surfaces, never papers over
- Category strings must resolve to the exact tree pair (confirm with operator).
- Images, price, stock are outside the core input scope; flag as required-but-absent.
- Some `Attribute.*` columns have no value in our job; leave blank, do not invent.
- A value that fails a column's validation (over length, off dropdown-list) is flagged in the
  QA side-report and not silently written or silently truncated.

## Scripts

Operate on the user-provided live template at run time (never a bundled copy; templates change).

```bash
python tests/test_takealot.py    # exporter gate: routing + rule enforcement helpers
```

`scripts/tal_export.py`:
- `route_product(tsin, category, trees)` -> edit_request | loadsheet_105 | loadsheet_120 (done)
- `load_rules(template_path)` -> per-column constraint map read from the file (done)
- `load_category_tree(template_path)` -> the Main/Lowest pairs for routing (done)
- `enforce_text_length` / `check_dropdown` -> rule helpers, flag never silently fix (done)
- `write_edit_request` / `write_loadsheet` -> artifact writers (next build increment)

## QA
Keep this skill's test gate green before packaging, and add cases here for each new behaviour:
routing by TSIN/CAT2, length rules (title 75 / subtitle 110 / barcode 20), dropdown
conformance, blank-stays-blank, and format/validation preservation on round-trip.
