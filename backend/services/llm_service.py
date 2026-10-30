"""
LLM Service.

Orchestrates LLM interactions for the application, including:
- PySR configuration generation
- Equation explanation
- Literature search
"""

import asyncio
import json
import logging
from dataclasses import replace
from typing import Any

import dspy

from backend.core.config import get_settings
from backend.infrastructure.llm.client import create_dspy_model, create_literature_model
from backend.infrastructure.llm.images import png_images
from backend.infrastructure.llm.signatures import (
    ExplainPySrEquations,
    ExplainPySrEquationsWithLiterature,
    GuessColumnDescriptions,
    LiteratureLaws,
    PySrConfigGenerator,
)
from backend.infrastructure.monitoring.llm_costs import record_web_searches
from backend.utils.json_utils import clean_and_fix_json_string
from backend.utils.user_llm import UserLLM

logger = logging.getLogger(__name__)


def generate_pysr_config(
    project_description: str,
    dataset_statistics: str,
    visualizations_b64: list[str],
    user_llm: UserLLM | None = None,
) -> str:
    """
    Generates PySR configuration JSON using LLM.

    Args:
        project_description: Description of the project
        dataset_statistics: Statistics of the dataset
        visualizations_b64: List of base64 encoded images
        user_llm: The user's own LLM settings (None = server keys)

    Returns:
        JSON string containing PySR configuration
    """
    lm = create_dspy_model(user_llm=user_llm)
    visual_inputs = png_images(visualizations_b64)

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
            logger.error(f"Failed to parse LLM response: {e}")
            raise ValueError(f"Failed to parse LLM response as valid JSON: {e}")

        return cleaned_json

    except Exception as e:
        logger.error(f"Error in generate_pysr_config: {e}")
        raise


# Small-LLM context is limited, so column suggestions are requested in chunks.
SUGGESTION_BATCH_SIZE = 8


def guess_column_descriptions_batch(
    project_description: str,
    target_variable: str,
    columns: list[str],
    user_llm: UserLLM | None = None,
) -> dict[str, str]:
    """
    Guesses short descriptions for one batch of column names.

    Server keys use the small model from SMALL_MODEL_NAME; Gemini user keys use the
    model the user selected (falling back to SMALL_USER_MODEL_NAME). On a user's
    OpenAI-compatible endpoint no small model is known, so their chosen model is used.

    Args:
        project_description: Description of the project/problem
        target_variable: Target variable name (may be empty)
        columns: Column names in this batch
        user_llm: The user's own LLM settings (None = server keys)

    Returns:
        Dict mapping requested column names to non-empty descriptions
        (columns the model omitted or left empty are absent).
    """
    settings = get_settings().llm
    if user_llm and user_llm.api_key:
        small = replace(user_llm, model=user_llm.small_model(settings.small_user_model_name))
        lm = create_dspy_model(user_llm=small)
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
        requested = set(columns)
        return {
            col: desc.strip()
            for col, desc in parsed.items()
            if col in requested and isinstance(desc, str) and desc.strip()
        }

    except Exception as e:
        logger.error(f"Error in guess_column_descriptions_batch: {e}")
        raise


async def suggest_column_descriptions(
    project_description: str,
    target_variable: str,
    columns: list[str],
    user_llm: UserLLM | None = None,
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
            user_llm,
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


def find_literature_laws(
    features_dict: dict[str, str], user_api_key: str | None = None
) -> dict[str, Any]:
    """
    Searches the scientific literature on the web for equations relating the features.

    Args:
        features_dict: Dictionary mapping variable names to descriptions
        user_api_key: Optional user-provided OpenAI API key

    Returns:
        Dictionary with 'equations' list
    """
    try:
        lm = create_literature_model(user_api_key=user_api_key)

        features_json = json.dumps(features_dict, indent=2)
        predictor = dspy.Predict(LiteratureLaws)

        with dspy.settings.context(lm=lm):
            response = predictor(features_json=features_json)
        n_searches = record_web_searches(lm)
        logger.info(f"Literature search used {n_searches} web searches")

        equations_str = response.equations
        logger.debug(f"Literature search output: {equations_str}")
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
            logger.warning(f"Failed to parse literature JSON: {e}. Raw: {cleaned_json[:200]}")
            return {"equations": [], "_parse_error": str(e)}

    except Exception as e:
        logger.error(f"Error in find_literature_laws: {e}")
        raise


def generate_equation_explanation(
    project_spec_json: str,
    data_spec_json: str,
    literature_context: dict[str, Any] | None = None,
    user_llm: UserLLM | None = None,
    shap_plots: list[dspy.Image] | None = None,
) -> dict[str, Any]:
    """
    Generates explanation for PySR equations as structured JSON.

    Args:
        project_spec_json: JSON string of project specification
        data_spec_json: JSON string of equations data
        literature_context: Optional dict of fitted published laws
        user_llm: The user's own LLM settings (None = server keys)
        shap_plots: Optional SHAP plot images

    Returns:
        Dict with structured equation explanations (equations, summary, recommendation)
    """
    has_literature = literature_context and literature_context.get("equations")

    # The explanation step never searches the web — it only integrates citations already
    # produced by the literature search — so the plain chat model is used with no web
    # search tool.
    lm = create_dspy_model(user_llm=user_llm)

    # With published laws, the project spec is enriched with them.
    if has_literature:
        try:
            enhanced_project_spec = json.loads(project_spec_json)
            enhanced_project_spec["literature_equations"] = literature_context.get("equations", [])
            project_spec_json = json.dumps(enhanced_project_spec, indent=2)
        except json.JSONDecodeError:
            logger.warning(
                "Failed to parse project_spec_json for enhancement, proceeding with original"
            )

    signature = ExplainPySrEquationsWithLiterature if has_literature else ExplainPySrEquations
    predictor = dspy.Predict(signature)

    logger.info(f"Generating explanations. With literature: {bool(has_literature)}")

    try:
        with dspy.settings.context(lm=lm):
            logger.debug(f"Explain Equations Input - Project Spec: {project_spec_json}")
            logger.debug(f"Explain Equations Input - Data Spec: {data_spec_json}")

            response = predictor(
                project_spec_json=project_spec_json,
                data_spec_json=data_spec_json,
                shap_plots=shap_plots or [],
            )
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
        raise
