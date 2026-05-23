# Failure case: da-6-2 — the rubric demands an all-4-timepoint significance filter the question never asks for

**Task**: `da-6-2` (BiomniBench-DA / MoTrPAC endurance-training rat
study — temporal dynamics of the skeletal-muscle transcriptome)
**Scores**: 11 runs — best **65 / 100** (two runs at 65; rest 0–52).
**Routing**: `vertical_agent_selector` → `bulk_rna_analyst` (correct)
**Failure class**: benchmark-calibration — the rubric scores one
specific gene-selection methodology (require significance at *all
four* timepoints before pattern encoding) that the question never
communicates, and which is the *opposite* of what the question's
"temporal dynamics" framing implies. Aggravated by an internally
incoherent criterion (names a per-gene column for a per-timepoint
requirement).
**Severity**: high as a benchmark-validity signal — the agent's
analysis is sound, instruction-faithful, and biologically richer than
the rubric's mandated method; it is graded against an un-stated recipe
worth 30 points.

---

## TL;DR

da-6-2 asks how the skeletal-muscle transcriptome **dynamically
changes** over an 8-week training course and what the **predominant
sex-specific or shared temporal patterns** are. The agent ran a clean
temporal analysis: filter to the transcriptomics × vastus-lateralis
slice, encode each gene's 1w/2w/4w/8w response as a directional state
(Up / Down / none, `|logFC| ≥ 0.2`), classify shared vs sex-specific,
rank patterns by gene count, interpret. The rubric instead requires
that a gene be **statistically significant at all four timepoints**
before it is allowed a pattern — discarding every late-onset,
transient, and delayed-response gene. That filter is not in
`instruction.md`, is not standard time-course methodology, and removes
**86%** of the training-responsive genes — i.e. exactly the temporal
dynamics the question is about. The agent loses 20 points (criterion 2)
outright and 10 more (criterion 4, which is defined on top of
criterion 2) for not guessing it.

## What the task asks

`instruction.md` — Question (verbatim):

> "How does gene expression in vastus lateralis skeletal muscle
> (SKM-VL) dynamically change over the 8-week training course in males
> and females, and what are the predominant sex-specific or shared
> temporal expression patterns?"

The question contains no completeness requirement. "Dynamically
change" and "temporal expression patterns" are open framing that, if
anything, argue for *including* genes whose significance turns on or
off across the course — onset, transient, and delayed responses are
temporal dynamics. `instruction.md` otherwise only documents the
column list; it never says "restrict to genes significant at every
timepoint".

## What the agent actually did (from the trajectory)

Routed to `bulk_rna_analyst`; `trace.md` shows a deliberate analysis:

- Located the true header (row 18, below the `#` comment block).
- Filtered to `assay_code == 'transcript-rna-seq'` AND
  `tissue_code == 't56-vastus-lateralis'` → **6,128 rows** (the grader
  confirmed this count and gave criterion 1 an A).
- Kept the 766 features with a complete record for **both sexes at all
  four timepoints**.
- Per gene × sex × timepoint: directional call
  `timewise_p_value < 0.05 AND |logFC| ≥ 0.2` → a 4-character state
  string over (1w, 2w, 4w, 8w) with three states U / D / `.`
  (`.` = no significant directional change).
- Classified each gene mutually-exclusively as shared / sex-divergent /
  female-specific / male-specific; ranked patterns by gene count per
  category; reported a continuous male–female logFC concordance that
  rises with training duration (Pearson r 0.13 → 0.63 from 1w to 8w).

This is a legitimate, standard temporal-pattern analysis. A 3-state
(U/D/none) per-timepoint encoding produces fully-determined, unambiguous
patterns — `..UU` (late induction), `...U` (8w-only), `UUUU`
(sustained) — and "shared = same string in both sexes" is unambiguous
with three states. The grader gave the encoding (criterion 3) and the
ranking (criterion 5) an A, and confirmed the categories are mutually
exclusive.

## The rubric grades a different, un-communicated methodology

Rubric **criterion 2** (20 pts) — "Require Significance at All Four
Timepoints per Sex":

> [A]: Per gene per sex, requires significance at ALL FOUR timepoints
> (1w, 2w, 4w, 8w). Genes that are significant at only 1-3 timepoints
> in a given sex are excluded from that sex's pattern set.
> [C]: No completeness filter, OR uses any gene that has at least one
> significant timepoint.

Rubric **criterion 4** (20 pts) — the shared / sex-specific
categorisation — defines its A level *on top of* criterion 2 ("shared
= significant at all 4 timepoints in BOTH sexes"). So failing
criterion 2 caps criterion 4 at B by construction.

The agent's 3-state encoding keeps genes with `.` positions; the
rubric's criterion 2-A excludes them. The agent scored **C (0/20)** on
criterion 2 and **B (10/20)** on criterion 4 — 30 points — purely for
choosing a different, equally-principled gene-selection rule.

## Data verification

Verified directly against
`environment/data/paper_deg.xlsx` (sheet *2 - Training-regulated
features*, header at row 18; TRNSCRPT × t56-vastus-lateralis slice):

**1. The mandated filter discards 86% of the responsive genes.**
Of the 1,532 (feature, sex) pairs that have a complete 4-timepoint
record, significance (`timewise_p_value < 0.05`) at:

| # significant timepoints | (feature, sex) pairs |
|---|---:|
| 0 | 368 |
| 1 | 447 |
| 2 | 343 |
| 3 | 213 |
| **4 (rubric's filter)** | **161** |

A "≥ 1 significant timepoint" analysis uses 1,164 pairs; the rubric's
"all 4" filter keeps **161 / 1,164 = 13.8%**. The 86% it discards are
precisely the onset / transient / delayed-response genes — the
temporal dynamics the question asks about. A gene induced only at 8w
(`...U`) has an unambiguous, biologically meaningful temporal pattern;
the rubric throws it away.

**2. Criterion 2 is internally incoherent.** Criterion 2-A says
"requires significance (`training_q < 0.05` or equivalent) at ALL FOUR
timepoints". `training_q` is a **single per-gene** FDR for the overall
training effect — verified constant across a gene's four timepoint
rows (`training_q.nunique() == 1` for all 1,532 (feature, sex) pairs).
"`training_q < 0.05` at all four timepoints" is therefore vacuous as
literally written: it is the same value at every timepoint. The
requirement is only computable via `timewise_p_value`, the one
genuinely per-timepoint significance column — which the rubric names
only as a vague "or equivalent". A 20-point criterion should not be
self-contradictory about which column it grades.

**3. Criterion 1 has a factual error.** Criterion 1 describes the
target tissue as "the gastrocnemius / skeletal-muscle-vastus-lateralis
(SKM-VL) tissue". The data has two distinct skeletal-muscle tissues:
`SKM-VL` = `t56-vastus-lateralis` and `SKM-GN` = `t55-gastrocnemius`.
They are different muscles; SKM-VL is unambiguously vastus lateralis
and gastrocnemius (SKM-GN) is explicitly out of scope. The criterion
text conflates them. This did not change grading here but corroborates
a hastily-written rubric.

## Why the rubric's filter is the wrong analysis for this question

Standard multi-timepoint expression methodology — trajectory
clustering, `maSigPro`-style polynomial modelling, or the MoTrPAC
study's own design — identifies a gene as training-regulated by an
**overall** test (this dataset literally ships that as the per-gene
`training_q` column) and then characterises *when* and *how* it
responds. None of these require per-timepoint significance everywhere;
doing so keeps only genes that were significantly regulated for the
entire 8 weeks — the **least** temporally dynamic subset — and answers
a narrower question ("which genes are persistently regulated") than the
one asked ("how does expression dynamically change… predominant
temporal patterns"). The agent's 3-state encoding over all
≥1-timepoint-responsive genes is the higher-resolution, more
question-faithful analysis.

## What this is NOT

- **Not a routing failure** — `bulk_rna_analyst` is the correct
  specialist and was selected.
- **Not agent under-scoping** — the trajectory shows a complete,
  documented temporal-pattern pipeline with a stated threshold,
  mutually-exclusive categories, and a pattern-frequency ranking. The
  grader gave criteria 1, 3, 5 an A and criterion 7 an A.
- **Not fixable on the omicos side without rubric leakage.** "Require
  significance at every timepoint" is not general best practice for
  time-course analysis — it is a task-specific, restrictive choice.
  Encoding it into a skill or agent would be both wrong general advice
  and overfitting to this task's hidden rubric.

## What this IS

A benchmark-calibration failure: the rubric demands a specific,
restrictive gene-selection rule (significance at all four timepoints)
that the question never communicates and that contradicts the
question's own "temporal dynamics" framing, then zeroes a valid,
biologically richer alternative. Aggravated by an internally
incoherent criterion-2 specification.

## The genuine agent shortcoming

Criterion 6 (B, 5/10) — the biological interpretation is generic: it
discusses endurance-training remodelling without naming example genes
from the top patterns or linking them to specific pathways
(mitochondrial / oxidative-phosphorylation programmes, etc.). This is
a real, legitimate shortfall and is fixable as general best practice
(always name the specific entities behind a pattern). It is worth ~5
points — one of seven criteria.

## Score decomposition and ceiling

| Criterion | Pts | Got | Note |
|---|---:|---:|---|
| 1 Restrict to TRNSCRPT × SKM-VL | 15 | 15 A | correct |
| 2 Significance at all 4 timepoints | 20 | **0 C** | un-communicated filter |
| 3 4-state directional encoding | 20 | 20 A | correct |
| 4 Shared / sex-specific (mut. excl.) | 20 | **10 B** | knock-on from crit 2 |
| 5 Pattern ranking & frequency | 15 | 15 A | correct |
| 6 Biological interpretation | 10 | **5 B** | genuine agent shortfall |
| 7 Source reliability | 0 | 0 A | correct |
| **Total** | | **65** | |

A scientifically sound, instruction-faithful analysis with criterion 6
fixed (name example genes) tops out at **15 + 0 + 20 + 10 + 15 + 10 +
0 = 70**. Exceeding 80 requires applying the all-4-timepoint filter —
an un-stated, restrictive, anti-question choice. The ~30-point gap
between 70 and a full score is the benchmark-calibration defect, not an
agent capability gap.

## Mitigation options

1. **Document and accept** (this file) — the dominant 30-point loss is
   a rubric-vs-instruction mismatch; do not chase it with skill/agent
   edits, which would be rubric leakage.
2. **Legitimately recoverable**: criterion 6 (+5) via the general
   "name the specific genes / pathways behind every reported pattern"
   best practice — already standard guidance for the analyst agents.
3. **Upstream fix (task maintainers)**: either (a) add the
   completeness requirement to `instruction.md` so it is part of the
   stated task, or (b) relax criterion 2 to accept any principled,
   documented per-timepoint encoding (including 3-state U/D/none over
   all training-responsive genes); and fix criterion 2's column
   reference (`timewise_p_value`, not `training_q`) and criterion 1's
   gastrocnemius/vastus-lateralis conflation.

## Run artifact pointers

- Runs: `runs/smoke-20260520-145630/…/da-6-2/` and
  `runs/smoke-20260520-144305/…/da-6-2/` (both 65); nine lower runs.
- Agent trace / answer: `workspace/trace.md`, `workspace/answer.txt`.
- Data verification: `environment/data/paper_deg.xlsx`, sheet
  *2 - Training-regulated features*, header row 18.
