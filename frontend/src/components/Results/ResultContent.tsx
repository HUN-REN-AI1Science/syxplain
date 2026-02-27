/**
 * ResultContent Component
 * Unified component for rendering equation results with format detection
 */

import React from 'react';
import EquationResultsView from './EquationResults/EquationResultsView';
import LegacyResultsFallback from './LegacyResultsFallback';
import type { EquationResults } from '@/types';

interface ResultContentProps {
  /** Result data - can be EquationResults object, JSON string, or legacy markdown */
  result: EquationResults | string | null;
  /** Optional ref for the results container (used for PDF export) */
  resultsRef?: React.RefObject<HTMLDivElement>;
}

/**
 * Extracts EquationResults from the backend's combined results format.
 *
 * The backend stores: { equations: [raw PySR], explanations: { equations: [enriched], summary, recommendation }, ... }
 * The frontend expects: { equations: [enriched], summary, recommendation }
 *
 * The enriched equations (with overview, term_explanations, citations, scatter_data)
 * live inside the `explanations` field. This function extracts them.
 */
const extractFromBackendFormat = (result: Record<string, unknown>): EquationResults | null => {
  const explanations = result.explanations;
  if (
    explanations &&
    typeof explanations === 'object' &&
    !Array.isArray(explanations) &&
    'equations' in explanations
  ) {
    const data = explanations as unknown as EquationResults & { error?: string };
    // When the LLM explanation step failed, explanations contains an error field
    // and the equations are raw PySR output (no overviews, citations, etc.)
    if ('error' in explanations && typeof (explanations as Record<string, unknown>).error === 'string') {
      return { ...data, _explanation_error: true };
    }
    return data;
  }
  return null;
};

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
      const extracted = extractFromBackendFormat(result as Record<string, unknown>);
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

export const ResultContent: React.FC<ResultContentProps> = ({ result, resultsRef }) => {
  if (!result) {
    return null;
  }

  const { type, data } = parseResult(result);

  if (type === 'new') {
    return (
      <div ref={resultsRef} className="space-y-8 animate-fade-in">
        <EquationResultsView data={data as EquationResults} />
      </div>
    );
  }

  // Legacy markdown format
  return <LegacyResultsFallback markdownContent={data as string} />;
};

export default ResultContent;
