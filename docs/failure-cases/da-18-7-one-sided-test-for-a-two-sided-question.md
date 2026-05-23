# Failure case: da-18-7 — the rubric docks 15 points for three calibration choices, one of them statistically wrong

**Task**: `da-18-7` (BiomniBench-DA / MSK-IMPACT endocrine-resistant
breast cancer — ESR1 vs MAPK mutual exclusivity)
**Score**: **70 / 100** (criteria: c1 A=15, c2 B=10, c3 B=10,
c4 B=10, c5 A=15, c6 A=10, c7 A=0)
**Routing**: `vertical_agent_selector` → `tabular_genomics_analyst`
(correct)
**Failure class**: benchmark calibration — the task technically
passes, but the score is suppressed ~15-20 points by three docked
criteria that are all methodology calibration; one of the three
(crit 4) penalizes the *statistically correct* choice.
**Severity**: medium — the score still clears the 0.7 bar, but it
mis-represents a well-reasoned analysis as a marginal pass and drags
the aggregate.

---

## TL;DR

da-18-7 asks whether ESR1 mutations and MAPK pathway alterations are
"mutually exclusive or co-occurring" in post-therapy HR+/HER2- breast
tumours. The agent ran a clean, deliberate analysis: correct cohort,
a per-sample 2×2 contingency table, a two-sided Fisher's exact test,
OR + 95% CI + p, and a referenced biological interpretation — graded
A on cohort definition (c1), contingency reporting (c5),
interpretation (c6) and sourcing (c7). It loses 15 points across the
remaining three criteria, and **all three are calibration**:

- **c2** — docked for "not restricting ESR1 to the ligand-binding
  domain (residues 300-550)". But every ESR1 variant the agent
  observed is *already* within 300-550 — the restriction would not
  change a single sample. A phantom penalty.
- **c3** — docked for a "much broader MAPK gene set" than the
  rubric's specific ~7-gene curation. There is no canonical MAPK gene
  set; the agent's broader RTK/RAS/MAPK set is documented and
  defensible.
- **c4** — docked for a two-sided Fisher's exact test where the
  rubric "requires" one-sided. But the question is explicitly
  two-directional ("exclusive **or** co-occurring") — a two-sided
  test is the statistically correct choice. The rubric penalizes the
  correct test.

## What the task asks

`instruction.md` — Question:

> "To identify genomic mechanisms driving endocrine resistance, are
> ESR1 mutations and MAPK pathway alterations **mutually exclusive or
> co-occurring** in post-hormonal therapy HR+HER2- tumors?"

The question names neither the ligand-binding domain, a specific MAPK
gene list, nor a test sidedness.

## What the agent actually did (from the trajectory)

Routed to `tabular_genomics_analyst`; `trace.md` (222 lines, 33 tool
calls) shows a deliberate analysis:

- **Cohort** — restricted to post-therapy HR+/HER2- using the
  *sequenced sample's* receptor status, keeping metastases and
  post-treatment primaries, excluding treatment-naive primaries; 705
  samples. Alternatives were explicitly considered and rejected.
- **ESR1 status** — per-sample flag from non-synonymous ESR1 calls;
  131/705 (18.6%). The trace explicitly reasons about the `Hotspot`
  field and rejects it because it is uniformly `0` in the file and
  would discard the known D538G / Y537 LBD changes.
- **MAPK status** — a 37-gene RTK/RAS/MAPK set, with negative
  regulators (`NF1`, `RASA1`, `SPRED1/2`, `DUSP4/6`, …) correctly
  coded so that *deep deletion* counts as pathway activation; 317/705
  (45.0%). Per-gene contributions were exported. The trace states the
  set is "intentionally broad for MAPK signaling in a targeted panel".
- **Test** — a 2×2 contingency table (ESR1 mut/wt × MAPK alt/wt),
  two-sided Fisher's exact: OR = 0.768, 95% CI 0.521-1.130, p = 0.206.
- **Conclusion** — "largely independent, partially overlapping
  endocrine-resistance mechanisms", with references.

## Why each docked criterion is calibration

### c2 — "did not restrict ESR1 to the LBD (residues 300-550)"

The agent's own ESR1 variant breakdown (top 10, covering 126/131
mutated samples):

| Variant | Samples | Residue | In 300-550? |
|---|---:|---:|:--:|
| D538G | 53 | 538 | ✓ |
| Y537S | 29 | 537 | ✓ |
| E380Q | 13 | 380 | ✓ |
| Y537C | 10 | 537 | ✓ |
| Y537N | 10 | 537 | ✓ |
| L536H | 4 | 536 | ✓ |
| V422del | 3 | 422 | ✓ |
| L536P | 2 | 536 | ✓ |
| F461V | 1 | 461 | ✓ |
| A546D | 1 | 546 | ✓ |

Every observed ESR1 variant is already inside the ligand-binding
domain. ESR1 mutations in breast cancer are overwhelmingly LBD
hotspots — "all non-synonymous ESR1" and "ESR1 LBD" are, in this
cohort, the same set. Formally restricting to residues 300-550 would
change the ESR1-mutant count by at most ~5 of 131 samples and would
not move OR or p. The agent additionally *reasoned about* the
restriction (rejecting the broken `Hotspot` column for a documented
reason). c2 B is a phantom penalty for an omitted formality with no
numerical effect.

### c3 — "much broader MAPK gene set than the specified set"

The rubric expects exactly `ERBB2, NF1, EGFR, KRAS, HRAS, BRAF,
MAP2K1` (+ NF1 deletions, EGFR amplifications). The agent used a
37-gene RTK/RAS/MAPK pathway set. There is **no canonical MAPK gene
set** — it is a definitional choice, and a broader RTK/RAS/MAPK set
that includes FGFR/RAS isoforms and negative regulators is a standard,
arguably more complete, curation. The agent documented the set,
handled negative regulators correctly, and exported per-gene
contributions. The rubric grades adherence to one specific
un-communicated list. Calibration.

### c4 — "two-sided Fisher's exact instead of the required one-sided"

This is the sharpest case. The question asks whether the two
alteration classes are "mutually exclusive **or** co-occurring" — an
explicitly **two-directional** question with no prior on the
direction. The statistically correct test for "is there any
association, in either direction" is **two-sided**. A one-sided test
presupposes you are only testing for depletion. The agent reported a
complete two-sided result (OR, 95% CI, p) — the right answer to the
question as asked. The rubric "requires" one-sided and docks the
two-sided choice. Here the rubric is not merely demanding an
un-communicated convention — it is penalizing the statistically
appropriate test for the question it itself posed.

## What this is NOT

- **Not a routing failure** — `tabular_genomics_analyst` is the right
  specialist and was selected.
- **Not agent under-scoping** — unlike its sister task da-18-5 (which
  answered only a literal frequency sub-clause), here the agent
  performed the full comparison the question asks for and earned A on
  four of seven criteria.
- **Not a skill gap** — `somatic-mutation-analysis` already prescribes
  a per-sample 2×2 + Fisher's exact for co-occurrence / exclusivity,
  and "use a curated pathway gene set and state it". The agent
  followed the skill. No skill edit would or should change this
  outcome; chasing the rubric's exact gene list or test sidedness
  would be rubric leakage.

## What this IS

A benchmark-calibration case: a well-reasoned, well-documented
analysis graded down ~15-20 points by three un-communicated
methodology expectations — one of which (one-sided test for a
two-directional question) is statistically incorrect. da-18-7's score
of 70 understates the analysis; its "true" quality is ~85-90.

## Run artifact pointers

- Run: `runs/tier2-batch2/vertical_agent_selector/da-18-7/`.
- Agent trace / answer: `workspace/trace.md`, `workspace/answer.txt`.
- Grade: `grade.json` (criteria 2/3/4 at level B).
