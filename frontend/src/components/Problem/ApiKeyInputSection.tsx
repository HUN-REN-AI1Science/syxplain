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
      <h4 className="font-heading font-semibold text-secondary mb-2">Security & Privacy</h4>
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
      <h4 className="font-heading font-semibold text-secondary mb-2">Estimated Token Usage</h4>
      <p className="text-sm">
        A typical analysis uses approximately <strong>5,000-15,000 tokens</strong> depending on data
        complexity. Deep research may use additional tokens.
      </p>
    </div>

    <div className="bg-brand-50 p-3 rounded">
      <h4 className="font-heading font-semibold text-primary mb-1">
        Want to Use Built-in API Keys?
      </h4>
      <p className="text-sm text-secondary">
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
    <div className="space-y-3 mb-4">
      {/* Security disclaimer — standalone banner, applies to all keys */}
      <div className="flex items-start gap-3 bg-brand-50 border border-[var(--color-border)] rounded-lg px-4 py-3">
        <i className="pi pi-shield text-brand-500 mt-0.5" />
        <div className="flex-1 min-w-0">
          <p className="text-sm text-secondary">
            Your API keys are used only for this analysis session and are{' '}
            <strong>never stored</strong> on our servers.
          </p>
          <p className="text-xs text-muted mt-1">
            Want to use built-in API keys instead? Contact your administrator to request access.
          </p>
        </div>
        <HelpButton title="How Your API Keys Are Used">
          <ApiKeyHelpContent />
        </HelpButton>
      </div>

      {/* Google Gemini card */}
      <div className="bg-surface-alt border border-[var(--color-border)] rounded-lg p-4">
        <div className="flex items-center gap-2 mb-0.5">
          <h4 className="font-heading font-semibold text-secondary">Google Gemini</h4>
        </div>
        <p className="text-sm text-muted mb-4">Default LLM for running Syxplain.</p>

        {geminiError && <Message severity="error" text={geminiError} className="mb-3 w-full" />}

        {geminiValidationStatus === 'valid' && (
          <Message
            severity="success"
            text="Gemini API key validated successfully."
            className="mb-3 w-full"
          />
        )}

        <div className="space-y-3">
          <div>
            <label className="block text-sm font-medium text-secondary mb-1">API Key</label>
            <InputText
              type="password"
              value={geminiApiKey}
              onChange={(e) => onGeminiApiKeyChange(e.target.value)}
              placeholder="AIza..."
              className="w-full"
            />
            <small className="text-muted">
              Get your key from{' '}
              <a
                href="https://aistudio.google.com/apikey"
                target="_blank"
                rel="noopener noreferrer"
                className="text-link hover:underline"
              >
                aistudio.google.com/apikey
              </a>
            </small>
          </div>

          <div>
            <label className="block text-sm font-medium text-secondary mb-1">Model</label>
            <Dropdown
              value={geminiModel}
              options={modelOptions}
              onChange={(e) => onGeminiModelChange(e.value)}
              className="w-full"
              disabled={geminiModels.length === 0}
            />
          </div>
        </div>
      </div>

      {/* OpenAI card — only when deep research is selected */}
      {showOpenAiInput && (
        <div className="bg-surface-alt border border-[var(--color-border)] rounded-lg p-4">
          <div className="flex items-center gap-2 mb-0.5">
            <h4 className="font-heading font-semibold text-secondary">OpenAI</h4>
            <span className="text-xs font-medium text-muted bg-[var(--color-border)] rounded-full px-2 py-0.5">
              Deep Research
            </span>
          </div>
          <p className="text-sm text-muted mb-4">
            Scientific literature search using an OpenAI model.
          </p>

          {openaiError && <Message severity="error" text={openaiError} className="mb-3 w-full" />}

          {openaiValidationStatus === 'valid' && (
            <Message
              severity="success"
              text="OpenAI API key validated successfully."
              className="mb-3 w-full"
            />
          )}

          <div className="space-y-3">
            <div>
              <label className="block text-sm font-medium text-secondary mb-1">API Key</label>
              <InputText
                type="password"
                value={openaiApiKey}
                onChange={(e) => onOpenaiApiKeyChange(e.target.value)}
                placeholder="sk-..."
                className="w-full"
              />
              <small className="text-muted">
                Get your key from{' '}
                <a
                  href="https://platform.openai.com/api-keys"
                  target="_blank"
                  rel="noopener noreferrer"
                  className="text-link hover:underline"
                >
                  platform.openai.com/api-keys
                </a>
              </small>
            </div>

            <div>
              <label className="block text-sm font-medium text-secondary mb-1">Model</label>
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
