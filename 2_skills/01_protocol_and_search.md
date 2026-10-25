# 01 — Protocol and Provider-Configurable Paper Gathering

Read AGENTS.md and the active protocol overrides. Complete the RQs, PICOC, date
range, publication types, eligibility rules, extraction variables, and synthesis
plan. Change protocol Status to READY when these definitions are usable. Do not
choose an arbitrary research topic to fill the template.

## User-Driven Provider Selection and Capping in OpenCode

Before executing any database queries, the model must interactively consult and
confirm with the user through OpenCode:

1. **Target Providers / Databases**:
   - Determine which providers to query (`openalex`, `arxiv`, `pubmed`, or a combination).
   - *Default recommendation*: For most domains (e.g., Computer Science, Engineering, Social Sciences), **OpenAlex alone** is often sufficient as it comprehensively indexes Crossref, PubMed, arXiv, and institutional repositories. Highlight to the user that OpenAlex unifies search syntax.
   - For biomedical reviews requiring specific MeSH vocabulary trees, include `pubmed`.
   - For fast-moving AI/ML topics requiring preprints before publisher indexing, include `arxiv`.
2. **Per-Provider Result Limits (`--max-results`)**:
   - Confirm whether the user wants to truncate or limit papers retrieved per provider (e.g., 50, 100, 200, 500). Default is 200 per database.
3. **Date Cutoffs (`--since YYYY-MM-DD`)**:
   - Confirm whether the search should be bounded by publication date.

Record the agreed database selection, caps, and queries in `1_workspace/protocol.md`.

## Execution and Translation

Translate concepts separately for each selected provider:
- **OpenAlex** uses its `search` syntax or filter expressions.
- **arXiv** uses fielded expressions such as `all:` or `ti:`.
- **PubMed** supports field tags such as `[Title/Abstract]` and MeSH terms.

Use separate `search --dbs` invocations when syntax or caps differ per provider:

```text
python 2_skills/engine.py init
python 2_skills/engine.py search --query "retrieval augmented generation" --dbs openalex --max-results 150
python 2_skills/engine.py search --query "all:\"retrieval augmented generation\"" --dbs arxiv --max-results 50
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
