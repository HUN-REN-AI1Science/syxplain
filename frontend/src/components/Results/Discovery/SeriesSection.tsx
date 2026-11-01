/**
 * SeriesSection Component
 * Time-series results: when the rows are a long series in time, the feature stage proposed
 * time-dependent features (lags and period aggregates), measured them and selected the
 * useful ones as inputs, and models were scored forward in time. Shows which features were
 * kept, why, and how much memory they explain. Older runs show their lag screening instead.
 */

import React from 'react';
import HelpButton from '@components/HelpButton';
import { asArray, fmtR2, seriesEvidence } from '@utils/discovery';
import type { SeriesReport } from '@/types';

interface SeriesSectionProps {
  series: SeriesReport;
  targetColumn: string;
}

export const SeriesSection: React.FC<SeriesSectionProps> = ({ series, targetColumn }) => {
  const features = asArray(series.lag_features);
  const { gains, before, after } = seriesEvidence(series);
  const stage = series.feature_stage;
  const nCandidates = asArray(series.evidence?.candidates).length;
  const nRejected = asArray(series.rejected).length;
  const padded = series.padded_rows ?? 0;

  return (
    <div>
      <h3 className="text-lg font-bold text-primary font-heading mb-3 flex items-center gap-2">
        <i className="pi pi-history text-brand-500" aria-hidden="true"></i>
        Time series: earlier conditions
        <HelpButton title="Time series">
          <p>
            Your rows form a series along {series.time_column}
            {series.group_column ? `, one per ${series.group_column}` : ''}. {targetColumn} may
            depend on earlier conditions as well as on the current ones. Before the first symbolic
            regression search, an AI step proposed time-dependent features: lagged copies (X_l2 is X
            two steps earlier) and period aggregates (X_mean_year is the mean of X over the same
            calendar year, repeated on each of its rows; X_sum_prev_month the sum over the previous
            month). Each was computed and measured by how much it lowers the cross-validated error
            of a linear model, and a second AI step selected the useful ones as inputs.
          </p>
          <p className="mt-2">
            Where a feature has no history yet (the first steps of a series), it takes the nearest
            available value of that series, so the row is kept. A feature of {targetColumn}&apos;s
            own past is the exception: a value taken from a later row would contain the row&apos;s
            own {targetColumn}, so those first rows are left out.
          </p>
          <p className="mt-2">
            Models are scored forward in time: cross-validation uses contiguous blocks of the series
            and the holdout is its final part, so held-out scores show how well a model predicts
            later periods.
          </p>
        </HelpButton>
      </h3>
      {stage?.status === 'failed' ? (
        <p className="text-sm text-muted mb-2">
          The time-dependent feature step failed, so only the current values were used
          {stage.message ? ` (${stage.message})` : ''}.
        </p>
      ) : features.length === 0 ? (
        <p className="text-sm text-muted mb-2">
          No earlier condition was selected: {targetColumn} is modelled from the current values.
        </p>
      ) : (
        <ul className="space-y-1 mb-2 text-sm">
          {features.map((f) => {
            const gain = gains.get(f.feature);
            return (
              <li key={f.feature} className="text-secondary">
                <code>{f.feature}</code>: {f.description}
                {typeof gain === 'number' && (
                  <span className="text-xs text-muted">
                    {' '}
                    · removes {Math.round(gain * 100)}% of the remaining CV error
                  </span>
                )}
                {f.reason && <span className="block text-xs text-muted ml-4">{f.reason}</span>}
              </li>
            );
          })}
        </ul>
      )}
      {stage?.rationale && <p className="text-xs text-muted mb-1">{stage.rationale}</p>}
      <p className="text-xs text-muted">
        Lag-1 autocorrelation of the residuals: {fmtR2(before)} with the current values only
        {features.length > 0 ? `, ${fmtR2(after)} with the selected features` : ''} (0 = no memory
        left)
        {nCandidates > 0
          ? ` · ${nCandidates} candidates measured${nRejected ? `, ${nRejected} specs rejected` : ''}`
          : ''}
        {padded > 0 ? ` · ${padded} first rows filled with the nearest available value` : ''}
        {(series.rows_without_history ?? 0) > 0
          ? ` · ${series.rows_without_history} first rows lack the history and are not used`
          : ''}
      </p>
    </div>
  );
};

export default SeriesSection;
