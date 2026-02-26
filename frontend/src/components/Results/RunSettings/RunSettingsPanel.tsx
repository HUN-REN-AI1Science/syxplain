/**
 * RunSettingsPanel Component
 * Displays expandable run configuration details
 */

import React, { useState } from 'react';
import { Panel, type PanelHeaderTemplateOptions, type PanelToggleEvent } from 'primereact/panel';
import { Button } from 'primereact/button';
import { Tag } from 'primereact/tag';
import { ProgressBar } from 'primereact/progressbar';
import { runsService } from '@services/api';
import { formatFileSize } from '@utils/formatting';
import type { RunDetails } from '@/types';

interface RunSettingsPanelProps {
  runId: string;
}

const RunSettingsPanel: React.FC<RunSettingsPanelProps> = ({ runId }) => {
  const [collapsed, setCollapsed] = useState(true);
  const [loading, setLoading] = useState(false);
  const [runDetails, setRunDetails] = useState<RunDetails | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [hasFetched, setHasFetched] = useState(false);

  const handleDownloadCsv = async () => {
    try {
      const response = await runsService.downloadCsv(runId);
      const url = window.URL.createObjectURL(new Blob([response.data]));
      const link = document.createElement('a');
      link.href = url;
      link.setAttribute('download', runDetails?.csv_filename || 'data.csv');
      document.body.appendChild(link);
      link.click();
      link.remove();
      window.URL.revokeObjectURL(url);
    } catch (e) {
      console.error('Failed to download CSV:', e);
    }
  };

  const handleToggle = async (e: PanelToggleEvent) => {
    const isExpanding = !e.value; // e.value is the NEW collapsed state, so !e.value means expanding

    // Fetch data only on first expand
    if (isExpanding && !hasFetched) {
      setCollapsed(false);
      setLoading(true);
      setError(null);

      try {
        const response = await runsService.getDetails(runId);
        setRunDetails(response.data);
        setHasFetched(true);
      } catch (err) {
        console.error('Failed to fetch run details:', err);
        setError('Failed to load run details');
      } finally {
        setLoading(false);
      }
    } else {
      setCollapsed(e.value);
    }
  };

  const headerTemplate = (options: PanelHeaderTemplateOptions) => {
    return (
      <div className="flex items-center justify-between w-full px-4 py-3">
        <div className="flex items-center">
          <i className="pi pi-cog text-muted text-lg mr-3"></i>
          <span className="text-lg font-bold text-primary font-heading">Run Configuration</span>
        </div>
        <button
          className="w-8 h-8 rounded-lg bg-surface-alt hover:bg-surface-alt flex items-center justify-center transition-colors"
          onClick={options.onTogglerClick}
        >
          <i
            className={`pi ${options.collapsed ? 'pi-chevron-down' : 'pi-chevron-up'} text-secondary text-sm`}
          ></i>
        </button>
      </div>
    );
  };

  const { problem_description, csv_metadata } = runDetails || {};
  const features = problem_description?.features || {};
  const featureEntries = Object.entries(features);

  // Determine file type from filename for dynamic button label
  const getFileTypeLabel = () => {
    const filename = csv_metadata?.filename || runDetails?.csv_filename || '';
    const ext = filename.split('.').pop()?.toLowerCase();
    if (ext === 'xlsx' || ext === 'xls') {
      return 'Download Excel';
    }
    return 'Download CSV';
  };

  return (
    <div className="mb-6 animate-fade-in">
      <Panel
        headerTemplate={headerTemplate}
        toggleable
        collapsed={collapsed}
        onToggle={handleToggle}
        className="run-settings-panel bg-surface rounded-xl border border-[var(--color-border)] shadow-sm overflow-hidden"
      >
        {/* Loading State */}
        {loading && (
          <div className="py-8 px-4">
            <div className="flex flex-col items-center justify-center">
              <div className="w-full max-w-md mb-4">
                <ProgressBar mode="indeterminate" style={{ height: '6px' }} />
              </div>
              <p className="text-secondary text-sm">Loading run configuration...</p>
            </div>
          </div>
        )}

        {/* Error State */}
        {error && !loading && (
          <div className="py-8 px-4 text-center">
            <i className="pi pi-exclamation-circle text-red-500 text-3xl mb-3"></i>
            <p className="text-red-600">{error}</p>
            <Button
              label="Retry"
              icon="pi pi-refresh"
              className="p-button-outlined p-button-sm mt-3"
              onClick={() => {
                setHasFetched(false);
                handleToggle({ value: true } as PanelToggleEvent);
              }}
            />
          </div>
        )}

        {/* Content - shown when data is loaded */}
        {!loading && !error && runDetails && (
          <div className="space-y-4 pt-2">
            {/* Top row: Dataset Info and Target Variable */}
            <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
              {/* Dataset Info Card */}
              <div className="lg:col-span-2 bg-surface-alt rounded-xl p-5 border border-[var(--color-border)]">
                <div className="flex items-center justify-between mb-4">
                  <div className="flex items-center">
                    <i className="pi pi-file text-muted text-lg mr-3 flex-shrink-0"></i>
                    <div className="min-w-0">
                      <h4 className="font-bold text-primary">Dataset</h4>
                      <p
                        className="text-sm text-secondary font-mono truncate"
                        title={csv_metadata?.filename}
                      >
                        {csv_metadata?.filename || runDetails.csv_filename}
                      </p>
                    </div>
                  </div>
                  <Button
                    label={getFileTypeLabel()}
                    icon="pi pi-download"
                    size="small"
                    className="p-button-outlined flex-shrink-0 ml-4"
                    onClick={handleDownloadCsv}
                  />
                </div>
                <div className="grid grid-cols-3 gap-2 sm:gap-4">
                  <div className="bg-surface rounded-lg p-3 text-center border border-[var(--color-border)]">
                    <div className="text-xl sm:text-2xl font-bold text-primary">
                      {csv_metadata?.row_count?.toLocaleString() ?? '-'}
                    </div>
                    <div className="text-xs text-secondary uppercase tracking-wider mt-1">Rows</div>
                  </div>
                  <div className="bg-surface rounded-lg p-3 text-center border border-[var(--color-border)]">
                    <div className="text-xl sm:text-2xl font-bold text-primary">
                      {csv_metadata?.column_count ?? '-'}
                    </div>
                    <div className="text-xs text-secondary uppercase tracking-wider mt-1">
                      Columns
                    </div>
                  </div>
                  <div className="bg-surface rounded-lg p-3 text-center border border-[var(--color-border)]">
                    <div className="text-xl sm:text-2xl font-bold text-primary">
                      {csv_metadata?.size_bytes ? formatFileSize(csv_metadata.size_bytes) : '-'}
                    </div>
                    <div className="text-xs text-secondary uppercase tracking-wider mt-1">Size</div>
                  </div>
                </div>
              </div>

              {/* Target Variable Card */}
              <div className="bg-surface-alt rounded-xl p-5 border border-[var(--color-border)]">
                <div className="flex items-center mb-3">
                  <i className="pi pi-flag text-muted text-lg mr-3 flex-shrink-0"></i>
                  <h4 className="font-bold text-primary">Target Variable</h4>
                </div>
                <div className="flex items-center justify-center py-4">
                  <Tag
                    value={problem_description?.target_variable || 'N/A'}
                    severity="success"
                    className="text-lg px-4 py-2 font-mono"
                  />
                </div>
                <p className="text-center text-sm text-secondary mt-2">
                  The variable being predicted
                </p>
              </div>
            </div>

            {/* Analysis Mode - Compact */}
            <div
              className="rounded-xl p-4 border bg-surface-alt border-[var(--color-border)]"
            >
              <div className="flex items-center justify-between">
                <div className="flex items-center">
                  <i
                    className={`pi ${runDetails.analysis_type === 'deep' ? 'pi-search' : 'pi-bolt'} text-muted text-lg mr-3 flex-shrink-0`}
                  ></i>
                  <div>
                    <h4 className="font-bold text-primary">Analysis Mode</h4>
                    <p className="text-sm text-secondary">
                      {runDetails.analysis_type === 'deep'
                        ? 'Enhanced with scientific literature research'
                        : 'Standard analysis workflow'}
                    </p>
                  </div>
                </div>
                <Tag
                  value={runDetails.analysis_type === 'deep' ? 'Deep Analysis' : 'Quick Analysis'}
                  severity={runDetails.analysis_type === 'deep' ? 'warning' : 'info'}
                  className="text-base px-3 py-1"
                />
              </div>
            </div>

            {/* Project Description */}
            <div className="bg-surface-alt rounded-xl p-5 border border-[var(--color-border)]">
              <div className="flex items-center mb-3">
                <i className="pi pi-pencil text-muted text-lg mr-3 flex-shrink-0"></i>
                <h4 className="font-bold text-primary">Project Description</h4>
              </div>
              <p className="text-primary leading-relaxed whitespace-pre-wrap">
                {problem_description?.project_description || 'No description provided.'}
              </p>
            </div>

            {/* Features - Table Layout */}
            {featureEntries.length > 0 && (
              <div className="bg-surface-alt rounded-xl p-5 border border-[var(--color-border)]">
                <div className="flex items-center mb-4">
                  <i className="pi pi-list text-muted text-lg mr-3 flex-shrink-0"></i>
                  <div>
                    <h4 className="font-bold text-primary">Feature Descriptions</h4>
                    <p className="text-sm text-secondary">
                      {featureEntries.length} features used in analysis
                    </p>
                  </div>
                </div>

                {/* Table-like feature list */}
                <div className="bg-surface rounded-lg border border-[var(--color-border)] overflow-hidden">
                  {/* Table Header */}
                  <div className="hidden sm:grid grid-cols-12 gap-2 sm:gap-4 px-4 py-3 bg-surface-alt border-b border-[var(--color-border)]">
                    <div className="sm:col-span-4 text-xs font-semibold text-secondary uppercase tracking-wider">
                      Feature Name
                    </div>
                    <div className="sm:col-span-8 text-xs font-semibold text-secondary uppercase tracking-wider">
                      Description
                    </div>
                  </div>

                  {/* Table Body */}
                  <div className="max-h-[280px] overflow-y-auto custom-scrollbar">
                    {featureEntries.map(([featureName, description], index) => (
                      <div
                        key={featureName}
                        className={`grid grid-cols-1 sm:grid-cols-12 gap-2 sm:gap-4 px-4 py-3 items-center hover:bg-brand-50 transition-colors ${
                          index !== featureEntries.length - 1 ? 'border-b border-[var(--color-border)]' : ''
                        }`}
                      >
                        <div className="sm:col-span-4 flex items-center min-w-0">
                          <div className="w-6 h-6 bg-surface-alt rounded flex items-center justify-center mr-2 flex-shrink-0">
                            <i className="pi pi-database text-muted text-xs"></i>
                          </div>
                          <code
                            className="text-sm font-semibold text-link truncate"
                            title={featureName}
                          >
                            {featureName}
                          </code>
                        </div>
                        <div className="sm:col-span-8 text-sm text-secondary">
                          {description || (
                            <span className="text-muted italic">No description provided</span>
                          )}
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              </div>
            )}

            {/* Run timestamp and duration */}
            {runDetails.created_at && (
              <div className="flex items-center justify-center text-sm text-muted pt-2">
                <i className="pi pi-clock mr-2"></i>
                <span>Run started: {new Date(runDetails.created_at).toLocaleString()}</span>
                {runDetails.start_time && runDetails.finish_time && (
                  <span className="ml-3">
                    Duration:{' '}
                    {(() => {
                      const seconds = Math.floor(
                        (new Date(runDetails.finish_time).getTime() -
                          new Date(runDetails.start_time).getTime()) /
                          1000
                      );
                      if (seconds < 60) return `${seconds}s`;
                      const minutes = Math.floor(seconds / 60);
                      const secs = seconds % 60;
                      if (minutes < 60) return `${minutes}m ${secs}s`;
                      const hours = Math.floor(minutes / 60);
                      return `${hours}h ${minutes % 60}m`;
                    })()}
                  </span>
                )}
              </div>
            )}
          </div>
        )}
      </Panel>
    </div>
  );
};

export default RunSettingsPanel;
