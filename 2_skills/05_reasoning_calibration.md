# 05 — Permanent reasoning calibration

Trigger this workflow immediately when the user identifies a reasoning flaw.
Read the correction and locate the specific failure: a criterion was misread,
negative evidence was inferred from silence, a visual was skipped, population or
outcome scope drifted, a quote did not support the conclusion, or reports were
mistaken for independent studies.

1. Append a dated rule under exactly
   `## Active Reasoning Clarifications & Overrides` in `1_workspace/protocol.md`.
   Include the user's correction, a concrete behavioral rule, scope/criteria,
   affected paper citations, and whether it clarifies or amends the protocol.
   Preserve previous rules; explicitly supersede a conflicting rule.
2. Identify all potentially affected records, including earlier exclusions. Use
   audit history and stored quotes; do not assume only the most recent batch was
   affected. Record this set and the reason for its scope in the protocol.
3. Re-read original evidence in batches of at most 15 abstracts or 3 full texts
   per turn. Maintain the same context ceiling, quote-first sequence, strongest
   exclusion argument, and mandatory vision inspection for relevant assets.
4. Re-record affected decisions using `record-decision`, with notes identifying
   the correction. If a title/abstract decision is reopened, re-establish its
   full-text outcome before using it in the synthesis. Keep prior audit events
   and evidence rows; explain superseded extraction values in narrative.
5. Regenerate PRISMA, review the matrix's current-eligibility labels, amend the
   synthesis, and record which findings changed and which remain unresolved.
6. Run `python 2_skills/engine.py checkpoint --message "Reasoning calibration"`.

Rules must be actionable, for example: absence of a comparator in an abstract
requires full-text review when the protocol permits single-arm studies. Avoid
vague promises to be more careful or a rule engineered to force inclusion. If a
correction remains ambiguous, record the uncertainty and ask one focused question
while progressing with unaffected records. Never invent a user preference.
