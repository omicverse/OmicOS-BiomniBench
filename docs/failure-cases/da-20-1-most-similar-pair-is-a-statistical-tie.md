# Failure case: da-20-1 — the "most similar pair" the rubric demands is a statistical tie

**Task**: `da-20-1` (BiomniBench-DA / bulk RNA-seq / unsupervised structure)
**Scores**: 10 runs; best **71 / 100**. The best run recovers the four
cell types perfectly (K-means ARI = 1.0) and scores A on 4 of 7
criteria — the ~29-point gap is the rubric, not the analysis.
**Routing**: `vertical_agent_selector` → `bulk_rna_analyst` (correct)
**Failure class**: benchmark-calibration — the rubric forces one
paper-specific answer onto a sub-1% statistical tie, rationalises it
with markers that do not support the claimed relationship, and pins
two preprocessing parameters to exact values that the instruction
never states and that contradict the skill the agent correctly used.
**Severity**: moderate — the agent's analysis is correct and
skill-compliant; the rubric suppresses ~29 points.

---

## TL;DR

da-20-1 asks whether four primary cell types have distinct or
overlapping baseline transcriptional signatures **and which two are
most similar**. The agent (best run) ran the standard pipeline,
recovered all four cell types perfectly (K-means ARI = 1.0,
silhouette 0.88), computed pairwise cell-type similarity three ways,
and reported the closest pair its data actually shows.

The rubric requires the answer be **AoSMC–SkMM**. The data does not
support that as *the* answer:

- By every metric the agent computed — centroid distance in the
  embedding, Pearson and Spearman of the mean profiles — **SkMM–
  Fibroblast is the closest pair, with AoSMC–SkMM second by under
  1%**. The "most similar pair" is a statistical tie; the data does
  not single one out.
- The rubric's biological rationale — cite **ACTA2 / TAGLN** as
  shared-lineage evidence for AoSMC–SkMM — is incorrect. ACTA2 and
  TAGLN are smooth-muscle markers (also expressed by fibroblasts and
  myofibroblasts); they are **not** skeletal-myoblast markers. They do
  not evidence an AoSMC–SkMM kinship.

Two further criteria (C2, C3) dock the agent for using ~3,000
variance-filtered genes and 10 SVD components instead of the rubric's
~10,000 and 50–100 — values absent from `instruction.md` and at odds
with the `sample-clustering` skill the agent followed.

## What the task asks

`instruction.md` — Question:

> "To validate our primary cell screening platform before compound
> profiling, do the four primary cell types show distinct or
> overlapping baseline transcriptional signatures, **and which cell
> types are most similar to each other?**"

The instruction states no preprocessing parameters, no marker list,
and no expected pair. It asks an open question: which two are closest.

## The rubric's required answer

Rubric Criterion 5 ("Biological Interpretation of Lineage
Similarity", 10 pts), level A:

> "...while **AoSMCs and SkMMs show greater transcriptional
> similarity**; identifies established cell-type markers including at
> minimum ACTA2 and TAGLN for AoSMCs, MEST or MDK for SkMMs ... and
> attributes AoSMC–SkMM similarity to their shared
> mesenchymal/contractile lineage."

Level B further expects the answer to cite "specific shared markers
such as **ACTA2 and TAGLN as evidence of this lineage relationship**."

So C5 grades against one fixed pair (AoSMC–SkMM) and one fixed
rationale (shared contractile lineage, evidenced by ACTA2/TAGLN).

## Problem 1 — the data shows a near-tie, not AoSMC–SkMM

The best run's pairwise cell-type similarity, from
`outputs/celltype_similarity_pairs.csv` (the agent computed all three
metrics the `sample-clustering` skill prescribes for a "which groups
are most similar" question):

| Pair | Centroid PC distance ↓ | Pearson ↑ | Spearman ↑ |
|---|---|---|---|
| **SkMM–Fibroblast** | **71.47** | **0.8923** | **0.8728** |
| AoSMC–SkMM | 72.07 | 0.8833 | 0.8528 |
| AoSMC–Fibroblast | 79.08 | 0.8610 | 0.8393 |
| SkMM–Melanocyte | 88.49 | 0.8228 | 0.7828 |
| AoSMC–Melanocyte | 89.97 | 0.8099 | 0.7700 |
| Fibroblast–Melanocyte | 90.54 | 0.8252 | 0.7971 |

All three metrics rank **SkMM–Fibroblast first** and AoSMC–SkMM
second. The separation between the top two pairs is below 1% on every
metric (Pearson 0.8923 vs 0.8833; PC distance 71.47 vs 72.07). The
data does not robustly determine a single "most similar pair" — the
top two are tied within noise. The agent reported its computed #1
(SkMM–Fibroblast); the rubric requires #2.

## Problem 2 — the rubric's marker rationale is biologically wrong

C5 wants AoSMC–SkMM similarity "attributed to shared
mesenchymal/contractile lineage" and (level B) ACTA2/TAGLN cited "as
evidence of this lineage relationship."

- **ACTA2** (smooth-muscle α-actin) and **TAGLN** (transgelin / SM22α)
  are canonical **smooth-muscle** markers, and are also expressed by
  fibroblasts and myofibroblasts. They are not skeletal-myoblast
  markers — skeletal myoblasts are marked by PAX7 / MYF5 / MYOD1 /
  MYOG.
- ACTA2/TAGLN therefore link AoSMC to **fibroblasts** (the
  well-documented smooth-muscle ↔ myofibroblast ↔ fibroblast
  transcriptional continuum), not to skeletal myoblasts. They cannot
  serve as evidence of an AoSMC–SkMM relationship.
- The rubric is internally inconsistent here: it lists ACTA2/TAGLN for
  AoSMC and an entirely different, non-overlapping set (MEST/MDK) for
  SkMM, then asks the agent to cite the two as "shared markers"
  evidencing one lineage. The markers it names for the two cell types
  do not overlap.

Skeletal muscle and smooth muscle are distinct muscle lineages with
distinct contractile programs; "the two muscle types must be the most
similar pair" is a loose prior, not what this baseline DMSO data
shows.

## Problem 3 — C2/C3 pin parameters the instruction never states

Criterion 2 (25 pts) requires "variance-based filtering to retain the
top **~10,000** most variable genes" and TruncatedSVD "to **~50–100**
components"; Criterion 3 (15 pts) repeats the 50–100 component count.
The agent used ~3,000 genes and 10 components → C2 = B, C3 = B
(−12 and −7).

But the agent loaded and followed the `sample-clustering` skill, which
says to variance-filter to "the **few thousand** most variable
features" and reduce to "**tens of** components." ~3,000 genes and 10
components are exactly what that guidance yields. The rubric's
"10,000 / 50–100" appears nowhere in `instruction.md` and is tighter
than the skill the agent correctly used. And the choice made no
difference to the result: K-means on the agent's embedding gave
ARI = 1.0, NMI = 1.0, silhouette 0.88 — a perfect, unambiguous
four-way recovery (C4 = A).

## Side-by-side

| Aspect | Rubric expectation | Agent's output (best run) | Match |
|---|---|---|---|
| Baseline subset (DMSO 0.0625%) | 192-sample subset, QC reviewed | correct, QC summarised | ✅ C1 A |
| Variance filter | ~10,000 genes | ~3,000 (per `sample-clustering` skill) | ◐ C2 B |
| Dim. reduction | TruncatedSVD, 50–100 comp | TruncatedSVD, 10 comp (per skill) | ◐ C3 B |
| K-means k=4 + concordance | exact 4-way recovery | ARI = NMI = 1.0, 48/cluster | ✅ C4 A |
| Most similar pair | AoSMC–SkMM | SkMM–Fibroblast (its computed #1) | ❌ C5 C |
| Limitations | ≥2 stated | stated | ✅ C6 A |
| Source reliability | traceable | traceable | ✅ C7 A |

Four criteria at A, including a perfect clustering. The lost points
are the parameter recipe and a forced most-similar-pair.

## What this is NOT

- **Not a routing failure** — `bulk_rna_analyst` is the correct
  specialist and was selected.
- **Not an agent capability gap** — the agent ran the full pipeline,
  recovered the four cell types perfectly, and used the exact
  three-metric similarity method the `sample-clustering` skill
  prescribes for a "which groups are most similar" question.
- **Not a preprocessing failure** — the C2/C3 parameter choices match
  the loaded skill and produced a flawless clustering.

## What this IS

A benchmark-calibration failure on two layers:

1. **C5 over-determines a tie.** The data ranks SkMM–Fibroblast and
   AoSMC–SkMM within <1% of each other on every metric. The rubric
   requires one specific pair be named, and rationalises it with
   markers (ACTA2/TAGLN) that do not actually support an AoSMC–SkMM
   relationship. An honest analysis of this data reports a near-tie;
   the rubric scores that as C.
2. **C2/C3 pin exact parameters.** The rubric demands ~10,000 genes
   and 50–100 components; the instruction states neither, and the
   `sample-clustering` skill the agent correctly followed recommends
   lower values. The clustering was perfect regardless.

Neither is fixable on the omicos side without rubric leakage. The
~29-point gap is the rubric's, not the agent's.

## The one genuine agent gap

The agent reported SkMM–Fibroblast as the most similar pair as a
flat conclusion, without noting that SkMM–Fibroblast and AoSMC–SkMM
are statistically indistinguishable in this data. A maximally rigorous
answer would state the near-tie explicitly. This would not recover
C5 — the rubric still requires the AoSMC–SkMM pair be named — but it
is the one place the answer could have been sharper.

## Run artifact pointers

- Best run: `runs/smoke-20260520-155130/vertical_agent_selector/da-20-1/`
  (score 71).
- Pairwise similarity: `workspace/outputs/celltype_similarity_pairs.csv`,
  `celltype_mean_profile_pearson.csv`, `celltype_centroid_pc_distances.csv`.
- Clustering concordance: `workspace/outputs/kmeans_cluster_vs_celltype.csv`,
  `analysis_summary.json` (`kmeans`: ARI/NMI = 1.0).
- Agent trace / answer: `workspace/trace.md`, `workspace/answer.txt`.
