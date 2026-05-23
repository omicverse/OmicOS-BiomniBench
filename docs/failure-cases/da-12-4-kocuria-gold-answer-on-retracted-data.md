# Failure case: da-12-4 — gold answer rests on a retracted dataset and a contaminant genus

**Task**: `da-12-4` (BiomniBench-DA / oncology / survival-analysis / medium)
**Run**: `covered14` (`runs/covered14/vertical_agent_selector/da-12-4/`)
**Score**: 73 / 100 — passing, but criterion 4 scored C (0)
**Routing**: `vertical_agent_selector` → `microbiome_analyst_pro` (correct)
**Failure class**: benchmark calibration — the gold answer is *literally*
correct under the task's recipe but *scientifically* unsupportable;
the underlying dataset's methodology was retracted.
**Severity**: high as a benchmark-validity signal — the agent's
conclusion is the scientifically correct one and the rubric penalized
it.

---

## TL;DR

da-12-4 asks whether the genus *Kocuria* is significantly associated
with poor prognosis in TCGA-LUAD. The agent ran a methodologically
sound survival analysis (matched cohort A, per-feature univariate Cox
A, dual-threshold rule A, reporting A) and concluded **"not
significant"**. The rubric expects **"significant"** (HR ≈ 1.0124,
p ≈ 0.0234) and scored criterion 4 = C (0).

The agent is right. Three independent lines of evidence say *Kocuria*
is not a real prognostic factor here, and the question itself sits on
discredited data:

1. **Statistics** — every defensible encoding the agent tried is
   non-significant; the one "significant" result does not survive the
   multiple-testing correction that 230 simultaneous taxon tests
   demand.
2. **Biology** — *Kocuria* is a skin/mucosa commensal and a recognised
   sequencing **contaminant** genus; no literature links it to lung-
   cancer prognosis.
3. **Data provenance** — the TCGA tumor-microbiome data lineage
   (Poore et al. 2020, *Nature*) was **retracted in July 2024** for
   data-analysis errors (batch / contamination / misclassified human
   reads).

The agent's only real shortcoming: it reached the right answer by
statistics alone and never cross-checked the literature, so its
trace's References section carries no biological citation for
*Kocuria* — a missed chance to make the conclusion airtight.

---

## What the task asks

`instruction.md`:

> "From lung cancer patients with matched tumor-sample microbiome and
> RNA-seq data, is Kocuria significantly associated with poor
> prognosis? … perform a univariate Cox Proportional Hazards analysis
> to each microbiome with poor prognosis (defined as a Hazard
> Ratio > 1 and p-value < 0.05)."

No abundance transformation is specified. No multiple-testing
correction is mentioned. The microbiome file `TCGA_microbiota-01A.csv`
ships **raw count** columns.

## The two readings — and why the gold one is weak

**Literal-recipe reading (the rubric's gold):** take the microbiome
column as given (raw count), fit one univariate Cox, apply the
*nominal* p < 0.05 rule. Under this exact recipe *Kocuria* hits
HR ≈ 1.0124, p ≈ 0.0234 → "Yes, significant."

**Scientifically rigorous reading (the agent's):** *Kocuria* is sparse
(non-zero in 51 / 457 matched samples, 89 % zeros, total 476 reads).
Raw counts conflate sequencing depth with abundance, so the agent
CPM-normalised + `log1p` + z-scored before Cox, and reported BH-FDR
q-values because 230 taxa were tested simultaneously. Result:
non-significant.

| Encoding | HR | p | verdict |
|---|---|---|---|
| Rubric gold (raw count) | ≈1.0124 | ≈0.0234 (nominal) | "significant" |
| Agent primary (log-relative abundance) | 1.0166 | 0.802 | not sig |
| Agent sensitivity (log raw count) | 1.0368 | 0.587 | not sig |
| Agent sensitivity (binary presence/absence) | 1.0380 | 0.592 | not sig |
| Agent BH-FDR q (any encoding) | — | ≈0.999 | not sig |

The gold's "significant" is the single outlier encoding (untransformed
raw count), it is only marginal (p just under 0.05), and it dies
under FDR correction. Three reasonable encodings agree on
non-significant — that is a robustness signal, not noise.

## Literature check (which the agent did NOT do)

A web-literature review the agent never ran:

- **Kocuria is a recognised contaminant genus.** Family
  Micrococcaceae, normal skin/mucosa flora; clinical microbiology
  routinely treats it as a "laboratory and specimen contaminant"
  (Kandi et al. 2016, *Cureus* / PMC5017880). Its da-12-4 profile —
  sparse, low-count, sporadic — is the textbook signature of a
  low-biomass sequencing contaminant, not a true intratumoral
  coloniser.
- **No LUAD prognostic literature flags Kocuria.** The intratumoral-
  microbiome–survival literature for lung adenocarcinoma names
  *Luteibacter*, *Chryseobacterium*, *Streptococcus*,
  *Pseudoalteromonas*, *Serratia*, *Methylobacterium*, … — not
  *Kocuria*. The likely source paper for this very dataset (TCGA-LUAD,
  ~478 matched patients; "Predictable regulation of survival by
  intratumoral microbe-immune crosstalk in LUAD", PMC10876218) flags
  *Luteibacter* / *Chryseobacterium*.
- **The data lineage was retracted.** The TCGA tumor-microbiome
  resource (Poore et al. 2020, *Nature*, "Microbiome analyses of
  blood and tissues …") was **retracted in July 2024** after Gihawi,
  Hill et al. showed the "cancer microbiome" signal in TCGA was
  largely batch-effect and contamination artefact ("Major data
  analysis errors invalidate cancer microbiome findings", bioRxiv
  2023.07.28.550993).

## Side-by-side

| Aspect | Rubric A-level expectation | Agent's output | Match |
|---|---|---|---|
| Matched cohort | 457 samples, 173 events | 457 samples, 173 events | ✅ crit 1 A |
| Per-feature univariate Cox | one Cox per taxon | 230 taxa modelled | ✅ crit 2 A |
| Dual-threshold poor-prognosis rule | HR>1 ∧ p<0.05 | applied; 12 nominal hits | ✅ crit 3 A |
| Reporting | top hits + cohort stats | full | ✅ crit 5 A |
| **Kocuria verdict** | **"significant" (raw-count nominal p≈0.0234)** | **"not significant" (3 encodings + FDR)** | ❌ crit 4 C |

Every criterion except 4 is A. The single lost criterion is the
*Kocuria*-specific conclusion, lost purely because the agent did the
more rigorous analysis.

## What this is NOT

- **Not an agent capability gap** — the survival analysis is
  textbook-correct (cohort matching, per-feature Cox, FDR,
  three-encoding robustness check all A-grade).
- **Not a routing failure** — `microbiome_analyst_pro` is the right
  specialist and was selected.
- **Not a borderline-noise coin-flip** — the agent's p ≈ 0.80 vs the
  gold's p ≈ 0.0234 differ ~30×; the disagreement is structural
  (abundance transformation), not a near-0.05 wobble.

## What this IS

A **benchmark-validity** failure on two layers:

1. The gold answer is the *literal* output of an under-specified
   recipe (raw count, nominal p, no FDR) — defensible only as
   "what the task literally said", not as a scientific claim.
2. The recipe is applied to a dataset whose methodology was
   formally retracted, on a genus with no biological prior and the
   profile of a contaminant.

The agent's conclusion is the scientifically correct one.

## The one genuine agent lesson

The agent reached the right answer by statistics alone. Its trace's
References section cites only methods (Cox 1972, Benjamini-Hochberg
1995, lifelines, TCGA-LUAD) — **zero biological citations for
Kocuria**, despite `instruction.md` explicitly requiring "References:
real citations for biological mechanisms invoked **and any external
knowledge used**".

Had the agent done a literature sanity-check (Kocuria is a contaminant
genus; no LUAD prognostic prior; the data lineage was retracted) it
could have written a citation-backed, far stronger conclusion instead
of a bare statistical one. Generalisable lesson for the catalog:
**when a statistical result is the deliverable — especially when it
conflicts with or lacks a biological prior — cross-check it against
the literature and cite the check.**

## Run artifact pointers

- Run dir: `runs/covered14/vertical_agent_selector/da-12-4/`
- Agent trace: `runs/.../da-12-4/workspace/trace.md`
- Agent answer: `runs/.../da-12-4/workspace/answer.txt`
- Grade: `reports/covered14/matrix.csv`

## Sources

- Kandi V. et al. 2016. Emerging Bacterial Infection: Identification
  and Clinical Significance of *Kocuria* Species. *Cureus*. PMC5017880.
- Poore G.D. et al. 2020. Microbiome analyses of blood and tissues
  suggest cancer diagnostic approach. *Nature*. PMC7500457.
  **Retracted July 2024.**
- Gihawi A., Hill C. et al. 2023. Major data analysis errors
  invalidate cancer microbiome findings. bioRxiv 2023.07.28.550993.
- "Predictable regulation of survival by intratumoral microbe-immune
  crosstalk in patients with lung adenocarcinoma." PMC10876218.
