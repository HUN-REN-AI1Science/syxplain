/**
 * Discovery report helpers shared by the results UI and the PDF export
 */

import type {
  CoherenceStatus,
  DomainCoherence,
  KnownLawRelation,
  MetricBasis,
  RejectedForm,
  ScatterData,
} from '@/types';

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

/** The value if it is an array, otherwise [] (stored reports may lack fields) */
export const asArray = <T>(x: T[] | null | undefined): T[] => (Array.isArray(x) ? x : []);

/** Model ids such as C12, M3, S40, L1, D7 (rate laws) */
export const MODEL_ID_PATTERN = /\b([CMSLD]\d+)\b/;

/** Splits text into plain parts (even indices) and model-id tokens (odd indices) */
export const splitModelIds = (text: string): string[] =>
  text.split(new RegExp(MODEL_ID_PATTERN.source, 'g'));

/** Human wording for the selector's headline reason */
export const headlineReasonText = (reason: string | null | undefined): string => {
  // '_weak': no model passed the strict checks, so the headline is the best usable one
  const weak = reason?.endsWith('_weak') ?? false;
  const base = weak ? reason!.slice(0, -'_weak'.length) : reason;
  const caveat = weak ? ' No model passed every check; treat it with caution.' : '';
  switch (base) {
    case 'agent_pick_within_1se':
      return `The agent's pick, within one standard error of the best cross-validated score.${caveat}`;
    case 'dominates_agent_pick':
      return `No more complex than the agent's pick and with a lower cross-validated error, so it replaces that pick.${caveat}`;
    case 'simplest_within_1se':
    case 'best_cv_1se':
      return `The simplest model within one standard error of the best cross-validated score.${caveat}`;
    case 'best_cv':
      return `The best cross-validated score, and no simpler model is within one standard error of it.${caveat}`;
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

/** Wording of a coherence check's status (results page and PDF) */
export const COHERENCE_LABEL: Record<CoherenceStatus, string> = {
  pass: 'agrees',
  warn: 'caution',
  fail: 'conflict',
  na: 'not available',
};

/** How a discovered equation relates to a known law (results page and PDF) */
export const KNOWN_LAW_RELATION_LABEL: Record<KnownLawRelation['relation'], string> = {
  equivalent: 'same law, other form',
  similar: 'similar predictions',
  partial: 'covers part of it',
  different: 'different',
};

/** The known law's accuracy against the discovered equation */
export const KNOWN_LAW_COMPARISON_TEXT: Record<KnownLawRelation['comparison'], string> = {
  better: 'fits better',
  tied: 'fits as well',
  worse: 'fits worse',
};

/** Overall coherence verdict */
export const COHERENCE_OVERALL_LABEL: Record<CoherenceStatus, string> = {
  pass: 'Coherent',
  warn: 'Partly coherent',
  fail: 'Conflicting evidence',
  na: 'Not assessed',
};

/** The explanation AI's domain-plausibility status mapped onto the check statuses */
export const DOMAIN_STATUS: Record<string, CoherenceStatus> = {
  consistent: 'pass',
  questionable: 'warn',
  inconsistent: 'fail',
};

/** The AI's domain checks, dropping entries that are not objects (LLM output is unvalidated) */
export const domainChecksOf = (
  domain: DomainCoherence | null | undefined
): NonNullable<DomainCoherence['domain_checks']> =>
  Array.isArray(domain?.domain_checks)
    ? domain.domain_checks.filter((d) => d !== null && typeof d === 'object')
    : [];
