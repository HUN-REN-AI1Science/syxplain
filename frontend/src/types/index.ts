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

export type RunStatus = 'pending' | 'running' | 'completed' | 'failed' | 'timeout';
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
