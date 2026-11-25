/**
 * Security utilities for XSS prevention and input sanitization.
 *
 * OWASP: A03:2021 - Injection
 */
import DOMPurify from 'dompurify';

/**
 * Sanitize HTML content to prevent XSS attacks.
 * Use this for any content that might contain HTML from API responses.
 *
 * @param dirty - Potentially unsafe HTML string
 * @returns Sanitized string safe for rendering
 */
export function sanitizeHtml(dirty: string | undefined | null): string {
  if (!dirty) return '';
  return DOMPurify.sanitize(dirty, {
    ALLOWED_TAGS: ['b', 'i', 'em', 'strong', 'sub', 'sup', 'br'],
    ALLOWED_ATTR: [],
  });
}

/**
 * Sanitize plain text by removing any HTML tags.
 * Use this for text content that should never contain HTML.
 *
 * @param dirty - Potentially unsafe string
 * @returns Plain text with HTML stripped
 */
export function sanitizeText(dirty: string | undefined | null): string {
  if (!dirty) return '';
  return DOMPurify.sanitize(dirty, {
    ALLOWED_TAGS: [],
    ALLOWED_ATTR: [],
  });
}

/**
 * Validate and sanitize a URL to prevent javascript: and data: URI attacks.
 *
 * @param url - URL string to validate
 * @returns Sanitized URL or empty string if invalid
 */
export function sanitizeUrl(url: string | undefined | null): string {
  if (!url) return '';

  // Trim whitespace
  const trimmed = url.trim();

  // Block dangerous protocols
  const lowerUrl = trimmed.toLowerCase();
  const dangerousProtocols = ['javascript:', 'data:', 'vbscript:', 'file:'];

  for (const protocol of dangerousProtocols) {
    if (lowerUrl.startsWith(protocol)) {
      console.warn(`Blocked dangerous URL protocol: ${protocol}`);
      return '';
    }
  }

  // Only allow http, https, and relative URLs
  if (
    !lowerUrl.startsWith('http://') &&
    !lowerUrl.startsWith('https://') &&
    !lowerUrl.startsWith('/') &&
    !lowerUrl.startsWith('#')
  ) {
    // Could be a relative URL or malformed - check for protocol
    if (lowerUrl.includes(':')) {
      console.warn(`Blocked URL with unknown protocol: ${url}`);
      return '';
    }
  }

  return trimmed;
}

/**
 * Check if a URL is safe to use as an external link.
 *
 * @param url - URL to check
 * @returns true if URL is safe for external linking
 */
export function isExternalUrlSafe(url: string | undefined | null): boolean {
  const sanitized = sanitizeUrl(url);
  if (!sanitized) return false;

  const lower = sanitized.toLowerCase();
  return lower.startsWith('http://') || lower.startsWith('https://');
}
