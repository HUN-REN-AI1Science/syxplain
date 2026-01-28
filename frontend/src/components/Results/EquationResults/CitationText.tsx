/**
 * CitationText Component
 * Renders text with citation references [1], [2], etc. as clickable links
 * to the corresponding citation URLs.
 * Also handles combined citations like [1, 2, 3] or [2, 3].
 */

import React from 'react';
import { sanitizeUrl, sanitizeText } from '@utils/security';

interface CitationTextProps {
  text: string;
  citations?: string[];
  className?: string;
}

/**
 * Creates a clickable citation link element with URL sanitization
 */
const createCitationLink = (
  citationNumber: number,
  citationUrl: string,
  key: string
): JSX.Element => {
  // Sanitize URL to prevent javascript: and data: URI attacks
  const safeUrl = sanitizeUrl(citationUrl);

  // If URL is unsafe, render as plain text instead of link
  if (!safeUrl) {
    return <span key={key}>{citationNumber}</span>;
  }

  return (
    <a
      key={key}
      href={safeUrl}
      target="_blank"
      rel="noopener noreferrer"
      className="citation-link"
      title={`Open citation: ${safeUrl}`}
    >
      {citationNumber}
    </a>
  );
};

/**
 * Parses text and converts [1], [2], [1, 2, 3], etc. patterns into clickable links
 * that open the corresponding citation URL in a new tab
 */
const CitationText: React.FC<CitationTextProps> = ({ text, citations = [], className = '' }) => {
  // Sanitize input text to prevent XSS (strips any HTML tags)
  const safeText = sanitizeText(text);

  // Regex to match both single citations [1] and combined citations [1, 2, 3]
  // Matches: [1], [12], [1, 2], [1, 2, 3], [1,2,3], etc.
  const citationPattern = /\[(\d+(?:\s*,\s*\d+)*)\]/g;

  // Split text into parts: regular text and citation references
  const parts: (string | JSX.Element)[] = [];
  let lastIndex = 0;
  let match: RegExpExecArray | null;

  while ((match = citationPattern.exec(safeText)) !== null) {
    // Add text before the match
    if (match.index > lastIndex) {
      parts.push(safeText.slice(lastIndex, match.index));
    }

    const citationContent = match[1]; // Content inside brackets, e.g., "1" or "1, 2, 3"
    const citationNumbers = citationContent.split(/\s*,\s*/).map(num => parseInt(num.trim(), 10));

    // Check if this is a single citation or multiple
    if (citationNumbers.length === 1) {
      const citationNumber = citationNumbers[0];
      const citationIndex = citationNumber - 1;

      if (citationIndex >= 0 && citationIndex < citations.length) {
        const citationUrl = citations[citationIndex];
        parts.push(
          <span key={`citation-group-${match.index}`} className="citation-group text-blue-600">
            [
            {createCitationLink(citationNumber, citationUrl, `citation-${match.index}`)}
            ]
          </span>
        );
      } else {
        // No matching citation - render as plain text
        parts.push(match[0]);
      }
    } else {
      // Multiple citations like [1, 2, 3]
      const citationElements: (string | JSX.Element)[] = ['['];
      const matchIndex = match.index; // Capture for use in closure

      citationNumbers.forEach((citationNumber, idx) => {
        const citationIndex = citationNumber - 1;

        if (citationIndex >= 0 && citationIndex < citations.length) {
          const citationUrl = citations[citationIndex];
          citationElements.push(
            createCitationLink(citationNumber, citationUrl, `citation-${matchIndex}-${idx}`)
          );
        } else {
          // No matching citation - render as plain number
          citationElements.push(String(citationNumber));
        }

        // Add comma separator between citations (except for the last one)
        if (idx < citationNumbers.length - 1) {
          citationElements.push(', ');
        }
      });

      citationElements.push(']');

      parts.push(
        <span key={`citation-group-${match.index}`} className="citation-group text-blue-600">
          {citationElements}
        </span>
      );
    }

    lastIndex = match.index + match[0].length;
  }

  // Add remaining text after last match
  if (lastIndex < safeText.length) {
    parts.push(safeText.slice(lastIndex));
  }

  return <span className={className}>{parts}</span>;
};

export default CitationText;
