/**
 * Discovery report helpers shared by the results UI and the PDF export
 */

import type { MetricBasis, RejectedForm, ScatterData } from '@/types';

/**
 * Renders an LLM-authored value as text. Stored runs may hold objects where a string
 * was expected (e.g. {text, evidence}); never let those crash the page or print "undefined".
 */
export const asText = (x: unknown): string => {
  if (typeof x === 'string') return x;
  if (x === null || x === undefined) return '';
  if (typeof x === 'number' || typeof x === 'boolean') return String(x);
  if (typeof x === 'object') {
    const obj = x as Record<string, unknown>;
    for (const key of ['text', 'description', 'value']) {
      if (typeof obj[key] === 'string') return obj[key] as string;
    }
  }
  try {
    return JSON.stringify(x);
  } catch {
    return String(x);
  }
};

/** "form: reason"; old runs may store plain strings */
export const rejectedFormText = (r: RejectedForm | string | unknown): string => {
  if (!r || typeof r !== 'object') return asText(r);
  const { form, reason } = r as Partial<RejectedForm>;
  const text = [asText(form), asText(reason)].filter(Boolean).join(': ');
  return text || asText(r);
};

export const rejectedFormModelId = (r: RejectedForm | string | unknown): string => {
  if (!r || typeof r !== 'object') return '';
  const id = (r as Partial<RejectedForm>).model_id;
  return typeof id === 'string' ? id : '';
};

export const fmtR2 = (v: number | null | undefined): string =>
  typeof v === 'number' ? v.toFixed(3) : '—';

/** Noise ceiling with its spread across repeated fits, e.g. "0.812 ± 0.021" */
export const fmtCeiling = (ceiling: number | null | undefined, sd?: number | null): string =>
  typeof ceiling === 'number' && typeof sd === 'number' && sd > 0
    ? `${ceiling.toFixed(3)} ± ${sd.toFixed(3)}`
    : fmtR2(ceiling);

/** Missing metric_basis means a run from before the field existed: those used a holdout */
export const basisOf = (basis: MetricBasis | null | undefined): MetricBasis =>
  basis === 'cv' ? 'cv' : 'holdout';

/** Full label of the score a model is ranked by */
export const metricLabel = (basis: MetricBasis | null | undefined, holdoutN?: number | null) =>
  basisOf(basis) === 'cv'
    ? 'CV R² (cross-validated; dataset too small for a holdout)'
    : typeof holdoutN === 'number' && holdoutN > 0
      ? `Held-out R² (n=${holdoutN})`
      : 'Held-out R²';

/** Short column header for tables */
export const metricShortLabel = (
  basis: MetricBasis | null | undefined,
  holdoutN?: number | null
) => (basisOf(basis) === 'cv' ? 'CV R²' : metricLabel(basis, holdoutN));

/** The R² on the metric basis (falls back across fields for old runs) */
export const metricValue = (m: {
  metric_basis?: MetricBasis | null;
  holdout_r2?: number | null;
  cv_r2?: number | null;
  score?: number | null;
}): number | null => {
  const pick =
    basisOf(m.metric_basis) === 'cv' ? (m.cv_r2 ?? m.score) : (m.holdout_r2 ?? m.score ?? m.cv_r2);
  return typeof pick === 'number' ? pick : null;
};

/** Which predictions a measured-vs-predicted plot shows, or '' when unknown (old runs) */
export const scatterBasisLabel = (data: ScatterData | undefined): string => {
  if (data?.basis === 'cv_oof') return 'out-of-fold CV predictions';
  if (data?.basis === 'holdout') return 'held-out rows';
  return '';
};

/** Model ids such as C12, M3, S40, L1 */
export const MODEL_ID_PATTERN = /\b([CMSL]\d+)\b/;

/** Splits text into plain parts (even indices) and model-id tokens (odd indices) */
export const splitModelIds = (text: string): string[] =>
  text.split(new RegExp(MODEL_ID_PATTERN.source, 'g'));

/** Human wording for the selector's headline reason */
export const headlineReasonText = (reason: string | null | undefined): string => {
  switch (reason) {
    case 'agent_pick_within_1se':
      return "The agent's pick, within one standard error of the best cross-validated score.";
    case 'best_cv_1se':
      return 'The simplest model within one standard error of the best cross-validated score.';
    case 'no_eligible_model':
      return 'No model met the selection criteria; this is the best available.';
    default:
      return '';
  }
};

/** alias = column pairs, skipping identity mappings */
export const variableLegend = (variables: Record<string, string> | undefined): [string, string][] =>
  Object.entries(variables ?? {}).filter(
    ([alias, col]) => typeof col === 'string' && alias !== col
  );
