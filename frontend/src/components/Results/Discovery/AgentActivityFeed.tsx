/**
 * AgentActivityFeed Component
 * Log of what the discovery agent did (fits, PySR searches, notes, thoughts), newest first.
 * Scrollable: new rows slide in at the top and the view stays there unless the reader has
 * scrolled down to read older ones. Tabs narrow it to one kind of step. With `fill` it takes
 * the height of its container; with `live` off (a finished run) rows do not animate in.
 */

import React, { useLayoutEffect, useMemo, useRef, useState } from 'react';
import { fmtR2 } from '@utils/discovery';
import { formatClock } from '@utils/formatting';
import type { AgentEvent } from '@/types';
import { feedGroup, type FeedGroup } from './agentState';

const KIND_ICONS: Record<string, string> = {
  thought: 'pi pi-comment',
  fit: 'pi pi-chart-line',
  note: 'pi pi-book',
  search_started: 'pi pi-play',
  search_completed: 'pi pi-check-circle',
  search_failed: 'pi pi-times-circle',
  search_cancelled: 'pi pi-ban',
  wait: 'pi pi-clock',
  tool: 'pi pi-search',
  agent: 'pi pi-android',
};

const KIND_COLORS: Record<string, string> = {
  search_completed: 'text-green-600',
  search_failed: 'text-red-500',
  note: 'text-amber-500',
  thought: 'text-muted',
};

const KIND_LABELS: Record<string, string> = {
  thought: 'Reasoning',
  fit: 'Formula fitted',
  note: 'Working note',
  search_started: 'Search started',
  search_completed: 'Search finished',
  search_failed: 'Search failed',
  search_cancelled: 'Search cancelled',
  wait: 'Waiting',
  tool: 'Looked at the data',
  agent: 'Agent',
};

const FILTERS: { id: FeedGroup | 'all'; label: string }[] = [
  { id: 'all', label: 'All' },
  { id: 'reasoning', label: 'Reasoning' },
  { id: 'formulas', label: 'Formulas' },
  { id: 'cluster', label: 'Cluster' },
  { id: 'notes', label: 'Notes' },
];

/** Rows rendered at first; a finished run can hold up to 2000 events */
const PAGE_ROWS = 300;

/** Distance from the top (px) within which the feed keeps following new rows */
const FOLLOW_THRESHOLD = 40;

// Row keys follow the event objects, not their position: once the activity buffer is full, every
// new event shifts the positions of all the others, which would remount (and re-animate) each row.
const rowIds = new WeakMap<AgentEvent, number>();
let nextRowId = 0;
const rowKey = (event: AgentEvent): number => {
  let id = rowIds.get(event);
  if (id === undefined) {
    id = nextRowId++;
    rowIds.set(event, id);
  }
  return id;
};

/** Text of an event; older or partial events may lack it */
const eventText = (event: AgentEvent): string => {
  if (typeof event.text === 'string' && event.text) return event.text;
  const subject = event.search_id ?? event.model_id ?? '';
  const kind = (event.kind || 'step').replace(/_/g, ' ');
  return subject ? `${subject}: ${kind}` : kind;
};

interface AgentActivityFeedProps {
  events: AgentEvent[];
  title: string;
  /** Take the full height of the container (the list scrolls inside it) */
  fill?: boolean;
  /** Animate rows as they arrive; off when replaying a finished run */
  live?: boolean;
}

export const AgentActivityFeed: React.FC<AgentActivityFeedProps> = React.memo(
  ({ events, title, fill = false, live = true }) => {
    const scrollRef = useRef<HTMLUListElement>(null);
    const [following, setFollowing] = useState(true);
    const [filter, setFilter] = useState<FeedGroup | 'all'>('all');
    const [limit, setLimit] = useState(PAGE_ROWS);

    // Newest first
    const matching = useMemo(
      () =>
        (filter === 'all' ? events : events.filter((event) => feedGroup(event.kind) === filter))
          .slice()
          .reverse(),
      [events, filter]
    );
    const shown = matching.length > limit ? matching.slice(0, limit) : matching;
    // The length stops changing once the buffer is full, so follow the newest event instead
    const latest = events[events.length - 1];

    useLayoutEffect(() => {
      const el = scrollRef.current;
      if (el && following) el.scrollTo({ top: 0, behavior: 'smooth' });
    }, [latest, following, filter]);

    const handleScroll = () => {
      const el = scrollRef.current;
      if (!el) return;
      setFollowing(el.scrollTop < FOLLOW_THRESHOLD);
    };

    return (
      <div className={fill ? 'text-left h-full flex flex-col' : 'text-left'}>
        <div className="mb-2 flex flex-wrap items-center gap-2">
          <h4 className="m-0 text-sm font-semibold text-secondary flex items-center gap-2">
            <i className="pi pi-bolt text-brand-500" aria-hidden="true"></i>
            {title}
          </h4>
          {events.length > 0 && (
            <>
              <span className="text-xs text-muted tabular-nums">
                {filter === 'all' ? events.length : `${matching.length} of ${events.length}`} steps
              </span>
              <div
                role="group"
                aria-label="Show only"
                className="ml-auto flex flex-wrap gap-1 bg-surface-alt rounded-lg p-0.5"
              >
                {FILTERS.map((f) => (
                  <button
                    key={f.id}
                    type="button"
                    aria-pressed={filter === f.id}
                    onClick={() => {
                      setFilter(f.id);
                      setFollowing(true);
                    }}
                    className={`min-h-8 px-3 rounded-md text-xs border-0 cursor-pointer ${
                      filter === f.id
                        ? 'bg-surface text-primary font-semibold shadow-sm'
                        : 'bg-transparent text-secondary font-medium'
                    }`}
                  >
                    {f.label}
                  </button>
                ))}
              </div>
            </>
          )}
        </div>
        <div className={fill ? 'relative flex-1 min-h-0' : 'relative'}>
          <ul
            ref={scrollRef}
            onScroll={handleScroll}
            aria-live={live ? 'polite' : undefined}
            aria-label={title}
            className={`agent-feed-scroll ${fill ? 'h-full' : 'max-h-[28rem]'} overflow-y-auto bg-surface-alt rounded-lg border border-[var(--color-border)] divide-y divide-[var(--color-border)]`}
          >
            {events.length === 0 && (
              <li className="flex items-start gap-3 px-3 py-2 text-sm">
                <i className="pi pi-info-circle text-brand-500 mt-0.5" aria-hidden="true"></i>
                <span className="flex-1 min-w-0 text-secondary">
                  The agent&rsquo;s steps will appear here.
                </span>
              </li>
            )}
            {events.length > 0 && shown.length === 0 && (
              <li className="px-3 py-2 text-sm text-muted">Nothing of this kind yet.</li>
            )}
            {shown.map((event) => (
              <li
                key={rowKey(event)}
                className={`flex items-start gap-3 px-3 py-2 text-sm ${live ? 'agent-feed-row-enter' : ''}`}
              >
                <i
                  className={`${KIND_ICONS[event.kind] ?? 'pi pi-circle'} ${KIND_COLORS[event.kind] ?? 'text-brand-500'} mt-0.5`}
                  aria-hidden="true"
                ></i>
                <span className="flex-1 min-w-0 flex flex-col gap-0.5">
                  <span className="text-[11px] font-semibold uppercase tracking-wide text-muted">
                    {KIND_LABELS[event.kind] ?? event.kind.replace(/_/g, ' ')}
                  </span>
                  <span
                    className={`break-words ${event.kind === 'thought' ? 'italic text-muted' : 'text-secondary'}`}
                  >
                    {eventText(event)}
                  </span>
                </span>
                {typeof event.cv_r2 === 'number' && (
                  <span className="self-center shrink-0 text-xs font-semibold tabular-nums px-2 py-0.5 rounded-full bg-green-50 text-green-800">
                    R² {fmtR2(event.cv_r2)}
                  </span>
                )}
                {typeof event.t === 'number' && (
                  <span className="text-xs text-muted tabular-nums shrink-0">
                    {formatClock(event.t)}
                  </span>
                )}
              </li>
            ))}
            {matching.length > shown.length && (
              <li className="px-3 py-2 text-center">
                <button
                  type="button"
                  onClick={() => setLimit(limit + PAGE_ROWS)}
                  className="min-h-8 px-3 rounded-md text-xs border-0 cursor-pointer bg-transparent text-link font-medium"
                >
                  Show older steps ({matching.length - shown.length} more)
                </button>
              </li>
            )}
          </ul>
          {!following && (
            <button
              type="button"
              onClick={() => setFollowing(true)}
              className="absolute top-2 left-1/2 -translate-x-1/2 rounded-full bg-brand-500 text-white text-xs px-3 py-1 shadow-md flex items-center gap-1"
            >
              <i className="pi pi-arrow-up text-xs" aria-hidden="true"></i>
              Latest
            </button>
          )}
        </div>
      </div>
    );
  }
);

AgentActivityFeed.displayName = 'AgentActivityFeed';

export default AgentActivityFeed;
