/**
 * ApiKeyInputSection Component
 * Displays API key input fields for users without HUN-REN access
 * Includes help information about key security and usage
 */

import React from 'react';
import { InputText } from 'primereact/inputtext';
import { Dropdown } from 'primereact/dropdown';
import { Message } from 'primereact/message';
import HelpButton from '../HelpButton';

interface ApiKeyInputSectionProps {
  apiKey: string;
  model: string;
  models: string[];
  onApiKeyChange: (value: string) => void;
  onModelChange: (value: string) => void;
  error?: string | null;
  validationStatus?: 'idle' | 'validating' | 'valid' | 'invalid';
}

const ApiKeyHelpContent = () => (
  <div className="space-y-4">
    <div>
      <h4 className="font-semibold text-slate-700 mb-2">Security & Privacy</h4>
      <ul className="list-disc pl-5 space-y-1">
        <li><strong>Your key is never stored</strong> - It exists only in memory during the analysis and is discarded immediately after.</li>
        <li><strong>No logging</strong> - Your API key is never written to any logs or databases.</li>
        <li><strong>Encrypted in transit</strong> - All communication uses HTTPS encryption.</li>
      </ul>
    </div>

    <div>
      <h4 className="font-semibold text-slate-700 mb-2">Estimated Token Usage</h4>
      <p className="text-sm">
        A typical analysis uses approximately <strong>5,000-15,000 tokens</strong> depending on data complexity.
        Deep research may use additional tokens.
      </p>
    </div>

    <div className="bg-blue-50 p-3 rounded">
      <h4 className="font-semibold text-blue-800 mb-1">Want to Use Built-in API Keys?</h4>
      <p className="text-sm text-blue-700">
        If you'd like access to the built-in HUN-REN API keys (no personal key required),
        please contact the system administrators to request access privileges.
      </p>
    </div>
  </div>
);

export const ApiKeyInputSection: React.FC<ApiKeyInputSectionProps> = ({
  apiKey,
  model,
  models,
  onApiKeyChange,
  onModelChange,
  error,
  validationStatus = 'idle',
}) => {
  const modelOptions = models.map((m, index) => ({
    label: index === 0 ? `${m} (Recommended)` : m,
    value: m,
  }));

  return (
    <div className="bg-slate-50 border border-slate-200 rounded-lg p-4 mb-4">
      <div className="flex items-start mb-4">
        <i className="pi pi-key text-blue-500 mr-3 mt-1 text-xl" />
        <div className="flex-1">
          <div className="flex items-center gap-2">
            <h4 className="font-semibold text-slate-700">OpenAI API Key Required</h4>
            <HelpButton title="How Your API Key Is Used">
              <ApiKeyHelpContent />
            </HelpButton>
          </div>
          <p className="text-sm text-slate-600 mt-1">
            Your API key is used only for this analysis session and is <strong>never stored</strong> on our servers.
          </p>
          <p className="text-sm text-slate-500 mt-2">
            <i className="pi pi-info-circle mr-1" />
            Want to use built-in API keys instead? Contact your administrator to request access.
          </p>
        </div>
      </div>

      {error && (
        <Message severity="error" text={error} className="mb-4 w-full" />
      )}

      {validationStatus === 'valid' && (
        <Message severity="success" text="API key validated successfully. Your key will be used for this analysis only." className="mb-4 w-full" />
      )}

      <div className="space-y-4">
        <div>
          <label className="block text-sm font-medium text-slate-700 mb-1">
            OpenAI API Key
          </label>
          <InputText
            type="password"
            value={apiKey}
            onChange={(e) => onApiKeyChange(e.target.value)}
            placeholder="sk-..."
            className="w-full"
          />
          <small className="text-slate-500">
            Get your API key from{' '}
            <a
              href="https://platform.openai.com/api-keys"
              target="_blank"
              rel="noopener noreferrer"
              className="text-blue-600 hover:underline"
            >
              platform.openai.com
            </a>
          </small>
        </div>

        <div>
          <label className="block text-sm font-medium text-slate-700 mb-1">
            Model
          </label>
          <Dropdown
            value={model}
            options={modelOptions}
            onChange={(e) => onModelChange(e.value)}
            className="w-full"
            disabled={models.length === 0}
          />
          {models.length > 0 && (
            <small className="text-slate-500">
              {models[0]} is recommended for best results
            </small>
          )}
        </div>
      </div>
    </div>
  );
};

export default ApiKeyInputSection;
