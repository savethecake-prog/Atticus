# Decision log

Atticus maintains this per job. One line per decision: what was decided, why, the
evidence or source behind it, and anything escalated to the user. This is provenance
for the steering itself, not only for the data.

Format:

`YYYY-MM-DD | stage | decision | why | evidence/source | escalated?`

Examples:

`2026-06-08 | sourcing | took manufacturer value over retailer mirror for net weight | manufacturer is source of truth on conflict | manufacturer datasheet URL | no`
`2026-06-08 | building | left operating temperature blank on the desk tab | field not applicable; SALT drops N/A required fields | constitution s3 | no`
`2026-06-08 | review | parked 60 component EANs | user cannot supply; correct source is the distributor PIM, not scraped variant barcodes | user instruction | yes, noted in decision report`
