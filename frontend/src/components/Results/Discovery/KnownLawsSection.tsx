/**
 * KnownLawsSection Component
 * How the headline equation relates to known laws. The agent explores without seeing any
 * named or published law; afterwards the classic catalog and the literature laws are fitted
 * to the same data and compared with the discovery, by their predictions (backend verdicts).
 * Hidden for runs from before the blind exploration.
 */

import React from 'react';
import { Tag } from 'primereact/tag';
import HelpButton from '@components/HelpButton';
import {
  asText,
  fmtR2,
  KNOWN_LAW_COMPARISON_TEXT,
  KNOWN_LAW_RELATION_LABEL,
} from '@utils/discovery';
import type { KnownLawRelation, KnownLawRelations } from '@/types';

const RELATION_SEVERITY: Record<
  KnownLawRelation['relation'],
  'success' | 'info' | 'warning' | 'secondary'
> = {
  equivalent: 'success',
  similar: 'info',
  partial: 'warning',
  different: 'secondary',
};

const KIND_TEXT: Record<KnownLawRelation['kind'], string> = {
  classic: 'named law',
  literature: 'published law',
};

interface KnownLawsSectionProps {
  relations: KnownLawRelations;
  /** Renders a model id as a leaderboard link when it has a row */
  renderModelId: (modelId: string) => React.ReactNode;
  /** No discovered equation was usable, so the headline is itself a known law */
  headlineIsReference?: boolean;
}

export const KnownLawsSection: React.FC<KnownLawsSectionProps> = ({
  relations,
  renderModelId,
  headlineIsReference = false,
}) => {
  const rows = Array.isArray(relations.headline) ? relations.headline : [];
  const n = relations.n_known_laws ?? { classic: 0, literature: 0 };
  const emptyText = headlineIsReference
    ? 'No discovered equation was usable, so the recommended equation is itself a known law.'
    : n.classic + n.literature > 0
      ? 'No discovered equation was recommended to compare with the known laws.'
      : 'No known law fits these data better than the mean.';
  return (
    <div>
      <h4 className="text-sm font-semibold text-secondary mb-2 flex items-center gap-2">
        <i className="pi pi-sitemap text-brand-500" aria-hidden="true"></i>
        Relation to known laws
        <HelpButton title="Relation to known laws">
          <p>
            The AI agent searched for equations from your data alone, without seeing any named or
            published law, so that known forms do not bias the search. Afterwards the classic named
            laws and the laws found in the literature were fitted to the same data and compared with
            the recommended equation through their predictions.
          </p>
          <p className="mt-2">
            &ldquo;Same law, other form&rdquo; means the discovery rediscovered that law;
            &ldquo;covers part of it&rdquo; means the law describes some of its variables and the
            discovery adds the others; &ldquo;different&rdquo; means a new relationship for these
            data.
          </p>
        </HelpButton>
      </h4>
      <p className="text-xs text-muted mb-2">
        {n.classic} named and {n.literature} published laws were fitted after the discovery, for
        comparison.
      </p>
      {rows.length === 0 ? (
        <p className="text-sm text-muted">{emptyText}</p>
      ) : (
        <ul className="space-y-2">
          {rows.map((r) => {
            const relation = r.relation in RELATION_SEVERITY ? r.relation : 'different';
            return (
              <li
                key={r.law_id}
                className="text-sm bg-surface-alt rounded-lg px-3 py-2 border border-[var(--color-border)]"
              >
                <div className="flex flex-wrap items-center gap-2">
                  <Tag
                    value={KNOWN_LAW_RELATION_LABEL[relation]}
                    severity={RELATION_SEVERITY[relation]}
                    className="text-xs"
                  />
                  <span className="font-medium text-primary">{asText(r.label)}</span>
                  <span className="text-xs text-muted">
                    {KIND_TEXT[r.kind] ?? r.kind} · {renderModelId(r.law_id)}
                  </span>
                </div>
                <code className="block font-mono text-xs text-secondary mt-1 break-words">
                  {asText(r.equation)}
                </code>
                <p className="text-xs text-secondary mt-1">
                  {KNOWN_LAW_COMPARISON_TEXT[r.comparison] ?? ''} (CV R² {fmtR2(r.cv_r2)}) ·
                  predictions agree R² {fmtR2(r.agreement_r2)}
                  {r.relation === 'partial' && typeof r.shape_r2 === 'number' && (
                    <>
                      {' '}
                      · same shape along {r.shared_features.join(', ')} (R² {fmtR2(r.shape_r2)})
                    </>
                  )}
                </p>
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
};

export default KnownLawsSection;
