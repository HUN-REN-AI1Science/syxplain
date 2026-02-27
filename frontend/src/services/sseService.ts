/**
 * SSE Service for Real-time Progress Updates
 *
 * Uses fetch() with Authorization header to connect to the SSE endpoint,
 * then reads the ReadableStream and parses SSE frames.
 */

import { getToken } from '@services/api';
import type { ConnectionState, ServerMessage, SSEOptions } from '@/types/sse';

const DEFAULT_OPTIONS: Required<
  Omit<SSEOptions, 'onMessage' | 'onStateChange' | 'onError' | 'onClose'>
> = {
  maxRetries: 5,
  initialDelay: 1000,
  maxDelay: 30000,
};

/** HTTP status codes that should not trigger reconnection. */
const NON_RECOVERABLE_CODES = new Set([401, 403, 404]);

export class ProgressSSE {
  private runId: string;
  private options: Required<SSEOptions>;
  private abortController: AbortController | null = null;
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
      onClose: options.onClose ?? (() => {}),
    };
  }

  /**
   * Connect to the SSE endpoint.
   * Gets the JWT token and starts a fetch-based SSE stream.
   */
  async connect(): Promise<void> {
    if (this.closed) {
      return;
    }

    this.setState('connecting');

    try {
      const token = getToken();
      if (!token) {
        throw new Error('No authentication token available');
      }

      this.abortController = new AbortController();
      const url = `/api/sse/progress/${this.runId}`;

      const response = await fetch(url, {
        headers: {
          Authorization: `Bearer ${token}`,
          Accept: 'text/event-stream',
        },
        signal: this.abortController.signal,
      });

      if (!response.ok) {
        if (NON_RECOVERABLE_CODES.has(response.status)) {
          this.options.onError(new Error(`SSE connection failed: ${response.status}`));
          this.setState('failed');
          return;
        }
        throw new Error(`SSE connection failed: ${response.status}`);
      }

      this.retryCount = 0;
      this.setState('connected');

      await this.readStream(response);
    } catch (error) {
      if (this.closed) return;
      // AbortError is expected on intentional close
      if (error instanceof DOMException && error.name === 'AbortError') return;

      this.options.onError(error instanceof Error ? error : new Error(String(error)));
      this.scheduleReconnect();
    }
  }

  /**
   * Close the SSE connection permanently.
   */
  close(): void {
    this.closed = true;
    this.cleanup();
    this.setState('disconnected');
  }

  /**
   * Get the current connection state.
   */
  getState(): ConnectionState {
    return this.state;
  }

  private setState(state: ConnectionState): void {
    if (this.state !== state) {
      this.state = state;
      this.options.onStateChange(state);
    }
  }

  /**
   * Read and parse the SSE stream from a fetch Response.
   */
  private async readStream(response: Response): Promise<void> {
    const reader = response.body?.getReader();
    if (!reader) {
      throw new Error('Response body is not readable');
    }

    const decoder = new TextDecoder();
    let buffer = '';

    try {
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });

        // SSE frames are delimited by blank lines (\n\n)
        const frames = buffer.split('\n\n');
        // Last element is incomplete — keep it in the buffer
        buffer = frames.pop() ?? '';

        for (const frame of frames) {
          this.parseFrame(frame);
        }
      }
    } finally {
      reader.releaseLock();
    }

    // Stream ended normally (server closed)
    if (!this.closed) {
      this.options.onClose();
      this.setState('disconnected');
    }
  }

  /**
   * Parse a single SSE frame and dispatch the message.
   */
  private parseFrame(frame: string): void {
    let eventType = 'message';
    let data = '';

    for (const line of frame.split('\n')) {
      if (line.startsWith(':')) {
        // Comment line (e.g. keepalive) — ignore
        continue;
      }

      const colonIndex = line.indexOf(':');
      if (colonIndex === -1) continue;

      const field = line.slice(0, colonIndex);
      // SSE spec: if there's a space after the colon, skip it
      const value = line[colonIndex + 1] === ' ' ? line.slice(colonIndex + 2) : line.slice(colonIndex + 1);

      switch (field) {
        case 'event':
          eventType = value;
          break;
        case 'data':
          data += (data ? '\n' : '') + value;
          break;
      }
    }

    if (!data) return;

    try {
      const message = JSON.parse(data) as ServerMessage;
      // Verify the event type matches known types
      if (eventType === 'initial_state' || eventType === 'progress_update') {
        this.options.onMessage(message);
      }
    } catch (error) {
      console.error('Failed to parse SSE message:', error);
    }
  }

  private scheduleReconnect(): void {
    if (this.closed) {
      return;
    }

    if (this.retryCount >= this.options.maxRetries) {
      this.setState('failed');
      return;
    }

    this.setState('reconnecting');
    this.retryCount++;

    // Exponential backoff with jitter
    const delay = Math.min(
      this.options.initialDelay * Math.pow(2, this.retryCount - 1) + Math.random() * 1000,
      this.options.maxDelay
    );

    console.log(
      `SSE reconnecting in ${Math.round(delay)}ms (attempt ${this.retryCount}/${this.options.maxRetries})`
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

    if (this.abortController) {
      this.abortController.abort();
      this.abortController = null;
    }
  }
}
