/**
 * SeriesSection Component
 * Time-series results: when the rows are a long series in time, earlier conditions
 * (lagged copies of the predictors and of the target) were screened and the useful ones
 * added as features, and models were scored forward in time. Shows which lags were kept
 * and how much memory they explain.
 */

import React from 'react';
import HelpButton from '@components/HelpButton';
import { asArray, fmtR2 } from '@utils/discovery';
import type { SeriesReport } from '@/types';

interface SeriesSectionProps {
  series: SeriesReport;
  targetColumn: string;
}

export const SeriesSection: React.FC<SeriesSectionProps> = ({ series, targetColumn }) => {
  const lags = asArray(series.lag_features);
  const gains = new Map(
    asArray(series.screening?.candidates).map((c) => [c.feature, c.gain] as const)
  );
  const ac = series.screening?.residual_autocorrelation;
  return (
    <div>
      <h4 className="text-sm font-semibold text-secondary mb-2 flex items-center gap-2">
        <i className="pi pi-history text-brand-500" aria-hidden="true"></i>
        Time series: earlier conditions
        <HelpButton title="Time series">
          <p>
            Your rows form a series along {series.time_column}
            {series.group_column ? `, one per ${series.group_column}` : ''}. {targetColumn} may
            depend on earlier conditions as well as on the current ones, so lagged copies of the
            variables were tested: X_l2 is X two steps earlier, X_m3 the mean of X over the previous
            three steps. A lag was added as a feature only when it lowered the cross-validated
            error, beyond what the current values explain.
          </p>
          <p className="mt-2">
            Models are scored forward in time: cross-validation uses contiguous blocks of the series
            and the holdout is its final part, so held-out scores show how well a model predicts
            later periods.
          </p>
        </HelpButton>
      </h4>
      {lags.length === 0 ? (
        <p className="text-sm text-muted mb-2">
          No earlier condition improved the fit: {targetColumn} follows the current values.
        </p>
      ) : (
        <ul className="space-y-1 mb-2 text-sm">
          {lags.map((lag) => {
            const gain = gains.get(lag.feature);
            return (
              <li key={lag.feature} className="text-secondary">
                <code>{lag.feature}</code>: {lag.description}
                {typeof gain === 'number' && (
                  <span className="text-xs text-muted">
                    {' '}
                    · removes {Math.round(gain * 100)}% of the remaining CV error
                  </span>
                )}
              </li>
            );
          })}
        </ul>
      )}
      <p className="text-xs text-muted">
        Lag-1 autocorrelation of the residuals: {fmtR2(ac?.current_drivers_only)} with the current
        values only
        {lags.length > 0 ? `, ${fmtR2(ac?.with_selected_lags)} with the lags` : ''} (0 = no memory
        left)
        {series.rows_without_history > 0
          ? ` · ${series.rows_without_history} first rows lack the history and are not used`
          : ''}
      </p>
    </div>
  );
};

export default SeriesSection;
