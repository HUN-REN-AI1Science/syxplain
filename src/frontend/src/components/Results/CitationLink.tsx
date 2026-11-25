/**
 * CitationLink Component
 * One numbered source: its title as the link (when the literature search returned one), with
 * the address beneath it in small print; older runs without titles show the address alone.
 */

import React from 'react';
import { sanitizeUrl } from '@utils/security';

interface CitationLinkProps {
  /** 1-based number, as the [n] markers in the text */
  index: number;
  url: string;
  title?: string | null;
}

export const CitationLink: React.FC<CitationLinkProps> = ({ index, url, title }) => {
  const safeUrl = sanitizeUrl(url);
  const label = title?.trim();
  if (!safeUrl) {
    return <span className="text-secondary">[{index}] Invalid URL</span>;
  }
  return (
    <a
      href={safeUrl}
      target="_blank"
      rel="noopener noreferrer"
      className="group inline-flex flex-col min-w-0 no-underline"
    >
      <span className="text-link group-hover:underline break-words">
        <span className="citation-link">[{index}]</span> {label || safeUrl}
      </span>
      {label && <span className="text-xs text-muted break-all">{safeUrl}</span>}
    </a>
  );
};

export default CitationLink;
