/**
 * ShapSection Component
 * Random-forest SHAP summary: feature importance, the shape of each feature's effect,
 * interacting pairs, the SHAP plots and whether the headline equation agrees with them.
 * Hidden when the data shows no clear signal (shap.reliable === false).
 */

import React, { useEffect, useState } from 'react';
import { asText } from '@utils/discovery';
import type { ShapAgreement, ShapPlot, ShapSummary } from '@/types';

/**
 * "saturating increasing — try mitscherlich, ..." -> "saturating increasing"; a label that
 * also reports a disagreeing marginal curve ("...; but the marginal curve looks ...") keeps
 * only its first part (the full text is in the tooltip).
 */
const shapeName = (label: string): string => label.split('; ')[0].split(' — ')[0].split(' (')[0];

const isNegligible = (label: string): boolean =>
  label.trim().toLowerCase().startsWith('negligible');

const VERDICT_STYLE: Record<ShapAgreement['verdict'], { icon: string; className: string }> = {
  agrees: { icon: 'pi-check-circle', className: 'text-green-600' },
  disagrees: { icon: 'pi-exclamation-triangle', className: 'text-amber-600' },
  opposite: { icon: 'pi-times-circle', className: 'text-red-600' },
  ignored: { icon: 'pi-minus-circle', className: 'text-amber-600' },
  undetermined: { icon: 'pi-question-circle', className: 'text-muted' },
};

/** Loads the plot PNGs and shows them as a gallery; click to enlarge. */
const ShapPlots: React.FC<{
  plots: ShapPlot[];
  loadPlot: (filename: string) => Promise<Blob>;
}> = ({ plots, loadPlot }) => {
  const [urls, setUrls] = useState<Record<string, string>>({});
  const [open, setOpen] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    const created: string[] = [];
    Promise.all(
      plots.map((p) =>
        loadPlot(p.name)
          .then((blob) => {
            if (cancelled) {
              return null; // unmounted or re-run: a URL made now would never be revoked
            }
            const url = URL.createObjectURL(blob);
            created.push(url);
            return [p.name, url] as const;
          })
          .catch(() => null)
      )
    ).then((loaded) => {
      if (!cancelled) {
        setUrls(Object.fromEntries(loaded.filter((e) => e !== null)));
      }
    });
    return () => {
      cancelled = true;
      created.forEach(URL.revokeObjectURL);
    };
  }, [plots, loadPlot]);

  const shown = plots.filter((p) => urls[p.name]);
  if (shown.length === 0) {
    return null;
  }
  const enlarged = shown.find((p) => p.name === open);
  return (
    <div className="mt-4">
      <p className="text-xs text-muted mb-2">
        SHAP plots (effect on the target in target units; click to enlarge)
      </p>
      {enlarged && (
        <button
          type="button"
          className="block w-full mb-3 cursor-zoom-out"
          onClick={() => setOpen(null)}
          aria-label={`Close ${enlarged.title}`}
        >
          <img
            src={urls[enlarged.name]}
            alt={enlarged.title}
            className="mx-auto max-w-full rounded border border-[var(--color-border)] bg-white"
          />
        </button>
      )}
      <div className="grid gap-3 grid-cols-2 md:grid-cols-3">
        {shown.map((p) => (
          <button
            key={p.name}
            type="button"
            className={`rounded border bg-white p-1 cursor-zoom-in ${p.name === open ? 'border-brand-500' : 'border-[var(--color-border)]'}`}
            onClick={() => setOpen(p.name === open ? null : p.name)}
            aria-label={`Enlarge ${p.title}`}
          >
            <img src={urls[p.name]} alt={p.title} className="w-full h-auto" loading="lazy" />
          </button>
        ))}
      </div>
    </div>
  );
};

export const ShapSection: React.FC<{
  shap: ShapSummary;
  plots?: ShapPlot[];
  agreement?: ShapAgreement[];
  loadPlot?: (filename: string) => Promise<Blob>;
}> = ({ shap, plots = [], agreement = [], loadPlot }) => {
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
      {agreement.length > 0 && (
        <div className="mt-4">
          <p className="text-xs text-muted mb-1">
            Does the headline equation follow these effects?
          </p>
          <ul className="space-y-1 text-sm">
            {agreement.map((a) => {
              const style = VERDICT_STYLE[a.verdict] ?? VERDICT_STYLE.undetermined;
              return (
                <li key={a.feature} className="flex gap-2 items-start">
                  <i
                    className={`pi ${style.icon} ${style.className} mt-0.5`}
                    aria-hidden="true"
                  ></i>
                  <span className="text-secondary">
                    <span className="font-medium text-primary">{a.feature}</span>: {a.verdict}
                    <span className="text-muted"> — {asText(a.note)}</span>
                  </span>
                </li>
              );
            })}
          </ul>
        </div>
      )}
      {loadPlot && plots.length > 0 && <ShapPlots plots={plots} loadPlot={loadPlot} />}
    </div>
  );
};

export default ShapSection;
