/**
 * DynamicsSection Component
 * Rate-law results: when the rows are measurements over time and the agent confirmed it,
 * it also looked for d(target)/dt = f(target, inputs) with its own formulas and SINDy.
 * Shows the recommended rate law, the other candidates and the law integrated over the
 * (held-out) trajectories next to the measurements.
 */

import React, { useMemo, useState } from 'react';
import {
  Chart as ChartJS,
  Legend,
  LinearScale,
  LineElement,
  PointElement,
  Tooltip,
} from 'chart.js';
import { Scatter } from 'react-chartjs-2';
import { Tag } from 'primereact/tag';
import HelpButton from '@components/HelpButton';
import { asArray, asText, fmtR2 } from '@utils/discovery';
import type { DynamicsReport, RateLawEntry, TrajectoryTrace } from '@/types';

ChartJS.register(LinearScale, PointElement, LineElement, Tooltip, Legend);

const COLORS = ['0, 82, 204', '220, 38, 38', '22, 163, 74', '202, 138, 4', '147, 51, 234'];
const MAX_PLOTTED = 5;

const TrajectoryPlot: React.FC<{
  traces: TrajectoryTrace[];
  timeLabel: string;
  targetLabel: string;
}> = ({ traces, timeLabel, targetLabel }) => {
  const data = useMemo(
    () => ({
      datasets: traces.slice(0, MAX_PLOTTED).flatMap((tr, i) => {
        const color = COLORS[i % COLORS.length];
        const measured = {
          label: `${tr.trajectory} measured`,
          data: tr.t.map((t, j) => ({ x: t, y: tr.measured[j] })),
          backgroundColor: `rgba(${color}, 0.6)`,
          pointRadius: 3,
        };
        if (!tr.simulated) return [measured];
        return [
          measured,
          {
            label: `${tr.trajectory} simulated`,
            data: tr.t.map((t, j) => ({ x: t, y: tr.simulated![j] })),
            showLine: true,
            borderColor: `rgba(${color}, 0.9)`,
            borderWidth: 2,
            pointRadius: 0,
            fill: false,
          },
        ];
      }),
    }),
    [traces]
  );
  const options = useMemo(
    () => ({
      responsive: true,
      maintainAspectRatio: true,
      aspectRatio: 1.6,
      plugins: {
        legend: { position: 'top' as const, labels: { usePointStyle: true, font: { size: 10 } } },
      },
      scales: {
        x: { title: { display: true, text: timeLabel, font: { size: 12 } } },
        y: { title: { display: true, text: targetLabel, font: { size: 12 } } },
      },
    }),
    [timeLabel, targetLabel]
  );
  return (
    <div className="w-full max-w-xl">
      <Scatter data={data} options={options} />
    </div>
  );
};

const RateLawCard: React.FC<{
  law: RateLawEntry;
  rate: string;
  renderModelId: (id: string) => React.ReactNode;
}> = ({ law, rate, renderModelId }) => (
  <li className="text-sm bg-surface-alt rounded-lg px-3 py-2 border border-[var(--color-border)]">
    <div className="flex flex-wrap items-center gap-2">
      {renderModelId(law.model_id)}
      {law.is_headline && <Tag value="recommended" severity="success" className="text-xs" />}
      {law.agent_recommended && !law.is_headline && (
        <Tag value="agent pick" severity="info" className="text-xs" />
      )}
      <span className="text-xs text-muted">{law.source ? `SINDy (${law.source})` : law.label}</span>
    </div>
    <code className="block mt-1 text-primary break-all">
      {rate} = {law.equation}
    </code>
    <p className="text-xs text-muted mt-1">
      derivative CV R² {fmtR2(law.dydt_cv_r2)} · simulation R² {fmtR2(law.simulation_train_r2)}
      {typeof law.holdout_r2 === 'number'
        ? ` · held-out simulation R² ${fmtR2(law.holdout_r2)}`
        : ''}
      {law.simulation_diverged ? ` · diverges on ${law.simulation_diverged} trajectories` : ''}
    </p>
    {law.not_recommended && (
      <p className="text-xs text-muted mt-1">Not recommended: {law.not_recommended}</p>
    )}
    {law.agent_why && <p className="text-secondary mt-1">{asText(law.agent_why)}</p>}
  </li>
);

interface DynamicsSectionProps {
  dynamics: DynamicsReport;
  targetColumn: string;
  renderModelId: (modelId: string) => React.ReactNode;
}

export const DynamicsSection: React.FC<DynamicsSectionProps> = ({
  dynamics,
  targetColumn,
  renderModelId,
}) => {
  const laws = asArray(dynamics.equations);
  const headline = laws.find((l) => l.is_headline) ?? null;
  const [plotId, setPlotId] = useState<string | null>(null);
  const plotted =
    laws.find((l) => l.model_id === plotId && l.traces) ??
    (headline?.traces ? headline : laws.find((l) => l.traces));
  const split = dynamics.split;
  return (
    <div>
      <h3 className="text-lg font-bold text-primary font-heading mb-3 flex items-center gap-2">
        <i className="pi pi-chart-line text-brand-500" aria-hidden="true"></i>
        Rate law (dynamics)
        <HelpButton title="Rate law">
          <p>
            Your rows are measurements over time ({split.time_column}
            {split.group_column ? `, one trajectory per ${split.group_column}` : ''}). Besides the
            equation for {targetColumn} itself, the AI agent looked for the law of its rate of
            change, d{dynamics.state}/dt, using its own formulas and SINDy (sparse regression over
            candidate terms).
          </p>
          <p className="mt-2">
            The derivative R² is not comparable with the R² of the other equations. The real test is
            the simulation: the law is integrated from the start of each trajectory and compared
            with the measurements, on {split.scored_on}.
          </p>
        </HelpButton>
      </h3>
      <p className="text-xs text-muted mb-2">
        {split.trajectories} trajectories along {split.time_column} · inputs{' '}
        {dynamics.inputs.length ? dynamics.inputs.join(', ') : 'none'} · {dynamics.n_models} rate
        laws fitted
        {typeof dynamics.dydt_noise_ceiling_r2 === 'number'
          ? ` · derivative noise ceiling ${fmtR2(dynamics.dydt_noise_ceiling_r2)}`
          : ''}
      </p>
      {laws.length === 0 ? (
        <p className="text-sm text-muted">No rate law was fitted.</p>
      ) : (
        <>
          {!headline && (
            <p className="text-sm text-muted mb-2">
              No rate law passed the checks, so none is recommended.
            </p>
          )}
          <ul className="space-y-2">
            {laws.map((law) => (
              <RateLawCard
                key={law.model_id}
                law={law}
                rate={dynamics.rate}
                renderModelId={renderModelId}
              />
            ))}
          </ul>
          {plotted?.traces && (
            <div className="mt-3">
              <div className="flex flex-wrap items-center gap-2 mb-1">
                <span className="text-xs text-muted">
                  Simulated vs measured (
                  {plotted.traces_basis === 'holdout' ? 'held-out' : 'training'} trajectories):
                </span>
                {laws
                  .filter((l) => l.traces)
                  .map((l) => (
                    <button
                      key={l.model_id}
                      type="button"
                      onClick={() => setPlotId(l.model_id)}
                      className={`text-xs font-mono px-2 py-0.5 rounded border border-[var(--color-border)] ${
                        l.model_id === plotted.model_id ? 'bg-brand-500 text-white' : ''
                      }`}
                    >
                      {l.model_id}
                    </button>
                  ))}
              </div>
              <TrajectoryPlot
                traces={plotted.traces}
                timeLabel={split.time_column}
                targetLabel={targetColumn}
              />
            </div>
          )}
        </>
      )}
    </div>
  );
};
