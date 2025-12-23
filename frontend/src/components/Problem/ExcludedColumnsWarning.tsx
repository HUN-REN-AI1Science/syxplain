/**
 * ExcludedColumnsWarning Component
 * Displays warning about automatically excluded non-numeric columns
 */

import React from 'react';

interface ExcludedColumnsWarningProps {
  excludedColumns: string[];
}

export const ExcludedColumnsWarning: React.FC<ExcludedColumnsWarningProps> = ({
  excludedColumns,
}) => {
  if (!excludedColumns || excludedColumns.length === 0) return null;

  return (
    <div className="mb-6 animate-fade-in">
      <div className="bg-yellow-50 border border-yellow-200 rounded-lg p-4 flex items-start">
        <i className="pi pi-exclamation-triangle text-yellow-600 text-xl mr-3 mt-0.5"></i>
        <div>
          <h4 className="font-semibold text-yellow-800 text-sm">Columns Excluded</h4>
          <p className="text-sm text-yellow-700 mt-1">
            The following columns were automatically excluded because they contain non-numeric data:
            <span className="font-mono ml-1 font-medium">{excludedColumns.join(', ')}</span>
          </p>
        </div>
      </div>
    </div>
  );
};

export default ExcludedColumnsWarning;
