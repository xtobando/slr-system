# 02 — Rank, quote, challenge, decide

1. Read RQs, PICOC, eligibility, and active overrides. Run
   `python 2_skills/engine.py rank`. The score combines dense cosine similarity
   and lexical TF-IDF similarity when FastEmbed is installed; otherwise it is
   deterministic lexical TF-IDF cosine. The audit records backend and model.
   Scores are priorities, never probabilities or exclusion thresholds.
2. Run `python 2_skills/engine.py fetch-batch --phase screen --limit 15`.
   Process at most 15 abstracts in this turn. Do not collect successive batches
   into the same turn. Keep the total context below the project ceiling of
   272,000 tokens and aim below 200,000 with room for tool output.
3. Copy the relevant exact title/abstract quote first. Identify which criterion
   it supports. Missing methods or abstract content means uncertainty, not absence.
4. State the strongest grounded argument for exclusion, even if inclusion seems
   obvious. Resolve it against the quote and protocol. Do not invent objections.
5. Record a TITLE_ABSTRACT INCLUDE, EXCLUDE, or MAYBE with the criterion code,
   quote, devil's-advocate argument, and concise notes using `record-decision`.
   The command rejects empty arguments and unmatched textual quotes. An INCLUDE
   code must be IC; an EXCLUDE code must be EC. For MAYBE use the unsettled rule.
6. Checkpoint after the batch. MAYBE records appear in status but are not recycled
   automatically into UNSCREENED batches; adjudicate those keys explicitly.

CLI form (supply actual source evidence, never these explanatory labels):

```text
python 2_skills/engine.py record-decision --bib-key KEY --stage TITLE_ABSTRACT --devils-advocate ARGUMENT --quote QUOTE --decision INCLUDE --code IC1 --notes RATIONALE
```

Before final inclusion, ingest and read full text, invoke vision for relevant
assets, then record a FULL_TEXT decision. The engine preserves both stages in
audit events. Title/abstract INCLUDE is not a final included report. Re-screening
an earlier stage reopens the full-text decision and retains older evidence for
traceability. Never claim two independent reviewers when one agent performs both
passes. Use the calibration playbook whenever a user identifies a flaw.
