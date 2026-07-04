/**
 * ResultsView Component
 * Displays analysis results with SSE-based real-time progress updates
 */

import React, { useEffect, useState, useRef, useCallback } from 'react';
import { Button } from 'primereact/button';
import { Toast } from 'primereact/toast';
import { Dialog } from 'primereact/dialog';
import {
  RunSettingsPanel,
  ShareDialog,
  AnalysisProgressView,
  ResultsHeader,
  ResultContent,
  FailedRunReport,
  LoadingSpinner,
  hasExplanationError,
} from '@components/Results';
import type { ResultsStatus } from '@components/Results';
import { runsService } from '@services/api';
import { useProgressInterpolation } from '@hooks/useProgressInterpolation';
import { useRunProgress } from '@hooks/useRunProgress';
import type { ProgressPhase, EquationResults, RunErrorDetails } from '@/types';

// ============================================================================
// Types
// ============================================================================

interface ResultsViewProps {
  runId: string | null;
  fromHistory?: boolean;
  initialProgressPhases?: ProgressPhase[];
}

// ============================================================================
// Component
// ============================================================================

const ResultsView: React.FC<ResultsViewProps> = ({
  runId,
  fromHistory = false,
  initialProgressPhases = [],
}) => {
  // State
  const [result, setResult] = useState<EquationResults | string | null>(null);
  const [progressPhases, setProgressPhases] = useState<ProgressPhase[]>(initialProgressPhases);
  const [exportingPdf, setExportingPdf] = useState(false);
  const [shareToken, setShareToken] = useState<string | null>(null);
  const [showShareDialog, setShowShareDialog] = useState(false);
  const [showDeleteDialog, setShowDeleteDialog] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [cancelling, setCancelling] = useState(false);
  const [duration, setDuration] = useState<string | null>(null);
  const [targetVariable, setTargetVariable] = useState<string | null>(null);
  const [errorDetails, setErrorDetails] = useState<RunErrorDetails | null>(null);

  // Refs
  const toast = useRef<Toast>(null);
  const resultsRef = useRef<HTMLDivElement>(null);

  // Callbacks for useRunProgress
  // Note: we don't setResult here — the isCompleted useEffect always
  // fetches the final results (with LLM explanations) from the API.
  const handleComplete = useCallback((_results: EquationResults) => {
    // Results will be fetched from API by the isCompleted effect
  }, []);

  const handleError = useCallback(() => {
    // Error is already tracked by the hook
  }, []);

  // Real-time progress via SSE
  const {
    progress: backendProgress,
    status,
    error,
    isReady: initialFetchDone,
  } = useRunProgress({
    runId,
    onComplete: handleComplete,
    onError: handleError,
    enabled: !!runId,
  });

  // Derived state (declared early so hooks below can reference it)
  const isCompleted = status === 'completed';
  const isTerminal = ['completed', 'failed', 'timeout', 'cancelled'].includes(status);

  // Fetch run details from API for any terminal state.
  // Completed: SSE intermediate results (from compute phase) lack LLM
  // explanations and summary, so always fetch the final results.
  // Failed/timeout/cancelled: fetch structured error details for the report.
  useEffect(() => {
    if (isTerminal && runId) {
      runsService
        .getById(runId)
        .then((response) => {
          // Only show results for completed runs — failed runs may hold
          // partial compute output that the results view can't render
          if (response.data.status === 'completed' && response.data.results) {
            setResult(response.data.results as EquationResults | string);
          }
          setErrorDetails(response.data.error_details || null);
          setShareToken(response.data.public_share_token || null);
          setTargetVariable(response.data.target_variable || null);
          // Compute duration from timing data
          const { start_time, finish_time } = response.data;
          if (start_time && finish_time) {
            const seconds = Math.floor(
              (new Date(finish_time).getTime() - new Date(start_time).getTime()) / 1000
            );
            const hours = Math.floor(seconds / 3600);
            const minutes = Math.floor((seconds % 3600) / 60);
            const secs = seconds % 60;
            if (hours > 0) setDuration(`${hours}h ${minutes}m`);
            else if (minutes > 0) setDuration(`${minutes}m ${secs}s`);
            else setDuration(`${secs}s`);
          }
        })
        .catch(console.error);
    }
  }, [isTerminal, runId]);

  // Custom hook for smooth progress interpolation and step description
  const { displayProgress, currentStepDescription, isInQueuePhase } = useProgressInterpolation({
    phases: progressPhases,
    backendProgress,
    status,
  });

  // Update phases if provided after mount (e.g. from run response)
  useEffect(() => {
    if (initialProgressPhases.length > 0) {
      setProgressPhases(initialProgressPhases);
    }
  }, [initialProgressPhases]);

  // Handle PDF export (lazy loads the PDF library)
  const handleExportPdf = async () => {
    if (!result || !runId) return;

    setExportingPdf(true);
    try {
      // Parse result the same way ResultContent does, extracting from
      // the backend's combined format (enriched data lives inside `explanations`)
      let parsedData: EquationResults;
      const raw = typeof result === 'object' ? result : JSON.parse(result);

      if (
        raw &&
        typeof raw === 'object' &&
        'explanations' in raw &&
        raw.explanations &&
        typeof raw.explanations === 'object' &&
        !Array.isArray(raw.explanations) &&
        'equations' in raw.explanations
      ) {
        // Backend combined format: extract enriched data from explanations wrapper
        parsedData = raw.explanations as EquationResults;
      } else {
        parsedData = raw as EquationResults;
      }

      // Dynamic import to reduce initial bundle size
      const { generateResultsPdf } = await import('@utils/pdfExport');
      await generateResultsPdf(parsedData, runId, targetVariable);
      toast.current?.show({
        severity: 'success',
        summary: 'Export Complete',
        detail: 'PDF saved successfully',
      });
    } catch (e) {
      console.error('PDF export failed:', e);
      toast.current?.show({
        severity: 'error',
        summary: 'Export Failed',
        detail: 'Failed to generate PDF',
      });
    } finally {
      setExportingPdf(false);
    }
  };

  // Handle run cancellation
  const handleCancelRun = async () => {
    if (!runId || cancelling) return;
    setCancelling(true);
    try {
      await runsService.cancel(runId);
      // Don't reset cancelling — SSE will deliver terminal status
      // which hides the entire progress section
    } catch (e) {
      console.error('Failed to cancel:', e);
      setCancelling(false); // Only reset on error so user can retry
      toast.current?.show({
        severity: 'error',
        summary: 'Cancel Failed',
        detail: 'Failed to cancel the analysis',
      });
    }
  };

  // Handle run deletion
  const handleDeleteRun = async () => {
    if (!runId) return;
    setDeleting(true);
    try {
      await runsService.delete(runId);
      toast.current?.show({
        severity: 'success',
        summary: 'Run Deleted',
        detail: 'The run has been permanently deleted',
      });
      // Navigate to history after short delay
      setTimeout(() => {
        window.location.href = '/history';
      }, 1500);
    } catch (e) {
      console.error('Failed to delete run:', e);
      toast.current?.show({
        severity: 'error',
        summary: 'Delete Failed',
        detail: 'Failed to delete the run',
      });
      setDeleting(false);
      setShowDeleteDialog(false);
    }
  };

  // Waiting for run to be created (runId not yet available)
  const isStarting = !runId;

  // Actively processing (pending/running) - shows progress bar
  const isProcessing = initialFetchDone && (status === 'pending' || status === 'running');

  // Loading a completed run from history (fetching data but run is already complete)
  const isFetchingCompletedRun = !initialFetchDone && fromHistory && !!runId;

  // Initial connection state - show progress bar immediately while connecting
  const isConnecting = !initialFetchDone && !fromHistory && !!runId;

  // True while we've reached 'completed' but are still fetching final results from API
  const isLoadingResults = isCompleted && !result;

  // Check if result is in the new EquationResults format (not legacy markdown)
  // Accounts for both direct EquationResults and backend combined format (explanations wrapper)
  const isNewFormat =
    result !== null &&
    typeof result === 'object' &&
    (('equations' in result && 'summary' in result) || 'explanations' in result);

  // Check if the LLM explanation step failed (results are incomplete)
  const explanationFailed = hasExplanationError(result);

  // Terminal failure states (shown even when no error string was recorded,
  // so failed runs opened from history always get a report)
  const isTerminalError = status === 'failed' || status === 'timeout' || status === 'cancelled';

  // Determine header status
  const getHeaderStatus = (): ResultsStatus => {
    if (isStarting) return 'processing';
    if (isFetchingCompletedRun) return 'loading';
    if (isLoadingResults) return 'loading';
    if ((isProcessing || isConnecting) && !isTerminalError) return 'processing';
    if (isCompleted) return 'completed';
    if (status === 'cancelled') return 'cancelled';
    if (status === 'failed' || status === 'timeout') return 'failed';
    return 'processing';
  };

  // Header action buttons - hidden when explanations failed
  const renderHeaderActions = () => {
    if (!isCompleted || !isNewFormat || explanationFailed) return null;

    return (
      <>
        <Button
          icon={shareToken ? 'pi pi-link' : 'pi pi-share-alt'}
          onClick={() => setShowShareDialog(true)}
          size="large"
          className={`${shareToken ? '!bg-green-600 hover:!bg-green-700 !border-green-600' : '!bg-blue-600 hover:!bg-blue-700 !border-blue-600'} !text-white font-semibold px-3 py-2 shadow-sm`}
          tooltip={shareToken ? 'Shared - Manage Link' : 'Share Results'}
          tooltipOptions={{ position: 'bottom' }}
        />
        <Button
          icon={exportingPdf ? 'pi pi-spin pi-spinner' : 'pi pi-file-pdf'}
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
        subtitle={
          runId ? (
            <>
              Run ID: <span className="font-mono">{runId.slice(0, 8)}...</span>
              {duration && (
                <span className="ml-3 text-muted">
                  <i className="pi pi-clock mr-1"></i>
                  {duration}
                </span>
              )}
            </>
          ) : (
            <>Starting analysis...</>
          )
        }
        status={getHeaderStatus()}
        actions={renderHeaderActions()}
      />

      {/* Run Settings Panel - shown only when navigating from history */}
      {fromHistory && runId && <RunSettingsPanel runId={runId} />}

      <div>
        {/* Error / Cancelled State - detailed failure report for terminal failures */}
        {isTerminalError && (
          <FailedRunReport status={status} error={error} errorDetails={errorDetails} />
        )}

        {/* Loading State - Progress bar for starting, processing, or initial connection */}
        {(isStarting || isProcessing || isConnecting) && !isTerminalError && (
          <>
            <AnalysisProgressView
              displayProgress={isStarting || isConnecting ? 0 : displayProgress}
              stepDescription={
                isStarting
                  ? 'Starting analysis...'
                  : isConnecting
                    ? 'Connecting to analysis server...'
                    : currentStepDescription
              }
              isInQueuePhase={isStarting || isConnecting || isInQueuePhase}
              isJobSubmitted={
                status === 'running' && !isStarting && !isConnecting && !isInQueuePhase
              }
            />
            {status === 'running' && !isStarting && !isConnecting && (
              <div className="flex justify-center mt-4">
                <Button
                  label={cancelling ? 'Cancelling...' : 'Stop Analysis'}
                  icon={cancelling ? 'pi pi-spin pi-spinner' : 'pi pi-stop'}
                  className="!bg-red-600 hover:!bg-red-700 !border-red-600 !text-white font-semibold px-4 py-2 shadow-sm"
                  onClick={handleCancelRun}
                  disabled={cancelling}
                />
              </div>
            )}
          </>
        )}

        {/* Loading State - Simple spinner for fetching completed runs or waiting for API after completion */}
        {(isFetchingCompletedRun || isLoadingResults) && !isTerminalError && (
          <LoadingSpinner message="Loading results..." className="py-20" />
        )}

        {/* Results - only show after run completes to avoid flashing legacy format during processing */}
        {result && isCompleted && (
          <ResultContent result={result} resultsRef={resultsRef} targetVariable={targetVariable} />
        )}
      </div>

      {/* Share Dialog */}
      {runId && (
        <ShareDialog
          visible={showShareDialog}
          onHide={() => setShowShareDialog(false)}
          runId={runId}
          currentShareToken={shareToken}
          onShareStatusChange={setShareToken}
        />
      )}

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
        className="w-full max-w-md mx-4"
        closable={!deleting}
        footer={
          <div className="flex flex-col-reverse sm:flex-row justify-end gap-2 sm:gap-3 pt-2">
            <Button
              label="Cancel"
              icon="pi pi-times"
              onClick={() => setShowDeleteDialog(false)}
              disabled={deleting}
              className="!bg-surface-alt hover:!bg-surface-alt !border-[var(--color-border)] !text-primary font-medium px-4 py-2"
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
              All data related to this analysis run will be permanently removed, including results,
              configurations, and any shared links.
            </p>
          </div>
          <p className="text-secondary">Are you sure you want to delete this run?</p>
        </div>
      </Dialog>

      {/* Danger Zone - Delete Button (any finished run, including failed ones) */}
      {isTerminal && initialFetchDone && (
        <div className="mt-12 pt-6 border-t border-[var(--color-border)]">
          <div className="flex flex-col sm:flex-row sm:items-start sm:justify-between gap-4">
            <div>
              <h4 className="text-sm font-semibold text-red-600 mb-1">Danger Zone</h4>
              <p className="text-sm text-secondary">
                Permanently delete this run and all associated data
              </p>
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
