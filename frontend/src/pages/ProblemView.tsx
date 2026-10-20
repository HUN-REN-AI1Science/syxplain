/**
 * ProblemView Page
 * Form for defining the problem description, target variable, and features
 */

import React, { useState, useRef, useEffect } from 'react';
import { SelectButton, type SelectButtonChangeEvent } from 'primereact/selectbutton';
import { Toast } from 'primereact/toast';
import { configService, permissionsService } from '@services/api';
import { useAuth } from '@contexts/AuthContext';
import { useDescriptionSuggestions } from '@hooks/useDescriptionSuggestions';
import {
  ExcludedColumnsWarning,
  ProjectDetailsSection,
  TargetVariableSection,
  FeaturesSection,
  JsonConfigUpload,
  RunAnalysisActions,
  ApiKeyInputSection,
} from '@components/Problem';

interface ProblemViewProps {
  columns: string[];
  excludedColumns?: string[];
  nanCounts?: Record<string, number>;
  onSubmit: (data: Record<string, unknown>) => void;
}

const ProblemView: React.FC<ProblemViewProps> = ({
  columns,
  excludedColumns,
  nanCounts,
  onSubmit,
}) => {
  const { hasHunrenAccess } = useAuth();
  const [mode, setMode] = useState<'form' | 'json'>('form');
  const [jsonContent, setJsonContent] = useState('');
  const toast = useRef<Toast>(null);

  // Form state
  const [projectDescription, setProjectDescription] = useState('');
  const [targetVariable, setTargetVariable] = useState('');
  const [featureDescriptions, setFeatureDescriptions] = useState<Record<string, string>>({});
  // Columns the user manually removed from the analysis (issue #49)
  const [removedColumns, setRemovedColumns] = useState<string[]>([]);

  // Gemini API key state (for users without HUN-REN access)
  const [geminiApiKey, setGeminiApiKey] = useState('');
  const [geminiModel, setGeminiModel] = useState('');
  const [geminiModels, setGeminiModels] = useState<string[]>([]);
  const [geminiKeyError, setGeminiKeyError] = useState<string | null>(null);
  const [geminiValidationStatus, setGeminiValidationStatus] = useState<
    'idle' | 'validating' | 'valid' | 'invalid'
  >('idle');

  // A column can be a feature when it's neither the target nor auto-excluded.
  // `target` is a param so the JSON import path can test against its own target.
  const isSelectableFeature = (col: string, target: string = targetVariable) =>
    col !== target && !excludedColumns?.includes(col);

  // "Active" narrows that to columns the user hasn't removed
  const isActiveColumn = (col: string) => isSelectableFeature(col) && !removedColumns.includes(col);

  // Single source of truth for the feature columns in play
  const activeColumns = columns.filter(isActiveColumn);

  const handleRemoveColumn = (col: string) => {
    setRemovedColumns((prev) => (prev.includes(col) ? prev : [...prev, col]));
  };

  const handleRestoreColumn = (col: string) => {
    setRemovedColumns((prev) => prev.filter((c) => c !== col));
  };

  // Selecting a column as target always re-includes it, so a removed column
  // picked from the dropdown can't stay in the removed list
  const handleTargetChange = (value: string) => {
    setTargetVariable(value);
    setRemovedColumns((prev) => prev.filter((c) => c !== value));
  };

  // Automatic column description suggestions (issue #45)
  const canSuggest = hasHunrenAccess || geminiApiKey.trim().length > 0;
  const lastSuggestedForRef = useRef('');

  const applySuggestions = (descriptions: Record<string, string>) => {
    // Functional update: never overwrite text the user typed while inference ran
    setFeatureDescriptions((prev) => {
      const next = { ...prev };
      for (const [col, desc] of Object.entries(descriptions)) {
        if (!next[col]?.trim()) next[col] = desc;
      }
      return next;
    });
  };

  const {
    status: suggestionStatus,
    failedColumns,
    errorMessage: suggestionError,
    requestSuggestions,
  } = useDescriptionSuggestions({ onDescriptions: applySuggestions });

  const getEmptyActiveColumns = () =>
    activeColumns.filter((col) => !featureDescriptions[col]?.trim());

  const triggerSuggestions = (manual = false) => {
    // Manual clicks always explain why nothing happened; the blur trigger stays silent
    const explain = (detail: string) => {
      if (manual) {
        toast.current?.show({ severity: 'info', summary: 'Suggestions', detail });
      }
    };

    if (mode !== 'form') return;
    if (!canSuggest) {
      explain('Enter your Gemini API key first to enable suggestions.');
      return;
    }
    if (projectDescription.trim().length < 20) {
      explain('Write a longer project description first (at least a sentence).');
      return;
    }
    const emptyColumns = getEmptyActiveColumns();
    if (emptyColumns.length === 0) {
      explain('All feature descriptions are already filled in.');
      return;
    }

    // Recorded only when a request is actually dispatched, so blurs that hit a
    // guard (e.g. no key yet) can still auto-trigger later for the same text
    lastSuggestedForRef.current = projectDescription;
    requestSuggestions({
      project_description: projectDescription,
      target_variable: targetVariable || undefined,
      columns: emptyColumns,
      gemini_api_key: !hasHunrenAccess ? geminiApiKey : undefined,
      gemini_model: !hasHunrenAccess ? geminiModel || undefined : undefined,
    });
  };

  const handleDescriptionBlur = () => {
    // Only auto-trigger when the description changed since the last suggestion run
    if (lastSuggestedForRef.current === projectDescription) return;
    triggerSuggestions();
  };

  // OpenAI API key state (optional; enables the literature search)
  const [openaiApiKey, setOpenaiApiKey] = useState('');
  const [openaiKeyError, setOpenaiKeyError] = useState<string | null>(null);
  const [openaiValidationStatus, setOpenaiValidationStatus] = useState<
    'idle' | 'validating' | 'valid' | 'invalid'
  >('idle');

  // Fetch available Gemini models on mount
  useEffect(() => {
    const fetchGeminiModels = async () => {
      try {
        const response = await configService.getUserApiModels();
        const models = response.data.models || [];
        setGeminiModels(models);
        // Auto-select first model if available
        if (models.length > 0) {
          setGeminiModel(models[0]);
        }
      } catch (e) {
        console.error('Failed to fetch Gemini models:', e);
      }
    };
    fetchGeminiModels();
  }, []);

  const validateAndGetPayload = () => {
    if (!projectDescription.trim()) {
      toast.current?.show({
        severity: 'error',
        summary: 'Validation Error',
        detail: 'Project Description is required.',
      });
      return null;
    }
    if (!targetVariable) {
      toast.current?.show({
        severity: 'error',
        summary: 'Validation Error',
        detail: 'Target Variable is required.',
      });
      return null;
    }

    // Check if target variable has NaN values
    if (nanCounts && nanCounts[targetVariable] > 0) {
      toast.current?.show({
        severity: 'error',
        summary: 'Invalid Target Variable',
        detail: `The target variable "${targetVariable}" contains ${nanCounts[targetVariable]} missing (NaN) values. Please clean your data or select a different target.`,
      });
      return null;
    }

    if (activeColumns.length === 0) {
      toast.current?.show({
        severity: 'error',
        summary: 'Validation Error',
        detail: 'At least one feature column (besides the target) is required to run the analysis.',
      });
      return null;
    }

    const missingDescriptions = activeColumns.filter(
      (col) => !featureDescriptions[col] || featureDescriptions[col].trim() === ''
    );

    if (missingDescriptions.length > 0) {
      toast.current?.show({
        severity: 'error',
        summary: 'Validation Error',
        detail: `Please provide descriptions for all features. Missing: ${missingDescriptions.join(', ')}`,
      });
      return null;
    }

    const features: Record<string, string> = {};
    activeColumns.forEach((col) => {
      features[col] = featureDescriptions[col];
    });

    return {
      project_description: projectDescription,
      target_variable: targetVariable,
      features: features,
    };
  };

  const handleExportJson = () => {
    const payload = validateAndGetPayload();
    if (!payload) return;

    // Export
    const jsonString = JSON.stringify(payload, null, 2);
    const blob = new Blob([jsonString], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = 'problem_config.json';
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    URL.revokeObjectURL(url);
  };

  // Validate Gemini API key with backend (format check)
  const validateGeminiKey = async (): Promise<boolean> => {
    if (hasHunrenAccess) return true;

    if (!geminiApiKey.trim()) {
      setGeminiKeyError('Gemini API key is required');
      return false;
    }

    setGeminiValidationStatus('validating');
    setGeminiKeyError(null);

    try {
      await permissionsService.validateKeys({ gemini_api_key: geminiApiKey });
      setGeminiValidationStatus('valid');
      return true;
    } catch (error: unknown) {
      const err = error as { response?: { data?: { detail?: string } } };
      const errorMessage = err.response?.data?.detail || 'Gemini API key validation failed';
      setGeminiKeyError(errorMessage);
      setGeminiValidationStatus('invalid');
      return false;
    }
  };

  // Validate the optional OpenAI API key with backend (format + live check)
  const validateOpenaiKey = async (): Promise<boolean> => {
    if (!openaiApiKey.trim()) return true;

    setOpenaiValidationStatus('validating');
    setOpenaiKeyError(null);

    try {
      await permissionsService.validateKeys({ openai_api_key: openaiApiKey });
      setOpenaiValidationStatus('valid');
      return true;
    } catch (error: unknown) {
      const err = error as { response?: { data?: { detail?: string } } };
      const errorMessage = err.response?.data?.detail || 'OpenAI API key validation failed';
      setOpenaiKeyError(errorMessage);
      setOpenaiValidationStatus('invalid');
      return false;
    }
  };

  const handleSubmit = async () => {
    // Validate API keys for users without HUN-REN access
    if (!hasHunrenAccess) {
      const isGeminiValid = await validateGeminiKey();
      if (!isGeminiValid) return;

      // The OpenAI key is optional; validate it only when provided
      const isOpenaiValid = await validateOpenaiKey();
      if (!isOpenaiValid) return;
    }

    // Build user_api_keys payload
    const userApiKeys = !hasHunrenAccess
      ? {
          gemini_api_key: geminiApiKey,
          gemini_model: geminiModel,
          ...(openaiApiKey.trim() ? { openai_api_key: openaiApiKey.trim() } : {}),
        }
      : undefined;

    if (mode === 'json') {
      try {
        if (!jsonContent.trim()) {
          toast.current?.show({
            severity: 'error',
            summary: 'Validation Error',
            detail: 'JSON content is empty.',
          });
          return;
        }
        const parsed = JSON.parse(jsonContent);

        // Validate JSON structure
        if (
          !parsed.project_description ||
          typeof parsed.project_description !== 'string' ||
          !parsed.project_description.trim()
        ) {
          toast.current?.show({
            severity: 'error',
            summary: 'Validation Error',
            detail: 'JSON must contain a valid "project_description".',
          });
          return;
        }
        if (
          !parsed.target_variable ||
          typeof parsed.target_variable !== 'string' ||
          !parsed.target_variable.trim()
        ) {
          toast.current?.show({
            severity: 'error',
            summary: 'Validation Error',
            detail: 'JSON must contain a valid "target_variable".',
          });
          return;
        }
        if (
          !parsed.features ||
          typeof parsed.features !== 'object' ||
          Array.isArray(parsed.features) ||
          Object.keys(parsed.features).length === 0
        ) {
          toast.current?.show({
            severity: 'error',
            summary: 'Validation Error',
            detail: 'JSON must contain "features" object with at least one feature.',
          });
          return;
        }

        // Validate that target_variable exists in columns
        if (!columns.includes(parsed.target_variable)) {
          toast.current?.show({
            severity: 'error',
            summary: 'Invalid Target Variable',
            detail: `The target variable "${parsed.target_variable}" does not exist in the uploaded dataset.`,
          });
          return;
        }

        // Validate that all feature names exist in columns
        const invalidFeatures = Object.keys(parsed.features).filter(
          (feature) => !columns.includes(feature)
        );
        if (invalidFeatures.length > 0) {
          toast.current?.show({
            severity: 'error',
            summary: 'Invalid Features',
            detail: `The following features do not exist in the dataset: ${invalidFeatures.join(', ')}`,
          });
          return;
        }

        // Check if target variable has NaN values
        if (nanCounts && nanCounts[parsed.target_variable] > 0) {
          toast.current?.show({
            severity: 'error',
            summary: 'Invalid Target Variable',
            detail: `The target variable "${parsed.target_variable}" contains missing (NaN) values. Please clean your data or select a different target.`,
          });
          return;
        }

        // Drop legacy analysis-mode fields that older exported configs may carry
        // eslint-disable-next-line @typescript-eslint/no-unused-vars
        const { analysis_type, deep_research_model, ...problem } = parsed;
        onSubmit({
          ...problem,
          user_api_keys: userApiKeys,
        });
      } catch (e) {
        toast.current?.show({
          severity: 'error',
          summary: 'Invalid JSON',
          detail: (e as Error).message,
        });
      }
    } else {
      // Validation for Form Mode
      const payload = validateAndGetPayload();
      if (payload) {
        onSubmit({
          ...payload,
          user_api_keys: userApiKeys,
        });
      }
    }
  };

  const handleModeChange = (newMode: 'form' | 'json') => {
    if (!newMode) return;
    if (newMode === 'form' && mode === 'json') {
      // JSON → Form: populate form fields from JSON
      try {
        const parsed = JSON.parse(jsonContent);
        if (parsed.project_description) setProjectDescription(parsed.project_description);
        if (parsed.target_variable) setTargetVariable(parsed.target_variable);
        if (parsed.features) {
          setFeatureDescriptions(parsed.features);
          // The JSON's feature set is authoritative: selectable columns absent
          // from it are treated as removed (auto-excluded stay in their own bucket).
          // Fall back to the current target when the JSON omits one, and use an
          // own-property check so a column named e.g. "toString" isn't mistaken
          // for a present feature.
          const importedTarget = parsed.target_variable || targetVariable;
          setRemovedColumns(
            columns.filter(
              (col) =>
                isSelectableFeature(col, importedTarget) &&
                !Object.prototype.hasOwnProperty.call(parsed.features, col)
            )
          );
        }
      } catch {
        // Invalid JSON — leave form as-is
      }
    } else if (newMode === 'json' && mode === 'form') {
      // Form → JSON: build JSON from current form fields
      const features: Record<string, string> = {};
      activeColumns.forEach((col) => {
        if (featureDescriptions[col]) features[col] = featureDescriptions[col];
      });
      setJsonContent(
        JSON.stringify(
          { project_description: projectDescription, target_variable: targetVariable, features },
          null,
          2
        )
      );
    }
    setMode(newMode);
  };

  const modeOptions = [
    { label: 'Interactive Form', value: 'form' },
    { label: 'Upload JSON', value: 'json' },
  ];

  const isSubmitDisabled =
    (mode === 'form' && Boolean(targetVariable && nanCounts && nanCounts[targetVariable] > 0)) ||
    geminiValidationStatus === 'validating' ||
    openaiValidationStatus === 'validating';

  return (
    <div className="p-4">
      <div className="flex flex-col md:flex-row justify-between items-start md:items-center mb-8">
        <div>
          <h2 className="text-2xl font-bold text-primary font-heading mb-2">Define the Problem</h2>
          <p className="text-secondary">Tell the AI what you want to predict and explain.</p>
        </div>

        <div className="mt-4 md:mt-0">
          <SelectButton
            value={mode}
            onChange={(e: SelectButtonChangeEvent) => handleModeChange(e.value)}
            options={modeOptions}
          />
        </div>
      </div>

      <ExcludedColumnsWarning excludedColumns={excludedColumns || []} />

      {mode === 'json' ? (
        <JsonConfigUpload jsonContent={jsonContent} onChange={setJsonContent} />
      ) : (
        <div className="space-y-8 animate-fade-in">
          <ProjectDetailsSection
            projectDescription={projectDescription}
            onChange={setProjectDescription}
            onBlur={handleDescriptionBlur}
          />

          <div className="grid grid-cols-1 lg:grid-cols-3 gap-8">
            <div className="lg:col-span-1">
              <TargetVariableSection
                columns={columns}
                targetVariable={targetVariable}
                nanCounts={nanCounts}
                onChange={handleTargetChange}
              />
            </div>

            <div className="lg:col-span-2">
              <FeaturesSection
                activeColumns={activeColumns}
                featureDescriptions={featureDescriptions}
                removedColumns={removedColumns}
                onRemoveColumn={handleRemoveColumn}
                onRestoreColumn={handleRestoreColumn}
                onChange={setFeatureDescriptions}
                suggestionStatus={suggestionStatus}
                suggestionError={suggestionError}
                failedColumns={failedColumns}
                canSuggest={canSuggest}
                onSuggest={() => triggerSuggestions(true)}
              />
            </div>
          </div>
        </div>
      )}

      <Toast ref={toast} />

      {/* API Key Input for users without HUN-REN access */}
      {!hasHunrenAccess && (
        <div className="mt-6">
          <ApiKeyInputSection
            geminiApiKey={geminiApiKey}
            geminiModel={geminiModel}
            geminiModels={geminiModels}
            onGeminiApiKeyChange={(value) => {
              setGeminiApiKey(value);
              setGeminiKeyError(null);
              setGeminiValidationStatus('idle');
            }}
            onGeminiModelChange={setGeminiModel}
            geminiError={geminiKeyError}
            geminiValidationStatus={geminiValidationStatus}
            openaiApiKey={openaiApiKey}
            onOpenaiApiKeyChange={(value) => {
              setOpenaiApiKey(value);
              setOpenaiKeyError(null);
              setOpenaiValidationStatus('idle');
            }}
            openaiError={openaiKeyError}
            openaiValidationStatus={openaiValidationStatus}
          />
        </div>
      )}

      <RunAnalysisActions
        onSubmit={handleSubmit}
        onExportJson={handleExportJson}
        disabled={isSubmitDisabled}
        showExportButton={mode === 'form'}
      />
    </div>
  );
};

export default ProblemView;
