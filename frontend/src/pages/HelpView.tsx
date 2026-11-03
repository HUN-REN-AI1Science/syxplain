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
      { id: 'running-analysis', label: 'Running an analysis' },
      { id: 'how-it-works', label: 'How equations are found' },
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
  {
    id: 'keys-api',
    label: 'Keys & API',
    children: [
      { id: 'llm-keys', label: 'Using your own LLM key' },
      { id: 'programmatic-api', label: 'Programmatic API' },
    ],
  },
];

const ADMIN_NAV: NavItem = {
  id: 'admin',
  label: 'Admin',
  children: [
    { id: 'admin-backend', label: 'System configuration' },
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

const getNavIds = (items: NavItem[]): string[] =>
  items.flatMap((item) => [item.id, ...(item.children?.map((c) => c.id) ?? [])]);

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

/** A bordered card describing one part of the results page */
const ResultCard: React.FC<{ title: React.ReactNode; children: React.ReactNode }> = ({
  title,
  children,
}) => (
  <div className="rounded-lg border border-[var(--color-border)] bg-surface p-4">
    <div className="text-sm font-semibold text-primary mb-1">{title}</div>
    <div className="text-sm text-secondary leading-relaxed">{children}</div>
  </div>
);

const Code: React.FC<{ children: React.ReactNode }> = ({ children }) => (
  <code className="font-mono text-sm bg-surface-alt px-1 rounded">{children}</code>
);

// ============================================================================
// Content sections
// ============================================================================

const GettingStarted: React.FC = () => (
  <>
    <SectionHeading id="getting-started" title="Getting Started" />

    <SubHeading id="what-is-syxplain" title="What is Syxplain?" />
    <Prose>
      Syxplain discovers <strong>interpretable mathematical equations</strong> from tabular data.
      Instead of a black-box prediction model, it returns compact formulas you can read, check, and
      reason about, together with the evidence for and against each one.
    </Prose>
    <Prose>
      The search combines <strong>symbolic regression</strong> (an evolutionary search over
      formulas) with an <strong>AI agent</strong> that works like a scientist: it studies the data,
      proposes its own formulas, reads why each one falls short, and steers further symbolic
      regression searches. Model selection and scoring are done by code, not by the AI, and known
      laws from the literature are compared with the results only after the search is finished.
    </Prose>
    <Prose>
      The <strong>Syxplain platform</strong> runs this method for you. Symbolic regression is
      computationally intensive; the platform runs the searches on a computing cluster, so you can
      focus on your data and results.
    </Prose>
    <InfoBox variant="info">
      A publication describing the method is in preparation. A reference will be added here once it
      is available.
    </InfoBox>

    <SubHeading id="uploading-data" title="Uploading your data" />
    <Prose>
      Syxplain accepts tabular data as <strong>CSV (.csv)</strong> or{' '}
      <strong>Excel (.xlsx, .xls)</strong> files. Upload your file on the first step of the
      workflow.
    </Prose>
    <ul className="list-disc list-inside text-secondary space-y-2 mb-4 ml-2">
      <li>The first row must contain column headers.</li>
      <li>
        Only numeric columns are used. Non-numeric columns are excluded and listed under{' '}
        <strong>Columns Excluded</strong> so you can see what was left out.
      </li>
      <li>
        The target column must not contain missing values. Rows with missing values in the selected
        features are left out; the results report how many.
      </li>
      <li>
        If the rows form a series in time, Syxplain detects it and tests equations on predicting
        later values from earlier ones (see below).
      </li>
      <li>
        The maximum file size is set by your administrator. Larger datasets take longer to process.
      </li>
    </ul>
    <InfoBox variant="tip">
      Use descriptive column names and describe each feature on the problem page. Column names
      become the variable names in the equations, and the descriptions give the AI the context it
      needs to explain the results.
    </InfoBox>
  </>
);

const Analysis: React.FC = () => (
  <>
    <SectionHeading id="analysis" title="Analysis" />

    <SubHeading id="running-analysis" title="Running an analysis" />
    <Prose>
      After uploading, the <strong>Define the Problem</strong> page asks for a short project
      description, the <strong>Target</strong> column, and the <strong>Features</strong> to use,
      each with a description (<strong>Suggest descriptions</strong> drafts them for you). Click{' '}
      <strong>Run Analysis</strong> to start.
    </Prose>
    <Prose>
      While the analysis runs, the progress page follows the AI agent live: what it is doing, the
      best equation so far, a live leaderboard, and the state of its symbolic regression searches.
      You can leave the page and come back later, or use <strong>Stop Analysis</strong> to cancel
      the run.
    </Prose>

    <SubHeading id="how-it-works" title="How equations are found" />
    <ol className="list-decimal list-outside text-secondary space-y-3 mb-4 ml-6">
      <li>
        <strong>Baseline search.</strong> A symbolic regression search over all features starts
        first, so it runs while the agent works.
      </li>
      <li>
        <strong>Profiling.</strong> The agent studies the data: correlations, mutual information,
        random-forest importance, and a <strong>noise ceiling</strong> (the out-of-fold
        random-forest R², an estimate of the best accuracy the data allows). SHAP values show the
        shape of each feature&apos;s effect and which features interact, with plots.
      </li>
      <li>
        <strong>Exploration, blind to known laws.</strong> The agent designs its own formulas. Each
        fit comes back with diagnosed reasons it falls short (for example a wrong curve shape, a
        missing variable, or parameters the data cannot determine). Guided by these, it launches
        targeted symbolic regression searches and records its findings in a lab notebook.
      </li>
      <li>
        <strong>Time-ordered data.</strong> When the rows form a series in time, earlier conditions
        (lagged values and aggregates over earlier periods) are proposed, measured, and kept as
        inputs only when they help. For measurements over time, the agent also looks for a rate law
        (how fast the target changes), using its own formulas and SINDy.
      </li>
      <li>
        <strong>Relation to known laws.</strong> Only after exploration, classic named laws and
        published laws found by a literature search are fitted to the same data. Each discovered
        equation is classified against them as <em>equivalent</em> (the same law in another form),{' '}
        <em>similar</em>, <em>partial</em>, or <em>different</em> (a new relationship).
      </li>
      <li>
        <strong>Selection and scoring, by code.</strong> Models are ranked by 5-fold
        cross-validation on the training rows, and the simplest model within one standard error of
        the best becomes the recommended equation. A 20% holdout, set aside at the start, is scored
        once at the end. Datasets under 40 rows use cross-validation only; for time series the
        holdout is the final part of each series. The recommended equation is then checked against
        the SHAP effects.
      </li>
      <li>
        <strong>Coherence.</strong> Code checks whether the independent lines of evidence agree on
        the recommended equation (noise ceiling, holdout, SHAP, known laws, parameters, and the
        agent&apos;s conclusion).
      </li>
      <li>
        <strong>Explanation.</strong> An LLM writes the summary, the explanation of each equation
        and its terms, and a judgement of domain plausibility. It cannot override the computed
        checks.
      </li>
    </ol>
    <InfoBox variant="info">
      Literature and known laws never steer the search. The agent does not see them while it
      explores; they are used only at the end to show how the discoveries relate to what is already
      known.
    </InfoBox>
    <InfoBox variant="tip">
      If you use your own LLM key, an OpenAI key is optional; it enables the literature search.
      Without it the analysis still runs and the discoveries are compared with the classic named
      laws only.
    </InfoBox>

    <SubHeading id="understanding-results" title="Understanding results" />
    <Prose>Scores on the results page:</Prose>
    <div className="space-y-4 mb-6">
      <div className="rounded-lg border border-[var(--color-border)] bg-surface p-4">
        <div className="flex items-center gap-2 mb-2">
          <Tag value="Held-out R²" className="bg-[rgba(34,197,94,0.12)] text-green-700 text-xs" />
          <Tag value="CV R²" className="bg-[rgba(34,197,94,0.12)] text-green-700 text-xs" />
        </div>
        <p className="text-sm text-secondary">
          The share of the target&apos;s variation an equation explains.{' '}
          <strong>Higher is better</strong>; 1 is a perfect fit. Held-out R² is measured on rows no
          model was trained on. CV R² is the cross-validated score on the training rows, used to
          compare models; small datasets show CV R² only.
        </p>
      </div>

      <div className="rounded-lg border border-[var(--color-border)] bg-surface p-4">
        <div className="flex items-center gap-2 mb-2">
          <Tag value="Complexity" className="bg-surface-alt text-primary text-xs" />
        </div>
        <p className="text-sm text-secondary">
          The number of operations in the equation. <strong>Lower means simpler.</strong> Simpler
          equations are easier to interpret and less likely to overfit.
        </p>
      </div>

      <div className="rounded-lg border border-[var(--color-border)] bg-surface p-4">
        <div className="flex items-center gap-2 mb-2">
          <Tag value="Noise ceiling (R²)" className="bg-red-50 text-red-700 text-xs" />
        </div>
        <p className="text-sm text-secondary">
          An estimate of the best accuracy a flexible model reaches on this data. An equation near
          it leaves only noise unexplained; a value near or below zero means the variables do not
          predict the target.
        </p>
      </div>
    </div>

    <Prose>The results page shows, from top to bottom:</Prose>
    <div className="space-y-4 mb-6">
      <ResultCard title="Analysis Summary">
        The <strong>Key Drivers</strong>, <strong>Secondary Drivers</strong>, and{' '}
        <strong>Findings</strong> in plain language. Warnings about the run, and a note when
        Syxplain detected a time series, appear above it.
      </ResultCard>

      <ResultCard
        title={
          <span className="flex items-center gap-2">
            Recommended: Equation N
            <Tag value="recommended" severity="success" className="text-xs" />
          </span>
        }
      >
        The headline equation chosen by code, with its variables, R², complexity, and the reason it
        was chosen. If the explanation AI would have preferred a different equation, a note says so
        and why.
      </ResultCard>

      <ResultCard title="Time series: earlier conditions / Rate law (dynamics)">
        Shown only for time-ordered data: which earlier conditions were kept as inputs and why, and
        the recommended rate law integrated over the measured trajectories.
      </ResultCard>

      <ResultCard title="Other equations">
        The remaining equations from symbolic regression and the fitted laws, with R² and
        complexity. <strong>Equally good</strong> marks equations statistically tied with the
        recommended one. Open a row for its explanation, <strong>Term Breakdown</strong>,{' '}
        <strong>Predicted vs. Measured</strong> plot, and <strong>Scientific Sources</strong>.
      </ResultCard>

      <ResultCard title="Does the evidence agree?">
        <p className="mb-2">
          Computed checks of the recommended equation, each marked as agreeing, a caution, or a
          conflict, with an overall verdict:
        </p>
        <div className="flex flex-wrap gap-2 mb-2">
          <Tag value="Coherent" severity="success" className="text-xs" />
          <Tag value="Partly coherent" severity="warning" className="text-xs" />
          <Tag value="Conflicting evidence" severity="danger" className="text-xs" />
        </div>
        <p>
          The rows cover the noise ceiling, generalization to the holdout, the SHAP effects (open
          the row for <strong>Feature effects (SHAP)</strong> with plots), published and named laws
          (open the rows for <strong>Relation to known laws</strong> and{' '}
          <strong>Published laws tested</strong>), the parameters, and the agent&apos;s statements.
          The AI&apos;s <strong>Domain plausibility</strong> assessment follows.
        </p>
      </ResultCard>

      <ResultCard title="How the equations were found">
        Collapsed by default. The agent&apos;s summary; the noise ceiling, number of models tested,
        symbolic searches, and held-out rows; the <strong>Model leaderboard</strong>, where each
        model is rated <em>Best possible</em>, <em>Nearly best</em>, <em>Misses a pattern</em>, or{' '}
        <em>Nothing to predict</em> against the noise ceiling; and the agent&apos;s notebook
        (rejected forms with reasons, insights, data issues), open questions, and the symbolic
        regression searches.
      </ResultCard>
    </div>
  </>
);

const ExportingSharing: React.FC = () => (
  <>
    <SectionHeading id="exporting-sharing" title="Exporting & Sharing" />

    <SubHeading id="export-pdf" title="Export to PDF" />
    <Prose>
      Click the <strong>PDF button</strong> (red, top-right of the results page) to download a
      report. It includes the summary, the equations with their scores and term breakdowns, the
      evidence (SHAP effects, relation to known laws, published laws tested, domain plausibility),
      and the discovery report (leaderboard, agent notes, symbolic searches).
    </Prose>
    <InfoBox variant="info">
      PDF export is only available once the analysis has completed successfully.
    </InfoBox>

    <SubHeading id="export-data" title="Export data (CSV / Excel)" />
    <Prose>
      Each equation under <strong>Other equations</strong> has an <strong>Export Data</strong>{' '}
      button next to its Predicted vs. Measured plot. It exports the measured and predicted values
      for that equation:
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
      On the problem page, the <strong>Export JSON</strong> button downloads your project
      description, target, and feature descriptions as a JSON file. Upload it on the same page in a
      later session to fill in the same settings.
    </Prose>

    <SubHeading id="sharing" title="Sharing results" />
    <Prose>
      Click the <strong>Share button</strong> (blue, top-right of the results page) to generate a
      public link to your results. Anyone with the link can view them without logging in.
    </Prose>
    <ul className="list-disc list-inside text-secondary space-y-2 mb-4 ml-2">
      <li>The link stays active until you revoke it.</li>
      <li>
        Click the Share button again (it turns green when active) to manage or revoke the link. Your
        shared runs are also listed on your Profile page.
      </li>
      <li>Revoking a link makes the results private again immediately.</li>
    </ul>
    <InfoBox variant="warning">
      Anyone with the link can view your results. Do not share links to sensitive or confidential
      analyses.
    </InfoBox>
  </>
);

const KeysApi: React.FC = () => (
  <>
    <SectionHeading id="keys-api" title="Keys & API" />

    <SubHeading id="llm-keys" title="Using your own LLM key" />
    <Prose>
      Accounts with <strong>Server Keys Access</strong> run analyses on the server&apos;s built-in
      LLM keys. Without it, the problem page asks for your own key, which is used only for that
      analysis and is not stored. Choose a provider:
    </Prose>
    <ul className="list-disc list-inside text-secondary space-y-2 mb-4 ml-2">
      <li>
        <strong>Google Gemini</strong>: a Gemini API key and a model from the list.
      </li>
      <li>
        <strong>OpenAI-compatible</strong>: any endpoint that speaks the OpenAI API (OpenAI,
        OpenRouter, vLLM, LiteLLM, and others). Enter the key, the base URL (empty means OpenAI),
        and the model name. The endpoint must be publicly reachable.
      </li>
      <li>
        <strong>OpenAI (optional)</strong>: an OpenAI key enables the literature search. On
        OpenAI&apos;s own endpoint, the main key is used for it.
      </li>
    </ul>
    <Prose>
      Your Profile page shows whether your account has Server Keys Access. To request it, contact
      your administrator.
    </Prose>

    <SubHeading id="programmatic-api" title="Programmatic API" />
    <Prose>
      You can run analyses from scripts and notebooks. Generate a key on your{' '}
      <strong>Profile</strong> page under <strong>API Key</strong> (it is shown only once; you can
      regenerate or revoke it there), and send it in the <Code>X-API-Key</Code> header.
    </Prose>
    <ul className="list-disc list-inside text-secondary space-y-2 mb-4 ml-2">
      <li>
        <Code>POST /api/v1/analyze</Code> uploads a CSV or Excel file (form field <Code>file</Code>)
        and starts a run. The <Code>params</Code> form field is a JSON string with{' '}
        <Code>project_description</Code>, <Code>target_variable</Code>, and <Code>features</Code>{' '}
        (column name to description). Without Server Keys Access, also pass your LLM key (
        <Code>provider</Code>, <Code>api_key</Code>, <Code>model</Code>, <Code>api_base</Code>).
      </li>
      <li>
        <Code>GET /api/v1/runs/{'{run_id}'}</Code> returns the run&apos;s status, and the results
        once it has completed. Poll it until the run finishes.
      </li>
      <li>
        <Code>GET /api/v1/runs</Code> lists your runs;{' '}
        <Code>POST /api/v1/runs/{'{run_id}'}/cancel</Code> cancels one.
      </li>
    </ul>
    <InfoBox variant="tip">
      The interactive API documentation at <a href="/docs">/docs</a> lists every endpoint and
      parameter, with examples, and lets you try requests with your key.
    </InfoBox>
  </>
);

const AdminSection: React.FC = () => (
  <>
    <SectionHeading id="admin" title="Admin" />
    <InfoBox variant="info">This section is only visible to administrators.</InfoBox>

    <SubHeading id="admin-backend" title="System configuration" />
    <Prose>
      The <strong>Config</strong> tab of the Admin panel is a read-only view of the current
      settings: compute backend, analysis timeout and maximum file size; whether the cluster
      connection, literature search, and user API keys are available; rate limits; and masked
      secrets. Changing a setting requires updating the environment variables and restarting the
      application. The other tabs cover runs, errors, system status, the audit log, and usage
      analytics.
    </Prose>

    <SubHeading id="admin-users" title="User management" />
    <Prose>
      User accounts and roles are managed through <strong>Keycloak</strong>. The administrator role
      grants access to this Admin panel; the server-keys role lets a user run analyses on the
      server&apos;s LLM keys instead of their own.
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
    const allIds = [...getNavIds(NAV), ...(isAdmin ? getNavIds([ADMIN_NAV]) : [])];

    const observer = new IntersectionObserver(
      (entries) => {
        const visible = entries.filter((e) => e.isIntersecting);
        if (visible.length > 0) {
          const closestToTop = visible.reduce((closest, entry) =>
            Math.abs(entry.boundingClientRect.top) < Math.abs(closest.boundingClientRect.top)
              ? entry
              : closest
          );
          setActiveId(closestToTop.target.id);
        }
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
          <KeysApi />
          {isAdmin && <AdminSection />}
          {/* Bottom padding so the last section can reach the top of the viewport */}
          <div className="h-64" />
        </div>
      </div>
    </div>
  );
};

export default HelpView;
