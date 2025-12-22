/**
 * CitationText Component
 * Renders text with citation references [1], [2], etc. as clickable links
 * to the corresponding citation URLs
 */

import React from 'react';

interface CitationTextProps {
  text: string;
  citations?: string[];
  className?: string;
}

/**
 * Parses text and converts [1], [2], etc. patterns into clickable links
 * that open the corresponding citation URL in a new tab
 */
const CitationText: React.FC<CitationTextProps> = ({ text, citations = [], className = '' }) => {
  // Regex to match citation references like [1], [2], [12], etc.
  const citationPattern = /\[(\d+)\]/g;

  // Split text into parts: regular text and citation references
  const parts: (string | JSX.Element)[] = [];
  let lastIndex = 0;
  let match;

  while ((match = citationPattern.exec(text)) !== null) {
    // Add text before the match
    if (match.index > lastIndex) {
      parts.push(text.slice(lastIndex, match.index));
    }

    const citationNumber = parseInt(match[1], 10);
    const citationIndex = citationNumber - 1; // Convert 1-based to 0-based index

    // Check if citation exists in the array
    if (citationIndex >= 0 && citationIndex < citations.length) {
      const citationUrl = citations[citationIndex];
      parts.push(
        <a
          key={`citation-${match.index}`}
          href={citationUrl}
          target="_blank"
          rel="noopener noreferrer"
          className="citation-link"
          title={`Open citation: ${citationUrl}`}
        >
          [{citationNumber}]
        </a>
      );
    } else {
      // No matching citation - render as plain text
      parts.push(match[0]);
    }

    lastIndex = match.index + match[0].length;
  }

  // Add remaining text after last match
  if (lastIndex < text.length) {
    parts.push(text.slice(lastIndex));
  }

  return <span className={className}>{parts}</span>;
};

export default CitationText;
