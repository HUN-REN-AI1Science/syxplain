import os
import dspy
from typing import List

import langfuse_config


def get_dspy_lm() -> dspy.LM:
    """Configures and returns a DSPy LM client."""
    model_name = os.environ.get("OPENAI_MODEL_NAME", "gpt-4o")
    api_key = os.environ.get("OPENAI_API_KEY")
    base_url = os.environ.get("OPENAI_API_BASE")

    if not api_key:
        raise ValueError("OPENAI_API_KEY environment variable is required but not set or is empty.")
    return dspy.LM(model=f"openai/{model_name}", api_key=api_key, base_url=base_url)


class PySrConfigGenerator(dspy.Signature):
    """
    You are a senior expert Data Scientist working on a high stakes project.

    Your task is to select symbolic operators to initalize a PySRRegressor. Use ALL inputs:
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
    - If DATA_SPEC asks for code, return code only.
    - structure your response in markdown with sections for each equation explanation and a final summary. Should look nice after converting to HTML with pandoc.

    Unless I say otherwise, respond in concise technical English.
    """
    project_spec: str = dspy.InputField(desc="JSON string of project specification")
    data_spec: str = dspy.InputField(desc="JSON string of equations data")

    explanation: str = dspy.OutputField(desc="Markdown explanation of the equations")


def generate_pysr_config(project_description: str, dataset_statistics: str, visualizations_b64: List[str]) -> str:
    """Generates PySR configuration JSON using LLM."""
    lm = get_dspy_lm()

    # Create dspy.Image objects from base64 strings with Data URI format
    visual_inputs = [dspy.Image(f"data:image/png;base64,{img_b64}") for img_b64 in visualizations_b64]

    predictor = dspy.Predict(PySrConfigGenerator)

    with dspy.settings.context(lm=lm):
        response = predictor(
            project_description=project_description,
            dataset_statistics=dataset_statistics,
            visualizations=visual_inputs
        )

    config_json = response.config_json

    # Basic cleanup
    cleaned_json = config_json.replace("```json", "").replace("```", "").strip()
    if not (cleaned_json.startswith("{") and cleaned_json.endswith("}")):
        try:
            start = cleaned_json.find("{")
            end = cleaned_json.rfind("}") + 1
            if start >= 0 and end > start:
                cleaned_json = cleaned_json[start:end]
        except Exception:
            pass

    langfuse_config.flush_traces()
    return cleaned_json


def generate_equation_explanation(project_spec_json: str, data_spec_json: str) -> str:
    """Generates explanation for PySR equations."""
    lm = get_dspy_lm()
    predictor = dspy.Predict(ExplainPySrEquations)

    with dspy.settings.context(lm=lm):
        response = predictor(
            project_spec=project_spec_json,
            data_spec=data_spec_json
        )

    langfuse_config.flush_traces()
    return response.explanation
