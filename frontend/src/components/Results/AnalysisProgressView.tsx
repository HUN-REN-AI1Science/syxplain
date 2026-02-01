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
}

export const AnalysisProgressView: React.FC<AnalysisProgressViewProps> = ({
  displayProgress,
  stepDescription,
}) => (
  <div className="text-center py-20">
    <div className="max-w-md mx-auto mb-6">
      <ProgressBar
        value={displayProgress}
        showValue={false}
        style={{ height: '8px' }}
        className="mb-2"
      />
      <p className="text-lg font-semibold text-blue-600">{Math.floor(displayProgress)}% complete</p>
    </div>

    {/* Animated Step Description */}
    <div className="h-8 mb-4">
      <p
        key={stepDescription}
        className="step-description-animate text-base font-medium text-slate-400"
      >
        {stepDescription}
      </p>
    </div>

    {/* Subtle Separator */}
    <hr className="max-w-md mx-auto border-slate-200 mb-6" />

    <h3 className="text-xl font-semibold text-slate-800 mt-4 mb-2">AI is analyzing your data</h3>
    <p className="text-slate-500 max-w-md mx-auto mb-4">
      This process involves symbolic regression and LLM reasoning. It might take a few minutes
      depending on the dataset size.
    </p>
    <p className="text-slate-600 text-sm max-w-md mx-auto">
      You can safely leave this page. Your results will be available in the{' '}
      <span className="font-semibold">History</span> menu once completed.
    </p>
  </div>
);

export default AnalysisProgressView;
