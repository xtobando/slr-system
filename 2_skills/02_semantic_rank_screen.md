# 02 ? Semantic prefilter, then LLM screening

Collect title/abstract metadata using the exact provider strings in
`1_workspace/search_strings.txt`. Do not dump thousands of abstracts into the
LLM context or retrieve PDFs before the semantic prefilter.

Run `python 2_skills/engine.py rank --backend fastembed --threshold 0.5`, or
select `--backend ollama` with an installed embedding model. The review owner
can choose another cutoff. Only title and abstract enter paper embeddings.
Long text is chunked, pooled and normalized instead of silently losing its
end. The score is raw cosine similarity against the plan's semantic query.
Failed embeddings never fall back to TF-IDF or a generative model.

Read counts in `1_workspace/semantic_screening.md` and the full ranking in
`semantic_ranking.csv`. PASS means score >= threshold; BELOW_THRESHOLD removes
a record from the automatic reading queue. MISSING_ABSTRACT requires metadata;
PENDING requires reranking. These states do not overwrite historical scientific
INCLUDE/EXCLUDE decisions, quotations or extracted evidence.

Use `python 2_skills/engine.py screen-semantic --threshold 0.6` to try a different
cutoff without reembedding. Explain how the choice changes workload and recall.
A cutoff of 0.5 is an initial setting, not a universal probability. Scores depend
on the model, query and pooling scheme. Changes to the plan or metadata require
reranking. Use the same model and query when comparing cutoffs.

Only now run `python 2_skills/engine.py fetch-batch --phase screen --limit 15`.
It returns only current passing title/abstract records. Read at most 15 per turn.
Copy an exact quote first, identify its IC/EC criterion, state the strongest
grounded argument against inclusion, then record TITLE_ABSTRACT INCLUDE,
EXCLUDE or MAYBE through `record-decision`. Uncertainty is not an exclusion.

A passing record with INCLUDE advances to `ingest` and PDF reading. Follow
playbook 03 for full-text eligibility and image inspection. Threshold PASS alone
is not final inclusion. MAYBE requires explicit adjudication; prior events are
retained. Checkpoint batches. One agent's two passes are not independent reviewers.

Historical records not returned by the current precise query plan are marked
OUTSIDE_SEARCH and cannot bypass the search filter using a previous high score.
