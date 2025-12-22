/**
 * usePysrStream Hook
 * Connects to WebSocket for live PySR equation updates during training
 */

import { useState, useEffect, useRef, useCallback } from 'react';

export interface UsePysrStreamOptions {
  /** Run ID to stream equations for */
  runId: string;
  /** Whether to enable streaming (only during PySR training step) */
  enabled: boolean;
}

export interface UsePysrStreamResult {
  /** Current equations content */
  equations: string;
  /** Whether WebSocket is connected */
  isConnected: boolean;
}

/**
 * Hook for streaming live PySR equation updates via WebSocket
 *
 * @example
 * const { equations, isConnected } = usePysrStream({
 *   runId: 'abc-123',
 *   enabled: isPysrTrainingStep,
 * });
 */
export function usePysrStream(options: UsePysrStreamOptions): UsePysrStreamResult {
  const { runId, enabled } = options;

  const [equations, setEquations] = useState('');
  const [isConnected, setIsConnected] = useState(false);
  const wsRef = useRef<WebSocket | null>(null);
  const reconnectTimeoutRef = useRef<NodeJS.Timeout | null>(null);

  const connect = useCallback(() => {
    if (!enabled || !runId) return;

    // Use current host (in dev, this flows through Vite proxy; in prod, it's the same origin)
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const wsUrl = `${protocol}//${window.location.host}/ws/runs/${runId}/live`;

    console.log('Connecting to WebSocket:', wsUrl);
    try {
      const ws = new WebSocket(wsUrl);
      wsRef.current = ws;

      ws.onopen = () => {
        setIsConnected(true);
      };

      ws.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data);
          if (data.type === 'equations' && data.content) {
            setEquations(data.content);
          }
        } catch {
          // Ignore parse errors
        }
      };

      ws.onclose = () => {
        setIsConnected(false);
        wsRef.current = null;

        // Attempt reconnect if still enabled
        if (enabled) {
          reconnectTimeoutRef.current = setTimeout(() => {
            connect();
          }, 2000);
        }
      };

      ws.onerror = () => {
        ws.close();
      };
    } catch {
      // Connection failed
    }
  }, [runId, enabled]);

  const disconnect = useCallback(() => {
    if (reconnectTimeoutRef.current) {
      clearTimeout(reconnectTimeoutRef.current);
      reconnectTimeoutRef.current = null;
    }
    if (wsRef.current) {
      wsRef.current.close();
      wsRef.current = null;
    }
    setIsConnected(false);
    setEquations('');
  }, []);

  // Connect/disconnect based on enabled state
  useEffect(() => {
    if (enabled) {
      connect();
    } else {
      disconnect();
    }

    return () => {
      disconnect();
    };
  }, [enabled, connect, disconnect]);

  return { equations, isConnected };
}
