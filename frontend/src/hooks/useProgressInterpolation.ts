/**
 * useProgressInterpolation Hook
 * Smoothly interpolates progress values for better UX
 */

import { useState, useEffect, useRef, useMemo } from 'react';
import type { ProgressPhase } from '@/types';

export interface UseProgressInterpolationOptions {
  /** Progress phases configuration */
  phases?: ProgressPhase[];
  /** Current backend progress (0-100) */
  backendProgress: number;
  /** Current status */
  status: string;
  /** Update interval in milliseconds */
  updateInterval?: number;
}

export interface UseProgressInterpolationResult {
  /** Smoothly interpolated display progress */
  displayProgress: number;
  /** Current step description based on backend progress */
  currentStepDescription: string;
  /** Current step label (shorter) */
  currentStepLabel: string;
  /** Whether the analysis is in the early HPC queue phase */
  isInQueuePhase: boolean;
}

/**
 * Hook for smoothly interpolating progress values
 * Creates a better UX by slowly incrementing progress between backend updates
 *
 * @example
 * const { displayProgress, currentStepDescription } = useProgressInterpolation({
 *   phases: progressPhases,
 *   backendProgress: 45,
 *   status: 'running',
 * });
 */
export function useProgressInterpolation(
  options: UseProgressInterpolationOptions
): UseProgressInterpolationResult {
  const { phases = [], backendProgress, status, updateInterval = 500 } = options;

  const [displayProgress, setDisplayProgress] = useState(0);
  const phasesRef = useRef(phases);
  const lastBackendUpdateRef = useRef<number>(Date.now());

  // Update phases ref
  useEffect(() => {
    phasesRef.current = phases;
  }, [phases]);

  // Track when backendProgress last changed
  useEffect(() => {
    lastBackendUpdateRef.current = Date.now();
  }, [backendProgress]);

  // Compute current step description based on backend progress
  const { currentStepDescription, currentStepLabel } = useMemo(() => {
    if (status === 'completed') {
      return {
        currentStepDescription: 'Analysis complete!',
        currentStepLabel: 'Complete',
      };
    }
    if (status === 'failed' || status === 'timeout' || status === 'cancelled') {
      return {
        currentStepDescription: status === 'cancelled' ? 'Analysis cancelled' : 'Analysis stopped',
        currentStepLabel: status === 'timeout' ? 'Timeout' : status === 'cancelled' ? 'Cancelled' : 'Failed',
      };
    }
    if (phases.length === 0) {
      return {
        currentStepDescription: 'Processing...',
        currentStepLabel: 'Processing',
      };
    }

    // Find the current phase based on backend progress
    // The current phase is the one whose progress_end we haven't reached yet
    let currentPhase: ProgressPhase | null = null;

    for (let i = 0; i < phases.length; i++) {
      if (backendProgress < phases[i].progress_end) {
        currentPhase = phases[i];
        break;
      }
      // If we've passed this phase's progress_end, continue to next
      currentPhase = phases[i];
    }

    if (currentPhase) {
      return {
        currentStepDescription: currentPhase.description || currentPhase.label,
        currentStepLabel: currentPhase.label,
      };
    }

    return {
      currentStepDescription: 'Finalizing...',
      currentStepLabel: 'Finalizing',
    };
  }, [backendProgress, phases, status]);

  useEffect(() => {
    // If completed, show 100%
    if (status === 'completed') {
      setDisplayProgress(100);
      return;
    }

    // If failed, timeout, or cancelled, show current backend progress
    if (status === 'failed' || status === 'timeout' || status === 'cancelled') {
      setDisplayProgress(backendProgress);
      return;
    }

    const getCurrentPhaseInfo = (backendProg: number) => {
      if (phasesRef.current.length === 0) {
        // Fallback defaults if config not loaded
        return { maxProgress: Math.min(backendProg + 5, 98), incrementRate: 0.2 };
      }

      // Find the phase that just ended (backend progress >= progress_end)
      let currentPhase: ProgressPhase | null = null;
      let nextPhase: ProgressPhase | null = null;

      for (let i = 0; i < phasesRef.current.length; i++) {
        if (backendProg >= phasesRef.current[i].progress_end) {
          currentPhase = phasesRef.current[i];
          nextPhase = phasesRef.current[i + 1] || null;
        }
      }

      // Max progress is the next phase's progress_end - 1, or 98 if at the end
      const maxProgress = nextPhase ? nextPhase.progress_end - 1 : 98;
      const incrementRate = currentPhase?.increment_rate || 0.2;

      return { maxProgress, incrementRate };
    };

    const intervalId = setInterval(() => {
      setDisplayProgress((current) => {
        const { maxProgress, incrementRate } = getCurrentPhaseInfo(backendProgress);

        // If backend jumped ahead significantly, catch up faster
        if (backendProgress > current + 5) {
          return Math.min(current + 2, backendProgress);
        }

        // If we've reached the max for current phase, creep slowly after a delay
        if (current >= maxProgress) {
          const timeSinceUpdate = Date.now() - lastBackendUpdateRef.current;
          if (timeSinceUpdate < 10_000) {
            return current; // Normal: hold at max for first 10s
          }
          // Slow creep: 0.02% per 500ms (~2.4%/min), capped at maxProgress + 5
          const creepCeiling = Math.min(maxProgress + 5, 98);
          if (current >= creepCeiling) return current;
          return Math.min(current + 0.02, creepCeiling);
        }

        // Normal slow increment towards max
        return Math.min(current + incrementRate, maxProgress);
      });
    }, updateInterval);

    return () => clearInterval(intervalId);
  }, [backendProgress, status, updateInterval]);

  // Determine if we're in the early HPC queue phase (progress < 5% and running)
  const isInQueuePhase = useMemo(() => {
    return backendProgress < 5 && status === 'running';
  }, [backendProgress, status]);

  return { displayProgress, currentStepDescription, currentStepLabel, isInQueuePhase };
}
