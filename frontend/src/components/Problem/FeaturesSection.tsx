/**
 * FeaturesSection Component
 * Card for entering feature descriptions
 */

import React from 'react';
import { InputTextarea } from 'primereact/inputtextarea';
import HelpButton from '@components/HelpButton';

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
  <div className="bg-surface p-6 rounded-xl border border-[var(--color-border)] shadow-sm h-full">
    <div className="flex items-start gap-3 mb-4">
      <i className="pi pi-list text-muted text-lg mt-1 shrink-0"></i>
      <div>
        <div className="flex items-center gap-2">
          <h3 className="text-lg font-heading font-bold text-primary">Features</h3>
          <HelpButton title="Feature Descriptions">
            <h4>Why provide descriptions?</h4>
            <p>
              Feature descriptions help the AI understand the <strong>scientific meaning</strong> of
              each column in your data. This enables more accurate and interpretable equation
              explanations.
            </p>

            <h4>Writing Good Descriptions</h4>
            <ul>
              <li>
                Include the <strong>physical units</strong> (e.g., "mg/kg", "°C", "m/s")
              </li>
              <li>
                Describe what the feature <strong>measures or represents</strong>
              </li>
              <li>
                Mention any <strong>measurement methods</strong> if relevant
              </li>
            </ul>

            <h4>Examples</h4>
            <ul>
              <li>
                <code>pH</code> → "Soil pH measured in water suspension, unitless scale 0-14"
              </li>
              <li>
                <code>temp</code> → "Air temperature in degrees Celsius at 2m height"
              </li>
              <li>
                <code>N_content</code> → "Total nitrogen content in mg/kg of soil"
              </li>
            </ul>
          </HelpButton>
        </div>
        <p className="text-sm text-secondary">Describe your data columns.</p>
      </div>
    </div>

    <div className="space-y-3 max-h-[400px] overflow-y-auto pr-2 custom-scrollbar">
      {columns.map(
        (col) =>
          col !== targetVariable && (
            <div
              key={col}
              className="flex flex-col sm:flex-row sm:items-start space-y-2 sm:space-y-0 sm:space-x-4 p-3 bg-surface-alt rounded-lg border border-[var(--color-border)] hover:border-blue-200 transition-colors"
            >
              <div className="w-full sm:w-1/3 flex items-center sm:self-center">
                <div className="bg-surface-alt p-2 rounded-lg mr-3 flex-shrink-0 w-8 h-8 flex items-center justify-center">
                  <i className="pi pi-database text-muted text-sm"></i>
                </div>
                <span
                  className="text-sm font-mono font-semibold text-secondary truncate"
                  title={col}
                >
                  {col}
                </span>
              </div>
              <div className="w-full sm:w-2/3">
                <InputTextarea
                  className="w-full p-inputtext-sm bg-surface border-[var(--color-border)] resize-none"
                  placeholder={`Description for ${col}`}
                  value={featureDescriptions[col] || ''}
                  onChange={(e) => onChange({ ...featureDescriptions, [col]: e.target.value })}
                  rows={2}
                />
              </div>
            </div>
          )
      )}
    </div>
  </div>
);

export default FeaturesSection;
