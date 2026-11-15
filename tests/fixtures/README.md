# Test fixtures

Trimmed copies of real responses from the Diavgeia OpenData API (`https://diavgeia.gov.gr/opendata/`),
cut from `glaux probe` output. Everything is as published except the replacements listed below.

## Personal data replaced

Checked by hand on 2026-11-15 before committing.

- Payee and contractor names (`sponsor[].sponsorAFMName.name`, `person[].name`) are replaced with
  placeholders that keep the shape of the original: the legal-form suffix for companies (`Α.Ε`,
  `& ΣΙΑ Ε.Ε`) and the `SURNAME,,FIRST,FATHER` format for a natural person. The same replacement is
  applied where the name appears in a subject.
- Their tax IDs are replaced with obviously fake ones that pass the checksum: `000000012`,
  `000000024`, `000000036`, `000000048`, `000000050`.
- `signerIds` are replaced with `9000000NN`, and version-log `creator` values with `0000_NNNN`.
- `odeManagerEmail` in organisations is `redacted@example.invalid`.

Public bodies (paying organisations, their tax IDs and units) are kept as published. ADAs are real,
so the official documents can be looked up, but the payee details in these files no longer match them.

## Files

All in `diavgeia/`.

| File | Source request | Fetched | Notes |
|---|---|---|---|
| `search_page.json` | `search.json?from_issue_date=2026-10-14&to_issue_date=2026-10-14&size=500` | 2026-11-14 | `info` unchanged; `decisions` trimmed to one per spending type (Β.2.1, Β.2.2, Β.1.3, Δ.1, Δ.2.1, Δ.2.2). All have the Athens-midnight issue date encoding. |
| `search_advanced_page.json` | `search/advanced.json?q=issueDate:[DT(2026-10-14T00:00:00) TO DT(2026-10-14T23:59:59)]&size=10` | 2026-11-15 | Trimmed to two decisions: one with each issue date encoding (00:00 and 03:00 Athens). |
| `search_advanced_revoked.json` | `search/advanced.json?q=status:"Ανακληθείσα" AND submissionTimestamp:[2026-11-01 to 2026-11-13]&size=3` | 2026-11-15 | Trimmed to one revoked decision. |
| `decision_B21.json` | `decisions/93ΨΣ7ΛΛ-8ΒΘ.json` | 2026-11-14 | Same record as the Β.2.1 entry in `search_page.json`. Its payees are two employees (travel expenses). |
| `versionlog.json` | `decisions/93ΨΣ7ΛΛ-8ΒΘ/versionlog.json` | 2026-11-14 | One published version. |
| `versionlog_revoked.json` | `decisions/ΨΙΖ0469Η2Ξ-ΙΦΛ/versionlog.json` | 2026-11-15 | Published, then revoked with a reason. |
| `types.json` | `types.json` | 2026-11-14 | Complete. |
| `type_details_B21.json` | `types/Β.2.1/details.json` | 2026-11-14 | Complete. |
| `organizations.json` | `organizations.json` | 2026-11-14 | Trimmed to the 8 bodies referenced by the decisions above. |
| `search_terms.json` | `search/terms.json` | 2026-11-15 | Complete list of advanced search terms. |
