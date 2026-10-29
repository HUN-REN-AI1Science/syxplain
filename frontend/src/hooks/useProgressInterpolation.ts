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
  /** Seconds spent in the current step (since this page saw it begin) */
  stepElapsedS: number;
  /** Typical duration of the current step in seconds, when known */
  stepExpectedS: number | null;
  /** Whether the analysis is in the early HPC queue phase */
  isInQueuePhase: boolean;
  /** Index of the running phase in `phases` (-1 before the first) */
  phaseIndex: number;
}

/** Share of a phase's span reached after `elapsed` seconds: ~86% at `expected`, never 100% */
const phaseFraction = (elapsedS: number, expectedS: number): number =>
  1 - Math.exp((-2 * elapsedS) / Math.max(expectedS, 1));

/** Index of the running phase: the last one whose start the backend has reached */
const phaseIndexAt = (phases: ProgressPhase[], progress: number): number => {
  let idx = -1;
  phases.forEach((p, i) => {
    if (progress >= p.progress_start) idx = i;
  });
  return idx;
};

/**
 * Hook for smoothly interpolating progress values.
 *
 * Each phase starts at its `progress_start` (set by the backend when the phase begins) and
 * the bar advances towards the next phase's start along the phase's typical duration, so the
 * bar's share of each step matches how long that step usually takes. Backend progress inside
 * a phase (the agent phase reports its own) is never undercut.
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
  const [stepElapsedS, setStepElapsedS] = useState(0);
  const phaseIndex = useMemo(
    () => phaseIndexAt(phases, backendProgress),
    [phases, backendProgress]
  );
  const phaseStartedAtRef = useRef<number>(Date.now());

  // A new phase restarts the step clock
  useEffect(() => {
    phaseStartedAtRef.current = Date.now();
    setStepElapsedS(0);
  }, [phaseIndex]);

  const currentPhase = phaseIndex >= 0 ? phases[phaseIndex] : null;

  // Compute current step description based on backend progress
  const currentStepDescription = useMemo(() => {
    if (status === 'completed') return 'Analysis complete!';
    if (status === 'failed' || status === 'timeout' || status === 'cancelled') {
      return status === 'cancelled' ? 'Analysis cancelled' : 'Analysis stopped';
    }
    if (!currentPhase) return 'Processing...';
    return currentPhase.description || currentPhase.label;
  }, [currentPhase, status]);

  useEffect(() => {
    if (status === 'completed') {
      setDisplayProgress(100);
      return;
    }
    if (status === 'failed' || status === 'timeout' || status === 'cancelled') {
      setDisplayProgress(backendProgress);
      return;
    }

    const target = (): number => {
      if (!currentPhase) {
        // Phases not loaded (e.g. page opened mid-run): creep a little past the backend
        return Math.min(backendProgress + 5, 98);
      }
      const next = phases[phaseIndex + 1];
      const end = (next ? next.progress_start : 99) - 0.5;
      const elapsedS = (Date.now() - phaseStartedAtRef.current) / 1000;
      const start = currentPhase.progress_start;
      const timed = start + (end - start) * phaseFraction(elapsedS, currentPhase.expected_s);
      return Math.min(Math.max(timed, backendProgress), end);
    };

    const intervalId = setInterval(() => {
      setStepElapsedS(Math.floor((Date.now() - phaseStartedAtRef.current) / 1000));
      setDisplayProgress((current) => {
        const goal = target();
        if (goal <= current) return current;
        // Ease towards the goal, so backend jumps animate instead of snapping
        return goal - current < 0.05 ? goal : current + (goal - current) * 0.25;
      });
    }, updateInterval);

    return () => clearInterval(intervalId);
  }, [backendProgress, status, updateInterval, phases, phaseIndex, currentPhase]);

  // Queue phase: only while backend hasn't started processing yet
  const isInQueuePhase = useMemo(() => {
    return status === 'pending';
  }, [status]);

  return {
    displayProgress,
    currentStepDescription,
    stepElapsedS,
    stepExpectedS: currentPhase?.expected_s ?? null,
    isInQueuePhase,
    phaseIndex,
  };
}
