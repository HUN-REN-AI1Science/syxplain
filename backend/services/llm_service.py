"""
LLM Service.

Orchestrates LLM interactions for the application, including:
- PySR configuration generation
- Equation explanation
- Deep research
"""

import asyncio
import json
import logging
from typing import Any

import dspy

from backend.core.config import get_settings
from backend.infrastructure.llm.client import create_deep_research_model, create_dspy_model
from backend.infrastructure.llm.signatures import (
    DeepResearchEquations,
    ExplainPySrEquations,
    ExplainPySrEquationsDeep,
    GuessColumnDescriptions,
    PySrConfigGenerator,
)
from backend.infrastructure.monitoring.langfuse_service import flush_traces, observe, report_usage
from backend.utils.json_utils import clean_and_fix_json_string

logger = logging.getLogger(__name__)


@observe(name="generate_pysr_config", as_type="generation")
def generate_pysr_config(
    project_description: str,
    dataset_statistics: str,
    visualizations_b64: list[str],
    user_api_key: str | None = None,
    user_model: str | None = None,
) -> str:
    """
    Generates PySR configuration JSON using LLM.

    Args:
        project_description: Description of the project
        dataset_statistics: Statistics of the dataset
        visualizations_b64: List of base64 encoded images
        user_api_key: Optional user-provided API key
        user_model: Optional user-specified model

    Returns:
        JSON string containing PySR configuration
    """
    lm = create_dspy_model(user_api_key=user_api_key, user_model=user_model)
    visual_inputs = [
        dspy.Image(f"data:image/png;base64,{img_b64}") for img_b64 in visualizations_b64
    ]

    predictor = dspy.Predict(PySrConfigGenerator)

    try:
        with dspy.settings.context(lm=lm):
            response = predictor(
                project_description=project_description,
                dataset_statistics=dataset_statistics,
                visualizations=visual_inputs,
            )

        config_json = response.config_json
        cleaned_json = clean_and_fix_json_string(config_json)

        try:
            json.loads(cleaned_json)
        except json.JSONDecodeError as e:
            flush_traces()
            logger.error(f"Failed to parse LLM response: {e}")
            raise ValueError(f"Failed to parse LLM response as valid JSON: {e}")

        report_usage(lm)
        return cleaned_json

    except Exception as e:
        logger.error(f"Error in generate_pysr_config: {e}")
        flush_traces()
        raise


# Small-LLM context is limited, so column suggestions are requested in chunks.
SUGGESTION_BATCH_SIZE = 8


@observe(name="guess_column_descriptions_batch", as_type="generation")
def guess_column_descriptions_batch(
    project_description: str,
    target_variable: str,
    columns: list[str],
    user_api_key: str | None = None,
    user_model: str | None = None,
) -> dict[str, str]:
    """
    Guesses short descriptions for one batch of column names.

    Server keys use the small model from SMALL_MODEL_NAME; user keys use the
    model the user selected (falling back to SMALL_USER_MODEL_NAME).

    Args:
        project_description: Description of the project/problem
        target_variable: Target variable name (may be empty)
        columns: Column names in this batch
        user_api_key: Optional user-provided API key
        user_model: Optional user-selected model (used with user_api_key)

    Returns:
        Dict mapping requested column names to non-empty descriptions
        (columns the model omitted or left empty are absent).
    """
    settings = get_settings().llm
    if user_api_key:
        lm = create_dspy_model(
            user_api_key=user_api_key,
            user_model=user_model or settings.small_user_model_name,
        )
    else:
        lm = create_dspy_model(model_name=settings.small_model_name)

    predictor = dspy.Predict(GuessColumnDescriptions)

    try:
        with dspy.settings.context(lm=lm):
            response = predictor(
                project_description=project_description,
                target_variable=target_variable,
                columns_json=json.dumps(columns),
            )

        cleaned_json = clean_and_fix_json_string(response.descriptions_json)
        parsed = json.loads(cleaned_json)
        report_usage(lm)

        requested = set(columns)
        return {
            col: desc.strip()
            for col, desc in parsed.items()
            if col in requested and isinstance(desc, str) and desc.strip()
        }

    except Exception as e:
        logger.error(f"Error in guess_column_descriptions_batch: {e}")
        flush_traces()
        raise


async def suggest_column_descriptions(
    project_description: str,
    target_variable: str,
    columns: list[str],
    user_api_key: str | None = None,
    user_model: str | None = None,
) -> tuple[dict[str, str], list[str]]:
    """
    Guesses descriptions for all columns, batching calls to the small model.

    Batches run in parallel; batches that fail or return incomplete results are
    retried once. Columns still missing afterwards are reported as failed rather
    than silently omitted.

    Returns:
        (descriptions, failed_columns)
    """
    unique_columns = list(dict.fromkeys(columns))
    descriptions: dict[str, str] = {}

    async def run_batch(batch: list[str]) -> dict[str, str]:
        return await asyncio.to_thread(
            guess_column_descriptions_batch,
            project_description,
            target_variable,
            batch,
            user_api_key,
            user_model,
        )

    async def run_pass(cols: list[str]) -> None:
        batches = [
            cols[i : i + SUGGESTION_BATCH_SIZE] for i in range(0, len(cols), SUGGESTION_BATCH_SIZE)
        ]
        results = await asyncio.gather(*(run_batch(b) for b in batches), return_exceptions=True)
        for batch, result in zip(batches, results, strict=True):
            if isinstance(result, BaseException):
                logger.warning(f"Suggestion batch failed ({batch[:3]}...): {result}")
            else:
                descriptions.update(result)

    await run_pass(unique_columns)
    missing = [col for col in unique_columns if col not in descriptions]
    if missing:
        await run_pass(missing)

    failed_columns = [col for col in unique_columns if col not in descriptions]
    return descriptions, failed_columns


@observe(name="deep_research_equations", as_type="generation")
def deep_research_equations(
    features_dict: dict[str, str], model_name: str | None = None, user_api_key: str | None = None
) -> dict[str, Any]:
    """
    Performs deep scientific research to find equations relating features.

    Args:
        features_dict: Dictionary mapping variable names to descriptions
        model_name: Optional override for model name (only used with server keys)
        user_api_key: Optional user-provided API key

    Returns:
        Dictionary with 'equations' list
    """
    try:
        lm = create_deep_research_model(model_name=model_name, user_api_key=user_api_key)

        features_json = json.dumps(features_dict, indent=2)
        predictor = dspy.Predict(DeepResearchEquations)

        with dspy.settings.context(lm=lm):
            response = predictor(features_json=features_json)

        report_usage(lm, model_name=model_name)

        equations_str = response.equations
        logger.debug(f"Deep Research Output: {equations_str}")
        cleaned_json = clean_and_fix_json_string(equations_str)

        try:
            parsed = json.loads(cleaned_json)
            # If model returned a bare array, wrap it in an object
            if isinstance(parsed, list):
                parsed = {"equations": parsed}
            else:
                parsed.setdefault("equations", [])
            return parsed
        except json.JSONDecodeError as e:
            logger.warning(f"Failed to parse deep research JSON: {e}. Raw: {cleaned_json[:200]}")
            return {"equations": [], "_parse_error": str(e)}

    except Exception as e:
        logger.error(f"Error in deep_research_equations: {e}")
        flush_traces()
        raise


@observe(name="generate_equation_explanation", as_type="generation")
def generate_equation_explanation(
    project_spec_json: str,
    data_spec_json: str,
    deep_research_context: dict[str, Any] | None = None,
    user_api_key: str | None = None,
    user_model: str | None = None,
) -> dict[str, Any]:
    """
    Generates explanation for PySR equations as structured JSON.

    Args:
        project_spec_json: JSON string of project specification
        data_spec_json: JSON string of equations data
        deep_research_context: Optional dict from deep research step
        user_api_key: Optional user-provided API key
        user_model: Optional user-specified model

    Returns:
        Dict with structured equation explanations (equations, summary, recommendation)
    """
    is_deep_analysis = deep_research_context and deep_research_context.get("equations")

    # The explanation step never searches the web — it only integrates citations already
    # produced by the deep research step — so the plain chat model is used with no web
    # search tool.
    lm = create_dspy_model(user_api_key=user_api_key, user_model=user_model)

    # Deep analysis additionally enriches the project spec with the researched equations.
    if is_deep_analysis:
        try:
            enhanced_project_spec = json.loads(project_spec_json)
            enhanced_project_spec["deep_research_equations"] = deep_research_context.get(
                "equations", []
            )
            project_spec_json = json.dumps(enhanced_project_spec, indent=2)
        except json.JSONDecodeError:
            logger.warning(
                "Failed to parse project_spec_json for enhancement, proceeding with original"
            )

    signature = ExplainPySrEquationsDeep if is_deep_analysis else ExplainPySrEquations
    predictor = dspy.Predict(signature)

    logger.info(f"Generating explanations. Deep Analysis: {is_deep_analysis}")

    try:
        with dspy.settings.context(lm=lm):
            logger.debug(f"Explain Equations Input - Project Spec: {project_spec_json}")
            logger.debug(f"Explain Equations Input - Data Spec: {data_spec_json}")

            response = predictor(project_spec_json=project_spec_json, data_spec_json=data_spec_json)
        report_usage(lm)

        explanation_json = response.explanation_json
        logger.debug(f"Explain Equations Output: {explanation_json}")

        cleaned_json = clean_and_fix_json_string(explanation_json)
        logger.debug(f"Explain Equations Cleaned Output: {cleaned_json}")

        # Validation Logic (adapted from original)
        try:
            parsed = json.loads(cleaned_json)

            # Ensure defaults
            parsed.setdefault("equations", [])
            parsed.setdefault(
                "summary", {"key_drivers": [], "secondary_drivers": [], "findings": ""}
            )
            # No recommendation: the backend falls back to the selector's headline.
            parsed.setdefault(
                "recommendation", {"equation_id": None, "simplified_equation": "", "rationale": []}
            )

            # Post-process: Renumber equation IDs
            if parsed["equations"]:
                old_to_new_id = {}
                for new_id, eq in enumerate(parsed["equations"], start=1):
                    old_id = eq.get("id")
                    if old_id is not None:
                        old_to_new_id[old_id] = new_id
                    eq["id"] = new_id

                # Update recommendation ID
                rec = parsed.get("recommendation", {})
                old_rec_id = rec.get("equation_id")
                if old_rec_id in old_to_new_id:
                    rec["equation_id"] = old_to_new_id[old_rec_id]

            return parsed

        except json.JSONDecodeError as e:
            # Log detailed error information for debugging
            error_pos = e.pos if hasattr(e, "pos") else "unknown"
            context_start = max(0, error_pos - 50) if isinstance(error_pos, int) else 0
            context_end = (
                min(len(cleaned_json), error_pos + 50) if isinstance(error_pos, int) else 100
            )
            context = (
                cleaned_json[context_start:context_end]
                if isinstance(error_pos, int)
                else cleaned_json[:100]
            )
            logger.error(
                f"Failed to parse explanation JSON: {e}. "
                f"Error at position {error_pos}. Context around error: ...{context}..."
            )
            # Fallback
            fallback = {
                "equations": [],
                "summary": {
                    "key_drivers": [],
                    "secondary_drivers": [],
                    "findings": explanation_json,
                },
                "recommendation": {"equation_id": 0, "simplified_equation": "", "rationale": []},
                "_parse_error": str(e),
            }
            return fallback

    except Exception as e:
        logger.error(f"Error in generate_equation_explanation: {e}")
        flush_traces()
        raise
