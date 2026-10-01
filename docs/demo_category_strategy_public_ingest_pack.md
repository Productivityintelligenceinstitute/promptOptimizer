# Category Strategy demo ingest pack — UK public-sector cloud (real public sources)

Use this pack when you want a **real-document** Category Strategy Intelligence Briefing run — same pattern as the Deel / Contentsquare packs: ingest public text, then paste a short User request.

Do **not** invent private company strategy. These sources are public UK government materials.


| Role in the briefing                                | Document                                            | Source                                                                                                                                                                                                            |
| --------------------------------------------------- | --------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Approved category / cloud strategy                  | Doc A — One Government Cloud Strategy excerpts      | [Cloud guide for the public sector](https://www.gov.uk/government/publications/cloud-guide-for-the-public-sector/cloud-guide-for-the-public-sector) (updated 29 Nov 2023, Open Government Licence v3.0)           |
| Operating priorities / commercial rules of the road | Doc B — Cloud First, MoUs, lock-in, cost, residency | Same OGCS guide                                                                                                                                                                                                   |
| What materially changed / market signals            | Doc C — G-Cloud 15 launch + framework facts         | [GCA news 10 Aug 2026](https://www.gov.uk/government/news/g-cloud-relaunches-with-biggest-upgrade-in-its-history) and [G-Cloud 15 RM1557.15](https://www.webprod-cms.crowncommercial.gov.uk/agreements/RM1557.15) |


Walkthrough: create/open the Category Strategy job → add **Trusted sources** (section below) → ingest A with metadata → ingest B with metadata → ingest C with metadata → paste the User request → Run.

Use the same metadata keys on ingest and on trusted sources so retrieval filters line up.

---



## Job — trusted sources (add when creating / editing the job)

On **Sources** step, add these three trusted sources (Exact match). Or paste this JSON if you edit `trustedSources` as JSON:

```json
[
  { "key": "documentId", "value": "UK-OGCS-CLOUD-GUIDE-2023", "op": "eq" },
  { "key": "documentId", "value": "UK-CLOUD-FIRST-COMMERCIAL-PRIORITIES-2023", "op": "eq" },
  { "key": "documentId", "value": "UK-GCLOUD15-SIGNALS-2026-08", "op": "eq" }
]
```

UI equivalent:


| Metadata key | Value                                       | Match |
| ------------ | ------------------------------------------- | ----- |
| `documentId` | `UK-OGCS-CLOUD-GUIDE-2023`                  | Exact |
| `documentId` | `UK-CLOUD-FIRST-COMMERCIAL-PRIORITIES-2023` | Exact |
| `documentId` | `UK-GCLOUD15-SIGNALS-2026-08`               | Exact |


Optional extra filters (add if you want category-scoped retrieval only):


| Metadata key   | Value                  | Match |
| -------------- | ---------------------- | ----- |
| `category`     | `Cloud Infrastructure` | Exact |
| `jurisdiction` | `UK`                   | Exact |


Do not also trust the synthetic Jet Industries demo IDs (`demo-category-strategy-cloud-2026`, etc.) on this job if you want only the public pack.

---



## Doc A — ingest as category strategy

**Suggested title:** One Government Cloud Strategy (OGCS) — Cloud guide excerpts  
**Suggested id / filename:** `UK-OGCS-CLOUD-GUIDE-2023`

**Metadata** (paste into ingest metadata / metadataJson — same keys as trusted sources)

```
documentType=category_strategy
documentId=UK-OGCS-CLOUD-GUIDE-2023
id=UK-OGCS-CLOUD-GUIDE-2023
source=UK-OGCS-CLOUD-GUIDE-2023
file=uk_ogcs_cloud_guide_2023
name=UK OGCS Cloud Guide 2023
title=One Government Cloud Strategy (OGCS) Cloud guide excerpts
category=Cloud Infrastructure
jurisdiction=UK
publisher=GOV.UK / GDS / Government Commercial Function
licence=OGL-v3.0
sourceUrl=https://www.gov.uk/government/publications/cloud-guide-for-the-public-sector/cloud-guide-for-the-public-sector
asOfDate=2023-11-29
demoBatch=category-strategy-public-2026-09-29
```

**Body** (paste as the document text)

```
SOURCE: GOV.UK — Cloud guide for the public sector (also known as The One Government Cloud Strategy / OGCS).
Updated: 29 November 2023.
Licence: Open Government Licence v3.0.
URL: https://www.gov.uk/government/publications/cloud-guide-for-the-public-sector/cloud-guide-for-the-public-sector
Demo ingest batch: category-strategy-public-2026-09-29.

PURPOSE OF THIS GUIDE
This guide is for government workers responsible for:
- deciding and setting cloud strategy
- implementing migrations to cloud
- implementing new capabilities in the cloud
- managing cloud usage (cost / risk / sustainability)

It covers how to:
- enable cross-functional collaboration throughout the cloud lifecycle
- realise best practice cloud service usage
- maximise commercial, technical, security, and people capabilities

FOREWORD (ABRIDGED)
Properly implemented cloud technology can improve speed of delivery, increase security and create opportunities for organisations to innovate. Government organisations and functions need to work together more effectively across functions to take full advantage of these benefits.

This cloud guide, also known as ‘The One Government Cloud Strategy’ (OGCS), includes lock-in, commercial, technical, security, operations, people and related issues. It aims to support the government by providing an effective way to gain benefits from using the cloud and other hosting solutions.

One size does not fit all when it comes to the use of public cloud. Organisations may take valid, and sometimes opposing, strategic decisions because cloud technology is versatile or because of unique maturity or capability.

CROSS-FUNCTIONAL COLLABORATION
Government organisations that combine functional capability can get more from the cloud, while maintaining value for money and a high standard of delivery. For example, a joint technical and commercial approach to cost optimisation reduced a Home Office portfolio’s cloud spend by 40%.

Four functions are essential for a successful cloud strategy:
- digital and technology — building and managing cloud estates and advising on technical solutions
- commercial — planning and negotiation of contracts with cloud service providers and managing the continuing relationship
- security — continuity of quality services and protection of systems, networks and data
- human resources — recruiting, re-skilling, developing, deploying and retaining people

Longer term, organisations might retain a central multi-disciplinary and cross-functional team to continuously improve cloud delivery, facilitate best practice, and act as a central point of contact for cloud service providers.

CHOOSING A HOSTING STRATEGY
Organisations need to consider and regularly reassess which cloud services are most appropriate. Decisions should be based on requirements, cloud capability, and implications of the choice. It is important to know how to choose between a single, hybrid or multi-cloud solution and when to consider cloud concentration risk.

SECURITY (ABRIDGED)
Cloud services can have native security advantages over local or on-premises technology. Organisations must understand their security needs to determine confidence that a cloud service is secure enough to handle their data. NCSC guidance on cloud security and zero trust principles is referenced by the guide.

PEOPLE AND SKILLS (ABRIDGED)
Adopting the cloud can mean significant changes in culture for commercial, financial and technical staff. Engaging with the workforce is critical.
```

---



## Doc B — ingest as stakeholder / operating priorities

**Suggested title:** UK Cloud First policy and commercial operating priorities (OGCS)  
**Suggested id / filename:** `UK-CLOUD-FIRST-COMMERCIAL-PRIORITIES-2023`

**Metadata**

```
documentType=stakeholder_priorities
documentId=UK-CLOUD-FIRST-COMMERCIAL-PRIORITIES-2023
id=UK-CLOUD-FIRST-COMMERCIAL-PRIORITIES-2023
source=UK-CLOUD-FIRST-COMMERCIAL-PRIORITIES-2023
file=uk_cloud_first_commercial_priorities_2023
name=UK Cloud First commercial priorities 2023
title=UK Cloud First policy and commercial operating priorities
category=Cloud Infrastructure
jurisdiction=UK
publisher=GOV.UK / GDS / Government Commercial Function
licence=OGL-v3.0
sourceUrl=https://www.gov.uk/government/publications/cloud-guide-for-the-public-sector/cloud-guide-for-the-public-sector
asOfDate=2023-11-29
demoBatch=category-strategy-public-2026-09-29
```

**Body** (paste as the document text)

```
SOURCE: GOV.UK — Cloud guide for the public sector (OGCS), same publication as Doc A.
Updated: 29 November 2023.
Licence: Open Government Licence v3.0.
URL: https://www.gov.uk/government/publications/cloud-guide-for-the-public-sector/cloud-guide-for-the-public-sector
Demo ingest batch: category-strategy-public-2026-09-29.

THE CLOUD FIRST POLICY
When procuring new or existing services, public sector organisations should consider and fully evaluate potential cloud solutions first before considering any other option. The policy was reassessed in 2019 and remains a flagship technology policy.

ASSESSING THE COMMERCIAL CASE
Cloud services procurement and implementation typically follow the programme business case approval process, alongside and within each organisation’s own spend controls and governance.

Organisations should follow Crown Commercial Services’ / successor agency contract management standards to make sure they:
- agree contracts of appropriate length
- retain ownership of intellectual property of products and services
- retain access to any data held by third parties

Buying frameworks from the Digital Marketplace or G-Cloud can make this easier.

USING MEMORANDUMS OF UNDERSTANDING
Crown Commercial Service has been implementing a common cloud procurement process with multiple cloud service providers as part of the One Government Cloud Strategy (OGCS).

Benefits include baseline commercial, technical, security and legal principles across government with each cloud service provider. Memorandums of Understanding (MoUs) use the combined purchasing power of government to achieve better commercial results, such as greater discounts for smaller departments and reduced negotiation time for government and providers.

BALANCING TECHNICAL LOCK-IN
While there is more flexibility available in the cloud, there is a risk of becoming dependent on the products and services from particular providers. Lock-in is where switching from one technology or provider to another is difficult, time consuming and disproportionately expensive. Organisations must balance the benefits and risks of cloud lock-in.

MANAGING COSTS
When using the cloud, bills change according to usage. To realise the full financial benefits of cloud, organisations need to:
- be flexible in how they budget for cloud services
- put in place systems and processes to monitor spending
- design applications to take advantage of the cloud cost model
- recognise that if projected costs appear flat / fixed and predictable, they may not be fully leveraging the true benefits of cloud

OFFSHORING AND DATA RESIDENCY
Offshoring or overseas hosting is where any part of the service relating to stored data is conducted outside the UK. This includes where data and services are physically located, who manages the services, and who has access to the data — including UK-resident data accessed by provider personnel based in other countries.

There is no government policy which directly prevents departments or services from storing or processing cloud-based data in any specific country. Each department must take risk-based decisions about use of cloud providers for government data regardless of geographic location of the data.

When making this decision, consider:
- ICO guidance on adequacy
- ICO guidance on data protection and international transfer of data
- European Commission guidance on adequacy of protection of personal data in non-EU countries
- NCSC cloud principles
```

---



## Doc C — ingest as category signals / what changed

**Suggested title:** G-Cloud 15 launch and framework signal pack (August 2026)  
**Suggested id / filename:** `UK-GCLOUD15-SIGNALS-2026-08`

**Metadata**

```
documentType=category_signals
documentId=UK-GCLOUD15-SIGNALS-2026-08
id=UK-GCLOUD15-SIGNALS-2026-08
source=UK-GCLOUD15-SIGNALS-2026-08
file=uk_gcloud15_signals_2026_08
name=UK G-Cloud 15 signals August 2026
title=G-Cloud 15 launch and RM1557.15 framework signals
category=Cloud Infrastructure
jurisdiction=UK
publisher=Government Commercial Agency
frameworkId=RM1557.15
frameworkName=G-Cloud 15
sourceUrl=https://www.gov.uk/government/news/g-cloud-relaunches-with-biggest-upgrade-in-its-history
relatedUrl=https://www.webprod-cms.crowncommercial.gov.uk/agreements/RM1557.15
asOfDate=2026-08-10
startDate=2026-08-06
endDate=2028-02-05
gCloud14ExpiryDate=2026-10-28
demoBatch=category-strategy-public-2026-09-29
```

**Body** (paste as the document text)

```
SOURCE A: GOV.UK news — “G-Cloud relaunches with biggest upgrade in its history”
From: Government Commercial Agency
Published: 10 August 2026
URL: https://www.gov.uk/government/news/g-cloud-relaunches-with-biggest-upgrade-in-its-history

SOURCE B: GCA agreement page — G-Cloud 15 (RM1557.15)
URL: https://www.webprod-cms.crowncommercial.gov.uk/agreements/RM1557.15
Agreement number: RM1557.15
Start date: 06/08/2026
End date: 05/02/2028
Regulation: Procurement Act 2023
Agreement type: Open Framework
Demo ingest batch: category-strategy-public-2026-09-29.

WHAT CHANGED — FRAMEWORK
- G-Cloud 15 consolidates three previously separate frameworks (Cloud Compute 2 and Lots 1–3 and 4 of G-Cloud 14) into a single commercial agreement.
- First G-Cloud agreement launched since GCA was formed on 1 April 2026 (CCS combined into GCA).
- First G-Cloud iteration to operate under the Procurement Act 2023 and adopt an open framework format.
- Framework valued at approximately £14 billion over a 4-year term, with an estimated £3 billion in annual public sector cloud spend flowing through it.
- Call-off contracts can run up to a maximum of 60 months.
- Approximately 90% of suppliers are SMEs; new / growing businesses can join during an 18-month reopening window after launch and at regular intervals during the term.
- Supplier evaluation assesses quality, technical capability and price so buyers can call off with greater assurance, while still being able to compete at call-off.

TRANSITION / EXPIRY SIGNAL
- G-Cloud 14 remains operational until its expiry on 28 October 2026. All call-off contracts under G-Cloud 14 must be in place (signed) by that date.
- G-Cloud 15 has replaced G-Cloud 14 for new buying under RM1557.15.

SERVICES IN SCOPE (RM1557.15)
- IaaS and PaaS (Lot 1a; Lot 1b above OFFICIAL)
- Infrastructure software as a service / I-SaaS (Lot 2a)
- Other SaaS (Lot 2b)
- Cloud support services (Lot 3)

BUY ROUTES
1) Award without competition — straightforward / catalogue-met needs; award based on lowest price after filters and exclusion checks.
2) Competitive selection process — complex / high-value / tailored needs; award based on most advantageous tender (MAT).

WHEN YOU CANNOT USE G-CLOUD 15
- Contingent labour
- Co-location (use Crown Hosting)
- Non-cloud consultancy / hardware / bespoke design-development (use the named alternative frameworks on the agreement page)
- Recruitment is not included; only support relating to the cloud is permitted, not provision of staff or interims.

AVAILABLE FOR
Central government, charities, education, health, local authority, blue light, devolved administrations, British overseas territories.
```

---



## User request (paste only this — do not paste document excerpts)

```
Prepare the Category Strategy Intelligence Briefing for UK public-sector cloud hosting and cloud services for Cloud SteerCo.

Ground only in ingested docs:
- UK-OGCS-CLOUD-GUIDE-2023
- UK-CLOUD-FIRST-COMMERCIAL-PRIORITIES-2023
- UK-GCLOUD15-SIGNALS-2026-08

This cycle focus:
1) G-Cloud 14 → G-Cloud 15 transition before the 28 Oct 2026 call-off signing deadline
2) Single-cloud vs multi-cloud / hybrid under OGCS lock-in and concentration-risk guidance
3) MoU / cost-monitoring behaviour under award-without-competition vs competitive selection on RM1557.15
4) Departmental data residency / offshoring decisions vs G-Cloud 15 cloud-support (not contingent labour) scope

Do not invent spend, supplier awards, or clauses missing from retrieved context.
```

The job template already carries the briefing sections, ACT / INVESTIGATE / MONITOR / MAINTAIN rules, and per-issue fields. Do not restate those in the User request.

After a backend restart (template seed), re-run with the same User request — the Category Strategy job now uses a category glossary (not MSA/SOW), bans invented owner timings, and requires source-faithful Change language plus distinct MoU / cost / AWOC treatment.

**Retrieval note:** do not re-ingest. A bug treated `award-without-competition` as a `contractId` and returned **0 chunks** on prior runs — that is fixed. Re-run the same job; Technical details → Retrieval events should show `resultCount > 0` and real `[source:UK-…]` citations.

---



## Optional US alternate (if you want a second pack later)

- Strategy: [Federal Cloud Computing Strategy / Cloud Smart (24 Jun 2019)](https://bidenwhitehouse.archives.gov/wp-content/uploads/2019/06/Cloud-Strategy.pdf) — Category Management section  
- Signals: [GAO-26-107530 Cloud Computing: Federal Government Needs to Address Procurement Challenges (Jun 2026)](https://www.gao.gov/assets/gao-26-107530.pdf) — cost control, FAR gaps, multi-vendor interoperability

Prefer the UK pack above for one coherent jurisdiction and OGL-reusable text.