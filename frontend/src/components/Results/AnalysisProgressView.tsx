/**
 * AnalysisProgressView Component
 * Live workspace for a running analysis: the pipeline steps with the overall progress, what the
 * discovery agent is thinking, its lab notebook, and beside them the best equation so far, a
 * live leaderboard and the searches running on the cluster.
 */

import React, { useMemo } from 'react';
import { ProgressBar } from 'primereact/progressbar';
import { AgentActivityFeed } from './Discovery/AgentActivityFeed';
import {
  BestSoFar,
  CARD,
  ClusterSearches,
  CurrentThought,
  LiveLeaderboard,
} from './Discovery/LiveDiscoveryPanels';
import { deriveAgentState, withSearchProgress } from './Discovery/agentState';
import { formatClock } from '@utils/formatting';
import type { AgentEvent, ProgressPhase } from '@/types';

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
  /** Latest progress (%) of each cluster search */
  searchProgress?: Record<string, number>;
  /** Time spent in the current step, against how long it usually takes */
  stepTiming?: { elapsedS: number; expectedS: number | null };
  /** Pipeline phases (empty when the page was opened without them) */
  phases?: ProgressPhase[];
  /** Index of the running phase in `phases` (-1 before the first) */
  phaseIndex?: number;
}

/** Steps shorter than this are not worth a timing line */
const MIN_TIMED_STEP_S = 15;

// Stable defaults, so the memoised panels below are not re-rendered by a fresh empty value
const NO_EVENTS: AgentEvent[] = [];
const NO_PHASES: ProgressPhase[] = [];
const NO_PROGRESS: Record<string, number> = {};

type StepState = 'done' | 'active' | 'todo';

/** Consecutive phases of the same group merged into one step */
const groupSteps = (
  phases: ProgressPhase[],
  phaseIndex: number
): { label: string; state: StepState }[] => {
  const steps: { label: string; first: number; last: number }[] = [];
  phases.forEach((p, i) => {
    const label = p.group ?? p.label;
    const prev = steps[steps.length - 1];
    if (prev && prev.label === label) prev.last = i;
    else steps.push({ label, first: i, last: i });
  });
  return steps.map(({ label, first, last }) => ({
    label,
    state: phaseIndex > last ? 'done' : phaseIndex >= first ? 'active' : 'todo',
  }));
};

const STEP_PILL: Record<StepState, string> = {
  done: 'bg-green-50 text-green-800',
  active: 'bg-brand-500 text-white font-semibold',
  todo: 'bg-surface-alt text-secondary',
};

const formatDuration = (seconds: number): string =>
  seconds < 60 ? `${Math.round(seconds)}s` : formatClock(seconds);

const formatTypical = (seconds: number): string =>
  seconds < 60 ? `~${Math.round(seconds)}s` : `~${Math.round(seconds / 60)} min`;

export const AnalysisProgressView: React.FC<AnalysisProgressViewProps> = ({
  displayProgress,
  stepDescription,
  isInQueuePhase = false,
  isJobSubmitted = false,
  activity = NO_EVENTS,
  searchProgress = NO_PROGRESS,
  stepTiming,
  phases = NO_PHASES,
  phaseIndex = -1,
}) => {
  const showTiming =
    !isInQueuePhase &&
    stepTiming &&
    ((stepTiming.expectedS ?? 0) >= MIN_TIMED_STEP_S || stepTiming.elapsedS >= MIN_TIMED_STEP_S);

  const agent = useMemo(() => deriveAgentState(activity), [activity]);
  const searches = useMemo(
    () => withSearchProgress(agent.searches, searchProgress),
    [agent.searches, searchProgress]
  );
  const steps = useMemo(() => groupSteps(phases, phaseIndex), [phases, phaseIndex]);

  return (
    <div className="py-6 flex flex-col gap-6 text-left">
      {/* Header: what is happening, overall progress, and that leaving is fine */}
      <header className="flex flex-wrap items-end justify-between gap-4">
        <div className="flex flex-col gap-1.5 min-w-0" aria-live="polite">
          <div className="flex items-center gap-2 text-sm text-muted">
            <span
              className="w-2 h-2 rounded-full bg-brand-500 queue-pulse inline-block"
              aria-hidden="true"
            />
            {isInQueuePhase ? 'Waiting for resources' : 'Running'}
          </div>
          <h2 className="m-0 text-2xl font-heading font-bold text-primary">
            {isInQueuePhase ? (
              <>
                Queued<span className="queue-pulse">...</span>
              </>
            ) : (
              'The AI scientist is working on your data'
            )}
          </h2>
        </div>
        {!isInQueuePhase && (
          <span className="text-4xl font-heading font-bold text-brand-500 tabular-nums">
            {Math.floor(displayProgress)}%
          </span>
        )}
      </header>

      {/* Pipeline steps and the overall bar */}
      <nav
        aria-label="Analysis steps"
        className="bg-surface rounded-xl border border-[var(--color-border)] px-5 py-4 flex flex-col gap-3.5"
      >
        {steps.length > 0 && (
          <ol className="m-0 p-0 list-none flex flex-wrap items-center gap-x-1 gap-y-2">
            {steps.map((step, i) => (
              <li key={i} className="flex items-center gap-1">
                <span
                  aria-current={step.state === 'active' ? 'step' : undefined}
                  className={`inline-flex items-center gap-1.5 min-h-8 px-3 rounded-full text-sm ${STEP_PILL[step.state]}`}
                >
                  {step.state === 'done' && (
                    <>
                      <i className="pi pi-check text-xs" aria-hidden="true" />
                      <span className="sr-only">Done:</span>
                    </>
                  )}
                  {step.state === 'active' && (
                    <span
                      className="w-2 h-2 rounded-full bg-white queue-pulse inline-block"
                      aria-hidden="true"
                    />
                  )}
                  {step.label}
                </span>
                {i < steps.length - 1 && (
                  <i className="pi pi-angle-right text-xs text-muted" aria-hidden="true" />
                )}
              </li>
            ))}
          </ol>
        )}
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
        <div className="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1">
          <p
            key={stepDescription}
            className="m-0 text-sm font-medium text-secondary step-description-animate"
            aria-live="polite"
          >
            {stepDescription}
          </p>
          {showTiming && (
            <p className="m-0 text-xs text-muted tabular-nums">
              {formatDuration(stepTiming.elapsedS)} in this step
              {stepTiming.expectedS !== null && stepTiming.expectedS >= MIN_TIMED_STEP_S && (
                <> · usually {formatTypical(stepTiming.expectedS)}</>
              )}
            </p>
          )}
        </div>
        {isJobSubmitted && (
          <p className="m-0 text-xs text-muted">
            You can safely leave this page. Your results will be in the{' '}
            <span className="font-semibold">History</span> menu once the analysis is done.
          </p>
        )}
      </nav>

      <div className="flex flex-wrap items-start gap-6">
        {/* The agent: what it is thinking, and everything it has done */}
        <div className="flex flex-col gap-6 min-w-0" style={{ flex: '999 1 560px' }}>
          <CurrentThought
            thought={agent.thought}
            fallback="An AI agent designs equations from your data alone and steers symbolic regression towards better ones, then compares what it found with known scientific laws."
            runningSearches={agent.activeSearches}
          />
          <section className={CARD}>
            <AgentActivityFeed events={activity} title="Lab notebook" />
          </section>
        </div>

        {/* What it has found so far */}
        <aside className="flex flex-col gap-6 min-w-0" style={{ flex: '1 1 340px' }}>
          <BestSoFar best={agent.models[0]} history={agent.bestHistory} endT={agent.lastT} />
          <LiveLeaderboard models={agent.models} hasRateLaws={agent.hasRateLaws} />
          <ClusterSearches searches={searches} />
        </aside>
      </div>
    </div>
  );
};

export default AnalysisProgressView;
