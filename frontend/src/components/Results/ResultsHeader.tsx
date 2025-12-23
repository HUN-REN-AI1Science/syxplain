/**
 * ResultsHeader Component
 * Unified header for results views with status indicators and action buttons
 */

import React from 'react';
import { Message } from 'primereact/message';

export type ResultsStatus = 'loading' | 'processing' | 'completed' | 'failed';

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
    <div className="flex flex-col md:flex-row justify-between items-start md:items-center mb-6 pb-4 border-b border-slate-100 gap-4">
      <div>
        <h2 className="text-xl font-bold text-slate-800">{title}</h2>
        {subtitle && (
          <p className="text-sm text-slate-500">
            {subtitle}
          </p>
        )}
      </div>

      <div className="flex items-center space-x-3 w-full md:w-auto">
        {actions}
        <Message severity={statusConfig.severity} text={statusConfig.text} className="w-full md:w-auto" />
      </div>
    </div>
  );
};

export default ResultsHeader;
