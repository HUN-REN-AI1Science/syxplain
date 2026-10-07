/**
 * ShapSection Component
 * Random-forest SHAP summary: feature importance, the shape of each feature's effect and
 * interacting pairs. Hidden when the data shows no clear signal (shap.reliable === false).
 */

import React from 'react';
import { asText } from '@utils/discovery';
import type { ShapSummary } from '@/types';

/** "saturating increasing — try mitscherlich, ..." -> "saturating increasing" */
const shapeName = (label: string): string => label.split(' — ')[0].split(' (')[0];

const isNegligible = (label: string): boolean =>
  label.trim().toLowerCase().startsWith('negligible');

export const ShapSection: React.FC<{ shap: ShapSummary }> = ({ shap }) => {
  const heading = (
    <h4 className="text-sm font-semibold text-secondary mb-2 flex items-center gap-2">
      <i className="pi pi-chart-bar text-brand-500" aria-hidden="true"></i>
      Feature effects (SHAP)
    </h4>
  );

  if (shap.reliable === false) {
    return (
      <div>
        {heading}
        <p className="text-sm text-muted">
          <i className="pi pi-eye-slash mr-2" aria-hidden="true"></i>
          SHAP not shown: no clear signal. Feature effects and interactions estimated on data
          without a detectable relationship would only describe noise.
        </p>
      </div>
    );
  }

  const importance = (shap.importance ?? []).filter((f) => typeof f.share === 'number');
  const interactions = (shap.interactions ?? []).filter((p) => p.share_of_attribution >= 0.03);
  const maxShare = Math.max(...importance.map((f) => f.share), 0.01);

  return (
    <div>
      {heading}
      <div className="grid gap-4 md:grid-cols-2">
        <ul className="space-y-1.5">
          {importance.slice(0, 8).map((f) => {
            const effect = asText(shap.partial_effects?.[f.feature]);
            const negligible = isNegligible(effect);
            return (
              <li key={f.feature} className="text-sm">
                <div className="flex justify-between gap-2">
                  <span className={`truncate ${negligible ? 'text-muted' : 'text-primary'}`}>
                    {f.feature}
                  </span>
                  <span
                    className={`text-xs shrink-0 ${negligible ? 'text-muted italic opacity-70' : 'text-secondary'}`}
                    title={effect || undefined}
                  >
                    {effect ? shapeName(effect) : ''}
                  </span>
                </div>
                <div className="h-1.5 rounded-full bg-surface-alt mt-0.5">
                  <div
                    className={`h-1.5 rounded-full ${negligible ? 'bg-[var(--color-border)]' : 'bg-brand-500'}`}
                    style={{ width: `${(f.share / maxShare) * 100}%` }}
                    title={`${(f.share * 100).toFixed(1)}% of attribution`}
                  />
                </div>
              </li>
            );
          })}
        </ul>
        <div>
          <p className="text-xs text-muted mb-1">Interacting pairs (share of attribution)</p>
          {interactions.length > 0 ? (
            <ul className="space-y-1 text-sm text-secondary">
              {interactions.map((p) => (
                <li key={`${p.a}-${p.b}`}>
                  {p.a} × {p.b}{' '}
                  <span className="text-muted tabular-nums">
                    {(p.share_of_attribution * 100).toFixed(1)}%
                  </span>
                </li>
              ))}
            </ul>
          ) : (
            <p className="text-sm text-secondary">
              No notable interactions: effects look additive.
            </p>
          )}
        </div>
      </div>
    </div>
  );
};

export default ShapSection;
