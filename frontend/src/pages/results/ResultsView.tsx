/**
 * ResultsView Component
 * Displays analysis results with polling, progress visualization, and PDF export
 */

import React, { useEffect, useState, useRef } from 'react';
import { Button } from 'primereact/button';
import { Message } from 'primereact/message';
import { Toast } from 'primereact/toast';
import { Dialog } from 'primereact/dialog';
import {
  RunSettingsPanel,
  ShareDialog,
  AnalysisProgressView,
  ResultsHeader,
  ResultContent,
  LoadingSpinner,
} from '@components/Results';
import type { ResultsStatus } from '@components/Results';
import { runsService, configService } from '@services/api';
import { useProgressInterpolation } from '@hooks/useProgressInterpolation';
import type { ProgressPhase, EquationResults } from '@/types';

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
  const [result, setResult] = useState<EquationResults | string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [progressPhases, setProgressPhases] = useState<ProgressPhase[]>([]);
  const [exportingPdf, setExportingPdf] = useState(false);
  const [shareToken, setShareToken] = useState<string | null>(null);
  const [showShareDialog, setShowShareDialog] = useState(false);
  const [initialFetchDone, setInitialFetchDone] = useState(false);
  const [showDeleteDialog, setShowDeleteDialog] = useState(false);
  const [deleting, setDeleting] = useState(false);

  // Refs
  const toast = useRef<Toast>(null);
  const resultsRef = useRef<HTMLDivElement>(null);

  // Custom hook for smooth progress interpolation and step description
  const { displayProgress, currentStepDescription } = useProgressInterpolation({
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
          // Handle both new direct format and old wrapper format
          const results = response.data.results;
          if (results) {
            if ('equations' in results) {
              // New format: results is the EquationResults object directly
              setResult(results as EquationResults);
            } else if ('pysr_explanations' in results) {
              // Old format: results has pysr_explanations wrapper (string)
              setResult(results.pysr_explanations);
            }
          }
          setBackendProgress(100);
          setShareToken(response.data.public_share_token || null);
          clearInterval(intervalId);
        } else if (response.data.status === 'failed' || response.data.status === 'timeout') {
          setError(response.data.error || (response.data.status === 'timeout' ? 'Analysis timed out' : 'Unknown error'));
          clearInterval(intervalId);
        }
      } catch (e) {
        console.error(e);
      } finally {
        setInitialFetchDone(true);
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
      // Handle both object (new format) and string (old format)
      const parsedData: EquationResults = typeof result === 'object'
        ? result
        : JSON.parse(result);
      // Dynamic import to reduce initial bundle size
      const { generateResultsPdf } = await import('@utils/pdfExport');
      await generateResultsPdf(parsedData, runId);
      toast.current?.show({ severity: 'success', summary: 'Export Complete', detail: 'PDF saved successfully' });
    } catch (e) {
      console.error('PDF export failed:', e);
      toast.current?.show({ severity: 'error', summary: 'Export Failed', detail: 'Failed to generate PDF' });
    } finally {
      setExportingPdf(false);
    }
  };

  // Handle run deletion
  const handleDeleteRun = async () => {
    setDeleting(true);
    try {
      await runsService.delete(runId);
      toast.current?.show({ severity: 'success', summary: 'Run Deleted', detail: 'The run has been permanently deleted' });
      // Navigate to history after short delay
      setTimeout(() => {
        window.location.href = '/history';
      }, 1500);
    } catch (e) {
      console.error('Failed to delete run:', e);
      toast.current?.show({ severity: 'error', summary: 'Delete Failed', detail: 'Failed to delete the run' });
      setDeleting(false);
      setShowDeleteDialog(false);
    }
  };

  // Derived state
  const isCompleted = status === 'completed';

  // Actively processing (pending/running) - shows progress bar
  const isProcessing = initialFetchDone && (!runId || status === 'pending' || status === 'running');

  // Loading a completed run from history (fetching data but run is already complete)
  const isFetchingCompletedRun = !initialFetchDone && fromHistory;

  // Check if result is in the new EquationResults format (not legacy markdown)
  const isNewFormat = result !== null && typeof result === 'object' && 'equations' in result;

  // Determine header status
  const getHeaderStatus = (): ResultsStatus => {
    if (isFetchingCompletedRun) return 'loading';
    if (isProcessing && !error) return 'processing';
    if (isCompleted) return 'completed';
    return 'failed';
  };

  // Header action buttons
  const renderHeaderActions = () => {
    if (!isCompleted || !isNewFormat) return null;

    return (
      <>
        <Button
          icon={shareToken ? "pi pi-link" : "pi pi-share-alt"}
          onClick={() => setShowShareDialog(true)}
          size="large"
          className={`${shareToken ? '!bg-green-600 hover:!bg-green-700 !border-green-600' : '!bg-blue-600 hover:!bg-blue-700 !border-blue-600'} !text-white font-semibold px-3 py-2 shadow-sm`}
          tooltip={shareToken ? "Shared - Manage Link" : "Share Results"}
          tooltipOptions={{ position: 'bottom' }}
        />
        <Button
          icon={exportingPdf ? "pi pi-spin pi-spinner" : "pi pi-file-pdf"}
          onClick={handleExportPdf}
          disabled={exportingPdf}
          size="large"
          className="!bg-red-600 hover:!bg-red-700 !border-red-600 !text-white font-semibold px-3 py-2 shadow-sm"
          tooltip="Export to PDF"
          tooltipOptions={{ position: 'bottom' }}
        />
      </>
    );
  };

  return (
    <div className="p-4">
      <Toast ref={toast} />

      {/* Header */}
      <ResultsHeader
        title="Analysis Results"
        subtitle={runId ? (
          <>Run ID: <span className="font-mono">{runId.slice(0, 8)}...</span></>
        ) : (
          <>Starting analysis...</>
        )}
        status={getHeaderStatus()}
        actions={renderHeaderActions()}
      />

      {/* Run Settings Panel - shown only when navigating from history */}
      {fromHistory && <RunSettingsPanel runId={runId} />}

      <div>
        {/* Error State */}
        {error && (
          <div className="mb-6">
            <Message severity="error" text={`Analysis Failed: ${error}`} className="w-full" />
          </div>
        )}

        {/* Loading State - Progress bar for active processing */}
        {isProcessing && !error && (
          <AnalysisProgressView
            displayProgress={displayProgress}
            stepDescription={currentStepDescription}
          />
        )}

        {/* Loading State - Simple spinner for fetching completed runs */}
        {isFetchingCompletedRun && !error && (
          <LoadingSpinner
            message="Loading results..."
            className="py-20"
          />
        )}

        {/* Results */}
        {result && (
          <ResultContent result={result} resultsRef={resultsRef} />
        )}
      </div>

      {/* Share Dialog */}
      <ShareDialog
        visible={showShareDialog}
        onHide={() => setShowShareDialog(false)}
        runId={runId}
        currentShareToken={shareToken}
        onShareStatusChange={setShareToken}
      />

      {/* Delete Confirmation Dialog */}
      <Dialog
        visible={showDeleteDialog}
        onHide={() => !deleting && setShowDeleteDialog(false)}
        header={
          <div className="flex items-center gap-2 text-red-600">
            <i className="pi pi-exclamation-triangle text-xl"></i>
            <span>Delete Run Permanently</span>
          </div>
        }
        className="w-full max-w-md"
        closable={!deleting}
        footer={
          <div className="flex justify-end gap-3 pt-2">
            <Button
              label="Cancel"
              icon="pi pi-times"
              onClick={() => setShowDeleteDialog(false)}
              disabled={deleting}
              className="!bg-slate-100 hover:!bg-slate-200 !border-slate-200 !text-slate-700 font-medium px-4 py-2"
            />
            <Button
              label={deleting ? 'Deleting...' : 'Delete Permanently'}
              icon={deleting ? 'pi pi-spin pi-spinner' : 'pi pi-trash'}
              onClick={handleDeleteRun}
              disabled={deleting}
              className="!bg-red-600 hover:!bg-red-700 !border-red-600 !text-white font-semibold px-4 py-2 shadow-sm"
            />
          </div>
        }
      >
        <div className="py-4">
          <div className="bg-red-50 border border-red-200 rounded-lg p-4 mb-4">
            <p className="text-red-700 font-medium mb-2">
              <i className="pi pi-info-circle mr-2"></i>
              This action cannot be undone.
            </p>
            <p className="text-red-600 text-sm">
              All data related to this analysis run will be permanently removed, including results, configurations, and any shared links.
            </p>
          </div>
          <p className="text-slate-600">
            Are you sure you want to delete this run?
          </p>
        </div>
      </Dialog>

      {/* Danger Zone - Delete Button */}
      {isCompleted && (
        <div className="mt-12 pt-6 border-t border-slate-200">
          <div className="flex items-start justify-between">
            <div>
              <h4 className="text-sm font-semibold text-red-600 mb-1">Danger Zone</h4>
              <p className="text-sm text-slate-500">Permanently delete this run and all associated data</p>
            </div>
            <Button
              label="Delete Run"
              icon="pi pi-trash"
              onClick={() => setShowDeleteDialog(true)}
              className="!bg-red-600 hover:!bg-red-700 !border-red-600 !text-white font-semibold px-4 py-2 shadow-sm"
            />
          </div>
        </div>
      )}
    </div>
  );
};

export default ResultsView;
