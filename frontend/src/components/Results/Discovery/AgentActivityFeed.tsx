/**
 * AgentActivityFeed Component
 * Live log of what the discovery agent is doing (fits, PySR searches, notes, thoughts).
 * Fixed-height and scrollable: new rows slide in at the bottom and the view follows them
 * unless the reader has scrolled up to read older ones.
 */

import React, { useEffect, useLayoutEffect, useRef, useState } from 'react';
import type { AgentEvent } from '@/types';

const KIND_ICONS: Record<string, string> = {
  thought: 'pi pi-comment',
  fit: 'pi pi-chart-line',
  note: 'pi pi-book',
  search_started: 'pi pi-play',
  search_progress: 'pi pi-spin pi-cog',
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

/** Distance from the bottom (px) within which the feed keeps following new rows */
const FOLLOW_THRESHOLD = 40;

const formatTime = (seconds: number): string => {
  const m = Math.floor(seconds / 60);
  const s = Math.floor(seconds % 60);
  return `${m}:${s.toString().padStart(2, '0')}`;
};

/** Text of an event; older or partial events may lack it */
const eventText = (event: AgentEvent): string => {
  if (typeof event.text === 'string' && event.text) return event.text;
  const subject = event.search_id ?? event.model_id ?? '';
  const progress = typeof event.progress === 'number' ? ` (${Math.round(event.progress)}%)` : '';
  if (event.kind === 'search_progress') return `${subject || 'Search'} running${progress}`;
  const kind = (event.kind || 'step').replace(/_/g, ' ');
  return subject ? `${subject}: ${kind}` : kind;
};

interface AgentActivityFeedProps {
  events: AgentEvent[];
  title?: string;
  /** Shown as the first row, before the agent has done anything */
  intro?: string;
}

export const AgentActivityFeed: React.FC<AgentActivityFeedProps> = ({
  events,
  title = 'What the AI scientist is doing',
  intro,
}) => {
  const scrollRef = useRef<HTMLUListElement>(null);
  const [following, setFollowing] = useState(true);

  // A progress ping is superseded by any later event of the same search (a newer ping,
  // or its completion/failure/cancellation), so each search shows one row. Rows keep
  // their position in the stream as key, so only genuinely new rows mount (and animate).
  const visible = events
    .map((event, idx) => ({ event, idx }))
    .filter(
      ({ event: e, idx: i }) =>
        e.kind !== 'search_progress' ||
        !e.search_id ||
        !events.slice(i + 1).some((later) => later.search_id === e.search_id)
    );

  useLayoutEffect(() => {
    const el = scrollRef.current;
    if (el && following) el.scrollTo({ top: el.scrollHeight, behavior: 'smooth' });
  }, [events.length, following]);

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

  if (visible.length === 0 && !intro) return null;

  return (
    <div className="max-w-xl mx-auto text-left mb-6">
      <h4 className="text-sm font-semibold text-secondary mb-2 flex items-center gap-2">
        <i className="pi pi-bolt text-brand-500" aria-hidden="true"></i>
        {title}
        {visible.length > 0 && (
          <span className="ml-auto text-xs font-normal text-muted tabular-nums">
            {visible.length} steps
          </span>
        )}
      </h4>
      <div className="relative">
        <ul
          ref={scrollRef}
          onScroll={handleScroll}
          aria-live="polite"
          aria-label={title}
          className="agent-feed-scroll max-h-72 overflow-y-auto bg-surface-alt rounded-lg border border-[var(--color-border)] divide-y divide-[var(--color-border)]"
        >
          {intro && (
            <li className="flex items-start gap-3 px-3 py-2 text-sm">
              <i className="pi pi-info-circle text-brand-500 mt-0.5" aria-hidden="true"></i>
              <span className="flex-1 min-w-0 text-secondary">{intro}</span>
            </li>
          )}
          {visible.map(({ event, idx }) => (
            <li
              key={`${idx}-${event.kind}`}
              className="flex items-start gap-3 px-3 py-2 text-sm agent-feed-row-enter"
            >
              <i
                className={`${KIND_ICONS[event.kind] ?? 'pi pi-circle'} ${KIND_COLORS[event.kind] ?? 'text-brand-500'} mt-0.5`}
                aria-hidden="true"
              ></i>
              <span
                className={`flex-1 min-w-0 break-words ${event.kind === 'thought' ? 'italic text-muted' : 'text-secondary'}`}
              >
                {eventText(event)}
              </span>
              {typeof event.t === 'number' && (
                <span className="text-xs text-muted tabular-nums shrink-0">
                  {formatTime(event.t)}
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
};

export default AgentActivityFeed;
