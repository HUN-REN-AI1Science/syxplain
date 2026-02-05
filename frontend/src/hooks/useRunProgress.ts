/**
 * useRunProgress Hook
 *
 * Provides real-time progress updates for a run using WebSocket connection.
 */

import { useCallback, useEffect, useRef, useState } from 'react';
import { ProgressWebSocket } from '@services/websocketService';
import type { EquationResults, RunStatus } from '@/types';
import type {
  ConnectionState,
  ServerMessage,
  UseRunProgressOptions,
  UseRunProgressReturn,
} from '@/types/websocket';

const TERMINAL_STATUSES: RunStatus[] = ['completed', 'failed', 'timeout', 'cancelled'];

export function useRunProgress(options: UseRunProgressOptions): UseRunProgressReturn {
  const { runId, onComplete, onError, enabled = true } = options;

  // State
  const [progress, setProgress] = useState(0);
  const [status, setStatus] = useState<RunStatus>('pending');
  const [error, setError] = useState<string | null>(null);
  const [results, setResults] = useState<EquationResults | null>(null);
  const [connectionState, setConnectionState] = useState<ConnectionState>('disconnected');
  const [isReady, setIsReady] = useState(false);

  // Refs
  const wsRef = useRef<ProgressWebSocket | null>(null);
  const isTerminalRef = useRef(false);
  const onCompleteRef = useRef(onComplete);
  const onErrorRef = useRef(onError);

  // Keep callback refs up to date
  onCompleteRef.current = onComplete;
  onErrorRef.current = onError;

  // Handle terminal state
  const handleTerminalState = useCallback((newStatus: RunStatus, newError: string | null, newResults: EquationResults | null) => {
    if (isTerminalRef.current) return;
    isTerminalRef.current = true;

    if (newStatus === 'completed' && newResults) {
      onCompleteRef.current?.(newResults);
    } else if (newStatus === 'failed' || newStatus === 'timeout' || newStatus === 'cancelled') {
      const errorMessage = newError || (newStatus === 'timeout' ? 'Analysis timed out' : newStatus === 'cancelled' ? 'Analysis was cancelled' : 'Unknown error');
      onErrorRef.current?.(errorMessage);
    }
  }, []);

  // Handle WebSocket message
  const handleMessage = useCallback((message: ServerMessage) => {
    if (message.type === 'pong') return;

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
  }, [handleTerminalState]);

  // Handle WebSocket state change
  const handleStateChange = useCallback((state: ConnectionState) => {
    setConnectionState(state);
  }, []);

  // Main effect: manage WebSocket connection
  useEffect(() => {
    if (!enabled || !runId) return;

    isTerminalRef.current = false;

    const ws = new ProgressWebSocket(runId, {
      onMessage: handleMessage,
      onStateChange: handleStateChange,
      onError: (err) => {
        console.error('WebSocket error:', err);
      },
    });

    wsRef.current = ws;
    ws.connect();

    return () => {
      ws.close();
      wsRef.current = null;
    };
  }, [enabled, runId, handleMessage, handleStateChange]);

  // Cleanup on terminal state
  useEffect(() => {
    if (TERMINAL_STATUSES.includes(status)) {
      wsRef.current?.close();
    }
  }, [status]);

  return {
    progress,
    status,
    error,
    results,
    connectionState,
    isReady,
  };
}

export type { UseRunProgressOptions, UseRunProgressReturn };
