/**
 * Formatting Utilities
 * Common formatting functions used across the application
 */

/**
 * Format bytes into human-readable file size
 */
export function formatFileSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(2)} MB`;
}

/**
 * Escape special characters for AsciiMath rendering
 * Wraps all multi-character variable names in quotes to prevent AsciiMath
 * from parsing parts of identifiers as reserved symbols (gt, lt, log, sin, etc.)
 */
export function escapeForAsciiMath(text: string): string {
  // Match any identifier (letter followed by alphanumerics/underscores)
  // that is 2+ characters long - these need to be quoted to prevent
  // AsciiMath from parsing substrings as reserved symbols
  const identifierPattern = /([a-zA-Z][a-zA-Z0-9_]+)/g;

  const result = text.replace(identifierPattern, (match) => {
    // Quote all multi-character identifiers
    return `"${match}"`;
  });

  return result;
}

export interface AnalysisTypeDisplay {
  label: string;
  icon: string;
  severity: 'info' | 'warning' | 'success';
}

/**
 * Display of a run's analysis type. Current runs ('standard') have a single mode;
 * runs from before it keep their 'quick'/'deep' label.
 */
export function analysisTypeDisplay(analysisType?: string | null): AnalysisTypeDisplay {
  if (analysisType === 'quick') return { label: 'Quick', icon: 'pi-bolt', severity: 'info' };
  if (analysisType === 'deep') return { label: 'Deep', icon: 'pi-search', severity: 'warning' };
  return { label: 'Standard', icon: 'pi-cog', severity: 'success' };
}

/** Label for legacy quick/deep runs; null for current runs, which need none. */
export function legacyAnalysisTypeLabel(analysisType?: string | null): string | null {
  return analysisType === 'quick' || analysisType === 'deep'
    ? analysisTypeDisplay(analysisType).label
    : null;
}
