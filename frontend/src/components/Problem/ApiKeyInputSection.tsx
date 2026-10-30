/**
 * ApiKeyInputSection Component
 * Displays API key input fields for users without HUN-REN access.
 * The main LLM is either Google Gemini or any OpenAI-compatible endpoint; an optional
 * OpenAI key enables the literature search.
 */

import React from 'react';
import { InputText } from 'primereact/inputtext';
import { Dropdown } from 'primereact/dropdown';
import { Message } from 'primereact/message';
import { SelectButton, type SelectButtonChangeEvent } from 'primereact/selectbutton';
import HelpButton from '../HelpButton';
import type { LlmProvider } from '@/types';

const OPENAI_DEFAULT_API_BASE = 'https://api.openai.com/v1';

// An empty base means OpenAI's; only OpenAI's own API has the literature web search
const isOpenaiBase = (apiBase: string) => {
  const base = apiBase.trim();
  if (!base) return true;
  try {
    const url = new URL(base);
    return url.protocol === 'https:' && url.hostname.toLowerCase() === 'api.openai.com';
  } catch {
    return false;
  }
};

const providerOptions: { label: string; value: LlmProvider }[] = [
  { label: 'Google Gemini', value: 'gemini' },
  { label: 'OpenAI-compatible', value: 'openai_compatible' },
];

/** The user's OpenAI-compatible endpoint, as typed */
export interface CompatEndpoint {
  apiKey: string;
  apiBase: string;
  model: string;
}

interface ApiKeyInputSectionProps {
  provider: LlmProvider;
  onProviderChange: (value: LlmProvider) => void;
  geminiApiKey: string;
  geminiModel: string;
  geminiModels: string[];
  onGeminiApiKeyChange: (value: string) => void;
  onGeminiModelChange: (value: string) => void;
  compat: CompatEndpoint;
  onCompatChange: (patch: Partial<CompatEndpoint>) => void;
  // Validation state of the main LLM (whichever provider is selected)
  llmError?: string | null;
  llmValidationStatus?: 'idle' | 'validating' | 'valid' | 'invalid';
  openaiApiKey: string;
  onOpenaiApiKeyChange: (value: string) => void;
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
        complexity. The literature search (when an OpenAI key is available) uses additional tokens.
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
  provider,
  onProviderChange,
  geminiApiKey,
  geminiModel,
  geminiModels,
  onGeminiApiKeyChange,
  onGeminiModelChange,
  compat,
  onCompatChange,
  llmError,
  llmValidationStatus = 'idle',
  openaiApiKey,
  onOpenaiApiKeyChange,
  openaiError,
  openaiValidationStatus = 'idle',
}) => {
  const modelOptions = geminiModels.map((m, index) => ({
    label: index === 0 ? `${m} (Recommended)` : m,
    value: m,
  }));
  const isGemini = provider === 'gemini';
  // On OpenAI's own endpoint the main key doubles as the literature key
  const mainKeyCoversLiterature = !isGemini && isOpenaiBase(compat.apiBase);

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

      {/* Main LLM card — Google Gemini or any OpenAI-compatible endpoint */}
      <div className="bg-surface-alt border border-[var(--color-border)] rounded-lg p-4">
        <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-2 mb-0.5">
          <h4 className="font-heading font-semibold text-secondary">LLM provider</h4>
          <SelectButton
            value={provider}
            options={providerOptions}
            onChange={(e: SelectButtonChangeEvent) => {
              if (e.value) onProviderChange(e.value as LlmProvider);
            }}
            allowEmpty={false}
          />
        </div>
        <p className="text-sm text-muted mb-4">
          {isGemini
            ? 'Default LLM for running Syxplain.'
            : 'Any endpoint that speaks the OpenAI API: OpenAI itself, OpenRouter, vLLM, LiteLLM, ...'}
        </p>

        {llmError && <Message severity="error" text={llmError} className="mb-3 w-full" />}

        {llmValidationStatus === 'valid' && (
          <Message
            severity="success"
            text={
              isGemini
                ? 'Gemini API key validated successfully.'
                : 'Endpoint, API key and model validated successfully.'
            }
            className="mb-3 w-full"
          />
        )}

        <div className="space-y-3">
          <div>
            <label className="block text-sm font-medium text-secondary mb-1">API Key</label>
            <InputText
              type="password"
              value={isGemini ? geminiApiKey : compat.apiKey}
              onChange={(e) =>
                isGemini
                  ? onGeminiApiKeyChange(e.target.value)
                  : onCompatChange({ apiKey: e.target.value })
              }
              placeholder={isGemini ? 'AIza...' : 'sk-...'}
              className="w-full"
            />
            {isGemini && (
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
            )}
          </div>

          {!isGemini && (
            <div>
              <label className="block text-sm font-medium text-secondary mb-1">Base URL</label>
              <InputText
                type="url"
                value={compat.apiBase}
                onChange={(e) => onCompatChange({ apiBase: e.target.value })}
                placeholder={OPENAI_DEFAULT_API_BASE}
                className="w-full"
              />
              <small className="text-muted">
                Any OpenAI-compatible endpoint, e.g. OpenRouter, vLLM, LiteLLM. Leave empty for
                OpenAI. It must be publicly reachable.
              </small>
            </div>
          )}

          <div>
            <label className="block text-sm font-medium text-secondary mb-1">Model</label>
            {isGemini ? (
              <Dropdown
                value={geminiModel}
                options={modelOptions}
                onChange={(e) => onGeminiModelChange(e.value)}
                className="w-full"
                disabled={geminiModels.length === 0}
              />
            ) : (
              <>
                <InputText
                  value={compat.model}
                  onChange={(e) => onCompatChange({ model: e.target.value })}
                  placeholder="e.g. gpt-5"
                  className="w-full"
                />
                <small className="text-muted">
                  The model name exactly as your endpoint expects it.
                </small>
              </>
            )}
          </div>
        </div>
      </div>

      {/* OpenAI card — optional, enables the literature search */}
      <div className="bg-surface-alt border border-[var(--color-border)] rounded-lg p-4">
        <div className="flex items-center gap-2 mb-0.5">
          <h4 className="font-heading font-semibold text-secondary">OpenAI</h4>
          <span className="text-xs font-medium text-muted bg-[var(--color-border)] rounded-full px-2 py-0.5">
            Optional
          </span>
        </div>
        <p className="text-sm text-muted mb-4">
          {mainKeyCoversLiterature
            ? 'Enables the literature search. If left empty, your main OpenAI key above is used for it.'
            : 'Enables the literature search, which runs on OpenAI. Without it the analysis still runs, just without the literature step.'}
        </p>

        {openaiError && <Message severity="error" text={openaiError} className="mb-3 w-full" />}

        {openaiValidationStatus === 'valid' && (
          <Message
            severity="success"
            text="OpenAI API key validated successfully."
            className="mb-3 w-full"
          />
        )}

        <div>
          <label className="block text-sm font-medium text-secondary mb-1">
            OpenAI API key (optional)
          </label>
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
      </div>
    </div>
  );
};

export default ApiKeyInputSection;
