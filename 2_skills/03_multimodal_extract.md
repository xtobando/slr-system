# 03 — Retrieve, read, inspect, extract

For standalone conversion of a local PDF to Markdown with figure/formula crops,
use the optional [PDF-to-Markdown skill](pdf-to-markdown/SKILL.md). Its
`convert-pdf` command creates separate artifacts without changing review state.
It does not replace the database-linked `ingest` workflow described here.

Run `python 2_skills/engine.py ingest` after title/abstract inclusion, or use
`--bib-key` for a particular paper. The engine tries an existing local PDF first,
then OA metadata, configured Unpaywall, and an optional institutional library URL.
Cookies must be Netscape format, scoped to domains, and obtained through lawful
access. A library login page is not a PDF. Failed retrieval becomes
NEEDS_MANUAL_PDF with a clickable source link; place the file at the displayed
`3_papers/raw_pdfs/BibKey.pdf` path and run ingest again.

Run `python 2_skills/engine.py fetch-batch --phase extract --limit 3`. Process at
most three included papers per turn. It returns paths, not full texts; read
sections sequentially and track the wrapper's remaining context. A large paper
may need its own fresh turn. Stay below the 272,000-token project ceiling.

Every parsed page has `<!-- PAGE N -->`, with N the one-based physical PDF page
(not the journal's printed page number). Every page is rendered at 200 DPI and
linked by `[VISUAL_ASSET: 3_papers/parsed_cache/BibKey/page_N_visual.png]`.
Caption, math-symbol, image, and vector-drawing detection is recorded in Markdown;
rendering all pages prevents heuristic misses from discarding content.

**When an RQ-relevant section contains a VISUAL_ASSET tag, invoke the image/vision
inspection tool on that exact PNG.** Inspect figure panels, axes, equations,
subscripts, units, captions, matrices, and table footnotes. Never substitute a
guess from malformed extracted text. For scanned PDFs, use the page image; no
OCR text is fabricated. If the image is illegible, inspect the original PDF at
higher zoom using the wrapper or defer the finding. PNG preservation is not an
assurance of lossless mathematical transcription.

Establish FULL_TEXT eligibility using the quote-first and devil's-advocate process.
For a decision quote visible only in a PNG, add `vision:page=N` to notes. This is
an explicit inspection attestation; the engine checks that the asset exists.
For each extraction, copy the quote first, then record a narrowly defined value:

```text
python 2_skills/engine.py record-extraction --bib-key KEY --variable VARIABLE --quote QUOTE --page 4 --value VALUE --used-vision 1
```

The record must belong to a FULL_TEXT INCLUDE paper. Text-only evidence must
match that page's extracted text; visual evidence requires the page PNG and
`--used-vision 1`. Record uncertainty in the value and narrative; do not invent
precision. An identical repeated record is idempotent; a changed value/quote
creates another evidence row, preserving previous claims for adjudication.
The generated matrix shows current eligibility so reopened/excluded papers are
not silently treated as final evidence. Cite every paper with its clickable local
PDF and DOI, or arXiv/PubMed source. Checkpoint after each completed batch.
