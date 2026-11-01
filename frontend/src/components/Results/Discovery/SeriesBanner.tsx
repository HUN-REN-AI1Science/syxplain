/**
 * SeriesBanner Component
 * Top-of-page note that Syxplain recognised the rows as a time series: what that changed
 * (equations tested on predicting the end of each series) and which earlier conditions were
 * added as inputs. The details are in the time-series section below the equations.
 */

import React from 'react';
import { seriesSummary } from '@utils/discovery';
import type { SeriesReport } from '@/types';

interface SeriesBannerProps {
  series: SeriesReport;
  /** Held-out rows (the final part of each series), when there is a holdout */
  holdoutRows?: number | null;
}

export const SeriesBanner: React.FC<SeriesBannerProps> = ({ series, holdoutRows }) => {
  const { along, tested, added, features } = seriesSummary(series, holdoutRows);
  return (
    <div
      role="note"
      className="bg-[rgba(59,130,246,0.06)] border border-[rgba(59,130,246,0.2)] rounded-xl p-4 flex items-start gap-3"
    >
      <i className="pi pi-chart-line text-brand-500 mt-0.5" aria-hidden="true"></i>
      <div className="min-w-0 flex flex-col gap-2">
        <p className="m-0 font-semibold text-primary">Syxplain detected a time series</p>
        <p className="m-0 text-sm text-secondary leading-relaxed">
          Your rows form {along}. Equations were therefore tested on predicting{' '}
          <strong className="text-primary">{tested}</strong>
          {added}
        </p>
        <div className="flex flex-wrap items-center gap-2">
          <span className="text-xs font-semibold px-2 py-1 rounded-md bg-brand-50 text-brand-500">
            Forward-in-time test
          </span>
          {features.map((f) => (
            <span
              key={f}
              className="text-xs font-semibold font-mono px-2 py-1 rounded-md bg-brand-50 text-brand-500"
            >
              {f}
            </span>
          ))}
          <a href="#series-section" className="text-sm font-medium text-link hover:underline">
            Details below
          </a>
        </div>
      </div>
    </div>
  );
};

export default SeriesBanner;
