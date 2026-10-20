/**
 * LiteratureSection Component
 * Published laws found for this target, with their sources and how each one scored when fitted
 * to the data (or why it could not be fitted).
 */

import React from 'react';
import { sanitizeUrl } from '@utils/security';
import { asText, fmtR2 } from '@utils/discovery';
import type { DiscoveryReport } from '@/types';

const STATUS_TEXT: Record<string, string> = {
  empty: 'No published laws were found for this target.',
  failed: 'The literature search failed, so no published laws were tested.',
  pending: 'The literature search had not finished when the run completed.',
};

interface LiteratureSectionProps {
  literature: NonNullable<DiscoveryReport['literature']>;
  /** Renders a model id as a leaderboard link when it has a row */
  renderModelId: (modelId: string) => React.ReactNode;
}

export const LiteratureSection: React.FC<LiteratureSectionProps> = ({
  literature,
  renderModelId,
}) => {
  const laws = Array.isArray(literature.laws) ? literature.laws : [];
  return (
    <div>
      <h4 className="text-sm font-semibold text-secondary mb-2 flex items-center gap-2">
        <i className="pi pi-book text-brand-500" aria-hidden="true"></i>
        Published laws tested
      </h4>
      {laws.length === 0 ? (
        <p className="text-sm text-muted">{STATUS_TEXT[literature.status] ?? STATUS_TEXT.empty}</p>
      ) : (
        <ul className="space-y-2">
          {laws.map((law, i) => {
            const citations = (law.citations ?? [])
              .map((c) => sanitizeUrl(asText(c)))
              .filter(Boolean);
            const unmapped = (law.unmapped ?? []).map(asText).filter(Boolean);
            let fit: React.ReactNode;
            if (law.model_id && typeof law.cv_r2 === 'number') {
              fit = (
                <>
                  Fitted as {renderModelId(law.model_id)}: CV R² {fmtR2(law.cv_r2)}
                </>
              );
            } else if (law.fit_error) {
              fit = <>Not fitted: {asText(law.fit_error)}</>;
            } else if (unmapped.length > 0) {
              fit = <>Not fitted: unmapped variables {unmapped.join(', ')}</>;
            } else if (law.model_id) {
              fit = <>Fitted as {renderModelId(law.model_id)}</>;
            }
            return (
              <li
                key={i}
                className="text-sm bg-surface-alt rounded-lg px-3 py-2 border border-[var(--color-border)]"
              >
                <code className="font-mono text-primary break-words">{asText(law.equation)}</code>
                {fit && <p className="text-xs text-secondary mt-1">{fit}</p>}
                {citations.length > 0 && (
                  <p className="text-xs mt-1 flex flex-wrap gap-x-3 gap-y-1">
                    {citations.map((url, c) => (
                      <a
                        key={c}
                        href={url}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="text-link hover:underline break-all"
                      >
                        [{c + 1}] {url}
                      </a>
                    ))}
                  </p>
                )}
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
};

export default LiteratureSection;
