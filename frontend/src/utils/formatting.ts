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
 * Wraps variable names with underscores in quotes for proper rendering
 * Also escapes AsciiMath reserved keywords (gt, lt, ge, le, etc.) that would
 * otherwise be converted to relational symbols using text() function
 */
export function escapeForAsciiMath(text: string): string {
  // AsciiMath reserved keywords that get converted to symbols
  // These need to be wrapped in text() when used as variable names
  const reservedKeywords = [
    'gt', 'lt', 'ge', 'le', 'gte', 'lte', 'ne', 'eq',
    'and', 'or', 'not', 'mod', 'if', 'in'
  ];

  let result = text;

  // First, escape variable names with underscores using quotes
  result = result.replace(/([a-zA-Z][a-zA-Z0-9]*(?:_[a-zA-Z0-9]+)+)/g, '"$1"');

  // Then, escape reserved keywords when they appear as standalone words
  // using text() which is the documented AsciiMath way to render literal text
  for (const keyword of reservedKeywords) {
    // Match the keyword as a standalone word (not part of a larger identifier)
    // and not already within quotes or text()
    const regex = new RegExp(`(?<![a-zA-Z0-9_"(])\\b(${keyword})\\b(?![a-zA-Z0-9_"])`, 'gi');
    result = result.replace(regex, 'text($1)');
  }

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
