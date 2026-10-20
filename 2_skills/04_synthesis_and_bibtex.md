# 04 — Evidence synthesis and reproducible flow

Run `python 2_skills/engine.py prisma`. It prints and inserts a generated summary
and Mermaid flowchart between PRISMA markers in `synthesis_report.md`, preserving
all narrative outside those markers. No diagram counts are manually invented.

Identified counts are distinct source-record identities retrieved, counted once
per database across reruns. They are not provider-estimated hit totals. Duplicates
removed equal identified source records minus distinct canonical paper keys.
Historical decision events preserve title/abstract and full-text stages despite
the one-row current screening schema. Current MAYBE decisions are unresolved,
not exclusions. A reopened earlier stage supersedes its previous full-text
decision. Missing/manual PDFs are retrieval outcomes, not eligibility decisions.
Pending retrieval and unresolved assessments remain visible; do not silently
reclassify them to make a flow diagram balance.

Final Included means FULL_TEXT INCLUDE reports. Before claiming a number of
studies, link multiple reports of the same study in narrative and explain that
linkage. Search caps, errors, late indexing, and pending adjudication must be
reported. Consult the [PRISMA 2020 resources](https://www.prisma-statement.org/prisma-2020).

Use the extraction matrix as traceable evidence. Compare findings by RQ,
population, design, intervention, outcomes, and risk of bias. Preserve disagreement,
null findings, uncertainty, units, denominators, and time points. Avoid vote counting
and unsupported causal claims. Pool effects only under the prespecified analysis
plan; otherwise write a structured narrative synthesis.

Every paper reference in workspace Markdown must use
`[@BibKey](../3_papers/raw_pdfs/BibKey.pdf) ([DOI](https://doi.org/...))`, with arXiv
or PubMed replacing DOI when absent. Do not use bare citation keys or guessed
identifiers. `references.bib` is synchronized from SQLite on search/init/checkpoint;
do not hand-edit it. Metadata enrichment preserves previously assigned keys.

Write title/abstract, rationale, methods, results, risk of bias, discussion,
limitations, registration/amendments, funding/conflicts, and data availability.
Disclose agent assistance and human adjudication honestly. Checkpoint the completed
synthesis. For a living review, run `update`, screen new records in capped batches,
and document any conclusions that changed.
