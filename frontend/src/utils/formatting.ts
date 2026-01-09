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
 * Wraps variable names in quotes to prevent AsciiMath from converting
 * reserved keywords (gt, lt, ge, le, etc.) that appear within identifiers
 * to relational symbols
 */
export function escapeForAsciiMath(text: string): string {
  // AsciiMath reserved keywords that get converted to symbols
  // These can appear within identifiers (e.g., "avgt" contains "gt")
  const reservedKeywords = [
    'gt', 'lt', 'ge', 'le', 'gte', 'lte', 'ne', 'eq',
    'and', 'or', 'not', 'mod', 'in'
  ];

  // Create a pattern that matches any identifier (letter followed by alphanumerics/underscores)
  // We'll check each match to see if it contains a reserved keyword
  const identifierPattern = /([a-zA-Z][a-zA-Z0-9_]*)/g;

  const result = text.replace(identifierPattern, (match) => {
    // Check if this identifier contains any reserved keyword as a substring
    const containsReserved = reservedKeywords.some(keyword =>
      match.toLowerCase().includes(keyword)
    );

    // If it contains a reserved keyword, quote it to prevent symbol conversion
    if (containsReserved) {
      return `"${match}"`;
    }

    // Also quote identifiers with underscores (existing behavior)
    if (match.includes('_')) {
      return `"${match}"`;
    }

    return match;
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
