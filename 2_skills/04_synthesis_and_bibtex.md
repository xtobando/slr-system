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

## LaTeX SLR Manuscript Generation (`SLRBlueprint.tex`)

When drafting the final review manuscript in LaTeX (`1_workspace/manuscript.tex`), you must strictly adhere to the layout and structural specification in [`1_workspace/SLRBlueprint.tex`](../1_workspace/SLRBlueprint.tex):
- Keep documentclass `\documentclass[11pt]{article}`, geometry margins (`[margin=1in]{geometry}`), paragraph formatting (`\setlength{\parindent}{0pt}`, `\setlength{\parskip}{1\baselineskip}`), and core packages (`amsmath,amssymb`, `tikz-cd`, `multicol`).
- Structure the document strictly following the blueprint sections:
  1. `\title{[Systematic Literature Review Title]: A Systematic Literature Review}`
  2. `\author{[Author Name]\thanks{[Affiliation and contact information]}}`
  3. `\maketitle`
  4. `\begin{abstract}`: One unstructured paragraph that introduces the topic and motivation, states the review objective and method, reports the number of included primary studies, summarizes the synthesis dimensions and main findings, and identifies principal research gaps.
  5. `\textbf{Keywords:}`
  6. `\section{Introduction}`
  7. `\section{Methodology}`
     - `\subsection{Research Questions}`
     - `\subsection{Search of Primary Studies}`
     - `\subsection{Analysis of Primary Studies}` (with `\subsubsection{Inclusion and Exclusion Criteria}` and `\subsubsection{Quality Assessment}`)
     - `\subsection{Data Extraction}`
     - `\subsection{Threats to Validity}` (with `\subsubsection{Incomplete Selection of Primary Studies}`, `\subsubsection{Biased Analysis of Primary Studies}`, and `\subsubsection{Inaccurate Data Extraction}`)
  8. `\section{Results and Discussion}`
     - `\subsection{Study Overview}`
     - `\subsection{Results of RQ1: [Insert Research Question]}` (with dimension-specific `\subsubsection` elements)
     - `\subsection{Results of RQ2: [Insert Research Question]}`
     - Further RQs as defined in the protocol.
  9. `\section{Conclusions}`: Answer review objectives and RQs; summarize key findings, implications, and literature limitations without introducing new evidence.
  10. `\section{Future Work}`: Translate literature evidence gaps into specific, actionable research directions.
  11. Unnumbered end sections:
      - `\section*{Funding}`
      - `\section*{Acknowledgments}`
      - `\section*{Conflicts of Interest}`
      - `\section*{Abbreviations}`
      - `\section*{References}` (using standard BibTeX referencing matching entries in `3_papers/references.bib`).

### Critical Guidance on Limitations
* **Intrinsic Literature Limitations ONLY**: When discussing limitations in the synthesis, discussion, conclusions, and future work, **strictly focus on the limitations of the primary literature per se** (e.g., methodological constraints, narrow sample populations, confounding factors, lack of longitudinal validation, unstandardized evaluation metrics, domain assumptions in the reviewed studies).
* **Do NOT Discuss Search Limitations in Literature Analysis**: Do not discuss review or search limitations (such as search engine boundaries, keyword filtering, retrieval caps, or query omissions) when presenting the state of the art, synthesized evidence, conclusions, or literature limitations. Threats regarding the search process belong solely under `\subsubsection{Incomplete Selection of Primary Studies}` in the Methodology section. Everywhere else, limitations must exclusively reflect deficiencies, weaknesses, and constraints intrinsic to the reviewed literature itself.

Write title/abstract, rationale, methods, results, risk of bias, discussion,
literature limitations, registration/amendments, funding/conflicts, and data availability.
Disclose agent assistance and human adjudication honestly. Checkpoint the completed
synthesis. For a living review, run `update`, screen new records in capped batches,
and document any conclusions that changed.
