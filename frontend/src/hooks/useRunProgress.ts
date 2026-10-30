/**
 * useRunProgress Hook
 *
 * Provides real-time progress updates for a run using SSE connection.
 */

import { useCallback, useEffect, useRef, useState } from 'react';
import { ProgressSSE } from '@services/sseService';
import { appendActivity } from '@components/Results/Discovery/agentState';
import type { AgentEvent, EquationResults, ProgressPhase, RunStatus } from '@/types';
import type {
  ConnectionState,
  ServerMessage,
  UseRunProgressOptions,
  UseRunProgressReturn,
} from '@/types/sse';

const TERMINAL_STATUSES: RunStatus[] = ['completed', 'failed', 'timeout', 'cancelled'];
/** Past this, the oldest narration makes room (fits and search events are always kept) */
const MAX_ACTIVITY = 300;

export function useRunProgress(options: UseRunProgressOptions): UseRunProgressReturn {
  const { runId, onComplete, onError, enabled = true } = options;

  // State
  const [progress, setProgress] = useState(0);
  const [status, setStatus] = useState<RunStatus>('pending');
  const [error, setError] = useState<string | null>(null);
  const [results, setResults] = useState<EquationResults | null>(null);
  const [connectionState, setConnectionState] = useState<ConnectionState>('disconnected');
  const [isReady, setIsReady] = useState(false);
  const [activity, setActivity] = useState<AgentEvent[]>([]);
  const [searchProgress, setSearchProgress] = useState<Record<string, number>>({});
  const [phases, setPhases] = useState<ProgressPhase[]>([]);

  // Refs
  const sseRef = useRef<ProgressSSE | null>(null);
  const isTerminalRef = useRef(false);
  const onCompleteRef = useRef(onComplete);
  const onErrorRef = useRef(onError);

  // Keep callback refs up to date
  onCompleteRef.current = onComplete;
  onErrorRef.current = onError;

  // Handle terminal state
  const handleTerminalState = useCallback(
    (newStatus: RunStatus, newError: string | null, newResults: EquationResults | null) => {
      if (isTerminalRef.current) return;
      isTerminalRef.current = true;

      if (newStatus === 'completed' && newResults) {
        onCompleteRef.current?.(newResults);
      } else if (newStatus === 'failed' || newStatus === 'timeout' || newStatus === 'cancelled') {
        const errorMessage =
          newError ||
          (newStatus === 'timeout'
            ? 'Analysis timed out'
            : newStatus === 'cancelled'
              ? 'Analysis was cancelled'
              : 'Unknown error');
        onErrorRef.current?.(errorMessage);
      }
    },
    []
  );

  // Handle SSE message
  const handleMessage = useCallback(
    (message: ServerMessage) => {
      if (message.type === 'agent_event') {
        setActivity((prev) => appendActivity(prev, [message.event], MAX_ACTIVITY));
        return;
      }
      if (message.type === 'search_progress') {
        setSearchProgress((prev) => ({ ...prev, [message.search_id]: message.progress }));
        return;
      }
      if (message.type === 'initial_state') {
        if (message.recent_events?.length) {
          setActivity(
            appendActivity(
              [],
              message.recent_events.map((m) => m.event),
              MAX_ACTIVITY
            )
          );
        }
        if (message.search_progress) setSearchProgress(message.search_progress);
        if (message.progress_phases?.length) setPhases(message.progress_phases);
      }
      if (message.type === 'initial_state' || message.type === 'progress_update') {
        setProgress(message.progress);
        setStatus(message.status);
        setError(message.error);
        setIsReady(true);

        if (message.results) {
          setResults(message.results);
        }

        if (TERMINAL_STATUSES.includes(message.status)) {
          handleTerminalState(message.status, message.error, message.results);
        }
      }
    },
    [handleTerminalState]
  );

  // Handle SSE state change
  const handleStateChange = useCallback((state: ConnectionState) => {
    setConnectionState(state);
  }, []);

  // Main effect: manage SSE connection
  useEffect(() => {
    if (!enabled || !runId) return;

    isTerminalRef.current = false;
    // A new run starts with an empty live view, not the previous run's agent activity
    setActivity([]);
    setSearchProgress({});

    const sse = new ProgressSSE(runId, {
      onMessage: handleMessage,
      onStateChange: handleStateChange,
      onError: (err) => {
        console.error('SSE error:', err);
      },
    });

    sseRef.current = sse;
    sse.connect();

    return () => {
      sse.close();
      sseRef.current = null;
    };
  }, [enabled, runId, handleMessage, handleStateChange]);

  // Cleanup on terminal state
  useEffect(() => {
    if (TERMINAL_STATUSES.includes(status)) {
      sseRef.current?.close();
    }
  }, [status]);

  return {
    progress,
    status,
    error,
    results,
    connectionState,
    isReady,
    activity,
    searchProgress,
    phases,
  };
}

export type { UseRunProgressOptions, UseRunProgressReturn };
