/**
 * WebSocket Service for Real-time Progress Updates
 *
 * Provides a WebSocket connection with automatic reconnection,
 * exponential backoff, and keepalive ping/pong.
 */

import { supabase } from '@services/supabaseClient';
import type { ConnectionState, ServerMessage, WebSocketOptions } from '@/types/websocket';

const DEFAULT_OPTIONS: Required<
  Omit<WebSocketOptions, 'onMessage' | 'onStateChange' | 'onError' | 'onClose'>
> = {
  maxRetries: 5,
  initialDelay: 1000,
  maxDelay: 30000,
  pingInterval: 30000,
};

export class ProgressWebSocket {
  private runId: string;
  private options: Required<WebSocketOptions>;
  private ws: WebSocket | null = null;
  private state: ConnectionState = 'disconnected';
  private retryCount = 0;
  private reconnectTimeout: ReturnType<typeof setTimeout> | null = null;
  private pingInterval: ReturnType<typeof setInterval> | null = null;
  private closed = false;

  constructor(runId: string, options: WebSocketOptions = {}) {
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
   * Connect to the WebSocket server.
   * Gets the JWT token from Supabase and establishes connection.
   */
  async connect(): Promise<void> {
    if (this.closed) {
      return;
    }

    this.setState('connecting');

    try {
      const token = await this.getAuthToken();
      if (!token) {
        throw new Error('No authentication token available');
      }

      const wsUrl = this.buildWebSocketUrl(token);
      this.ws = new WebSocket(wsUrl);

      this.ws.onopen = this.handleOpen.bind(this);
      this.ws.onmessage = this.handleMessage.bind(this);
      this.ws.onerror = this.handleError.bind(this);
      this.ws.onclose = this.handleClose.bind(this);
    } catch (error) {
      this.options.onError(error instanceof Error ? error : new Error(String(error)));
      this.scheduleReconnect();
    }
  }

  /**
   * Close the WebSocket connection permanently.
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

  private async getAuthToken(): Promise<string | null> {
    const {
      data: { session },
    } = await supabase.auth.getSession();
    return session?.access_token ?? null;
  }

  private buildWebSocketUrl(token: string): string {
    // Use relative URL so Vite proxy handles it in dev, and nginx handles it in production
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const host = window.location.host;
    return `${protocol}//${host}/ws/progress/${this.runId}?token=${encodeURIComponent(token)}`;
  }

  private setState(state: ConnectionState): void {
    if (this.state !== state) {
      this.state = state;
      this.options.onStateChange(state);
    }
  }

  private handleOpen(): void {
    this.retryCount = 0;
    this.setState('connected');
    this.startPingInterval();
  }

  private handleMessage(event: MessageEvent): void {
    try {
      const message = JSON.parse(event.data) as ServerMessage;
      this.options.onMessage(message);
    } catch (error) {
      console.error('Failed to parse WebSocket message:', error);
    }
  }

  private handleError(event: Event): void {
    console.error('WebSocket error:', event);
    this.options.onError(new Error('WebSocket connection error'));
  }

  private handleClose(event: CloseEvent): void {
    this.cleanup();
    this.options.onClose(event.code, event.reason);

    // Don't reconnect if intentionally closed, normal server close, or auth failed
    if (
      this.closed ||
      event.code === 1000 ||
      event.code === 4001 ||
      event.code === 4003 ||
      event.code === 4004
    ) {
      this.setState('disconnected');
      return;
    }

    this.scheduleReconnect();
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
      `WebSocket reconnecting in ${Math.round(delay)}ms (attempt ${this.retryCount}/${this.options.maxRetries})`
    );

    this.reconnectTimeout = setTimeout(() => {
      this.connect();
    }, delay);
  }

  private startPingInterval(): void {
    this.stopPingInterval();
    this.pingInterval = setInterval(() => {
      if (this.ws?.readyState === WebSocket.OPEN) {
        this.ws.send(JSON.stringify({ type: 'ping' }));
      }
    }, this.options.pingInterval);
  }

  private stopPingInterval(): void {
    if (this.pingInterval) {
      clearInterval(this.pingInterval);
      this.pingInterval = null;
    }
  }

  private cleanup(): void {
    this.stopPingInterval();

    if (this.reconnectTimeout) {
      clearTimeout(this.reconnectTimeout);
      this.reconnectTimeout = null;
    }

    if (this.ws) {
      this.ws.onopen = null;
      this.ws.onmessage = null;
      this.ws.onerror = null;
      this.ws.onclose = null;

      if (this.ws.readyState === WebSocket.OPEN || this.ws.readyState === WebSocket.CONNECTING) {
        this.ws.close();
      }
      this.ws = null;
    }
  }
}
