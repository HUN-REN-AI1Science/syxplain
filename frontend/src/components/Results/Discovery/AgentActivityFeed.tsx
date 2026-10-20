/**
 * AgentActivityFeed Component
 * Live log of what the discovery agent is doing (fits, PySR searches, notes, thoughts)
 */

import React from 'react';
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
  /** Maximum number of rows shown (most recent) */
  limit?: number;
  title?: string;
}

export const AgentActivityFeed: React.FC<AgentActivityFeedProps> = ({
  events,
  limit = 8,
  title = 'What the AI scientist is doing',
}) => {
  // A progress ping is superseded by any later event of the same search (a newer ping,
  // or its completion/failure/cancellation), so each search shows one row.
  const visible = events
    .filter(
      (e, i) =>
        e.kind !== 'search_progress' ||
        !e.search_id ||
        !events.slice(i + 1).some((later) => later.search_id === e.search_id)
    )
    .slice(-limit)
    .reverse();

  if (visible.length === 0) return null;

  return (
    <div className="max-w-xl mx-auto text-left mb-6" aria-live="polite">
      <h4 className="text-sm font-semibold text-secondary mb-2 flex items-center gap-2">
        <i className="pi pi-bolt text-brand-500" aria-hidden="true"></i>
        {title}
      </h4>
      <ul className="bg-surface-alt rounded-lg border border-[var(--color-border)] divide-y divide-[var(--color-border)]">
        {visible.map((event, idx) => (
          <li
            key={`${event.t ?? ''}-${event.kind}-${idx}`}
            className={`flex items-start gap-3 px-3 py-2 text-sm ${idx === 0 ? 'step-description-animate' : ''}`}
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
    </div>
  );
};

export default AgentActivityFeed;
