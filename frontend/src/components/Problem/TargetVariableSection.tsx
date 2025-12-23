/**
 * TargetVariableSection Component
 * Card for selecting target variable with NaN warning
 */

import React from 'react';
import { Dropdown } from 'primereact/dropdown';

interface TargetVariableSectionProps {
  columns: string[];
  targetVariable: string;
  nanCounts?: Record<string, number>;
  onChange: (value: string) => void;
}

export const TargetVariableSection: React.FC<TargetVariableSectionProps> = ({
  columns,
  targetVariable,
  nanCounts,
  onChange,
}) => (
  <div className="bg-white p-6 rounded-xl border border-slate-200 shadow-sm h-full">
    <div className="flex items-center mb-4">
      <div className="bg-green-100 p-2 rounded-lg mr-3 flex-shrink-0">
        <i className="pi pi-compass text-green-600 text-lg"></i>
      </div>
      <div>
        <h3 className="text-lg font-bold text-slate-800">Target</h3>
        <p className="text-sm text-slate-500">What to predict?</p>
      </div>
    </div>

    <div className="mt-4">
      <label className="block text-sm font-semibold text-slate-700 mb-2">Target Variable</label>
      <Dropdown
        value={targetVariable}
        onChange={(e: any) => onChange(e.value)}
        options={columns.map(col => ({ label: col, value: col }))}
        placeholder="Select Target..."
        className="w-full bg-slate-50 border-slate-200"
      />
      {targetVariable && nanCounts && nanCounts[targetVariable] > 0 && (
        <div className="mt-3 bg-red-50 border border-red-200 rounded-lg p-3 flex items-start animate-fade-in">
          <i className="pi pi-exclamation-circle text-red-500 mr-2 mt-0.5"></i>
          <div className="text-sm text-red-700">
            <strong>Warning:</strong> This column contains missing values.
            Analysis cannot proceed with a target containing missing data.
          </div>
        </div>
      )}
    </div>
  </div>
);

export default TargetVariableSection;
