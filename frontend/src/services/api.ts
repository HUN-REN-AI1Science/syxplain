/**
 * API Service Layer
 * Typed API methods with proper request/response handling
 */

import axios, { AxiosInstance } from 'axios';
import { supabase } from '../supabaseClient';
import type {
  PaginatedResponse,
  RunSummary,
  RunDetails,
  UploadResponse,
  ProfileData,
  ProgressPhase,
} from '../types';

// ============================================================================
// Base API Instance
// ============================================================================

const api: AxiosInstance = axios.create({
  baseURL: '/api',
});

// Add request interceptor to inject auth token
api.interceptors.request.use(async (config) => {
  const { data: { session } } = await supabase.auth.getSession();

  if (session?.access_token) {
    config.headers.Authorization = `Bearer ${session.access_token}`;
  }

  return config;
});

// Add response interceptor for 401 handling
api.interceptors.response.use(
  (response) => response,
  async (error) => {
    if (error.response?.status === 401) {
      await supabase.auth.signOut();
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
    api.get<{ status: string; progress: number; results?: { pysr_explanations: string }; error?: string }>(`/runs/${id}`),

  getDetails: (id: string) =>
    api.get<RunDetails>(`/runs/${id}/details`),

  create: (data: { problem_description: object; csv_filename: string; analysis_type: string; deep_research_model: string | null }) =>
    api.post<{ run_id: string }>('/run', data),

  downloadCsv: (id: string) =>
    api.get(`/runs/${id}/download-csv`, { responseType: 'blob' }),
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
  getProgressConfig: () =>
    api.get<{ phases: ProgressPhase[] }>('/progress-config'),

  getDeepResearchModels: () =>
    api.get<{ models: string[] }>('/config/deep-research-models'),
};

// ============================================================================
// Profile Service
// ============================================================================

export const profileService = {
  get: () => api.get<ProfileData>('/profile'),
  delete: () => api.delete('/profile'),
};

// Default export for backwards compatibility
export default api;
