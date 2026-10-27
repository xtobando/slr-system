# Implementation validation

Original baseline validated on 2026-10-20 with Python 3.12.10 on Windows.

The original delivered review database contained zero papers and zero decisions/extractions.
The reproducible validation scripts are published under `1_workspace/validation/`.
Fixture records and live smoke-test metadata are isolated in ignored `case-*` and
`live-*` subdirectories; earlier local-only runs used `1_workspace/.tests/`.

## Automated checks

23 regression tests passed. They cover the exact four application tables and
foreign keys, normalized identifiers, cross-database deduplication, repeated-source
counting, title collisions, bibliography synchronization, quote validation, stage
gating, 200-DPI visual rendering including blank pages, page-grounded extraction,
idempotent evidence insertion, visual-asset requirements, changed/corrupt PDF
invalidation, PRISMA history and narrative preservation, manual PDF handling,
deterministic ranking, hard batch caps, all three metadata parsers, capped/failed
search persistence, PDF/HTML download validation, interrupted search recovery,
Git snapshots, unrelated staged-file preservation, living-search watermarks,
upstream staging without replacement, and concurrent-process locking.

After installing requirements in the active virtual environment and making Git
available on PATH, run the regression suite from the project root:

```powershell
python 1_workspace/validation/test_engine.py
```

The suite uses temporary fixture repositories inside `validation`, validates their
resolved paths before cleanup, and never changes the main review database.

## Standalone PDF conversion

Validated on 2026-10-20 with Python 3.15.0 and PyMuPDF 1.28.2 on Windows.
All 23 existing engine regression tests and 13 new conversion tests passed.

```powershell
python 1_workspace/validation/test_pdf_conversion.py
```

Synthetic fixtures cover text, formula candidates, raster images, vector diagrams,
blank and scanned pages, rotated pages with a shifted CropBox, actual crop content,
relative Markdown links, source hashes, literal Markdown/HTML text, invalid and
encrypted PDFs, DPI and pixel limits, refusal to overwrite an existing directory,
cleanup after a failed render, and conversion without opening the review database.
The CLI reports rendering failures without leaving a completed export. A visual
check confirmed the sample equation, labeled diagram, and image crops.

The skill's frontmatter, local links, and CLI documentation were checked. The
optional skill-creator validator needs PyYAML, which is not a project dependency;
dependency-free structure checks were used instead.

These checks do not establish OCR or automatic LaTeX accuracy: the converter
performs neither. Crops are heuristic, every page retains a rendered PNG, and the
original PDF remains authoritative. No personal proposal or review data was used
as a fixture.

## Live checks

One small unauthenticated public query succeeded against each of OpenAlex, arXiv,
and PubMed. Titles, identifiers, and provider result totals were parsed successfully.
These smoke checks establish connectivity and response compatibility at validation
time; they do not establish exhaustive query recall or future service availability.
Synthetic local PDFs exercised parsing and download validation separately.

## Remaining deployment-specific checks

During the original baseline validation FastEmbed was not installed and the
then-current ranking backend was TF-IDF. The current implementation requires a
real embedding backend; its later FastEmbed validation is recorded below. Neural
weights require a first-use download.
Institutional proxy login, domain-specific cookies, Unpaywall credentials, and
account-specific API keys require the review owner's configuration. The image
inspection playbook requires an image-capable wrapper tool; Python does not attest
that an LLM actually inspected an image. OpenCode is not installed by this project.

The original development workspace's `.runtime` directory contains a portable
Python interpreter, declared core dependencies, and official MinGit for that
machine. This runtime and the old `.tests` directory are ignored by Git and are not
included in GitHub clones. Use README.md's virtual-environment setup after cloning.

The source bundle `system_source.md` contains every requested source file in full
and in the requested sequence, plus the bibliography and quickstart. SQLite is a
generated binary initialized by the engine, not a text source file.


## Real semantic prefilter ? 2026-10-27

50 offline behavioral tests passed (23 engine, 13 PDF, 14 semantic pipeline).
Tests cover title/abstract-only query scope, exact search-plan execution, >1,000
fixture records, malformed metadata skips, four-table legacy migration, actual
cosine threshold boundaries, no lexical fallback, missing abstracts, stale
metadata, old records outside current queries, LLM/PDF access gates, failure
atomicity, invalid vectors, model-specific caches, and the Ollama embedding API.

The main Python 3.15 environment uses a separate Python 3.12.15 embedding worker
with FastEmbed 0.9.1 and ONNX Runtime 1.31.1. Real BAAI/bge-small-en-v1.5 weights
were downloaded and tested: 384-dimensional embeddings gave cosine 0.82928 for
an EMG-prosthesis example and 0.48312 for an unrelated ocean example. Unicode
survived the Windows worker roundtrip. These examples verify operation, not
systematic-review recall or the scientific validity of a 0.5 cutoff.

The three precise OpenAlex query families in search_strings.txt were executed
with title/abstract scope and 2015?2026 date bounds. They fetched 2,868, 718 and
1,255 records. Two records lacked titles and were logged/skipped; those two
runs remain incomplete. The local corpus grew from 794 to 5,220 unique records.
No PDFs were retrieved, no new eligibility decisions were made, and existing
screening/extraction history was retained. The semantic prefilter reports its
own current selection in semantic_screening.md and semantic_ranking.csv.

Ollama integration was tested with controlled HTTP responses; no live Ollama
server was installed because the real FastEmbed backend is operational. Use
`python 1_workspace/validation/live_semantic.py` for a real-model check and
`python -m unittest discover -s 1_workspace/validation -p 'test_*.py' -v`
for the offline suite. Embedding weights and isolated runtimes are ignored by
Git. A pre-migration SQLite backup is kept under 1_workspace/.backups/.


Final verification: the current precise queries cover 4,716 of the 5,220 stored
records; 3,970 have abstracts and real scores, 746 need abstract metadata, and
504 older records are OUTSIDE_SEARCH. At 0.5 all 3,970 scored candidates pass;
0.7 would retain 3,227 and 0.8 would retain 1,522. These are workload comparisons,
not validated precision/recall estimates. A real 15-record LLM batch was checked
for threshold, query provenance and current metadata hashes without printing
its abstracts or recording review decisions. SQLite quick_check returned ok;
225 screened records, 70 evidence rows and 29 parsed PDFs were preserved.

## Pre-publication review — 2026-10-27

All 56 offline behavioral tests passed. Additional tests cover persistent custom
search plans, non-overlapping date partitions and independent update watermarks,
stale extraction batch entries, and numerical stability of embedding vectors.
The selected plan now also governs ranking and eligibility checks after restart.

The FastEmbed model check succeeded offline with 384 dimensions, Unicode
roundtrip, related cosine 0.82928 and unrelated cosine 0.48312. This validates
operation, not threshold calibration. The current 0.5 threshold passes all 3,970
scored candidates; reviewers should evaluate a threshold using labeled examples.
Ollama was exercised with simulated responses, not a live server.

An initial one-shot OpenCode CLI diagnostic returned an empty list before the
registry finished loading. A persistent authenticated localhost probe confirmed
pdf-to-markdown registration in OpenCode 2.1.4. The published
check_opencode_skills.py waits for registration without a model call. The agent
contract retains a direct-file fallback for other wrappers.

The publication workflow prepares an isolated tree based on current origin/main,
preserving SLRBlueprint.tex and the upstream manuscript/provider guidance. Its
source allowlist excludes the live database, signed proposal, review outputs,
PDF conversions, model caches, local tools and private checkpoint ancestry. The
exported database contains an empty current schema; upstream initial narrative
templates are preserved, and search strings are replaced by an executable
question-answering example. Publication checks exercise exclusion of private
sentinels, preservation of dirty destinations and refusal of populated upstream
databases. The owner's original review and Git history remain untouched.

Final release-tree validation: all 59 offline tests passed. Native PDF skill
registration also passed in the isolated release tree. Its SQLite quick_check
returned ok and all four application tables were empty. README links, its two
main sections, and the three application folders were checked successfully.
