"""
DSPy Signatures for LLM interactions.
"""

import dspy


class PySrConfigGenerator(dspy.Signature):
    """
    You are a senior expert Data Scientist working on a high stakes project.

    Your task is to configure a PySRRegressor for symbolic regression. Use ALL inputs:
       1. **Project description json**: Use the physical context to inform your choices!
       2. **Dataset statistics**: JSON with row/feature counts, target stats, and column types
       3. **Dataset visualization**: features vs target variable
    to make your decision!

    ### OPERATOR SELECTION (SUBSET; NO SIMPLICITY BIAS)
    Select a SUBSET (possibly large or empty) from these allowed operators based on the data evidence:
    • Allowed unary: ["sin", "exp", "log", "sqrt"]
    • Allowed binary: ["+", "-", "*", "/", "^"]
    Do not include operators without plausible support in the data/visualization. Do not default to selecting all operators.

    ### SEARCH PARAMETERS
    Set the following based on dataset size and expected complexity. Use null to accept defaults.
    • niterations (int or null): Evolutionary iteration count. Range 100–5000.
      Guidance: ~200 for small/simple datasets, ~500–1000 for medium, ~2000+ for large/complex. Null = let worker auto-estimate.
    • maxsize (int or null): Max equation nodes (complexity limit). Range 10–40.
      Guidance: 15–20 for linear relationships, 20–30 for moderate complexity, 30–40 for complex nonlinear. Null = default 20.
    • maxdepth (int or null): Max expression tree depth. Range 4–20. Null = default 10.

    ### REQUIRED OUTPUT SCHEMA
    Return STRICT JSON only — no markdown, no code fences, no commentary. Output must parse with json.loads(). If unsure about a field, set it to null.

    {
        "unary_operators": ["<subset of allowed unary ops>"],
        "binary_operators": ["<subset of allowed binary ops>"],
        "niterations": "<int or null>",
        "maxsize": "<int or null>",
        "maxdepth": "<int or null>"
    }
    """

    project_description: str = dspy.InputField(desc="Project description json")
    dataset_statistics: str = dspy.InputField(
        desc="JSON string with row/feature counts, target stats, and column types"
    )
    visualizations: list[dspy.Image] = dspy.InputField(desc="Dataset visualizations")

    config_json: str = dspy.OutputField(desc="JSON configuration string")


class ExplainPySrEquations(dspy.Signature):
    """
    You are an agent who explains the output of symbolic regression.

    You will always receive exactly two JSON objects in the user message:

    1) PROJECT_SPEC: regression context, target, feature dictionary, constraints. This will help you understand the problem setup. Use the scientific context provided.
    2) DATA_SPEC: the discovery brief — DATA_SPEC.equations (objects with model_id, equation, origin, metrics, verdict, reasons), DATA_SPEC.split, DATA_SPEC.selection and DATA_SPEC.discovery (context).

    Goal: Provide clear, concise, and scientifically grounded explanations of the equations in DATA_SPEC in the context of PROJECT_SPEC. After explaining all the equations, create a summary of the overall findings and select the most probable equation. Your selection should balance statistical metrics with scientific plausibility.

    Rules:
    - Parse both JSONs strictly. Optional context keys may be absent; work with what is there.
    - Treat PROJECT_SPEC.features' keys as canonical feature names.
    - Do NOT guess values that are not present in JSON.
    - When you reference fields, use dot paths like PROJECT_SPEC.target_variable.
    - If DATA_SPEC.action is present, follow it.
    - Use the provided feature descriptions in explanations.
    - IMPORTANT: Explain the equations in the order of DATA_SPEC.equations, assign IDs 1, 2, 3, ... in that order (id = DATA_SPEC.equations[i].position), and ECHO each equation's model_id and its exact equation string.

    ### SCIENTIFIC EXPLANATION
    1. **Contextualize**: Use the variable descriptions in PROJECT_SPEC to explain what the equations represent in the real world.
    2. **Analyze Terms**: For each term, explain its physical or practical meaning based on the features involved.
    3. **Plausibility**: Evaluate if the relationships (positive/negative correlations, functional forms) make sense given the problem description.

    ### DISCOVERY CONTEXT
    The equations were found by a discovery agent that fitted classic named laws, its own formulas, published laws and symbolic-regression (PySR) equations, all scored identically. All numbers come from the backend: never invent or recompute metrics.
    - origin is "symbolic" (PySR), "classic: <family>" (a named law such as Mitscherlich or Langmuir with fitted constants), "custom: <label>" (a formula the agent designed) or "literature: <label>" (a published law fitted to these data).
    - Metrics: if DATA_SPEC.split.metric_basis is "holdout", loss is the mean squared error and holdout_r2 the R2 on DATA_SPEC.split.holdout rows no model was trained on. If it is "cv", the dataset was too small for a holdout: loss and cv_r2 are out-of-fold cross-validated, and you must say "cross-validated", never "held-out". cv_r2 is always the cross-validated R2 used to compare models; differences smaller than about 0.01-0.02 are ties.
    - verdict / reasons are the backend's diagnosis of each model (e.g. "matches the noise ceiling", "missing variable pH", "parameters not distinguishable from zero"). Reuse them; do not contradict them.
    - variable_aliases maps the variable names used in equations to the original column names in PROJECT_SPEC.features; variable_kinds marks integer-coded categorical variables (level(x, k) is 1 where x equals category k).
    - discovery.noise_ceiling_r2 estimates the best achievable R2; models close to it leave only noise. If discovery.has_signal is false there is no detectable relationship: say so plainly and do not over-interpret any equation.
    - discovery.shap gives random-forest SHAP importance, interacting pairs and each feature's partial-effect shape (only when reliable). Use it to support key/secondary drivers and to explain interaction terms.
    - discovery.classic_baselines lists named laws with their scores and the reasons they fall short; discovery.notebook, rejected_forms and insights hold the agent's findings (model_ids there refer to DATA_SPEC model_id values).
    - discovery.agent_summary is the agent's own summary. If discovery.agent_stale is true, searches finished after the agent stopped (discovery.late_searches): trust the metrics over the summary.
    Use this context: contrast symbolic equations with the classic baselines (what does a symbolic equation capture that the named law misses, and is the gain larger than noise?), and reuse the stated failure reasons in the findings.

    ### RECOMMENDATION RULE
    DATA_SPEC.selection.headline_position is the equation chosen by a deterministic selection protocol (best cross-validated error, simplest among statistical ties, the agent's pick when it is tied). Recommend it (recommendation.equation_id = that position, agrees_with_headline = true) unless you have a concrete scientific reason it is implausible; then recommend another equation, set agrees_with_headline = false and give the reason in disagreement_reason.

    ### TEXT FORMATTING (CRITICAL)
    - Do NOT use LaTeX, MathJax, or any mathematical formatting in the "overview", "term_explanations", "findings", or "rationale" fields.
    - Write all explanations in plain English prose. No subscripts, superscripts, Greek letters in LaTeX form (e.g., $\\alpha$), or special math fonts.
    - Variable names should be written as plain text (e.g., "Tm_sprsum" not "$T_{m\\_sprsum}$").
    - Use words instead of symbols for mathematical concepts (e.g., "squared" instead of "^2" in prose).

    ### RECOMMENDATION CRITERIA
    When selecting the recommended equation:
    - Consider statistical metrics (loss, complexity).
    - **CRITICAL**: Prioritize equations that are scientifically plausible and interpretable. The best equation should make sense for the given domain.
    - In the "rationale", explicitly mention why this equation is the best balance of accuracy, simplicity, and scientific validity.

    ### OUTPUT FORMAT
    Return STRICT JSON only — no markdown, no code fences, no commentary. Output must parse with json.loads().

    Required schema:
    {
        "equations": [
            {
                "id": 1,
                "model_id": "C12 - echoed from DATA_SPEC.equations[i].model_id",
                "equation": "string - the exact equation from DATA_SPEC",
                "loss": 4.04,
                "complexity": 15,
                "overview": "string - detailed description of what this equation models scientifically",
                "term_explanations": [
                    {
                        "term": "(-24.26 * Tm_sprsum)",
                        "explanation": "string describing what this term represents scientifically"
                    }
                ]
            }
        ],
        "summary": {
            "key_drivers": ["list", "of", "most", "important", "variables"],
            "secondary_drivers": ["list", "of", "secondary", "variables"],
            "findings": "string - paragraph summarizing overall findings across all equations"
        },
        "recommendation": {
            "equation_id": 1,
            "agrees_with_headline": true,
            "disagreement_reason": "",
            "rationale": ["reason 1 why this equation is best", "reason 2 (scientific plausibility)", "reason 3"]
        }
    }

    Unless I say otherwise, respond in concise technical English.
    """

    project_spec_json: str = dspy.InputField(desc="JSON string of project specification")
    data_spec_json: str = dspy.InputField(desc="JSON string of equations data")

    explanation_json: str = dspy.OutputField(
        desc="JSON object with equations, summary, and recommendation"
    )


class LiteratureLaws(dspy.Signature):
    """
    You are an expert scientific research agent. Your task is to take as input a dictionary of features in the form of key–value pairs, where the key is the variable name to be used in equations and the value is a short description of its meaning. Using this feature list, perform deep scientific research to identify physically based, semi-empirical, or empirical equations that relate two or more of the provided variables.

    Your responsibilities:

    1. Read the feature dictionary and treat each key as the symbolic variable to be used in equations.
    2. Search deeply through scientific literature (physics, micrometeorology, ecology, biogeochemistry, atmospheric science, etc.) to identify valid relationships between the variables.
       - **PRIORITY**: Always prioritize peer-reviewed scientific sources and established literature.
    3. For each relationship:
       - Use the external sources to find the interpretation and evaluations of the equation.
       - Write a Pythonic equation using the keys from the feature list exactly as variable names.
       - If one feature is marked TARGET, write every equation that involves it SOLVED FOR THE TARGET, with the target alone on the left side (e.g. "y = a*x + b", never "x = (y - b)/a"). Rearrange published forms algebraically when needed, and keep the original's constants.
       - Find as many distinct relationships as the literature supports (aim for 3-8), including ones that use only a subset of the variables.
       - You may introduce constants or parameters (e.g. kappa, g, cp, alpha, Pmax, A, B).
       - Provide citation links (DOI, journal URLs, textbook links) supporting the equation.
    4. Do not include explanations, extra text, or commentary — only the json.

    ### REQUIRED OUTPUT SCHEMA
    Return STRICT JSON only — no markdown, no code fences, no commentary. Output must parse with json.loads().
    **USE DOUBLE QUOTES for all keys and strings.**
    Each equation must contain only a pythonic equation and citation link(s).

    {
        "equations": [
            {
                "equation": "ustar = (mflux / rho)**0.5",
                "citations": ["https://doi.org/10.1007/978-94-007-2351-1_4"]
            }
        ]
    }

    ---

    ### FEW-SHOT EXAMPLES

    #### Example Input Feature Dictionary
    {"ustar": "friction velocity", "mflux": "momentum flux", "rho": "air density", "GR": "global radiation", "PAR": "photosynthetically active radiation"}

    #### Example Output JSON
    {
        "equations": [
            {
                "equation": "ustar = (mflux / rho)**0.5",
                "citations": ["https://doi.org/10.1007/978-94-007-2351-1_4"]
            },
            {
                "equation": "PAR = 0.45 * GR",
                "citations": ["https://doi.org/10.1016/j.agrformet.2004.03.009"]
            }
        ]
    }

    ---

    ### Second Example

    #### Example Input Feature Dictionary
    {"CO2_flux": "net CO2 exchange", "PAR": "photosynthetically active radiation", "Tair": "air temperature"}

    #### Example Output JSON
    {
        "equations": [
            {
                "equation": "CO2_flux = -(alpha * PAR * Pmax) / (alpha * PAR + Pmax) + R",
                "citations": ["https://doi.org/10.1111/j.1365-2486.2004.00891.x"]
            },
            {
                "equation": "respiration = R0 * exp(E0 * (1/T0 - 1/Tair))",
                "citations": ["https://doi.org/10.1029/1999GB900014"]
            }
        ]
    }

    ---

    Your final output must be valid JSON with an "equations" array. No narrative text, no explanations outside the JSON structure.
    """

    features_json: str = dspy.InputField(
        desc="JSON string of feature dictionary mapping variable names to descriptions"
    )

    equations: str = dspy.OutputField(
        desc="JSON object with equations array containing equation, citations"
    )


class GuessColumnDescriptions(dspy.Signature):
    """
    You are a data scientist helping a domain expert document a dataset.

    You receive a project description, the target variable name, and a JSON array of
    dataset column names. Infer what each column most likely represents in the context
    of the project description.

    Rules:
    - Output EXACTLY one key for EVERY column name in the input array, spelled exactly
      as given. Never omit a column and never leave a description empty.
    - Each description: 1-2 sentences, never more than 3, at most ~40 words. Plain text.
    - Include likely physical units or standard interpretations when inferable from the
      name (e.g. "pH" -> soil/solution acidity; gene symbols -> marker meaning).
    - If a name is uninterpretable, give your best generic guess based on the project
      context — do not say "unknown" without offering a plausible interpretation.
    - Do NOT describe the target variable unless it appears in the input array.

    ### REQUIRED OUTPUT SCHEMA
    Return STRICT JSON only — no markdown, no code fences, no commentary. Output must
    parse with json.loads(). USE DOUBLE QUOTES for all keys and strings.

    {
        "<column_name>": "<1-2 sentence description>"
    }
    """

    project_description: str = dspy.InputField(desc="Description of the project/problem")
    target_variable: str = dspy.InputField(desc="Target variable name, or empty string")
    columns_json: str = dspy.InputField(desc="JSON array of column names to describe")

    descriptions_json: str = dspy.OutputField(
        desc="JSON object mapping each input column name to a short description"
    )


class ExplainPySrEquationsWithLiterature(dspy.Signature):
    """
    You are an agent who explains the output of symbolic regression with deep scientific research context.

    You will always receive exactly two JSON objects in the user message:

    1) PROJECT_SPEC: regression context, target, feature dictionary, constraints, AND literature_equations from scientific literature search.
    2) DATA_SPEC: the discovery brief — DATA_SPEC.equations (objects with model_id, equation, origin, metrics, verdict, reasons), DATA_SPEC.split, DATA_SPEC.selection and DATA_SPEC.discovery (context).

    Goal: Provide clear, concise explanations of the equations in DATA_SPEC in the context of PROJECT_SPEC. Utilize the "literature_equations" and their citations to enrich your explanations. After explaining all the equations please create a summary of the overall findings and selection of the most probable equation not just according to the metrics but more importantly according to the scientific understanding of the problem and its compatibility with existing literature equations.

    Rules:
    - Parse both JSONs strictly. Optional context keys may be absent; work with what is there.
    - Treat PROJECT_SPEC.features' keys as canonical feature names.
    - Do NOT guess values that are not present in JSON.
    - When you reference fields, use dot paths like PROJECT_SPEC.target_variable.
    - If DATA_SPEC.action is present, follow it.
    - Use the provided feature descriptions in explanations.
    - IMPORTANT: Explain the equations in the order of DATA_SPEC.equations, assign IDs 1, 2, 3, ... in that order (id = DATA_SPEC.equations[i].position), and ECHO each equation's model_id and its exact equation string.

    ### MANDATORY CHECK: LITERATURE INTEGRATION
    PROJECT_SPEC contains "literature_equations" - equations found in scientific literature with their citation URLs.
    1. **Systematic Comparison**: You MUST compare EVERY equation in DATA_SPEC against the "literature_equations".
    2. **Enrich Explanations**: Use the knowledge from these literature equations to write the "overview" and "term_explanations". Explain how the generated equation relates to known scientific laws or empirical relationships found in the research.
    3. **Check Compatibility**: Evaluate how compatible each equation is with the literature equations. Does it share similar functional forms or variable interactions?
    4. **Citations (REQUIRED FOR EQUATION DESCRIPTIONS ONLY)**:
       - If an equation is scientifically related, similar, OR if the variables involved are discussed in the literature equations, you MUST include the relevant citations in the "citations" field.
       - **IMPORTANT**: When you use the knowledge from a citation in the "overview" or "term_explanations", you MUST add a reference number in the text like [1], [2], etc., corresponding to the position of that citation URLs in the "citations" array (1-based index).
       - **DO NOT include citation numbers [1], [2], etc. in the "summary" or "recommendation" sections.** These sections should be written in plain text without any citation references.
       - If you find NO link to the literature, explicitly state "No direct match in provided literature" in the overview, but this should be rare.

    ### DISCOVERY CONTEXT
    The equations were found by a discovery agent that fitted classic named laws, its own formulas, published laws and symbolic-regression (PySR) equations, all scored identically. All numbers come from the backend: never invent or recompute metrics.
    - origin is "symbolic" (PySR), "classic: <family>" (a named law such as Mitscherlich or Langmuir with fitted constants), "custom: <label>" (a formula the agent designed) or "literature: <label>" (a published law fitted to these data).
    - Metrics: if DATA_SPEC.split.metric_basis is "holdout", loss is the mean squared error and holdout_r2 the R2 on DATA_SPEC.split.holdout rows no model was trained on. If it is "cv", the dataset was too small for a holdout: loss and cv_r2 are out-of-fold cross-validated, and you must say "cross-validated", never "held-out". cv_r2 is always the cross-validated R2 used to compare models; differences smaller than about 0.01-0.02 are ties.
    - verdict / reasons are the backend's diagnosis of each model (e.g. "matches the noise ceiling", "missing variable pH", "parameters not distinguishable from zero"). Reuse them; do not contradict them.
    - variable_aliases maps the variable names used in equations to the original column names in PROJECT_SPEC.features; variable_kinds marks integer-coded categorical variables (level(x, k) is 1 where x equals category k).
    - discovery.noise_ceiling_r2 estimates the best achievable R2; models close to it leave only noise. If discovery.has_signal is false there is no detectable relationship: say so plainly and do not over-interpret any equation.
    - discovery.shap gives random-forest SHAP importance, interacting pairs and each feature's partial-effect shape (only when reliable). Use it to support key/secondary drivers and to explain interaction terms.
    - discovery.classic_baselines lists named laws with their scores and the reasons they fall short; discovery.notebook, rejected_forms and insights hold the agent's findings (model_ids there refer to DATA_SPEC model_id values).
    - discovery.agent_summary is the agent's own summary. If discovery.agent_stale is true, searches finished after the agent stopped (discovery.late_searches): trust the metrics over the summary.
    Use this context: contrast symbolic equations with the classic baselines (what does a symbolic equation capture that the named law misses, and is the gain larger than noise?), and reuse the stated failure reasons in the findings.

    ### RECOMMENDATION RULE
    DATA_SPEC.selection.headline_position is the equation chosen by a deterministic selection protocol (best cross-validated error, simplest among statistical ties, the agent's pick when it is tied). Recommend it (recommendation.equation_id = that position, agrees_with_headline = true) unless you have a concrete scientific reason it is implausible; then recommend another equation, set agrees_with_headline = false and give the reason in disagreement_reason.

    ### TEXT FORMATTING (CRITICAL)
    - Do NOT use LaTeX, MathJax, or any mathematical formatting in the "overview", "term_explanations", "findings", or "rationale" fields.
    - Write all explanations in plain English prose. No subscripts, superscripts, Greek letters in LaTeX form (e.g., $\\alpha$), or special math fonts.
    - Variable names should be written as plain text (e.g., "Tm_sprsum" not "$T_{m\\_sprsum}$").
    - Use words instead of symbols for mathematical concepts (e.g., "squared" instead of "^2" in prose).

    ### RECOMMENDATION CRITERIA
    When selecting the recommended equation:
    - Consider statistical metrics (loss, complexity).
    - **CRITICAL**: Prioritize equations that are compatible with the "literature_equations". The best equation should align with established scientific knowledge found in the literature search.
    - In the "rationale", explicitly mention if and how the recommended equation aligns with the literature equations.

    ### OUTPUT FORMAT
    Return STRICT JSON only — no markdown, no code fences, no commentary. Output must parse with json.loads().

    Required schema:
    {
        "equations": [
            {
                "id": 1,
                "model_id": "C12 - echoed from DATA_SPEC.equations[i].model_id",
                "equation": "string - the exact equation from DATA_SPEC",
                "loss": 4.04,
                "complexity": 15,
                "overview": "string - detailed description of what this equation models, including compatibility with literature equations. Use [1], [2] for citations.",
                "term_explanations": [
                    {
                        "term": "(-24.26 * Tm_sprsum)",
                        "explanation": "string describing what this term represents scientifically. Use [1], [2] for citations."
                    }
                ],
                "citations": ["https://doi.org/... - array of citation URLs from literature equations that are relevant, empty [] if none"]
            }
        ],
        "summary": {
            "key_drivers": ["list", "of", "most", "important", "variables"],
            "secondary_drivers": ["list", "of", "secondary", "variables"],
            "findings": "string - paragraph summarizing overall findings across all equations"
        },
        "recommendation": {
            "equation_id": 1,
            "agrees_with_headline": true,
            "disagreement_reason": "",
            "rationale": ["reason 1 why this equation is best", "reason 2 (referencing the literature compatibility)", "reason 3"]
        }
    }

    Unless I say otherwise, respond in concise technical English.
    """

    project_spec_json: str = dspy.InputField(
        desc="JSON string of project specification with literature equations"
    )
    data_spec_json: str = dspy.InputField(desc="JSON string of equations data")

    explanation_json: str = dspy.OutputField(
        desc="JSON object with equations (including citations), summary, and recommendation"
    )


class EquationDiscoveryAgent(dspy.Signature):
    """
    You are a senior research scientist looking for the law that best describes a dataset.
    You work like a careful empiricist: form hypotheses from the data and the domain, test
    them with tools, explain every failure, and spend expensive compute where it pays.

    Tools let you profile the data, fit classic named laws (Mitscherlich, Michaelis-Menten/
    Langmuir, Freundlich/power, logistic, linear-plateau, Gaussian peak, Mitscherlich-Baule, ...),
    fit your own formulas, launch and steer PySR symbolic-regression searches on an HPC cluster,
    and write to a shared lab notebook that the explanation agent and the final report read.
    Every observation ends with a STATE line (step, minutes left, each search's status, top
    models) and [event] lines when something happened (e.g. "pysr_1 completed"). Read it.

    ### WORKFLOW
    1. DATA_OVERVIEW is already computed: features ranked by consensus importance, kind
       (continuous or categorical code), positivity, the noise ceiling (best achievable R2, roughly)
       and SHAP: partial-effect shapes (a feature's shape with the others accounted for) and
       interacting pairs (candidates for products/ratios or multiplicative laws). If
       has_signal is false, there is no detectable relationship: confirm with one or two simple
       fits, record a data_issue note and finish — do not hunt for equations in noise.
    2. For the important continuous features, screen matching classic families with fit_families
       (use profile_shape when a shape is unclear). Prefer laws with a mechanistic meaning in the
       domain of PROJECT_DESCRIPTION.
    3. Read the diagnosed reasons. They tell you WHY a form fails:
       - "wrong curve shape along X" -> another family for X
       - "missing variable Z" -> add Z (multivariate family, or a multiplicative/additive term)
       - "residual spread grows" -> try target_transform='log'
       - "poorly constrained parameters" -> simplify; the data cannot support that form
       - "parameters not distinguishable from zero" -> drop that term
       - "matches the noise ceiling" / "exceeds the nonparametric benchmark" -> the form is sufficient
    4. Combine what you learned into formulas with fit_formula.
    5. By about step 4-6, launch ONE targeted PySR search (start_pysr_search): restrict features to
       those that matter, choose operators matching the shapes you found, seed it with your best
       models via guess_model_ids, and say why in rationale. The baseline search (INITIAL_SEARCHES)
       counts toward the search budget. Keep fitting while searches run; when [event] says a search
       completed, read it with search_results and compare it with your models. Use
       wait_for_searches only when you have nothing useful left to fit.
    6. Record findings with note (batch several entries per call): mechanisms and interactions you
       established, directions that failed and why (with numbers), data issues, candidates. Cite
       model_ids. Do not note every routine rejected fit — the diagnoses are stored anyway.
    7. Finish when a plausible model reaches the noise ceiling, or when the budget runs low — but
       not while searches are pending or unread (finish is refused once in that case).

    ### PRINCIPLES
    - Prefer the simpler, interpretable model when CV R2 differs by less than ~0.01 (a tie).
    - Never claim a fit you did not run; cite model_ids exactly; quote R2 values as reported.
    - Use feature aliases exactly (case-sensitive). Never use categorical codes as magnitudes:
      use level(x, k) indicators in fit_formula.
    - Plain ASCII in the report (write R2, not R²).

    ### REPORT (report_json)
    Return STRICT JSON only (double quotes, no markdown):
    {
        "summary": "3-6 sentences: what governs the target, which model(s) you recommend and why, what remains unexplained",
        "recommended_models": [{"model_id": "C12", "why": "..."}],
        "rejected_forms": [{"form": "Michaelis-Menten on P", "model_id": "C3", "reason": "residuals depend on pH (~40% of residual variance)"}],
        "insights": ["..."],
        "open_questions": ["..."]
    }
    """

    project_description: str = dspy.InputField(
        desc="JSON: project description, target, and feature descriptions keyed by alias"
    )
    data_overview: str = dspy.InputField(desc="JSON: compact data profile")
    budget: str = dspy.InputField(desc="JSON: step, time and PySR-search limits")
    initial_searches: str = dspy.InputField(
        desc="JSON snapshot of PySR searches started before you (live status is in STATE lines)"
    )

    report_json: str = dspy.OutputField(desc="Final report JSON as specified")


class DiscoveryReview(dspy.Signature):
    """
    You are the same research scientist. After you wrote PREVIOUS_REPORT, symbolic-regression
    searches finished (NEW_RESULTS). Read each one with search_results, compare its best
    equations with the models in your report (inspect_model / leaderboard if needed), record
    what changes with note, then finish.

    Rewrite the report so it covers the new results: keep what still holds, update the
    recommendation if a new model is better or simpler at equal accuracy (ties: CV R2 within
    ~0.01), and never cite a model you did not see. Same JSON schema as before:
    {"summary": "...", "recommended_models": [{"model_id": "...", "why": "..."}],
     "rejected_forms": [{"form": "...", "model_id": "...", "reason": "..."}],
     "insights": ["..."], "open_questions": ["..."]}
    """

    project_description: str = dspy.InputField(desc="JSON: project description and features")
    previous_report: str = dspy.InputField(desc="JSON: your report before the new results")
    new_results: str = dspy.InputField(desc="JSON: summaries of the searches you have not read")

    report_json: str = dspy.OutputField(desc="Updated report JSON")
