import logging
import json
import os
import dspy
from typing import List

from langfuse_config import observe, report_usage_to_langfuse, flush_traces

logger = logging.getLogger(__name__)


def get_dspy_lm() -> dspy.LM:
    """Configures and returns a DSPy LM client."""
    model_name = os.environ.get("OPENAI_MODEL_NAME", "gpt-4o")
    api_key = os.environ.get("OPENAI_API_KEY")
    api_base = os.environ.get("OPENAI_API_BASE")

    if not api_key:
        raise ValueError("OPENAI_API_KEY environment variable is required but not set or is empty.")
    return dspy.LM(model=f"openai/{model_name}", api_key=api_key, api_base=api_base)


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


@observe(name="generate_pysr_config", as_type="generation")
def generate_pysr_config(project_description: str, dataset_statistics: str, visualizations_b64: List[str]) -> str:
    """Generates PySR configuration JSON using LLM."""
    lm = get_dspy_lm()
    visual_inputs = [dspy.Image(f"data:image/png;base64,{img_b64}") for img_b64 in visualizations_b64]

    predictor = dspy.Predict(PySrConfigGenerator)
    with dspy.settings.context(lm=lm):
        response = predictor(
            project_description=project_description,
            dataset_statistics=dataset_statistics,
            visualizations=visual_inputs
        )

    config_json = response.config_json
    cleaned_json = config_json.replace("```json", "").replace("```", "").strip()

    if not (cleaned_json.startswith("{") and cleaned_json.endswith("}")):
        start = cleaned_json.find("{")
        end = cleaned_json.rfind("}") + 1
        if start >= 0 and end > start:
            cleaned_json = cleaned_json[start:end]

    try:
        json.loads(cleaned_json)
    except json.JSONDecodeError as e:
        flush_traces()
        raise ValueError(f"Failed to parse LLM response as valid JSON: {e}. Raw response: {config_json[:500]}")

    report_usage_to_langfuse(lm)
    return cleaned_json


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


@observe(name="generate_equation_explanation", as_type="generation")
def generate_equation_explanation(project_spec_json: str, data_spec_json: str, deep_research_context: dict = None) -> str:
    """Generates explanation for PySR equations as structured JSON.

    Args:
        project_spec_json: JSON string of project specification
        data_spec_json: JSON string of equations data
        deep_research_context: Optional dict from deep research step (for deep analysis mode)

    Returns:
        JSON string with structured equation explanations
    """
    model_name = os.environ.get("OPENAI_MODEL_NAME", "gpt-4o")
    api_key = os.environ.get("OPENAI_API_KEY")
    api_base = os.environ.get("OPENAI_API_BASE")

    # Enable web search for deep analysis mode (when deep_research_context is provided)
    lm_kwargs = dict(
        model=f"openai/{model_name}",
        api_key=api_key,
        api_base=api_base,
    )

    if deep_research_context and deep_research_context.get("equations"):
        lm_kwargs["web_search_options"] = {"search_context_size": "high"}

    lm = dspy.LM(**lm_kwargs)

    # If deep research context is provided, append it to the project spec
    if deep_research_context and deep_research_context.get("equations"):
        enhanced_project_spec = json.loads(project_spec_json)
        enhanced_project_spec["deep_research_equations"] = deep_research_context.get("equations", [])
        project_spec_json = json.dumps(enhanced_project_spec, indent=2)

    logger.info(f"project_spec_json: {project_spec_json}")

    predictor = dspy.Predict(ExplainPySrEquations)
    try:
        with dspy.settings.context(lm=lm):
            response = predictor(
                project_spec_json=project_spec_json,
                data_spec_json=data_spec_json
            )
        report_usage_to_langfuse(lm)

        # Clean and validate JSON response
        explanation_json = response.explanation_json
        cleaned_json = explanation_json.replace("```json", "").replace("```", "").strip()

        # Extract JSON if wrapped in other content
        if not (cleaned_json.startswith("{") and cleaned_json.endswith("}")):
            start = cleaned_json.find("{")
            end = cleaned_json.rfind("}") + 1
            if start >= 0 and end > start:
                cleaned_json = cleaned_json[start:end]

        # Validate JSON structure
        try:
            parsed = json.loads(cleaned_json)
            # Ensure required keys exist
            if "equations" not in parsed:
                parsed["equations"] = []
            if "summary" not in parsed:
                parsed["summary"] = {"key_drivers": [], "secondary_drivers": [], "findings": ""}
            if "recommendation" not in parsed:
                parsed["recommendation"] = {"equation_id": 1, "simplified_equation": "", "rationale": []}
            return json.dumps(parsed, indent=2)
        except json.JSONDecodeError as e:
            # Return a fallback structure with raw content
            fallback = {
                "equations": [],
                "summary": {"key_drivers": [], "secondary_drivers": [], "findings": explanation_json},
                "recommendation": {"equation_id": 0, "simplified_equation": "", "rationale": []},
                "_parse_error": str(e)
            }
            return json.dumps(fallback, indent=2)

    except Exception as e:
        flush_traces()
        raise


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


@observe(name="deep_research_equations", as_type="generation")
def deep_research_equations(features_dict: dict, model_name: str = None) -> dict:
    """Performs deep scientific research to find equations relating features.

    Uses the specified deep research model to search scientific literature
    and identify physical equations that relate the provided variables.

    Args:
        features_dict: Dictionary mapping variable names to descriptions
        model_name: Name of the deep research model to use (optional, falls back to env var)

    Returns:
        Dictionary with 'equations' list containing equation objects
    """
    # Use provided model_name or fall back to first model from environment variable
    if not model_name:
        models_env = os.environ.get("DEEP_RESEARCH_MODEL", "")
        if models_env:
            # Environment variable may contain comma-separated list of models
            model_name = models_env.split(",")[0].strip()
        else:
            model_name = "o4-mini-deep-research"
    api_key = os.environ.get("DEEP_RESEARCH_API_KEY")
    api_base = os.environ.get("DEEP_RESEARCH_API_BASE")

    if not api_key:
        raise ValueError("DEEP_RESEARCH_API_KEY environment variable is required but not set.")

    lm = dspy.LM(
        model=f"openai/{model_name}",
        api_key=api_key,
        api_base=api_base,
        extra_body={
            "tools": [
                {
                    "type": "web_search_preview",
                    "search_context_size": "medium"
                }
            ]
        }
    )

    features_json = json.dumps(features_dict, indent=2)
    predictor = dspy.Predict(DeepResearchEquations)

    try:
        with dspy.settings.context(lm=lm):
            response = predictor(features_json=features_json)
        report_usage_to_langfuse(lm, model_name=model_name)

        # Parse and validate JSON response
        equations_str = response.equations
        cleaned_json = equations_str.replace("```json", "").replace("```", "").strip()

        # Extract JSON if wrapped in other content
        if not (cleaned_json.startswith("{") and cleaned_json.endswith("}")):
            start = cleaned_json.find("{")
            end = cleaned_json.rfind("}") + 1
            if start >= 0 and end > start:
                cleaned_json = cleaned_json[start:end]

        try:
            parsed = json.loads(cleaned_json)
            # Ensure required structure exists
            if "equations" not in parsed:
                parsed = {"equations": []}
            return parsed
        except json.JSONDecodeError as e:
            logger.warning(f"Failed to parse deep research JSON: {e}. Raw: {equations_str[:500]}")
            return {"equations": [], "_parse_error": str(e)}
    except Exception as e:
        flush_traces()
        raise
