"""
DSPy Signatures for LLM interactions.
"""
from typing import List
import dspy


class PySrConfigGenerator(dspy.Signature):
    """
    You are a senior expert Data Scientist working on a high stakes project.

    Your task is to select symbolic operators to initialize a PySRRegressor. Use ALL inputs:
       1. **Project description json**: Use the physical context to inform your choices!
       2. **Dataset statistics**: features and target variable distribution
       3. **Dataset visualization**: features vs target variable
    to make your decision!

    ### OPERATOR SELECTION (SUBSET; NO SIMPLICITY BIAS)
    Select a SUBSET (possibly large or empty) from these allowed operators based on the data evidence:
    • Allowed unary: ["sin", "exp", "log", "sqrt"]
    • Allowed binary: ["+", "-", "*", "/", "^"]
    Do not include operators without plausible support in the CSV/visualization. Do not default to selecting all operators.

    ### REQUIRED OUTPUT SCHEMA
    Return STRICT JSON only — no markdown, no code fences, no commentary. Output must parse with json.loads(). If unsure about a field, set it to null.

    {
        "unary_operators": ["<subset of allowed unary ops>"],
        "binary_operators": ["<subset of allowed binary ops>"]
    }
    """
    project_description: str = dspy.InputField(desc="Project description json")
    dataset_statistics: str = dspy.InputField(desc="Dataset statistics")
    visualizations: List[dspy.Image] = dspy.InputField(desc="Dataset visualizations")

    config_json: str = dspy.OutputField(desc="JSON configuration string")


class ExplainPySrEquations(dspy.Signature):
    """
    You are an agent who explains the output of symbolic regression.

    You will always receive exactly two JSON objects in the user message:

    1) PROJECT_SPEC: regression context, target, feature dictionary, constraints this will help you understand the problem setup. You should use the scientific understanding of the problem.
    2) DATA_SPEC: equations, loss, complexity.

    Goal: Provide clear, concise explanations of the equations in DATA_SPEC in the context of PROJECT_SPEC. After explaining all the equations please create a summary of the overall findings and selection of the most probable equation not just according to the metrics but more importantly according to the scientific understanding of the problem.

    Rules:
    - Parse both JSONs strictly. If a key is missing, say which and stop.
    - Treat PROJECT_SPEC.features' keys as canonical feature names.
    - Do NOT guess values that are not present in JSON.
    - When you reference fields, use dot paths like PROJECT_SPEC.target_variable.
    - If DATA_SPEC.action is present, follow it.
    - Use the provided feature descriptions in explanations.
    - IMPORTANT: Assign equation IDs sequentially starting from 1 (1, 2, 3, ...) in the order they appear in DATA_SPEC.

    ### OUTPUT FORMAT
    Return STRICT JSON only — no markdown, no code fences, no commentary. Output must parse with json.loads().

    Required schema:
    {
        "equations": [
            {
                "id": 1,
                "equation": "string - the exact equation from DATA_SPEC",
                "loss": 4.04,
                "complexity": 15,
                "overview": "string - brief 1-2 sentence description of what this equation models",
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
            "rationale": ["reason 1 why this equation is best", "reason 2", "reason 3"]
        }
    }

    Unless I say otherwise, respond in concise technical English.
    """
    project_spec_json: str = dspy.InputField(desc="JSON string of project specification")
    data_spec_json: str = dspy.InputField(desc="JSON string of equations data")

    explanation_json: str = dspy.OutputField(desc="JSON object with equations, summary, and recommendation")


class ExplainPySrEquationsDeep(dspy.Signature):
    """
    You are an agent who explains the output of symbolic regression with deep scientific research context.

    You will always receive exactly two JSON objects in the user message:

    1) PROJECT_SPEC: regression context, target, feature dictionary, constraints, AND deep_research_equations from scientific literature search.
    2) DATA_SPEC: equations, loss, complexity.

    Goal: Provide clear, concise explanations of the equations in DATA_SPEC in the context of PROJECT_SPEC. After explaining all the equations please create a summary of the overall findings and selection of the most probable equation not just according to the metrics but more importantly according to the scientific understanding of the problem.

    Rules:
    - Parse both JSONs strictly. If a key is missing, say which and stop.
    - Treat PROJECT_SPEC.features' keys as canonical feature names.
    - Do NOT guess values that are not present in JSON.
    - When you reference fields, use dot paths like PROJECT_SPEC.target_variable.
    - If DATA_SPEC.action is present, follow it.
    - Use the provided feature descriptions in explanations.
    - IMPORTANT: Assign equation IDs sequentially starting from 1 (1, 2, 3, ...) in the order they appear in DATA_SPEC.

    ### CITATIONS (Deep Analysis)
    PROJECT_SPEC contains "deep_research_equations" - equations found in scientific literature with their citation URLs.
    For each equation you explain, check if any of the deep research equations are scientifically related or similar.
    If so, include the citations from those related deep research equations in the "citations" field.
    Only include citations that are genuinely relevant to the equation being explained.
    If no related citations exist, set "citations" to an empty array [].

    ### OUTPUT FORMAT
    Return STRICT JSON only — no markdown, no code fences, no commentary. Output must parse with json.loads().

    Required schema:
    {
        "equations": [
            {
                "id": 1,
                "equation": "string - the exact equation from DATA_SPEC",
                "loss": 4.04,
                "complexity": 15,
                "overview": "string - brief 1-2 sentence description of what this equation models",
                "term_explanations": [
                    {
                        "term": "(-24.26 * Tm_sprsum)",
                        "explanation": "string describing what this term represents scientifically"
                    }
                ],
                "citations": ["https://doi.org/... - array of citation URLs from deep research equations that are relevant, empty [] if none"]
            }
        ],
        "summary": {
            "key_drivers": ["list", "of", "most", "important", "variables"],
            "secondary_drivers": ["list", "of", "secondary", "variables"],
            "findings": "string - paragraph summarizing overall findings across all equations"
        },
        "recommendation": {
            "equation_id": 1,
            "rationale": ["reason 1 why this equation is best", "reason 2", "reason 3"]
        }
    }

    Unless I say otherwise, respond in concise technical English.
    """
    project_spec_json: str = dspy.InputField(desc="JSON string of project specification with deep research equations")
    data_spec_json: str = dspy.InputField(desc="JSON string of equations data")

    explanation_json: str = dspy.OutputField(desc="JSON object with equations (including citations), summary, and recommendation")


class DeepResearchEquations(dspy.Signature):
    """
    You are an expert scientific research agent. Your task is to take as input a dictionary of features in the form of key–value pairs, where the key is the variable name to be used in equations and the value is a short description of its meaning. Using this feature list, perform deep scientific research to identify physically based, semi-empirical, or empirical equations that relate two or more of the provided variables.

    Your responsibilities:

    1. Read the feature dictionary and treat each key as the symbolic variable to be used in equations.
    2. Search deeply through scientific literature (physics, micrometeorology, ecology, biogeochemistry, atmospheric science, etc.) to identify valid relationships between the variables.
    3. For each relationship:
       - Write a Pythonic equation using the keys from the feature list exactly as variable names.
       - You may introduce constants or parameters (e.g. kappa, g, cp, alpha, Pmax, A, B).
       - Provide citation links (DOI, journal URLs, textbook links) supporting the equation.
       - Optionally provide a brief description of the equation's physical meaning.
    4. Do not include explanations, extra text, or commentary — only the json.

    ### REQUIRED OUTPUT SCHEMA
    Return STRICT JSON only — no markdown, no code fences, no commentary. Output must parse with json.loads().
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
    features_json: str = dspy.InputField(desc="JSON string of feature dictionary mapping variable names to descriptions")

    equations: str = dspy.OutputField(desc="JSON object with equations array containing equation, citations")
