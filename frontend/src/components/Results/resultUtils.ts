/**
 * Result utility functions
 * Shared helpers for result format detection and validation
 */

/**
 * Check if backend results contain an LLM explanation error.
 * Used to hide share/export actions when results are incomplete.
 */
export const hasExplanationError = (result: unknown): boolean => {
  if (!result || typeof result !== 'object') return false;
  const r = result as Record<string, unknown>;
  const explanations = r.explanations;
  return (
    !!explanations &&
    typeof explanations === 'object' &&
    !Array.isArray(explanations) &&
    'error' in (explanations as Record<string, unknown>)
  );
};
