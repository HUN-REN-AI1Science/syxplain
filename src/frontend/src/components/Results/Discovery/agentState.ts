/**
 * Live view of a discovery run, rebuilt from the agent's activity events: the latest thought,
 * every scored model ranked, the best score over time and the state of each cluster search.
 */

import type { AgentEvent } from '@/types';

export type FeedGroup = 'reasoning' | 'formulas' | 'cluster' | 'notes' | 'other';

export const feedGroup = (kind: string): FeedGroup => {
  if (kind === 'thought') return 'reasoning';
  if (kind === 'fit') return 'formulas';
  if (kind.startsWith('search_') || kind === 'wait') return 'cluster';
  if (kind === 'note') return 'notes';
  return 'other';
};

/** Events the live panels are rebuilt from; the agent's budget bounds how many a run has */
const RESULT_KINDS = new Set([
  'fit',
  'search_started',
  'search_completed',
  'search_failed',
  'search_cancelled',
]);

/**
 * Append an event, keeping at most `max` once the oldest narration (thoughts, notes, tool
 * steps) has made room: fits and search events are never dropped, so the leaderboard and
 * search panels stay complete on long runs. Mirrors the server's replay log.
 */
export const appendActivity = (
  prev: AgentEvent[],
  added: AgentEvent[],
  max: number
): AgentEvent[] => {
  const all = [...prev, ...added];
  let excess = all.length - max;
  if (excess <= 0) return all;
  return all.filter((e) => {
    if (excess > 0 && !RESULT_KINDS.has(e.kind)) {
      excess -= 1;
      return false;
    }
    return true;
  });
};

export interface LiveModel {
  modelId: string;
  label: string;
  expression: string;
  cvR2: number;
  /** Seconds into the agent session when it was scored */
  t: number | null;
}

export type LiveSearchStatus = 'submitted' | 'running' | 'completed' | 'failed' | 'cancelled';

export interface LiveSearch {
  searchId: string;
  features: string[];
  rationale: string;
  status: LiveSearchStatus;
  /** Cluster-reported progress (%) while running */
  progress: number | null;
  nEquations: number | null;
  bestCvR2: number | null;
}

export interface AgentState {
  thought: AgentEvent | null;
  /** Static models, best first; rate laws are scored on the derivative and kept out */
  models: LiveModel[];
  /** Each improvement of the best CV R² over time */
  bestHistory: { t: number; cvR2: number }[];
  /** Seconds into the agent session of the latest event */
  lastT: number;
  searches: LiveSearch[];
  /** Searches not finished yet (submitted or running) */
  activeSearches: number;
  hasRateLaws: boolean;
}

const isScored = (e: AgentEvent): e is AgentEvent & { model_id: string; cv_r2: number } =>
  (e.kind === 'fit' || e.kind === 'search_completed') &&
  typeof e.model_id === 'string' &&
  typeof e.cv_r2 === 'number';

export const deriveAgentState = (events: AgentEvent[]): AgentState => {
  let thought: AgentEvent | null = null;
  let lastT = 0;
  let hasRateLaws = false;
  const models = new Map<string, LiveModel>();
  const bestHistory: { t: number; cvR2: number }[] = [];
  const searches = new Map<string, LiveSearch>();

  const searchOf = (id: string): LiveSearch => {
    let s = searches.get(id);
    if (!s) {
      s = {
        searchId: id,
        features: [],
        rationale: '',
        status: 'submitted',
        progress: null,
        nEquations: null,
        bestCvR2: null,
      };
      searches.set(id, s);
    }
    return s;
  };

  for (const e of events) {
    if (typeof e.t === 'number') lastT = Math.max(lastT, e.t);
    if (e.kind === 'thought') thought = e;

    if (isScored(e)) {
      if (e.problem === 'dynamic') {
        hasRateLaws = true;
      } else {
        const t = typeof e.t === 'number' ? e.t : null;
        models.set(e.model_id, {
          modelId: e.model_id,
          label: e.label ?? '',
          expression: e.expression ?? '',
          cvR2: e.cv_r2,
          t,
        });
        const best = bestHistory[bestHistory.length - 1];
        if (t !== null && (!best || e.cv_r2 > best.cvR2)) bestHistory.push({ t, cvR2: e.cv_r2 });
      }
    }

    if (!e.search_id) continue;
    const s = searchOf(e.search_id);
    switch (e.kind) {
      case 'search_started':
        s.features = e.features ?? [];
        s.rationale = e.rationale ?? '';
        break;
      case 'search_completed':
        s.status = 'completed';
        s.nEquations = e.n_equations ?? null;
        s.bestCvR2 = typeof e.cv_r2 === 'number' ? e.cv_r2 : null;
        break;
      case 'search_failed':
        s.status = 'failed';
        break;
      case 'search_cancelled':
        s.status = 'cancelled';
        break;
    }
  }

  return {
    thought,
    models: [...models.values()].sort((a, b) => b.cvR2 - a.cvR2),
    bestHistory,
    lastT,
    searches: [...searches.values()],
    activeSearches: [...searches.values()].filter((s) => s.status === 'submitted').length,
    hasRateLaws,
  };
};

/**
 * Searches with the cluster's latest progress applied: a submitted search that reports progress
 * is running. Kept apart from `deriveAgentState` so frequent progress pings leave the rest of
 * the state (and the panels drawn from it) untouched.
 */
export const withSearchProgress = (
  searches: LiveSearch[],
  searchProgress: Record<string, number>
): LiveSearch[] =>
  searches.map((s): LiveSearch => {
    const progress = searchProgress[s.searchId];
    return s.status === 'submitted' && typeof progress === 'number'
      ? { ...s, status: 'running', progress }
      : s;
  });
