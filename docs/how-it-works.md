# How Syxplain works

Syxplain takes a table of measurements, a target column and a short description of the
problem, and returns interpretable equations for the target. Each equation comes with
evidence for and against it, how it relates to known scientific laws, and a
plain-language explanation.

The pipeline combines an LLM agent (reasoning, planning, explanation) with numerical
tools (symbolic regression, least-squares fitting, cross-validation, SHAP, SINDy). The
rule throughout is that **code decides, the LLM proposes and explains**:
- Which model is the headline, how well it fits, and whether the evidence agrees are
  all computed.
- The LLM chooses what to try next and puts the results into words.

```mermaid
flowchart LR
    A[Upload data<br/>+ problem description] --> B[Profiling<br/>noise ceiling, SHAP]
    A --> P[Baseline PySR search<br/>starts immediately]
    A -.-> L[Literature scout<br/>runs in background]
    B --> C[Blind exploration<br/>agent + PySR + SINDy]
    P --> C
    C --> R[Relate to known laws]
    L -.-> R
    R --> S[Model selection<br/>CV, holdout, SHAP check]
    S --> K[Coherence verdict]
    K --> E[Explanation<br/>LLM]
```

## 1. Baseline search

Before any reasoning starts, a baseline PySR search is submitted:
- it uses all continuous features
- an LLM chooses the operators from the feature plots

It starts first so that the compute queue wait overlaps with the agent's work.

Integer-coded categories (soil type codes and the like) are never used as magnitudes, only
as `level(x, k)` indicators.

## 2. Profiling

The agent profiles the data with:
- correlations and mutual information
- random-forest permutation importance
- a **noise ceiling**: the out-of-fold random-forest R², roughly the best accuracy any
  model can reach on this data
- **SHAP** on that forest: feature importance, interacting feature pairs (candidates
  for product terms and multiplicative laws), and each feature's partial-effect shape
  with the other features accounted for

SHAP plots are shown to the agent as images: a summary plot and dependence plots of the
top features, coloured by their interaction partner. From these the agent can read
plateaus, bends and outliers directly, without relying on a shape label.

`DISCOVERY_SHAP_IMAGES=false` gives the agent text SHAP only.

SHAP runs in the backend in seconds (rows, trees and the interaction sample are capped).

## 3. Blind exploration

**Exploration is blind to known laws**, so existing knowledge does not bias the search:
- the agent has no access to the classic law catalog or the literature
- shape labels name no model family

The agent designs its own formulas from the shapes and interactions it sees. Every
candidate is fitted the same way, and comes back with **diagnosed reasons it falls
short**:
- wrong curve shape, and where
- a missing variable, and which one
- variance growing with the value
- unidentifiable parameters
- "matches the noise ceiling"

Guided by those reasons, the agent launches **targeted PySR searches**. For each one it
chooses:
- the feature subset
- the operators
- the target transform
- warm-start guesses: its best formulas so far, or, when it has none, the strongest SHAP
  interaction as `c0 + c1*a*b` and `c0 + c1*a/b`

It compares the results with its own formulas.

It records its findings in a **lab notebook** (rejected forms with reasons, insights,
data issues), which the explanation step reads.

### Time-ordered data

When the rows are measurements along time, the run detects the time structure. The
agent can confirm or override the detection.

**Long series along time** (annual GPP, monthly groundwater levels; at least 20 points
per series) get a feature stage before the first PySR search. The measurements need not be
evenly spaced: the step is the typical distance between measurements, and a value "K steps
earlier" is read between the two measurements around that moment when they are close
together (a long gap gives a missing value). It covers the case where the target depends
on earlier conditions as well as current ones.

By default the features come from the orders of an automatic ARIMA search (`auto_arima`,
with the current features as regressors) on the training rows:
- orders p and d (and one season earlier for a seasonal fit) name the target's earlier
  values;
- order q names the earlier errors of that fit. An error is the measured value minus the
  value predicted one step ahead from earlier measurements, so it is known before the row
  it is used on.

The ARIMA model itself is never a candidate equation; symbolic regression decides which
of the features an equation uses.

`DISCOVERY_SERIES_FEATURES` selects the source. With `llm`, an LLM proposes lags and
aggregates over earlier periods of any column, code computes and measures them, and an LLM
selects at most a handful. With `both`, the LLM is also shown the orders and what the fit
leaves open (memory at longer distances, memory left in the errors, signs of nonlinear
dynamics, as numbers and as a picture), adds features the fit cannot give, and writes a
short note for the agent that steers the searches.

For series, the holdout is **chronological**. A random split would let every held-out
step sit between training steps, which measures interpolation rather than prediction
forward in time.

**Rate laws** (how a state changes, `d(target)/dt = f(state, inputs)`) are searched with
**SINDy**:
- sparse regression over a library of named terms, swept from the simplest law to the
  fullest
- each law is integrated from every trajectory's start, because a law that fits the
  derivatives can still drift or blow up
- SINDy takes seconds and runs in the backend

## 4. Relation to known laws

Only after exploration are the discoveries compared with existing knowledge, from two
sources:
- **Classic named laws**, screened on the variables the discoveries use: Mitscherlich,
  Michaelis-Menten/Langmuir, Freundlich/power, logistic, Gompertz,
  linear/quadratic-plateau, Gaussian peak, Mitscherlich-Baule, Cobb-Douglas, and others.
- **Published laws**, collected by a literature scout. The scout runs in the background
  from the start of the run, using the main model with web search. It writes the laws
  solved for the target, and they are fitted with the published constants as starting
  values. The agent never sees them.

Code compares each discovered equation with each known law through their predictions.
The relation is one of:

| Relation | Meaning |
|---|---|
| **equivalent** | The same law in another algebraic form, i.e. a rediscovery |
| **similar** | The predictions agree closely |
| **partial** | The law describes some of the variables; the discovery adds the others |
| **different** | A new relationship |

Code also records whether the law fits better, as well, or worse than the discovery,
beyond noise.

## 5. Model selection

**Code, not an LLM, picks the headline model** among the discovered equations:
1. Models are ranked by 5-fold cross-validation on the training rows.
2. They are checked by guards.
3. The simplest model within one standard error of the best wins.

Known laws are references. One becomes the headline only when no discovered equation is
usable.

The 20% holdout is scored once, at the end. Datasets under 40 rows use cross-validation
only.

The headline equation is then **checked against SHAP**. For each important feature, the
check asks whether the equation's effect follows the forest's SHAP effect:
- agrees
- disagrees
- opposite
- the feature is ignored

Misses are reported as limitations.

## 6. Coherence

The results page asks whether the independent lines of evidence agree on the headline.
Code checks it against:
- the noise ceiling
- the holdout (generalization gap)
- the SHAP effects
- the published and named laws: a known law that fits better than the discovery is a
  caution; a rediscovered law agrees
- its own parameters: are they determined by the data, and defined on every row?
- the agent's conclusion

Each check comes out as agrees, caution or conflict, and the worst one is the overall
verdict.

## 7. Explanation

The explanation LLM writes the report:
- what the headline equation says
- how it relates to known laws
- its limitations

It also adds what code cannot judge: whether each effect direction and the limiting
behaviour are plausible in the domain. It may not override the computed checks.

## Budgets and failure handling

The agent is bounded by a budget (`DISCOVERY_*` settings, see
[configuration.md](configuration.md)). These are ceilings; the agent stops earlier when
it is done.

If the agent fails, the run still finishes with the baseline search, compared with the
known laws as usual.

## Cost per analysis

Every LLM call of a run is counted and priced:
- tokens per model, including cached and reasoning tokens
- web searches

Each run logs one line and stores the same summary under `results.usage`:

```bash
docker logs syxplain-backend 2>&1 | grep "ANALYTICS run_usage"
# ANALYTICS run_usage {"run_id":"...","outcome":"completed","models":{"gpt-4o":{"calls":17,...,"cost_usd":0.41}},"total_cost_usd":0.41,...}
```

Prices for OpenAI models are built in. Other models are priced with `LLM_PRICES_JSON`.

## Where things live

| Step | Code |
|---|---|
| Pipeline orchestration | `backend/services/orchestrator_service.py` |
| Agent and its tools | `backend/services/discovery/agent.py`, `tools.py`, `session.py` |
| Fitting, CV, diagnostics | `backend/services/discovery/fitting.py`, `selection.py` |
| Profiling and SHAP | `backend/services/discovery/profiling.py` |
| Time series, features, SINDy | `series.py`, `features.py`, `feature_stage.py`, `temporal.py`, `sindy.py` |
| Known laws | `families.py`, `literature.py`, `relate.py` |
| Headline, coherence | `report.py`, `coherence.py` |
| LLM prompts (DSPy signatures) | `backend/infrastructure/llm/signatures.py` |
| PySR worker | `slurm_worker/tasks/pysr_task.py` |
