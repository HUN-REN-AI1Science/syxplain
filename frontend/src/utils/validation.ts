/**
 * Validation Utilities
 * Form and data validation functions
 */

import type { ProblemDescription } from '@/types';

export interface ValidationResult {
  isValid: boolean;
  errors: ValidationError[];
}

export interface ValidationError {
  field: string;
  message: string;
}

/**
 * Validate problem form data in form mode
 */
export function validateProblemForm(
  projectDescription: string,
  targetVariable: string,
  featureDescriptions: Record<string, string>,
  columns: string[],
  excludedColumns: string[] = [],
  nanCounts: Record<string, number> = {}
): ValidationResult {
  const errors: ValidationError[] = [];

  // Project description is required
  if (!projectDescription.trim()) {
    errors.push({
      field: 'project_description',
      message: 'Project Description is required.',
    });
  }

  // Target variable is required
  if (!targetVariable) {
    errors.push({
      field: 'target_variable',
      message: 'Target Variable is required.',
    });
  }

  // Check if target variable has NaN values
  if (targetVariable && nanCounts[targetVariable] > 0) {
    errors.push({
      field: 'target_variable',
      message: `The target variable "${targetVariable}" contains ${nanCounts[targetVariable]} missing (NaN) values. Please clean your data or select a different target.`,
    });
  }

  // Get active columns (excluding target and non-numeric)
  const activeColumns = columns.filter(
    (col) => col !== targetVariable && !excludedColumns.includes(col)
  );

  // Check for missing feature descriptions
  const missingDescriptions = activeColumns.filter(
    (col) => !featureDescriptions[col] || featureDescriptions[col].trim() === ''
  );

  if (missingDescriptions.length > 0) {
    errors.push({
      field: 'features',
      message: `Please provide descriptions for all features. Missing: ${missingDescriptions.join(', ')}`,
    });
  }

  return {
    isValid: errors.length === 0,
    errors,
  };
}

/**
 * Validate JSON configuration
 */
export function validateJsonConfig(
  jsonContent: string,
  columns: string[],
  nanCounts: Record<string, number> = {}
): ValidationResult {
  const errors: ValidationError[] = [];

  // Check if JSON is empty
  if (!jsonContent.trim()) {
    errors.push({
      field: 'json',
      message: 'JSON content is empty.',
    });
    return { isValid: false, errors };
  }

  // Try parsing JSON
  let parsed: ProblemDescription;
  try {
    parsed = JSON.parse(jsonContent);
  } catch (e) {
    errors.push({
      field: 'json',
      message: `Invalid JSON: ${(e as Error).message}`,
    });
    return { isValid: false, errors };
  }

  // Validate project_description
  if (!parsed.project_description || typeof parsed.project_description !== 'string' || !parsed.project_description.trim()) {
    errors.push({
      field: 'project_description',
      message: 'JSON must contain a valid "project_description".',
    });
  }

  // Validate target_variable
  if (!parsed.target_variable || typeof parsed.target_variable !== 'string' || !parsed.target_variable.trim()) {
    errors.push({
      field: 'target_variable',
      message: 'JSON must contain a valid "target_variable".',
    });
  }

  // Validate features
  if (!parsed.features || typeof parsed.features !== 'object' || Array.isArray(parsed.features) || Object.keys(parsed.features).length === 0) {
    errors.push({
      field: 'features',
      message: 'JSON must contain "features" object with at least one feature.',
    });
  }

  // Validate target_variable exists in columns
  if (parsed.target_variable && !columns.includes(parsed.target_variable)) {
    errors.push({
      field: 'target_variable',
      message: `The target variable "${parsed.target_variable}" does not exist in the uploaded dataset.`,
    });
  }

  // Validate feature names exist in columns
  if (parsed.features) {
    const invalidFeatures = Object.keys(parsed.features).filter(
      (feature) => !columns.includes(feature)
    );
    if (invalidFeatures.length > 0) {
      errors.push({
        field: 'features',
        message: `The following features do not exist in the dataset: ${invalidFeatures.join(', ')}`,
      });
    }
  }

  // Check if target variable has NaN values
  if (parsed.target_variable && nanCounts[parsed.target_variable] > 0) {
    errors.push({
      field: 'target_variable',
      message: `The target variable "${parsed.target_variable}" contains missing (NaN) values. Please clean your data or select a different target.`,
    });
  }

  return {
    isValid: errors.length === 0,
    errors,
  };
}

/**
 * Validate deep research model selection
 */
export function validateDeepResearchModel(
  analysisType: 'quick' | 'deep',
  selectedModel: string | null,
  availableModels: string[]
): ValidationResult {
  const errors: ValidationError[] = [];

  if (analysisType === 'deep') {
    const model = selectedModel || (availableModels.length > 0 ? availableModels[0] : null);
    if (!model) {
      errors.push({
        field: 'deep_research_model',
        message: 'Please select a deep research model.',
      });
    }
  }

  return {
    isValid: errors.length === 0,
    errors,
  };
}
