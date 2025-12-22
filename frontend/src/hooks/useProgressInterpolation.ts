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
  const {
    phases = [],
    backendProgress,
    status,
    updateInterval = 500,
  } = options;

  const [displayProgress, setDisplayProgress] = useState(0);
  const phasesRef = useRef(phases);

  // Update phases ref
  useEffect(() => {
    phasesRef.current = phases;
  }, [phases]);

  // Compute current step description based on backend progress
  const { currentStepDescription, currentStepLabel } = useMemo(() => {
    if (status === 'completed') {
      return {
        currentStepDescription: 'Analysis complete!',
        currentStepLabel: 'Complete'
      };
    }
    if (status === 'failed' || status === 'timeout') {
      return {
        currentStepDescription: 'Analysis stopped',
        currentStepLabel: status === 'timeout' ? 'Timeout' : 'Failed'
      };
    }
    if (phases.length === 0) {
      return {
        currentStepDescription: 'Processing...',
        currentStepLabel: 'Processing'
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
      currentStepLabel: 'Finalizing'
    };
  }, [backendProgress, phases, status]);

  useEffect(() => {
    // If completed, show 100%
    if (status === 'completed') {
      setDisplayProgress(100);
      return;
    }

    // If failed or timeout, show current backend progress
    if (status === 'failed' || status === 'timeout') {
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

        // If we've reached the max for current phase, hold there
        if (current >= maxProgress) {
          return current;
        }

        // Normal slow increment towards max
        return Math.min(current + incrementRate, maxProgress);
      });
    }, updateInterval);

    return () => clearInterval(intervalId);
  }, [backendProgress, status, updateInterval]);

  return { displayProgress, currentStepDescription, currentStepLabel };
}

