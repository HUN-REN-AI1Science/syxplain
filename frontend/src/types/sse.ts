/**
 * SSE Types for Real-time Progress Updates
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

export type ServerMessage = InitialStateMessage | ProgressUpdateMessage;

// ============================================================================
// Connection State
// ============================================================================

export type ConnectionState =
  | 'connecting'
  | 'connected'
  | 'reconnecting'
  | 'disconnected'
  | 'failed';

// ============================================================================
// SSE Service Options
// ============================================================================

export interface SSEOptions {
  /** Called when a message is received from the server */
  onMessage?: (message: ServerMessage) => void;
  /** Called when connection state changes */
  onStateChange?: (state: ConnectionState) => void;
  /** Called when an error occurs */
  onError?: (error: Error) => void;
  /** Maximum number of reconnection attempts before giving up (default: 5) */
  maxRetries?: number;
  /** Initial reconnection delay in ms (default: 1000) */
  initialDelay?: number;
  /** Maximum reconnection delay in ms (default: 30000) */
  maxDelay?: number;
}

// ============================================================================
// Hook Options and Return Types
// ============================================================================

export interface UseRunProgressOptions {
  runId: string | null;
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
  /** Current connection state */
  connectionState: ConnectionState;
  /** Whether the initial data has been loaded */
  isReady: boolean;
}
