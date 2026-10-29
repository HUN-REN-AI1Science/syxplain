/**
 * LiveDiscoveryPanels
 * Panels of the progress page that follow a running discovery agent: what it is thinking,
 * the best equation so far, a live leaderboard and the state of its cluster searches.
 */

import React from 'react';
import { fmtR2 } from '@utils/discovery';
import { formatClock } from '@utils/formatting';
import type { AgentEvent } from '@/types';
import type { LiveModel, LiveSearch, LiveSearchStatus } from './agentState';

/** Surface of every panel on the progress page */
export const CARD = 'bg-surface rounded-xl border border-[var(--color-border)] p-5';

// ============================================================================
// Current thought
// ============================================================================

interface CurrentThoughtProps {
  thought: AgentEvent | null;
  /** Shown before the agent has said anything */
  fallback: string;
  runningSearches: number;
}

const CurrentThoughtPanel: React.FC<CurrentThoughtProps> = ({
  thought,
  fallback,
  runningSearches,
}) => (
  <section
    aria-labelledby="current-thought-h"
    className="bg-brand-50 border border-brand-200 rounded-xl px-6 py-5 flex flex-col gap-3"
  >
    <div className="flex items-center gap-2.5">
      <span
        className="w-8 h-8 rounded-lg bg-brand-500 text-white inline-flex items-center justify-center"
        aria-hidden="true"
      >
        <i className="pi pi-comment" />
      </span>
      <h2 id="current-thought-h" className="text-sm font-semibold text-brand-800 m-0">
        {thought ? 'Thinking now' : 'Getting started'}
      </h2>
      {typeof thought?.t === 'number' && (
        <span className="ml-auto text-xs text-secondary tabular-nums">
          {formatClock(thought.t)}
        </span>
      )}
    </div>
    <p
      key={thought?.t ?? 'fallback'}
      className="m-0 text-lg leading-relaxed text-primary step-description-animate"
      aria-live="polite"
    >
      {thought?.text || fallback}
    </p>
    {runningSearches > 0 && (
      <p className="m-0 text-sm text-secondary">
        {runningSearches === 1
          ? '1 symbolic regression search is running on the cluster'
          : `${runningSearches} symbolic regression searches are running on the cluster`}
      </p>
    )}
  </section>
);

// ============================================================================
// Best equation so far
// ============================================================================

/** Step line of the best CV R² over the session; the y axis spans the scores seen */
const BestSparkline: React.FC<{ history: { t: number; cvR2: number }[]; endT: number }> = ({
  history,
  endT,
}) => {
  if (history.length < 2) return null;
  const W = 300;
  const H = 64;
  const span = Math.max(endT, history[history.length - 1].t, 1);
  // Not clamped at 0: early fits can score below 0, and clamping would flatten them to the floor
  const lo = Math.min(...history.map((p) => p.cvR2)) - 0.02;
  const hi = Math.min(1, Math.max(...history.map((p) => p.cvR2)) + 0.02);
  const x = (t: number) => (t / span) * W;
  const y = (v: number) => H - 4 - ((Math.max(v, lo) - lo) / Math.max(hi - lo, 1e-6)) * (H - 8);
  const path =
    history
      .map((p, i) => (i === 0 ? `M${x(p.t)} ${y(p.cvR2)}` : `H${x(p.t)} V${y(p.cvR2)}`))
      .join(' ') + ` H${W}`;
  const summary = history.map((p) => `${fmtR2(p.cvR2)} at ${formatClock(p.t)}`).join(', ');

  return (
    <figure className="m-0 flex flex-col gap-1">
      <svg
        viewBox={`0 0 ${W} ${H}`}
        width="100%"
        height={H}
        preserveAspectRatio="none"
        role="img"
        aria-label={`Best cross-validated R² over time: ${summary}`}
      >
        <path
          d={path}
          fill="none"
          stroke="var(--color-success)"
          strokeWidth={2}
          vectorEffect="non-scaling-stroke"
          strokeLinejoin="round"
        />
      </svg>
      <figcaption className="flex justify-between text-[11px] text-muted tabular-nums">
        <span>0:00</span>
        <span>best score as the agent works</span>
        <span>{formatClock(span)}</span>
      </figcaption>
    </figure>
  );
};

interface BestSoFarProps {
  best: LiveModel | undefined;
  history: { t: number; cvR2: number }[];
  endT: number;
}

const BestSoFarPanel: React.FC<BestSoFarProps> = ({ best, history, endT }) => (
  <section aria-labelledby="best-so-far-h" className={`${CARD} flex flex-col gap-3.5`}>
    <div className="flex items-center gap-2">
      <h2 id="best-so-far-h" className="m-0 text-[15px] font-semibold">
        Best equation so far
      </h2>
      {best && (
        <span className="ml-auto text-xs text-muted">
          <span className="font-mono">{best.modelId}</span>
          {best.t !== null && <> · found {formatClock(best.t)}</>}
        </span>
      )}
    </div>
    {best ? (
      <>
        <div className="bg-surface-alt border border-[var(--color-border)] rounded-lg px-4 py-3 font-mono text-sm leading-relaxed break-words">
          {best.expression || best.label}
        </div>
        <div className="flex items-baseline gap-2.5">
          <span className="text-3xl font-bold tabular-nums text-semantic-success">
            {fmtR2(best.cvR2)}
          </span>
          <span className="text-sm text-muted">cross-validated R²</span>
        </div>
        <BestSparkline history={history} endT={endT} />
        <p className="m-0 text-xs leading-normal text-muted">
          Scores are cross-validated while the agent searches. Before results are shown, every model
          is scored again on held-out data it has never seen.
        </p>
      </>
    ) : (
      <p className="m-0 text-sm text-muted">No equation has been scored yet.</p>
    )}
  </section>
);

// ============================================================================
// Leaderboard
// ============================================================================

const LEADERBOARD_ROWS = 5;

interface LiveLeaderboardProps {
  models: LiveModel[];
  hasRateLaws: boolean;
}

const LiveLeaderboardPanel: React.FC<LiveLeaderboardProps> = ({ models, hasRateLaws }) => {
  if (models.length < 2) return null;
  const top = models.slice(0, LEADERBOARD_ROWS);
  const lo = Math.max(0, Math.min(...top.map((m) => m.cvR2)) - 0.05);
  const width = (v: number) => `${Math.max(2, ((v - lo) / Math.max(1 - lo, 1e-6)) * 100)}%`;

  return (
    <section aria-labelledby="live-leaderboard-h" className={`${CARD} flex flex-col gap-3`}>
      <div className="flex items-center">
        <h2 id="live-leaderboard-h" className="m-0 text-[15px] font-semibold">
          Leaderboard
        </h2>
        <span className="ml-auto text-xs text-muted">{models.length} scored</span>
      </div>
      <ol className="m-0 p-0 list-none flex flex-col gap-2.5">
        {top.map((m, i) => (
          <li key={m.modelId} className="flex flex-col gap-1">
            <div className="flex items-baseline gap-2 text-sm">
              <span className="font-mono text-muted w-10 shrink-0">{m.modelId}</span>
              <span className="flex-1 min-w-0 truncate" title={m.expression || m.label}>
                {m.label || m.expression}
              </span>
              <span className="font-semibold tabular-nums">{fmtR2(m.cvR2)}</span>
            </div>
            <div className="ml-12 h-1 rounded-full bg-surface-alt overflow-hidden">
              <div
                className={`h-full rounded-full ${i === 0 ? 'bg-semantic-success' : 'bg-[var(--color-border-hover)]'}`}
                style={{ width: width(m.cvR2) }}
              />
            </div>
          </li>
        ))}
      </ol>
      {hasRateLaws && (
        <p className="m-0 text-xs text-muted">
          Rate laws are scored on the rate of change, so they are listed in the notebook instead.
        </p>
      )}
    </section>
  );
};

// ============================================================================
// Cluster searches
// ============================================================================

const STATUS_CHIP: Record<LiveSearchStatus, { label: string; className: string }> = {
  submitted: { label: 'Waiting for a node', className: 'bg-surface-alt text-secondary' },
  running: { label: 'Running', className: 'bg-brand-500 text-white' },
  completed: { label: 'Finished', className: 'bg-green-50 text-green-800' },
  failed: { label: 'Failed', className: 'bg-red-50 text-red-700' },
  cancelled: { label: 'Cancelled', className: 'bg-surface-alt text-secondary' },
};

const searchMeta = (s: LiveSearch): string => {
  if (s.status === 'completed') {
    const n = s.nEquations ?? 0;
    return `${n} equation${n === 1 ? '' : 's'}${s.bestCvR2 !== null ? ` · best ${fmtR2(s.bestCvR2)}` : ''}`;
  }
  if (s.status === 'running' && s.progress !== null) return `${Math.round(s.progress)}%`;
  return '';
};

const searchBar = (s: LiveSearch): { width: string; className: string } => {
  if (s.status === 'completed') return { width: '100%', className: 'bg-semantic-success' };
  if (s.status === 'running') return { width: `${s.progress ?? 0}%`, className: 'bg-brand-500' };
  return { width: '0%', className: '' };
};

const ClusterSearchesPanel: React.FC<{ searches: LiveSearch[] }> = ({ searches }) => {
  if (searches.length === 0) return null;
  return (
    <section aria-labelledby="cluster-searches-h" className={`${CARD} flex flex-col gap-3.5`}>
      <h2 id="cluster-searches-h" className="m-0 text-[15px] font-semibold">
        Searches on the cluster
      </h2>
      <ul className="m-0 p-0 list-none flex flex-col divide-y divide-[var(--color-border)]">
        {searches.map((s) => {
          const chip = STATUS_CHIP[s.status];
          const bar = searchBar(s);
          return (
            <li key={s.searchId} className="flex flex-col gap-1.5 py-3 first:pt-0 last:pb-0">
              <div className="flex items-center gap-2 text-sm">
                <span className="font-mono font-medium">{s.searchId}</span>
                <span
                  className={`text-[11px] font-semibold px-2 py-0.5 rounded-full ${chip.className}`}
                >
                  {chip.label}
                </span>
                <span className="ml-auto text-muted tabular-nums">{searchMeta(s)}</span>
              </div>
              <div className="h-1.5 rounded-full bg-surface-alt overflow-hidden">
                <div
                  className={`h-full rounded-full transition-[width] duration-slow ${bar.className}`}
                  style={{ width: bar.width }}
                />
              </div>
              {(s.rationale || s.features.length > 0) && (
                <span className="text-xs leading-normal text-secondary">
                  {s.rationale || `On ${s.features.join(', ')}`}
                </span>
              )}
            </li>
          );
        })}
      </ul>
    </section>
  );
};

// The progress page re-renders on every tick of its progress bar; the panels only change
// when the agent's activity does.
export const CurrentThought = React.memo(CurrentThoughtPanel);
export const BestSoFar = React.memo(BestSoFarPanel);
export const LiveLeaderboard = React.memo(LiveLeaderboardPanel);
export const ClusterSearches = React.memo(ClusterSearchesPanel);
