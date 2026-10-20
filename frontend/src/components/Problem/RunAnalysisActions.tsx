/**
 * RunAnalysisActions Component
 * Export JSON and Run Analysis buttons below the problem form
 */

import React from 'react';
import { Button } from 'primereact/button';
import { Tooltip } from 'primereact/tooltip';
import { useNavigation } from '@contexts/NavigationContext';

interface RunAnalysisActionsProps {
  onSubmit: () => void;
  onExportJson?: () => void;
  disabled: boolean;
  showExportButton: boolean;
}

export const RunAnalysisActions: React.FC<RunAnalysisActionsProps> = ({
  onSubmit,
  onExportJson,
  disabled,
  showExportButton,
}) => {
  const { navigateTo } = useNavigation();

  return (
    <div className="mt-4 flex justify-end items-center space-x-4">
      {showExportButton && onExportJson && (
        <>
          <Tooltip target=".btn-export-json" position="bottom" autoHide={false}>
            <span>
              Download the current problem configuration as a JSON file, so you can re-import it
              later.{' '}
              <button
                className="underline text-brand-300 hover:text-brand-200"
                onClick={() => navigateTo('help', 'export-json')}
              >
                Learn more
              </button>
            </span>
          </Tooltip>
          <Button
            label="Export JSON"
            icon="pi pi-download"
            onClick={onExportJson}
            className="btn-export-json p-button-outlined p-button-secondary font-bold py-3 px-6 text-xl"
          />
        </>
      )}

      <Tooltip target=".btn-run-analysis" position="bottom" autoHide={false}>
        <span>
          Discover symbolic equations from your data with the full Syxplain pipeline, including a
          literature search for relevant domain knowledge.{' '}
          <button
            className="underline text-brand-300 hover:text-brand-200"
            onClick={() => navigateTo('help', 'running-analysis')}
          >
            Learn more
          </button>
        </span>
      </Tooltip>
      <Button
        label="Run Analysis"
        icon="pi pi-play"
        iconPos="left"
        onClick={onSubmit}
        size="large"
        disabled={disabled}
        className={`btn-run-analysis font-bold py-3 px-6 text-xl shadow-lg transition-all ${
          disabled
            ? 'bg-slate-300 border-slate-300 text-secondary cursor-not-allowed'
            : 'bg-blue-500 hover:bg-blue-600 border-blue-500 text-white hover:shadow-xl'
        }`}
      />
    </div>
  );
};

export default RunAnalysisActions;
