/**
 * Discovery report helpers shared by the results UI and the PDF export
 */

import type {
  CoherenceStatus,
  DiscoveryReport,
  DiscoverySelection,
  DomainCoherence,
  KnownLawRelation,
  MetricBasis,
  RejectedForm,
  ScatterData,
  SeriesReport,
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
  if (!reason) return '';
  if (reason === 'coherent_literature_law')
    return 'A law from your literature: no discovered equation is coherent with it.';
  if (reason === 'no_eligible_model')
    return 'No model met the selection criteria; this is the best available.';
  // <coherent_>base<_weak><_no_coherent_model>: the selector composes the reason
  const coherent = reason.startsWith('coherent_');
  const noCoherent = reason.endsWith('_no_coherent_model');
  let base = reason.replace(/^coherent_/, '').replace(/_no_coherent_model$/, '');
  const weak = base.endsWith('_weak');
  base = base.replace(/_weak$/, '');
  const among = coherent ? ' among the equations coherent with your literature' : '';
  let text: string;
  switch (base) {
    case 'agent_pick_within_1se':
      text = `The agent's pick, within one standard error of the best cross-validated score${among}.`;
      break;
    case 'simplest_within_1se':
    case 'best_cv_1se':
      text = `The simplest model within one standard error of the best cross-validated score${among}.`;
      break;
    case 'best_cv':
      text = `The best cross-validated score${among}.`;
      break;
    default:
      return '';
  }
  if (noCoherent)
    text += ' No equation is coherent with your literature, so the score alone decided.';
  if (weak) text += ' No model passed the strict quality checks.';
  return text;
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

/**
 * Model ids statistically tied with the best cross-validated error (the selector's 1-SE
 * rule), the headline excluded. Runs without the threshold fall back to the shortlist.
 */
export const tiedModelIds = (
  equations: { model_id?: string; cv_rmse?: number | null }[],
  selection: DiscoverySelection | null | undefined
): Set<string> => {
  const headline = selection?.headline_model_id;
  const threshold = selection?.tie_threshold_rmse;
  const ids =
    typeof threshold === 'number'
      ? equations
          .filter((e) => typeof e.cv_rmse === 'number' && e.cv_rmse <= threshold)
          .map((e) => e.model_id)
      : (selection?.shortlist ?? []);
  return new Set(ids.filter((id): id is string => !!id && id !== headline));
};

/** "classic: Mitscherlich" -> "Classic law: Mitscherlich", "symbolic" -> "Symbolic regression" */
export const originLabel = (origin: string): string => {
  if (origin === 'symbolic') return 'Symbolic regression';
  const [kind, ...rest] = origin.split(':');
  const name = rest.join(':').trim();
  const prefix =
    kind === 'classic' ? 'Classic law' : kind === 'literature' ? 'Published law' : 'Agent formula';
  return name ? `${prefix}: ${name}` : prefix;
};

/**
 * What the time-series note says, in parts so the page can emphasise the test period:
 * how the rows were read, which rows the equations were tested on, and what was added.
 */
export const seriesSummary = (
  series: SeriesReport,
  holdoutRows: number | null | undefined
): { along: string; tested: string; added: string; features: string[] } => {
  const features = asArray(series.lag_features).map((f) => f.feature);
  const many = (series.n_series ?? 1) > 1;
  const n = features.length;
  return {
    along: many
      ? `${series.n_series} series along ${series.time_column}, one per ${series.group_column ?? 'trajectory'}`
      : `one series along ${series.time_column}`,
    tested: holdoutRows
      ? `the final ${holdoutRows} rows${many ? ' (the end of each series)' : ''}`
      : 'later periods (cross-validation on contiguous time blocks)',
    added: n
      ? `, and ${n} earlier condition${n > 1 ? 's were' : ' was'} added as input${n > 1 ? 's' : ''}.`
      : '. No earlier condition improved the fit.',
    features,
  };
};

/** Gains per feature and the residual memory before/after, also for runs before the feature stage */
export const seriesEvidence = (series: SeriesReport) => {
  const old = series.screening?.residual_autocorrelation;
  type Scored = { feature: string; gain: number | null };
  const scored = asArray<Scored>(series.evidence?.candidates ?? series.screening?.candidates);
  return {
    gains: new Map(scored.map((c) => [c.feature, c.gain] as const)),
    before: series.residual_autocorrelation?.current_drivers_only ?? old?.current_drivers_only,
    after: series.residual_autocorrelation?.with_selected ?? old?.with_selected_lags,
  };
};

/** Whether the run has anything for the "Does the evidence agree?" section */
export const hasEvidence = (
  report: DiscoveryReport | null | undefined,
  domain: DomainCoherence | null | undefined
): boolean =>
  !!report &&
  (!!report.coherence ||
    !!report.shap?.available ||
    !!report.relations ||
    !!report.literature ||
    domainChecksOf(domain).length > 0 ||
    !!asText(domain?.assessment));
