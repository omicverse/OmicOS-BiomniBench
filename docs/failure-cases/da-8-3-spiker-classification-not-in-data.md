# Failure case: da-8-3 — the task requires participant classifications the data never ships

**Task**: `da-8-3` (BiomniBench-DA / metabolic / differential-expression / medium)
**Scores**: 3 runs — covered14 63, codex 36, codex 52. Best **63 / 100**;
the 70 pass line was never reached.
**Routing**: `vertical_agent_selector` → `metabolomics_analyst_pro` (correct)
**Failure class**: benchmark validity — the instruction refers to
"participant phenotypic classifications" as if they are provided, but
no shipped data file contains them; the rubric then grades against a
derivation method, and a correlation analysis, that the instruction
never communicates.
**Severity**: high as a benchmark-validity signal — the agent's
analyses are sound; it is graded against a hidden recipe applied to a
classification the data does not contain.

---

## TL;DR

da-8-3 asks for the top-10 differentially abundant metabolites
"between the 'potato-spiker' and 'grape-spiker' groups" and which
lipids "statistically mediate" insulin-resistance differences. The
question says to use "the participant phenotypic classifications" and
the dataset blurb says participants are "classified into … spiker
groups" — both speak of the classifications as a given. **No shipped
data file contains a spiker classification column.** The agent must
reverse-engineer the groups from raw continuous-glucose-monitor (CGM)
curves with zero guidance on the method, and the rubric then grades
against one specific method — a per-food median split — that the
instruction never states.

Across three runs the agent scored 36 / 52 / 63, never passing,
losing points on two things, neither communicated by `instruction.md`:

1. the spiker-grouping method (rubric wants a per-food median split);
2. a Pearson/Spearman **correlation** analysis the rubric requires,
   while the instruction asks only that lipids "**mediate**" the
   differences — i.e. a mediation analysis, which the agent did run.

## What the task asks

`instruction.md` — Question:

> "Using the metabolomics quantification data **and the participant
> phenotypic classifications**, identify the top 10 differentially
> abundant metabolites between the 'potato-spiker' and 'grape-spiker'
> groups, and determine which specific lipid species … statistically
> **mediate** the observed differences in insulin resistance and
> beta-cell function."

Dataset description:

> "74 participants … **classified into** carbohydrate-response
> phenotypes ('spiker' groups: rice, potato, bread, grape, etc.)."

Both passages present the spiker classifications as already-existing,
ready-to-use inputs.

## The classifications are not in the data

The four shipped files:

- `data_cgm.csv` — raw CGM curves (`glucose` × `subject` × `food` ×
  `rep` × `mins_since_start`).
- `data_meta.csv` — 74 × 19 columns: `id`, HbA1c, fasting glucose,
  fasting insulin, BMI, Systolic/Diastolic bp, cholesterol panel,
  Sex, Ethnicity, Free fatty acids, age, DI, SSPG, IE, Hepatic IR,
  OGTT120. **No spiker / phenotype / class column.**
- `data_metabolomics.csv`, `data_lipids.csv` — abundance matrices.

No file contains a spiker classification. To obtain "potato-spiker"
the agent must derive it from `data_cgm.csv` — compute each subject's
glycemic response per food, then decide who is a "spiker" — and the
instruction supplies no derivation method.

## The two unstated requirements

**1. The grouping method.** The rubric's gold defines the spiker
groups by a **per-food median split** (independent classifications — a
subject can be a high responder for several foods). The agent's runs
used a winner-take-all argmax (each subject → their single
highest-spiking food). Both are defensible operationalizations of
"X-spiker"; `instruction.md` states neither. The choice is not
cosmetic — argmax collapses the comparison to n ≈ 3–5 per group (the
agent's own answer notes "only 4 potato-spikers and 3 grape-spikers …
none survived FDR, top q ≈ 0.934"); the median split keeps the groups
large enough to test.

**2. The correlation analysis.** Criteria 4 and 5 require Pearson /
Spearman correlation coefficients between the top-10 lipids and the
metabolic phenotypes. The instruction asks only that lipids
"**mediate**" the differences — a mediation analysis, which the agent
performed. Correlation is a rubric-only addition.

## Side-by-side

| Aspect | Rubric expectation | Agent's output | Match |
|---|---|---|---|
| Spiker classification | per-food median split (independent) | derived from CGM, argmax/z-score | ❌ crit 1 B |
| Differential abundance | top-10 DA metabolites | computed, Welch t-test | ✅ crit 2 A |
| Top-10 reporting | with lipid class / IDs | partial ID labelling | ◐ crit 3 B |
| Lipid–phenotype link | correlation **and** mediation | mediation only ("mediate" was the ask) | ❌ crit 4 C / crit 5 B |
| Traceability / refs | real, sourced | ✅ | ✅ crit 8 A |

The differential-abundance analysis itself is sound (crit 2 = A). The
lost criteria are the grouping recipe and the correlation analysis —
both absent from the instruction.

## What this is NOT

- **Not a routing failure** — `metabolomics_analyst_pro` is the
  correct specialist and was selected.
- **Not an agent capability gap** — the agent correctly identified
  that no spiker column exists, derived groups from CGM, ran
  differential abundance (crit 2 A) and a mediation analysis, and
  honestly reported that the small derived groups yield no
  FDR-significant hits.

## What this IS

A benchmark-validity failure on two layers:

1. The task instructs the agent to "use the participant phenotypic
   classifications" and describes participants as "classified into
   spiker groups", but those classifications are in none of the
   shipped files — they must be reverse-engineered, with no method
   specified.
2. The rubric then scores against a specific derivation (per-food
   median split) and a specific extra analysis (correlation) that the
   instruction never communicates.

An agent cannot reproduce an un-stated recipe; whatever grouping it
chooses is graded against a hidden gold. This is not fixable on the
omicos side without rubric leakage.

## Note on the related skill change

`bulk-metabol-multivariate` was given a "Defining the comparison
groups" section while investigating da-8-3 (PR #112). That section was
later **de-overfit** (PR #120): it had encoded the median-split as an
absolute rule, which bent the skill toward this one task's
un-communicated gold. The retained, general guidance — derive groups
deliberately, sanity-check group sizes, report tiny-n groups as a
limitation — is valid independently of da-8-3.

## Run artifact pointers

- Runs: `runs/covered14/…/da-8-3/` (63), two `runs/smoke-*/…/da-8-3/`
  codex runs (36, 52).
- Agent trace / answer: `workspace/trace.md`, `workspace/answer.txt`
  in each run dir.
