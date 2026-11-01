/**
 * ResultsView Component
 * Displays analysis results with SSE-based real-time progress updates
 */

import React, { useEffect, useMemo, useState, useRef, useCallback } from 'react';
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
  extractDiscovery,
  extractEquationResults,
  extractWarnings,
  isResultIncomplete,
} from '@components/Results';
import type { ResultsStatus } from '@components/Results';
import { runsService } from '@services/api';
import { useProgressInterpolation } from '@hooks/useProgressInterpolation';
import { useRunProgress } from '@hooks/useRunProgress';
import type { AgentEvent, EquationResults } from '@/types';

type ResultsTab = 'results' | 'process';
const PROCESS_HASH = '#process';

/** The tab named in the address (#process), so the process view can be linked and revisited */
const tabFromHash = (): ResultsTab =>
  window.location.hash === PROCESS_HASH ? 'process' : 'results';

// ============================================================================
// Types
// ============================================================================

interface ResultsViewProps {
  runId: string | null;
  fromHistory?: boolean;
}

// ============================================================================
// Component
// ============================================================================

const ResultsView: React.FC<ResultsViewProps> = ({ runId, fromHistory = false }) => {
  // State
  const [result, setResult] = useState<EquationResults | string | null>(null);
  const [exportingPdf, setExportingPdf] = useState(false);
  const [shareToken, setShareToken] = useState<string | null>(null);
  const [showShareDialog, setShowShareDialog] = useState(false);
  const loadPlot = useCallback(
    (name: string) => runsService.downloadFile(runId ?? '', name).then((r) => r.data),
    [runId]
  );
  const [showDeleteDialog, setShowDeleteDialog] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [cancelling, setCancelling] = useState(false);
  const [duration, setDuration] = useState<string | null>(null);
  const [targetVariable, setTargetVariable] = useState<string | null>(null);
  const [tab, setTab] = useState<ResultsTab>(tabFromHash);

  useEffect(() => {
    const onHashChange = () => setTab(tabFromHash());
    window.addEventListener('hashchange', onHashChange);
    return () => window.removeEventListener('hashchange', onHashChange);
  }, []);

  const selectTab = (next: ResultsTab) => {
    setTab(next);
    const url = `${window.location.pathname}${window.location.search}${next === 'process' ? PROCESS_HASH : ''}`;
    window.history.replaceState(null, '', url);
  };

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
    activity,
    searchProgress,
    phases: progressPhases,
  } = useRunProgress({
    runId,
    onComplete: handleComplete,
    onError: handleError,
    enabled: !!runId,
  });

  // Derived state (declared early so hooks below can reference it)
  const isCompleted = status === 'completed';

  // Fetch final results from API when run completes.
  // Always fetch from API on completion — SSE intermediate results
  // (from compute phase) lack LLM explanations and summary.
  useEffect(() => {
    if (isCompleted && runId) {
      runsService
        .getById(runId)
        .then((response) => {
          if (response.data.results) {
            setResult(response.data.results as EquationResults | string);
          }
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
  }, [isCompleted, runId]);

  // Custom hook for smooth progress interpolation and step description
  const {
    displayProgress,
    currentStepDescription,
    stepElapsedS,
    stepExpectedS,
    isInQueuePhase,
    phaseIndex,
  } = useProgressInterpolation({
    phases: progressPhases,
    backendProgress,
    status,
  });

  // Handle PDF export (lazy loads the PDF library)
  const handleExportPdf = async () => {
    if (!result || !runId) return;

    setExportingPdf(true);
    try {
      // Parse result the same way ResultContent does, extracting from
      // the backend's combined format (enriched data lives inside `explanations`)
      const raw = typeof result === 'object' ? result : JSON.parse(result);
      const parsedData: EquationResults = extractEquationResults(raw) ?? (raw as EquationResults);

      // Dynamic import to reduce initial bundle size
      const { generateResultsPdf } = await import('@utils/pdfExport');
      const discovery = extractDiscovery(raw);
      await generateResultsPdf(
        parsedData,
        runId,
        targetVariable,
        discovery,
        parsedData.warnings ?? extractWarnings(raw)
      );
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
  /** No run state yet: still starting or connecting */
  const preRun = isStarting || isConnecting;

  // True while we've reached 'completed' but are still fetching final results from API
  const isLoadingResults = isCompleted && !result;

  // The agent's stored activity: the live workspace can be replayed once the run is done
  const storedActivity = useMemo<AgentEvent[]>(() => {
    if (!result || typeof result !== 'object') return [];
    return extractDiscovery(result)?.activity ?? [];
  }, [result]);
  const hasProcess = isCompleted && storedActivity.length > 0;
  const showingProcess = hasProcess && tab === 'process';
  // Each tab stays mounted once shown, so switching back keeps its state (no re-typesetting)
  const [processSeen, setProcessSeen] = useState(false);
  useEffect(() => {
    if (showingProcess) setProcessSeen(true);
  }, [showingProcess]);

  // Check if result is in the new EquationResults format (not legacy markdown)
  // Accounts for both direct EquationResults and backend combined format (explanations wrapper)
  const isNewFormat =
    result !== null &&
    typeof result === 'object' &&
    (('equations' in result && 'summary' in result) || 'explanations' in result);

  // Results are incomplete only when the LLM explanation failed on a legacy run; with a
  // discovery report the equations and report are complete, so share/export stay enabled
  const resultIncomplete = isResultIncomplete(result);

  // Only show error for terminal failure states, not transient SSE messages
  const isTerminalError =
    !!error && (status === 'failed' || status === 'timeout' || status === 'cancelled');

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

  // Header action buttons - hidden when the results are incomplete
  const renderHeaderActions = () => {
    if (!isCompleted || !isNewFormat || resultIncomplete) return null;

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

      {/* Run Settings Panel - from the history, and on every finished report */}
      {(fromHistory || isCompleted) && runId && <RunSettingsPanel runId={runId} />}

      <div>
        {/* Error / Cancelled State - only for terminal failures, not transient messages */}
        {isTerminalError && (
          <div className="mb-6">
            <Message
              severity={status === 'cancelled' ? 'warn' : 'error'}
              text={status === 'cancelled' ? error : `Analysis Failed: ${error}`}
              className="w-full"
            />
          </div>
        )}

        {/* Loading State - Progress bar for starting, processing, or initial connection */}
        {(isStarting || isProcessing || isConnecting) && !isTerminalError && (
          <>
            <AnalysisProgressView
              displayProgress={preRun ? 0 : displayProgress}
              stepDescription={
                isStarting
                  ? 'Starting analysis...'
                  : isConnecting
                    ? 'Connecting to analysis server...'
                    : currentStepDescription
              }
              isInQueuePhase={preRun || isInQueuePhase}
              stepTiming={preRun ? undefined : { elapsedS: stepElapsedS, expectedS: stepExpectedS }}
              isJobSubmitted={status === 'running' && !preRun && !isInQueuePhase}
              activity={activity}
              searchProgress={searchProgress}
              phases={progressPhases}
              phaseIndex={preRun ? -1 : phaseIndex}
            />
            {status === 'running' && !preRun && (
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

        {/* Results and the process that led to them (the live workspace, replayed) */}
        {hasProcess && (
          <div
            role="tablist"
            aria-label="Results view"
            className="mt-2 mb-2 inline-flex gap-1 bg-surface-alt rounded-lg p-1"
          >
            {(
              [
                ['results', 'Results', 'pi pi-chart-bar'],
                ['process', 'Analysis process', 'pi pi-history'],
              ] as const
            ).map(([id, label, icon]) => (
              <button
                key={id}
                type="button"
                role="tab"
                aria-selected={tab === id}
                onClick={() => selectTab(id)}
                className={`min-h-9 px-4 rounded-md text-sm border-0 cursor-pointer flex items-center gap-2 ${
                  tab === id
                    ? 'bg-surface text-primary font-semibold shadow-sm'
                    : 'bg-transparent text-secondary font-medium'
                }`}
              >
                <i className={`${icon} text-xs`} aria-hidden="true" />
                {label}
              </button>
            ))}
          </div>
        )}

        {(showingProcess || processSeen) && (
          <div hidden={!showingProcess}>
            <AnalysisProgressView
              displayProgress={100}
              stepDescription=""
              activity={storedActivity}
              phases={progressPhases}
              finished
              durationLabel={duration}
            />
          </div>
        )}

        {/* Results - only show after run completes to avoid flashing legacy format during processing */}
        {result && isCompleted && (
          <div hidden={showingProcess}>
            <ResultContent
              result={result}
              resultsRef={resultsRef}
              targetVariable={targetVariable}
              loadPlot={runId ? loadPlot : undefined}
            />
          </div>
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

      {/* Danger Zone - Delete Button */}
      {isCompleted && (
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
