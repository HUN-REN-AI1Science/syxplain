/**
 * AnalysisProgressView Component
 * Displays analysis progress with animated progress bar and step descriptions
 * Enhanced with rotating messages during HPC queue phase
 */

import React, { useState, useEffect } from 'react';
import { ProgressBar } from 'primereact/progressbar';
import { AnalysisTipsPanel } from './AnalysisTipsPanel';

// Friendly messages shown during queue phase
const QUEUE_MESSAGES = [
  'Your analysis is in the queue...',
  'Waiting for computing resources...',
  'Almost ready to start...',
  'Preparing your analysis environment...',
];

const CONNECTING_MESSAGES = [
  'Connecting to the computing cluster...',
  'Setting up your analysis...',
];

interface AnalysisProgressViewProps {
  /** Current progress percentage (0-100) */
  displayProgress: number;
  /** Current step description */
  stepDescription: string;
  /** Whether we're in the early queue phase */
  isInQueuePhase?: boolean;
}

export const AnalysisProgressView: React.FC<AnalysisProgressViewProps> = ({
  displayProgress,
  stepDescription,
  isInQueuePhase = false,
}) => {
  const [messageIndex, setMessageIndex] = useState(0);
  const [messageKey, setMessageKey] = useState(0);

  // Determine which message set to use
  const isConnecting = displayProgress < 1;
  const messages = isConnecting ? CONNECTING_MESSAGES : QUEUE_MESSAGES;

  // Rotate messages during queue phase
  useEffect(() => {
    if (!isInQueuePhase) return;

    const interval = setInterval(() => {
      setMessageIndex((prev) => (prev + 1) % messages.length);
      setMessageKey((prev) => prev + 1);
    }, 6000);

    return () => clearInterval(interval);
  }, [isInQueuePhase, messages.length]);

  // Get the appropriate message/description
  const displayMessage = isInQueuePhase ? messages[messageIndex] : stepDescription;

  // Get the appropriate heading
  const heading = isInQueuePhase ? 'Your analysis is queued' : 'AI is analyzing your data';

  // Get the appropriate subtext
  const subtext = isInQueuePhase
    ? 'Your analysis will start as soon as computing resources become available.'
    : 'This process involves symbolic regression and LLM reasoning. It might take a few minutes depending on the dataset size.';

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

      {/* Animated Step Description / Queue Message */}
      <div className="h-8 mb-4">
        <p
          key={isInQueuePhase ? messageKey : stepDescription}
          className={`text-base font-medium text-slate-400 ${isInQueuePhase ? 'message-animate' : 'step-description-animate'}`}
        >
          {displayMessage}
        </p>
      </div>

      {/* Subtle Separator */}
      <hr className="max-w-md mx-auto border-slate-200 mb-6" />

      <h3 className="text-xl font-semibold text-slate-800 mt-4 mb-2">
        {heading}
        {isInQueuePhase && <span className="queue-pulse ml-2 text-blue-500">...</span>}
      </h3>
      <p className="text-slate-500 max-w-md mx-auto mb-4">{subtext}</p>
      <p className="text-slate-600 text-sm max-w-md mx-auto">
        You can safely leave this page. Your results will be available in the{' '}
        <span className="font-semibold">History</span> menu once completed.
      </p>

      {/* Tips panel shown during queue phase */}
      <AnalysisTipsPanel visible={isInQueuePhase} />
    </div>
  );
};

export default AnalysisProgressView;
