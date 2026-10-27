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

The core packages are `requests`, `python-dotenv`, `PyMuPDF`, and `numpy`. Ranking requires FastEmbed or Ollama. SQLite is provided by Python.

### Clone and install

Clone the repository, then run the remaining commands from its root. Virtual environments stay under `1_workspace/` to retain the three application folders.

**Windows PowerShell**

```powershell
git clone https://github.com/xtobando/slr-system.git
Set-Location slr-system
python -m venv 1_workspace/.venv
Set-ExecutionPolicy -Scope Process -ExecutionPolicy RemoteSigned
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
Set-ExecutionPolicy -Scope Process -ExecutionPolicy RemoteSigned
.\1_workspace\.venv\Scripts\Activate.ps1
python -c "import sys; print(sys.executable)"
```

Confirm the execution-policy change if prompted. `-Scope Process` applies it only to the current PowerShell session; closing the terminal removes it. It allows locally created scripts such as the activation script to run. See Microsoft's [Set-ExecutionPolicy documentation](https://learn.microsoft.com/en-us/powershell/module/microsoft.powershell.security/set-executionpolicy).

The printed interpreter path should end in `1_workspace\.venv\Scripts\python.exe`. Launch OpenCode from this activated terminal so it inherits the environment. To leave the environment, run `deactivate`.

If you use **Command Prompt (`cmd.exe`)**, activate with:

```bat
1_workspace\.venv\Scripts\activate.bat
```

An organization's Group Policy can override this setting. If PowerShell still blocks the activation script, use the environment's interpreter directly:

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
| `SLR_RANK_BACKEND` | `fastembed` | Real embeddings: `fastembed` or `ollama`. Legacy `auto` means FastEmbed; TF-IDF is rejected. |
| `SLR_EMBEDDING_MODEL` | `BAAI/bge-small-en-v1.5` | FastEmbed model name. |
| `SLR_EMBEDDING_PYTHON` | Empty | Compatible interpreter; otherwise detects `.semantic-venv`. |
| `SLR_EMBEDDING_TIMEOUT` | `600` | Worker/API response timeout in seconds. |
| `SLR_SEMANTIC_THRESHOLD` | `0.5` | Fallback cosine cutoff; the search plan and CLI can set it explicitly. |
| `SLR_OLLAMA_URL` | `http://127.0.0.1:11434` | Ollama embedding API base URL. |
| `SLR_OLLAMA_MODEL` | `nomic-embed-text:v1.5` | Installed Ollama embedding model. |
| `SLR_HTTP_TIMEOUT` | `45` | HTTP read timeout in seconds; connection timeout is 10 seconds. |
| `SLR_MAX_PDF_MB` | `100` | Download-size limit in units of 1,024 × 1,024 bytes. |

Do not commit `.env`, credentials, or cookie jars. The supplied ignore rules exclude them. Institutional retrieval uses credentials you supply; it does not automate interactive login or guarantee access to every publisher. An HTML login page is rejected as a PDF.

### Real semantic embeddings and threshold screening

Paper selection now follows **precise title/abstract queries -> thousands of metadata records -> dense embedding cosine score -> threshold -> LLM reading -> PDF retrieval**. There is no TF-IDF or hybrid fallback.

The main interpreter can remain Python 3.15. FastEmbed can run in a separate compatible environment, automatically detected at `1_workspace/.semantic-venv/`. The following Windows commands require `uv`; if it is not already installed, run `python -m pip install uv` first:

```powershell
uv venv --python 3.12 1_workspace/.semantic-venv
uv pip install --python 1_workspace/.semantic-venv/Scripts/python.exe 'fastembed>=0.4,<1'
python 2_skills/engine.py rank --backend fastembed --threshold 0.5
```

Alternatively install FastEmbed into a supported active Python, or set `SLR_EMBEDDING_PYTHON` to that interpreter's path. Weights and content-addressed embedding caches stay under ignored `1_workspace/.models/`. Long inputs are token-chunked, weighted and normalized; only paper titles and abstracts are embedded. The audit records model weights hashes, runtime version, query hash, input hashes and run ID.

If you already have Python 3.12 and the Windows Python launcher, an alternative without `uv` is:

```powershell
py -3.12 -m venv 1_workspace/.semantic-venv
& ./1_workspace/.semantic-venv/Scripts/python.exe -m pip install 'fastembed>=0.4,<1'
```

Ollama is an alternative embedding service; no generative chat calls are made:

```powershell
ollama pull nomic-embed-text:v1.5
python 2_skills/engine.py rank --backend ollama --model nomic-embed-text:v1.5 --threshold 0.5
```

Start `ollama serve` if it is not already running. `SLR_OLLAMA_URL` defaults to `http://127.0.0.1:11434`. Ollama model digests are recorded, long inputs are chunked and `truncate=false` prevents silent context truncation. Backend failures stop ranking; previous completed scores remain intact.

The default cutoff is recorded in `1_workspace/search_strings.txt`. Change it without recomputing embeddings:

```powershell
python 2_skills/engine.py screen-semantic --threshold 0.6
```

A CLI-selected cutoff is retained for the next ranking with the same model identity, semantic query and plan. Editing the plan or changing models returns to the new plan default unless you pass an explicit cutoff. Scores are raw cosine similarities in [-1, 1], not probabilities. The initial 0.5 cutoff is configurable and model-dependent. Review recall and workload before treating any value as appropriate. PASS records reach the LLM; BELOW_THRESHOLD records stay outside its reading queue. MISSING_ABSTRACT remains a metadata queue, not an eligibility exclusion. OUTSIDE_SEARCH retains historical records that were not returned by the current precise queries; they cannot enter this funnel even with an old high score. Existing eligibility decisions and evidence are retained separately. Changed metadata or search plans require reranking.

The current selection is exported to `1_workspace/semantic_ranking.csv` and `semantic_screening.md`. The report compares passing counts at several thresholds so you can choose a cutoff before the LLM reads records. See [Ollama embeddings](https://docs.ollama.com/api/embed) and [OpenAlex title/abstract search](https://help.openalex.org/api/searching/).

### Connect an agent wrapper

Launch your configured wrapper from the repository root after activating the environment. For OpenCode, the project's requested invocation is:

```text
opencode --model openai/gpt-6.1-sol
```

The wrapper and provider must actually expose that model identifier; this project does not install OpenCode, authenticate an account, or establish model availability. Verify those steps in the wrapper's documentation. Other wrappers can use the same files and CLI if they can follow [AGENTS.md](AGENTS.md), read local files, execute commands, and inspect PNGs.

The included [opencode.json](opencode.json) configures `./2_skills` as a native skill source and permits loading the PDF skill using OpenCode 2 permissions. Start OpenCode from `slr-system/` so the relative source resolves correctly, and restart existing sessions after configuration changes. Native discovery was verified with OpenCode 2.1.4. The registry loads asynchronously: a single `api --standalone skill.list` call can return before loading finishes. Use `python 1_workspace/validation/check_opencode_skills.py` for a check that waits for registration without invoking a model. [AGENTS.md](AGENTS.md) also provides a direct-file fallback. See the [OpenCode 2 skill-source configuration](https://opencode.ai/v2/docs/skills).

Begin a review session with a prompt such as:

> Read AGENTS.md and 1_workspace/protocol.md, then run the status command. Help me complete the protocol before searching. Follow the numbered playbooks, record evidence through engine.py, inspect relevant visual assets, and checkpoint each completed batch.

The project sets a 272,000-token context ceiling and recommends a fresh context before 200,000 tokens. These are workflow limits, not verified model capacities. Use the lower limit supported by your wrapper/model. Batch limits cannot measure the wrapper's total text and image context.

## 2. Usage guide

### What the system can do

- Search **OpenAlex, arXiv, and PubMed**, recording the executed queries, source memberships, and completion status.
- Deduplicate bibliographic records, keep stable citation keys, and synchronize a master BibTeX file.
- Collect thousands of title/abstract records and prefilter with genuine semantic embeddings and a chosen cosine threshold before LLM reading.
- Persist title/abstract and full-text decisions with quotations, eligibility codes, and an argument against inclusion.
- Retrieve available PDFs or accept manually supplied files, extract page-marked text, and render every page as a 200-DPI PNG.
- Convert a local PDF independently of a review into Markdown with full-page images and figure/formula candidate crops, using the optional PDF-to-Markdown skill.
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
├── opencode.json
├── 1_workspace/
│   ├── protocol.md
│   ├── slr_state.sqlite
│   ├── extraction_matrix.md
│   ├── synthesis_report.md
│   ├── validation_report.md
│   ├── system_source.md
│   └── validation/
│       ├── test_engine.py
│       ├── test_pdf_conversion.py
│       ├── live_connectors.py
│       └── package_source.py
├── 2_skills/
│   ├── 01_protocol_and_search.md
│   ├── 02_semantic_rank_screen.md
│   ├── 03_multimodal_extract.md
│   ├── 04_synthesis_and_bibtex.md
│   ├── 05_reasoning_calibration.md
│   ├── pdf-to-markdown/
│   │   ├── SKILL.md
│   │   └── agents/
│   │       └── openai.yaml
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
| [opencode.json](opencode.json) | Configures `2_skills/` as a native OpenCode skill source and permits loading the PDF skill; verify discovery in your installation. |
| [search_strings.txt](1_workspace/search_strings.txt) | Exact executable title/abstract search strings, dates, semantic query, and cutoff. |
| `1_workspace/search_runs/` | Immutable per-run text snapshots of exact queries and collection outcomes. |
| `1_workspace/semantic_ranking.csv` | Full metadata ranking and PASS/BELOW_THRESHOLD/MISSING_ABSTRACT/PENDING/OUTSIDE_SEARCH states. |
| `1_workspace/semantic_screening.md` | Current model/run/threshold and prefilter counts. |
| [protocol.md](1_workspace/protocol.md) | Edit research questions, PICOC, searches, eligibility, extraction variables, synthesis plan, and dated corrections. |
| `1_workspace/slr_state.sqlite` | Persistent database. Use engine commands for changes; inspect a closed copy for ad hoc analysis. |
| [extraction_matrix.md](1_workspace/extraction_matrix.md) | Generated evidence table; record evidence through the CLI rather than editing this file. |
| [synthesis_report.md](1_workspace/synthesis_report.md) | Write the narrative here, outside the generated PRISMA markers. |
| [validation_report.md](1_workspace/validation_report.md) | Validation scope, test instructions, and deployment-specific limits. |
| [system_source.md](1_workspace/system_source.md) | Generated source handoff snapshot. Edit actual project files and regenerate when needed. |
| [validation/test_engine.py](1_workspace/validation/test_engine.py) | Run the reproducible behavioral regression suite in isolated fixture workspaces. |
| [validation/test_semantic_pipeline.py](1_workspace/validation/test_semantic_pipeline.py) | Test real-vector handling, threshold gating, plan provenance, migrations and missing metadata using controlled fixtures. |
| [validation/live_semantic.py](1_workspace/validation/live_semantic.py) | Run a real model acceptance example with Unicode text and record the weights identity. |
| [validation/test_pdf_conversion.py](1_workspace/validation/test_pdf_conversion.py) | Test standalone PDF conversion using synthetic PDFs in isolated directories. |
| [validation/live_connectors.py](1_workspace/validation/live_connectors.py) | Optional network smoke check against all three databases using isolated fixtures. |
| [validation/package_source.py](1_workspace/validation/package_source.py) | Regenerates `system_source.md` from the current source files. |
| [01_protocol_and_search.md](2_skills/01_protocol_and_search.md) | Protocol formulation, query translation, search provenance, and completeness checks. |
| [02_semantic_rank_screen.md](2_skills/02_semantic_rank_screen.md) | Reading priority, quote-first screening, and the exclusion challenge. |
| [03_multimodal_extract.md](2_skills/03_multimodal_extract.md) | Retrieval, full-text reading, visual inspection, and evidence extraction. |
| [04_synthesis_and_bibtex.md](2_skills/04_synthesis_and_bibtex.md) | Traceable synthesis, reporting, citations, and PRISMA interpretation. |
| [05_reasoning_calibration.md](2_skills/05_reasoning_calibration.md) | Permanent corrections and reassessment of affected papers. |
| [pdf-to-markdown/SKILL.md](2_skills/pdf-to-markdown/SKILL.md) | Optional local document-conversion skill, separate from the five review stages. |
| [engine.py](2_skills/engine.py) | Unified deterministic CLI described below. |
| [SLRBlueprint.tex](1_workspace/SLRBlueprint.tex) | LaTeX manuscript structure; keep search-process limitations in methodology and distinguish them from primary-literature limitations. |
| [check_opencode_skills.py](1_workspace/validation/check_opencode_skills.py) | Waits for native PDF skill registration without invoking a model. |
| [prepare_publication.py](1_workspace/validation/prepare_publication.py) | Builds a source-only release in a separate clean upstream clone. |
| [references.bib](3_papers/references.bib) | Generated bibliography; avoid manual edits because synchronization replaces it. |
| `3_papers/raw_pdfs/` | Store original PDFs as `<bib_key>.pdf`, using keys already assigned by the database. |
| `3_papers/parsed_cache/` | Generated per-paper `fulltext.md` and `page_N_visual.png` files. |

Generated local directories also include `.venv/`, `.models/`, and `skill_updates/` beneath `1_workspace/`. Keep the three top-level application folders when extending the project.

### Workflow and review states

```mermaid
flowchart TD
    A[Complete protocol] --> B[Search and deduplicate]
    B --> C[Rank reading priority]
    C --> T[Apply semantic cosine threshold]
    T --> D[LLM reads passing titles and abstracts]
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

### Configure the review and choose an embedding model

1. Edit [protocol.md](1_workspace/protocol.md) to define the research questions, PICOC, eligibility rules and review limits. Edit [search_strings.txt](1_workspace/search_strings.txt) to set the provider-specific queries, date ranges, `semantic_query` and starting `semantic_threshold`. Review the checked-in topic and replace it when starting a different review. A source-only publication uses an executable question-answering example rather than the owner's live review plan; neither an example query nor a default cutoff establishes validated recall.
2. Edit the local `.env` to choose the backend and model. For example, for FastEmbed:

   ```dotenv
   SLR_RANK_BACKEND=fastembed
   SLR_EMBEDDING_MODEL=BAAI/bge-small-en-v1.5
   SLR_EMBEDDING_PYTHON=
   ```

   An empty interpreter setting uses `1_workspace/.semantic-venv` when present, otherwise the interpreter running the engine. Use an **absolute path** for `SLR_EMBEDDING_PYTHON` if you select a different environment. CLI options `--backend` and `--model` override the environment for that ranking; existing process environment variables override values in `.env`.
3. Choose a model supported by the installed backend. `BAAI/bge-small-en-v1.5` is the current default, has 384 dimensions and was tested locally; it is an English model. The installed FastEmbed catalog also lists `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2` for multilingual text. That alternative has not been validated on this review: test it against representative English and Spanish records before relying on its ranking. Models in the catalog differ in architecture, size, input limits and instruction prefixes; this engine's FastEmbed worker requires a tokenizer and ONNX model files. See [FastEmbed's supported models](https://qdrant.github.io/fastembed/examples/Supported_Models/).

   List the catalog from the isolated environment without downloading every model:

   ```powershell
   @'
   from fastembed import TextEmbedding
   for model in TextEmbedding.list_supported_models():
       print(model['model'], model['description'])
   '@ | & ./1_workspace/.semantic-venv/Scripts/python.exe -
   ```

4. To use Ollama instead, install and start Ollama, pull an **embedding** model, and configure its separate settings:

   ```powershell
   ollama pull nomic-embed-text:v1.5
   ```

   ```dotenv
   SLR_RANK_BACKEND=ollama
   SLR_OLLAMA_MODEL=nomic-embed-text:v1.5
   SLR_OLLAMA_URL=http://127.0.0.1:11434
   ```

   `SLR_EMBEDDING_MODEL` applies to FastEmbed; `SLR_OLLAMA_MODEL` applies to Ollama. The local service must expose `/api/tags` and `/api/embed`; the configured model must already be pulled. The engine adds the Nomic search-query/document prefixes for `nomic-embed-text`. Other Ollama models may require different prefixes or context limits; consult their model instructions before using them. Ollama support is covered by mocked API tests but has not been tested against a live Ollama service in this project.
5. Check the selected backend with `python 1_workspace/validation/live_semantic.py --backend fastembed`, or replace `fastembed` with `ollama`. Add `--model NAME` to test another model without changing `.env`. This downloads model files on first use if needed, caches them locally, and runs a small embedding example without changing review decisions. It checks that the model operates; it does not validate your cutoff or measure review recall.

After changing the model or backend, run `rank` again before using its results. Cosine values and useful cutoffs differ by model, query and corpus; do not transfer `0.5` or any other cutoff as a validated relevance probability. Compare the counts in `semantic_screening.md` and assess the selection against known relevant studies. A normal `rank` uses the configured model; for one run, for example:

```powershell
python 2_skills/engine.py rank --backend fastembed --model BAAI/bge-small-en-v1.5 --threshold 0.5
```

`--threshold` has highest priority. Otherwise the engine reuses a previously selected threshold for the same plan, semantic query and embedding identity; if none matches, it reads `semantic_threshold` from the plan, then `SLR_SEMANTIC_THRESHOLD`, then `0.5`. `screen-semantic --threshold VALUE` immediately reuses existing scores. Editing the plan, including its default threshold, changes its hash and requires `rank` again.

### Search, rank, and prefilter before LLM reading

Edit [search_strings.txt](1_workspace/search_strings.txt), an executable UTF-8 INI document containing exact Boolean queries for each provider, dates, a 5,000-record-per-query limit, the semantic query and default cutoff. Each query family needs a translation for the selected databases. Providers have different syntax; recorded translations do not establish identical recall.

```powershell
python 2_skills/engine.py search-plan
python 2_skills/engine.py rank --backend fastembed --threshold 0.5
python 2_skills/engine.py fetch-batch --phase screen --limit 15
```

To collect from selected providers use `search-plan --dbs openalex,arxiv`; override each query's limit with `--max-results 10000`. No PDFs are retrieved and no abstracts are sent to a generative LLM during collection or ranking. The engine itself returns only passing metadata when the agent subsequently requests a batch.

`search-plan --file 1_workspace/another-plan.txt` selects an alternative active plan, which the engine records and reuses for ranking, provenance checks and `update`, including after a restart. Keep it available in the workspace; restore it or select another plan if it is moved. An absolute plan path outside the project is recorded as an absolute path and is not portable. A standalone `search --query` adds records, but they only become eligible for the semantic funnel if the exact provider/query and date scope match the active plan. When splitting one provider/query into date partitions, use non-overlapping inclusive ranges, such as 2015-01-01–2019-12-31 and 2020-01-01–2026-12-31.

Every query execution is saved in `1_workspace/search_runs/<run_id>.txt` and the audit table, including its exact string, dates, scope, retrieved/new/skipped counts and completion status. Missing-title records are skipped and logged without aborting the remaining collection; a run with skips remains explicitly incomplete.

OpenAlex uses `search.title_and_abstract` and 100-record pages. Without a key it uses basic paging, limited to the first 10,000 results; a key enables cursor paging. PubMed's existing 9,999-result window still requires date-partitioned query sections for larger sets. arXiv queries must use `ti:`/`abs:` and PubMed queries `[Title/Abstract]` or `[tiab]`. Full-text searching is not part of this metadata funnel. Thousands of records or a capped query must never be called exhaustive.

Inspect `semantic_screening.md` and the ranking CSV before proceeding. Only PASS rows with current metadata hashes can enter an LLM batch, receive new review decisions, or proceed to PDF ingestion. Historical decisions are retained rather than rewritten by the threshold.

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

`ingest` processes currently included papers that also pass the current semantic threshold. To process a specific existing record:

```powershell
$bibKey = Read-Host "bib_key to ingest"
python 2_skills/engine.py ingest --bib-key "$bibKey"
```

Retrieval tries the existing local PDF, available OA locations, configured Unpaywall, and an optional institutional URL. Failures are reported as `NEEDS_MANUAL_PDF` with a source link and target path. Obtain the PDF through your permitted access, save it at the displayed path, and rerun ingestion. `PARSE_ERROR` means the source needs inspection; failed retrieval is not an exclusion decision.

Each ingested paper contains physical page markers `<!-- PAGE N -->` and `[VISUAL_ASSET: ...]` links. Every page is rendered at 200 DPI, including scanned pages and pages without detected figures. The review's `ingest` command uses full-page visual references and does not create separate figure crops or OCR scanned pages. Read relevant sections sequentially and open the referenced PNGs with the wrapper's image tool. Inspect equations, captions, axes, units, and footnotes. The original PDF remains authoritative. For a separate Markdown conversion with crops, use the optional utility below.

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

### Convert a standalone PDF to Markdown

The optional [PDF-to-Markdown skill](2_skills/pdf-to-markdown/SKILL.md) converts a local PDF without a review protocol or database record. It uses the existing PyMuPDF dependency and leaves the source PDF, SQLite database, bibliography, and review decisions unchanged. You do not need to run `init`, `search`, or `ingest` first.

The model can select this skill itself when your request needs reusable PDF text or visual evidence. In OpenCode, simply ask:

> Read my proposal PDF and summarize its methodology, equations, and diagrams.

Or ask for the artifact directly:

> Make a Markdown version of this PDF, keeping its formulas and pictures.

The agent should load the skill, run the converter when useful, inspect the images, and continue your task. The skill description guides selection; merely mentioning a PDF or requesting citation metadata does not require conversion. `metadata.opencode/autoinvoke` is enabled, and `agents/openai.yaml` also permits implicit invocation for compatible hosts that register this directory. If native discovery fails, the instruction in `AGENTS.md` directs the agent to read the skill file directly.

To check native discovery on OpenCode 2 without invoking a model, run:

```powershell
python 1_workspace/validation/check_opencode_skills.py
```

The check starts an authenticated temporary server bound to localhost, waits for `pdf-to-markdown`, then stops the server. Its OpenCode runtime and configuration use temporary directories. Add `--opencode 'C:/path/to/opencode.exe'` if the executable is not on PATH. It checks registration, not whether a model will select the skill for every request. A one-shot `opencode api --standalone skill.list` is not a reliable diagnostic because it may race asynchronous loading. The agent can still follow `AGENTS.md` directly in wrappers without native skill discovery.

For direct terminal use, the underlying command remains available:

```powershell
$pdfPath = Read-Host "Local PDF path, absolute or relative to the project root"
python 2_skills/engine.py convert-pdf --pdf "$pdfPath"
```

The default destination is `3_papers/parsed_cache/documents/<slug>-<hash12>-<dpi>dpi/`, derived from the filename, source hash, and rendering resolution. The default resolution is **300 DPI**. To choose a different destination or resolution:

```powershell
$pdfPath = Read-Host "Local PDF path"
$outputDir = Read-Host "New output directory under 1_workspace/ or 3_papers/parsed_cache/"
python 2_skills/engine.py convert-pdf --pdf "$pdfPath" --output-dir "$outputDir" --dpi 300
```

Input and output paths are resolved relative to the project root, even when the command is launched elsewhere. Absolute input paths are allowed. Output must stay under `1_workspace/` or `3_papers/parsed_cache/`, and the destination must not already exist. Use a new destination to rerun a conversion; existing artifacts are never overwritten. Output in the default parsed cache is ignored by Git. Files placed under `1_workspace/` may be included in later workspace checkpoints, so choose deliberately for private documents.

| Output | Purpose |
|---|---|
| `fulltext.md` | Extracted text as basic paragraph Markdown, with relative image embeds and physical page references. |
| `page_N_visual.png` | Full-page visual reference for every page, retained alongside crops. |
| Crop PNGs | Heuristically detected embedded images, vector graphics, and formula candidates, plus requested manual regions. |
| `assets.json` | Source SHA-256 and asset metadata, including page numbers and bounding boxes. |

Keep the folder together so relative image links work. Crop detection may miss or truncate content; inspect relevant crops against the full-page images. Every page remains available even when automatic detection misses an equation or diagram. Scanned PDFs retain page images but may yield little text: the utility does not perform OCR, reconstruct exact layout or tables, or automatically generate LaTeX.

For a missed or incomplete crop, inspect the original page and supply an explicit rectangle in a fresh output directory:

```powershell
$pdfPath = Read-Host "Local PDF path"
$outputDir = Read-Host "New conversion output directory"
$page = Read-Host "One-based physical PDF page number"
$x0 = Read-Host "Left coordinate in unrotated PDF points"
$y0 = Read-Host "Top coordinate in unrotated PDF points"
$x1 = Read-Host "Right coordinate in unrotated PDF points"
$y1 = Read-Host "Bottom coordinate in unrotated PDF points"
python 2_skills/engine.py convert-pdf --pdf "$pdfPath" --output-dir "$outputDir" --crop "$page" "$x0" "$y0" "$x1" "$y1"
```

Repeat `--crop PAGE X0 Y0 X1 Y1` for multiple regions. Coordinates use the unrotated PyMuPDF page coordinate system: 72 points per inch, origin at the top left, x increases rightward, and y increases downward. Manually requested crops supplement the full-page images. DPI must be between 72 and 600; renderings above 80 million pixels per page are rejected, so reduce DPI if necessary.

Formulas are preserved as images. If you also need editable math, the agent can add verified `$...$` or `$$...$$` only after inspecting the visual. Prefer a companion `annotated.md`, keep the original image reference, and preserve the generated `fulltext.md`. Unclear symbols stay unresolved. Conversion alone does not establish paper eligibility or create extracted evidence; use the normal review commands for that work.

### Complete command reference

All commands use `python 2_skills/engine.py COMMAND`. Global and per-command `-h` / `--help` are available:

```text
python 2_skills/engine.py --help
python 2_skills/engine.py record-decision --help
```

There are **14 commands**. Every application-specific flag is listed below.

| Command | Required flags | Optional flags and defaults | Result |
|---|---|---|---|
| `init` | None | None | Creates missing folders/tables, initializes Git if needed, synchronizes bibliography. |
| `search` | `--query TEXT` | `--dbs openalex,arxiv,pubmed`; `--max-results 5000`; `--since YYYY-MM-DD`; `--until YYYY-MM-DD` | Searches title/abstract fields, deduplicates, records skipped metadata and saves an exact-query text snapshot. |
| `search-plan` | None | `--file 1_workspace/search_strings.txt`; `--dbs openalex,arxiv,pubmed`; `--max-results N` | Executes precise provider-specific queries and date bounds from the explicit plan. |
| `rank` | None | `--picoc-text TEXT`; `--backend fastembed` or `ollama`; `--model NAME`; `--threshold VALUE` | Computes genuine title/abstract embedding cosine scores and applies the threshold. Query/cutoff normally come from search_strings.txt; protocol is a query fallback. |
| `screen-semantic` | `--threshold VALUE` | None | Reapplies the threshold to a completed semantic run without recomputing embeddings. |
| `fetch-batch` | `--phase screen` or `--phase extract` | `--limit N`, default/max 15 for screen or 3 for extract | Prints bounded JSON. Positive limits above the phase cap are rejected; a byte budget may reduce output further. |
| `record-decision` | `--bib-key KEY`; `--stage TITLE_ABSTRACT` or `FULL_TEXT`; `--devils-advocate TEXT`; `--quote TEXT`; `--decision INCLUDE`, `EXCLUDE`, or `MAYBE`; `--code ICn` or `ECn` | `--notes TEXT`, default empty | Validates source evidence, stores the current decision, and preserves a historical audit event. Codes must be defined in the protocol. |
| `ingest` | None | `--bib-key KEY` | Retrieves and parses all currently included records, or one specified existing key. |
| `convert-pdf` | `--pdf PATH` | `--output-dir DIR`; `--dpi 300` (72–600); repeatable `--crop PAGE X0 Y0 X1 Y1` | Converts a local PDF to Markdown and visual assets in a new directory. Output is restricted to `1_workspace/` or `3_papers/parsed_cache/`; no database or bibliography changes. |
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
| `screening` | Current review stage and evidence, plus cosine score, semantic status, ranking run ID and metadata hash. Schema migration preserves existing rows and the four-table architecture. |
| `extractions` | Variable/value evidence rows with quotation, physical page, and visual-inspection assertion. |
| `audit_log` | Query provenance, historical screening decisions, ingestion events, ranking backend, update outcomes, and checkpoint information. |

SQLite's internal bookkeeping tables are not additional application tables. The current screening row changes as work progresses; audit events preserve prior decisions for PRISMA and reassessment. This is an application audit trail, not a tamper-proof external ledger. Source hashes detect PDFs changed since parsing and prevent recording against stale text.

### Backups and recovery

The semantic-workflow migration keeps a local SQLite backup under ignored `1_workspace/.backups/`. Embedding runtimes, their caches and model weights stay local.

```text
python 2_skills/engine.py checkpoint --message "Review milestone"
git log --oneline -10
```

A checkpoint commits `1_workspace/` and `3_papers/references.bib`, subject to `.gitignore`. It closes SQLite before Git reads the database. It uses a local commit identity without changing your global Git identity. The checkpoint hash is stored in SQLite after committing, so that hash is included in the next snapshot.

| Included in normal workspace checkpoints | Excluded from those checkpoints |
|---|---|
| Protocol, SQLite state, matrix, report, and other nonignored workspace files; bibliography | `.env`, cookie jars, environments, runtimes, model caches, raw PDFs, parsed images/text, and changes to root configuration or `2_skills/` |

Root and skill code are versioned by ordinary Git commits. Checkpoints do not automatically run after every engine command and never push. The playbooks instruct the agent to checkpoint after completed batches and protocol changes.

Review checkpoints can contain protocol details, quotations, a bibliography and SQLite state. Keep that history in a private backup destination if the review data is not intended for publication. `.gitignore` excludes new standalone PDFs, conversion artifacts and tools, but does not remove files already tracked or present in earlier commits.

### Publish the system source separately from review data

Prepare a fresh clone beneath the ignored `1_workspace/.publication/` directory. This starts from the current public history and preserves upstream changes, including [SLRBlueprint.tex](1_workspace/SLRBlueprint.tex), without merging private review checkpoints. The following commands run from the working project root:

```powershell
git clone --no-tags --single-branch --branch main https://github.com/xtobando/slr-system.git 1_workspace/.publication/slr-system
python 1_workspace/validation/prepare_publication.py --destination 1_workspace/.publication/slr-system
git -C 1_workspace/.publication/slr-system switch -c publication/semantic-review
git -C 1_workspace/.publication/slr-system diff --stat
```

Use an unused clone path if the example destination already exists. The preparation command requires a clean clone at its fetched `origin/main`; it refuses an upstream database or bibliography containing review records. It copies an explicit source allowlist, preserves empty upstream protocol/report/matrix templates, writes an executable example search plan, and rebuilds the source bundle from those public files. It does not copy the live SQLite database, review outputs, signed proposal, PDF assets, model weights, executable tools, `.env`, or the working repository's local commits.

After reviewing that prepared tree, run its tests with the working environment and commit there. For example, from the original project root:

```powershell
python -m unittest discover -s 1_workspace/.publication/slr-system/1_workspace/validation -p 'test_*.py' -v
git -C 1_workspace/.publication/slr-system add --all
git -C 1_workspace/.publication/slr-system commit -m "Add real semantic screening and configurable workflow"
```

To publish the reviewed source branch, push from that separate clone and open a pull request:

```text
git -C 1_workspace/.publication/slr-system push -u origin HEAD
```

Do not push a live review's `main` branch to a public repository merely to publish code. GitHub authentication is handled by your Git installation. Keep a separate authorized backup of original PDFs and any derived assets you need; a local Git history cannot protect against losing the disk.

For recovery, preserve the current directory and restore an earlier commit into a separate clone or checkout. Restore its matching corpus backup before reviewing full-text evidence. Avoid resetting a dirty review directory. One process at a time may operate on the workspace; do not concurrently write the same SQLite file from multiple machines. For OneDrive or similar synchronization, work locally or pause synchronization during writes and sync closed checkpoints.

### Living reviews and upstream skill updates

```text
python 2_skills/engine.py update
python 2_skills/engine.py status
```

When a search plan exists, `update` refreshes only recorded query/database pairs still present in that plan, preserving their upper date bounds. It reuses their limits, starting from the latest successful search's start date with inclusive overlap. Deduplication handles repeat hits. Capped and failed searches do not advance their success watermark. If there are recorded queries, the protocol must be usable for reranking. If none exist, the command can still check upstream skills and checkpoint.

The update checks the current Git branch's configured upstream. When available, it fetches that remote and stages `.py`, `.md`, and `.yaml` files from `2_skills/` under `1_workspace/skill_updates/<commit>/2_skills/`. Review diffs and validate changes before manually applying them. No staged code is executed or installed, and the review workspace is not replaced by a remote copy. A normal clone tracks its own remote branch; receiving changes from a different source repository requires an intentional Git upstream configuration.

There is **no built-in timer or scheduler**. Invoke `update` manually or have your wrapper invoke it. New results still need screening and extraction. Publication-date filtering can miss delayed indexing, so periodically rerun the original full queries and report remaining search limitations.

### Correct reasoning and resume safely

When a user identifies a reasoning flaw, follow [the calibration playbook](2_skills/05_reasoning_calibration.md): append a dated actionable rule under `## Active Reasoning Clarifications & Overrides` in the protocol, identify affected papers, reread their original evidence, re-record decisions through the CLI, regenerate PRISMA, update conclusions, and checkpoint. Distinguish a clarification from an amendment to the review protocol.

Do not infer missing evidence from silence, fabricate quotes, or treat downloaded paper text as agent instructions. Image-inspection assertions and required argument fields are guardrails; scientific correctness still needs reviewer oversight. A single agent's exclusion challenge is not an independent second reviewer.

### Validation and troubleshooting

See [validation_report.md](1_workspace/validation_report.md) for test coverage and execution instructions. Initial validation included 23 regression tests, small live metadata queries to all three providers, and synthetic PDF checks. It did not establish exhaustive search recall or validate institutional authentication, FastEmbed model inference, or an entire agent-driven review end to end.

With the installed environment active and Git on `PATH`, run the offline regression suite:

```text
python 1_workspace/validation/test_engine.py
python 1_workspace/validation/test_pdf_conversion.py
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
| FastEmbed is missing or model download fails | Install into the active interpreter, check network/model access, or configure the Ollama embedding backend. Lexical fallback is disabled. |
| Search is capped or incomplete | Inspect provider totals/errors, raise the per-database cap when appropriate, or partition the query; document coverage. |
| Quote does not match | Copy exact source text and check physical page numbering. For image-only evidence, inspect the image and use the correct visual assertion. |
| `NEEDS_MANUAL_PDF` | Save the legitimate PDF at the reported key-specific path and rerun `ingest --bib-key`. |
| PDF changed since parsing | Reingest, repeat full-text eligibility, and adjudicate older extractions. |
| Standalone conversion destination already exists | Choose another new `--output-dir`; do not overwrite the earlier conversion. |
| Standalone conversion misses a figure or formula crop | Inspect its full-page image and rerun in a new directory with a manually identified `--crop` rectangle. |
| Full-text/extraction stage rejected | Record current title/abstract inclusion first, then full-text inclusion before extraction. |
| Git checkpoint fails | Confirm Git is available and inspect the repository and write permissions; do not discard review state to fix Git. |
| Update reports `no_upstream` | Configure the intended branch upstream if skill fetching is wanted; recorded literature searches can still run. |
| Local PDF links fail on GitHub | PDFs are deliberately kept outside normal commits; open the workspace locally with its corpus present. |
