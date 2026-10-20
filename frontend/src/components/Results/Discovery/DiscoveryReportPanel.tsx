/**
 * DiscoveryReportPanel Component
 * Shows how the discovery agent reached the equations: classic-law baselines scored on
 * held-out (or, for small data, cross-validated) predictions, the diagnosed reasons each form
 * falls short, the agent's lab notebook and the symbolic regression searches it ran.
 */

import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { Tag } from 'primereact/tag';
import HelpButton from '@components/HelpButton';
import {
  asText,
  basisOf,
  fmtCeiling,
  metricLabel,
  rejectedFormModelId,
  rejectedFormText,
} from '@utils/discovery';
import { Leaderboard, MAX_ROWS } from './Leaderboard';
import { LiteratureSection } from './LiteratureSection';
import { ModelIdText } from './ModelIdText';
import { ShapSection } from './ShapSection';
import type { DiscoveryReport, NotebookEntry } from '@/types';

const NOTE_META: Record<NotebookEntry['kind'], { title: string; icon: string }> = {
  rejected_form: { title: 'Rejected forms', icon: 'pi pi-times-circle text-red-500' },
  insight: { title: 'Insights', icon: 'pi pi-bolt text-amber-500' },
  candidate: { title: 'Candidates', icon: 'pi pi-star text-green-600' },
  data_issue: { title: 'Data issues', icon: 'pi pi-exclamation-triangle text-amber-500' },
  hypothesis: { title: 'Open hypotheses', icon: 'pi pi-question-circle text-brand-500' },
};

const asArray = <T,>(x: T[] | null | undefined): T[] => (Array.isArray(x) ? x : []);

const Stat: React.FC<{ label: string; value: string; hint?: string }> = ({
  label,
  value,
  hint,
}) => (
  <div className="bg-surface rounded-lg border border-[var(--color-border)] px-4 py-3" title={hint}>
    <div className="text-xs text-muted">{label}</div>
    <div className="text-lg font-semibold text-primary tabular-nums">{value}</div>
  </div>
);

const Note: React.FC<{ tone: 'info' | 'warn'; children: React.ReactNode }> = ({
  tone,
  children,
}) => (
  <div
    className={`rounded-lg p-3 text-sm text-secondary flex items-start gap-2 border ${
      tone === 'warn'
        ? 'bg-[rgba(245,158,11,0.06)] border-[rgba(245,158,11,0.2)]'
        : 'bg-[rgba(59,130,246,0.06)] border-[rgba(59,130,246,0.2)]'
    }`}
  >
    <i
      className={`pi pi-info-circle mt-0.5 ${tone === 'warn' ? 'text-amber-500' : 'text-brand-500'}`}
      aria-hidden="true"
    ></i>
    <div className="min-w-0">{children}</div>
  </div>
);

interface DiscoveryReportPanelProps {
  report: DiscoveryReport;
  loadPlot?: (filename: string) => Promise<Blob>;
}

export const DiscoveryReportPanel: React.FC<DiscoveryReportPanelProps> = ({ report, loadPlot }) => {
  const [showAll, setShowAll] = useState(false);
  const [openIds, setOpenIds] = useState<Set<string>>(() => new Set());
  const [scrollTarget, setScrollTarget] = useState<{ id: string; at: number } | null>(null);
  const [highlightId, setHighlightId] = useState<string | null>(null);

  const agent = report.agent ?? ({} as Partial<DiscoveryReport['agent']>);
  const leaderboard = asArray(report.leaderboard);
  const notebook = asArray(report.notebook);
  const searches = asArray(report.searches);
  const split = report.split ?? { complete_rows: 0, train: 0, holdout: 0, scored_on: '' };
  const ceiling = typeof report.noise_ceiling_r2 === 'number' ? report.noise_ceiling_r2 : null;
  const ceilingText = fmtCeiling(ceiling, report.noise_ceiling_sd);
  const basis = basisOf(split.metric_basis ?? leaderboard[0]?.metric_basis);
  const holdoutN = split.holdout || null;

  const knownIds = useMemo(() => new Set(leaderboard.map((e) => e.model_id)), [leaderboard]);
  const agentPicks = useMemo(
    () => new Set(asArray(agent.recommended_models).map((r) => r.model_id)),
    [agent.recommended_models]
  );
  const headlineId =
    report.selection?.headline_model_id ?? leaderboard.find((e) => e.is_headline)?.model_id ?? null;

  const toggleRow = useCallback((id: string) => {
    setOpenIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }, []);

  /** Opens a leaderboard row (showing all rows if needed) and scrolls it into view */
  const selectModel = useCallback(
    (id: string) => {
      const idx = leaderboard.findIndex((e) => e.model_id === id);
      if (idx < 0) return;
      if (idx >= MAX_ROWS) setShowAll(true);
      setOpenIds((prev) => new Set(prev).add(id));
      setScrollTarget({ id, at: Date.now() });
    },
    [leaderboard]
  );

  useEffect(() => {
    if (!scrollTarget) return;
    document
      .getElementById(`model-${scrollTarget.id}`)
      ?.scrollIntoView({ behavior: 'smooth', block: 'center' });
    setHighlightId(scrollTarget.id);
    const timer = window.setTimeout(() => setHighlightId(null), 2000);
    return () => window.clearTimeout(timer);
  }, [scrollTarget]);

  const linkify = (text: unknown) => (
    <ModelIdText text={text} known={knownIds} onSelect={selectModel} />
  );
  const renderModelId = (id: string) =>
    knownIds.has(id) ? linkify(id) : <span className="font-mono">{id}</span>;

  const evidenceOf = (n: Partial<NotebookEntry>): string =>
    asText(n.evidence) || asArray(n.model_ids).join(', ');

  const rejected = [
    ...asArray(agent.rejected_forms).map((r) => ({
      text: rejectedFormText(r),
      evidence: rejectedFormModelId(r),
    })),
    ...notebook
      .filter((n) => n.kind === 'rejected_form')
      .map((n) => ({ text: asText(n.text), evidence: evidenceOf(n) })),
  ].filter((r) => r.text);
  const notesByKind = (['insight', 'data_issue', 'candidate', 'hypothesis'] as const)
    .map((kind) => ({
      kind,
      entries: [
        ...(kind === 'insight'
          ? asArray(agent.insights).map((t) => ({ text: asText(t), evidence: '' }))
          : []),
        ...notebook
          .filter((n) => n.kind === kind)
          .map((n) => ({ text: asText(n.text), evidence: evidenceOf(n) })),
      ].filter((n) => n.text),
    }))
    .filter((g) => g.entries.length > 0);
  const openQuestions = asArray(agent.open_questions).map(asText).filter(Boolean);
  const claimsFailed = asArray(agent.claims_failed);
  const lateSearches = asArray(agent.late_searches);
  const pickRejected = asArray(report.selection?.agent_pick_rejected);
  const excluded = asArray(split.excluded_columns);
  const renamed = Object.entries(report.aliases ?? {}).filter(([alias, col]) => alias !== col);
  const completedSearches = searches.filter((s) => s.status === 'completed').length;
  const nModels = report.n_models_total ?? leaderboard.length;

  return (
    <section className="rounded-xl border border-[var(--color-border)] bg-surface p-6 space-y-6">
      <div className="flex items-center gap-2">
        <h3 className="text-lg font-bold text-primary font-heading flex items-center gap-2">
          <i className="pi pi-sitemap text-brand-500" aria-hidden="true"></i>
          How the equations were found
        </h3>
        <HelpButton title="Discovery report">
          <h4>Classic laws first</h4>
          <p>
            An AI agent first fits classic, named laws (for example Mitscherlich, Langmuir or a
            power law) to your data. For each one it diagnoses <strong>why</strong> it falls short:
            a wrong curve shape, a missing variable, noise that grows with the value, or parameters
            the data cannot pin down.
          </p>
          <h4>Feature effects</h4>
          <p>
            SHAP values from a random forest show how much each variable contributes, the shape of
            its effect once the other variables are accounted for, and which pairs of variables
            interact (their effects depend on each other). The agent uses these to choose functional
            forms and multiplicative terms.
          </p>
          <h4>Then symbolic regression</h4>
          <p>
            It uses those diagnoses to steer symbolic regression searches on the computing cluster
            (which variables, which operators, and which starting formulas).
          </p>
          <h4>Fair scoring</h4>
          {basis === 'cv' ? (
            <p>
              This dataset is too small to set rows aside, so every model is scored by{' '}
              <strong>cross-validation</strong>: each row is predicted by a fit that did not see it.
              The red marker shows the <strong>noise ceiling</strong>: an estimate of the best
              accuracy a flexible model reaches on this data. A model near it leaves only noise
              unexplained.
            </p>
          ) : (
            <>
              <p>
                Every model is scored on {holdoutN ? `${holdoutN} held-out rows` : 'held-out rows'}{' '}
                that no model was trained on. The red marker shows the{' '}
                <strong>noise ceiling</strong>: an estimate of the best accuracy any model can reach
                on this data. A model near it leaves only noise unexplained.
              </p>
              <p>
                <strong>CV R²</strong> is the cross-validated score on the training rows, which the
                agent used to compare models and which the verdict is based on. On small datasets
                the held-out rows are few, so the two can differ noticeably; trust a model more when
                both agree.
              </p>
            </>
          )}
        </HelpButton>
      </div>

      {report.has_signal === false && (
        <div
          role="status"
          className="bg-red-50 border border-red-200 rounded-lg p-4 text-sm flex items-start gap-3"
        >
          <i className="pi pi-ban text-red-500 text-lg mt-0.5" aria-hidden="true"></i>
          <p className="text-primary">
            <span className="font-semibold">No detectable relationship:</span> even a flexible model
            cannot predict the target from these variables (noise-ceiling R² {ceilingText}). Treat
            every equation below as unsupported by the data.
          </p>
        </div>
      )}

      {agent.error && (
        <Note tone="warn">
          The discovery agent stopped early ({asText(agent.error)}). The results come from the
          baseline search and an automatic screen of classic laws.
        </Note>
      )}

      {agent.source === 'auto_fallback' && (
        <Note tone="warn">
          The agent did not write a final report; the summary below was assembled automatically from
          its session.
        </Note>
      )}

      {agent.summary && <p className="text-secondary leading-relaxed">{linkify(agent.summary)}</p>}

      {(lateSearches.length > 0 || agent.stale) && (
        <Note tone="info">
          Searches finished after the agent stopped
          {lateSearches.length > 0 ? `: ${lateSearches.join(', ')}` : ''}; their best models are
          included in the leaderboard but were not reviewed by the agent.
        </Note>
      )}

      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
        <Stat
          label="Noise ceiling (R²)"
          value={ceilingText}
          hint="Out-of-fold random-forest R²: a rough upper bound of achievable accuracy. Negative means a flexible model cannot predict the target at all."
        />
        <Stat
          label="Models tested"
          value={String(
            report.n_models_total ?? leaderboard.length + asArray(report.failed_fits).length
          )}
        />
        <Stat label="Symbolic searches" value={`${completedSearches}/${searches.length}`} />
        {basis === 'cv' ? (
          <Stat
            label="Scoring"
            value="CV only"
            hint="Dataset too small for a holdout: all scores are cross-validated"
          />
        ) : (
          <Stat
            label="Held-out rows"
            value={String(split.holdout || '—')}
            hint={split.scored_on ? `Scored on ${split.scored_on}` : undefined}
          />
        )}
      </div>

      {(typeof split.uploaded === 'number' || excluded.length > 0) && (
        <div className="text-sm text-secondary space-y-1">
          {typeof split.uploaded === 'number' && (
            <p>
              <i className="pi pi-database text-brand-500 mr-2" aria-hidden="true"></i>
              {split.complete_rows} of {split.uploaded} rows complete
              {split.dropped_incomplete
                ? ` (${split.dropped_incomplete} dropped for missing values)`
                : ''}
              .
            </p>
          )}
          {excluded.length > 0 && (
            <div>
              <p className="text-xs text-muted">Columns left out of the analysis:</p>
              <ul className="list-disc pl-5 text-xs text-secondary space-y-0.5">
                {excluded.map((c) => (
                  <li key={asText(c.column)}>
                    <span className="font-medium">{asText(c.column)}</span>
                    {c.reason ? `: ${asText(c.reason)}` : ''}
                  </li>
                ))}
              </ul>
            </div>
          )}
        </div>
      )}

      {report.shap?.available && (
        <ShapSection
          shap={report.shap}
          plots={asArray(report.shap_plots)}
          agreement={asArray(report.shap_agreement)}
          loadPlot={loadPlot}
        />
      )}

      {leaderboard.length > 0 && (
        <div>
          <h4 className="text-sm font-semibold text-secondary mb-2">
            Model leaderboard (
            {nModels > leaderboard.length
              ? `top ${leaderboard.length} of ${nModels}`
              : `${leaderboard.length} models`}
            ) · {metricLabel(basis, holdoutN)}
          </h4>
          <Leaderboard
            entries={leaderboard}
            ceiling={ceiling}
            basis={basis}
            holdoutN={holdoutN}
            headlineId={headlineId}
            agentPicks={agentPicks}
            openIds={openIds}
            highlightId={highlightId}
            showAll={showAll}
            onToggleRow={toggleRow}
            onToggleShowAll={() => setShowAll(!showAll)}
          />
          {pickRejected.length > 0 && (
            <div className="mt-3 text-sm text-secondary">
              <p className="text-xs text-muted mb-1">Agent picks the selector did not recommend:</p>
              <ul className="list-disc pl-5 space-y-0.5">
                {pickRejected.map((p, i) => (
                  <li key={i}>
                    {renderModelId(asText(p.model_id))}: {linkify(p.reason)}
                  </li>
                ))}
              </ul>
            </div>
          )}
        </div>
      )}

      {rejected.length > 0 && (
        <div>
          <h4 className="text-sm font-semibold text-secondary mb-2 flex items-center gap-2">
            <i className={NOTE_META.rejected_form.icon} aria-hidden="true"></i>
            Why these laws didn't fit
          </h4>
          <ul className="space-y-2">
            {rejected.map((r, i) => (
              <li
                key={i}
                className="text-sm text-secondary bg-surface-alt rounded-lg px-3 py-2 border border-[var(--color-border)]"
              >
                {linkify(r.text)}
                {r.evidence && (
                  <span className="text-xs text-muted ml-2">({linkify(r.evidence)})</span>
                )}
              </li>
            ))}
          </ul>
        </div>
      )}

      {notesByKind.map(({ kind, entries }) => (
        <div key={kind}>
          <h4 className="text-sm font-semibold text-secondary mb-2 flex items-center gap-2">
            <i className={NOTE_META[kind].icon} aria-hidden="true"></i>
            {NOTE_META[kind].title}
          </h4>
          <ul className="list-disc pl-5 space-y-1 text-sm text-secondary">
            {entries.map((n, i) => (
              <li key={i}>
                {linkify(n.text)}
                {n.evidence && (
                  <span className="text-xs text-muted ml-2">({linkify(n.evidence)})</span>
                )}
              </li>
            ))}
          </ul>
        </div>
      ))}

      {openQuestions.length > 0 && (
        <div>
          <h4 className="text-sm font-semibold text-secondary mb-2">Open questions</h4>
          <ul className="list-disc pl-5 space-y-1 text-sm text-secondary">
            {openQuestions.map((q, i) => (
              <li key={i}>{linkify(q)}</li>
            ))}
          </ul>
        </div>
      )}

      {claimsFailed.length > 0 && (
        <div>
          <h4 className="text-xs font-semibold text-muted mb-1">
            Unverified claims (statements the agent made that its results did not confirm)
          </h4>
          <ul className="list-disc pl-5 space-y-0.5 text-xs text-muted">
            {claimsFailed.map((c, i) => (
              <li key={i}>
                {asText(c.text)}
                {c.issue ? ` (${asText(c.issue)})` : ''}
              </li>
            ))}
          </ul>
        </div>
      )}

      {report.literature && (
        <LiteratureSection literature={report.literature} renderModelId={renderModelId} />
      )}

      {searches.length > 0 && (
        <details className="group">
          <summary className="text-sm font-semibold text-secondary cursor-pointer select-none">
            Symbolic regression searches ({searches.length})
          </summary>
          <ul className="mt-2 space-y-2">
            {searches.map((s) => (
              <li
                key={s.search_id}
                className="text-sm bg-surface-alt rounded-lg px-3 py-2 border border-[var(--color-border)]"
              >
                <div className="flex flex-wrap items-center gap-2">
                  <span className="font-mono text-xs">{s.search_id}</span>
                  <Tag
                    value={s.status}
                    severity={
                      s.status === 'completed'
                        ? 'success'
                        : s.status === 'failed'
                          ? 'danger'
                          : 'info'
                    }
                    className="text-xs"
                  />
                  {lateSearches.includes(s.search_id) && (
                    <Tag value="not reviewed" severity="warning" className="text-xs" />
                  )}
                  <span className="text-xs text-muted">
                    {asArray(s.features).join(', ')} · operators{' '}
                    {[...asArray(s.binary_operators), ...asArray(s.unary_operators)].join(' ')}
                    {s.target_transform ? ` · ${s.target_transform}(target)` : ''}
                    {typeof s.best_cv_r2 === 'number'
                      ? ` · best CV R² ${s.best_cv_r2.toFixed(3)}`
                      : ''}
                  </span>
                  {s.best_model_id && knownIds.has(s.best_model_id) && (
                    <span className="text-xs text-muted">best: {linkify(s.best_model_id)}</span>
                  )}
                </div>
                {s.rationale && <p className="text-secondary mt-1">{asText(s.rationale)}</p>}
                {s.error && <p className="text-red-500 text-xs mt-1">{asText(s.error)}</p>}
              </li>
            ))}
          </ul>
        </details>
      )}

      {renamed.length > 0 && (
        <p className="text-xs text-muted">
          Variable names in equations:{' '}
          {renamed.map(([alias, col], i) => (
            <span key={alias}>
              {i > 0 && ', '}
              <code>{alias}</code> = {col}
            </span>
          ))}
        </p>
      )}
    </section>
  );
};

export default DiscoveryReportPanel;
