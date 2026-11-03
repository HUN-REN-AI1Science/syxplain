/**
 * ResultsHeader Component
 * Unified header for results views with status indicators and action buttons
 */

import React from 'react';
import { Message } from 'primereact/message';
import HelpButton from '@components/HelpButton';

export type ResultsStatus = 'loading' | 'processing' | 'completed' | 'failed' | 'cancelled';

interface ResultsHeaderProps {
  /** Header title */
  title: string;
  /** Subtitle - can be string or React node for flexible content */
  subtitle?: string | React.ReactNode;
  /** Current status of the results */
  status: ResultsStatus;
  /** Optional custom status message */
  statusMessage?: string;
  /** Optional action buttons to display on the right */
  actions?: React.ReactNode;
}

const getStatusConfig = (status: ResultsStatus, statusMessage?: string) => {
  switch (status) {
    case 'loading':
      return { severity: 'info' as const, text: statusMessage || 'Loading Results...' };
    case 'processing':
      return { severity: 'info' as const, text: statusMessage || 'Processing Data...' };
    case 'completed':
      return { severity: 'success' as const, text: statusMessage || 'Completed' };
    case 'failed':
      return { severity: 'error' as const, text: statusMessage || 'Failed' };
    case 'cancelled':
      return { severity: 'warn' as const, text: statusMessage || 'Cancelled' };
  }
};

export const ResultsHeader: React.FC<ResultsHeaderProps> = ({
  title,
  subtitle,
  status,
  statusMessage,
  actions,
}) => {
  const statusConfig = getStatusConfig(status, statusMessage);

  return (
    <div className="flex flex-col md:flex-row justify-between items-start md:items-center mb-6 pb-4 border-b border-[var(--color-border)] gap-4">
      <div>
        <div className="flex items-center gap-2">
          <h2 className="font-heading text-xl font-bold text-primary">{title}</h2>
          <HelpButton title="Understanding Analysis Results">
            <h4>What's in the Results?</h4>
            <p>
              Your analysis includes discovered mathematical equations that explain the relationship
              between your features and target variable.
            </p>

            <h4>Key Sections</h4>
            <ul>
              <li>
                <strong>Analysis Summary</strong> - Key and secondary drivers identified from your
                data
              </li>
              <li>
                <strong>Recommended Equation</strong> - The simplest model that is as accurate as
                the best one (cross-validation), scored once on held-out rows
              </li>
              <li>
                <strong>Other equations</strong> - The other candidates, with their fit and plots
              </li>
              <li>
                <strong>Does the evidence agree?</strong> - Checks of the recommended equation
                against the noise ceiling, held-out rows, SHAP effects and known laws
              </li>
              <li>
                <strong>How the equations were found</strong> - The agent's work and the model
                leaderboard
              </li>
            </ul>

            <h4>Actions Available</h4>
            <ul>
              <li>
                <strong>Share</strong> - Create a public link to share your results
              </li>
              <li>
                <strong>Export PDF</strong> - Download a complete report
              </li>
              <li>
                <strong>Export Data</strong> - Download predicted values as CSV/Excel
              </li>
            </ul>
          </HelpButton>
        </div>
        {subtitle && <p className="text-sm text-secondary">{subtitle}</p>}
      </div>

      <div className="flex items-center space-x-3 w-full md:w-auto">
        {actions}
        <Message
          severity={statusConfig.severity}
          text={statusConfig.text}
          className="w-full md:w-auto"
        />
      </div>
    </div>
  );
};

export default ResultsHeader;
