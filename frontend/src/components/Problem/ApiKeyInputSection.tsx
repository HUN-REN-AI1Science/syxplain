/**
 * ApiKeyInputSection Component
 * Displays API key input fields for users without HUN-REN access.
 * Always shows Gemini key input; conditionally shows OpenAI key for deep research.
 */

import React from 'react';
import { InputText } from 'primereact/inputtext';
import { Dropdown } from 'primereact/dropdown';
import { Message } from 'primereact/message';
import HelpButton from '../HelpButton';

interface ApiKeyInputSectionProps {
  geminiApiKey: string;
  geminiModel: string;
  geminiModels: string[];
  onGeminiApiKeyChange: (value: string) => void;
  onGeminiModelChange: (value: string) => void;
  geminiError?: string | null;
  geminiValidationStatus?: 'idle' | 'validating' | 'valid' | 'invalid';
  showOpenAiInput: boolean;
  openaiApiKey: string;
  onOpenaiApiKeyChange: (value: string) => void;
  openaiModel: string;
  openaiModels: string[];
  onOpenaiModelChange: (value: string) => void;
  openaiError?: string | null;
  openaiValidationStatus?: 'idle' | 'validating' | 'valid' | 'invalid';
}

const ApiKeyHelpContent = () => (
  <div className="space-y-4">
    <div>
      <h4 className="font-semibold text-slate-700 mb-2">Security & Privacy</h4>
      <ul className="list-disc pl-5 space-y-1">
        <li>
          <strong>Your keys are never stored</strong> - They exist only in memory during the
          analysis and are discarded immediately after.
        </li>
        <li>
          <strong>No logging</strong> - Your API keys are never written to any logs or databases.
        </li>
        <li>
          <strong>Encrypted in transit</strong> - All communication uses HTTPS encryption.
        </li>
      </ul>
    </div>

    <div>
      <h4 className="font-semibold text-slate-700 mb-2">Estimated Token Usage</h4>
      <p className="text-sm">
        A typical analysis uses approximately <strong>5,000-15,000 tokens</strong> depending on data
        complexity. Deep research may use additional tokens.
      </p>
    </div>

    <div className="bg-blue-50 p-3 rounded">
      <h4 className="font-semibold text-blue-800 mb-1">Want to Use Built-in API Keys?</h4>
      <p className="text-sm text-blue-700">
        If you'd like access to the built-in HUN-REN API keys (no personal key required), please
        contact the system administrators to request access privileges.
      </p>
    </div>
  </div>
);

export const ApiKeyInputSection: React.FC<ApiKeyInputSectionProps> = ({
  geminiApiKey,
  geminiModel,
  geminiModels,
  onGeminiApiKeyChange,
  onGeminiModelChange,
  geminiError,
  geminiValidationStatus = 'idle',
  showOpenAiInput,
  openaiApiKey,
  onOpenaiApiKeyChange,
  openaiModel,
  openaiModels,
  onOpenaiModelChange,
  openaiError,
  openaiValidationStatus = 'idle',
}) => {
  const modelOptions = geminiModels.map((m, index) => ({
    label: index === 0 ? `${m} (Recommended)` : m,
    value: m,
  }));

  return (
    <div className="bg-slate-50 border border-slate-200 rounded-lg p-4 mb-4">
      <div className="flex items-start mb-4">
        <i className="pi pi-key text-blue-500 mr-3 mt-1 text-xl" />
        <div className="flex-1">
          <div className="flex items-center gap-2">
            <h4 className="font-semibold text-slate-700">Google Gemini API Key Required</h4>
            <HelpButton title="How Your API Keys Are Used">
              <ApiKeyHelpContent />
            </HelpButton>
          </div>
          <p className="text-sm text-slate-600 mt-1">
            Your API key is used only for this analysis session and is <strong>never stored</strong>{' '}
            on our servers.
          </p>
          <p className="text-sm text-slate-500 mt-2">
            <i className="pi pi-info-circle mr-1" />
            Want to use built-in API keys instead? Contact your administrator to request access.
          </p>
        </div>
      </div>

      {geminiError && <Message severity="error" text={geminiError} className="mb-4 w-full" />}

      {geminiValidationStatus === 'valid' && (
        <Message
          severity="success"
          text="Gemini API key validated successfully."
          className="mb-4 w-full"
        />
      )}

      <div className="space-y-4">
        <div>
          <label className="block text-sm font-medium text-slate-700 mb-1">
            Google Gemini API Key
          </label>
          <InputText
            type="password"
            value={geminiApiKey}
            onChange={(e) => onGeminiApiKeyChange(e.target.value)}
            placeholder="AIza..."
            className="w-full"
          />
          <small className="text-slate-500">
            Get your API key from{' '}
            <a
              href="https://aistudio.google.com/apikey"
              target="_blank"
              rel="noopener noreferrer"
              className="text-blue-600 hover:underline"
            >
              aistudio.google.com/apikey
            </a>
          </small>
        </div>

        <div>
          <label className="block text-sm font-medium text-slate-700 mb-1">Model</label>
          <Dropdown
            value={geminiModel}
            options={modelOptions}
            onChange={(e) => onGeminiModelChange(e.value)}
            className="w-full"
            disabled={geminiModels.length === 0}
          />
        </div>
      </div>

      {/* OpenAI API Key for Deep Research */}
      {showOpenAiInput && (
        <div className="mt-6 pt-4 border-t border-slate-200">
          <div className="flex items-start mb-3">
            <i className="pi pi-search text-amber-500 mr-3 mt-1 text-lg" />
            <div>
              <h4 className="font-semibold text-slate-700">OpenAI API Key for Deep Research</h4>
              <p className="text-sm text-slate-600 mt-1">
                Deep research performs scientific literature search using an OpenAI model.
              </p>
            </div>
          </div>

          {openaiError && <Message severity="error" text={openaiError} className="mb-4 w-full" />}

          {openaiValidationStatus === 'valid' && (
            <Message
              severity="success"
              text="OpenAI API key validated successfully."
              className="mb-4 w-full"
            />
          )}

          <div className="space-y-4">
            <div>
              <label className="block text-sm font-medium text-slate-700 mb-1">
                OpenAI API Key
              </label>
              <InputText
                type="password"
                value={openaiApiKey}
                onChange={(e) => onOpenaiApiKeyChange(e.target.value)}
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
                  platform.openai.com/api-keys
                </a>
              </small>
            </div>

            <div>
              <label className="block text-sm font-medium text-slate-700 mb-1">Model</label>
              <Dropdown
                value={openaiModel}
                options={openaiModels.map((m, index) => ({
                  label: index === 0 ? `${m} (Recommended)` : m,
                  value: m,
                }))}
                onChange={(e) => onOpenaiModelChange(e.value)}
                className="w-full"
                disabled={openaiModels.length === 0}
              />
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

export default ApiKeyInputSection;
