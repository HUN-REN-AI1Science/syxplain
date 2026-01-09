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
 * Format date to locale string
 */
export function formatDate(date: string | Date, options?: Intl.DateTimeFormatOptions): string {
  const dateObj = typeof date === 'string' ? new Date(date) : date;
  return dateObj.toLocaleString(undefined, options);
}

/**
 * Format date for display (short format)
 */
export function formatDateShort(date: string | Date): string {
  return formatDate(date, {
    year: 'numeric',
    month: 'short',
    day: 'numeric',
  });
}

/**
 * Format date with time
 */
export function formatDateTime(date: string | Date): string {
  return formatDate(date);
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

/**
 * Truncate string with ellipsis
 */
export function truncate(str: string, maxLength: number): string {
  if (str.length <= maxLength) return str;
  return str.slice(0, maxLength - 3) + '...';
}

/**
 * Format number with thousands separator
 */
export function formatNumber(num: number): string {
  return num.toLocaleString();
}

/**
 * Format percentage
 */
export function formatPercent(value: number, decimals = 0): string {
  return `${value.toFixed(decimals)}%`;
}
