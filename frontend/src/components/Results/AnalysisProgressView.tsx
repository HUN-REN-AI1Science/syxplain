/**
 * AnalysisProgressView Component
 * Displays analysis progress with animated progress bar and step descriptions
 */

import React from 'react';
import { ProgressBar } from 'primereact/progressbar';
import { AgentActivityFeed } from './Discovery/AgentActivityFeed';
import type { AgentEvent } from '@/types';

interface AnalysisProgressViewProps {
  /** Current progress percentage (0-100) */
  displayProgress: number;
  /** Current step description */
  stepDescription: string;
  /** Whether we're in the early queue phase */
  isInQueuePhase?: boolean;
  /** Whether the job has been submitted to compute cluster */
  isJobSubmitted?: boolean;
  /** Live discovery-agent activity */
  activity?: AgentEvent[];
}

export const AnalysisProgressView: React.FC<AnalysisProgressViewProps> = ({
  displayProgress,
  stepDescription,
  isInQueuePhase = false,
  isJobSubmitted = false,
  activity = [],
}) => {
  return (
    <div className="text-center py-20">
      {/* Hero: percentage number */}
      <div aria-live="polite" className="mb-6">
        {isInQueuePhase ? (
          <p className="text-4xl font-heading font-bold text-brand-500 mb-2">
            Queued<span className="queue-pulse">...</span>
          </p>
        ) : (
          <p className="text-4xl font-heading font-bold text-brand-500 mb-2">
            {Math.floor(displayProgress)}%
          </p>
        )}
      </div>

      {/* Progress bar */}
      <div className="max-w-md mx-auto mb-6">
        {isInQueuePhase ? (
          <ProgressBar
            mode="indeterminate"
            style={{ height: '6px', borderRadius: '9999px' }}
            className="progress-bar-shimmer"
          />
        ) : (
          <ProgressBar
            value={displayProgress}
            showValue={false}
            style={{ height: '6px', borderRadius: '9999px' }}
          />
        )}
      </div>

      {/* Step Description with crossfade */}
      <div className="h-8 mb-4" aria-live="polite">
        <p
          key={stepDescription}
          className="text-base font-medium text-muted step-description-animate"
        >
          {stepDescription}
        </p>
      </div>

      <hr className="max-w-md mx-auto border-[var(--color-border)] mb-6" />

      <h3 className="font-heading text-xl font-semibold text-primary mt-4 mb-2">
        {isInQueuePhase ? 'Waiting for resources...' : 'AI is analyzing your data'}
      </h3>
      <p className="text-secondary max-w-md mx-auto mb-4">
        An AI agent tests classic scientific laws against your data, works out why they fall short,
        and steers symbolic regression towards better equations.
      </p>

      <AgentActivityFeed events={activity} />

      {isJobSubmitted && (
        <div className="max-w-md mx-auto bg-surface-alt rounded-lg px-4 py-3 text-sm text-secondary">
          You can safely leave this page. Your results will be available in the{' '}
          <span className="font-semibold">History</span> menu once completed.
        </div>
      )}
    </div>
  );
};

export default AnalysisProgressView;
