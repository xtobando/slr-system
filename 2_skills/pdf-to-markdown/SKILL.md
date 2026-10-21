---
name: pdf-to-markdown
description: Read and convert local PDFs into reusable Markdown while preserving formulas, figures, and diagrams as images. Use when a task needs PDF text and visual evidence, including explaining a proposal's methods or equations, even without an explicit conversion request. Use the normal ingest workflow for registered SLR paper evidence.
metadata:
  opencode/autoinvoke: "true"
---

# PDF to Markdown

Select this skill when reusable PDF text and preserved visuals help fulfill the
user's task. The user need not name the skill or request a terminal command.
Do not convert a PDF merely because it is mentioned, or when only citation
metadata is needed. Continue with the user's reading, explanation, or extraction
task after conversion; creating Markdown is an intermediate step when appropriate.

Locate the project root two directories above this skill directory. Prefer its
`1_workspace/.venv/Scripts/python.exe` on Windows or
`1_workspace/.venv/bin/python` on Unix when present; otherwise use the configured
Python environment. Run `2_skills/engine.py convert-pdf` yourself from that root.
This utility needs PyMuPDF from `requirements.txt`; no additional
package or model is required. It does not initialize or modify SQLite, BibTeX,
screening, or review history. Do not run `init` or `status` solely for conversion.

## Convert the requested PDF

Use the PDF identified by the user or task context; clarify only if the intended
document is ambiguous. Relative input and output paths resolve
from the project root; absolute input paths are also supported. A basic command
is `python 2_skills/engine.py convert-pdf --pdf PATH` with the actual path quoted.

| Flag | Behavior |
|---|---|
| `--pdf PATH` | Required local PDF input. The original file is read, not modified. |
| `--output-dir DIR` | Optional new directory under `1_workspace/` or `3_papers/parsed_cache/`. The destination must not already exist. |
| `--dpi N` | Resolution for page and crop PNGs; default 300, allowed range 72–600. |
| `--crop PAGE X0 Y0 X1 Y1` | Optional manually identified crop; repeat for multiple regions. Page is one-based and physical. Coordinates are unrotated PyMuPDF page points, 72 per inch, with origin at top left, x rightward and y downward. |

Without `--output-dir`, output goes to
`3_papers/parsed_cache/documents/<slug>-<hash12>-<dpi>dpi/`. Existing destinations
are rejected rather than overwritten. Reuse an existing conversion when its
`assets.json` source SHA-256 matches the current PDF, the resolution suits the
task, and its Markdown and referenced images exist. For another rendering, choose a fresh
output directory; do not delete prior artifacts automatically. A page rendering
above 80 million pixels is rejected. Reduce DPI within the allowed range if an
oversized page requires it.

The result contains:

- `fulltext.md`: extracted text as basic paragraph Markdown with relative image
  embeds and page references.
- `page_N_visual.png`: a complete rendered image of every page, retained even
  when crops exist.
- Candidate image, vector, and formula crops, plus any requested manual crops.
- `assets.json`: source SHA-256 and page/bounding-box metadata for the assets.

Keep Markdown and its images together so relative embeds resolve. Output under
`3_papers/parsed_cache/` stays local under the existing ignore rules. Output under
`1_workspace/` may be tracked by Git; choose the destination to match the user's
sharing intent, without publishing documents as part of conversion.

## Check visual preservation

Inspect the generated Markdown and open relevant full-page PNGs with the
available image tool. Compare candidate crops against the page, especially
equations, multi-panel figures, labels, captions, and table footnotes. Detection
is heuristic: an undetected region remains visible in its full-page asset.

If a needed crop is missing or cut off, identify its unrotated coordinates from
the source page and rerun conversion into a new directory with `--crop`. Do not
guess coordinates from a rotated screenshot without mapping them back to the
unrotated page. Retain full-page references alongside crops.

The converter does not reconstruct exact reading order, table structure, or
layout and does not perform OCR or generate LaTeX. Scanned pages may have little
extractable text. Formulas are preserved visually; malformed extracted text is
not a reliable transcription. PNG rendering is not lossless mathematical proof.

If the user wants editable mathematics, inspect the original visual and add only
verified `$...$` or `$$...$$` transcriptions, preferably in a companion
`annotated.md`. Keep the original image reference and generated `fulltext.md`.
If vision is unavailable or symbols remain unclear, preserve the image and
report the limitation rather than inventing notation.

Return links to the conversion folder's Markdown and manifest, state any pages
requiring manual review, and describe whether formulas remain images or include
verified transcription. Do not imply that conversion completed SLR screening or
evidence extraction.
