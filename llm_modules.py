import os
import dspy
from typing import List

import langfuse_config


def get_dspy_lm() -> dspy.LM:
    """Configures and returns a DSPy LM client."""
    model_name = os.environ.get("OPENAI_MODEL_NAME", "gpt-4o")
    api_key = os.environ.get("OPENAI_API_KEY")
    base_url = os.environ.get("OPENAI_API_BASE")

    return dspy.LM(model=f"openai/{model_name}", api_key=api_key, base_url=base_url)


def _get_prompt(name: str) -> str:
    """Get prompt from Langfuse. Raises error if not available."""
    prompt = langfuse_config.get_prompt(name)
    if prompt is None:
        raise RuntimeError(f"Required prompt '{name}' not found in Langfuse. Please ensure Langfuse is configured and the prompt exists with 'production' label.")
    return prompt


def _create_pysr_config_signature():
    """Create PySR config signature with prompt from Langfuse."""
    prompt = _get_prompt("sym_operator_selection")

    class PySrConfigGenerator(dspy.Signature):
        __doc__ = prompt
        project_description: str = dspy.InputField(desc="Project description json")
        dataset_statistics: str = dspy.InputField(desc="Dataset statistics")
        visualizations: List[dspy.Image] = dspy.InputField(desc="Dataset visualizations")
        config_json: str = dspy.OutputField(desc="JSON configuration string")

    return PySrConfigGenerator


def _create_explainer_signature():
    """Create explainer signature with prompt from Langfuse."""
    prompt = _get_prompt("pysr_explainer_sys")

    class ExplainPySrEquations(dspy.Signature):
        __doc__ = prompt
        project_spec: str = dspy.InputField(desc="JSON string of project specification")
        data_spec: str = dspy.InputField(desc="JSON string of equations data")
        explanation: str = dspy.OutputField(desc="Markdown explanation of the equations")

    return ExplainPySrEquations


def generate_pysr_config(project_description: str, dataset_statistics: str, visualizations_b64: List[str]) -> str:
    """Generates PySR configuration JSON using LLM."""
    lm = get_dspy_lm()

    # Create dspy.Image objects from base64 strings with Data URI format
    visual_inputs = [dspy.Image(f"data:image/png;base64,{img_b64}") for img_b64 in visualizations_b64]

    # Get signature with prompt from Langfuse
    PySrConfigGenerator = _create_pysr_config_signature()
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
        except:
            pass

    langfuse_config.flush_traces()
    return cleaned_json


def generate_equation_explanation(project_spec_json: str, data_spec_json: str) -> str:
    """Generates explanation for PySR equations."""
    lm = get_dspy_lm()

    # Get signature with prompt from Langfuse
    ExplainPySrEquations = _create_explainer_signature()
    predictor = dspy.Predict(ExplainPySrEquations)

    with dspy.settings.context(lm=lm):
        response = predictor(
            project_spec=project_spec_json,
            data_spec=data_spec_json
        )

    langfuse_config.flush_traces()
    return response.explanation
