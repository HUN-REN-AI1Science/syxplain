/**
 * AuditLogs Component
 * View and filter admin action audit logs
 */

import React, { useState, useEffect, RefObject } from 'react';
import { DataTable, DataTablePageEvent } from 'primereact/datatable';
import { Column } from 'primereact/column';
import { Toast } from 'primereact/toast';
import { Button } from 'primereact/button';
import { Dropdown } from 'primereact/dropdown';
import { Calendar } from 'primereact/calendar';
import { Tag } from 'primereact/tag';
import { Dialog } from 'primereact/dialog';
import { adminService } from '@services/api';
import type { AuditLogEntry, AuditFilterOptions } from '@/types';

interface AuditLogsProps {
  toast: RefObject<Toast | null>;
}

const AuditLogs: React.FC<AuditLogsProps> = ({ toast }) => {
  const [logs, setLogs] = useState<AuditLogEntry[]>([]);
  const [filterOptions, setFilterOptions] = useState<AuditFilterOptions | null>(null);
  const [loading, setLoading] = useState(true);
  const [totalRecords, setTotalRecords] = useState(0);
  const [selectedLog, setSelectedLog] = useState<AuditLogEntry | null>(null);
  const [detailDialogVisible, setDetailDialogVisible] = useState(false);

  // Pagination
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(25);

  // Filters
  const [actionFilter, setActionFilter] = useState<string | null>(null);
  const [adminFilter, setAdminFilter] = useState<string | null>(null);
  const [targetTypeFilter, setTargetTypeFilter] = useState<string | null>(null);
  const [dateFrom, setDateFrom] = useState<Date | null>(null);
  const [dateTo, setDateTo] = useState<Date | null>(null);

  const targetTypeOptions = [
    { label: 'All Types', value: null },
    { label: 'User', value: 'user' },
    { label: 'Run', value: 'run' },
  ];

  useEffect(() => {
    fetchFilterOptions();
  }, []);

  useEffect(() => {
    fetchLogs();
  }, [page, pageSize, actionFilter, adminFilter, targetTypeFilter, dateFrom, dateTo]);

  const fetchFilterOptions = async () => {
    try {
      const response = await adminService.getAuditFilterOptions();
      setFilterOptions(response.data);
    } catch (error: unknown) {
      console.error('Failed to load filter options:', error);
    }
  };

  const fetchLogs = async () => {
    try {
      setLoading(true);
      const response = await adminService.getAuditLogs({
        page,
        page_size: pageSize,
        action: actionFilter || undefined,
        admin_email: adminFilter || undefined,
        target_type: targetTypeFilter || undefined,
        date_from: dateFrom?.toISOString(),
        date_to: dateTo?.toISOString(),
      });
      setLogs(response.data.items);
      setTotalRecords(response.data.total);
    } catch (error: unknown) {
      toast.current?.show({
        severity: 'error',
        summary: 'Error',
        detail: 'Failed to load audit logs',
      });
    } finally {
      setLoading(false);
    }
  };

  const handlePageChange = (e: DataTablePageEvent) => {
    setPage((e.page ?? 0) + 1);
    setPageSize(e.rows);
  };

  const clearFilters = () => {
    setActionFilter(null);
    setAdminFilter(null);
    setTargetTypeFilter(null);
    setDateFrom(null);
    setDateTo(null);
    setPage(1);
  };

  const exportToCSV = () => {
    const headers = [
      'Date',
      'Admin',
      'Action',
      'Target Type',
      'Target ID',
      'IP Address',
      'Details',
    ];
    const rows = logs.map((log) => [
      new Date(log.created_at).toISOString(),
      log.admin_email,
      log.action,
      log.target_type,
      log.target_id,
      log.ip_address || '',
      log.details ? JSON.stringify(log.details) : '',
    ]);

    const csvContent = [
      headers.join(','),
      ...rows.map((row) => row.map((cell) => `"${cell}"`).join(',')),
    ].join('\n');

    const blob = new Blob([csvContent], { type: 'text/csv;charset=utf-8;' });
    const link = document.createElement('a');
    link.href = URL.createObjectURL(blob);
    link.download = `audit_logs_${new Date().toISOString().split('T')[0]}.csv`;
    link.click();
  };

  const viewLogDetail = (log: AuditLogEntry) => {
    setSelectedLog(log);
    setDetailDialogVisible(true);
  };

  const getActionSeverity = (action: string): 'success' | 'danger' | 'warning' | 'info' => {
    if (action.includes('grant')) return 'success';
    if (action.includes('delete')) return 'danger';
    if (action.includes('revoke') || action.includes('cancel')) return 'warning';
    return 'info';
  };

  const getActionIcon = (action: string): string => {
    if (action.includes('grant')) return 'pi pi-check-circle';
    if (action.includes('revoke')) return 'pi pi-times-circle';
    if (action.includes('delete')) return 'pi pi-trash';
    if (action.includes('cancel')) return 'pi pi-ban';
    return 'pi pi-cog';
  };

  const actionTemplate = (rowData: AuditLogEntry) => (
    <div className="flex items-center gap-2">
      <i className={`${getActionIcon(rowData.action)} text-sm`} />
      <Tag value={rowData.action} severity={getActionSeverity(rowData.action)} />
    </div>
  );

  const targetTemplate = (rowData: AuditLogEntry) => (
    <div className="flex flex-col">
      <span className="text-sm">{rowData.target_type}</span>
      <span className="text-xs text-slate-400 font-mono">
        {rowData.target_id.substring(0, 12)}...
      </span>
    </div>
  );

  const dateTemplate = (rowData: AuditLogEntry) => (
    <span className="text-sm">{new Date(rowData.created_at).toLocaleString()}</span>
  );

  const adminTemplate = (rowData: AuditLogEntry) => (
    <div className="flex flex-col">
      <span className="text-sm">{rowData.admin_email}</span>
      {rowData.ip_address && <span className="text-xs text-slate-400">{rowData.ip_address}</span>}
    </div>
  );

  const detailsTemplate = (rowData: AuditLogEntry) =>
    rowData.details ? (
      <Button
        icon="pi pi-eye"
        className="p-button-sm p-button-text"
        onClick={() => viewLogDetail(rowData)}
        tooltip="View Details"
      />
    ) : (
      <span className="text-slate-400">-</span>
    );

  const actionOptions = filterOptions?.actions.map((a) => ({ label: a, value: a })) || [];
  const adminOptions = filterOptions?.admins.map((a) => ({ label: a, value: a })) || [];

  const header = (
    <div className="flex flex-col gap-4">
      {/* Filters Grid */}
      <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-3 items-end">
        <div>
          <label className="block text-sm text-slate-600 mb-1">Action</label>
          <Dropdown
            value={actionFilter}
            options={[{ label: 'All Actions', value: null }, ...actionOptions]}
            onChange={(e) => {
              setActionFilter(e.value);
              setPage(1);
            }}
            className="w-full"
            filter
            showClear
          />
        </div>
        <div>
          <label className="block text-sm text-slate-600 mb-1">Admin</label>
          <Dropdown
            value={adminFilter}
            options={[{ label: 'All Admins', value: null }, ...adminOptions]}
            onChange={(e) => {
              setAdminFilter(e.value);
              setPage(1);
            }}
            className="w-full"
            filter
            showClear
          />
        </div>
        <div>
          <label className="block text-sm text-slate-600 mb-1">Target</label>
          <Dropdown
            value={targetTypeFilter}
            options={targetTypeOptions}
            onChange={(e) => {
              setTargetTypeFilter(e.value);
              setPage(1);
            }}
            className="w-full"
          />
        </div>
        <div>
          <label className="block text-sm text-slate-600 mb-1">From</label>
          <Calendar
            value={dateFrom}
            onChange={(e) => {
              setDateFrom(e.value as Date);
              setPage(1);
            }}
            showIcon
            className="w-full"
          />
        </div>
        <div>
          <label className="block text-sm text-slate-600 mb-1">To</label>
          <Calendar
            value={dateTo}
            onChange={(e) => {
              setDateTo(e.value as Date);
              setPage(1);
            }}
            showIcon
            className="w-full"
          />
        </div>
        <div className="flex gap-2 justify-end">
          <Button
            icon="pi pi-filter-slash"
            className="p-button-outlined p-button-sm"
            onClick={clearFilters}
            tooltip="Clear"
          />
          <Button
            icon="pi pi-refresh"
            className="p-button-outlined p-button-sm"
            onClick={fetchLogs}
            tooltip="Refresh"
          />
        </div>
      </div>
      {/* Export Button */}
      <div className="flex justify-end">
        <Button
          icon="pi pi-download"
          label="Export CSV"
          className="p-button-outlined p-button-sm"
          onClick={exportToCSV}
          disabled={logs.length === 0}
        />
      </div>
    </div>
  );

  return (
    <div className="overflow-x-auto">
      <DataTable
        value={logs}
        loading={loading}
        paginator
        rows={pageSize}
        totalRecords={totalRecords}
        lazy
        first={(page - 1) * pageSize}
        onPage={handlePageChange}
        rowsPerPageOptions={[25, 50, 100]}
        header={header}
        emptyMessage="No audit logs found"
        className="text-sm"
        paginatorTemplate="FirstPageLink PrevPageLink PageLinks NextPageLink LastPageLink CurrentPageReport RowsPerPageDropdown"
        currentPageReportTemplate="Showing {first} to {last} of {totalRecords} logs"
      >
        <Column field="created_at" header="Date" body={dateTemplate} style={{ width: '160px' }} />
        <Column header="Admin" body={adminTemplate} style={{ width: '220px' }} />
        <Column header="Action" body={actionTemplate} style={{ width: '180px' }} />
        <Column header="Target" body={targetTemplate} style={{ width: '180px' }} />
        <Column header="Details" body={detailsTemplate} style={{ width: '80px' }} />
      </DataTable>

      {/* Detail Dialog */}
      <Dialog
        header="Audit Log Details"
        visible={detailDialogVisible}
        onHide={() => setDetailDialogVisible(false)}
        className="w-full max-w-lg mx-4"
      >
        {selectedLog && (
          <div className="space-y-4">
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
              <div>
                <label className="text-sm text-slate-500">Date</label>
                <p>{new Date(selectedLog.created_at).toLocaleString()}</p>
              </div>
              <div>
                <label className="text-sm text-slate-500">Admin</label>
                <p>{selectedLog.admin_email}</p>
              </div>
              <div>
                <label className="text-sm text-slate-500">Action</label>
                <p>
                  <Tag
                    value={selectedLog.action}
                    severity={getActionSeverity(selectedLog.action)}
                  />
                </p>
              </div>
              <div>
                <label className="text-sm text-slate-500">Target</label>
                <p>
                  {selectedLog.target_type}/{selectedLog.target_id}
                </p>
              </div>
              {selectedLog.ip_address && (
                <div>
                  <label className="text-sm text-slate-500">IP Address</label>
                  <p className="font-mono">{selectedLog.ip_address}</p>
                </div>
              )}
            </div>

            {selectedLog.details && (
              <div>
                <label className="text-sm text-slate-500">Details</label>
                <pre className="bg-slate-50 p-3 rounded text-sm overflow-auto max-h-48 font-mono">
                  {JSON.stringify(selectedLog.details, null, 2)}
                </pre>
              </div>
            )}
          </div>
        )}
      </Dialog>
    </div>
  );
};

export default AuditLogs;
