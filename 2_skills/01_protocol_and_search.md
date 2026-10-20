# 01 — Protocol and three-database search

Read AGENTS.md and the active protocol overrides. Complete the RQs, PICOC, date
range, publication types, eligibility rules, extraction variables, and synthesis
plan. Change protocol Status to READY when these definitions are usable. Do not
choose an arbitrary research topic to fill the template.

Translate concepts separately: OpenAlex uses its `search` syntax; arXiv uses
fielded expressions such as `all:` or `ti:`; PubMed supports field tags and MeSH.
There is no universally equivalent Boolean string. Record each translation and
its limits in the protocol. Use separate `search --dbs` invocations when syntax
differs. `--max-results` applies per database, not to the combined corpus.

```text
python 2_skills/engine.py init
python 2_skills/engine.py search --query "retrieval augmented generation" --dbs openalex --max-results 200
python 2_skills/engine.py search --query "all:\"retrieval augmented generation\"" --dbs arxiv --max-results 200
python 2_skills/engine.py search --query "retrieval augmented generation[Title/Abstract]" --dbs pubmed --max-results 200
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
