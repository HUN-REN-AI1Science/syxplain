/**
 * SSE Service for Real-time Progress Updates
 *
 * Uses the browser's native EventSource API for reliable SSE streaming.
 * Authentication is passed via ?token= query parameter since EventSource
 * does not support custom headers.
 */

import { getToken } from '@services/api';
import type { ConnectionState, ServerMessage, SSEOptions } from '@/types/sse';

const DEFAULT_OPTIONS: Required<Omit<SSEOptions, 'onMessage' | 'onStateChange' | 'onError'>> = {
  maxRetries: 5,
  initialDelay: 1000,
  maxDelay: 30000,
};

export class ProgressSSE {
  private runId: string;
  private options: Required<SSEOptions>;
  private eventSource: EventSource | null = null;
  private state: ConnectionState = 'disconnected';
  private retryCount = 0;
  private reconnectTimeout: ReturnType<typeof setTimeout> | null = null;
  private closed = false;

  constructor(runId: string, options: SSEOptions = {}) {
    this.runId = runId;
    this.options = {
      ...DEFAULT_OPTIONS,
      onMessage: options.onMessage ?? (() => {}),
      onStateChange: options.onStateChange ?? (() => {}),
      onError: options.onError ?? (() => {}),
    };
  }

  /**
   * Connect to the SSE endpoint using native EventSource.
   */
  connect(): void {
    if (this.closed) return;

    this.setState('connecting');

    const token = getToken();
    if (!token) {
      this.options.onError(new Error('No authentication token available'));
      this.setState('failed');
      return;
    }

    const url = `/api/sse/progress/${this.runId}?token=${encodeURIComponent(token)}`;
    const es = new EventSource(url);
    this.eventSource = es;

    es.addEventListener('initial_state', (event: MessageEvent) => {
      this.retryCount = 0;
      this.setState('connected');
      this.handleMessage(event.data);
    });

    es.addEventListener('progress_update', (event: MessageEvent) => {
      this.handleMessage(event.data);
    });

    es.addEventListener('agent_event', (event: MessageEvent) => {
      this.handleMessage(event.data);
    });

    es.addEventListener('error', (event: MessageEvent) => {
      try {
        const data = JSON.parse(event.data);
        this.options.onError(new Error(data.message || 'SSE error'));
      } catch {
        // Not a JSON error event — handled by onerror
      }
    });

    es.onerror = () => {
      if (this.closed) return;

      // EventSource fires onerror when the connection drops.
      // If readyState is CLOSED, the browser won't auto-reconnect.
      if (es.readyState === EventSource.CLOSED) {
        this.cleanup();
        this.scheduleReconnect();
      }
      // If CONNECTING, the browser is auto-reconnecting — wait.
    };
  }

  close(): void {
    this.closed = true;
    this.cleanup();
    this.setState('disconnected');
  }

  getState(): ConnectionState {
    return this.state;
  }

  private setState(state: ConnectionState): void {
    if (this.state !== state) {
      this.state = state;
      this.options.onStateChange(state);
    }
  }

  private handleMessage(data: string): void {
    try {
      const message = JSON.parse(data) as ServerMessage;
      this.options.onMessage(message);
    } catch (error) {
      console.error('Failed to parse SSE message:', error);
    }
  }

  private scheduleReconnect(): void {
    if (this.closed) return;

    if (this.retryCount >= this.options.maxRetries) {
      this.setState('failed');
      return;
    }

    this.setState('reconnecting');
    this.retryCount++;

    const delay = Math.min(
      this.options.initialDelay * Math.pow(2, this.retryCount - 1) + Math.random() * 1000,
      this.options.maxDelay
    );

    this.reconnectTimeout = setTimeout(() => {
      this.connect();
    }, delay);
  }

  private cleanup(): void {
    if (this.reconnectTimeout) {
      clearTimeout(this.reconnectTimeout);
      this.reconnectTimeout = null;
    }

    if (this.eventSource) {
      this.eventSource.close();
      this.eventSource = null;
    }
  }
}
