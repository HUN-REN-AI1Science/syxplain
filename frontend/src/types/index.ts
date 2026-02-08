/**
 * Shared TypeScript interfaces for Syxplain Frontend
 * Centralized type definitions to ensure consistency across components
 */

// ============================================================================
// API Response Types
// ============================================================================

export interface PaginatedResponse<T> {
  items: T[];
  total: number;
  page: number;
  page_size: number;
  total_pages: number;
}

// ============================================================================
// Run / Analysis Types
// ============================================================================

export interface RunSummary {
  id: string;
  status: RunStatus;
  created_at: string;
  csv_filename: string;
  target_variable: string | null;
  progress: number;
  analysis_type: AnalysisType;
  start_time: string | null;
  finish_time: string | null;
}

export interface RunDetails {
  id: string;
  status: RunStatus;
  created_at: string | null;
  problem_description: ProblemDescription;
  csv_filename: string;
  csv_metadata: CsvMetadata | null;
  analysis_type: AnalysisType | null;
  error: string | null;
}

export type RunStatus = 'pending' | 'running' | 'completed' | 'failed' | 'timeout' | 'cancelled';
export type AnalysisType = 'quick' | 'deep';

export interface ProblemDescription {
  project_description: string;
  target_variable: string;
  features: Record<string, string>;
}

export interface CsvMetadata {
  filename: string;
  size_bytes: number;
  row_count: number | null;
  column_count: number | null;
  columns: string[];
}

// ============================================================================
// Equation Types
// ============================================================================

export interface TermExplanation {
  term: string;
  explanation: string;
}

export interface ScatterData {
  measured: number[];
  predicted: number[];
}

export interface Equation {
  id: number;
  equation: string;
  loss: number;
  complexity: number;
  overview: string;
  term_explanations: TermExplanation[];
  citations?: string[];
  scatter_data?: ScatterData;
}

export interface Summary {
  key_drivers: string[];
  secondary_drivers: string[];
  findings: string;
}

export interface Recommendation {
  equation_id: number;
  rationale: string[];
}

export interface EquationResults {
  equations: Equation[];
  summary: Summary;
  recommendation: Recommendation;
  _parse_error?: string;
}

// ============================================================================
// Progress Types
// ============================================================================

export interface ProgressPhase {
  name: string;
  label: string;
  description?: string;
  progress_end: number;
  increment_rate: number;
}

// ============================================================================
// Upload Types
// ============================================================================

export interface UploadResponse {
  filename: string;
  columns: string[];
  column_types: Record<string, string>;
  nan_counts: Record<string, number>;
  error?: string;
}

// ============================================================================
// Profile Types
// ============================================================================

export interface ProfileData {
  email: string;
  created_at: string | null;
  total_runs: number;
  total_files: number;
}

// ============================================================================
// Form Types
// ============================================================================

export interface ProblemFormPayload {
  project_description: string;
  target_variable: string;
  features: Record<string, string>;
  analysis_type: AnalysisType;
  deep_research_model: string | null;
}

// ============================================================================
// Permission Types
// ============================================================================

export interface UserPermissions {
  use_hunren_keys: boolean;
  is_admin: boolean;
}

export interface UserApiKeys {
  openai_api_key: string;
  openai_model: string;
}

export interface UserPermissionInfo {
  user_id: string;
  email: string;
  use_hunren_keys: boolean;
  granted_by: string | null;
  user_created_at: string | null;
  permission_updated_at: string | null;
}

// ============================================================================
// Admin Dashboard Types
// ============================================================================

export interface DashboardStats {
  total_users: number;
  active_users_24h: number;
  total_runs: number;
  runs_today: number;
  success_rate: number;
  avg_duration_seconds: number;
  pending_runs: number;
  running_runs: number;
}

export interface RunTrendItem {
  date: string;
  total: number;
  completed: number;
  failed: number;
  timeout: number;
  cancelled: number;
}

export interface StatusDistributionItem {
  status: string;
  count: number;
}

// ============================================================================
// Admin Run Management Types
// ============================================================================

export interface AdminRunSummary {
  id: string;
  user_id: string;
  user_email: string | null;
  status: RunStatus;
  created_at: string;
  csv_filename: string;
  target_variable: string | null;
  progress: number;
  analysis_type: AnalysisType;
  start_time: string | null;
  finish_time: string | null;
  error: string | null;
}

export interface AdminRunDetail {
  id: string;
  user_id: string;
  user_email: string | null;
  status: RunStatus;
  created_at: string | null;
  problem_description: ProblemDescription;
  csv_filename: string;
  analysis_type: AnalysisType;
  error: string | null;
  progress: number;
  start_time: string | null;
  finish_time: string | null;
  results: Record<string, unknown> | null;
  slurm_job_ids: Record<string, string> | null;
}

export interface AdminRunActionResponse {
  success: boolean;
  message: string;
  run_id: string;
}

// ============================================================================
// System Monitoring Types
// ============================================================================

export interface SystemHealth {
  database_connected: boolean;
  slurm_configured: boolean;
  slurm_connected: boolean;
  api_healthy: boolean;
  uptime_seconds: number;
  checked_at: string;
}

export interface PartitionInfo {
  name: string;
  state: string;
  total_nodes: number;
  total_cpus: number;
}

export interface SlurmStatus {
  cluster_status: string;
  queue_length: number;
  active_jobs: number;
  total_jobs: number;
  partitions: PartitionInfo[];
  node_status: Record<string, number>;
  total_nodes: number;
  checked_at: string;
  error?: string;
  // Configuration info for highlighting in UI
  configured_partition?: string;
  configured_cpus?: number;
  configured_memory?: string;
}

// ============================================================================
// Audit Log Types
// ============================================================================

export interface AuditLogEntry {
  id: string;
  admin_email: string;
  action: string;
  target_type: string;
  target_id: string;
  details: Record<string, unknown> | null;
  ip_address: string | null;
  created_at: string;
}

export interface AuditFilterOptions {
  actions: string[];
  admins: string[];
}

// ============================================================================
// Error Monitoring Types
// ============================================================================

export interface ErrorDistributionItem {
  error_type: string;
  count: number;
}

export interface ErrorTrendItem {
  date: string;
  total: number;
  failed: number;
  failure_rate: number;
}

// ============================================================================
// Analytics Types
// ============================================================================

export interface UserGrowthItem {
  date: string;
  count: number;
}

export interface TopUserItem {
  user_id: string;
  email: string | null;
  run_count: number;
  completed: number;
}

export interface PerformanceStats {
  avg_duration: number;
  median_duration: number;
  p95_duration: number;
  success_rate: number;
  total_completed: number;
}

export interface PerformanceByTypeItem {
  type: string;
  total_runs: number;
  completed: number;
  failed: number;
  avg_duration: number;
  success_rate: number;
}

// ============================================================================
// Configuration Types
// ============================================================================

export interface RateLimitsConfig {
  runs_per_minute: number;
  uploads_per_minute: number;
  admin_requests_per_minute: number;
}

export interface FeaturesConfig {
  slurm_configured: boolean;
  deep_research_enabled: boolean;
  user_api_keys_enabled: boolean;
}

export interface SecretsConfig {
  openai_api_key: string | null;
  deep_research_api_key: string | null;
  slurm_auth_token: string | null;
  database_host: string | null;
}

export interface SystemConfig {
  compute_backend: string;
  analysis_timeout_hours: number;
  max_file_size_mb: number;
  rate_limits: RateLimitsConfig;
  features: FeaturesConfig;
  secrets: SecretsConfig;
}

// ============================================================================
// Activity Feed Types
// ============================================================================

export interface ActivityItem {
  id: string;
  admin_email: string;
  action: string;
  target_type: string;
  target_id: string;
  details: Record<string, unknown> | null;
  created_at: string;
}

// ============================================================================
// Feedback Types
// ============================================================================

export type FeedbackCategory = 'bug' | 'feature';

export interface FeedbackContext {
  current_view?: string;
  workflow_step?: number;
  current_run_id?: string;
  csv_filename?: string;
  browser_user_agent?: string;
  screen_resolution?: string;
  timestamp?: string;
  app_url?: string;
}

export interface FeedbackRequest {
  category: FeedbackCategory;
  title: string;
  description: string;
  context?: FeedbackContext;
}

export interface FeedbackResponse {
  success: boolean;
  issue_url: string | null;
  issue_number: number | null;
  message: string;
}
