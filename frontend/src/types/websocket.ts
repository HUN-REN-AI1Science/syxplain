/**
 * WebSocket Types for Real-time Progress Updates
 */

import type { EquationResults, RunStatus } from './index';

// ============================================================================
// Server -> Client Messages
// ============================================================================

export interface InitialStateMessage {
  type: 'initial_state';
  run_id: string;
  status: RunStatus;
  progress: number;
  error: string | null;
  results: EquationResults | null;
}

export interface ProgressUpdateMessage {
  type: 'progress_update';
  run_id: string;
  status: RunStatus;
  progress: number;
  step_name: string | null;
  error: string | null;
  results: EquationResults | null;
  timestamp: string;
}

export interface PongMessage {
  type: 'pong';
}

export type ServerMessage = InitialStateMessage | ProgressUpdateMessage | PongMessage;

// ============================================================================
// Client -> Server Messages
// ============================================================================

export interface PingMessage {
  type: 'ping';
}

export type ClientMessage = PingMessage;

// ============================================================================
// Connection State
// ============================================================================

export type ConnectionState = 'connecting' | 'connected' | 'reconnecting' | 'disconnected' | 'failed';

// ============================================================================
// WebSocket Service Options
// ============================================================================

export interface WebSocketOptions {
  /** Called when a message is received from the server */
  onMessage?: (message: ServerMessage) => void;
  /** Called when connection state changes */
  onStateChange?: (state: ConnectionState) => void;
  /** Called when an error occurs */
  onError?: (error: Error) => void;
  /** Called when the connection is closed */
  onClose?: (code: number, reason: string) => void;
  /** Maximum number of reconnection attempts before giving up (default: 5) */
  maxRetries?: number;
  /** Initial reconnection delay in ms (default: 1000) */
  initialDelay?: number;
  /** Maximum reconnection delay in ms (default: 30000) */
  maxDelay?: number;
  /** Ping interval in ms to keep connection alive (default: 30000) */
  pingInterval?: number;
}

// ============================================================================
// Hook Options and Return Types
// ============================================================================

export interface UseRunProgressOptions {
  runId: string;
  /** Called when the run completes successfully */
  onComplete?: (results: EquationResults) => void;
  /** Called when the run fails */
  onError?: (error: string) => void;
  /** Whether to enable the hook (default: true) */
  enabled?: boolean;
}

export interface UseRunProgressReturn {
  /** Current progress percentage (0-100) */
  progress: number;
  /** Current run status */
  status: RunStatus;
  /** Error message if the run failed */
  error: string | null;
  /** Results if the run completed */
  results: EquationResults | null;
  /** Current connection method */
  connectionMethod: 'websocket' | 'polling';
  /** Current connection state */
  connectionState: ConnectionState;
  /** Whether the initial data has been loaded */
  isReady: boolean;
}
