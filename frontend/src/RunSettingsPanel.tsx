import React, { useState } from 'react';
import { Panel } from 'primereact/panel';
import { Button } from 'primereact/button';
import { Tag } from 'primereact/tag';
import { ProgressBar } from 'primereact/progressbar';
import api from './api';

interface RunDetails {
  id: string;
  status: string;
  created_at: string | null;
  problem_description: {
    project_description: string;
    target_variable: string;
    features: Record<string, string>;
  };
  csv_filename: string;
  csv_metadata: {
    filename: string;
    size_bytes: number;
    row_count: number | null;
    column_count: number | null;
    columns: string[];
  } | null;
  analysis_type: string | null;
  error: string | null;
}

interface RunSettingsPanelProps {
  runId: string;
}

const RunSettingsPanel: React.FC<RunSettingsPanelProps> = ({ runId }) => {
  const [collapsed, setCollapsed] = useState(true);
  const [loading, setLoading] = useState(false);
  const [runDetails, setRunDetails] = useState<RunDetails | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [hasFetched, setHasFetched] = useState(false);

  const formatFileSize = (bytes: number): string => {
    if (bytes < 1024) return `${bytes} B`;
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
    return `${(bytes / (1024 * 1024)).toFixed(2)} MB`;
  };

  const handleDownloadCsv = async () => {
    try {
      const response = await api.get(`/runs/${runId}/download-csv`, {
        responseType: 'blob',
      });
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

  const handleToggle = async (e: any) => {
    const isExpanding = !e.value; // e.value is the NEW collapsed state, so !e.value means expanding

    // Fetch data only on first expand
    if (isExpanding && !hasFetched) {
      setCollapsed(false);
      setLoading(true);
      setError(null);

      try {
        const response = await api.get(`/runs/${runId}/details`);
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

  const headerTemplate = (options: any) => {
    return (
      <div className="flex items-center justify-between w-full pr-2">
        <div className="flex items-center">
          <div className="w-10 h-10 bg-gradient-to-r from-blue-500 to-indigo-600 rounded-lg flex items-center justify-center mr-3">
            <i className="pi pi-cog text-white text-lg"></i>
          </div>
          <span className="text-lg font-bold text-slate-800">Run Configuration</span>
        </div>
        <button
          className="w-8 h-8 rounded-lg bg-slate-100 hover:bg-slate-200 flex items-center justify-center transition-colors"
          onClick={options.onTogglerClick}
        >
          <i className={`pi ${options.collapsed ? 'pi-chevron-down' : 'pi-chevron-up'} text-slate-500 text-sm`}></i>
        </button>
      </div>
    );
  };

  const { problem_description, csv_metadata } = runDetails || {};
  const features = problem_description?.features || {};
  const featureEntries = Object.entries(features);

  return (
    <div className="mb-6 animate-fade-in">
      <Panel
        headerTemplate={headerTemplate}
        toggleable
        collapsed={collapsed}
        onToggle={handleToggle}
        className="run-settings-panel bg-white rounded-xl border border-slate-200 shadow-sm overflow-hidden"
      >
        {/* Loading State */}
        {loading && (
          <div className="py-8 px-4">
            <div className="flex flex-col items-center justify-center">
              <div className="w-full max-w-md mb-4">
                <ProgressBar mode="indeterminate" style={{ height: '6px' }} />
              </div>
              <p className="text-slate-500 text-sm">Loading run configuration...</p>
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
                handleToggle({ value: true });
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
              <div className="lg:col-span-2 bg-gradient-to-br from-slate-50 to-slate-100 rounded-xl p-5 border border-slate-200">
                <div className="flex items-center justify-between mb-4">
                  <div className="flex items-center">
                    <div className="w-10 h-10 bg-blue-100 rounded-lg flex items-center justify-center mr-3 flex-shrink-0">
                      <i className="pi pi-file text-blue-600 text-lg"></i>
                    </div>
                    <div className="min-w-0">
                      <h4 className="font-bold text-slate-800">Dataset</h4>
                      <p className="text-sm text-slate-500 font-mono truncate" title={csv_metadata?.filename}>
                        {csv_metadata?.filename || runDetails.csv_filename}
                      </p>
                    </div>
                  </div>
                  <Button
                    label="Download CSV"
                    icon="pi pi-download"
                    size="small"
                    className="p-button-outlined flex-shrink-0 ml-4"
                    onClick={handleDownloadCsv}
                  />
                </div>
                <div className="grid grid-cols-3 gap-4">
                  <div className="bg-white rounded-lg p-3 text-center border border-slate-100">
                    <div className="text-2xl font-bold text-slate-800">
                      {csv_metadata?.row_count?.toLocaleString() ?? '-'}
                    </div>
                    <div className="text-xs text-slate-500 uppercase tracking-wider mt-1">Rows</div>
                  </div>
                  <div className="bg-white rounded-lg p-3 text-center border border-slate-100">
                    <div className="text-2xl font-bold text-slate-800">
                      {csv_metadata?.column_count ?? '-'}
                    </div>
                    <div className="text-xs text-slate-500 uppercase tracking-wider mt-1">Columns</div>
                  </div>
                  <div className="bg-white rounded-lg p-3 text-center border border-slate-100">
                    <div className="text-2xl font-bold text-slate-800">
                      {csv_metadata?.size_bytes ? formatFileSize(csv_metadata.size_bytes) : '-'}
                    </div>
                    <div className="text-xs text-slate-500 uppercase tracking-wider mt-1">Size</div>
                  </div>
                </div>
              </div>

              {/* Target Variable Card */}
              <div className="bg-gradient-to-br from-green-50 to-emerald-100 rounded-xl p-5 border border-green-200">
                <div className="flex items-center mb-3">
                  <div className="w-10 h-10 bg-green-100 rounded-lg flex items-center justify-center mr-3 flex-shrink-0">
                    <i className="pi pi-compass text-green-600 text-lg"></i>
                  </div>
                  <h4 className="font-bold text-slate-800">Target Variable</h4>
                </div>
                <div className="flex items-center justify-center py-4">
                  <Tag
                    value={problem_description?.target_variable || 'N/A'}
                    severity="success"
                    className="text-lg px-4 py-2 font-mono"
                  />
                </div>
                <p className="text-center text-sm text-slate-500 mt-2">
                  The variable being predicted
                </p>
              </div>
            </div>

            {/* Analysis Mode - Compact */}
            <div className={`rounded-xl p-4 border ${runDetails.analysis_type === 'deep' ? 'bg-gradient-to-br from-purple-50 to-fuchsia-100 border-purple-200' : 'bg-gradient-to-br from-orange-50 to-amber-100 border-orange-200'}`}>
              <div className="flex items-center justify-between">
                <div className="flex items-center">
                  <div className={`w-10 h-10 rounded-lg flex items-center justify-center mr-3 flex-shrink-0 ${runDetails.analysis_type === 'deep' ? 'bg-purple-100' : 'bg-orange-100'}`}>
                    <i className={`pi ${runDetails.analysis_type === 'deep' ? 'pi-search text-purple-600' : 'pi-bolt text-orange-600'} text-lg`}></i>
                  </div>
                  <div>
                    <h4 className="font-bold text-slate-800">Analysis Mode</h4>
                    <p className="text-sm text-slate-500">
                      {runDetails.analysis_type === 'deep' ? 'Enhanced with scientific literature research' : 'Standard analysis workflow'}
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
            <div className="bg-gradient-to-br from-indigo-50 to-purple-50 rounded-xl p-5 border border-indigo-100">
              <div className="flex items-center mb-3">
                <div className="w-10 h-10 bg-indigo-100 rounded-lg flex items-center justify-center mr-3 flex-shrink-0">
                  <i className="pi pi-info-circle text-indigo-600 text-lg"></i>
                </div>
                <h4 className="font-bold text-slate-800">Project Description</h4>
              </div>
              <p className="text-slate-700 leading-relaxed whitespace-pre-wrap pl-[52px]">
                {problem_description?.project_description || 'No description provided.'}
              </p>
            </div>

            {/* Features - Table Layout */}
            {featureEntries.length > 0 && (
              <div className="bg-gradient-to-br from-purple-50 to-pink-50 rounded-xl p-5 border border-purple-100">
                <div className="flex items-center mb-4">
                  <div className="w-10 h-10 bg-purple-100 rounded-lg flex items-center justify-center mr-3 flex-shrink-0">
                    <i className="pi pi-list text-purple-600 text-lg"></i>
                  </div>
                  <div>
                    <h4 className="font-bold text-slate-800">Feature Descriptions</h4>
                    <p className="text-sm text-slate-500">{featureEntries.length} features used in analysis</p>
                  </div>
                </div>

                {/* Table-like feature list */}
                <div className="bg-white rounded-lg border border-purple-100 overflow-hidden">
                  {/* Table Header */}
                  <div className="grid grid-cols-12 gap-4 px-4 py-3 bg-purple-50 border-b border-purple-100">
                    <div className="col-span-4 text-xs font-semibold text-purple-700 uppercase tracking-wider">
                      Feature Name
                    </div>
                    <div className="col-span-8 text-xs font-semibold text-purple-700 uppercase tracking-wider">
                      Description
                    </div>
                  </div>

                  {/* Table Body */}
                  <div className="max-h-[280px] overflow-y-auto custom-scrollbar">
                    {featureEntries.map(([featureName, description], index) => (
                      <div
                        key={featureName}
                        className={`grid grid-cols-12 gap-4 px-4 py-3 items-center hover:bg-purple-25 transition-colors ${index !== featureEntries.length - 1 ? 'border-b border-purple-50' : ''
                          }`}
                      >
                        <div className="col-span-4 flex items-center min-w-0">
                          <div className="w-6 h-6 bg-slate-100 rounded flex items-center justify-center mr-2 flex-shrink-0">
                            <i className="pi pi-database text-slate-400 text-xs"></i>
                          </div>
                          <code className="text-sm font-semibold text-purple-700 truncate" title={featureName}>
                            {featureName}
                          </code>
                        </div>
                        <div className="col-span-8 text-sm text-slate-600">
                          {description || <span className="text-slate-400 italic">No description provided</span>}
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              </div>
            )}

            {/* Run timestamp */}
            {runDetails.created_at && (
              <div className="flex items-center justify-center text-sm text-slate-400 pt-2">
                <i className="pi pi-clock mr-2"></i>
                <span>Run started: {new Date(runDetails.created_at).toLocaleString()}</span>
              </div>
            )}
          </div>
        )}
      </Panel>
    </div>
  );
};

export default RunSettingsPanel;
