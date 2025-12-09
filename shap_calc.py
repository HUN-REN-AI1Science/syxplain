import os
import logging
import time
import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestRegressor
import shap
from typing import List

logger = logging.getLogger(__name__)

# Environment variables for SHAP subsampling configuration
# SHAP_SUBSAMPLE_FRACTION: Fraction of data to use (default 0.1 = 10%)
# SHAP_SUBSAMPLE_MIN: Minimum number of samples (default 1000)
# SHAP_SUBSAMPLE_MAX: Maximum number of samples (default 5000)

def get_shap_subsample_params():
    """Get SHAP subsampling parameters from environment variables with defaults."""
    fraction = float(os.environ.get("SHAP_SUBSAMPLE_FRACTION", "0.1"))
    min_samples = int(os.environ.get("SHAP_SUBSAMPLE_MIN", "1000"))
    max_samples = int(os.environ.get("SHAP_SUBSAMPLE_MAX", "5000"))
    return fraction, min_samples, max_samples


def subsample_for_shap(X):
    """
    Subsample data for SHAP calculation based on environment variable configuration.

    Parameters:
    X: numpy array or pandas DataFrame of input data

    Returns:
    Subsampled data (numpy array or DataFrame, same type as input)
    """
    n_samples = X.shape[0]
    fraction, min_samples, max_samples = get_shap_subsample_params()

    # Calculate target sample size
    target_size = int(n_samples * fraction)

    # Apply min/max constraints
    target_size = max(target_size, min_samples)
    target_size = min(target_size, max_samples)

    # Don't subsample if we already have fewer samples than target
    if n_samples <= target_size:
        logger.info(f"SHAP subsampling: Using all {n_samples} samples (below target of {target_size})")
        return X

    logger.info(f"SHAP subsampling: Reducing from {n_samples} to {target_size} samples "
                f"(fraction={fraction}, min={min_samples}, max={max_samples})")

    # Random subsampling with fixed seed for reproducibility
    rng = np.random.default_rng(845506771)
    indices = rng.choice(n_samples, size=target_size, replace=False)

    if isinstance(X, pd.DataFrame):
        return X.iloc[indices].reset_index(drop=True)
    else:
        return X[indices]


def train_model(df, predictor_columns, target_column):
    logger.info("Step 1: Training RandomForest model...")
    start = time.time()
    model = RandomForestRegressor(n_estimators=200, n_jobs=-1)
    model.fit(df[predictor_columns], y=df[target_column])
    logger.info(f"Step 1: Model training completed in {time.time() - start:.2f}s")
    return model


def rank_interactions_regression(model, X_all, feature_names=None, percent_of_total_mass=80):
    """
    Analyzes SHAP interaction effects for a regression model, ranks them,
    and returns a list of top interaction pairs that constitute a
    specified percentage of the total interaction "mass".

    Parameters:
    model: Trained regression model (e.g., RandomForestRegressor).
    X_all: pandas DataFrame or numpy array of the entire dataset used for predictions.
    feature_names: List of strings, names of the features. If None, column names from X_all
                   or generic names will be used.
    percent_of_total_mass: int or float, the percentage of the total interaction "mass"
                           that the returned top interactions should account for.
                           (e.g., 80 for 80%).

    Returns:
    A list of tuples, where each tuple contains (feature_i_name, feature_j_name),
    representing the top interaction pairs that contribute to the specified
    percentage of the total interaction mass, sorted by mean absolute SHAP
    interaction value in descending order.
    """

    if feature_names is None:
        if isinstance(X_all, pd.DataFrame):
            feature_names = X_all.columns.tolist()
        else:
            feature_names = [f"Feature_{i}" for i in range(X_all.shape[1])]

    n_features = X_all.shape[1]

    # Use the appropriate explainer for the model type
    logger.info("Step 2: Creating SHAP explainer...")
    start = time.time()
    if isinstance(model, (RandomForestRegressor)):
        explainer = shap.TreeExplainer(model)
    else:
        explainer = shap.Explainer(model) # Default to general Explainer for other models
    logger.info(f"Step 2: SHAP explainer created in {time.time() - start:.2f}s")

    logger.info("Step 3: Subsampling data for SHAP computation...")
    start = time.time()
    # Subsample data for faster SHAP computation
    X_subsampled = subsample_for_shap(X_all)
    logger.info(f"Step 3: Subsampling completed in {time.time() - start:.2f}s")

    # Calculate SHAP interaction values on subsampled data
    logger.info("Step 4: Calculating SHAP interaction values (this may take a while)...")
    start = time.time()
    shap_interaction_values = explainer.shap_interaction_values(X_subsampled)
    logger.info(f"Step 4: SHAP interaction values calculated in {time.time() - start:.2f}s")

    # For regression, shap_interaction_values should be a 3D array (samples, features, features)
    if not isinstance(shap_interaction_values, np.ndarray) or shap_interaction_values.ndim != 3:
        raise ValueError(
            "Expected shap_interaction_values to be a 3D numpy array for regression. "
            f"Got shape: {shap_interaction_values.shape}"
        )

    logger.info(f"SHAP interaction values shape: {shap_interaction_values.shape}")

    # Calculate mean absolute interaction values
    logger.info("Step 5: Calculating mean absolute interaction matrix...")
    start = time.time()
    mean_abs_interaction_matrix = np.mean(np.abs(shap_interaction_values), axis=0)
    logger.info(f"Step 5: Mean absolute matrix calculated in {time.time() - start:.2f}s")

    # Create list of all unique interaction pairs with their mean absolute SHAP values
    logger.info("Step 6: Creating and sorting interaction pairs...")
    start = time.time()
    interaction_pairs_with_values = []
    for i in range(n_features):
        for j in range(i + 1, n_features):  # Only consider unique pairs (i,j) where i < j
            # Average the (i,j) and (j,i) elements from the mean_abs_interaction_matrix
            interaction_value = (mean_abs_interaction_matrix[i, j] + mean_abs_interaction_matrix[j, i]) / 2

            param_i = feature_names[i]
            param_j = feature_names[j]
            interaction_pairs_with_values.append((param_i, param_j, interaction_value))

    # Sort interaction pairs by magnitude in descending order
    interaction_pairs_with_values.sort(key=lambda x: x[2], reverse=True)
    logger.info(f"Step 6: Interaction pairs created and sorted in {time.time() - start:.2f}s")

    # Calculate total "mass" of interaction effects
    total_interaction_mass = sum(value for _, _, value in interaction_pairs_with_values)
    logger.info(f"Total sum of mean absolute unique interaction effects: {total_interaction_mass:.4f}")

    # Determine the target mass threshold
    target_mass = total_interaction_mass * (percent_of_total_mass / 100)
    logger.info(f"Target interaction mass for {percent_of_total_mass}% threshold: {target_mass:.4f}")

    # Select top interactions until the target mass is reached
    top_interactions_mass = 0
    top_interaction_list = []
    for param_i, param_j, value in interaction_pairs_with_values:
        if top_interactions_mass < target_mass:
            top_interaction_list.append((param_i, param_j))
            top_interactions_mass += value
        else:
            break

    logger.info(f"Selected {len(top_interaction_list)} top interaction pairs covering "
                f"{top_interactions_mass / total_interaction_mass * 100:.2f}% of total interaction mass.")

    logger.info(f"Top Interaction Effects (ranked by mean absolute SHAP interaction value) "
                f"until {percent_of_total_mass}% of total mass is covered:")
    for idx, (param_i, param_j, value) in enumerate(interaction_pairs_with_values[:len(top_interaction_list)], 1):
        logger.info(f"{idx}. {param_i} × {param_j}: {value:.4f}")

    return top_interaction_list


def get_top_feature_interactions(data: pd.DataFrame, predictor_columns: List[str], target_column: str):
    # Train xgboost model
    model = train_model(data, predictor_columns, target_column)

    # Rank interactions
    top_interactions = rank_interactions_regression(
        model,
        data[predictor_columns].values,
        feature_names=predictor_columns,
        percent_of_total_mass=80
    )

    return top_interactions
