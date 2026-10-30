/**
 * Hook for automatic column description suggestions.
 *
 * Wraps the suggest-descriptions endpoint with abort handling so that
 * re-triggers cancel the in-flight request and stale responses are dropped.
 */

import { useCallback, useEffect, useRef, useState } from 'react';
import axios from 'axios';
import { suggestionsService } from '@services/api';
import type { SuggestionPayload } from '@/types';

export type SuggestionStatus = 'idle' | 'loading' | 'partial' | 'error';

export interface UseDescriptionSuggestionsOptions {
  onDescriptions: (descriptions: Record<string, string>) => void;
}

export interface UseDescriptionSuggestionsResult {
  status: SuggestionStatus;
  failedColumns: string[];
  errorMessage: string;
  requestSuggestions: (payload: SuggestionPayload) => void;
}

export function useDescriptionSuggestions({
  onDescriptions,
}: UseDescriptionSuggestionsOptions): UseDescriptionSuggestionsResult {
  const [status, setStatus] = useState<SuggestionStatus>('idle');
  const [failedColumns, setFailedColumns] = useState<string[]>([]);
  const [errorMessage, setErrorMessage] = useState('');

  const abortRef = useRef<AbortController | null>(null);
  const requestIdRef = useRef(0);
  const onDescriptionsRef = useRef(onDescriptions);
  onDescriptionsRef.current = onDescriptions;

  useEffect(() => {
    return () => abortRef.current?.abort();
  }, []);

  const requestSuggestions = useCallback((payload: SuggestionPayload) => {
    abortRef.current?.abort();
    const controller = new AbortController();
    abortRef.current = controller;
    const requestId = ++requestIdRef.current;

    setStatus('loading');
    setFailedColumns([]);
    setErrorMessage('');

    suggestionsService
      .suggestDescriptions(payload, controller.signal)
      .then((response) => {
        if (requestId !== requestIdRef.current) return;
        const { descriptions, failed_columns } = response.data;
        onDescriptionsRef.current(descriptions);
        setFailedColumns(failed_columns);
        setStatus(failed_columns.length > 0 ? 'partial' : 'idle');
      })
      .catch((error) => {
        if (requestId !== requestIdRef.current) return;
        if (axios.isCancel(error)) return;
        setErrorMessage(
          axios.isAxiosError(error) && error.response?.data?.detail
            ? String(error.response.data.detail)
            : 'Could not generate suggestions. Please try again.'
        );
        setStatus('error');
      });
  }, []);

  return { status, failedColumns, errorMessage, requestSuggestions };
}
