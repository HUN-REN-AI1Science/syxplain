/**
 * AnalysisProgressView Component
 * Displays analysis progress with animated progress bar and step descriptions
 */

import React from 'react';
import { ProgressBar } from 'primereact/progressbar';

interface AnalysisProgressViewProps {
  /** Current progress percentage (0-100) */
  displayProgress: number;
  /** Current step description */
  stepDescription: string;
  /** Whether we're in the early queue phase */
  isInQueuePhase?: boolean;
  /** Whether the job has been submitted to compute cluster */
  isJobSubmitted?: boolean;
}

export const AnalysisProgressView: React.FC<AnalysisProgressViewProps> = ({
  displayProgress,
  stepDescription,
  isInQueuePhase = false,
  isJobSubmitted = false,
}) => {
  return (
    <div className="text-center py-20">
      <div className="max-w-md mx-auto mb-6">
        <ProgressBar
          value={displayProgress}
          showValue={false}
          style={{ height: '8px' }}
          className={`mb-2 ${isInQueuePhase ? 'progress-bar-shimmer' : ''}`}
        />
        <p className="text-lg font-semibold text-blue-600">{Math.floor(displayProgress)}% complete</p>
      </div>

      {/* Step Description */}
      <div className="h-8 mb-4">
        <p className="text-base font-medium text-slate-400">
          {stepDescription}
        </p>
      </div>

      {/* Subtle Separator */}
      <hr className="max-w-md mx-auto border-slate-200 mb-6" />

      <h3 className="text-xl font-semibold text-slate-800 mt-4 mb-2">
        AI is analyzing your data
        {isInQueuePhase && <span className="queue-pulse ml-2 text-blue-500">...</span>}
      </h3>
      <p className="text-slate-500 max-w-md mx-auto mb-4">
        Discovering mathematical equations and computing feature importance using symbolic regression.
      </p>

      {/* Only show "safe to leave" message when job is submitted to cluster */}
      {isJobSubmitted && (
        <p className="text-slate-600 text-sm max-w-md mx-auto">
          You can safely leave this page. Your results will be available in the{' '}
          <span className="font-semibold">History</span> menu once completed.
        </p>
      )}
    </div>
  );
};

export default AnalysisProgressView;
