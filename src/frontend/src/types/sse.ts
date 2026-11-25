/**
 * SSE Types for Real-time Progress Updates
 */

import type { AgentEvent, EquationResults, ProgressPhase, RunStatus } from './index';

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
  /** Recent discovery-agent activity, replayed for clients that join mid-run */
  recent_events?: AgentEventMessage[];
  /** Latest progress (%) of each cluster search */
  search_progress?: Record<string, number>;
  /** Progress phases, for clients that join without the run response (reload, history) */
  progress_phases?: ProgressPhase[];
}

export interface AgentEventMessage {
  type: 'agent_event';
  run_id: string;
  event: AgentEvent;
  timestamp: string;
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

/** How far one cluster search has got: its current state, not a step of the run's history */
export interface SearchProgressMessage {
  type: 'search_progress';
  run_id: string;
  search_id: string;
  progress: number;
  timestamp: string;
}

export type ServerMessage =
  | InitialStateMessage
  | ProgressUpdateMessage
  | AgentEventMessage
  | SearchProgressMessage;

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
  /** Live discovery-agent activity (most recent last) */
  activity: AgentEvent[];
  /** Latest progress (%) of each cluster search */
  searchProgress: Record<string, number>;
  /** Progress phases sent by the server on connect (empty until then) */
  phases: ProgressPhase[];
}
