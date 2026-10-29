/**
 * AgentActivityFeed Component
 * Live log of what the discovery agent is doing (fits, PySR searches, notes, thoughts).
 * Fixed-height and scrollable: new rows slide in at the bottom and the view follows them
 * unless the reader has scrolled up to read older ones. Tabs narrow it to one kind of step.
 */

import React, { useEffect, useLayoutEffect, useRef, useState } from 'react';
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

/** Distance from the bottom (px) within which the feed keeps following new rows */
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
}

export const AgentActivityFeed: React.FC<AgentActivityFeedProps> = React.memo(
  ({ events, title }) => {
    const scrollRef = useRef<HTMLUListElement>(null);
    const [following, setFollowing] = useState(true);
    const [filter, setFilter] = useState<FeedGroup | 'all'>('all');

    const shown =
      filter === 'all' ? events : events.filter((event) => feedGroup(event.kind) === filter);
    // The length stops changing once the buffer is full, so follow the newest event instead
    const latest = events[events.length - 1];

    useLayoutEffect(() => {
      const el = scrollRef.current;
      if (el && following) el.scrollTo({ top: el.scrollHeight, behavior: 'smooth' });
    }, [latest, following, filter]);

    // Re-follow when the feed is first shown with existing history
    useEffect(() => {
      const el = scrollRef.current;
      if (el) el.scrollTop = el.scrollHeight;
    }, []);

    const handleScroll = () => {
      const el = scrollRef.current;
      if (!el) return;
      setFollowing(el.scrollHeight - el.scrollTop - el.clientHeight < FOLLOW_THRESHOLD);
    };

    return (
      <div className="text-left">
        <div className="mb-2 flex flex-wrap items-center gap-2">
          <h4 className="m-0 text-sm font-semibold text-secondary flex items-center gap-2">
            <i className="pi pi-bolt text-brand-500" aria-hidden="true"></i>
            {title}
          </h4>
          {events.length > 0 && (
            <>
              <span className="text-xs text-muted tabular-nums">
                {filter === 'all' ? events.length : `${shown.length} of ${events.length}`} steps
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
        <div className="relative">
          <ul
            ref={scrollRef}
            onScroll={handleScroll}
            aria-live="polite"
            aria-label={title}
            className="agent-feed-scroll max-h-[28rem] overflow-y-auto bg-surface-alt rounded-lg border border-[var(--color-border)] divide-y divide-[var(--color-border)]"
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
                className="flex items-start gap-3 px-3 py-2 text-sm agent-feed-row-enter"
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
          </ul>
          {!following && (
            <button
              type="button"
              onClick={() => setFollowing(true)}
              className="absolute bottom-2 left-1/2 -translate-x-1/2 rounded-full bg-brand-500 text-white text-xs px-3 py-1 shadow-md flex items-center gap-1"
            >
              <i className="pi pi-arrow-down text-xs" aria-hidden="true"></i>
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
