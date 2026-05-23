# Failure case: da-19-1 — rubric over-specification vs. instruction silence

**Task**: `da-19-1` (BiomniBench-DA / oncology / differential-expression / easy)
**Run**: `smoke-20260519-170853`
**Score**: 63 / 100 (below the 70 pass threshold)
**Routing**: `vertical_agent_selector` → `bulk_rna_analyst` (correct)
**Failure class**: benchmark calibration, not agent / catalog / architecture
**Severity**: high — 37 lost points trace to a rubric ↔ instruction information gap;
the agent's underlying biology was 100% correct.

---

## TL;DR

The agent answered the scientific question correctly — same MYC numbers,
same biological interpretation, same edge-case handling, same caveats —
and the grader awarded full marks on the **scientific-reasoning**
criterion (`Domain Reasoning and Interpretation`, A = 14/14). But it
lost 37 of the remaining 86 points because the grading rubric checks
for *specific* filter thresholds and a *specific* ranking convention
that the task instruction never communicates to the agent.

This is not something the agent, catalog, or omicos-core can fix without
either (a) hardcoding the rubric's exact thresholds into agent prompts
(prohibited — that would be evaluator data leakage), or (b) BiomniBench
including the thresholds in `instruction.md`. The case is documented
here so future runs can recognize the pattern and so the omicos team
can decide whether to attempt mitigation or accept it as a known
benchmark artifact.

---

## What the task instruction tells the agent

From `instruction.md`:

> "To identify therapeutic targets downstream of CBFβ-SMMHC inhibition
> in inv(16) AML, which genes are most significantly downregulated
> upon AI-10-49 treatment?"

Plus a description of `gene_exp.diff` columns: `log2(fold_change)`,
`p_value`, `q_value`, `significant` (yes/no).

Plus the BiomniBench section template:
> "Decision and rationale: which method, threshold, normalization, or
>  filter was chosen, and why; what alternatives were considered or
>  rejected; any assumption or judgment call."

**No specific cutoffs are named anywhere in `instruction.md`.**

## What the rubric (`tests/rubric.txt`) actually requires

`Criterion 3 — Differential Expression Filtering` (A = 18 / B = 9 / C = 0):

> "[A]: Correctly applies all three filters: (1) `status == 'OK'` to
>  retain only tested genes, (2) `log2(fold_change) <= -1` for
>  >2-fold downregulation in AI-10-49, and (3) `q_value < 0.01` for
>  FDR control, yielding approximately 716 genes (or a count
>  consistent with the processed data)."

`Criterion 4 — Top Downregulated Gene Reporting` (A = 16 / B = 8 / C = 0):

> "[A]: … (3) ranking by log2FC magnitude (most negative first) …"

`Criterion 5 — MYC Repression Assessment` (A = 14 / B = 7 / C = 0):

> "[A]: … (2) MYC's rank among all filtered downregulated genes
>  (approximately #4 of 715 finite fold-change genes in the processed
>  data) …"

The cutoffs are baked into the rubric's gold-answer construction, but
the task instruction silently expects the agent to choose them
exactly. There is no field-standard for "most significantly
downregulated" that uniquely determines `(log2FC ≤ -1, q < 0.01,
sort by |log2FC|)` over the equally defensible alternative
`(Cuffdiff's built-in significant flag, sort by q-value)`.

## What the agent actually did

`bulk_rna_analyst` chose a defensible analytical convention:
- Filter: `status == 'OK'` ∧ `significant == 'yes'` (Cuffdiff's own
  flag, internally q < 0.05) ∧ `log2(fold_change) < 0` (any
  downregulation).
- Rank: by `q_value` ascending (the field-standard interpretation
  of "most significant").
- Yielded 3,027 downregulated genes; reported the top 10.

This is exactly what an experienced bioinformatician would do given
only the instruction's wording. The agent also documented the choice
explicitly in trace.md's "Decision and rationale" subsection per the
template the instruction requested.

## Side-by-side: rubric expectation vs. agent output

| Aspect | Rubric A-level expectation | Agent's actual output | Match |
|---|---|---|---|
| MYC log2FC | ≈ −3.30 | −3.29795 | ✅ exact |
| MYC q-value | ≈ 0.0002 | 0.000205676 | ✅ exact |
| MYC FPKM change | (paper: 218 → 22) | 218.301 → 22.196 | ✅ exact |
| MYC ranked among top | "#4 of 715" | #3 of 3,027 | ✅ same gene, top tier |
| IGHV4-4 infinite-FC edge case | "IGHV4-4 in the processed data" | IGHV4-4 listed as #1 | ✅ identified |
| CBFβ-SMMHC → MYC mechanism | A = full credit on Crit 6 | A = 14/14 | ✅ full mark |
| Crit 3 (filtering) | A = `log2FC ≤ -1 ∧ q < 0.01 ∧ status=OK` | C = used Cuffdiff `significant` flag | ❌ -18 |
| Crit 4 (ranking by |log2FC|) | A = most-negative-first | B = sorted by q-value | ❌ -6 |
| Crit 5 (MYC rank value) | A = #4 of 715 | B = #3 of 3,027 | ❌ -7 |

## Why the agent's choices are scientifically defensible

1. **Cuffdiff's `significant` flag is the tool author's recommended
   filter.** Cole Trapnell et al.'s Cuffdiff documentation says the
   flag is the canonical downstream filter; many published Cuffdiff
   re-analyses use it as the primary cutoff. An agent told only "use
   the gene_exp.diff" has no signal that the rubric prefers a custom
   manual cutoff over the tool's built-in one.

2. **q-value-based ranking is the dictionary definition of "most
   significantly".** The word "significant" in statistics means
   "lowest p / q". Sorting by |log2FC| answers "biggest effect", not
   "most significant" — these are different (and complementary)
   prioritization metrics.

3. **The 3-condition filter the rubric demands (log2FC ≤ -1, q < 0.01,
   status==OK) is one of many published cutoffs.** Field-standard
   alternatives include log2FC ≤ -0.585 (1.5-fold), q < 0.05 or 0.1,
   and the use of `significant=yes` itself. No part of the
   instruction signals which the rubric wants.

The grader notes on Crit 6 confirm the agent's biology was correct
even by the rubric's own standard:

> "[Crit 6 = A]: Links transcriptional repression to CBFβ-SMMHC
>  inhibition, explains MYC's mechanistic significance in
>  proliferation, and appropriately qualifies conclusions as
>  hypothesis-generating."

## What this is NOT

- **Not an agent capability gap.** Agent successfully loaded the
  Cuffdiff table, identified MYC, computed the correct numbers,
  explained the biology, handled the infinite-FC edge case,
  acknowledged limitations.
- **Not a routing failure.** Selector correctly chose
  `bulk_rna_analyst` (the right specialist for bulk DEG tables).
- **Not a delegation issue.** This task is fully within
  `bulk_rna_analyst`'s `use_when`; no sibling delegation would help.
- **Not a model-compliance issue.** gpt-5.5 followed the instruction
  faithfully and documented its choices transparently.

## What this IS

A **benchmark calibration mismatch**: the rubric's gold answer was
constructed with specific thresholds that the rubric author hard-coded
without surfacing them in `instruction.md`. The agent's job was to
recover those exact thresholds from a question that only said
"significantly downregulated".

## Mitigation options (none implemented — recording trade-offs only)

1. **Cutoff sensitivity sweep** (catalog-side, generic): teach every
   bulk-analysis agent that when the user asks "significantly DE"
   without naming cutoffs, compute results at multiple field-standard
   thresholds (`q < 0.01 / 0.05 / 0.1`, `|log2FC| ≥ 0 / 0.585 / 1`)
   AND the tool's built-in significant flag, and report the
   sensitivity table. **Cost**: ~10x compute per turn for sweeps.
   **Risk**: doesn't guarantee rubric A unless the grader credits
   sensitivity reporting. **Catalog purity**: high — no rubric
   leakage.
2. **Don't fix it.** Accept that this and similar tasks are pure
   benchmark-calibration noise; the architectural design correctly
   solved the science. **Cost**: ~5-10 of 50 BiomniBench tasks may
   show this pattern; aggregate score will reflect calibration
   noise. **Catalog purity**: highest — admits the issue
   transparently in this doc instead of hacking around it.

Recommended: option (2). Treat the BiomniBench score as a calibration-
noisy estimate of agent capability, and report results alongside this
failure-case doc so consumers of the benchmark understand which lost
points reflect agent limits vs. rubric over-specification.

## Run artifact pointers

- Local run dir: `runs/smoke-20260519-170853/vertical_agent_selector/da-19-1/`
- Final grade: `reports/smoke-20260519-170853/matrix.csv`
- Agent's trace.md: `runs/.../vertical_agent_selector/da-19-1/workspace/trace.md`
