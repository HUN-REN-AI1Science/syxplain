/**
 * CoherenceSection Component
 * Do the independent lines of evidence agree on the headline equation? The backend's
 * checks (noise ceiling, holdout, SHAP, published and named laws, parameters, agent) with
 * an overall verdict, then the explanation AI's domain-plausibility judgement.
 * Hidden for runs without a coherence report.
 */

import React from 'react';
import { Tag } from 'primereact/tag';
import HelpButton from '@components/HelpButton';
import {
  asText,
  COHERENCE_LABEL,
  COHERENCE_OVERALL_LABEL,
  DOMAIN_STATUS,
  domainChecksOf,
} from '@utils/discovery';
import type { CoherenceReport, CoherenceStatus, DomainCoherence } from '@/types';

const STATUS_ICON: Record<CoherenceStatus, string> = {
  pass: 'pi-check-circle text-green-600',
  warn: 'pi-exclamation-triangle text-amber-600',
  fail: 'pi-times-circle text-red-600',
  na: 'pi-minus-circle text-muted',
};

const OVERALL_SEVERITY: Record<CoherenceStatus, 'success' | 'warning' | 'danger' | 'info'> = {
  pass: 'success',
  warn: 'warning',
  fail: 'danger',
  na: 'info',
};

const CheckRow: React.FC<{ status: CoherenceStatus; title: unknown; detail: unknown }> = ({
  status,
  title,
  detail,
}) => {
  const known = status in STATUS_ICON ? status : 'na';
  return (
    <li className="flex gap-2 items-start">
      <i
        className={`pi ${STATUS_ICON[known]} mt-0.5`}
        title={COHERENCE_LABEL[known]}
        aria-label={COHERENCE_LABEL[known]}
      ></i>
      <span className="text-secondary">
        <span className="font-medium text-primary">{asText(title)}</span>
        <span className="text-muted"> — {asText(detail)}</span>
      </span>
    </li>
  );
};

interface CoherenceSectionProps {
  report: CoherenceReport;
  domain?: DomainCoherence | null;
}

export const CoherenceSection: React.FC<CoherenceSectionProps> = ({ report, domain }) => {
  const checks = Array.isArray(report.checks) ? report.checks : [];
  const domainChecks = domainChecksOf(domain);
  const assessment = asText(domain?.assessment);
  const overall = report.overall in OVERALL_SEVERITY ? report.overall : 'na';

  return (
    <section className="rounded-xl border border-[var(--color-border)] bg-surface p-6 space-y-5">
      <div className="flex items-center gap-2 flex-wrap">
        <h3 className="text-lg font-bold text-primary font-heading flex items-center gap-2">
          <i className="pi pi-link text-brand-500" aria-hidden="true"></i>
          Coherence of the recommended equation
        </h3>
        <Tag value={COHERENCE_OVERALL_LABEL[overall]} severity={OVERALL_SEVERITY[overall]} />
        <span className="text-xs text-muted font-mono">{report.model_id}</span>
        <HelpButton title="Coherence">
          <p>
            A good equation should be supported by every independent line of evidence, not only by
            its score. Each check compares the recommended equation with one of them:
          </p>
          <ul>
            <li>
              <strong>Noise ceiling</strong>: how close it gets to the best accuracy a flexible
              model reaches on these data.
            </li>
            <li>
              <strong>Generalization</strong>: whether it scores as well on rows set aside before
              any model was fitted.
            </li>
            <li>
              <strong>SHAP effects</strong>: whether it moves with each important variable the way
              the data does.
            </li>
            <li>
              <strong>Published and named laws</strong>: whether established laws fit as well, or
              the equation is a new claim that needs checking.
            </li>
            <li>
              <strong>Parameters</strong>: whether the data pins down every constant and the
              equation is defined on every row.
            </li>
            <li>
              <strong>Agent</strong>: whether the discovery agent reached the same conclusion.
            </li>
          </ul>
          <p>
            These checks are computed, not written by AI. The domain plausibility below is the
            explanation AI&apos;s judgement of whether the effect directions and limits make
            scientific sense.
          </p>
        </HelpButton>
      </div>

      <ul className="space-y-2 text-sm">
        {checks.map((c) => (
          <CheckRow key={c.key} status={c.status} title={c.label} detail={c.detail} />
        ))}
      </ul>

      {(domainChecks.length > 0 || assessment) && (
        <div className="space-y-2">
          <p className="text-xs text-muted">Domain plausibility (AI assessment)</p>
          {domainChecks.length > 0 && (
            <ul className="space-y-2 text-sm">
              {domainChecks.map((d, i) => (
                <CheckRow
                  key={`${d.aspect}-${i}`}
                  status={DOMAIN_STATUS[d.status] ?? 'na'}
                  title={d.aspect}
                  detail={d.explanation}
                />
              ))}
            </ul>
          )}
          {assessment && <p className="text-sm text-primary leading-relaxed">{assessment}</p>}
        </div>
      )}
    </section>
  );
};

export default CoherenceSection;
