# SLR Agent System

A local systematic literature review workspace combining an AI agent's reading and reasoning with a Python CLI for search, persistence, ranking, PDF processing, evidence validation, and reporting.

The agent wrapper supplies the language model and image-inspection tools. The Python engine makes **no LLM API calls**. Review decisions and evidence persist in SQLite and Markdown, so work can resume in a new session.

- [1. Setup](#1-setup)
- [2. Usage guide](#2-usage-guide)

## 1. Setup

### Requirements

- Python 3.10 or newer, with `pip` and virtual-environment support.
- Git available on `PATH`, including when commands run inside an agent wrapper.
- Network access for database queries, PDF downloads, GitHub operations, and the first FastEmbed model download.
- An agent wrapper with file, terminal, and image-inspection tools for the assisted review workflow. OpenCode is an example; install and authenticate it separately.

The core packages are `requests`, `python-dotenv`, `PyMuPDF`, and `numpy`. FastEmbed is optional. SQLite is provided by Python.

### Clone and install

Clone the repository, then run the remaining commands from its root. Virtual environments stay under `1_workspace/` to retain the three application folders.

**Windows PowerShell**

```powershell
git clone https://github.com/xtobando/slr-system.git
Set-Location slr-system
python -m venv 1_workspace/.venv
.\1_workspace\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
if (-not (Test-Path -LiteralPath .env)) { Copy-Item .env.example .env }
python 2_skills/engine.py init
python 2_skills/engine.py status
```

If your Windows installation exposes `py` rather than `python`, use `py -3 -m venv 1_workspace/.venv` for the environment-creation step.

**Activate an existing environment on Windows**

In each new PowerShell terminal, change to the repository root and run:

```powershell
.\1_workspace\.venv\Scripts\Activate.ps1
python -c "import sys; print(sys.executable)"
```

The printed interpreter path should end in `1_workspace\.venv\Scripts\python.exe`. Launch OpenCode from this activated terminal so it inherits the environment. To leave the environment, run `deactivate`.

If you use **Command Prompt (`cmd.exe`)**, activate with:

```bat
1_workspace\.venv\Scripts\activate.bat
```

If PowerShell blocks the activation script, use the environment's interpreter directly:

```powershell
& ./1_workspace/.venv/Scripts/python.exe -m pip install -r requirements.txt
& ./1_workspace/.venv/Scripts/python.exe 2_skills/engine.py status
```

To make that interpreter available to a wrapper launched from the same PowerShell terminal without activation, prepend its Scripts directory for that terminal:

```powershell
$env:PATH = (Resolve-Path '1_workspace/.venv/Scripts').Path + ';' + $env:PATH
```

These options follow Python's [virtual-environment activation instructions](https://docs.python.org/3/library/venv.html#how-venvs-work).

**macOS or Linux**

```bash
git clone https://github.com/xtobando/slr-system.git
cd slr-system
python3 -m venv 1_workspace/.venv
1_workspace/.venv/bin/python -m pip install -r requirements.txt
if [ ! -f .env ]; then cp .env.example .env; fi
source 1_workspace/.venv/bin/activate
python 2_skills/engine.py init
python 2_skills/engine.py status
```

Repeat environment activation in each new terminal (or the session-only `PATH` fallback above). All subsequent examples use `python` from that environment. You can always invoke its full path instead. The original developer's optional `1_workspace/.runtime/` and old `.tests/` are machine-local and are not distributed with the repository; portable validation scripts are included separately.

`init` is repeatable: it creates missing directories and database tables, synchronizes the bibliography, and initializes local Git when needed. It does not clear an existing review. A fresh review starts with a DRAFT protocol; complete it before screening or ranking.

### Configure `.env`

Edit the local `.env` copied from [`.env.example`](.env.example). Empty credential fields are optional. Existing process environment variables take precedence over `.env` values.

| Variable | Default | Purpose |
|---|---|---|
| `OPENALEX_EMAIL` | Empty | Contact address for OpenAlex requests. |
| `OPENALEX_API_KEY` | Empty | OpenAlex API authentication, if available or required for your usage. |
| `NCBI_API_KEY` | Empty | API key for PubMed's NCBI E-utilities. |
| `NCBI_EMAIL` | Empty | Contact address for NCBI requests. |
| `UNPAYWALL_EMAIL` | Empty | Enables Unpaywall lookup for papers with a DOI. |
| `INSTITUTIONAL_PROXY_URL` | Empty | Library login URL prefix or template containing `{url}` or `{url_encoded}`. |
| `CUSTOM_COOKIES_PATH` | Empty | Absolute or project-relative path to a Netscape-format cookie jar for authorized PDF access. |
| `HTTPS_PROXY` / `HTTP_PROXY` | Empty | Standard HTTP transport proxies; these are separate from a library login URL. |
| `REQUESTS_CA_BUNDLE` | Empty | Path to a trusted CA bundle when your network requires one. TLS verification stays enabled. |
| `SLR_RANK_BACKEND` | `auto` | `auto`, `tfidf`, or `fastembed`; see below. |
| `SLR_EMBEDDING_MODEL` | `BAAI/bge-small-en-v1.5` | FastEmbed model name. |
| `SLR_HTTP_TIMEOUT` | `45` | HTTP read timeout in seconds; connection timeout is 10 seconds. |
| `SLR_MAX_PDF_MB` | `100` | Download-size limit in units of 1,024 × 1,024 bytes. |

Do not commit `.env`, credentials, or cookie jars. The supplied ignore rules exclude them. Institutional retrieval uses credentials you supply; it does not automate interactive login or guarantee access to every publisher. An HTML login page is rejected as a PDF.

### Enable FastEmbed semantic ranking

Install into the same environment used by the engine:

```text
python -m pip install "fastembed>=0.4,<1"
```

Set these lines in `.env`:

```dotenv
SLR_RANK_BACKEND=fastembed
SLR_EMBEDDING_MODEL=BAAI/bge-small-en-v1.5
```

Then complete the research questions and PICOC in the protocol, search for papers, and run:

```text
python 2_skills/engine.py rank
```

For a nonempty corpus, successful neural ranking reports `"backend": "fastembed+tfidf"` and the selected model. The first run downloads weights to the ignored `1_workspace/.models/` directory. An empty corpus does not load the model and therefore cannot verify the neural installation.

| Backend | Behavior |
|---|---|
| `auto` | Uses FastEmbed when it can be imported; otherwise uses TF-IDF. A model download or inference failure is reported as an error. |
| `fastembed` | Requires FastEmbed; missing dependencies or model failures produce an error. |
| `tfidf` | Uses deterministic lexical TF-IDF cosine similarity without model downloads. |

With FastEmbed, the score is `0.8 × neural cosine similarity + 0.2 × TF-IDF cosine similarity`. Papers are ranked using their titles and abstracts against the review's research questions and PICOC. Scores determine reading order, not eligibility or confidence in a finding.

### Connect an agent wrapper

Launch your configured wrapper from the repository root after activating the environment. For OpenCode, the project's requested invocation is:

```text
opencode --model openai/gpt-6.1-sol
```

The wrapper and provider must actually expose that model identifier; this project does not install OpenCode, authenticate an account, or establish model availability. Verify those steps in the wrapper's documentation. Other wrappers can use the same files and CLI if they can follow [AGENTS.md](AGENTS.md), read local files, execute commands, and inspect PNGs.

Begin a review session with a prompt such as:

> Read AGENTS.md and 1_workspace/protocol.md, then run the status command. Help me complete the protocol before searching. Follow the numbered playbooks, record evidence through engine.py, inspect relevant visual assets, and checkpoint each completed batch.

The project sets a 272,000-token context ceiling and recommends a fresh context before 200,000 tokens. These are workflow limits, not verified model capacities. Use the lower limit supported by your wrapper/model. Batch limits cannot measure the wrapper's total text and image context.

## 2. Usage guide

### What the system can do

- Search **OpenAlex, arXiv, and PubMed**, recording the executed queries, source memberships, and completion status.
- Deduplicate bibliographic records, keep stable citation keys, and synchronize a master BibTeX file.
- Prioritize reading with hybrid neural/lexical ranking or an offline lexical backend.
- Persist title/abstract and full-text decisions with quotations, eligibility codes, and an argument against inclusion.
- Retrieve available PDFs or accept manually supplied files, extract page-marked text, and render every page as a 200-DPI PNG.
- Validate textual evidence against sources, record page-specific extractions, and regenerate a clickable evidence matrix.
- Generate PRISMA counts and a Mermaid flowchart while preserving your written narrative.
- Save local Git checkpoints and rerun searches for a living review.
- Preserve reasoning corrections in the protocol and retain decision history for reassessment.

The agent or reviewer supplies scientific judgment, visual interpretation, risk-of-bias assessment, and narrative synthesis. There is no background scheduler, automatic final eligibility classifier, automatic meta-analysis, or remote-backup service. Skill updates are downloaded for review and are not installed automatically.

### Project map

The repository has three application folders. Root-level files configure and document it; `.git/`, `.env`, caches, and virtual environments are operational state.

```text
slr-system/
├── README.md
├── LICENSE
├── AGENTS.md
├── .env.example
├── .gitignore
├── requirements.txt
├── 1_workspace/
│   ├── protocol.md
│   ├── slr_state.sqlite
│   ├── extraction_matrix.md
│   ├── synthesis_report.md
│   ├── validation_report.md
│   ├── system_source.md
│   └── validation/
│       ├── test_engine.py
│       ├── live_connectors.py
│       └── package_source.py
├── 2_skills/
│   ├── 01_protocol_and_search.md
│   ├── 02_semantic_rank_screen.md
│   ├── 03_multimodal_extract.md
│   ├── 04_synthesis_and_bibtex.md
│   ├── 05_reasoning_calibration.md
│   └── engine.py
└── 3_papers/
    ├── references.bib
    ├── raw_pdfs/
    └── parsed_cache/
```

Empty corpus directories are created by `init` and may not appear immediately after cloning.

| File or directory | How to use it |
|---|---|
| [AGENTS.md](AGENTS.md) | Master operating instructions for the agent: workflow, evidence rules, batch limits, recovery, and calibration. |
| [LICENSE](LICENSE) | The MIT license already selected for this repository. |
| [.env.example](.env.example) | Copy to local `.env` and configure integrations. |
| [.gitignore](.gitignore) | Controls which credentials, environments, and corpus assets remain local. |
| [requirements.txt](requirements.txt) | Install the core Python dependencies. FastEmbed is an optional additional installation. |
| [protocol.md](1_workspace/protocol.md) | Edit research questions, PICOC, searches, eligibility, extraction variables, synthesis plan, and dated corrections. |
| `1_workspace/slr_state.sqlite` | Persistent database. Use engine commands for changes; inspect a closed copy for ad hoc analysis. |
| [extraction_matrix.md](1_workspace/extraction_matrix.md) | Generated evidence table; record evidence through the CLI rather than editing this file. |
| [synthesis_report.md](1_workspace/synthesis_report.md) | Write the narrative here, outside the generated PRISMA markers. |
| [validation_report.md](1_workspace/validation_report.md) | Validation scope, test instructions, and deployment-specific limits. |
| [system_source.md](1_workspace/system_source.md) | Generated source handoff snapshot. Edit actual project files and regenerate when needed. |
| [validation/test_engine.py](1_workspace/validation/test_engine.py) | Run the reproducible behavioral regression suite in isolated fixture workspaces. |
| [validation/live_connectors.py](1_workspace/validation/live_connectors.py) | Optional network smoke check against all three databases using isolated fixtures. |
| [validation/package_source.py](1_workspace/validation/package_source.py) | Regenerates `system_source.md` from the current source files. |
| [01_protocol_and_search.md](2_skills/01_protocol_and_search.md) | Protocol formulation, query translation, search provenance, and completeness checks. |
| [02_semantic_rank_screen.md](2_skills/02_semantic_rank_screen.md) | Reading priority, quote-first screening, and the exclusion challenge. |
| [03_multimodal_extract.md](2_skills/03_multimodal_extract.md) | Retrieval, full-text reading, visual inspection, and evidence extraction. |
| [04_synthesis_and_bibtex.md](2_skills/04_synthesis_and_bibtex.md) | Traceable synthesis, reporting, citations, and PRISMA interpretation. |
| [05_reasoning_calibration.md](2_skills/05_reasoning_calibration.md) | Permanent corrections and reassessment of affected papers. |
| [engine.py](2_skills/engine.py) | Unified deterministic CLI described below. |
| [references.bib](3_papers/references.bib) | Generated bibliography; avoid manual edits because synchronization replaces it. |
| `3_papers/raw_pdfs/` | Store original PDFs as `<bib_key>.pdf`, using keys already assigned by the database. |
| `3_papers/parsed_cache/` | Generated per-paper `fulltext.md` and `page_N_visual.png` files. |

Generated local directories also include `.venv/`, `.models/`, and `skill_updates/` beneath `1_workspace/`. Keep the three top-level application folders when extending the project.

### Workflow and review states

```mermaid
flowchart TD
    A[Complete protocol] --> B[Search and deduplicate]
    B --> C[Rank reading priority]
    C --> D[Screen titles and abstracts]
    D --> E[Retrieve PDFs]
    E --> F[Read full text and inspect visuals]
    F --> G[Record full-text eligibility]
    G --> H[Extract page-grounded evidence]
    H --> I[Write synthesis and generate PRISMA]
    I --> J[Checkpoint and push when desired]
    J --> K[Run a living-review update]
    K --> C
```

`UNSCREENED` records enter title/abstract screening. `TITLE_ABSTRACT INCLUDE` advances a paper to retrieval; only `FULL_TEXT INCLUDE` is a final included report and permits extraction. `EXCLUDE` requires a supported exclusion criterion. `MAYBE` remains unresolved and requires explicit adjudication. Missing abstracts or unavailable PDFs do not establish ineligibility.

Re-recording a title/abstract decision reopens downstream full-text eligibility. Ingesting a changed PDF also reopens full-text review. Earlier evidence remains for traceability, so reassess it before using it in the synthesis. The matrix displays current eligibility alongside retained extraction rows.

### Start or resume

Read the protocol and its active overrides, then run:

```text
python 2_skills/engine.py status
```

Complete research questions, PICOC, eligibility codes, source-specific queries, extraction definitions, and the synthesis plan. Set the protocol's `Status:` to `READY` once those definitions are usable. The status label is a coordination aid; it does not certify methodological completeness.

### Search and rank

Translate the search strategy for each provider: OpenAlex search text, arXiv field expressions, and PubMed field tags/MeSH are not interchangeable. Separate commands preserve those translations. These PowerShell examples prompt for your approved strings:

```powershell
$openAlexQuery = Read-Host "Approved OpenAlex query"
$arxivQuery = Read-Host "Approved arXiv query"
$pubmedQuery = Read-Host "Approved PubMed query"
python 2_skills/engine.py search --query "$openAlexQuery" --dbs openalex --max-results 200
python 2_skills/engine.py search --query "$arxivQuery" --dbs arxiv --max-results 200
python 2_skills/engine.py search --query "$pubmedQuery" --dbs pubmed --max-results 200
python 2_skills/engine.py rank
python 2_skills/engine.py checkpoint --message "Initial search and ranking"
```

`--max-results` is a per-database limit, not a claim of exhaustive coverage. Review capped and failed searches before proceeding. PubMed searches above its implemented 9,999-record retrieval window need query partitioning. Identifier matches are preferred for deduplication; title-based matches and relationships between preprints and journal reports still need reviewer judgment.

### Screen titles and abstracts

```text
python 2_skills/engine.py fetch-batch --phase screen --limit 15
```

The JSON batch contains unscreened records ordered by descending relevance. Read each source, copy its exact quotation first, write the strongest grounded argument against inclusion, and then apply a protocol criterion. Do not combine repeated fetches to exceed 15 abstracts in one agent turn.

Record a decision with actual evidence. The following runnable PowerShell example asks for every review-specific value instead of supplying invented quotations:

```powershell
$bibKey = Read-Host "bib_key from the fetched record"
$quote = Read-Host "Exact quotation copied from its title or abstract"
$challenge = Read-Host "Grounded argument against inclusion"
$decision = Read-Host "Decision: INCLUDE, EXCLUDE, or MAYBE"
$criterion = Read-Host "Defined protocol criterion, such as IC1 or EC1"
$notes = Read-Host "Concise rationale and unresolved issues"
python 2_skills/engine.py record-decision --bib-key "$bibKey" --stage TITLE_ABSTRACT --devils-advocate "$challenge" --quote "$quote" --decision "$decision" --code "$criterion" --notes "$notes"
python 2_skills/engine.py checkpoint --message "Title and abstract screening batch"
```

The engine requires a nonempty exclusion argument, checks textual quotations after whitespace normalization, and verifies that the criterion code exists in the protocol. INCLUDE requires an `IC` code; EXCLUDE requires an `EC` code. The CLI cannot determine whether an argument is scientifically persuasive. MAYBE records are not automatically returned as unscreened; revisit their keys explicitly.

### Retrieve PDFs and assess full text

```text
python 2_skills/engine.py ingest
python 2_skills/engine.py fetch-batch --phase extract --limit 3
```

`ingest` processes currently included papers. To process a specific existing record:

```powershell
$bibKey = Read-Host "bib_key to ingest"
python 2_skills/engine.py ingest --bib-key "$bibKey"
```

Retrieval tries the existing local PDF, available OA locations, configured Unpaywall, and an optional institutional URL. Failures are reported as `NEEDS_MANUAL_PDF` with a source link and target path. Obtain the PDF through your permitted access, save it at the displayed path, and rerun ingestion. `PARSE_ERROR` means the source needs inspection; failed retrieval is not an exclusion decision.

Each parsed paper contains physical page markers `<!-- PAGE N -->` and `[VISUAL_ASSET: ...]` links. Every page is rendered at 200 DPI, including scanned pages and pages without detected figures. These are full-page visual references; the engine does not create separate figure crops or OCR scanned pages. Read relevant sections sequentially and open the referenced PNGs with the wrapper's image tool. Inspect equations, captions, axes, units, and footnotes. The original PDF remains authoritative.

The extract batch returns paths and prior extracted variables, not entire full texts. It can include ingested title/abstract inclusions awaiting full-text assessment as well as final inclusions. Read at most three full texts per agent turn; large papers may need separate contexts.

After reading the source, record its full-text decision:

```powershell
$bibKey = Read-Host "bib_key just reviewed"
$quote = Read-Host "Exact full-text quotation supporting eligibility"
$challenge = Read-Host "Grounded argument against inclusion"
$decision = Read-Host "Full-text decision: INCLUDE, EXCLUDE, or MAYBE"
$criterion = Read-Host "Applicable defined IC or EC criterion"
$notes = Read-Host "Rationale; add vision:page=N only for a quotation actually inspected in that PNG"
python 2_skills/engine.py record-decision --bib-key "$bibKey" --stage FULL_TEXT --devils-advocate "$challenge" --quote "$quote" --decision "$decision" --code "$criterion" --notes "$notes"
```

Full-text review requires current title/abstract inclusion. For a quotation visible only in an image, `vision:page=N` in notes asserts inspection of that physical page. The engine verifies the image exists but cannot prove the agent viewed it or that its transcription is correct.

### Extract evidence and synthesize

For a `FULL_TEXT INCLUDE` paper, record each narrowly defined variable using observed evidence:

```powershell
$bibKey = Read-Host "bib_key with FULL_TEXT INCLUDE"
$variable = Read-Host "Variable defined by the extraction protocol"
$quote = Read-Host "Exact supporting quotation from the inspected physical PDF page"
$page = Read-Host "One-based physical PDF page number"
$value = Read-Host "Extracted value, preserving units and uncertainty"
$usedVision = Read-Host "1 if this evidence was visually inspected, otherwise 0"
python 2_skills/engine.py record-extraction --bib-key "$bibKey" --variable "$variable" --quote "$quote" --page "$page" --value "$value" --used-vision "$usedVision"
python 2_skills/engine.py checkpoint --message "Full-text evidence batch"
```

Text-only quotations must match the specified page. Visual extractions require `--used-vision 1` and that page's image. Repeating an identical record is idempotent; changing the quote or value creates another evidence row, preserving earlier claims for adjudication.

The engine regenerates [the extraction matrix](1_workspace/extraction_matrix.md). Write interpretation, risk of bias, disagreements, limitations, and the narrative synthesis in [the report](1_workspace/synthesis_report.md). Generate its flow block with:

```text
python 2_skills/engine.py prisma
python 2_skills/engine.py checkpoint --message "Synthesis and PRISMA updated"
```

Do not edit content between `<!-- PRISMA:START -->` and `<!-- PRISMA:END -->`; it is regenerated. Counts represent distinct retrieved source records and included reports, not provider hit estimates or automatically linked studies. Link multiple reports of one study before claiming a distinct-study count. A generated chart alone is not full PRISMA 2020 compliance.

Workspace citations use clickable `[@BibKey]` links to the matching local PDF, plus the paper's verified DOI, arXiv, or PubMed link. The matrix generates these links. PDF links work locally after retrieval; they will not resolve on GitHub when the corresponding PDFs are excluded from the repository.

### Complete command reference

All commands use `python 2_skills/engine.py COMMAND`. Global and per-command `-h` / `--help` are available:

```text
python 2_skills/engine.py --help
python 2_skills/engine.py record-decision --help
```

There are **11 commands**. Every application-specific flag is listed below.

| Command | Required flags | Optional flags and defaults | Result |
|---|---|---|---|
| `init` | None | None | Creates missing folders/tables, initializes Git if needed, synchronizes bibliography. |
| `search` | `--query TEXT` | `--dbs openalex,arxiv,pubmed`; `--max-results 200`; `--since YYYY-MM-DD` | Retrieves metadata, deduplicates, updates BibTeX, and records per-database outcomes. `--since` is an inclusive publication-date filter; omit for unrestricted dates. |
| `rank` | None | `--picoc-text TEXT` | Scores all records. Normally reads Research Questions and PICOC from the protocol; the flag supplies an explicit query instead. |
| `fetch-batch` | `--phase screen` or `--phase extract` | `--limit N`, default/max 15 for screen or 3 for extract | Prints bounded JSON. Positive limits above the phase cap are rejected; a byte budget may reduce output further. |
| `record-decision` | `--bib-key KEY`; `--stage TITLE_ABSTRACT` or `FULL_TEXT`; `--devils-advocate TEXT`; `--quote TEXT`; `--decision INCLUDE`, `EXCLUDE`, or `MAYBE`; `--code ICn` or `ECn` | `--notes TEXT`, default empty | Validates source evidence, stores the current decision, and preserves a historical audit event. Codes must be defined in the protocol. |
| `ingest` | None | `--bib-key KEY` | Retrieves and parses all currently included records, or one specified existing key. |
| `record-extraction` | `--bib-key KEY`; `--variable TEXT`; `--quote TEXT`; `--page N`; `--value TEXT` | `--used-vision 0` or `1`, default `0` | Stores evidence for a final inclusion and regenerates the matrix. Page is a positive physical PDF page number. |
| `prisma` | None | None | Prints PRISMA counts and Mermaid flowchart; updates the generated report block. |
| `checkpoint` | `--message TEXT` | None | Commits workspace state and bibliography to local Git. |
| `update` | None | None | Replays searches, reranks, stages upstream skills for review when configured, and checkpoints. |
| `status` | None | None | Prints protocol status, paper/source counts, screening stages, PDF states, extraction totals, and latest checkpoint. |

Exit codes are `0` for success, `1` for handled execution errors, `2` for an incomplete operation or argument-parser error, and `130` for interruption. A capped search or unavailable PDF can return `2` while preserving successfully completed work. Inspect output before treating a command as complete.

### SQLite and evidence history

The database has exactly four application tables:

| Table | Stores |
|---|---|
| `papers` | Stable bibliography keys, bibliographic metadata, DOI/arXiv/PMID/OpenAlex identifiers, source memberships, retrieval status, and local paths. |
| `screening` | Current stage, score, decision, quotation, criterion code, exclusion argument, and notes for each paper. |
| `extractions` | Variable/value evidence rows with quotation, physical page, and visual-inspection assertion. |
| `audit_log` | Query provenance, historical screening decisions, ingestion events, ranking backend, update outcomes, and checkpoint information. |

SQLite's internal bookkeeping tables are not additional application tables. The current screening row changes as work progresses; audit events preserve prior decisions for PRISMA and reassessment. This is an application audit trail, not a tamper-proof external ledger. Source hashes detect PDFs changed since parsing and prevent recording against stale text.

### Backups and recovery

```text
python 2_skills/engine.py checkpoint --message "Review milestone"
git log --oneline -10
```

A checkpoint commits `1_workspace/` and `3_papers/references.bib`, subject to `.gitignore`. It closes SQLite before Git reads the database. It uses a local commit identity without changing your global Git identity. The checkpoint hash is stored in SQLite after committing, so that hash is included in the next snapshot.

| Included in normal workspace checkpoints | Excluded from those checkpoints |
|---|---|
| Protocol, SQLite state, matrix, report, and other nonignored workspace files; bibliography | `.env`, cookie jars, environments, runtimes, model caches, raw PDFs, parsed images/text, and changes to root configuration or `2_skills/` |

Root and skill code are versioned by ordinary Git commits. Checkpoints do not automatically run after every engine command and never push. The playbooks instruct the agent to checkpoint after completed batches and protocol changes.

To back up committed work remotely, run a normal push after confirming the remote and branch:

```text
git remote -v
git status --short
git push
```

Your clone normally tracks its source branch. GitHub authentication is handled by your Git installation. Keep a separate authorized backup of original PDFs and any derived assets you need; a local Git history cannot protect against losing the disk.

For recovery, preserve the current directory and restore an earlier commit into a separate clone or checkout. Restore its matching corpus backup before reviewing full-text evidence. Avoid resetting a dirty review directory. One process at a time may operate on the workspace; do not concurrently write the same SQLite file from multiple machines. For OneDrive or similar synchronization, work locally or pause synchronization during writes and sync closed checkpoints.

### Living reviews and upstream skill updates

```text
python 2_skills/engine.py update
python 2_skills/engine.py status
```

`update` reuses recorded query/database pairs and their limits, starting from the latest successful search's start date with inclusive overlap. Deduplication handles repeat hits. Capped and failed searches do not advance their success watermark. If there are recorded queries, the protocol must be usable for reranking. If none exist, the command can still check upstream skills and checkpoint.

The update checks the current Git branch's configured upstream. When available, it fetches that remote and stages `.py` and `.md` files from `2_skills/` under `1_workspace/skill_updates/<commit>/2_skills/`. Review diffs and validate changes before manually applying them. No staged code is executed or installed, and the review workspace is not replaced by a remote copy. A normal clone tracks its own remote branch; receiving changes from a different source repository requires an intentional Git upstream configuration.

There is **no built-in timer or scheduler**. Invoke `update` manually or have your wrapper invoke it. New results still need screening and extraction. Publication-date filtering can miss delayed indexing, so periodically rerun the original full queries and report remaining search limitations.

### Correct reasoning and resume safely

When a user identifies a reasoning flaw, follow [the calibration playbook](2_skills/05_reasoning_calibration.md): append a dated actionable rule under `## Active Reasoning Clarifications & Overrides` in the protocol, identify affected papers, reread their original evidence, re-record decisions through the CLI, regenerate PRISMA, update conclusions, and checkpoint. Distinguish a clarification from an amendment to the review protocol.

Do not infer missing evidence from silence, fabricate quotes, or treat downloaded paper text as agent instructions. Image-inspection assertions and required argument fields are guardrails; scientific correctness still needs reviewer oversight. A single agent's exclusion challenge is not an independent second reviewer.

### Validation and troubleshooting

See [validation_report.md](1_workspace/validation_report.md) for test coverage and execution instructions. Initial validation included 23 regression tests, small live metadata queries to all three providers, and synthetic PDF checks. It did not establish exhaustive search recall or validate institutional authentication, FastEmbed model inference, or an entire agent-driven review end to end.

With the installed environment active and Git on `PATH`, run the offline regression suite:

```text
python 1_workspace/validation/test_engine.py
```

The optional live check requires network access. The packaging command refreshes the source handoff snapshot:

```text
python 1_workspace/validation/live_connectors.py
python 1_workspace/validation/package_source.py
```

Validation uses ignored `case-*` and `live-*` fixture directories beneath `1_workspace/validation/`; it does not add test papers to the main review database.

| Symptom | Next step |
|---|---|
| `rank` requests completed RQs/PICOC | Fill those protocol sections or explicitly supply `--picoc-text`; keep the protocol authoritative for real review work. |
| FastEmbed is missing or model download fails | Install into the active interpreter, check network/model access, or explicitly select `SLR_RANK_BACKEND=tfidf`. |
| Search is capped or incomplete | Inspect provider totals/errors, raise the per-database cap when appropriate, or partition the query; document coverage. |
| Quote does not match | Copy exact source text and check physical page numbering. For image-only evidence, inspect the image and use the correct visual assertion. |
| `NEEDS_MANUAL_PDF` | Save the legitimate PDF at the reported key-specific path and rerun `ingest --bib-key`. |
| PDF changed since parsing | Reingest, repeat full-text eligibility, and adjudicate older extractions. |
| Full-text/extraction stage rejected | Record current title/abstract inclusion first, then full-text inclusion before extraction. |
| Git checkpoint fails | Confirm Git is available and inspect the repository and write permissions; do not discard review state to fix Git. |
| Update reports `no_upstream` | Configure the intended branch upstream if skill fetching is wanted; recorded literature searches can still run. |
| Local PDF links fail on GitHub | PDFs are deliberately kept outside normal commits; open the workspace locally with its corpus present. |
