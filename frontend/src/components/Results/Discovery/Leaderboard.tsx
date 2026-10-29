/**
 * Leaderboard Component
 * Ranked table of every fitted model with its score bar against the noise ceiling, verdict and
 * expandable diagnosis. Expansion and "show all" are controlled by the parent so model-id links
 * elsewhere in the report can open a row.
 */

import React from 'react';
import { Tag } from 'primereact/tag';
import { MathJax, MathJaxContext } from 'better-react-mathjax';
import { escapeForAsciiMath } from '@utils/formatting';
import { mathJaxConfig } from '@utils/mathjax';
import { asText, fmtR2, metricShortLabel, metricValue } from '@utils/discovery';
import type { LeaderboardEntry, MetricBasis, ModelKind, ModelVerdict } from '@/types';

export const MAX_ROWS = 10;

const KIND_TAG: Record<ModelKind, { label: string; className: string }> = {
  classic: { label: 'Classic law', className: 'bg-[rgba(34,197,94,0.12)] text-green-700' },
  custom: { label: 'Agent formula', className: 'bg-[rgba(139,92,246,0.12)] text-violet-700' },
  symbolic: { label: 'Symbolic', className: 'bg-brand-50 text-brand-500' },
  literature: { label: 'Published law', className: 'bg-[rgba(245,158,11,0.12)] text-amber-700' },
};

const VERDICT_TAG: Record<
  ModelVerdict,
  {
    label: string;
    hint: string;
    severity: 'success' | 'info' | 'warning' | 'danger' | 'secondary';
  }
> = {
  good: {
    label: 'Best possible',
    hint: 'As accurate as this data allows: what it does not explain looks like measurement noise.',
    severity: 'success',
  },
  adequate: {
    label: 'Nearly best',
    hint: 'Close to the best accuracy this data allows, but some pattern is left unexplained or some terms are uncertain.',
    severity: 'info',
  },
  poor: {
    label: 'Misses a pattern',
    hint: 'Clearly below the best accuracy this data allows: part of the relationship is not captured.',
    severity: 'warning',
  },
  failed: {
    label: 'Fit failed',
    hint: 'The equation could not be fitted to the data.',
    severity: 'danger',
  },
  no_signal: {
    label: 'Nothing to predict',
    hint: 'Even a flexible model cannot predict the target from these variables.',
    severity: 'secondary',
  },
};

/** Horizontal R² bar with a marker at the noise ceiling (the marker is clamped to the bar) */
const R2Bar: React.FC<{ value: number | null; ceiling: number | null }> = ({ value, ceiling }) => {
  const pct = (v: number) => `${Math.max(0, Math.min(1, v)) * 100}%`;
  return (
    <div className="flex items-center gap-2 min-w-[9rem]">
      <span className="tabular-nums text-sm w-12 text-right">{fmtR2(value)}</span>
      <div className="relative flex-1 h-2 rounded-full bg-surface-alt border border-[var(--color-border)]">
        {typeof value === 'number' && (
          <div
            className="absolute inset-y-0 left-0 rounded-full bg-brand-500"
            style={{ width: pct(value) }}
          />
        )}
        {typeof ceiling === 'number' && (
          <div
            className="absolute -inset-y-1 w-0.5 bg-red-500"
            style={{ left: pct(ceiling) }}
            title={`Noise ceiling ≈ ${ceiling.toFixed(3)}`}
          />
        )}
      </div>
    </div>
  );
};

interface RowProps {
  entry: LeaderboardEntry;
  rank: number;
  ceiling: number | null;
  basis: MetricBasis;
  headline: boolean;
  agentPick: boolean;
  open: boolean;
  highlighted: boolean;
  onToggle: () => void;
}

const LeaderboardRow: React.FC<RowProps> = ({
  entry,
  rank,
  ceiling,
  basis,
  headline,
  agentPick,
  open,
  highlighted,
  onToggle,
}) => {
  const kind = KIND_TAG[entry.kind] ?? KIND_TAG.custom;
  const verdict = VERDICT_TAG[entry.verdict] ?? VERDICT_TAG.poor;
  const reasons = (entry.reasons ?? []).map(asText).filter(Boolean);

  return (
    <>
      <tr
        id={`model-${entry.model_id}`}
        className={`border-t border-[var(--color-border)] hover:bg-surface-alt cursor-pointer scroll-mt-24 transition-colors ${
          highlighted ? 'bg-brand-50' : ''
        }`}
        onClick={onToggle}
        aria-expanded={open}
      >
        <td className="px-3 py-2 text-muted tabular-nums">{rank}</td>
        <td className="px-3 py-2">
          <div className="flex flex-wrap items-center gap-2">
            <code className="text-xs font-mono px-1.5 py-0.5 rounded bg-surface-alt text-secondary border border-[var(--color-border)]">
              {entry.model_id}
            </code>
            <span className="font-medium text-primary">{entry.label}</span>
            <Tag value={kind.label} className={`text-xs px-2 py-0.5 ${kind.className}`} />
            {headline && (
              <Tag
                value="Recommended"
                icon="pi pi-star-fill"
                severity="success"
                className="text-xs"
              />
            )}
            {agentPick && <Tag value="Agent pick" severity="info" className="text-xs" />}
          </div>
          <div className="text-xs text-muted mt-0.5">{(entry.features ?? []).join(', ')}</div>
        </td>
        <td className="px-3 py-2">
          <R2Bar value={metricValue(entry)} ceiling={ceiling} />
        </td>
        {basis === 'holdout' && (
          <td className="px-3 py-2 text-right tabular-nums text-muted hidden md:table-cell">
            {fmtR2(entry.cv_r2)}
          </td>
        )}
        <td className="px-3 py-2 text-center tabular-nums hidden sm:table-cell">
          {entry.complexity}
        </td>
        <td className="px-3 py-2">
          <span title={verdict.hint}>
            <Tag
              value={verdict.label}
              severity={verdict.severity}
              className="text-xs whitespace-nowrap"
            />
          </span>
        </td>
        <td className="px-2 py-2 text-muted">
          <i className={`pi ${open ? 'pi-chevron-up' : 'pi-chevron-down'}`} aria-hidden="true"></i>
        </td>
      </tr>
      {open && (
        <tr className="bg-surface-alt">
          <td></td>
          <td colSpan={basis === 'holdout' ? 6 : 5} className="px-3 pb-4 pt-1">
            <div className="overflow-x-auto py-2 mathjax-equation">
              <MathJaxContext config={mathJaxConfig}>
                <MathJax inline dynamic>
                  {`\`${escapeForAsciiMath(entry.equation)}\``}
                </MathJax>
              </MathJaxContext>
            </div>
            {reasons.length > 0 && (
              <>
                <h5 className="text-xs font-semibold text-secondary uppercase tracking-wide mt-2 mb-1">
                  Diagnosis
                </h5>
                <ul className="list-disc pl-5 space-y-1 text-sm text-secondary">
                  {reasons.map((r, i) => (
                    <li key={i}>{r}</li>
                  ))}
                </ul>
              </>
            )}
            <p className="text-xs text-muted mt-2">
              Cross-validated R² {fmtR2(entry.cv_r2)}
              {typeof entry.cv_se === 'number'
                ? ` (fold RMSE SE ${entry.cv_se.toPrecision(3)})`
                : ''}
              {' · '}
              {entry.n_params} fitted constants
              {entry.target_transform ? ` · fitted on ${entry.target_transform}(target)` : ''}
              {entry.source ? ` · from ${entry.source}` : ''}
              {entry.n_undefined
                ? ` · undefined on ${entry.n_undefined} rows (counted as errors)`
                : ''}
            </p>
          </td>
        </tr>
      )}
    </>
  );
};

interface LeaderboardProps {
  entries: LeaderboardEntry[];
  ceiling: number | null;
  basis: MetricBasis;
  holdoutN: number | null;
  headlineId: string | null;
  agentPicks: ReadonlySet<string>;
  openIds: ReadonlySet<string>;
  highlightId: string | null;
  showAll: boolean;
  onToggleRow: (modelId: string) => void;
  onToggleShowAll: () => void;
}

export const Leaderboard: React.FC<LeaderboardProps> = ({
  entries,
  ceiling,
  basis,
  holdoutN,
  headlineId,
  agentPicks,
  openIds,
  highlightId,
  showAll,
  onToggleRow,
  onToggleShowAll,
}) => {
  const rows = showAll ? entries : entries.slice(0, MAX_ROWS);
  return (
    <>
      <div className="overflow-x-auto rounded-lg border border-[var(--color-border)]">
        <table className="w-full text-sm">
          <thead className="bg-surface-alt text-left text-xs text-muted uppercase tracking-wide">
            <tr>
              <th className="px-3 py-2">#</th>
              <th className="px-3 py-2">Model</th>
              <th className="px-3 py-2 normal-case">{metricShortLabel(basis, holdoutN)}</th>
              {basis === 'holdout' && (
                <th className="px-3 py-2 text-right hidden md:table-cell normal-case">CV R²</th>
              )}
              <th className="px-3 py-2 text-center hidden sm:table-cell">Complexity</th>
              <th className="px-3 py-2">Fit quality</th>
              <th className="px-2 py-2">
                <span className="sr-only">Details</span>
              </th>
            </tr>
          </thead>
          <tbody>
            {rows.map((entry, i) => (
              <LeaderboardRow
                key={entry.model_id}
                entry={entry}
                rank={i + 1}
                ceiling={ceiling}
                basis={basis}
                headline={!!entry.is_headline || entry.model_id === headlineId}
                agentPick={entry.agent_recommended ?? agentPicks.has(entry.model_id)}
                open={openIds.has(entry.model_id)}
                highlighted={entry.model_id === highlightId}
                onToggle={() => onToggleRow(entry.model_id)}
              />
            ))}
          </tbody>
        </table>
      </div>
      {entries.length > MAX_ROWS && (
        <button
          type="button"
          className="mt-2 text-sm text-brand-500 hover:underline"
          onClick={onToggleShowAll}
        >
          {showAll ? 'Show fewer' : `Show all ${entries.length} models`}
        </button>
      )}
    </>
  );
};

export default Leaderboard;
