# BiomniBench-DA failure cases

This folder collects per-task case studies for tasks where the
benchmark question or rubric itself is broken — the gold answer rests
on scientifically wrong premises, or the rubric forces a methodology
that contradicts the question. These are the four tasks excluded from
the **capability mean** in the headline table; the **all-50 mean**
still includes them so unfiltered scores are visible.

For the broader analysis of every sub-0.7 task in the canonical
gpt-5.5 run (including the cases that are **not** benchmark-broken —
agent gaps and rubric-strict-but-defensible deductions), see the
"Failure analysis" section of the [top-level README](../../README.md).

## Index — 4 broken-benchmark tasks

| Task | Why the benchmark is broken | gpt-5.5 score | File |
|---|---|---:|---|
| `da-12-4` | Gold says *Kocuria* is a significant prognostic factor; the agent's earlier `covered14` run correctly said no — gold rests on a **retracted** TCGA tumor-microbiome paper (Poore et al. 2020 *Nature*, retracted 2024-07) and a known sequencing-contaminant genus. The canonical gpt-5.5 run happens to follow the broken recipe and score 0.86; the question is still scientifically wrong. | 0.86 | [da-12-4-kocuria-gold-answer-on-retracted-data.md](da-12-4-kocuria-gold-answer-on-retracted-data.md) |
| `da-6-2` | Question asks "**dynamically change** + predominant **temporal expression patterns**"; rubric requires significance at *all four* timepoints before pattern encoding — discarding 86% of training-responsive genes including every late-onset / transient / delayed response. The mandated filter is the **opposite** of what the question's framing implies. | 0.35 | [da-6-2-rubric-demands-all-4-timepoint-filter.md](da-6-2-rubric-demands-all-4-timepoint-filter.md) |
| `da-18-7` | Question asks explicitly bidirectional "mutually exclusive **or** co-occurring"; rubric forces a one-sided Fisher's exact test (which can only detect mutex). Statistically wrong test for the question's wording. Also docks for "ESR1 must be restricted to LBD aa 300-550" — every observed variant is already in 300-550, so the restriction is a phantom penalty. | 0.62 | [da-18-7-one-sided-test-for-a-two-sided-question.md](da-18-7-one-sided-test-for-a-two-sided-question.md) |
| `da-20-1` | Question asks "which two cell types most similar"; every metric the agent computes ranks SkMM-Fibroblast and AoSMC-SkMM within <1% (a statistical tie). Rubric requires AoSMC-SkMM and cites ACTA2/TAGLN as shared-lineage evidence — but ACTA2/TAGLN are **smooth-muscle / fibroblast markers, not skeletal-myoblast markers**, so the cited biology contradicts the cited pair. | 0.46 | [da-20-1-most-similar-pair-is-a-statistical-tie.md](da-20-1-most-similar-pair-is-a-statistical-tie.md) |

## What's NOT in this folder anymore

These were originally listed as failure cases but on re-review do not
meet the "benchmark broken" bar:

- **`da-19-1`** (gpt-5.5: 0.72 passing) — rubric is strict on filter thresholds (q<0.01 + log2FC<=-1) but the strict gold answer is itself scientifically defensible; agent uses Cuffdiff defaults and still passes. Not broken, just strict.
- **`da-8-3`** (gpt-5.5: 0.68) — the spiker definition is ambiguous (rubric C1=B), but the dominant score loss is the agent skipping the required phenotype correlation step (C4 = 0/15). That's an **agent gap**, not a benchmark issue.

Both are now discussed in the top-level README's "Failure analysis"
section under their respective categories.
