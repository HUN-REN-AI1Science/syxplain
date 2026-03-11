/**
 * RunManagement Component
 * Admin view for managing all runs across users
 */

import React, { useState, useEffect, useCallback, RefObject } from 'react';
import { DataTable, DataTablePageEvent, DataTableSortEvent } from 'primereact/datatable';
import { Column } from 'primereact/column';
import { Toast } from 'primereact/toast';
import { Button } from 'primereact/button';
import { InputText } from 'primereact/inputtext';
import { Dropdown } from 'primereact/dropdown';
import { Calendar } from 'primereact/calendar';
import { Tag } from 'primereact/tag';
import { Dialog } from 'primereact/dialog';
import { ConfirmDialog, confirmDialog } from 'primereact/confirmdialog';
import { adminService } from '@services/api';
import type { AdminRunSummary, AdminRunDetail } from '@/types';

interface RunManagementProps {
  toast: RefObject<Toast | null>;
}

const RunManagement: React.FC<RunManagementProps> = ({ toast }) => {
  const [runs, setRuns] = useState<AdminRunSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [totalRecords, setTotalRecords] = useState(0);
  const [selectedRun, setSelectedRun] = useState<AdminRunDetail | null>(null);
  const [detailDialogVisible, setDetailDialogVisible] = useState(false);

  // Pagination and sorting
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(10);
  const [sortField, setSortField] = useState('created_at');
  const [sortOrder, setSortOrder] = useState<'asc' | 'desc'>('desc');

  // Filters
  const [statusFilter, setStatusFilter] = useState<string | null>(null);
  const [typeFilter, setTypeFilter] = useState<string | null>(null);
  const [searchFilter, setSearchFilter] = useState('');
  const [dateFrom, setDateFrom] = useState<Date | null>(null);
  const [dateTo, setDateTo] = useState<Date | null>(null);

  const statusOptions = [
    { label: 'All Statuses', value: null },
    { label: 'Pending', value: 'pending' },
    { label: 'Running', value: 'running' },
    { label: 'Completed', value: 'completed' },
    { label: 'Failed', value: 'failed' },
    { label: 'Timeout', value: 'timeout' },
    { label: 'Cancelled', value: 'cancelled' },
  ];

  const typeOptions = [
    { label: 'All Types', value: null },
    { label: 'Quick', value: 'quick' },
    { label: 'Deep', value: 'deep' },
  ];

  const fetchRuns = useCallback(async () => {
    try {
      setLoading(true);
      const response = await adminService.getAllRuns({
        page,
        page_size: pageSize,
        sort_field: sortField,
        sort_order: sortOrder,
        status: statusFilter || undefined,
        analysis_type: typeFilter || undefined,
        search: searchFilter || undefined,
        date_from: dateFrom?.toISOString(),
        date_to: dateTo?.toISOString(),
      });
      setRuns(response.data.items);
      setTotalRecords(response.data.total);
    } catch (error: unknown) {
      toast.current?.show({
        severity: 'error',
        summary: 'Error',
        detail: 'Failed to load runs',
      });
    } finally {
      setLoading(false);
    }
  }, [
    page,
    pageSize,
    sortField,
    sortOrder,
    statusFilter,
    typeFilter,
    searchFilter,
    dateFrom,
    dateTo,
    toast,
  ]);

  useEffect(() => {
    fetchRuns();
  }, [fetchRuns]);

  const handleSearch = () => {
    setPage(1);
    fetchRuns();
  };

  const handlePageChange = (e: DataTablePageEvent) => {
    setPage((e.page ?? 0) + 1);
    setPageSize(e.rows);
  };

  const handleSort = (e: DataTableSortEvent) => {
    setSortField((e.sortField as string) || 'created_at');
    setSortOrder(e.sortOrder === 1 ? 'asc' : 'desc');
  };

  const viewRunDetail = async (run: AdminRunSummary) => {
    try {
      const response = await adminService.getRunDetail(run.id);
      setSelectedRun(response.data);
      setDetailDialogVisible(true);
    } catch (error: unknown) {
      toast.current?.show({
        severity: 'error',
        summary: 'Error',
        detail: 'Failed to load run details',
      });
    }
  };

  const handleCancelRun = (run: AdminRunSummary) => {
    confirmDialog({
      message: `Are you sure you want to cancel this run?`,
      header: 'Cancel Run',
      icon: 'pi pi-exclamation-triangle',
      acceptClassName: 'p-button-warning',
      accept: async () => {
        try {
          await adminService.cancelRun(run.id);
          toast.current?.show({
            severity: 'success',
            summary: 'Success',
            detail: 'Run cancelled successfully',
          });
          fetchRuns();
        } catch (error: unknown) {
          toast.current?.show({
            severity: 'error',
            summary: 'Error',
            detail: 'Failed to cancel run',
          });
        }
      },
    });
  };

  const handleDownloadFile = async (runId: string, filename?: string) => {
    try {
      const response = await adminService.downloadRunFile(runId);
      const blob = new Blob([response.data]);
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = filename || 'download';
      document.body.appendChild(a);
      a.click();
      window.URL.revokeObjectURL(url);
      a.remove();
    } catch (error: unknown) {
      toast.current?.show({
        severity: 'error',
        summary: 'Error',
        detail: 'Failed to download file',
      });
    }
  };

  const handleDeleteRun = (run: AdminRunSummary) => {
    confirmDialog({
      message: `Are you sure you want to delete this run? This action cannot be undone.`,
      header: 'Delete Run',
      icon: 'pi pi-trash',
      acceptClassName: 'p-button-danger',
      accept: async () => {
        try {
          await adminService.deleteRun(run.id);
          toast.current?.show({
            severity: 'success',
            summary: 'Success',
            detail: 'Run deleted successfully',
          });
          fetchRuns();
        } catch (error: unknown) {
          toast.current?.show({
            severity: 'error',
            summary: 'Error',
            detail: 'Failed to delete run',
          });
        }
      },
    });
  };

  const getStatusSeverity = (
    status: string
  ): 'success' | 'info' | 'warning' | 'danger' | 'secondary' => {
    const map: Record<string, 'success' | 'info' | 'warning' | 'danger' | 'secondary'> = {
      completed: 'success',
      running: 'info',
      pending: 'warning',
      failed: 'danger',
      timeout: 'danger',
      cancelled: 'secondary',
    };
    return map[status] || 'secondary';
  };

  const formatDuration = (start: string | null, finish: string | null): string => {
    if (!start || !finish) return '-';
    const duration = new Date(finish).getTime() - new Date(start).getTime();
    const seconds = Math.floor(duration / 1000);
    if (seconds < 60) return `${seconds}s`;
    if (seconds < 3600) return `${Math.floor(seconds / 60)}m ${seconds % 60}s`;
    return `${Math.floor(seconds / 3600)}h ${Math.floor((seconds % 3600) / 60)}m`;
  };

  const statusTemplate = (rowData: AdminRunSummary) => (
    <Tag value={rowData.status} severity={getStatusSeverity(rowData.status)} />
  );

  const userTemplate = (rowData: AdminRunSummary) => (
    <div className="flex flex-col">
      <span className="text-sm">{rowData.user_email || 'Unknown'}</span>
      <span className="text-xs text-muted">{rowData.user_id.substring(0, 8)}...</span>
    </div>
  );

  const dateTemplate = (rowData: AdminRunSummary) => (
    <span className="text-sm">{new Date(rowData.created_at).toLocaleString()}</span>
  );

  const durationTemplate = (rowData: AdminRunSummary) => (
    <span className="text-sm">{formatDuration(rowData.start_time, rowData.finish_time)}</span>
  );

  const actionsTemplate = (rowData: AdminRunSummary) => (
    <div className="flex gap-2">
      <Button
        icon="pi pi-eye"
        className="p-button-sm p-button-text"
        onClick={() => viewRunDetail(rowData)}
        tooltip="View Details"
      />
      {(rowData.status === 'pending' || rowData.status === 'running') && (
        <Button
          icon="pi pi-ban"
          className="p-button-sm p-button-text p-button-warning"
          onClick={() => handleCancelRun(rowData)}
          tooltip="Cancel"
        />
      )}
      <Button
        icon="pi pi-trash"
        className="p-button-sm p-button-text p-button-danger"
        onClick={() => handleDeleteRun(rowData)}
        tooltip="Delete"
      />
    </div>
  );

  const header = (
    <div className="flex flex-col gap-4">
      {/* Search Row */}
      <div className="w-full">
        <label className="block text-sm text-secondary mb-1">Search</label>
        <div className="p-inputgroup">
          <InputText
            value={searchFilter}
            onChange={(e) => setSearchFilter(e.target.value)}
            placeholder="Search by filename or target..."
            onKeyDown={(e) => e.key === 'Enter' && handleSearch()}
            className="w-full"
          />
          <Button icon="pi pi-search" onClick={handleSearch} />
        </div>
      </div>
      {/* Filters Row */}
      <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-3 items-end w-full">
        <div>
          <label className="block text-sm text-secondary mb-1">Status</label>
          <Dropdown
            value={statusFilter}
            options={statusOptions}
            onChange={(e) => setStatusFilter(e.value)}
            className="w-full"
          />
        </div>
        <div>
          <label className="block text-sm text-secondary mb-1">Type</label>
          <Dropdown
            value={typeFilter}
            options={typeOptions}
            onChange={(e) => setTypeFilter(e.value)}
            className="w-full"
          />
        </div>
        <div>
          <label className="block text-sm text-secondary mb-1">Date From</label>
          <Calendar
            value={dateFrom}
            onChange={(e) => setDateFrom(e.value as Date)}
            showIcon
            className="w-full"
          />
        </div>
        <div>
          <label className="block text-sm text-secondary mb-1">Date To</label>
          <Calendar
            value={dateTo}
            onChange={(e) => setDateTo(e.value as Date)}
            showIcon
            className="w-full"
          />
        </div>
        <div className="col-span-2 sm:col-span-1 lg:col-span-2 flex justify-end">
          <Button
            icon="pi pi-refresh"
            className="p-button-outlined"
            onClick={fetchRuns}
            tooltip="Refresh"
          />
        </div>
      </div>
    </div>
  );

  return (
    <div className="overflow-x-auto">
      <ConfirmDialog />

      <DataTable
        value={runs}
        loading={loading}
        paginator
        rows={pageSize}
        totalRecords={totalRecords}
        lazy
        first={(page - 1) * pageSize}
        onPage={handlePageChange}
        onSort={handleSort}
        sortField={sortField}
        sortOrder={sortOrder === 'asc' ? 1 : -1}
        rowsPerPageOptions={[10, 25, 50]}
        header={header}
        emptyMessage="No runs found"
        className="w-full"
        paginatorTemplate="FirstPageLink PrevPageLink PageLinks NextPageLink LastPageLink CurrentPageReport RowsPerPageDropdown"
        currentPageReportTemplate="Showing {first} to {last} of {totalRecords} runs"
      >
        <Column field="id" header="ID" body={(row) => row.id.substring(0, 8) + '...'} />
        <Column header="User" body={userTemplate} />
        <Column field="status" header="Status" body={statusTemplate} sortable />
        <Column field="analysis_type" header="Type" sortable />
        <Column field="created_at" header="Created" body={dateTemplate} sortable />
        <Column header="Duration" body={durationTemplate} />
        <Column header="Actions" body={actionsTemplate} />
      </DataTable>

      {/* Run Detail Dialog */}
      <Dialog
        header="Run Details"
        visible={detailDialogVisible}
        onHide={() => setDetailDialogVisible(false)}
        className="w-full max-w-3xl mx-4"
        maximizable
      >
        {selectedRun && (
          <div className="space-y-4">
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
              <div>
                <label className="text-sm text-secondary">Run ID</label>
                <p className="font-mono text-sm">{selectedRun.id}</p>
              </div>
              <div>
                <label className="text-sm text-secondary">User</label>
                <p>{selectedRun.user_email || selectedRun.user_id}</p>
              </div>
              <div>
                <label className="text-sm text-secondary">Status</label>
                <p>
                  <Tag
                    value={selectedRun.status}
                    severity={getStatusSeverity(selectedRun.status)}
                  />
                </p>
              </div>
              <div>
                <label className="text-sm text-secondary">Analysis Type</label>
                <p>{selectedRun.analysis_type}</p>
              </div>
              <div>
                <label className="text-sm text-secondary">File</label>
                <p>
                  <a
                    href="#"
                    className="text-primary hover:underline cursor-pointer"
                    onClick={(e) => {
                      e.preventDefault();
                      handleDownloadFile(selectedRun.id, selectedRun.csv_filename);
                    }}
                  >
                    {selectedRun.csv_filename}
                  </a>
                </p>
              </div>
              <div>
                <label className="text-sm text-secondary">Progress</label>
                <p>{selectedRun.progress}%</p>
              </div>
              <div>
                <label className="text-sm text-secondary">Created</label>
                <p>
                  {selectedRun.created_at ? new Date(selectedRun.created_at).toLocaleString() : '-'}
                </p>
              </div>
              <div>
                <label className="text-sm text-secondary">Duration</label>
                <p>{formatDuration(selectedRun.start_time, selectedRun.finish_time)}</p>
              </div>
            </div>

            {selectedRun.error && (
              <div className="bg-red-50 border border-red-200 rounded-lg p-4">
                <label className="text-sm text-red-600 font-medium">Error</label>
                <p className="text-sm text-red-800 font-mono whitespace-pre-wrap">
                  {selectedRun.error}
                </p>
              </div>
            )}

            <div>
              <label className="text-sm text-secondary">Problem Description</label>
              <pre className="bg-surface-alt p-3 rounded text-sm overflow-auto max-h-48">
                {JSON.stringify(selectedRun.problem_description, null, 2)}
              </pre>
            </div>

            {selectedRun.slurm_job_ids && (
              <div>
                <label className="text-sm text-secondary">Slurm Job IDs</label>
                <pre className="bg-surface-alt p-3 rounded text-sm">
                  {JSON.stringify(selectedRun.slurm_job_ids, null, 2)}
                </pre>
              </div>
            )}
          </div>
        )}
      </Dialog>
    </div>
  );
};

export default RunManagement;
