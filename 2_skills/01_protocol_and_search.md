# 01 — Protocol and three-database search

The executable strings are in `1_workspace/search_strings.txt`. Each section
records a provider-specific title/abstract Boolean query; [review] records dates,
a 5,000-record-per-query default, the embedding query and cutoff. Execute
`python 2_skills/engine.py search-plan`, optionally with `--dbs openalex,arxiv`.
Each run saves the exact query and outcome in `search_runs/<run_id>.txt` and
SQLite audit history. OpenAlex uses search.title_and_abstract; arXiv uses ti:/abs:;
PubMed uses [Title/Abstract]. Do not search full text or fetch PDFs at this stage.
Records without titles are logged and skipped; such runs remain incomplete.
OpenAlex uses 100-record pages, basic paging up to 10,000 without a key, or
cursor paging with a key. Caps, skips and provider errors must be disclosed.

Read AGENTS.md and the active protocol overrides. Complete the RQs, PICOC, date
range, publication types, eligibility rules, extraction variables, and synthesis
plan. Change protocol Status to READY when these definitions are usable. Do not
choose an arbitrary research topic to fill the template.

Before the first search, agree on selected providers, per-query caps, and date
cutoffs, then record them in the protocol and executable search plan. Reuse
already authorized settings. OpenAlex can be the selected general index;
arXiv and PubMed provide complementary coverage for preprints and biomedical
literature. Justify the provider set for the RQs rather than claiming that any
single index guarantees complete coverage. The current plan defaults to 5,000
records per query; explicitly report caps and split large queries when needed.

Translate concepts separately: OpenAlex uses its `search` syntax; arXiv uses
fielded expressions such as `all:` or `ti:`; PubMed supports field tags and MeSH.
There is no universally equivalent Boolean string. Record each translation and
its limits in the protocol. Use separate `search --dbs` invocations when syntax
differs. `--max-results` applies per database, not to the combined corpus.

```text
python 2_skills/engine.py init
python 2_skills/engine.py search --query "retrieval augmented generation" --dbs openalex --max-results 5000
python 2_skills/engine.py search --query '(ti:"retrieval augmented generation" OR abs:"retrieval augmented generation")' --dbs arxiv --max-results 5000
python 2_skills/engine.py search --query '"retrieval augmented generation"[Title/Abstract]' --dbs pubmed --max-results 5000
python 2_skills/engine.py checkpoint --message "Search round recorded"
```

The commands illustrate shell syntax, not the review's search strategy. Use
PowerShell single-quoted strings around queries containing literal double quotes.
OpenAlex supports optional mailto/API key; cursor paging may require a key.
arXiv calls are paced at least three seconds apart. NCBI is paced conservatively
and uses XML esearch/efetch. PubMed retrieval above its 9,999-result search window
is explicitly incomplete; partition searches by date rather than silently losing
records. Credentials and cookie jars must remain outside Git.

The engine preserves per-source record identities and search outcomes in audit_log.
Repeated queries do not inflate identified counts. DOI/PMID/arXiv/OpenAlex matches
are preferred to a normalized title prefix; conflicting identifiers are not merged
by title alone. Title matches can still need reviewer adjudication, particularly
preprints, corrections, companion reports, and generic titles. Merged metadata and
source memberships retain stable BibTeX keys; the bibliography is regenerated
atomically from SQLite so a repeated search cannot duplicate entries.

Review every failure, truncation warning, total, and query translation before
calling retrieval complete. `update` reuses recorded strings and start dates, with
inclusive date overlap. Repeat full searches periodically for delayed indexing.
See [OpenAlex authentication](https://help.openalex.org/api/authentication/),
[arXiv API manual](https://info.arxiv.org/help/api/user-manual.html), and
[NCBI E-utilities](https://www.ncbi.nlm.nih.gov/books/NBK25499/).
