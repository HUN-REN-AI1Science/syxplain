/**
 * API Service Layer
 * Typed API methods with proper request/response handling
 */

import axios, { AxiosInstance } from 'axios';
import type {
  PaginatedResponse,
  RunSummary,
  RunDetails,
  UploadResponse,
  ProfileData,
  ProgressPhase,
  EquationResults,
  UserPermissions,
  UserApiKeys,
  ApiKey,
  CreateApiKeyResponse,
  DashboardStats,
  RunTrendItem,
  StatusDistributionItem,
  AdminRunSummary,
  AdminRunDetail,
  AdminRunActionResponse,
  SystemHealth,
  SlurmStatus,
  AuditLogEntry,
  AuditFilterOptions,
  ErrorDistributionItem,
  ErrorTrendItem,
  UserGrowthItem,
  TopUserItem,
  PerformanceStats,
  PerformanceByTypeItem,
  SystemConfig,
  ActivityItem,
  FeedbackRequest,
  FeedbackResponse,
} from '@/types';

// ============================================================================
// Token getter (set by AuthContext)
// ============================================================================

let tokenGetter: (() => string | null) | null = null;
let signOutHandler: (() => void) | null = null;
let isRedirecting = false;

export function setTokenGetter(getter: () => string | null) {
  tokenGetter = getter;
}

export function setSignOutHandler(handler: () => void) {
  signOutHandler = handler;
}

export function getToken(): string | null {
  return tokenGetter ? tokenGetter() : null;
}

// ============================================================================
// Base API Instance
// ============================================================================

const api: AxiosInstance = axios.create({
  baseURL: '/api',
});

// Add request interceptor to inject auth token
api.interceptors.request.use(async (config) => {
  const token = getToken();
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

// Add response interceptor for 401 handling
api.interceptors.response.use(
  (response) => response,
  async (error) => {
    if (error.response?.status === 401 && !isRedirecting) {
      // Token is invalid — trigger OIDC re-authentication (once)
      isRedirecting = true;
      if (signOutHandler) {
        signOutHandler();
      } else {
        window.location.href = '/';
      }
    }
    return Promise.reject(error);
  }
);

// ============================================================================
// Runs Service
// ============================================================================

export interface GetRunsParams {
  page: number;
  page_size: number;
  sort_field: string;
  sort_order: 'asc' | 'desc';
  status?: string;
  analysis_type?: string;
  search?: string;
}

export const runsService = {
  getAll: (params: GetRunsParams) => {
    const searchParams = new URLSearchParams({
      page: params.page.toString(),
      page_size: params.page_size.toString(),
      sort_field: params.sort_field,
      sort_order: params.sort_order,
    });

    if (params.status) searchParams.append('status', params.status);
    if (params.analysis_type) searchParams.append('analysis_type', params.analysis_type);
    if (params.search) searchParams.append('search', params.search);

    return api.get<PaginatedResponse<RunSummary>>(`/runs?${searchParams.toString()}`);
  },

  getById: (id: string) =>
    api.get<{
      status: string;
      progress: number;
      results?: EquationResults | { pysr_explanations: string };
      error?: string;
      public_share_token?: string | null;
      start_time?: string | null;
      finish_time?: string | null;
      target_variable?: string | null;
    }>(`/runs/${id}`),

  getDetails: (id: string) => api.get<RunDetails>(`/runs/${id}/details`),

  create: (data: {
    problem_description: object;
    csv_filename: string;
    analysis_type: string;
    deep_research_model: string | null;
    user_api_keys?: UserApiKeys;
  }) => api.post<{ run_id: string; progress_phases?: ProgressPhase[] }>('/run', data),

  downloadCsv: (id: string) => api.get(`/runs/${id}/download-csv`, { responseType: 'blob' }),

  delete: (id: string) => api.delete<{ message: string }>(`/runs/${id}`),

  cancel: (id: string) => api.post<{ message: string }>(`/runs/${id}/cancel`),
};

// ============================================================================
// Upload Service
// ============================================================================

export const uploadService = {
  uploadFile: (file: File) => {
    const formData = new FormData();
    formData.append('file', file);
    return api.post<UploadResponse>('/upload', formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
    });
  },
};

// ============================================================================
// Config Service
// ============================================================================

export const configService = {
  getDeepResearchModels: () => api.get<{ models: string[] }>('/config/deep-research-models'),

  getUserApiModels: () => api.get<{ models: string[] }>('/config/user-api-models'),
};

// ============================================================================
// Profile Service
// ============================================================================

export const profileService = {
  get: () => api.get<ProfileData>('/profile'),
  delete: () => api.delete('/profile'),
};

// ============================================================================
// Sharing Service
// ============================================================================

export interface ShareResponse {
  share_token: string;
  share_url: string;
}

export interface SharedRunInfo {
  id: string;
  target_variable: string | null;
  csv_filename: string;
  analysis_type: string;
  created_at: string | null;
  share_token: string;
  share_url: string;
}

export const sharingService = {
  createShareLink: (runId: string) => api.post<ShareResponse>(`/runs/${runId}/share`),

  revokeShareLink: (runId: string) => api.delete(`/runs/${runId}/share`),

  getSharedRuns: () => api.get<{ items: SharedRunInfo[] }>('/runs/shared'),
};

// ============================================================================
// Public Service (No Auth)
// ============================================================================

// Create a separate axios instance for public endpoints (no auth token)
const publicApi = axios.create({
  baseURL: '/api',
});

export interface PublicRunData {
  status: string;
  progress: number;
  results: EquationResults | { pysr_explanations: string } | null;
  share_token: string;
  target_variable?: string | null;
}

export const publicService = {
  getResults: (token: string) => publicApi.get<PublicRunData>(`/public/${token}`),

  getDetails: (token: string) => publicApi.get<RunDetails>(`/public/${token}/details`),

  downloadCsv: (token: string) =>
    publicApi.get(`/public/${token}/download-csv`, { responseType: 'blob' }),
};

// ============================================================================
// API Keys Service
// ============================================================================

export const apiKeysService = {
  get: () => api.get<ApiKey | null>('/api-keys'),

  generate: () => api.post<CreateApiKeyResponse>('/api-keys'),

  revoke: () => api.delete<{ message: string }>('/api-keys'),

  regenerate: () => api.post<CreateApiKeyResponse>('/api-keys/regenerate'),
};

// ============================================================================
// Permission Service
// ============================================================================

export const permissionsService = {
  getMyPermissions: () => api.get<UserPermissions>('/permissions/me'),

  validateKeys: (data: { gemini_api_key?: string; openai_api_key?: string }) =>
    api.post<{ valid: boolean }>('/validate-keys', data),
};

// ============================================================================
// Suggestions Service
// ============================================================================

export interface SuggestDescriptionsResponse {
  descriptions: Record<string, string>;
  failed_columns: string[];
  model: string;
}

export const suggestionsService = {
  suggestDescriptions: (
    data: {
      project_description: string;
      target_variable?: string;
      columns: string[];
      gemini_api_key?: string;
      gemini_model?: string;
    },
    signal?: AbortSignal
  ) => api.post<SuggestDescriptionsResponse>('/suggest-descriptions', data, { signal }),
};

// ============================================================================
// Admin Service
// ============================================================================

export interface AdminRunsParams {
  page: number;
  page_size: number;
  sort_field?: string;
  sort_order?: 'asc' | 'desc';
  status?: string;
  analysis_type?: string;
  user_id?: string;
  search?: string;
  date_from?: string;
  date_to?: string;
}

export interface AuditLogsParams {
  page: number;
  page_size: number;
  action?: string;
  admin_email?: string;
  target_type?: string;
  date_from?: string;
  date_to?: string;
}

export const adminService = {
  // Dashboard
  getDashboardStats: () => api.get<DashboardStats>('/admin/dashboard/stats'),

  getRunTrends: (days: number = 30) =>
    api.get<{ items: RunTrendItem[] }>(`/admin/dashboard/trends?days=${days}`),

  getStatusDistribution: () =>
    api.get<{ items: StatusDistributionItem[] }>('/admin/dashboard/status-distribution'),

  getRecentActivity: (limit: number = 10) =>
    api.get<{ items: ActivityItem[] }>(`/admin/dashboard/recent-activity?limit=${limit}`),

  // Run Management
  getAllRuns: (params: AdminRunsParams) => {
    const searchParams = new URLSearchParams({
      page: params.page.toString(),
      page_size: params.page_size.toString(),
    });
    if (params.sort_field) searchParams.append('sort_field', params.sort_field);
    if (params.sort_order) searchParams.append('sort_order', params.sort_order);
    if (params.status) searchParams.append('status', params.status);
    if (params.analysis_type) searchParams.append('analysis_type', params.analysis_type);
    if (params.user_id) searchParams.append('user_id', params.user_id);
    if (params.search) searchParams.append('search', params.search);
    if (params.date_from) searchParams.append('date_from', params.date_from);
    if (params.date_to) searchParams.append('date_to', params.date_to);
    return api.get<PaginatedResponse<AdminRunSummary>>(`/admin/runs?${searchParams.toString()}`);
  },

  getRunDetail: (runId: string) => api.get<AdminRunDetail>(`/admin/runs/${runId}`),

  cancelRun: (runId: string) => api.post<AdminRunActionResponse>(`/admin/runs/${runId}/cancel`),

  deleteRun: (runId: string) => api.delete<AdminRunActionResponse>(`/admin/runs/${runId}`),

  downloadRunFile: (runId: string) =>
    api.get<Blob>(`/admin/runs/${runId}/download-csv`, { responseType: 'blob' }),

  // System Monitoring
  getSystemHealth: () => api.get<SystemHealth>('/admin/system/health'),

  getSlurmStatus: () => api.get<SlurmStatus>('/admin/system/slurm'),

  // Error Monitoring
  getFailedRuns: (page: number = 1, pageSize: number = 10, days: number = 30) =>
    api.get<PaginatedResponse<AdminRunSummary>>(
      `/admin/errors/runs?page=${page}&page_size=${pageSize}&days=${days}`
    ),

  getErrorDistribution: (days: number = 30) =>
    api.get<{ items: ErrorDistributionItem[] }>(`/admin/errors/distribution?days=${days}`),

  getErrorTrend: (days: number = 30) =>
    api.get<{ items: ErrorTrendItem[] }>(`/admin/errors/trend?days=${days}`),

  // Audit Logs
  getAuditLogs: (params: AuditLogsParams) => {
    const searchParams = new URLSearchParams({
      page: params.page.toString(),
      page_size: params.page_size.toString(),
    });
    if (params.action) searchParams.append('action', params.action);
    if (params.admin_email) searchParams.append('admin_email', params.admin_email);
    if (params.target_type) searchParams.append('target_type', params.target_type);
    if (params.date_from) searchParams.append('date_from', params.date_from);
    if (params.date_to) searchParams.append('date_to', params.date_to);
    return api.get<PaginatedResponse<AuditLogEntry>>(
      `/admin/audit-logs?${searchParams.toString()}`
    );
  },

  getAuditFilterOptions: () => api.get<AuditFilterOptions>('/admin/audit-logs/filters'),

  // Analytics
  getUserGrowth: (days: number = 90) =>
    api.get<{ items: UserGrowthItem[] }>(`/admin/analytics/users/growth?days=${days}`),

  getTopUsers: (limit: number = 10, periodDays: number = 30) =>
    api.get<{ items: TopUserItem[] }>(
      `/admin/analytics/users/top?limit=${limit}&period_days=${periodDays}`
    ),

  getPerformanceStats: () => api.get<PerformanceStats>('/admin/analytics/performance'),

  getPerformanceByType: () =>
    api.get<{ items: PerformanceByTypeItem[] }>('/admin/analytics/performance/by-type'),

  // Configuration
  getConfig: () => api.get<SystemConfig>('/admin/config'),
};

// ============================================================================
// Feedback Service
// ============================================================================

export const feedbackService = {
  submit: (data: FeedbackRequest) => api.post<FeedbackResponse>('/feedback', data),
};

// Default export for backwards compatibility
export default api;
