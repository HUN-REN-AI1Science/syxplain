/**
 * AnalysisTypeSelector Component
 * Analysis type selection with deep research model picker
 */

import React, { useRef } from 'react';
import { Button } from 'primereact/button';
import { Menu } from 'primereact/menu';
import { Dropdown, type DropdownChangeEvent } from 'primereact/dropdown';
import HelpButton from '@components/HelpButton';

interface AnalysisTypeSelectorProps {
  analysisType: 'quick' | 'deep';
  onAnalysisTypeChange: (type: 'quick' | 'deep') => void;
  deepResearchModels: string[];
  selectedDeepModel: string | null;
  onDeepModelChange: (model: string) => void;
  onSubmit: () => void;
  onExportJson?: () => void;
  disabled: boolean;
  showExportButton: boolean;
  hasHunrenAccess?: boolean;
}

export const AnalysisTypeSelector: React.FC<AnalysisTypeSelectorProps> = ({
  analysisType,
  onAnalysisTypeChange,
  deepResearchModels,
  selectedDeepModel,
  onDeepModelChange,
  onSubmit,
  onExportJson,
  disabled,
  showExportButton,
  hasHunrenAccess = true,
}) => {
  const analysisMenuRef = useRef<Menu>(null);

  return (
    <>
      {/* Help button row - right aligned above buttons */}
      <div className="mt-2 flex justify-end">
        <HelpButton title="Analysis Types">
          <h4>Quick Analysis</h4>
          <p>
            <strong>Fast and cost-effective.</strong> Uses web searches for background research.
            Ideal for initial exploration or when you need rapid results.
          </p>
          <ul>
            <li>Faster processing time</li>
            <li>Lower computational cost</li>
            <li>Basic literature context</li>
          </ul>

          <h4>Deep Analysis</h4>
          <p>
            <strong>Comprehensive and thorough.</strong> Performs extensive scientific literature
            research to validate discovered formulas against existing knowledge.
          </p>
          <ul>
            <li>In-depth literature review</li>
            <li>Higher accuracy validation</li>
            <li>More detailed scientific context</li>
            <li>Higher computational cost</li>
          </ul>

          <h4>Which should I choose?</h4>
          <p>
            Start with <strong>Quick Analysis</strong> for initial exploration. Use{' '}
            <strong>Deep Analysis</strong> when you need publication-quality results with thorough
            scientific validation.
          </p>
        </HelpButton>
      </div>

      {/* Button row */}
      <div className="mt-2 flex justify-end items-center space-x-4">
        {showExportButton && onExportJson && (
          <Button
            label="Export JSON"
            icon="pi pi-download"
            onClick={onExportJson}
            className="p-button-outlined p-button-secondary font-bold py-3 px-6 text-xl"
          />
        )}

        {/* Analysis Menu */}
        <Menu
          ref={analysisMenuRef}
          popup
          model={[
            {
              label: 'Quick Analysis',
              icon: 'pi pi-bolt',
              command: () => onAnalysisTypeChange('quick'),
              className: analysisType === 'quick' ? 'bg-blue-50' : '',
            },
            {
              label: 'Deep Analysis',
              icon: 'pi pi-search',
              command: () => onAnalysisTypeChange('deep'),
              className: analysisType === 'deep' ? 'bg-blue-50' : '',
            },
          ]}
        />

        {/* Split Button for Analysis Type Selection */}
        <div className="flex">
          <Button
            label={analysisType === 'quick' ? 'Quick Analysis' : 'Deep Analysis'}
            icon={analysisType === 'quick' ? 'pi pi-bolt' : 'pi pi-search'}
            iconPos="left"
            onClick={onSubmit}
            size="large"
            disabled={disabled}
            className={`font-bold py-3 px-6 text-xl shadow-lg transition-all rounded-r-none ${
              disabled
                ? 'bg-slate-300 border-slate-300 text-slate-500 cursor-not-allowed'
                : 'bg-blue-500 hover:bg-blue-600 border-blue-500 text-white hover:shadow-xl'
            }`}
          />
          <Button
            icon="pi pi-chevron-down"
            onClick={(e) => analysisMenuRef.current?.toggle(e)}
            size="large"
            disabled={disabled}
            className={`font-bold py-3 px-3 text-xl shadow-lg transition-all rounded-l-none border-l-0 ${
              disabled
                ? 'bg-slate-300 border-slate-300 text-slate-500 cursor-not-allowed'
                : 'bg-blue-600 hover:bg-blue-700 border-blue-500 text-white'
            }`}
          />
        </div>
      </div>

      {/* Deep Analysis Settings - shown when deep analysis is selected */}
      {analysisType === 'deep' && (
        <div className="mt-4 animate-fade-in">
          {/* Deep Research Model Selection - only shown for HUN-REN access users */}
          {hasHunrenAccess && (
            <div className="mb-4 flex flex-col items-end">
              <Dropdown
                value={selectedDeepModel}
                onChange={(e: DropdownChangeEvent) => onDeepModelChange(e.value)}
                options={deepResearchModels.map((model) => ({ label: model, value: model }))}
                placeholder="Select a model..."
                className="w-auto min-w-[200px] bg-slate-50"
                disabled={deepResearchModels.length === 0}
              />
              {deepResearchModels.length === 0 && (
                <p className="text-xs text-red-600 mt-2 w-full md:w-80 text-left">
                  <i className="pi pi-exclamation-circle mr-1"></i>
                  No deep research models configured. Contact administrator.
                </p>
              )}
            </div>
          )}

          {/* Warning - only shown for HUN-REN users, changes to danger for o3-deep-research */}
          {hasHunrenAccess && (
            <div
              className={`rounded-lg p-4 flex items-start ${
                selectedDeepModel === 'o3-deep-research'
                  ? 'bg-red-50 border border-red-200'
                  : 'bg-amber-50 border border-amber-200'
              }`}
            >
              <i
                className={`pi pi-exclamation-triangle text-xl mr-3 mt-0.5 ${
                  selectedDeepModel === 'o3-deep-research' ? 'text-red-600' : 'text-amber-600'
                }`}
              ></i>
              <div>
                <h4
                  className={`font-semibold text-sm ${
                    selectedDeepModel === 'o3-deep-research' ? 'text-red-800' : 'text-amber-800'
                  }`}
                >
                  {selectedDeepModel === 'o3-deep-research'
                    ? 'High Cost Warning'
                    : 'Deep Analysis Notice'}
                </h4>
                <p
                  className={`text-sm mt-1 ${
                    selectedDeepModel === 'o3-deep-research' ? 'text-red-700' : 'text-amber-700'
                  }`}
                >
                  {selectedDeepModel === 'o3-deep-research' ? (
                    <>
                      <strong>This model has the highest cost.</strong> Only run if you know what
                      you are doing and are sure about it. Deep Analysis performs additional
                      scientific literature research which is expensive.
                    </>
                  ) : (
                    <>
                      Deep Analysis is more expensive to run as it performs additional scientific
                      literature research. This system is currently in{' '}
                      <strong>experimental mode</strong> and is open for use, but this feature may
                      be behind a paywall in the future.
                    </>
                  )}
                </p>
              </div>
            </div>
          )}
        </div>
      )}
    </>
  );
};

export default AnalysisTypeSelector;
