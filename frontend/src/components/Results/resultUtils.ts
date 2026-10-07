/**
 * Result utility functions
 * Shared helpers for result format detection and validation
 */

import type { DiscoveryReport, Equation, EquationResults, RunWarning, ScatterData } from '@/types';

const asObject = (result: unknown): Record<string, unknown> | null => {
  let raw = result;
  if (typeof raw === 'string') {
    try {
      raw = JSON.parse(raw);
    } catch {
      return null;
    }
  }
  return raw && typeof raw === 'object' && !Array.isArray(raw)
    ? (raw as Record<string, unknown>)
    : null;
};

/**
 * Check if backend results contain an LLM explanation error.
 */
export const hasExplanationError = (result: unknown): boolean => {
  const r = asObject(result);
  if (!r) return false;
  const explanations = r.explanations;
  return (
    !!explanations &&
    typeof explanations === 'object' &&
    !Array.isArray(explanations) &&
    'error' in (explanations as Record<string, unknown>)
  );
};

/** The discovery agent's report (runs before the agentic pipeline have none) */
export const extractDiscovery = (result: unknown): DiscoveryReport | null => {
  const r = asObject(result);
  const discovery = r?.discovery;
  if (!discovery || typeof discovery !== 'object' || !('leaderboard' in discovery)) return null;
  return discovery as DiscoveryReport;
};

/** True when the run has a discovery report, so the results are usable without narration */
export const hasDiscoveryData = (result: unknown): boolean => extractDiscovery(result) !== null;

/**
 * Share/export are blocked only for legacy runs whose explanation failed:
 * with discovery data the equations and the report are complete.
 */
export const isResultIncomplete = (result: unknown): boolean =>
  hasExplanationError(result) && !hasDiscoveryData(result);

/** Non-fatal problems recorded by the backend (results.warnings) */
export const extractWarnings = (result: unknown): RunWarning[] => {
  const warnings = asObject(result)?.warnings;
  if (!Array.isArray(warnings)) return [];
  return warnings
    .filter((w): w is Record<string, unknown> => !!w && typeof w === 'object')
    .map((w) => ({
      stage: String(w.stage ?? '') as RunWarning['stage'],
      message: typeof w.message === 'string' ? w.message : JSON.stringify(w.message ?? ''),
    }));
};

/**
 * Gives every equation a numeric id and its scatter data. Equations stored without
 * narration (failed explanation step) are raw discovery entries without an `id`.
 */
const normalizeEquations = (equations: unknown, raw: Record<string, unknown>): Equation[] => {
  if (!Array.isArray(equations)) return [];
  const legacyScatter =
    raw.scatter_data && typeof raw.scatter_data === 'object'
      ? (raw.scatter_data as Record<string, ScatterData>)
      : {};
  return equations
    .filter((eq): eq is Equation => !!eq && typeof eq === 'object')
    .map((eq, i) => ({
      ...eq,
      id: typeof eq.id === 'number' ? eq.id : i + 1,
      scatter_data: eq.scatter_data ?? legacyScatter[eq.equation],
    }));
};

/**
 * Extracts EquationResults from the backend's combined results format.
 *
 * The backend stores: { equations: [raw], explanations: { equations: [enriched], summary,
 * recommendation }, discovery, warnings, ... }. The enriched equations (with overview,
 * term_explanations, citations, scatter_data) live inside `explanations`.
 */
export const extractEquationResults = (result: unknown): EquationResults | null => {
  const raw = asObject(result);
  if (!raw) return null;
  const warnings = extractWarnings(raw);
  const explanations = raw.explanations;
  if (
    explanations &&
    typeof explanations === 'object' &&
    !Array.isArray(explanations) &&
    'equations' in explanations
  ) {
    const data = explanations as unknown as EquationResults & { error?: unknown };
    const out: EquationResults = {
      ...data,
      equations: normalizeEquations(data.equations, raw),
      warnings,
    };
    // When the LLM explanation step failed, explanations contains an error field
    // and the equations are raw discovery output (no overviews, citations, etc.)
    if ('error' in data && data.error) {
      const explanationWarning = warnings.find((w) => w.stage === 'explanation');
      out._explanation_error = true;
      out._explanation_error_message =
        explanationWarning?.message || (typeof data.error === 'string' ? data.error : '');
    }
    return out;
  }
  return null;
};
