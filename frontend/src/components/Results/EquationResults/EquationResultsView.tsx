/**
 * EquationResultsView Component
 * Displays equation analysis results with MathJax rendering and interactive charts
 */

import React, { useState, useMemo } from 'react';
import { Tag } from 'primereact/tag';
import { Button } from 'primereact/button';
import { SplitButton } from 'primereact/splitbutton';
import { MathJax, MathJaxContext } from 'better-react-mathjax';
import {
  Chart as ChartJS,
  LinearScale,
  PointElement,
  LineElement,
  Tooltip,
  Legend,
  type TooltipItem,
} from 'chart.js';
import { Scatter } from 'react-chartjs-2';
import { escapeForAsciiMath } from '@utils/formatting';
import { mathJaxConfig } from '@utils/mathjax';
import { exportToCSV, exportToExcel } from '@utils/dataExport';
import { sanitizeText } from '@utils/security';
import { CitationLink } from '../CitationLink';
import {
  headlineReasonText,
  metricLabel,
  metricShortLabel,
  metricValue,
  originLabel,
  scatterBasisLabel,
  tiedModelIds,
  variableLegend,
} from '@utils/discovery';
import CitationText from './CitationText';
import HelpButton from '@components/HelpButton';
import type { DiscoverySelection, Equation, ScatterData, EquationResults } from '@/types';

// Register Chart.js components
ChartJS.register(LinearScale, PointElement, LineElement, Tooltip, Legend);

interface EquationResultsViewProps {
  data: EquationResults;
  targetVariable?: string | null;
  /**
   * The run has a discovery report: equations are usable even when the AI explanation
   * failed, so the "Analysis Failed" card is reserved for legacy runs.
   */
  hasDiscovery?: boolean;
  /** The selector's headline choice from the discovery report */
  selection?: DiscoverySelection;
  /** Shown right after the recommended equation (time series, rate law) */
  afterHero?: React.ReactNode;
  /** The evidence section is on the page, so the hero can link to it */
  hasEvidence?: boolean;
}

/** AsciiMath source "lhs = rhs"; the left-hand side is the target alias used by the equation */
const equationMath = (eq: Equation, targetVariable?: string | null): string => {
  const lhs = eq.target_alias || targetVariable;
  return `\`${lhs ? `${escapeForAsciiMath(lhs)} = ` : ''}${escapeForAsciiMath(eq.equation)}\``;
};

/** "where k = Kd_value, P = P_olsen" legend of the aliases an equation uses */
const VariablesLegend: React.FC<{ variables?: Record<string, string> }> = ({ variables }) => {
  const pairs = variableLegend(variables);
  if (pairs.length === 0) return null;
  return (
    <p className="mt-2 text-xs text-muted">
      where{' '}
      {pairs.map(([alias, col], i) => (
        <span key={alias}>
          {i > 0 && ', '}
          <code className="text-primary">{alias}</code> = {col}
        </span>
      ))}
    </p>
  );
};

// Interactive Scatter Plot Component
const ScatterPlot: React.FC<{ data: ScatterData }> = ({ data }) => {
  const chartData = useMemo(() => {
    const points = data.measured.map((m, i) => ({ x: m, y: data.predicted[i] }));

    // Calculate min/max for 1:1 line
    const allValues = [...data.measured, ...data.predicted];
    const minVal = Math.min(...allValues);
    const maxVal = Math.max(...allValues);
    const padding = (maxVal - minVal) * 0.05;

    return {
      datasets: [
        {
          label: 'Data Points',
          data: points,
          backgroundColor: 'rgba(0, 82, 204, 0.5)',
          borderColor: 'rgba(0, 82, 204, 0.8)',
          pointRadius: 4,
          pointHoverRadius: 6,
        },
        {
          label: '1:1 Line',
          data: [
            { x: minVal - padding, y: minVal - padding },
            { x: maxVal + padding, y: maxVal + padding },
          ],
          showLine: true,
          borderColor: 'rgba(220, 38, 38, 0.8)',
          borderDash: [5, 5],
          borderWidth: 2,
          pointRadius: 0,
          fill: false,
        },
      ],
    };
  }, [data]);

  const options = useMemo(() => {
    const allValues = [...data.measured, ...data.predicted];
    const minVal = Math.min(...allValues);
    const maxVal = Math.max(...allValues);
    const padding = (maxVal - minVal) * 0.1;

    return {
      responsive: true,
      maintainAspectRatio: true,
      aspectRatio: 1,
      plugins: {
        legend: {
          position: 'top' as const,
          labels: {
            usePointStyle: true,
            font: { size: 11 },
          },
        },
        tooltip: {
          callbacks: {
            label: (context: TooltipItem<'scatter'>) => {
              if (context.dataset.label === '1:1 Line') return '';
              return `Measured: ${context.parsed.x?.toFixed(3)}, Predicted: ${context.parsed.y?.toFixed(3)}`;
            },
          },
        },
      },
      scales: {
        x: {
          title: { display: true, text: 'Measured', font: { size: 12 } },
          min: minVal - padding,
          max: maxVal + padding,
          grid: { color: 'rgba(0, 0, 0, 0.05)' },
        },
        y: {
          title: { display: true, text: 'Predicted', font: { size: 12 } },
          min: minVal - padding,
          max: maxVal + padding,
          grid: { color: 'rgba(0, 0, 0, 0.05)' },
        },
      },
    };
  }, [data]);

  return (
    <div className="w-full max-w-sm sm:max-w-md mx-auto">
      <Scatter data={chartData} options={options} />
    </div>
  );
};

/** Everything shown about one equation: tags, formula, overview, terms, plot and sources */
const EquationDetails: React.FC<{
  equation: Equation;
  targetVariable?: string | null;
}> = ({ equation, targetVariable }) => {
  const r2 = metricValue(equation);
  const scatterBasis = scatterBasisLabel(equation.scatter_data);
  return (
    <div className="space-y-4">
      <div className="flex items-center gap-2 flex-wrap">
        {equation.model_id && (
          <code className="text-xs font-mono px-1.5 py-0.5 rounded bg-surface-alt text-secondary border border-[var(--color-border)]">
            {equation.model_id}
          </code>
        )}
        {equation.origin && (
          <Tag
            value={originLabel(equation.origin)}
            className={`text-xs ${
              equation.origin === 'symbolic'
                ? 'bg-brand-50 text-brand-500'
                : 'bg-[rgba(34,197,94,0.12)] text-green-700'
            }`}
          />
        )}
        {r2 !== null && (
          <Tag
            value={`${metricLabel(equation.metric_basis, equation.holdout_n)}: ${r2.toFixed(3)}`}
            className="bg-[rgba(34,197,94,0.12)] text-green-700 text-xs px-2 py-1"
          />
        )}
        <Tag
          value={`Complexity: ${equation.complexity}`}
          className="bg-surface-alt text-primary text-xs px-2 py-1"
        />
      </div>

      <div>
        <div className="bg-surface-alt rounded-lg p-6 overflow-x-auto border border-[var(--color-border)] mathjax-equation">
          <MathJaxContext config={mathJaxConfig}>
            <MathJax inline dynamic>
              {equationMath(equation, targetVariable)}
            </MathJax>
          </MathJaxContext>
        </div>
        <VariablesLegend variables={equation.variables} />
      </div>

      {equation.overview && (
        <p className="text-secondary leading-relaxed">
          <CitationText text={equation.overview} citations={equation.citations} />
        </p>
      )}

      {equation.term_explanations && equation.term_explanations.length > 0 && (
        <div>
          <h5 className="text-sm font-semibold text-primary flex items-center gap-2 mb-3">
            <i className="pi pi-info-circle text-brand-500"></i>
            Term Breakdown ({equation.term_explanations.length})
          </h5>
          <div className="space-y-2">
            {equation.term_explanations.map((term, idx) => (
              <div
                key={idx}
                className="bg-surface rounded-lg p-3 border border-[var(--color-border)]"
              >
                <code className="text-brand-500 font-mono text-sm bg-brand-50 px-2 py-1 rounded">
                  {term.term}
                </code>
                <p className="mt-2 text-sm text-secondary">
                  <CitationText text={term.explanation} citations={equation.citations} />
                </p>
              </div>
            ))}
          </div>
        </div>
      )}

      {(equation.scatter_data || (equation.citations?.length ?? 0) > 0) && (
        <div className="flex flex-wrap gap-4">
          {equation.scatter_data && (
            <div className="min-w-0" style={{ flex: '1 1 340px' }}>
              <div className="flex items-center justify-between flex-wrap gap-2 mb-3">
                <h5 className="text-sm font-semibold text-primary flex items-center gap-2">
                  <i className="pi pi-chart-line text-brand-500"></i>
                  Predicted vs. Measured
                  {scatterBasis && <span className="font-normal text-muted">({scatterBasis})</span>}
                </h5>
                <SplitButton
                  label="Export Data"
                  icon="pi pi-table"
                  onClick={() => {
                    exportToCSV([equation], `eq${equation.id}`);
                  }}
                  model={[
                    {
                      label: 'Excel (.xlsx)',
                      icon: 'pi pi-file-excel',
                      command: () => exportToExcel([equation], `eq${equation.id}`),
                    },
                  ]}
                  className="equation-export-button"
                  size="small"
                />
              </div>
              <div className="bg-surface rounded-lg p-4 border border-[var(--color-border)]">
                <ScatterPlot data={equation.scatter_data} />
              </div>
            </div>
          )}

          {equation.citations && equation.citations.length > 0 && (
            <div className="min-w-0" style={{ flex: '1 1 300px' }}>
              <h5 className="text-sm font-semibold text-primary flex items-center gap-2 mb-3">
                <i className="pi pi-book text-brand-500"></i>
                Scientific Sources ({equation.citations.length})
              </h5>
              <div className="bg-surface rounded-lg p-3 border border-[var(--color-border)]">
                <ul className="space-y-2">
                  {equation.citations.map((citation, idx) => (
                    <li key={idx} className="text-sm">
                      <CitationLink
                        index={idx + 1}
                        url={citation}
                        title={equation.citation_titles?.[idx]}
                      />
                    </li>
                  ))}
                </ul>
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
};

/** One compact row of the other equations; opening it shows every detail */
const EquationRow: React.FC<{
  equation: Equation;
  tied: boolean;
  targetVariable?: string | null;
}> = ({ equation, tied, targetVariable }) => {
  const [open, setOpen] = useState(false);
  const r2 = metricValue(equation);
  const note = [
    tied ? 'equally good as the recommended equation' : '',
    equation.origin ? originLabel(equation.origin) : '',
  ]
    .filter(Boolean)
    .join(' · ');
  return (
    <li>
      <button
        type="button"
        onClick={() => setOpen(!open)}
        aria-expanded={open}
        className="w-full grid items-center gap-3 px-4 py-3 text-left bg-surface border-0 cursor-pointer hover:bg-surface-alt transition-colors"
        style={{ gridTemplateColumns: '2.25rem minmax(0, 1fr) 4.5rem 5rem 1rem' }}
      >
        <span className="w-8 h-8 rounded-lg bg-blue-500 text-white font-bold text-sm flex items-center justify-center">
          {equation.id}
        </span>
        <span className="min-w-0 flex flex-col">
          <span className="font-mono text-sm text-primary truncate">
            {equation.target_alias || targetVariable
              ? `${equation.target_alias || targetVariable} = `
              : ''}
            {equation.equation}
          </span>
          {note && <span className="text-xs text-muted truncate">{note}</span>}
        </span>
        <span className="text-sm font-semibold text-primary tabular-nums text-right">
          {r2 !== null ? r2.toFixed(3) : '—'}
        </span>
        <span className="text-sm text-secondary tabular-nums text-right">
          {equation.complexity}
        </span>
        <i
          className={`pi ${open ? 'pi-chevron-up' : 'pi-chevron-down'} text-xs text-muted`}
          aria-hidden="true"
        ></i>
      </button>
      {open && (
        <div className="px-4 pb-5 pt-1 bg-[var(--color-surface)]">
          <EquationDetails equation={equation} targetVariable={targetVariable} />
        </div>
      )}
    </li>
  );
};

/** One line under the recommended equation: its scores and why it was chosen */
const HeroMetrics: React.FC<{ equation: Equation; reason: string; hasEvidence: boolean }> = ({
  equation,
  reason,
  hasEvidence,
}) => {
  const r2 = metricValue(equation);
  const cv = typeof equation.cv_r2 === 'number' ? equation.cv_r2 : null;
  const parts: React.ReactNode[] = [];
  if (r2 !== null) {
    parts.push(
      <span key="r2">
        <strong className="text-green-700 tabular-nums">
          {metricShortLabel(equation.metric_basis, equation.holdout_n)} {r2.toFixed(3)}
        </strong>
      </span>
    );
  }
  if (cv !== null && equation.metric_basis !== 'cv') {
    parts.push(
      <span key="cv" className="tabular-nums">
        CV R² {cv.toFixed(3)}
      </span>
    );
  }
  parts.push(
    <span key="cx" className="tabular-nums">
      complexity {equation.complexity}
    </span>
  );
  if (reason) parts.push(<span key="why">{reason}</span>);
  return (
    <div className="mt-3 flex flex-wrap gap-x-4 gap-y-1 text-sm text-secondary">
      {parts}
      {hasEvidence && (
        <a href="#evidence" className="text-link font-medium hover:underline">
          See the evidence
        </a>
      )}
    </div>
  );
};

/** Rows shown before "Show all" */
const OTHER_ROWS = 6;

const EquationResultsView: React.FC<EquationResultsViewProps> = ({
  data,
  targetVariable,
  hasDiscovery = false,
  selection,
  afterHero,
  hasEvidence = false,
}) => {
  const [showAllOthers, setShowAllOthers] = useState(false);
  const { equations = [], summary, recommendation } = data;
  // The selector's headline is the single recommended model. Runs from before it existed
  // fall back to the explanation AI's recommendation.
  const headline = equations.find((eq) => eq.is_headline);
  const recommendedId = headline?.id ?? recommendation?.equation_id ?? 0;
  const explainerDisagrees =
    !!headline &&
    recommendation?.agrees_with_headline === false &&
    recommendation.equation_id > 0 &&
    recommendation.equation_id !== headline.id;
  const headlineReason = headline ? headlineReasonText(selection?.headline_reason) : '';
  const others = equations.filter((eq) => eq.id !== recommendedId);
  const tiedIds = tiedModelIds(equations, selection);

  // Handle parse error fallback
  if (data._parse_error) {
    return (
      <div className="bg-[rgba(245,158,11,0.06)] border border-[rgba(245,158,11,0.2)] rounded-xl p-6">
        <div className="flex items-start gap-3">
          <i className="pi pi-exclamation-triangle text-amber-500 text-xl mt-0.5"></i>
          <div>
            <h4 className="font-semibold text-primary">Results Format Issue</h4>
            <p className="text-secondary mt-1 text-sm">
              The analysis completed but the results couldn't be fully parsed. Here's the raw
              output:
            </p>
            <pre className="mt-4 bg-surface p-4 rounded-lg border border-[var(--color-border)] text-sm overflow-x-auto whitespace-pre-wrap">
              {summary?.findings || 'No results available'}
            </pre>
          </div>
        </div>
      </div>
    );
  }

  // LLM explanation failure on a legacy run (no discovery report): the equations are raw
  // and unscored, so show an error instead of partial results
  if (data._explanation_error && !hasDiscovery) {
    return (
      <div className="bg-red-50 border border-red-200 rounded-xl p-6">
        <div className="flex flex-col items-center justify-center text-center py-8">
          <div className="w-16 h-16 bg-red-100 rounded-full flex items-center justify-center mb-4">
            <i className="pi pi-times-circle text-red-500 text-3xl"></i>
          </div>
          <h4 className="text-xl font-bold text-primary font-heading mb-2">Analysis Failed</h4>
          <p className="text-secondary max-w-md">
            The AI explanation step encountered an error during this analysis. The results could not
            be fully generated. Please re-run the analysis to get complete results.
          </p>
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Summary Section */}
      {summary && (
        <div className="bg-gradient-to-br from-brand-50 to-surface-alt rounded-xl border border-[var(--color-border)] p-6">
          <div className="flex items-center gap-2 mb-4">
            <h3 className="text-lg font-bold text-primary font-heading flex items-center gap-2">
              <i className="pi pi-chart-bar text-brand-500"></i>
              Analysis Summary
            </h3>
            <HelpButton title="Analysis Summary">
              <h4>What's in the Summary?</h4>
              <p>
                The summary provides an overview of the most influential factors identified by the
                symbolic regression analysis.
              </p>

              <h4>Key Drivers</h4>
              <p>
                <strong>Primary variables</strong> that have the strongest impact on your target.
                These appear most frequently in the discovered equations.
              </p>

              <h4>Secondary Drivers</h4>
              <p>
                <strong>Supporting variables</strong> that contribute to predictions but with less
                impact than key drivers.
              </p>

              <h4>Findings</h4>
              <p>
                A synthesized interpretation of what the analysis discovered about your data, and
                how the equations relate to known laws (classic laws, and published laws when the
                literature search ran).
              </p>
            </HelpButton>
          </div>

          {/* Key Drivers */}
          {summary.key_drivers && summary.key_drivers.length > 0 && (
            <div className="mb-4">
              <h4 className="text-sm font-semibold text-secondary mb-2">Key Drivers</h4>
              <div className="flex flex-wrap gap-2">
                {summary.key_drivers.map((driver, idx) => (
                  <Tag key={idx} value={driver} severity="success" className="font-mono text-sm" />
                ))}
              </div>
            </div>
          )}

          {/* Secondary Drivers */}
          {summary.secondary_drivers && summary.secondary_drivers.length > 0 && (
            <div className="mb-4">
              <h4 className="text-sm font-semibold text-secondary mb-2">Secondary Drivers</h4>
              <div className="flex flex-wrap gap-2">
                {summary.secondary_drivers.map((driver, idx) => (
                  <Tag
                    key={idx}
                    value={driver}
                    className="bg-surface-alt text-primary font-mono text-sm"
                  />
                ))}
              </div>
            </div>
          )}

          {/* Findings */}
          {summary.findings && (
            <div>
              <h4 className="text-sm font-semibold text-secondary mb-2">Findings</h4>
              <p className="text-primary leading-relaxed">{sanitizeText(summary.findings)}</p>
            </div>
          )}
        </div>
      )}

      {explainerDisagrees && (
        <div className="bg-[rgba(59,130,246,0.06)] border border-[rgba(59,130,246,0.2)] rounded-xl p-4 text-sm text-secondary flex items-start gap-3">
          <i className="pi pi-info-circle text-brand-500 mt-0.5" aria-hidden="true"></i>
          <div>
            <p>
              <span className="font-medium text-primary">
                The explanation AI prefers Equation {recommendation.equation_id}
              </span>
              {recommendation.disagreement_reason
                ? `: ${sanitizeText(recommendation.disagreement_reason)}`
                : '.'}
            </p>
            {recommendation.rationale?.length > 0 && (
              <ul className="mt-2 list-disc pl-5 space-y-1">
                {recommendation.rationale.map((reason, idx) => (
                  <li key={idx}>{sanitizeText(reason)}</li>
                ))}
              </ul>
            )}
          </div>
        </div>
      )}

      {/* Recommendation Card */}
      {recommendedId > 0 &&
        (() => {
          const recommendedEquation = equations.find((eq) => eq.id === recommendedId);
          const rationale =
            recommendation && recommendation.equation_id === recommendedId
              ? (recommendation.rationale ?? [])
              : [];
          return (
            <div className="bg-[rgba(34,197,94,0.06)] rounded-xl border border-[rgba(34,197,94,0.2)] p-6">
              <div className="flex items-start gap-4">
                <div className="w-10 h-10 bg-green-500 rounded-lg flex items-center justify-center flex-shrink-0">
                  <i className="pi pi-star-fill text-white text-lg"></i>
                </div>
                <div className="flex-1 min-w-0">
                  <h3 className="text-lg font-bold font-heading text-primary">
                    Recommended: Equation {recommendedId}
                  </h3>
                  {recommendedEquation && (
                    <div className="mt-3 bg-surface rounded-lg p-3 border border-[rgba(34,197,94,0.2)] overflow-x-auto mathjax-equation">
                      <MathJaxContext config={mathJaxConfig}>
                        <MathJax inline dynamic>
                          {equationMath(recommendedEquation, targetVariable)}
                        </MathJax>
                      </MathJaxContext>
                    </div>
                  )}
                  {recommendedEquation && (
                    <VariablesLegend variables={recommendedEquation.variables} />
                  )}
                  {recommendedEquation && (
                    <HeroMetrics
                      equation={recommendedEquation}
                      reason={headlineReason}
                      hasEvidence={hasEvidence}
                    />
                  )}
                  {rationale.length > 0 && (
                    <ul className="mt-4 space-y-2">
                      {rationale.map((reason, idx) => (
                        <li key={idx} className="flex items-start gap-2 text-secondary">
                          <i className="pi pi-check-circle text-green-500 mt-0.5 flex-shrink-0"></i>
                          <span className="text-sm">{reason}</span>
                        </li>
                      ))}
                    </ul>
                  )}
                </div>
              </div>
            </div>
          );
        })()}

      {afterHero}

      {/* The other equations: compact rows, each opening to the full detail */}
      {others.length > 0 && (
        <section className="rounded-xl border border-[var(--color-border)] bg-surface p-6 space-y-4">
          <div className="flex items-center gap-2 flex-wrap">
            <h3 className="text-lg font-bold text-primary font-heading flex items-center gap-2">
              <i className="pi pi-list text-brand-500"></i>
              {recommendedId > 0 ? 'Other equations' : 'Equations'} ({others.length})
            </h3>
            <HelpButton title="Understanding Equations">
              <h4>Equation Metrics</h4>
              <p>
                The list mixes symbolic-regression equations with classic, custom and published
                (literature) laws, ordered by complexity. Open a row for its explanation, term
                breakdown, predicted-vs-measured plot and sources.
              </p>
              <ul>
                <li>
                  <strong>R²</strong> - Share of the target&apos;s variation the equation explains.
                  It is measured on held-out rows no model was trained on, or, when the dataset is
                  too small for a holdout, by cross-validation (CV R²).
                </li>
                <li>
                  <strong>Complexity</strong> - Number of terms/operations in the equation. Lower
                  means simpler.
                </li>
                <li>
                  <strong>Equally good</strong> - Its error is statistically tied with the
                  recommended equation; the recommended one was preferred as the simpler choice.
                </li>
              </ul>
            </HelpButton>
            <span className="ml-auto text-xs text-muted">R² · complexity</span>
          </div>
          <ul className="m-0 p-0 list-none border border-[var(--color-border)] rounded-lg overflow-hidden divide-y divide-[var(--color-border)]">
            {(showAllOthers ? others : others.slice(0, OTHER_ROWS)).map((eq) => (
              <EquationRow
                key={eq.id}
                equation={eq}
                tied={!!eq.model_id && tiedIds.has(eq.model_id)}
                targetVariable={targetVariable}
              />
            ))}
          </ul>
          {others.length > OTHER_ROWS && (
            <Button
              label={showAllOthers ? 'Show fewer' : `Show all ${others.length}`}
              icon={showAllOthers ? 'pi pi-chevron-up' : 'pi pi-chevron-down'}
              className="p-button-text p-button-sm !text-brand-500 hover:!bg-brand-50 !px-4 !py-2"
              onClick={() => setShowAllOthers(!showAllOthers)}
            />
          )}
        </section>
      )}
    </div>
  );
};

export default EquationResultsView;
