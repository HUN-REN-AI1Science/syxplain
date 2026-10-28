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
  /** Time spent in the current step, against how long it usually takes */
  stepTiming?: { label: string; elapsedS: number; expectedS: number | null };
}

/** Steps shorter than this are not worth a timing line */
const MIN_TIMED_STEP_S = 15;

const formatDuration = (seconds: number): string => {
  if (seconds < 60) return `${Math.round(seconds)}s`;
  const m = Math.floor(seconds / 60);
  const s = Math.floor(seconds % 60);
  return `${m}:${s.toString().padStart(2, '0')}`;
};

const formatTypical = (seconds: number): string =>
  seconds < 60 ? `~${Math.round(seconds)}s` : `~${Math.round(seconds / 60)} min`;

export const AnalysisProgressView: React.FC<AnalysisProgressViewProps> = ({
  displayProgress,
  stepDescription,
  isInQueuePhase = false,
  isJobSubmitted = false,
  activity = [],
  stepTiming,
}) => {
  const showTiming =
    !isInQueuePhase &&
    stepTiming &&
    ((stepTiming.expectedS ?? 0) >= MIN_TIMED_STEP_S || stepTiming.elapsedS >= MIN_TIMED_STEP_S);

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
      <div className="h-8 mb-1" aria-live="polite">
        <p
          key={stepDescription}
          className="text-base font-medium text-muted step-description-animate"
        >
          {stepDescription}
        </p>
      </div>

      {/* How long this step has run, against its typical duration */}
      <p className="h-5 mb-4 text-xs text-muted tabular-nums">
        {showTiming && (
          <>
            {stepTiming.label} · {formatDuration(stepTiming.elapsedS)} in this step
            {stepTiming.expectedS !== null && stepTiming.expectedS >= MIN_TIMED_STEP_S && (
              <> · usually {formatTypical(stepTiming.expectedS)}</>
            )}
          </>
        )}
      </p>

      <hr className="max-w-md mx-auto border-[var(--color-border)] mb-6" />

      {/* The agent's history fills the explanation's place in a fixed-height scrolling feed */}
      <AgentActivityFeed
        events={activity}
        title={isInQueuePhase ? 'Waiting for resources...' : 'AI is analyzing your data'}
        intro="An AI agent tests classic scientific laws against your data, works out why they fall short, and steers symbolic regression towards better equations."
      />

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
