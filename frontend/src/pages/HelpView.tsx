/**
 * HelpView Page
 * In-app documentation with sidebar navigation and anchored sections
 */

import React, { useEffect, useRef, useState } from 'react';
import { Button } from 'primereact/button';
import { Tag } from 'primereact/tag';
import { useAuth } from '@contexts/AuthContext';

// ============================================================================
// Sidebar navigation structure
// ============================================================================

interface NavItem {
  id: string;
  label: string;
  children?: { id: string; label: string }[];
}

const NAV: NavItem[] = [
  {
    id: 'getting-started',
    label: 'Getting Started',
    children: [
      { id: 'what-is-syxplain', label: 'What is Syxplain?' },
      { id: 'uploading-data', label: 'Uploading your data' },
    ],
  },
  {
    id: 'analysis',
    label: 'Analysis',
    children: [
      { id: 'quick-analysis', label: 'Quick Analysis' },
      { id: 'deep-analysis', label: 'Deep Analysis' },
      { id: 'understanding-results', label: 'Understanding results' },
    ],
  },
  {
    id: 'exporting-sharing',
    label: 'Exporting & Sharing',
    children: [
      { id: 'export-pdf', label: 'Export to PDF' },
      { id: 'export-data', label: 'Export data (CSV / Excel)' },
      { id: 'export-json', label: 'Export configuration (JSON)' },
      { id: 'sharing', label: 'Sharing results' },
    ],
  },
];

const ADMIN_NAV: NavItem = {
  id: 'admin',
  label: 'Admin',
  children: [
    { id: 'admin-backend', label: 'Backend configuration' },
    { id: 'admin-users', label: 'User management' },
  ],
};

// ============================================================================
// Helpers
// ============================================================================

const scrollTo = (id: string) => {
  const el = document.getElementById(id);
  if (el) el.scrollIntoView({ behavior: 'smooth', block: 'start' });
};

// ============================================================================
// Layout primitives
// ============================================================================

const SectionHeading: React.FC<{ id: string; title: string }> = ({ id, title }) => (
  <h2
    id={id}
    className="text-2xl font-bold text-primary font-heading mt-12 mb-4 pb-2 border-b border-[var(--color-border)] scroll-mt-24"
  >
    {title}
  </h2>
);

const SubHeading: React.FC<{ id: string; title: string }> = ({ id, title }) => (
  <h3 id={id} className="text-lg font-semibold text-primary mt-8 mb-3 scroll-mt-24">
    {title}
  </h3>
);

const Prose: React.FC<{ children: React.ReactNode }> = ({ children }) => (
  <p className="text-secondary leading-relaxed mb-4">{children}</p>
);

const InfoBox: React.FC<{ children: React.ReactNode; variant?: 'info' | 'warning' | 'tip' }> = ({
  children,
  variant = 'info',
}) => {
  const styles = {
    info: 'bg-brand-50 border-brand-200 text-brand-800',
    warning: 'bg-amber-50 border-amber-200 text-amber-800',
    tip: 'bg-green-50 border-green-200 text-green-800',
  };
  const icons = {
    info: 'pi-info-circle',
    warning: 'pi-exclamation-triangle',
    tip: 'pi-check-circle',
  };

  return (
    <div className={`rounded-lg border p-4 mb-4 ${styles[variant]}`}>
      <div className="flex items-start gap-2">
        <i className={`pi ${icons[variant]} mt-0.5 flex-shrink-0`}></i>
        <div className="text-sm leading-relaxed">{children}</div>
      </div>
    </div>
  );
};

// ============================================================================
// Content sections
// ============================================================================

const GettingStarted: React.FC = () => (
  <>
    <SectionHeading id="getting-started" title="Getting Started" />

    <SubHeading id="what-is-syxplain" title="What is Syxplain?" />
    <Prose>
      Syxplain is a scientific method for discovering{' '}
      <strong>interpretable mathematical equations</strong> directly from data. Rather than
      producing black-box predictions, Syxplain finds compact formulas you can read, validate, and
      reason about — making it particularly valuable for scientific and engineering applications
      where understanding <em>why</em> a model works is as important as how accurate it is.
    </Prose>
    <Prose>
      At its core, Syxplain combines two powerful ideas. First, it uses a{' '}
      <strong>large language model (LLM)</strong> to intelligently configure the symbolic regression
      search — incorporating context about your problem to reduce the search space and steer the
      algorithm toward scientifically plausible equation structures. Second, it applies{' '}
      <strong>symbolic regression</strong> to find the equations that best fit your data within that
      guided search space. The discovered formulas are then analyzed, explained, and ranked to
      surface the most meaningful result.
    </Prose>
    <Prose>
      The <strong>Syxplain platform</strong> is a fully hosted implementation of this algorithm,
      extended with additional capabilities. Symbolic regression is computationally intensive —
      running it well requires significant resources and careful configuration. The platform takes
      care of all of that, so you can focus on your data and results rather than infrastructure.
    </Prose>
    <InfoBox variant="info">
      A peer-reviewed publication describing the Syxplain methodology in full detail is forthcoming.
      This documentation will be updated with a reference once it is available.
    </InfoBox>

    <SubHeading id="uploading-data" title="Uploading your data" />
    <Prose>
      Syxplain accepts tabular data in <strong>CSV format</strong>. Upload your file on the first
      step of the workflow.
    </Prose>
    <ul className="list-disc list-inside text-secondary space-y-2 mb-4 ml-2">
      <li>The first row must contain column headers.</li>
      <li>All columns must be numeric. Non-numeric columns are automatically excluded.</li>
      <li>
        Columns with a high proportion of missing values (<code>NaN</code>) are flagged so you can
        review them before proceeding.
      </li>
      <li>There is no strict row limit, but larger datasets increase processing time.</li>
    </ul>
    <InfoBox variant="tip">
      Use descriptive column names — Syxplain uses them as variable names in equations and as
      context for AI-generated explanations.
    </InfoBox>
  </>
);

const Analysis: React.FC = () => (
  <>
    <SectionHeading id="analysis" title="Analysis" />

    <SubHeading id="quick-analysis" title="Quick Analysis" />
    <Prose>
      Quick Analysis runs the <strong>core Syxplain algorithm</strong> on your data. The LLM
      generates explanations using your problem description and data context directly — no external
      research is performed. It is the right starting point for most use cases: faster,
      more cost-effective, and ideal for initial exploration or iterative experimentation.
    </Prose>
    <InfoBox variant="tip">
      Start with Quick Analysis to explore your data. Upgrade to Deep Analysis when you need results
      grounded in scientific literature.
    </InfoBox>

    <SubHeading id="deep-analysis" title="Deep Analysis" />
    <Prose>
      Deep Analysis extends the <strong>core Syxplain algorithm</strong> with internet search.
      Before symbolic regression runs, it queries scientific literature and known domain formulas to
      build a richer understanding of your problem. This context informs both the symbolic regression
      configuration and the final explanations, resulting in more grounded results. This operating
      mode can create more detail rich results if established theory exists, but comes at a higher
      computational cost and longer processing time.
    </Prose>
    <InfoBox variant="warning">
      Deep Analysis is more resource-intensive. It is currently available in experimental mode and
      may be subject to usage limits in the future.
    </InfoBox>

    <SubHeading id="understanding-results" title="Understanding results" />
    <Prose>
      Results are presented as a ranked list of equations on a <strong>Pareto frontier</strong> —
      the optimal trade-off between prediction accuracy (loss) and equation simplicity (complexity).
      No single equation dominates all others on both dimensions; the frontier shows you the full
      range of meaningful options.
    </Prose>

    <div className="space-y-4 mb-6">
      <div className="rounded-lg border border-[var(--color-border)] bg-surface p-4">
        <div className="flex items-center gap-2 mb-2">
          <Tag value="Loss (MSE)" className="bg-amber-100 text-amber-800 text-xs" />
        </div>
        <p className="text-sm text-secondary">
          Mean Squared Error between the equation's predictions and your measured values.{' '}
          <strong>Lower is better.</strong> A loss of 0 means a perfect fit.
        </p>
      </div>

      <div className="rounded-lg border border-[var(--color-border)] bg-surface p-4">
        <div className="flex items-center gap-2 mb-2">
          <Tag value="Complexity" className="bg-surface-alt text-primary text-xs" />
        </div>
        <p className="text-sm text-secondary">
          The number of mathematical operations in the equation.{' '}
          <strong>Lower means simpler.</strong> Simpler equations are easier to interpret and less
          likely to overfit.
        </p>
      </div>

      <div className="rounded-lg border border-[var(--color-border)] bg-surface p-4">
        <div className="flex items-center gap-2 mb-2">
          <Tag value="Recommended" severity="success" className="text-xs" />
        </div>
        <p className="text-sm text-secondary">
          Syxplain selects one equation as the best trade-off between accuracy and simplicity, and
          provides a rationale explaining the choice.
        </p>
      </div>

      <div className="rounded-lg border border-[var(--color-border)] bg-surface p-4">
        <p className="text-sm font-semibold text-primary mb-1">Term Breakdown</p>
        <p className="text-sm text-secondary">
          Each equation includes AI-generated explanations for its mathematical terms, describing
          what each part represents in the context of your problem and domain.
        </p>
      </div>

      <div className="rounded-lg border border-[var(--color-border)] bg-surface p-4">
        <p className="text-sm font-semibold text-primary mb-1">
          Scatter Plot (Predicted vs. Measured)
        </p>
        <p className="text-sm text-secondary">
          A scatter plot comparing predicted values against your actual measured values. Points
          close to the 1:1 diagonal indicate a good fit. Click <strong>Show Details</strong> on any
          equation card to reveal it.
        </p>
      </div>
    </div>
  </>
);

const ExportingSharing: React.FC = () => (
  <>
    <SectionHeading id="exporting-sharing" title="Exporting & Sharing" />

    <SubHeading id="export-pdf" title="Export to PDF" />
    <Prose>
      Click the <strong>PDF button</strong> (red, top-right of the results page) to download a
      formatted report. It includes all discovered equations, their metrics, term breakdowns, and
      scientific citations where available.
    </Prose>
    <InfoBox variant="info">
      PDF export is only available once the analysis has completed successfully.
    </InfoBox>

    <SubHeading id="export-data" title="Export data (CSV / Excel)" />
    <Prose>
      Each equation card contains an <strong>Export Data</strong> button inside its details section.
      This exports the measured vs. predicted scatter data for that equation:
    </Prose>
    <ul className="list-disc list-inside text-secondary space-y-2 mb-4 ml-2">
      <li>
        Click <strong>Export Data</strong> to download a CSV file.
      </li>
      <li>
        Click the dropdown arrow next to the button and select <strong>Excel (.xlsx)</strong> to
        download in spreadsheet format.
      </li>
    </ul>

    <SubHeading id="export-json" title="Export configuration (JSON)" />
    <Prose>
      After defining your problem, an <strong>Export JSON</strong> button appears in the analysis
      controls. It downloads your current problem configuration as a JSON file that you can
      re-import in a future session, saving you from re-entering the same settings.
    </Prose>

    <SubHeading id="sharing" title="Sharing results" />
    <Prose>
      Click the <strong>Share button</strong> (blue, top-right of the results page) to generate a
      public link to your results. Anyone with the link can view them without logging in.
    </Prose>
    <ul className="list-disc list-inside text-secondary space-y-2 mb-4 ml-2">
      <li>The link stays active until you revoke it.</li>
      <li>
        Click the Share button again — it turns green when active — to manage or revoke the link.
      </li>
      <li>Revoking a link makes the results private again immediately.</li>
    </ul>
    <InfoBox variant="warning">
      Anyone with the link can view your results. Do not share links to sensitive or confidential
      analyses.
    </InfoBox>
  </>
);

const AdminSection: React.FC = () => (
  <>
    <SectionHeading id="admin" title="Admin" />
    <InfoBox variant="info">This section is only visible to administrators.</InfoBox>

    <SubHeading id="admin-backend" title="Backend configuration" />
    <Prose>
      The Admin panel lets administrators configure backend connection settings. Use the{' '}
      <strong>Test Backend</strong> button to verify that the API is reachable and responding
      correctly.
    </Prose>

    <SubHeading id="admin-users" title="User management" />
    <Prose>
      User accounts and roles are managed through <strong>Keycloak</strong>. Admin-level access
      grants access to this Admin panel and elevated API features. Contact your system administrator
      to modify user roles.
    </Prose>
  </>
);

// ============================================================================
// Sidebar
// ============================================================================

const Sidebar: React.FC<{ showAdmin: boolean; activeId: string }> = ({ showAdmin, activeId }) => {
  const allNav = showAdmin ? [...NAV, ADMIN_NAV] : NAV;

  return (
    <nav className="w-56 flex-shrink-0 sticky top-24 self-start hidden lg:block">
      <ul className="space-y-1">
        {allNav.map((section) => (
          <li key={section.id}>
            <button
              onClick={() => scrollTo(section.id)}
              className={`w-full text-left text-sm font-semibold px-3 py-1.5 rounded-lg transition-colors ${
                activeId === section.id
                  ? 'text-brand-500 bg-brand-50'
                  : 'text-primary hover:text-brand-500 hover:bg-brand-50'
              }`}
            >
              {section.label}
            </button>
            {section.children && (
              <ul className="ml-3 mt-0.5 space-y-0.5">
                {section.children.map((child) => (
                  <li key={child.id}>
                    <button
                      onClick={() => scrollTo(child.id)}
                      className={`w-full text-left text-sm px-3 py-1 rounded-lg transition-colors ${
                        activeId === child.id
                          ? 'text-brand-500 bg-brand-50'
                          : 'text-secondary hover:text-brand-500 hover:bg-brand-50'
                      }`}
                    >
                      {child.label}
                    </button>
                  </li>
                ))}
              </ul>
            )}
          </li>
        ))}
      </ul>
    </nav>
  );
};

// ============================================================================
// Main component
// ============================================================================

interface HelpViewProps {
  onBack: () => void;
  anchor?: string;
}

const HelpView: React.FC<HelpViewProps> = ({ onBack, anchor }) => {
  const { isAdmin } = useAuth();
  const contentRef = useRef<HTMLDivElement>(null);
  const [activeId, setActiveId] = useState('getting-started');

  // Scroll to anchor on mount if provided
  useEffect(() => {
    if (anchor) {
      setTimeout(() => scrollTo(anchor), 100);
    }
  }, [anchor]);

  useEffect(() => {
    const allIds = [
      'getting-started',
      'what-is-syxplain',
      'uploading-data',
      'analysis',
      'quick-analysis',
      'deep-analysis',
      'understanding-results',
      'exporting-sharing',
      'export-pdf',
      'export-data',
      'export-json',
      'sharing',
      ...(isAdmin ? ['admin', 'admin-backend', 'admin-users'] : []),
    ];

    const observer = new IntersectionObserver(
      (entries) => {
        const visible = entries.filter((e) => e.isIntersecting);
        if (visible.length > 0) setActiveId(visible[0].target.id);
      },
      { rootMargin: '-20% 0px -70% 0px' }
    );

    allIds.forEach((id) => {
      const el = document.getElementById(id);
      if (el) observer.observe(el);
    });

    return () => observer.disconnect();
  }, [isAdmin]);

  return (
    <div className="p-4">
      {/* Header */}
      <div className="flex items-center gap-3 mb-8">
        <Button
          icon="pi pi-arrow-left"
          onClick={onBack}
          className="p-button-text p-button-sm !text-secondary hover:!text-primary"
        />
        <div>
          <h1 className="text-2xl font-bold text-primary font-heading">Documentation</h1>
          <p className="text-sm text-secondary mt-0.5">Learn how to use the Syxplain platform</p>
        </div>
      </div>

      {/* Layout: sidebar + content */}
      <div className="flex gap-10">
        <Sidebar showAdmin={isAdmin} activeId={activeId} />

        <div ref={contentRef} className="flex-1 min-w-0 max-w-3xl">
          <GettingStarted />
          <Analysis />
          <ExportingSharing />
          {isAdmin && <AdminSection />}
          {/* Bottom padding so the last section can reach the top of the viewport */}
          <div className="h-64" />
        </div>
      </div>
    </div>
  );
};

export default HelpView;
