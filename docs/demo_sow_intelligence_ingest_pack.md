# Demo ingest pack — SOW Intelligence (Northwind / Harborline)

Synthetic documents for the SOW Intelligence template. They are not a customer contract.

Ingest these three files into the job knowledge base (or rely on the demo KB bundle, version 4):

| Document ID | File | Role |
|---|---|---|
| NW-MSA-2025-003 | `docs/demo_kb/sow_northwind_msa_2025.txt` | Governing MSA |
| NW-SOW-2025-008 | `docs/demo_kb/sow_northwind_prior_2025.txt` | Completed fixed-deliverable SOW |
| NW-SOW-2026-014 | `docs/demo_kb/sow_northwind_draft_2026.txt` | Draft under review |

## User request

Paste only this. The template already carries classification, 5W1H, payment integrity, DOWNTIME, and the disposition list.

```
Prepare the SOW Intelligence pack for Harborline draft NW-SOW-2026-014 before signature.

Business intake: Northwind wants a finished cloud landing zone Product can use, with a target of 30 June 2026 for the first production workload. The buyer does not want a staff bench.

Ground only in ingested docs:
- NW-SOW-2026-014
- NW-MSA-2025-003
- NW-SOW-2025-008

Do not invent fees, owners, acceptance tests, or legal conclusions that are not in those documents.
```

## What a good pack does

- Classifies the draft as Staffing or Ambiguous, not Deliverable. The title says deliverable; the customer directs named people day to day.
- Flags the GBP 48,000 monthly invoice as capacity-style payment, not a managed service.
- Fails 5W1H on "Cloud landing zone" (no acceptance owner, test, or date in the draft).
- Flags the 12 percent rate increase as unexplained.
- Flags liability, confidentiality, and governing-law text that repeats the MSA, and leaves enforceability to counsel.
- Uses one disposition: Redesign Commercial Model or Do Not Approve Yet.
- Cites `[source:NW-SOW-2026-014]` and `[source:NW-MSA-2025-003]`.
