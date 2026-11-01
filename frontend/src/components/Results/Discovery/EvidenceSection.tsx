/**
 * EvidenceSection Component
 * "Does the evidence agree?": every independent line of evidence about the recommended
 * equation in one place, one row per check that opens for its detail. The backend's coherence
 * checks (noise ceiling, holdout, SHAP, published and named laws, parameters, agent) carry the
 * verdicts; the SHAP effects, the relation to known laws and the published laws tested open
 * under their check. The explanation AI's domain-plausibility judgement follows.
 */

import React, { useState } from 'react';
import { Tag } from 'primereact/tag';
import HelpButton from '@components/HelpButton';
import {
  asArray,
  asText,
  COHERENCE_LABEL,
  COHERENCE_OVERALL_LABEL,
  DOMAIN_STATUS,
  domainChecksOf,
  hasEvidence,
} from '@utils/discovery';
import { KnownLawsSection } from './KnownLawsSection';
import { LiteratureSection } from './LiteratureSection';
import { ShapSection } from './ShapSection';
import type { CoherenceStatus, DiscoveryReport, DomainCoherence } from '@/types';

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

/** Which detail section opens under which check */
type Extra = 'shap' | 'named_laws' | 'literature';

interface Row {
  key: string;
  status: CoherenceStatus;
  label: string;
  detail: string;
  extra?: Extra;
}

const plainId = (id: string) => <span className="font-mono">{id}</span>;

const StatusIcon: React.FC<{ status: CoherenceStatus }> = ({ status }) => {
  const known = status in STATUS_ICON ? status : 'na';
  return (
    <i
      className={`pi ${STATUS_ICON[known]} mt-0.5 shrink-0`}
      title={COHERENCE_LABEL[known]}
      aria-label={COHERENCE_LABEL[known]}
    ></i>
  );
};

interface EvidenceSectionProps {
  report: DiscoveryReport;
  domain?: DomainCoherence | null;
  loadPlot?: (filename: string) => Promise<Blob>;
}

export const EvidenceSection: React.FC<EvidenceSectionProps> = ({ report, domain, loadPlot }) => {
  const [open, setOpen] = useState<Set<string>>(() => new Set());
  // Rows opened once stay mounted (hidden when closed), so SHAP plots load only once
  const [visited, setVisited] = useState<Set<string>>(() => new Set());
  const coherence = report.coherence ?? null;
  const available: Record<Extra, boolean> = {
    shap: !!report.shap?.available,
    named_laws: !!report.relations,
    literature: !!report.literature,
  };

  const rows: Row[] = asArray(coherence?.checks).map((c) => ({
    key: c.key,
    status: c.status,
    label: asText(c.label),
    detail: asText(c.detail),
    extra: c.key in available && available[c.key as Extra] ? (c.key as Extra) : undefined,
  }));
  // Sections without a check of their own (older runs, or a check that was not computed)
  const claimed = new Set(rows.map((r) => r.extra));
  const fallbackLabels: Record<Extra, string> = {
    shap: 'Feature effects (SHAP)',
    named_laws: 'Relation to known laws',
    literature: 'Published laws tested',
  };
  const fallback: Row[] = (Object.keys(fallbackLabels) as Extra[])
    .filter((extra) => available[extra] && !claimed.has(extra))
    .map((extra) => ({
      key: extra,
      extra,
      label: fallbackLabels[extra],
      status: 'na' as CoherenceStatus,
      detail: '',
    }));
  const all = [...rows, ...fallback];

  const domainChecks = domainChecksOf(domain);
  const assessment = asText(domain?.assessment);
  if (!hasEvidence(report, domain)) return null;
  const overall = coherence && coherence.overall in OVERALL_SEVERITY ? coherence.overall : null;

  const toggle = (key: string) => {
    setVisited((prev) => (prev.has(key) ? prev : new Set(prev).add(key)));
    setOpen((prev) => {
      const next = new Set(prev);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });
  };

  const renderExtra = (extra: Extra) => {
    if (extra === 'shap' && report.shap) {
      return (
        <ShapSection
          shap={report.shap}
          plots={asArray(report.shap_plots)}
          agreement={asArray(report.shap_agreement)}
          loadPlot={loadPlot}
        />
      );
    }
    if (extra === 'named_laws' && report.relations) {
      return (
        <KnownLawsSection
          relations={report.relations}
          renderModelId={plainId}
          headlineIsReference={report.selection?.headline_is_reference === true}
        />
      );
    }
    if (extra === 'literature' && report.literature) {
      return <LiteratureSection literature={report.literature} renderModelId={plainId} />;
    }
    return null;
  };

  return (
    <section
      id="evidence"
      className="rounded-xl border border-[var(--color-border)] bg-surface p-6 space-y-4"
    >
      <div className="flex items-center gap-2 flex-wrap">
        <h3 className="text-lg font-bold text-primary font-heading flex items-center gap-2">
          <i className="pi pi-link text-brand-500" aria-hidden="true"></i>
          Does the evidence agree?
        </h3>
        {overall && (
          <Tag value={COHERENCE_OVERALL_LABEL[overall]} severity={OVERALL_SEVERITY[overall]} />
        )}
        <HelpButton title="Evidence">
          <p>
            A good equation should be supported by every independent line of evidence, not only by
            its score. Each row compares the recommended equation with one of them:
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
              the data does. Open the row for the importance, interactions and plots.
            </li>
            <li>
              <strong>Published and named laws</strong>: whether established laws fit as well, or
              the equation is a new claim. Open the rows for every law that was fitted.
            </li>
            <li>
              <strong>Parameters</strong>: whether the data pins down every constant and the
              equation is defined on every row.
            </li>
            <li>
              <strong>Agent</strong>: whether the discovery agent&apos;s statements held when
              checked.
            </li>
          </ul>
          <p>
            These checks are computed, not written by AI. The domain plausibility below is the
            explanation AI&apos;s judgement of whether the effect directions and limits make
            scientific sense.
          </p>
        </HelpButton>
      </div>

      {all.length > 0 && (
        <ul className="m-0 p-0 list-none border border-[var(--color-border)] rounded-lg divide-y divide-[var(--color-border)]">
          {all.map((row) => {
            const expandable = !!row.extra;
            const isOpen = expandable && open.has(row.key);
            const label = (
              <>
                <StatusIcon status={row.status} />
                <span className="flex-1 min-w-0 text-secondary">
                  <span className="font-medium text-primary">{row.label}</span>
                  {row.detail && <span className="text-muted"> — {row.detail}</span>}
                </span>
              </>
            );
            return (
              <li key={row.key}>
                {expandable ? (
                  <button
                    type="button"
                    onClick={() => toggle(row.key)}
                    aria-expanded={isOpen}
                    className="w-full flex items-start gap-2 px-4 py-3 text-left text-sm bg-transparent border-0 cursor-pointer hover:bg-surface-alt transition-colors"
                  >
                    {label}
                    <i
                      className={`pi ${isOpen ? 'pi-chevron-up' : 'pi-chevron-down'} text-xs text-muted mt-1`}
                      aria-hidden="true"
                    ></i>
                  </button>
                ) : (
                  <div className="flex items-start gap-2 px-4 py-3 text-sm">{label}</div>
                )}
                {row.extra && visited.has(row.key) && (
                  <div className="px-4 pb-4" hidden={!isOpen}>
                    {renderExtra(row.extra)}
                  </div>
                )}
              </li>
            );
          })}
        </ul>
      )}

      {(domainChecks.length > 0 || assessment) && (
        <div className="space-y-2">
          <p className="text-xs text-muted">Domain plausibility (AI assessment)</p>
          {domainChecks.length > 0 && (
            <ul className="space-y-2 text-sm m-0 p-0 list-none">
              {domainChecks.map((d, i) => (
                <li key={`${d.aspect}-${i}`} className="flex gap-2 items-start">
                  <StatusIcon status={DOMAIN_STATUS[d.status] ?? 'na'} />
                  <span className="text-secondary">
                    <span className="font-medium text-primary">{asText(d.aspect)}</span>
                    <span className="text-muted"> — {asText(d.explanation)}</span>
                  </span>
                </li>
              ))}
            </ul>
          )}
          {assessment && <p className="text-sm text-primary leading-relaxed">{assessment}</p>}
        </div>
      )}
    </section>
  );
};

export default EvidenceSection;
