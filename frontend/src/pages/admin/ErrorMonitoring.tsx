/**
 * ErrorMonitoring Component
 * Track failed runs and identify error patterns
 */

import React, { useState, useEffect, useCallback, RefObject } from 'react';
import { Card } from 'primereact/card';
import { Toast } from 'primereact/toast';
import { DataTable, DataTablePageEvent } from 'primereact/datatable';
import { Column } from 'primereact/column';
import { Chart } from 'primereact/chart';
import { Tag } from 'primereact/tag';
import { Dropdown } from 'primereact/dropdown';
import { Button } from 'primereact/button';
import { Dialog } from 'primereact/dialog';
import { adminService } from '@services/api';
import { legacyAnalysisTypeLabel } from '@utils/formatting';
import type { AdminRunSummary, ErrorDistributionItem, ErrorTrendItem } from '@/types';

interface ErrorMonitoringProps {
  toast: RefObject<Toast | null>;
}

const ErrorMonitoring: React.FC<ErrorMonitoringProps> = ({ toast }) => {
  const [failedRuns, setFailedRuns] = useState<AdminRunSummary[]>([]);
  const [distribution, setDistribution] = useState<ErrorDistributionItem[]>([]);
  const [trend, setTrend] = useState<ErrorTrendItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [totalRecords, setTotalRecords] = useState(0);
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(10);
  const [days, setDays] = useState(30);
  const [selectedError, setSelectedError] = useState<AdminRunSummary | null>(null);
  const [errorDialogVisible, setErrorDialogVisible] = useState(false);

  const daysOptions = [
    { label: 'Last 7 days', value: 7 },
    { label: 'Last 30 days', value: 30 },
    { label: 'Last 90 days', value: 90 },
  ];

  const fetchErrorData = useCallback(async () => {
    try {
      setLoading(true);
      const [runsRes, distRes, trendRes] = await Promise.all([
        adminService.getFailedRuns(page, pageSize, days),
        adminService.getErrorDistribution(days),
        adminService.getErrorTrend(days),
      ]);
      setFailedRuns(runsRes.data.items);
      setTotalRecords(runsRes.data.total);
      setDistribution(distRes.data.items);
      setTrend(trendRes.data.items);
    } catch (error: unknown) {
      toast.current?.show({
        severity: 'error',
        summary: 'Error',
        detail: 'Failed to load error data',
      });
    } finally {
      setLoading(false);
    }
  }, [page, pageSize, days, toast]);

  useEffect(() => {
    fetchErrorData();
  }, [fetchErrorData]);

  const handlePageChange = (e: DataTablePageEvent) => {
    setPage((e.page ?? 0) + 1);
    setPageSize(e.rows);
  };

  const viewError = (run: AdminRunSummary) => {
    setSelectedError(run);
    setErrorDialogVisible(true);
  };

  const errorColors: Record<string, string> = {
    Timeout: '#F59E0B',
    'API Error': '#EF4444',
    'File Error': '#8B5CF6',
    'Resource Error': '#EC4899',
    'Slurm Error': '#06B6D4',
    'Other Error': '#6B7280',
    'Unknown Error': '#9CA3AF',
  };

  const distributionChartData = {
    labels: distribution.map((d) => d.error_type),
    datasets: [
      {
        data: distribution.map((d) => d.count),
        backgroundColor: distribution.map((d) => errorColors[d.error_type] || '#6B7280'),
      },
    ],
  };

  const distributionChartOptions = {
    responsive: true,
    maintainAspectRatio: false,
    plugins: {
      legend: {
        position: 'bottom' as const,
        labels: {
          boxWidth: 12,
          padding: 8,
        },
      },
    },
  };

  const trendChartData = {
    labels: trend.map((t) => t.date),
    datasets: [
      {
        label: 'Total Runs',
        data: trend.map((t) => t.total),
        borderColor: '#3B82F6',
        backgroundColor: 'transparent',
        tension: 0.4,
        yAxisID: 'y',
      },
      {
        label: 'Failed',
        data: trend.map((t) => t.failed),
        borderColor: '#EF4444',
        backgroundColor: 'rgba(239, 68, 68, 0.1)',
        fill: true,
        tension: 0.4,
        yAxisID: 'y',
      },
      {
        label: 'Failure Rate (%)',
        data: trend.map((t) => t.failure_rate),
        borderColor: '#F59E0B',
        backgroundColor: 'transparent',
        tension: 0.4,
        borderDash: [5, 5],
        yAxisID: 'y1',
      },
    ],
  };

  const trendChartOptions = {
    responsive: true,
    maintainAspectRatio: false,
    plugins: {
      legend: {
        position: 'top' as const,
      },
    },
    scales: {
      y: {
        type: 'linear' as const,
        display: true,
        position: 'left' as const,
        beginAtZero: true,
        title: {
          display: true,
          text: 'Count',
        },
      },
      y1: {
        type: 'linear' as const,
        display: true,
        position: 'right' as const,
        beginAtZero: true,
        max: 100,
        title: {
          display: true,
          text: 'Failure Rate (%)',
        },
        grid: {
          drawOnChartArea: false,
        },
      },
    },
  };

  const getStatusSeverity = (status: string): 'danger' | 'warning' | 'secondary' => {
    return status === 'failed' ? 'danger' : status === 'timeout' ? 'warning' : 'secondary';
  };

  const statusTemplate = (rowData: AdminRunSummary) => (
    <Tag value={rowData.status} severity={getStatusSeverity(rowData.status)} />
  );

  const userTemplate = (rowData: AdminRunSummary) => (
    <span className="text-sm">{rowData.user_email || rowData.user_id.substring(0, 8) + '...'}</span>
  );

  const dateTemplate = (rowData: AdminRunSummary) => (
    <span className="text-sm">{new Date(rowData.created_at).toLocaleString()}</span>
  );

  const errorTemplate = (rowData: AdminRunSummary) => (
    <span
      className="text-sm text-red-600 cursor-pointer hover:underline truncate block max-w-xs"
      onClick={() => viewError(rowData)}
      title={rowData.error || 'Click to view details'}
    >
      {rowData.error
        ? rowData.error.substring(0, 50) + (rowData.error.length > 50 ? '...' : '')
        : 'No error message'}
    </span>
  );

  const actionsTemplate = (rowData: AdminRunSummary) => (
    <Button
      icon="pi pi-eye"
      className="p-button-sm p-button-text"
      onClick={() => viewError(rowData)}
      tooltip="View Error Details"
    />
  );

  // Calculate summary stats
  const totalFailures = distribution.reduce((sum, d) => sum + d.count, 0);
  const avgFailureRate =
    trend.length > 0 ? trend.reduce((sum, t) => sum + t.failure_rate, 0) / trend.length : 0;

  return (
    <div className="space-y-6">
      {/* Controls */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div className="flex items-center gap-3">
          <Dropdown
            value={days}
            options={daysOptions}
            onChange={(e) => {
              setDays(e.value);
              setPage(1);
            }}
            className="w-48"
          />
          <Button
            icon="pi pi-refresh"
            label="Refresh"
            className="p-button-outlined p-button-sm"
            onClick={fetchErrorData}
            loading={loading}
          />
        </div>
        <div className="flex flex-wrap gap-3 text-sm text-secondary">
          <span>
            Failures: <strong className="text-red-600">{totalFailures}</strong>
          </span>
          <span>
            Avg Rate: <strong className="text-orange-600">{avgFailureRate.toFixed(1)}%</strong>
          </span>
        </div>
      </div>

      {/* Charts Row */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Error Trend Chart */}
        <Card className="shadow-md lg:col-span-2">
          <h3 className="text-lg font-semibold font-heading text-primary mb-4">Error Trend</h3>
          <div className="h-48 sm:h-64">
            <Chart type="line" data={trendChartData} options={trendChartOptions} />
          </div>
        </Card>

        {/* Error Distribution Chart */}
        <Card className="shadow-md">
          <h3 className="text-lg font-semibold font-heading text-primary mb-4">
            Error Distribution
          </h3>
          <div className="h-48 sm:h-64">
            {distribution.length > 0 ? (
              <Chart type="pie" data={distributionChartData} options={distributionChartOptions} />
            ) : (
              <div className="flex items-center justify-center h-full text-muted">
                No errors in this period
              </div>
            )}
          </div>
        </Card>
      </div>

      {/* Failed Runs Table */}
      <Card className="shadow-md">
        <h3 className="text-lg font-semibold font-heading text-primary mb-4">Failed Runs</h3>
        <div className="overflow-x-auto">
          <DataTable
            value={failedRuns}
            loading={loading}
            paginator
            rows={pageSize}
            totalRecords={totalRecords}
            lazy
            first={(page - 1) * pageSize}
            onPage={handlePageChange}
            rowsPerPageOptions={[10, 25, 50]}
            emptyMessage="No failed runs found"
            className="text-sm"
            paginatorTemplate="FirstPageLink PrevPageLink PageLinks NextPageLink LastPageLink CurrentPageReport"
            currentPageReportTemplate="Showing {first} to {last} of {totalRecords} failed runs"
          >
            <Column field="id" header="ID" body={(row) => row.id.substring(0, 8) + '...'} />
            <Column header="User" body={userTemplate} />
            <Column field="status" header="Status" body={statusTemplate} />
            <Column header="Error" body={errorTemplate} />
            <Column field="created_at" header="Date" body={dateTemplate} />
            <Column header="" body={actionsTemplate} />
          </DataTable>
        </div>
      </Card>

      {/* Error Detail Dialog */}
      <Dialog
        header="Error Details"
        visible={errorDialogVisible}
        onHide={() => setErrorDialogVisible(false)}
        className="w-full max-w-2xl mx-4"
        maximizable
      >
        {selectedError && (
          <div className="space-y-4">
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
              <div>
                <label className="text-sm text-secondary">Run ID</label>
                <p className="font-mono text-sm">{selectedError.id}</p>
              </div>
              <div>
                <label className="text-sm text-secondary">User</label>
                <p>{selectedError.user_email || selectedError.user_id}</p>
              </div>
              <div>
                <label className="text-sm text-secondary">Status</label>
                <p>
                  <Tag
                    value={selectedError.status}
                    severity={getStatusSeverity(selectedError.status)}
                  />
                </p>
              </div>
              <div>
                <label className="text-sm text-secondary">File</label>
                <p>{selectedError.csv_filename}</p>
              </div>
              {legacyAnalysisTypeLabel(selectedError.analysis_type) && (
                <div>
                  <label className="text-sm text-secondary">Analysis Type</label>
                  <p>{legacyAnalysisTypeLabel(selectedError.analysis_type)}</p>
                </div>
              )}
              <div>
                <label className="text-sm text-secondary">Created</label>
                <p>{new Date(selectedError.created_at).toLocaleString()}</p>
              </div>
            </div>

            <div className="bg-red-50 border border-red-200 rounded-lg p-4">
              <label className="text-sm text-red-600 font-medium block mb-2">Error Message</label>
              <pre className="text-sm text-red-800 font-mono whitespace-pre-wrap overflow-auto max-h-64">
                {selectedError.error || 'No error message available'}
              </pre>
            </div>
          </div>
        )}
      </Dialog>
    </div>
  );
};

export default ErrorMonitoring;
