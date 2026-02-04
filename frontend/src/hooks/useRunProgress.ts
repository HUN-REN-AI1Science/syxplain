/**
 * useRunProgress Hook
 *
 * Provides real-time progress updates for a run, using WebSocket as primary
 * transport with automatic fallback to HTTP polling if WebSocket fails.
 */

import { useCallback, useEffect, useRef, useState } from 'react';
import { runsService } from '@services/api';
import { ProgressWebSocket } from '@services/websocketService';
import type { EquationResults, RunStatus } from '@/types';
import type {
  ConnectionState,
  ServerMessage,
  UseRunProgressOptions,
  UseRunProgressReturn,
} from '@/types/websocket';

const POLLING_INTERVAL = 2000;
const TERMINAL_STATUSES: RunStatus[] = ['completed', 'failed', 'timeout', 'cancelled'];

export function useRunProgress(options: UseRunProgressOptions): UseRunProgressReturn {
  const { runId, onComplete, onError, enabled = true } = options;

  // State
  const [progress, setProgress] = useState(0);
  const [status, setStatus] = useState<RunStatus>('pending');
  const [error, setError] = useState<string | null>(null);
  const [results, setResults] = useState<EquationResults | null>(null);
  const [connectionMethod, setConnectionMethod] = useState<'websocket' | 'polling'>('websocket');
  const [connectionState, setConnectionState] = useState<ConnectionState>('disconnected');
  const [isReady, setIsReady] = useState(false);

  // Refs
  const wsRef = useRef<ProgressWebSocket | null>(null);
  const pollingIntervalRef = useRef<ReturnType<typeof setInterval> | null>(null);
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

  // Handle WebSocket failure - fall back to polling
  const handleWsFailed = useCallback(() => {
    if (isTerminalRef.current) return;

    console.log('WebSocket failed, falling back to HTTP polling');
    setConnectionMethod('polling');
  }, []);

  // Start polling
  const startPolling = useCallback(async () => {
    if (isTerminalRef.current || !runId) return;

    const poll = async () => {
      if (isTerminalRef.current) return;

      try {
        const response = await runsService.getById(runId);
        const data = response.data;

        setStatus(data.status as RunStatus);
        setProgress(data.progress || 0);
        setIsReady(true);

        if (data.status === 'completed') {
          const results = data.results;
          if (results && 'equations' in results) {
            setResults(results as EquationResults);
            setProgress(100);
            handleTerminalState('completed', null, results as EquationResults);
          }
        } else if (TERMINAL_STATUSES.includes(data.status as RunStatus)) {
          const errorMessage = data.error || 'Unknown error';
          setError(errorMessage);
          handleTerminalState(data.status as RunStatus, errorMessage, null);
        }
      } catch (e) {
        console.error('Polling error:', e);
      }
    };

    // Initial poll
    await poll();

    // Set up interval
    pollingIntervalRef.current = setInterval(poll, POLLING_INTERVAL);
  }, [runId, handleTerminalState]);

  // Stop polling
  const stopPolling = useCallback(() => {
    if (pollingIntervalRef.current) {
      clearInterval(pollingIntervalRef.current);
      pollingIntervalRef.current = null;
    }
  }, []);

  // Main effect: manage connection
  useEffect(() => {
    if (!enabled || !runId) return;

    isTerminalRef.current = false;

    if (connectionMethod === 'websocket') {
      // Try WebSocket first
      const ws = new ProgressWebSocket(runId, {
        onMessage: handleMessage,
        onStateChange: handleStateChange,
        onClose: (code) => {
          // If auth failed or access denied, fall back to polling
          if (code === 4001 || code === 4003 || code === 4004) {
            handleWsFailed();
          }
        },
        onError: () => {
          // Don't immediately fail - let reconnection logic handle it
        },
      });

      wsRef.current = ws;
      ws.connect();

      // Watch for failed state
      const checkFailed = setInterval(() => {
        if (ws.getState() === 'failed') {
          handleWsFailed();
          clearInterval(checkFailed);
        }
      }, 500);

      return () => {
        clearInterval(checkFailed);
        ws.close();
        wsRef.current = null;
      };
    } else {
      // Use polling
      startPolling();
      setConnectionState('connected');

      return () => {
        stopPolling();
      };
    }
  }, [enabled, runId, connectionMethod, handleMessage, handleStateChange, handleWsFailed, startPolling, stopPolling]);

  // Cleanup on terminal state
  useEffect(() => {
    if (TERMINAL_STATUSES.includes(status)) {
      wsRef.current?.close();
      stopPolling();
    }
  }, [status, stopPolling]);

  return {
    progress,
    status,
    error,
    results,
    connectionMethod,
    connectionState,
    isReady,
  };
}

export type { UseRunProgressOptions, UseRunProgressReturn };
