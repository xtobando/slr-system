# Systematic literature review protocol

Status: DRAFT
Version: 1
Review title: Not yet specified.
Review owner: Not yet specified.
Registration and amendments: Not yet registered; record dated amendments here.

## Research Questions

No research questions have been specified. Define answerable RQ1, RQ2, and further
questions as needed before searching or screening.

## PICOC

| Component | Operational definition |
|---|---|
| Population | Not yet specified |
| Intervention | Not yet specified |
| Comparison | Not yet specified; explicitly mark not applicable when appropriate |
| Outcomes | Not yet specified |
| Context | Not yet specified |

## Search strategy

Selected providers / databases: OpenAlex (can be configured to OpenAlex only, or include arXiv and PubMed as decided by user).
Per-provider max results / truncation caps: Default 200 per provider (or user-specified limit).
Date coverage, languages, publication types: Not yet specified.
Publication date cutoff (`--since`): Not yet specified.
Search date and exact executed strings: Preserved in SQLite audit_log.
Canonical concepts and synonyms: Not yet specified.
OpenAlex query: Not yet specified.
arXiv query with field operators: Not yet specified (or marked N/A if not queried).
PubMed query with MeSH/free-text alternatives: Not yet specified (or marked N/A if not queried).
Search completeness: Review provider totals and all capped/failed runs; do not
describe a capped query as exhaustive. Preserve each translated string.

## Eligibility criteria

These criterion codes are a starting structure. Define their topic-specific
boundaries and eligible evidence types before use; document any amendments.

| Code | Rule |
|---|---|
| IC1 | Population and context satisfy the completed PICOC definitions |
| IC2 | The report supplies evidence answering at least one defined RQ |
| EC1 | Explicit evidence establishes a population/context outside scope |
| EC2 | Explicit evidence establishes an excluded publication or study type |
| EC3 | Explicit evidence establishes an outcome/intervention outside scope |

Unknown eligibility remains MAYBE using the relevant criterion, never EXCLUDE
solely because an abstract or PDF is missing. Record one primary exclusion reason.
Report retrieval failures separately. A preprint and later journal report may be
the same study; review their relationship before synthesizing both.

## Extraction variables and quality assessment

Define variable names, units, denominators, time points, comparison groups, and
missing-data conventions before extraction. Include study design, sample/context,
intervention, comparison, outcomes, intrinsic literature limitations, and RQ mapping where applicable.
Select and justify a domain-appropriate risk-of-bias instrument. Record supporting
quotes and pages for each assessment; do not fabricate a universal quality score.

## Synthesis plan

Group evidence by RQ, study design, and comparable outcomes following the structure
defined in `1_workspace/SLRBlueprint.tex`. Explain heterogeneity, negative findings,
conflicting evidence, and intrinsic literature limitations. When drafting the paper,
focus on the limitations within the synthesized primary literature per se (methodological,
theoretical, sample, and validity constraints), and do not discuss review/search limitations
outside the methodology section. Do not pool incompatible effects or count reports as
independent studies. Prespecify any meta-analysis.

## Active Reasoning Clarifications & Overrides

No user-specific corrections have been recorded. Permanent corrections must state
the date, triggering error, actionable rule, affected papers/criteria, and outcome
of re-screening. Cite papers using clickable local PDF and external identifier links.

## Review progress

No search, screening, extraction, or synthesis has been completed.
Use `engine.py status` for authoritative live counts.
