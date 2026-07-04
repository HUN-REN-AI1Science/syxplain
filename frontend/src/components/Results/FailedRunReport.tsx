/**
 * FailedRunReport Component
 * Detailed failure report for failed/timeout/cancelled runs:
 * what happened, what the user can do about it, and technical details.
 */

import React, { useState } from 'react';
import type { RunErrorDetails, RunStatus } from '@/types';

interface FailedRunReportProps {
  status: RunStatus;
  error: string | null;
  errorDetails?: RunErrorDetails | null;
}

interface CategoryMeta {
  icon: string;
  title: string;
  suggestions: string[];
}

// Mirrors backend/core/error_classification.py ErrorCategory values
const CATEGORY_META: Record<string, CategoryMeta> = {
  llm_auth: {
    icon: 'pi-key',
    title: 'AI Service Authentication Failed',
    suggestions: [
      'Check that your API key is entered correctly (no extra spaces).',
      'Verify the key is still active and has not been revoked.',
      'Generate a new API key from your provider and try again.',
    ],
  },
  llm_quota: {
    icon: 'pi-wallet',
    title: 'AI Service Quota Exceeded',
    suggestions: [
      'Check your API account balance and usage limits.',
      'Add credits or increase your spending limit.',
      'Wait a while and try again — rate limits often reset automatically.',
    ],
  },
  llm_model: {
    icon: 'pi-sliders-h',
    title: 'AI Model Not Available',
    suggestions: [
      'The selected model may have been deprecated or renamed.',
      'Start a new analysis with a different model.',
    ],
  },
  llm_unavailable: {
    icon: 'pi-cloud',
    title: 'AI Service Unavailable',
    suggestions: [
      'This is usually temporary — try running the analysis again.',
      'Check the AI provider status page if the problem persists.',
    ],
  },
  data: {
    icon: 'pi-table',
    title: 'Problem With Your Dataset',
    suggestions: [
      'Check that the target variable and all selected features exist in your file and contain numeric values.',
      'Remove columns that are empty or contain mostly missing values.',
      'Make sure the file has enough valid rows after removing missing data.',
      'Re-upload the file and start a new analysis with the corrected data.',
    ],
  },
  cluster_submit: {
    icon: 'pi-server',
    title: 'Could Not Reach the Computing Cluster',
    suggestions: [
      'The computing cluster may be under maintenance or at capacity.',
      'Try again later — this is not a problem with your data.',
      'If the problem persists, report it via the feedback button.',
    ],
  },
  cluster: {
    icon: 'pi-server',
    title: 'Computing Cluster Problem',
    suggestions: [
      'This was an infrastructure issue on the computing cluster, not a problem with your data.',
      'Try running the same analysis again.',
      'If it keeps failing, report it via the feedback button.',
    ],
  },
  resource_memory: {
    icon: 'pi-database',
    title: 'Computation Ran Out of Memory',
    suggestions: [
      'Reduce the number of rows in your dataset (e.g. use a representative sample).',
      'Select fewer feature columns for the analysis.',
      'Try a quick analysis instead of a deep one.',
    ],
  },
  resource_timeout: {
    icon: 'pi-clock',
    title: 'Computation Took Too Long',
    suggestions: [
      'Reduce the dataset size or the number of selected features.',
      'Try a quick analysis, which uses fewer iterations.',
      'Complex datasets sometimes succeed on a retry with slightly different settings.',
    ],
  },
  compute: {
    icon: 'pi-calculator',
    title: 'Computation Failed',
    suggestions: [
      'This is often caused by unusual data — check for constant columns, extreme outliers, or non-numeric values.',
      'Try again with fewer features or a cleaned dataset.',
      'If the technical details below mention a specific column, review that column in your file.',
    ],
  },
  internal: {
    icon: 'pi-exclamation-circle',
    title: 'Unexpected Error',
    suggestions: [
      'Try running the analysis again — transient errors often resolve on retry.',
      'If it keeps failing, report the problem via the feedback button and include this run ID.',
    ],
  },
};

const FailedRunReport: React.FC<FailedRunReportProps> = ({ status, error, errorDetails }) => {
  const [showTechnical, setShowTechnical] = useState(false);

  // Cancelled runs get a simple notice, not a failure report
  if (status === 'cancelled') {
    return (
      <div className="mb-6 rounded-lg border border-amber-300 bg-amber-50 p-4 flex items-start gap-3">
        <i className="pi pi-info-circle text-amber-500 text-xl mt-0.5" />
        <div>
          <h3 className="font-semibold text-amber-800 mb-1">Analysis Cancelled</h3>
          <p className="text-sm text-amber-700">
            {error || 'This analysis was cancelled before it finished.'} You can start a new
            analysis with the same or adjusted settings at any time.
          </p>
        </div>
      </div>
    );
  }

  const category =
    errorDetails?.category || (status === 'timeout' ? 'resource_timeout' : 'internal');
  const meta = CATEGORY_META[category] || CATEGORY_META.internal;
  const message =
    error || (status === 'timeout' ? 'The analysis timed out.' : 'The analysis failed.');

  const hasTechnical = !!(
    errorDetails?.technical ||
    errorDetails?.traceback ||
    errorDetails?.stage ||
    errorDetails?.task_type
  );

  return (
    <div className="mb-6 rounded-lg border border-red-300 bg-red-50 overflow-hidden">
      {/* Header */}
      <div className="p-4 sm:p-5">
        <div className="flex items-start gap-3">
          <i className={`pi ${meta.icon} text-red-500 text-2xl mt-0.5`} />
          <div className="min-w-0 flex-1">
            <h3 className="font-heading font-bold text-red-800 text-lg mb-1">{meta.title}</h3>
            <p className="text-sm text-red-700 break-words">{message}</p>
          </div>
        </div>

        {/* Suggestions */}
        <div className="mt-4 rounded-md bg-white/70 border border-red-200 p-4">
          <h4 className="text-sm font-semibold text-red-800 mb-2">
            <i className="pi pi-compass mr-2" />
            What you can do
          </h4>
          <ul className="list-disc pl-5 space-y-1">
            {meta.suggestions.map((suggestion, i) => (
              <li key={i} className="text-sm text-red-900/80">
                {suggestion}
              </li>
            ))}
          </ul>
        </div>
      </div>

      {/* Technical details (collapsible) */}
      {hasTechnical && (
        <div className="border-t border-red-200">
          <button
            className="w-full flex items-center gap-2 px-4 sm:px-5 py-2.5 text-sm font-medium text-red-800 hover:bg-red-100/60 transition-colors"
            onClick={() => setShowTechnical((v) => !v)}
          >
            <i className={`pi ${showTechnical ? 'pi-chevron-down' : 'pi-chevron-right'} text-xs`} />
            Technical details
          </button>
          {showTechnical && (
            <div className="px-4 sm:px-5 pb-4 space-y-3">
              <div className="flex flex-wrap gap-x-6 gap-y-1 text-xs text-red-900/70">
                {errorDetails?.stage && (
                  <span>
                    <strong>Failed during:</strong> {errorDetails.stage.replace(/_/g, ' ')}
                  </span>
                )}
                {errorDetails?.task_type && (
                  <span>
                    <strong>Task:</strong> {errorDetails.task_type.toUpperCase()}
                  </span>
                )}
              </div>
              {errorDetails?.technical && (
                <p className="text-xs font-mono text-red-900/80 break-words">
                  {errorDetails.technical}
                </p>
              )}
              {errorDetails?.traceback && (
                <pre className="text-xs font-mono text-red-900/70 bg-white/70 border border-red-200 rounded-md p-3 overflow-x-auto max-h-64 whitespace-pre-wrap">
                  {errorDetails.traceback}
                </pre>
              )}
            </div>
          )}
        </div>
      )}
    </div>
  );
};

export default FailedRunReport;
