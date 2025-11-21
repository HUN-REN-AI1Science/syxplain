import axios from 'axios';
import { supabase } from './supabaseClient';

const api = axios.create({
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
      // Token expired or invalid, sign out
      await supabase.auth.signOut();
    }
    return Promise.reject(error);
  }
);

export default api;
