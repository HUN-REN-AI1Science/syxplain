/**
 * ResultsView Component
 * Displays analysis results with polling, progress visualization, and PDF export
 */

import React, { useEffect, useState, useRef } from 'react';
import { Button } from 'primereact/button';
import { Message } from 'primereact/message';
import { ProgressBar } from 'primereact/progressbar';
import { Toast } from 'primereact/toast';
import RunSettingsPanel from './RunSettingsPanel';
import EquationResultsView from './EquationResultsView';
import { runsService, configService } from './services/api';
import { useProgressInterpolation } from './hooks/useProgressInterpolation';
// PDF export is dynamically imported when needed to reduce initial bundle size
import type { ProgressPhase, EquationResults } from './types';

// ============================================================================
// Types
// ============================================================================

interface ResultsViewProps {
  runId: string;
  fromHistory?: boolean;
}

// ============================================================================
// Component
// ============================================================================

const ResultsView: React.FC<ResultsViewProps> = ({ runId, fromHistory = false }) => {
  // State
  const [status, setStatus] = useState<string>('pending');
  const [backendProgress, setBackendProgress] = useState<number>(0);
  const [result, setResult] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [progressPhases, setProgressPhases] = useState<ProgressPhase[]>([]);
  const [exportingPdf, setExportingPdf] = useState(false);

  // Refs
  const toast = useRef<Toast>(null);
  const resultsRef = useRef<HTMLDivElement>(null);

  // Custom hook for smooth progress interpolation
  const { displayProgress } = useProgressInterpolation({
    phases: progressPhases,
    backendProgress,
    status,
  });

  // Fetch progress config on mount
  useEffect(() => {
    const fetchConfig = async () => {
      try {
        const response = await configService.getProgressConfig();
        setProgressPhases(response.data.phases || []);
      } catch (e) {
        console.error('Failed to fetch progress config:', e);
      }
    };
    fetchConfig();
  }, []);

  // Poll backend for actual progress
  useEffect(() => {
    if (!runId) return;

    let intervalId: NodeJS.Timeout;

    const poll = async () => {
      try {
        const response = await runsService.getById(runId);
        setStatus(response.data.status);
        setBackendProgress(response.data.progress || 0);

        if (response.data.status === 'completed') {
          setResult(response.data.results?.pysr_explanations || null);
          setBackendProgress(100);
          clearInterval(intervalId);
        } else if (response.data.status === 'failed' || response.data.status === 'timeout') {
          setError(response.data.error || (response.data.status === 'timeout' ? 'Analysis timed out' : 'Unknown error'));
          clearInterval(intervalId);
        }
      } catch (e) {
        console.error(e);
      }
    };

    poll();
    intervalId = setInterval(poll, 2000);

    return () => clearInterval(intervalId);
  }, [runId]);

  // Handle PDF export (lazy loads the PDF library)
  const handleExportPdf = async () => {
    if (!result) return;

    setExportingPdf(true);
    try {
      const parsedData: EquationResults = JSON.parse(result);
      // Dynamic import to reduce initial bundle size
      const { generateResultsPdf } = await import('./utils/pdfExport');
      await generateResultsPdf(parsedData, runId);
      toast.current?.show({ severity: 'success', summary: 'Export Complete', detail: 'PDF saved successfully' });
    } catch (e) {
      console.error('PDF export failed:', e);
      toast.current?.show({ severity: 'error', summary: 'Export Failed', detail: 'Failed to generate PDF' });
    } finally {
      setExportingPdf(false);
    }
  };

  // Derived state
  const isLoading = !runId || status === 'pending' || status === 'running';
  const isCompleted = status === 'completed';

  return (
    <div className="p-4">
      <Toast ref={toast} />

      {/* Header */}
      <div className="flex flex-col md:flex-row justify-between items-start md:items-center mb-6 pb-4 border-b border-slate-100 gap-4">
        <div>
          <h2 className="text-xl font-bold text-slate-800">Analysis Results</h2>
          <p className="text-sm text-slate-500">
            {runId ? (
              <>Run ID: <span className="font-mono">{runId.slice(0, 8)}...</span></>
            ) : (
              <>Starting analysis...</>
            )}
          </p>
        </div>

        <div className="flex items-center space-x-3 w-full md:w-auto">
          {isLoading && !error ? (
            <Message severity="info" text="Processing Data..." className="w-full md:w-auto" />
          ) : isCompleted ? (
            <>
              {result && (
                <Button
                  icon={exportingPdf ? "pi pi-spin pi-spinner" : "pi pi-file-pdf"}
                  onClick={handleExportPdf}
                  disabled={exportingPdf}
                  size="large"
                  className="!bg-red-600 hover:!bg-red-700 !border-red-600 !text-white font-semibold px-3 py-2 shadow-sm"
                  tooltip="Export to PDF"
                  tooltipOptions={{ position: 'bottom' }}
                />
              )}
              <Message severity="success" text="Completed" className="w-full md:w-auto" />
              </>
          ) : (
                <Message severity="error" text="Failed" className="w-full md:w-auto" />
          )}
        </div>
      </div>

      {/* Run Settings Panel - shown only when navigating from history */}
      {fromHistory && <RunSettingsPanel runId={runId} />}

      <div>
        {/* Error State */}
        {error && (
          <div className="mb-6">
            <Message severity="error" text={`Analysis Failed: ${error}`} className="w-full" />
          </div>
        )}

        {/* Loading State */}
        {isLoading && !error && (
          <LoadingState displayProgress={displayProgress} />
        )}

        {/* Results */}
        {result && (
          <div className="space-y-8 animate-fade-in">
            <ResultsContent result={result} resultsRef={resultsRef} />
          </div>
        )}
      </div>
    </div>
  );
};

// ============================================================================
// Sub-components
// ============================================================================

interface LoadingStateProps {
  displayProgress: number;
}

const LoadingState: React.FC<LoadingStateProps> = ({ displayProgress }) => (
  <div className="text-center py-20">
    <div className="max-w-md mx-auto mb-6">
      <ProgressBar value={displayProgress} showValue={false} style={{ height: '8px' }} className="mb-2" />
      <p className="text-lg font-semibold text-blue-600">{Math.floor(displayProgress)}% complete</p>
    </div>
    <h3 className="text-xl font-semibold text-slate-800 mt-4 mb-2">AI is analyzing your data</h3>
    <p className="text-slate-500 max-w-md mx-auto mb-4">
      This process involves symbolic regression and LLM reasoning. It might take a few minutes depending on the dataset size.
    </p>
    <p className="text-slate-600 text-sm max-w-md mx-auto">
      You can safely leave this page. Your results will be available in the <span className="font-semibold">History</span> menu once completed.
    </p>
  </div>
);

interface ResultsContentProps {
  result: string;
  resultsRef: React.RefObject<HTMLDivElement>;
}

const ResultsContent: React.FC<ResultsContentProps> = ({ result, resultsRef }) => {
  try {
    const parsedData: EquationResults = JSON.parse(result);
    return (
      <div ref={resultsRef}>
        <EquationResultsView data={parsedData} />
      </div>
    );
  } catch {
    // Fallback for legacy markdown format
    return <LegacyResultsFallback result={result} />;
  }
};

interface LegacyResultsFallbackProps {
  result: string;
}

const LegacyResultsFallback: React.FC<LegacyResultsFallbackProps> = ({ result }) => (
  <div className="bg-slate-50 border border-slate-200 rounded-xl p-8 text-center">
    <div className="w-16 h-16 bg-amber-100 rounded-full flex items-center justify-center mx-auto mb-4">
      <i className="pi pi-history text-amber-600 text-2xl"></i>
    </div>
    <h3 className="text-xl font-bold text-slate-800 mb-2">Legacy Run Format</h3>
    <p className="text-slate-600 max-w-md mx-auto mb-6">
      This analysis was generated using an older format that is no longer displayed in the application.
      You can download the original results as a Markdown file.
    </p>
    <Button
      label="Download Results (Markdown)"
      icon="pi pi-download"
      size="large"
      className="!bg-blue-600 hover:!bg-blue-700 !border-blue-600 !text-white font-semibold px-6 py-3 shadow-lg"
      onClick={() => {
        const blob = new Blob([result], { type: 'text/markdown' });
        const url = window.URL.createObjectURL(blob);
        const link = document.createElement('a');
        link.href = url;
        link.setAttribute('download', 'pysr_explanations.md');
        document.body.appendChild(link);
        link.click();
        link.remove();
        window.URL.revokeObjectURL(url);
      }}
    />
  </div>
);

export default ResultsView;
