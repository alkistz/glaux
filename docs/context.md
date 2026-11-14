# Project context

Captured on 2026-11-14 from the research and design conversation that started this repo.
Source links are at the end. Claims marked (unverified) were not checked against the live services.

## Goal

Build tools on Greek open government data that help identify and monitor corruption risk in governance
and public finances: surface unusual data and potentially trigger investigations. Corruption is not
measured directly. The aim is risk signals that point a human reviewer to places worth a closer look.

Decision: start with a more usable Diavgeia (vector search and metadata extraction), because every later
indicator depends on being able to find, filter and link decisions.

Decision (2026-11-14): the end product is a public web app that people can use, not only a private
tool. The MVP is the smallest public version: search plus decision pages (see roadmap step 4). Phase 1
builds the backend it runs on. What the public app may show about named people and companies is still
open (see open questions).

## Open data landscape in Greece

- **data.gov.gr**: national portal, relaunched May 2026 on CKAN. Reported size: 9,523 datasets, 31,441
  resources, 455 organisations (Protothema, May 2026); the EU data portal's write-up says 22,000+ datasets.
  The counts disagree, probably on how datasets are counted. 16 thematic categories. CKAN Action API at
  `/api/3/action/` (unverified), DCAT-AP metadata, bulk download in CSV/JSON/XML/XLSX. An older per-dataset
  API needed a token. Many older datasets were aggregates (daily or annual counts), not granular records.
- **Diavgeia**: every public body must publish its decisions. Official OpenData API, no key. 5,400+ bodies,
  millions of decisions. Decisions are PDFs with limited metadata. Diavgeia's own search matches exact word
  forms only, which is a real usability problem for inflected Greek. Third-party descriptions say the API has
  no server-side amount filter.
- **KIMDIS** (central electronic registry of public contracts, part of ESIDIS): records all contracts
  regardless of value, including below-threshold awards, which is where direct awards live. Used in an LSE
  Hellenic Observatory network analysis of 2018 to 2025 awards.
- **data.nap.gov.gr**: transport National Access Point (ferries, KTEL buses, air, motorways, road weather, OSM extract).
- **Also to check**: TED notices (EU, above threshold), business registry (GEMI), Mitos (procedure
  catalogue, reportedly SOAP), EU-funded project data (old NSRF system).
- **Quality context**: Greece scored 56% in the EU Open Data Maturity 2024 assessment against an EU average
  of 83%; weakest dimension was impact (38% vs 80%). Rank 28th in 2024, down from 13th in 2022.

## Why procurement and spending data

- Public procurement is about 12% of Greek GDP and the government activity most vulnerable to waste,
  mismanagement and corruption (OECD).
- Single Market Scoreboard 2024, Greece: single-bidder share 55% (EU mid-ranking country 28%), decision
  speed 125 days (74), 80% of procedures awarded to the cheapest bid (54%).
- Citizens perceive corruption as very widespread (Eurobarometer 2022: 98% in Greece vs 68% EU average;
  Liberties 2026 report: 97% vs 69%). The Commission's 2026 rule of law chapter says the track record of
  high-level corruption prosecutions remains low.
- Rules changed recently: the direct-award ceiling rose from EUR 20,000 to EUR 30,000, and Law 5218/2025
  (July 2025) tightened publication duties for below-threshold awards. Rule changes create structural
  breaks in any time series. Account for them.

## Key design consequence

Greece's baseline is already high. A naive "single bidder = suspicious" rule would flag over half of all
procedures. Score each procedure against peers (same buyer type, sector, region, value band) and look for
outliers, rather than using absolute thresholds.

## Candidate risk indicators (for later phases)

From the Open Contracting Partnership red-flag guide and the Fazekas corruption-risk-index work, plus
Greece-specific additions:
- single bidding in otherwise competitive markets
- non-open procedure, or no published call for tender
- unusually short advertisement period
- contract clustering just under the direct-award ceiling (also slicing)
- repeated awards between one buyer and one supplier, buyer-supplier network concentration
- contract value growth after award (modifications)
- Diavgeia decisions and payments that do not reconcile with registered contracts
- supplier profile: very new firm winning large awards, tax-haven ownership
- data-quality signals: tax IDs failing the checksum, missing or inconsistent metadata

Literature is explicit that these signal risk, not corruption. Data errors matter more when results feed
audits or investigations, so every flag needs verification with additional information.

## Prior art

- Opentender.eu (DIGIWHIST): EU procurement red flags, mostly TED-published above-threshold tenders.
- Transparency International EU, Integrity Watch Red Flags.
- Academic Greek procurement network analyses.
- An open corpus of about 1 million Diavgeia decisions with PDF text extracted (arXiv 2512.05647); may save
  extraction work.
- Third-party Diavgeia scrapers and aggregators exist; none verified.

Gap this project targets: joining Diavgeia, KIMDIS and registry data for Greece, including the
below-threshold space the EU-level tools barely see.

## Architecture decisions so far

- Postgres plus pgvector, one store for keyword and vector search (alternative considered: Elasticsearch).
- BGE-M3 multilingual embeddings (covers Greek). Subjects embedded for everything in scope; document
  chunks only for chosen decision types, since chunk embedding is the expensive part.
- Hybrid ranking by reciprocal rank fusion over four lists: FTS subjects, FTS chunks, vector subjects, vector chunks.
- Text normalised for search: lowercase, accents stripped, final sigma folded. Postgres FTS config `simple`
  for now.
- Day-by-day resumable harvest keyed on issue date.
- Regex extraction (tax IDs with checksum, amounts in Greek format, CPV, KIMDIS ids, ADA references) kept
  alongside structured API fields, both stored, never merged destructively.
- KIMDIS ids extracted from text are the planned join key to procurement records.

## Legal and ethical constraints

- Decisions may contain personal data (GDPR). Skip `private_data`, collect the minimum, do not republish
  personal data.
- Publishing named suspicion about people or companies carries defamation risk. Score authorities and
  procedures, publish methodology, keep named-entity leads in a private triage queue.
- Route verified leads to the Hellenic National Transparency Authority (aead.gr), investigative
  journalists or prosecutors, with a human-reviewed case file, not a raw score.
- Be a polite client of public services.
- A public web app makes us a controller of the personal data it shows, separately from Diavgeia.
  It needs a legal basis, a privacy notice, a way to handle objection and erasure requests, and a check
  of the reuse licence for Diavgeia data. Link to the official document on Diavgeia rather than
  re-hosting PDFs. Get legal advice before launch.

## Roadmap

1. Validate and fix the pipeline against the live API (`glaux probe`), build real fixtures.
2. Run a one-week harvest, time every stage, then scope the real corpus (years, decision types, bodies).
3. Evaluate extraction precision on about 100 hand-checked decisions, per field.
4. Public web app, MVP: search with filters Diavgeia lacks (amount, decision chain), a page per
   decision with its structured facts and a link to the official PDF, and a page per authority with
   spending statistics. No risk scores, natural persons masked. Hosted in the EU.
5. OCR for scanned PDFs (Tesseract, `ell` model).
6. Pull KIMDIS contracts and join on ADAM. Add TED and registry data where useful.
7. Peer-benchmarked risk indicators, back-tested on publicly known cases from the press. Published,
   if at all, only at authority and procedure level.
8. Triage interface (private) and a documented path for passing leads to authorities.

## Open questions

- Name: `glaux` chosen on 2026-11-14 (owl of Athena, owl on Athenian silver coins, vigilance). Known overlap: GLAUx is an existing Ancient Greek corpus and query project by Alek Keersmaekers. Availability on PyPI and GitHub was not confirmed; check before publishing anything under this name.
- Which decision types and which years define the first real corpus.
- Where this runs long term. A public app needs a server that holds the database and runs the query
  embedding model, so database size and model choice drive hosting cost.
- Who the public app is for first: journalists and researchers, citizens and local councillors, or
  businesses following public spending. The answer shapes the search and the pages.
- What the public app shows about payees: companies (legal persons) by name, natural persons and sole
  traders masked. Needs a rule to tell them apart (legal-form words such as Α.Ε., Ε.Π.Ε., Ι.Κ.Ε. in
  the name, tax ID patterns, later the business registry).

## Sources

- data.europa.eu, Greece relaunches its national open data portal: https://data.europa.eu/en/news-events/news/greece-relaunches-its-national-open-data-portal
- Protothema on data.gov.gr: https://en.protothema.gr/2026/05/14/data-gov-gr-is-greeces-new-national-open-data-portal-what-it-means-for-citizens-businesses-and-ai/
- Open Contracting Partnership, Red flags in public procurement (2024): https://open-contracting.org/wp-content/uploads/2024/12/OCP2024-RedFlagProcurement-1.pdf
- Fazekas and Kocsis, Corruption Risk Indicators (QoG): https://datafinder.qog.gu.se/dataset/cri
- U4, measuring corruption in government contracts: https://www.u4.no/blog/from-transparency-to-metrics-measuring-corruption-in-government-contracts
- LSE Hellenic Observatory paper on KIMDIS (GreeSE 219): https://www.lse.ac.uk/asset-library/hellenic-observatory/greese-no219.pdf
- EU Single Market Scoreboard, Greece: https://single-market-scoreboard.ec.europa.eu/node/314_cs
- OECD, Managing public procurement risks in Greece: https://www.oecd.org/en/publications/managing-public-procurement-risks-in-greece_27156f7c-en.html
- Open Data Maturity 2024 factsheet, Greece: https://data.europa.eu/sites/default/files/country-factsheet_greece_2024.pdf
- iMEdD, The slow death of open data in Greece: https://lab.imedd.org/en/?p=9919
- Greek Diavgeia decisions dataset (arXiv): https://arxiv.org/abs/2512.05647
- Liberties Rule of Law Report 2026, corruption trends: https://www.liberties.eu/en/stories/rolreport2026-corruption/45618
- Commission 2026 Rule of Law Report, Greece chapter (SWD(2026) 908)
- Transparency International EU, Integrity Watch Red Flags: https://transparency.eu/integrity-watch-red-flags/
- Transport NAP: https://data.nap.gov.gr