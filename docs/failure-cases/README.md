# BiomniBench-DA failure cases

This folder collects per-task case studies for tasks where the
omicos-biomnibench harness measured a low score AND the reason is
worth documenting rather than fixing. Two kinds of cases land here:

1. **Benchmark-calibration cases** — agent's underlying science is
   correct (verified by the grader's own scientific-reasoning
   criterion) but the rubric penalizes specific methodology choices
   that were never communicated through `instruction.md`. These are
   *not* fixable on the omicos side without rubric leakage. We
   document them so aggregate scores are interpretable.

2. **Architecture / catalog cases** — real gaps in omicos coverage
   (missing specialist, prompt-level limitation, model-compliance
   shortfall) where the documentation captures *why* the case
   exhibits the behavior and what would be needed to close the gap.
   These often have associated GitHub issues or PRs.

Each case file is named `<task_id>-<short-tag>.md`. Headings inside
follow the template: TL;DR, instruction vs. rubric quotes, agent
output, side-by-side, classification, mitigation options.

## Index

| Task | Class | Score | One-line | File |
|---|---|---:|---|---|
| da-19-1 | benchmark-calibration | 63 | Rubric expects specific log2FC/q cutoffs not in instruction; agent's biology matched gold exactly | [da-19-1-rubric-vs-instruction-mismatch.md](da-19-1-rubric-vs-instruction-mismatch.md) |
| da-12-4 | benchmark-calibration | 73 | Gold says Kocuria is a significant prognostic factor; agent (correctly) says no — gold rests on a retracted dataset + a contaminant genus | [da-12-4-kocuria-gold-answer-on-retracted-data.md](da-12-4-kocuria-gold-answer-on-retracted-data.md) |
| da-8-3 | benchmark-validity | 63 | Task says to use "participant phenotypic classifications" but no data file ships them; rubric grades an un-stated derivation method + a correlation analysis the instruction never asks for | [da-8-3-spiker-classification-not-in-data.md](da-8-3-spiker-classification-not-in-data.md) |
| da-18-7 | benchmark-calibration | 70 | Question asks an explicitly two-directional "exclusive or co-occurring" question; agent runs the statistically correct two-sided Fisher test; rubric docks it for not using one-sided, plus an ESR1-LBD restriction with zero numerical effect and a non-canonical MAPK gene list — score suppressed ~15-20 pts | [da-18-7-one-sided-test-for-a-two-sided-question.md](da-18-7-one-sided-test-for-a-two-sided-question.md) |
| da-6-2 | benchmark-calibration | 65 | Question asks for "temporal dynamics / predominant patterns"; rubric requires significance at all 4 timepoints before pattern encoding — an un-stated, restrictive filter that discards 86% of responsive genes (every late / transient responder) and contradicts the question; worth 30 pts. Criterion 2 also names a per-gene column (`training_q`) for a per-timepoint requirement | [da-6-2-rubric-demands-all-4-timepoint-filter.md](da-6-2-rubric-demands-all-4-timepoint-filter.md) |
| da-20-1 | benchmark-calibration | 71 | Question asks which two cell types are most similar; every metric the agent computes ranks SkMM–Fibroblast and AoSMC–SkMM within <1% (a statistical tie), but the rubric requires the AoSMC–SkMM pair be named and cites ACTA2/TAGLN as shared-lineage evidence — markers that are smooth-muscle/fibroblast, not skeletal-myoblast. C2/C3 also pin exact gene/component counts absent from the instruction; ~29 pts | [da-20-1-most-similar-pair-is-a-statistical-tie.md](da-20-1-most-similar-pair-is-a-statistical-tie.md) |
