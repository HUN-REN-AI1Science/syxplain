/**
 * SharedRunsTable Component
 * Table displaying shared analysis results with actions
 */

import React from 'react';
import { Button } from 'primereact/button';
import { ProgressSpinner } from 'primereact/progressspinner';
import type { SharedRunInfo } from '@services/api';

interface SharedRunsTableProps {
  sharedRuns: SharedRunInfo[];
  loading: boolean;
  onCopyUrl: (url: string) => void;
  onViewRun?: (runId: string) => void;
  onRevokeShare: (runId: string) => void;
}

export const SharedRunsTable: React.FC<SharedRunsTableProps> = ({
  sharedRuns,
  loading,
  onCopyUrl,
  onViewRun,
  onRevokeShare,
}) => (
  <div className="mb-6">
    <div className="flex items-center gap-2 mb-4">
      <i className="pi pi-share-alt text-blue-600 text-xl"></i>
      <h3 className="text-lg font-semibold text-slate-700">Shared Results</h3>
    </div>
    {loading ? (
      <div className="bg-slate-50 rounded-xl p-6 text-center">
        <ProgressSpinner style={{ width: '30px', height: '30px' }} />
      </div>
    ) : sharedRuns.length === 0 ? (
      <div className="bg-slate-50 rounded-xl p-6 text-center border border-slate-200">
        <i className="pi pi-inbox text-slate-300 text-3xl mb-2"></i>
        <p className="text-slate-500">No shared results yet</p>
        <p className="text-sm text-slate-400 mt-1">Share a completed analysis to see it here</p>
      </div>
    ) : (
      <div className="bg-white rounded-xl border border-slate-200 overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full text-left">
            <thead className="bg-slate-50 border-b border-slate-200">
              <tr>
                <th className="px-4 py-3 text-xs font-semibold text-slate-600 uppercase">Dataset</th>
                <th className="px-4 py-3 text-xs font-semibold text-slate-600 uppercase">Target</th>
                <th className="px-4 py-3 text-xs font-semibold text-slate-600 uppercase">Type</th>
                <th className="px-4 py-3 text-xs font-semibold text-slate-600 uppercase">Created</th>
                <th className="px-4 py-3 text-xs font-semibold text-slate-600 uppercase">Share Link</th>
                <th className="px-4 py-3 text-xs font-semibold text-slate-600 uppercase text-right">Actions</th>
              </tr>
            </thead>
            <tbody>
              {sharedRuns.map((run, idx) => (
                <tr key={run.id} className={idx !== sharedRuns.length - 1 ? 'border-b border-slate-100' : ''}>
                  <td className="px-4 py-3 text-slate-700 text-sm">
                    <span className="font-mono truncate max-w-[150px] inline-block" title={run.csv_filename}>
                      {run.csv_filename}
                    </span>
                  </td>
                  <td className="px-4 py-3 font-medium text-slate-800 font-mono text-sm">
                    {run.target_variable || '-'}
                  </td>
                  <td className="px-4 py-3">
                    <span className={`text-xs font-medium px-2 py-1 rounded-full ${run.analysis_type === 'deep' ? 'bg-blue-100 text-blue-700' : 'bg-orange-100 text-orange-700'}`}>
                      {run.analysis_type === 'deep' ? 'Deep' : 'Quick'}
                    </span>
                  </td>
                  <td className="px-4 py-3 text-slate-600 text-sm">
                    {run.created_at ? new Date(run.created_at).toLocaleDateString() : '-'}
                  </td>
                  <td className="px-4 py-3">
                    <div className="flex items-center gap-2">
                      <code className="text-xs text-blue-600 bg-blue-50 px-2 py-1 rounded truncate max-w-[120px]">
                        {run.share_url}
                      </code>
                      <Button
                        icon="pi pi-copy"
                        className="p-button-text p-button-sm !text-slate-400 hover:!text-blue-600"
                        onClick={() => onCopyUrl(run.share_url)}
                        tooltip="Copy link"
                        tooltipOptions={{ position: 'top' }}
                      />
                    </div>
                  </td>
                  <td className="px-4 py-3 text-right">
                    <div className="flex items-center justify-end gap-1">
                      {onViewRun && (
                        <Button
                          icon="pi pi-eye"
                          className="p-button-text p-button-sm !text-slate-400 hover:!text-blue-600"
                          onClick={() => onViewRun(run.id)}
                          tooltip="View results"
                          tooltipOptions={{ position: 'top' }}
                        />
                      )}
                      <Button
                        icon="pi pi-trash"
                        className="p-button-text p-button-sm p-button-danger"
                        onClick={() => onRevokeShare(run.id)}
                        tooltip="Revoke share link"
                        tooltipOptions={{ position: 'top' }}
                      />
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    )}
  </div>
);

export default SharedRunsTable;
