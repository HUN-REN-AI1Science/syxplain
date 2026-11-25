/**
 * ResultContent Component
 * Unified component for rendering equation results with format detection. Page order:
 * warnings, the time-series note, the summary and the recommended equation, the time-series
 * and rate-law sections, the other equations (compact rows), the evidence, and how the
 * equations were found (collapsed).
 */

import React from 'react';
import EquationResultsView from './EquationResults/EquationResultsView';
import DiscoveryReportPanel from './Discovery/DiscoveryReportPanel';
import { DynamicsSection } from './Discovery/DynamicsSection';
import EvidenceSection from './Discovery/EvidenceSection';
import { SeriesBanner } from './Discovery/SeriesBanner';
import { SeriesSection } from './Discovery/SeriesSection';
import LegacyResultsFallback from './LegacyResultsFallback';
import ResultWarnings from './ResultWarnings';
import SectionErrorBoundary from './SectionErrorBoundary';
import { extractDiscovery, extractEquationResults, extractWarnings } from './resultUtils';
import { hasEvidence } from '@utils/discovery';
import type { EquationResults } from '@/types';

interface ResultContentProps {
  /** Result data - can be EquationResults object, JSON string, or legacy markdown */
  result: EquationResults | string | null;
  /** Optional ref for the results container (used for PDF export) */
  resultsRef?: React.RefObject<HTMLDivElement>;
  /** Target variable name to prepend to equations (e.g. "y = ...") */
  targetVariable?: string | null;
  /** Fetches a run artifact (SHAP plots); without it the plots are not shown */
  loadPlot?: (filename: string) => Promise<Blob>;
}

/**
 * Parses result data and returns the appropriate format
 */
const parseResult = (
  result: EquationResults | string
): {
  type: 'new' | 'legacy';
  data: EquationResults | string;
} => {
  if (typeof result === 'object' && result !== null) {
    // Direct EquationResults format (has equations + summary at top level)
    if ('equations' in result && 'summary' in result) {
      return { type: 'new', data: result };
    }

    // Backend combined format: the EquationResults are inside `explanations`
    if ('explanations' in result) {
      const extracted = extractEquationResults(result);
      if (extracted) {
        return { type: 'new', data: extracted };
      }
    }

    // Has equations at top level (fallback — could be incomplete)
    if ('equations' in result) {
      return { type: 'new', data: result };
    }
  }

  // Handle string - try to parse as JSON
  if (typeof result === 'string') {
    try {
      const parsed = JSON.parse(result);
      if (parsed && typeof parsed === 'object') {
        return parseResult(parsed);
      }
    } catch {
      // Not valid JSON - treat as legacy markdown
    }
    return { type: 'legacy', data: result };
  }

  return { type: 'legacy', data: String(result) };
};

export const ResultContent: React.FC<ResultContentProps> = ({
  result,
  resultsRef,
  targetVariable,
  loadPlot,
}) => {
  if (!result) {
    return null;
  }

  const { type, data } = parseResult(result);

  if (type === 'new') {
    const equationData = data as EquationResults;
    const discovery = extractDiscovery(result);
    const warnings = equationData.warnings ?? extractWarnings(result);
    // With discovery data a failed narration is not fatal: the equations, their scores
    // and the report are complete. Legacy runs without it keep the "Analysis Failed" card.
    const explanationWarning = warnings.find((w) => w.stage === 'explanation');
    const explanationError =
      discovery && (equationData._explanation_error || explanationWarning)
        ? (explanationWarning?.message ?? equationData._explanation_error_message ?? '')
        : null;
    const targetColumn = discovery?.target?.column ?? '';
    const showEvidence = hasEvidence(discovery, equationData.coherence);
    const afterHero = discovery && (discovery.series || discovery.dynamics) && (
      <>
        {discovery.series && (
          <SectionErrorBoundary name="The time-series section">
            <section
              id="series-section"
              className="rounded-xl border border-[var(--color-border)] bg-surface p-6"
            >
              <SeriesSection series={discovery.series} targetColumn={targetColumn} />
            </section>
          </SectionErrorBoundary>
        )}
        {discovery.dynamics && (
          <SectionErrorBoundary name="The rate-law section">
            <section className="rounded-xl border border-[var(--color-border)] bg-surface p-6">
              <DynamicsSection
                dynamics={discovery.dynamics}
                targetColumn={targetColumn}
                renderModelId={(id) => <span className="font-mono">{id}</span>}
              />
            </section>
          </SectionErrorBoundary>
        )}
      </>
    );
    return (
      <div ref={resultsRef} className="space-y-8 animate-fade-in">
        <ResultWarnings warnings={warnings} explanationError={explanationError} />
        {discovery?.series && (
          <SeriesBanner series={discovery.series} holdoutRows={discovery.split?.holdout || null} />
        )}
        <EquationResultsView
          data={equationData}
          targetVariable={targetVariable}
          hasDiscovery={!!discovery}
          selection={discovery?.selection}
          afterHero={afterHero}
          hasEvidence={showEvidence}
        />
        {discovery && showEvidence && (
          <SectionErrorBoundary name="The evidence">
            <EvidenceSection
              report={discovery}
              domain={equationData.coherence}
              loadPlot={loadPlot}
            />
          </SectionErrorBoundary>
        )}
        {discovery && (
          <SectionErrorBoundary name="The discovery report">
            <DiscoveryReportPanel report={discovery} />
          </SectionErrorBoundary>
        )}
      </div>
    );
  }

  // Legacy markdown format
  return <LegacyResultsFallback markdownContent={data as string} />;
};

export default ResultContent;
