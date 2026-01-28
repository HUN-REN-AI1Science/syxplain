/**
 * ProblemView Page
 * Form for defining the problem description, target variable, and features
 */

import React, { useState, useRef, useEffect } from 'react';
import { SelectButton } from 'primereact/selectbutton';
import { Toast } from 'primereact/toast';
import { configService, permissionsService } from '@services/api';
import { useAuth } from '@contexts/AuthContext';
import {
  ExcludedColumnsWarning,
  ProjectDetailsSection,
  TargetVariableSection,
  FeaturesSection,
  JsonConfigUpload,
  AnalysisTypeSelector,
  ApiKeyInputSection,
} from '@components/Problem';

interface ProblemViewProps {
  columns: string[];
  excludedColumns?: string[];
  nanCounts?: Record<string, number>;
  onSubmit: (data: any) => void;
}

const ProblemView: React.FC<ProblemViewProps> = ({ columns, excludedColumns, nanCounts, onSubmit }) => {
  const { hasHunrenAccess } = useAuth();
  const [mode, setMode] = useState<'form' | 'json'>('form');
  const [jsonContent, setJsonContent] = useState('');
  const toast = useRef<Toast>(null);

  // Analysis type state
  const [analysisType, setAnalysisType] = useState<'quick' | 'deep'>('quick');

  // Deep research model state
  const [deepResearchModels, setDeepResearchModels] = useState<string[]>([]);
  const [selectedDeepModel, setSelectedDeepModel] = useState<string | null>(null);

  // Form state
  const [projectDescription, setProjectDescription] = useState('');
  const [targetVariable, setTargetVariable] = useState('');
  const [featureDescriptions, setFeatureDescriptions] = useState<Record<string, string>>({});

  // User API key state (for users without HUN-REN access)
  const [userApiKey, setUserApiKey] = useState('');
  const [userModel, setUserModel] = useState('');
  const [userApiModels, setUserApiModels] = useState<string[]>([]);
  const [apiKeyError, setApiKeyError] = useState<string | null>(null);
  const [apiKeyValidationStatus, setApiKeyValidationStatus] = useState<'idle' | 'validating' | 'valid' | 'invalid'>('idle');

  // Fetch available deep research models on mount
  useEffect(() => {
    const fetchModels = async () => {
      try {
        const response = await configService.getDeepResearchModels();
        const models = response.data.models || [];
        setDeepResearchModels(models);
        // Auto-select first model if available
        if (models.length > 0) {
          setSelectedDeepModel(models[0]);
        }
      } catch (e) {
        console.error('Failed to fetch deep research models:', e);
      }
    };
    fetchModels();
  }, []);

  // Fetch available user API models on mount
  useEffect(() => {
    const fetchUserModels = async () => {
      try {
        const response = await configService.getUserApiModels();
        const models = response.data.models || [];
        setUserApiModels(models);
        // Auto-select first model if available
        if (models.length > 0) {
          setUserModel(models[0]);
        }
      } catch (e) {
        console.error('Failed to fetch user API models:', e);
      }
    };
    fetchUserModels();
  }, []);

  const validateAndGetPayload = () => {
    if (!projectDescription.trim()) {
      toast.current?.show({ severity: 'error', summary: 'Validation Error', detail: 'Project Description is required.' });
      return null;
    }
    if (!targetVariable) {
      toast.current?.show({ severity: 'error', summary: 'Validation Error', detail: 'Target Variable is required.' });
      return null;
    }

    // Check if target variable has NaN values
    if (nanCounts && nanCounts[targetVariable] > 0) {
      toast.current?.show({
        severity: 'error',
        summary: 'Invalid Target Variable',
        detail: `The target variable "${targetVariable}" contains ${nanCounts[targetVariable]} missing (NaN) values. Please clean your data or select a different target.`
      });
      return null;
    }

    const activeColumns = columns.filter(col =>
      col !== targetVariable &&
      (!excludedColumns || !excludedColumns.includes(col))
    );

    const missingDescriptions = activeColumns.filter(col => !featureDescriptions[col] || featureDescriptions[col].trim() === '');

    if (missingDescriptions.length > 0) {
      toast.current?.show({ severity: 'error', summary: 'Validation Error', detail: `Please provide descriptions for all features. Missing: ${missingDescriptions.join(', ')}` });
      return null;
    }

    const features: Record<string, string> = {};
    activeColumns.forEach(col => {
      features[col] = featureDescriptions[col];
    });

    return {
      project_description: projectDescription,
      target_variable: targetVariable,
      features: features
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

  // Validate user API key with backend
  const validateApiKey = async (): Promise<boolean> => {
    if (hasHunrenAccess) return true;

    if (!userApiKey.trim()) {
      setApiKeyError('API key is required');
      return false;
    }

    setApiKeyValidationStatus('validating');
    setApiKeyError(null);

    try {
      await permissionsService.validateKeys({ openai_api_key: userApiKey });
      setApiKeyValidationStatus('valid');
      return true;
    } catch (error: any) {
      const errorMessage = error.response?.data?.detail || 'API key validation failed';
      setApiKeyError(errorMessage);
      setApiKeyValidationStatus('invalid');
      return false;
    }
  };

  const handleSubmit = async () => {
    // Validate API key for users without HUN-REN access
    if (!hasHunrenAccess) {
      const isKeyValid = await validateApiKey();
      if (!isKeyValid) {
        return;
      }
    }

    if (mode === 'json') {
      try {
        if (!jsonContent.trim()) {
          toast.current?.show({ severity: 'error', summary: 'Validation Error', detail: 'JSON content is empty.' });
          return;
        }
        const parsed = JSON.parse(jsonContent);

        // Validate JSON structure
        if (!parsed.project_description || typeof parsed.project_description !== 'string' || !parsed.project_description.trim()) {
          toast.current?.show({ severity: 'error', summary: 'Validation Error', detail: 'JSON must contain a valid "project_description".' });
          return;
        }
        if (!parsed.target_variable || typeof parsed.target_variable !== 'string' || !parsed.target_variable.trim()) {
          toast.current?.show({ severity: 'error', summary: 'Validation Error', detail: 'JSON must contain a valid "target_variable".' });
          return;
        }
        if (!parsed.features || typeof parsed.features !== 'object' || Array.isArray(parsed.features) || Object.keys(parsed.features).length === 0) {
          toast.current?.show({ severity: 'error', summary: 'Validation Error', detail: 'JSON must contain "features" object with at least one feature.' });
          return;
        }

        // Validate that target_variable exists in columns
        if (!columns.includes(parsed.target_variable)) {
          toast.current?.show({
            severity: 'error',
            summary: 'Invalid Target Variable',
            detail: `The target variable "${parsed.target_variable}" does not exist in the uploaded dataset.`
          });
          return;
        }

        // Validate that all feature names exist in columns
        const invalidFeatures = Object.keys(parsed.features).filter(feature => !columns.includes(feature));
        if (invalidFeatures.length > 0) {
          toast.current?.show({
            severity: 'error',
            summary: 'Invalid Features',
            detail: `The following features do not exist in the dataset: ${invalidFeatures.join(', ')}`
          });
          return;
        }

        // Check if target variable has NaN values
        if (nanCounts && nanCounts[parsed.target_variable] > 0) {
          toast.current?.show({
            severity: 'error',
            summary: 'Invalid Target Variable',
            detail: `The target variable "${parsed.target_variable}" contains missing (NaN) values. Please clean your data or select a different target.`
          });
          return;
        }

        // Validate deep research model selection (only for HUN-REN users)
        const deepModel = hasHunrenAccess
          ? (selectedDeepModel || (deepResearchModels.length > 0 ? deepResearchModels[0] : null))
          : 'o4-mini-deep-research';
        if (analysisType === 'deep' && hasHunrenAccess && !deepModel) {
          toast.current?.show({
            severity: 'error',
            summary: 'Model Required',
            detail: 'Please select a deep research model.'
          });
          return;
        }

        onSubmit({
          ...parsed,
          analysis_type: analysisType,
          deep_research_model: analysisType === 'deep' ? deepModel : null,
          user_api_keys: !hasHunrenAccess ? { openai_api_key: userApiKey, openai_model: userModel } : undefined
        });
      } catch (e) {
        toast.current?.show({ severity: 'error', summary: 'Invalid JSON', detail: (e as Error).message });
      }
    } else {
      // Validation for Form Mode
      const payload = validateAndGetPayload();
      if (payload) {
        // Validate deep research model selection (only for HUN-REN users)
        const deepModel = hasHunrenAccess
          ? (selectedDeepModel || (deepResearchModels.length > 0 ? deepResearchModels[0] : null))
          : 'o4-mini-deep-research';
        if (analysisType === 'deep' && hasHunrenAccess && !deepModel) {
          toast.current?.show({
            severity: 'error',
            summary: 'Model Required',
            detail: 'Please select a deep research model.'
          });
          return;
        }

        onSubmit({
          ...payload,
          analysis_type: analysisType,
          deep_research_model: analysisType === 'deep' ? deepModel : null,
          user_api_keys: !hasHunrenAccess ? { openai_api_key: userApiKey, openai_model: userModel } : undefined
        });
      }
    }
  };

  const modeOptions = [
    { label: 'Interactive Form', value: 'form' },
    { label: 'Upload JSON', value: 'json' }
  ];

  const isSubmitDisabled = mode === 'form' && Boolean(targetVariable && nanCounts && nanCounts[targetVariable] > 0);

  return (
    <div className="p-4">
      <div className="flex flex-col md:flex-row justify-between items-start md:items-center mb-8">
        <div>
          <h2 className="text-2xl font-bold text-slate-800 mb-2">Define the Problem</h2>
          <p className="text-slate-500">Tell the AI what you want to predict and explain.</p>
        </div>

        <div className="mt-4 md:mt-0">
          <SelectButton value={mode} onChange={(e: any) => setMode(e.value)} options={modeOptions} />
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
          />

          <div className="grid grid-cols-1 lg:grid-cols-3 gap-8">
            <div className="lg:col-span-1">
              <TargetVariableSection
                columns={columns}
                targetVariable={targetVariable}
                nanCounts={nanCounts}
                onChange={setTargetVariable}
              />
            </div>

            <div className="lg:col-span-2">
              <FeaturesSection
                columns={columns}
                targetVariable={targetVariable}
                featureDescriptions={featureDescriptions}
                onChange={setFeatureDescriptions}
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
            apiKey={userApiKey}
            model={userModel}
            models={userApiModels}
            onApiKeyChange={(value) => {
              setUserApiKey(value);
              setApiKeyError(null);
              setApiKeyValidationStatus('idle');
            }}
            onModelChange={setUserModel}
            error={apiKeyError}
            validationStatus={apiKeyValidationStatus}
          />
        </div>
      )}

      <AnalysisTypeSelector
        analysisType={analysisType}
        onAnalysisTypeChange={setAnalysisType}
        deepResearchModels={deepResearchModels}
        selectedDeepModel={selectedDeepModel}
        onDeepModelChange={setSelectedDeepModel}
        onSubmit={handleSubmit}
        onExportJson={handleExportJson}
        disabled={isSubmitDisabled || apiKeyValidationStatus === 'validating'}
        showExportButton={mode === 'form'}
        hasHunrenAccess={hasHunrenAccess}
      />
    </div>
  );
};

export default ProblemView;
