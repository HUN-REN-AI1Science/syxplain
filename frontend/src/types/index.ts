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
  start_time: string | null;
  finish_time: string | null;
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
  /** Which predictions are plotted: held-out rows, or out-of-fold CV predictions (small data) */
  basis?: 'holdout' | 'cv_oof';
}

/**
 * What a model's score is computed on. 'cv' when the dataset was too small for a holdout.
 * Runs from before this field existed are treated as 'holdout'.
 */
export type MetricBasis = 'holdout' | 'cv';

export interface Equation {
  id: number;
  equation: string;
  /** MSE on metric_basis */
  loss: number | null;
  complexity: number;
  overview: string;
  term_explanations: TermExplanation[];
  citations?: string[];
  scatter_data?: ScatterData;
  /** "symbolic" (PySR), "classic: <family>", "custom: <label>" or "literature: <label>" */
  origin?: string;
  model_id?: string;
  /** R² on metric_basis */
  score?: number | null;
  sympy_format?: string;
  source?: string | null;
  metric_basis?: MetricBasis;
  /** R² on held-out rows no model was trained on (null when metric_basis is 'cv') */
  holdout_r2?: number | null;
  holdout_n?: number;
  cv_r2?: number | null;
  /** Standard error of the fold RMSE */
  cv_se?: number | null;
  n_params?: number;
  target_transform?: string | null;
  verdict?: ModelVerdict;
  reasons?: string[];
  /** Rows where the model is undefined (counted as errors) */
  n_undefined?: number;
  /** Alias used in the equation -> original column name (includes the target alias) */
  variables?: Record<string, string>;
  target_alias?: string;
  /** The single recommended model chosen by the selector */
  is_headline?: boolean;
  agent_recommended?: boolean;
  agent_why?: string | null;
}

export interface Summary {
  key_drivers: string[];
  secondary_drivers: string[];
  findings: string;
}

export interface Recommendation {
  equation_id: number;
  rationale: string[];
  /** False when the explanation AI prefers a different equation than the selector's headline */
  agrees_with_headline?: boolean;
  disagreement_reason?: string;
}

/** A non-fatal problem during the run; the results are still usable */
export interface RunWarning {
  stage: 'agent' | 'explanation' | 'deep_research' | 'literature' | 'storage';
  message: string;
}

export interface EquationResults {
  equations: Equation[];
  summary: Summary;
  recommendation: Recommendation;
  _parse_error?: string;
  /** Set when the LLM explanation step failed; equations are raw discovery output */
  _explanation_error?: boolean;
  /** Error message of the failed explanation step, when known */
  _explanation_error_message?: string;
  /** Non-fatal problems (top-level results.warnings) */
  warnings?: RunWarning[];
  discovery?: DiscoveryReport;
}

// ============================================================================
// Discovery Agent Types
// ============================================================================

export type ModelKind = 'classic' | 'custom' | 'symbolic' | 'literature';
export type ModelVerdict = 'good' | 'adequate' | 'poor' | 'failed' | 'no_signal';

export interface LeaderboardEntry {
  model_id: string;
  kind: ModelKind;
  name: string;
  label: string;
  features: string[];
  equation: string;
  target_transform: string | null;
  complexity: number;
  n_params: number;
  cv_r2: number | null;
  cv_se?: number | null;
  holdout_r2: number | null;
  holdout_rmse: number | null;
  holdout_n?: number;
  metric_basis?: MetricBasis;
  aic: number | null;
  verdict: ModelVerdict;
  /** Diagnosed reasons the model falls short (or that it matches the noise ceiling) */
  reasons: string[];
  source: string | null;
  n_undefined?: number;
  is_headline?: boolean;
  agent_recommended?: boolean;
}

export type NotebookKind = 'hypothesis' | 'rejected_form' | 'candidate' | 'data_issue' | 'insight';

export interface NotebookEntry {
  kind: NotebookKind;
  /** LLM-authored; old runs may hold non-string values, render with asText */
  text: string;
  evidence: string;
  t: number;
  model_ids?: string[];
}

export interface DiscoverySearch {
  search_id: string;
  status: 'submitting' | 'queued' | 'completed' | 'failed' | 'cancelled';
  features: string[];
  unary_operators: string[] | null;
  binary_operators: string[] | null;
  maxsize: number | null;
  niterations: number | null;
  target_transform: string | null;
  guesses: string[];
  rationale: string;
  elapsed_s: number;
  error?: string;
  n_equations?: number;
  best_cv_r2?: number | null;
  best_model_id?: string;
  n_front?: number;
  n_ingested?: number;
  accepted_guesses?: string[];
  rejected_guesses?: { guess: string; reason: string }[];
  timeout_s?: number;
}

/** One step of the discovery agent, streamed live and kept in the report */
export interface AgentEvent {
  /** Seconds since the discovery session started (absent for cluster progress pings) */
  t?: number;
  kind: string;
  text?: string;
  search_id?: string;
  model_id?: string;
  progress?: number;
}

/** Random-forest SHAP summary computed during data profiling */
export interface ShapSummary {
  available: boolean;
  /** False when the data shows no clear signal: interactions and shapes are meaningless */
  reliable?: boolean;
  reason?: string;
  rows_used?: number;
  importance?: { feature: string; mean_abs_shap: number; share: number }[];
  interactions?: { a: string; b: string; share_of_attribution: number }[];
  /** Feature -> shape of its SHAP dependence (may start with "negligible effect") */
  partial_effects?: Record<string, string>;
}

export interface DiscoverySplit {
  complete_rows: number;
  train: number;
  holdout: number;
  scored_on: string;
  has_holdout?: boolean;
  regime?: 'holdout' | 'cv_only';
  metric_basis?: MetricBasis;
  uploaded?: number;
  dropped_incomplete?: number;
  missing_by_column?: Record<string, number>;
  excluded_columns?: { column: string; reason: string }[];
}

export interface DiscoverySelection {
  headline_model_id: string | null;
  /** e.g. 'agent_pick_within_1se' | 'best_cv_1se' | 'no_eligible_model' */
  headline_reason: string;
  shortlist: string[];
  agent_pick_rejected: { model_id: string; reason: string }[];
}

export interface RejectedForm {
  form: string;
  model_id?: string | null;
  reason: string;
}

export interface LiteratureLaw {
  equation: string;
  citations: string[];
  model_id: string | null;
  cv_r2: number | null;
  unmapped: string[];
  fit_error: string | null;
}

export interface DiscoveryAgentReport {
  summary: string;
  recommended_models: { model_id: string; why: string }[];
  /** Old runs may hold plain strings */
  rejected_forms: (RejectedForm | string)[];
  insights: string[];
  open_questions: string[];
  steps?: number | null;
  error: string | null;
  /** 'auto_fallback' = the agent did not write a report; built from the session state */
  source?: 'agent' | 'auto_fallback';
  stale?: boolean;
  late_searches?: string[];
  review_steps?: number;
  claims_failed?: { text: string; issue: string }[];
  reviewed_searches?: string[];
}

export interface DiscoveryReport {
  target: { alias: string; column: string };
  /** Expression variable name -> original column name */
  aliases: Record<string, string>;
  variable_kinds?: Record<string, 'continuous' | 'categorical'>;
  split: DiscoverySplit;
  /** Raw out-of-fold benchmark R² (can be negative) */
  noise_ceiling_r2: number | null;
  noise_ceiling_sd?: number | null;
  /** False = no detectable relationship between the variables and the target */
  has_signal?: boolean;
  shap?: ShapSummary | null;
  selection?: DiscoverySelection;
  n_models_total?: number;
  leaderboard: LeaderboardEntry[];
  failed_fits: { model_id: string; label: string; features: string[]; reason: string | null }[];
  notebook: NotebookEntry[];
  searches: DiscoverySearch[];
  budget: Record<string, number>;
  agent: DiscoveryAgentReport;
  literature?: {
    status: 'ok' | 'empty' | 'failed' | 'pending';
    laws: LiteratureLaw[];
  };
  activity?: AgentEvent[];
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
// API Key Types
// ============================================================================

export interface ApiKey {
  id: string;
  key_prefix: string;
  is_active: boolean;
  created_at: string | null;
  last_used_at: string | null;
}

export interface CreateApiKeyResponse {
  id: string;
  key: string;
  key_prefix: string;
  created_at: string | null;
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
  gemini_api_key: string;
  gemini_model: string;
  openai_api_key?: string;
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
