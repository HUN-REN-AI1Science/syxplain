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
 * Parses result data and returns the appropriate format
 */
const parseResult = (
  result: EquationResults | string
): {
  type: 'new' | 'legacy';
  data: EquationResults | string;
} => {
  // Handle object (new format) directly
  if (typeof result === 'object' && 'equations' in result) {
    return { type: 'new', data: result };
  }

  // Handle string - try to parse as JSON
  if (typeof result === 'string') {
    try {
      const parsed = JSON.parse(result);
      if (parsed && 'equations' in parsed) {
        return { type: 'new', data: parsed as EquationResults };
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
