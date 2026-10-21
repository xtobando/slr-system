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

FastEmbed is optional and was not installed for validation; the tested ranking
backend is deterministic TF-IDF. Neural weights require a first-use download.
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
