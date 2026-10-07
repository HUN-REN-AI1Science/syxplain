/**
 * ModelIdText Component
 * Renders LLM-authored text defensively and turns model ids (C12, M3, S40, L1) that exist in
 * the leaderboard into links that open and scroll to that leaderboard row.
 */

import React from 'react';
import { asText, splitModelIds } from '@utils/discovery';

interface ModelIdTextProps {
  text: unknown;
  /** Model ids that have a leaderboard row */
  known: ReadonlySet<string>;
  onSelect: (modelId: string) => void;
}

export const ModelIdText: React.FC<ModelIdTextProps> = ({ text, known, onSelect }) => {
  const parts = splitModelIds(asText(text));
  return (
    <>
      {parts.map((part, i) =>
        i % 2 === 1 && known.has(part) ? (
          <button
            key={i}
            type="button"
            className="font-mono text-brand-500 hover:underline"
            onClick={(e) => {
              e.stopPropagation();
              onSelect(part);
            }}
            title={`Show ${part} in the leaderboard`}
          >
            {part}
          </button>
        ) : (
          <React.Fragment key={i}>{part}</React.Fragment>
        )
      )}
    </>
  );
};

export default ModelIdText;
