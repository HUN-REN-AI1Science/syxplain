/**
 * FeaturesSection Component
 * Card for entering feature descriptions
 */

import React from 'react';
import { InputTextarea } from 'primereact/inputtextarea';

interface FeaturesSectionProps {
  columns: string[];
  targetVariable: string;
  featureDescriptions: Record<string, string>;
  onChange: (descriptions: Record<string, string>) => void;
}

export const FeaturesSection: React.FC<FeaturesSectionProps> = ({
  columns,
  targetVariable,
  featureDescriptions,
  onChange,
}) => (
  <div className="bg-white p-6 rounded-xl border border-slate-200 shadow-sm h-full">
    <div className="flex items-center mb-4">
      <div className="bg-purple-100 p-2 rounded-lg mr-3 flex-shrink-0">
        <i className="pi pi-list text-purple-600 text-lg"></i>
      </div>
      <div>
        <h3 className="text-lg font-bold text-slate-800">Features</h3>
        <p className="text-sm text-slate-500">Describe your data columns.</p>
      </div>
    </div>

    <div className="space-y-3 max-h-[400px] overflow-y-auto pr-2 custom-scrollbar">
      {columns.map(col => (
        col !== targetVariable && (
          <div key={col} className="flex flex-col sm:flex-row sm:items-start space-y-2 sm:space-y-0 sm:space-x-4 p-3 bg-slate-50 rounded-lg border border-slate-100 hover:border-blue-200 transition-colors">
            <div className="w-full sm:w-1/3 flex items-center sm:self-center">
              <div className="bg-slate-100 p-2 rounded-lg mr-3 flex-shrink-0 w-8 h-8 flex items-center justify-center">
                <i className="pi pi-database text-slate-400 text-sm"></i>
              </div>
              <span className="text-sm font-mono font-semibold text-slate-700 truncate" title={col}>{col}</span>
            </div>
            <div className="w-full sm:w-2/3">
              <InputTextarea
                className="w-full p-inputtext-sm bg-white border-slate-200 resize-none"
                placeholder={`Description for ${col}`}
                value={featureDescriptions[col] || ''}
                onChange={(e) => onChange({ ...featureDescriptions, [col]: e.target.value })}
                rows={2}
              />
            </div>
          </div>
        )
      ))}
    </div>
  </div>
);

export default FeaturesSection;
