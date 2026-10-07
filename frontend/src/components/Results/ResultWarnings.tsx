/**
 * ResultWarnings Component
 * Non-blocking notes about parts of a run that failed while the results stayed usable
 * (results.warnings). The missing AI explanation gets a prominent banner; other stages
 * get small notes.
 */

import React from 'react';
import type { RunWarning } from '@/types';

const STAGE_LABEL: Record<string, string> = {
  agent: 'Discovery agent',
  deep_research: 'Literature research',
  literature: 'Literature laws',
  storage: 'Storage',
};

interface ResultWarningsProps {
  warnings: RunWarning[];
  /** Message for the "AI explanation unavailable" banner; omitted = no banner */
  explanationError?: string | null;
}

export const ResultWarnings: React.FC<ResultWarningsProps> = ({ warnings, explanationError }) => {
  const others = warnings.filter((w) => w.stage !== 'explanation' && w.message);
  if (explanationError == null && others.length === 0) return null;

  return (
    <div className="space-y-2">
      {explanationError != null && (
        <div
          role="status"
          className="bg-[rgba(245,158,11,0.08)] border border-[rgba(245,158,11,0.3)] rounded-xl p-4 flex items-start gap-3"
        >
          <i
            className="pi pi-exclamation-triangle text-amber-500 text-lg mt-0.5"
            aria-hidden="true"
          ></i>
          <div className="text-sm">
            <p className="font-semibold text-primary">
              AI explanation unavailable{explanationError ? `: ${explanationError}` : ''}
            </p>
            <p className="text-secondary mt-1">
              The equations, their scores and the discovery report below are complete; only the
              written interpretation is missing or partial.
            </p>
          </div>
        </div>
      )}
      {others.map((w, i) => (
        <p
          key={`${w.stage}-${i}`}
          className="text-xs text-secondary bg-[rgba(245,158,11,0.06)] border border-[rgba(245,158,11,0.2)] rounded-lg px-3 py-2"
        >
          <i className="pi pi-info-circle text-amber-500 mr-2" aria-hidden="true"></i>
          <span className="font-medium">{STAGE_LABEL[w.stage] ?? w.stage}:</span> {w.message}
        </p>
      ))}
    </div>
  );
};

export default ResultWarnings;
