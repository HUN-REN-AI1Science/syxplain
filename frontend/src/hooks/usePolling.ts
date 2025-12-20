/**
 * usePolling Hook
 * Generic polling hook for data fetching with automatic stop conditions
 */

import { useState, useEffect, useCallback, useRef } from 'react';

export interface UsePollingOptions<T> {
  /** Polling interval in milliseconds */
  interval?: number;
  /** Function to determine if polling should stop */
  shouldStop?: (data: T) => boolean;
  /** Whether polling is enabled */
  enabled?: boolean;
  /** Callback when polling stops */
  onStop?: (data: T) => void;
  /** Callback on error */
  onError?: (error: Error) => void;
}

export interface UsePollingResult<T> {
  data: T | null;
  loading: boolean;
  error: Error | null;
  /** Manually trigger a fetch */
  refetch: () => Promise<void>;
  /** Stop polling */
  stop: () => void;
}

/**
 * Hook for polling data at regular intervals
 *
 * @example
 * const { data, loading, error } = usePolling(
 *   () => api.get(`/runs/${runId}`),
 *   {
 *     interval: 2000,
 *     shouldStop: (data) => data.status === 'completed' || data.status === 'failed',
 *   }
 * );
 */
export function usePolling<T>(
  fetcher: () => Promise<T>,
  options: UsePollingOptions<T> = {}
): UsePollingResult<T> {
  const {
    interval = 2000,
    shouldStop = () => false,
    enabled = true,
    onStop,
    onError,
  } = options;

  const [data, setData] = useState<T | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<Error | null>(null);
  const [stopped, setStopped] = useState(false);

  const intervalRef = useRef<NodeJS.Timeout | null>(null);
  const fetcherRef = useRef(fetcher);
  const shouldStopRef = useRef(shouldStop);
  const onStopRef = useRef(onStop);
  const onErrorRef = useRef(onError);

  // Update refs when callbacks change
  useEffect(() => {
    fetcherRef.current = fetcher;
    shouldStopRef.current = shouldStop;
    onStopRef.current = onStop;
    onErrorRef.current = onError;
  }, [fetcher, shouldStop, onStop, onError]);

  const stop = useCallback(() => {
    setStopped(true);
    if (intervalRef.current) {
      clearInterval(intervalRef.current);
      intervalRef.current = null;
    }
  }, []);

  const fetchData = useCallback(async () => {
    try {
      const result = await fetcherRef.current();
      setData(result);
      setError(null);

      // Check if we should stop polling
      if (shouldStopRef.current(result)) {
        stop();
        onStopRef.current?.(result);
      }

      return result;
    } catch (err) {
      const error = err instanceof Error ? err : new Error(String(err));
      setError(error);
      onErrorRef.current?.(error);
      throw error;
    } finally {
      setLoading(false);
    }
  }, [stop]);

  // Initial fetch and polling setup
  useEffect(() => {
    if (!enabled || stopped) {
      setLoading(false);
      return;
    }

    // Initial fetch
    fetchData();

    // Setup polling
    intervalRef.current = setInterval(() => {
      if (!stopped) {
        fetchData();
      }
    }, interval);

    return () => {
      if (intervalRef.current) {
        clearInterval(intervalRef.current);
        intervalRef.current = null;
      }
    };
  }, [enabled, interval, stopped, fetchData]);

  const refetch = useCallback(async () => {
    setLoading(true);
    await fetchData();
  }, [fetchData]);

  return {
    data,
    loading,
    error,
    refetch,
    stop,
  };
}
