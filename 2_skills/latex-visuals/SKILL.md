---
name: latex-visuals
description: Create or edit reproducible LaTeX diagrams and data plots using TikZ and PGFPlots, including figures for research manuscripts. Use when the requested deliverable is LaTeX source or a figure integrated into a LaTeX document.
metadata:
  opencode/autoinvoke: "true"
---

# LaTeX diagrams and plots

Create editable, publication-ready figures in LaTeX. Use TikZ for diagrams and PGFPlots for data-driven plots. Follow the target document's engine, class, packages, fonts, dimensions, and style; inspect its preamble before adding dependencies. If there is no target document, provide a small standalone `.tex` file and specify the required packages and compiler.

## Workflow

1. Establish the intended message, audience, output size, and source of the data or relationships. Inspect the relevant manuscript and data files. Ask only when an ambiguity would change the meaning of the figure.
2. Choose an appropriate form: a flowchart or network for relationships, a line or scatter plot for continuous measurements, bars or points for comparisons, and an appropriate uncertainty display when supplied. For review flow diagrams use actual recorded counts and distinguish reports from studies. Never invent observations, statistics, uncertainty, links, or counts; label illustrative examples clearly.
3. Write legible source using named styles, relative positioning and a modest palette. Use meaningful axis labels and units, legends where needed, accessible contrast and patterns or line styles in addition to color. Avoid misleading axes and unsupported interpolation. Keep external data in a stable, relative file path and document transformations, units, missing values, and provenance. Escape special LaTeX characters in labels and paths.
4. For manuscript integration, put reusable TikZ/PGFPlots content in a separate `.tex` file and include it with `\input{...}` inside the document's figure environment when appropriate. Avoid a second document preamble inside an included file. Respect existing caption and label conventions. Do not alter review evidence or generated PRISMA counts to fit a figure.
5. Compile with the project's existing build command when available; otherwise use `latexmk -pdf -halt-on-error -file-line-error figure.tex` or `pdflatex -halt-on-error -file-line-error figure.tex` for a standalone file, from the directory that resolves its relative paths. Use the project's chosen engine if it differs. Inspect the output at intended size, checking clipping, overlapping labels, symbols, contrast, axes, and fidelity to source data. Iterate on failures. Keep build artifacts in a separate build directory where practical.

TikZ and PGFPlots require a TeX distribution with the relevant packages; they are not Python dependencies of this project. For PGFPlots set a compatibility version supported by the installed distribution (for example `\pgfplotsset{compat=1.18}` when available). Do not silently install software or claim compilation or visual inspection succeeded if tools are unavailable. Deliver the source and explain any unverified output or missing dependency. If a figure depends on a specialized package or large dataset, state the dependency and preserve the input alongside the source where appropriate.
