import { useState, useEffect, useCallback } from 'react';
import api from './api';
import { DataTable, DataTablePageEvent, DataTableSortEvent } from 'primereact/datatable';
import { Column } from 'primereact/column';
import { Button } from 'primereact/button';
import { Tag } from 'primereact/tag';
import { Tooltip } from 'primereact/tooltip';
import { Dropdown } from 'primereact/dropdown';
import { InputText } from 'primereact/inputtext';

interface RunSummary {
  id: string;
  status: string;
  created_at: string;
  csv_filename: string;
  target_variable: string | null;
  progress: number;
  analysis_type: string;
}

interface PaginatedResponse {
  items: RunSummary[];
  total: number;
  page: number;
  page_size: number;
  total_pages: number;
}

interface HistoryViewProps {
  onSelectRun: (runId: string) => void;
}

const HistoryView: React.FC<HistoryViewProps> = ({ onSelectRun }) => {
  const [runs, setRuns] = useState<RunSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [totalRecords, setTotalRecords] = useState(0);

  // Pagination state
  const [page, setPage] = useState(1);
  const [pageSize] = useState(10);

  // Sorting state
  const [sortField, setSortField] = useState('created_at');
  const [sortOrder, setSortOrder] = useState<1 | -1 | 0>(-1); // -1 = desc, 1 = asc

  // Filter state
  const [statusFilter, setStatusFilter] = useState('');
  const [analysisTypeFilter, setAnalysisTypeFilter] = useState('');
  const [searchQuery, setSearchQuery] = useState('');
  const [debouncedSearch, setDebouncedSearch] = useState('');

  // Debounce search input
  useEffect(() => {
    const timer = setTimeout(() => {
      setDebouncedSearch(searchQuery);
      setPage(1); // Reset to first page on search
    }, 300);
    return () => clearTimeout(timer);
  }, [searchQuery]);

  const loadRuns = useCallback(async () => {
    setLoading(true);
    try {
      const params = new URLSearchParams({
        page: page.toString(),
        page_size: pageSize.toString(),
        sort_field: sortField,
        sort_order: sortOrder === 1 ? 'asc' : 'desc'
      });

      if (statusFilter) params.append('status', statusFilter);
      if (analysisTypeFilter) params.append('analysis_type', analysisTypeFilter);
      if (debouncedSearch) params.append('search', debouncedSearch);

      const response = await api.get<PaginatedResponse>(`/runs?${params.toString()}`);
      setRuns(response.data.items);
      setTotalRecords(response.data.total);
    } catch (error) {
      console.error('Failed to load runs:', error);
    } finally {
      setLoading(false);
    }
  }, [page, pageSize, sortField, sortOrder, statusFilter, analysisTypeFilter, debouncedSearch]);

  useEffect(() => {
    loadRuns();
  }, [loadRuns]);

  const onPageChange = (event: DataTablePageEvent) => {
    setPage((event.page ?? 0) + 1); // DataTable uses 0-indexed pages
  };

  const onSort = (event: DataTableSortEvent) => {
    setSortField(event.sortField as string);
    setSortOrder(event.sortOrder as 1 | -1 | 0);
  };

  const statusTemplate = (rowData: RunSummary) => {
    const statusMap: Record<string, { severity: 'success' | 'info' | 'warning' | 'danger', label: string }> = {
      completed: { severity: 'success', label: 'Completed' },
      running: { severity: 'info', label: 'Running' },
      pending: { severity: 'warning', label: 'Pending' },
      failed: { severity: 'danger', label: 'Failed' },
      timeout: { severity: 'danger', label: 'Timeout' }
    };

    const config = statusMap[rowData.status] || { severity: 'info', label: rowData.status };

    // Show progress tooltip for running/pending status
    if (rowData.status === 'running' || rowData.status === 'pending') {
      const tagId = `status-tag-${rowData.id.replace(/-/g, '')}`;
      return (
        <>
          <Tag
            severity={config.severity}
            value={config.label}
            className={tagId}
            style={{ cursor: 'help' }}
          />
          <Tooltip target={`.${tagId}`} content={`${rowData.progress || 0}% complete`} position="top" />
        </>
      );
    }

    return <Tag severity={config.severity} value={config.label} />;
  };

  const dateTemplate = (rowData: RunSummary) => {
    return new Date(rowData.created_at).toLocaleString();
  };

  const analysisTypeTemplate = (rowData: RunSummary) => {
    const isDeep = rowData.analysis_type === 'deep';
    return (
      <Tag
        value={isDeep ? 'Deep' : 'Quick'}
        severity={isDeep ? 'warning' : 'info'}
        icon={isDeep ? 'pi pi-search' : 'pi pi-bolt'}
      />
    );
  };

  const actionTemplate = (rowData: RunSummary) => {
    return (
      <Button
        label="View"
        icon="pi pi-eye"
        size="small"
        onClick={() => onSelectRun(rowData.id)}
        disabled={rowData.status !== 'completed'}
      />
    );
  };

  const statusOptions = [
    { label: 'All Statuses', value: '' },
    { label: 'Completed', value: 'completed' },
    { label: 'Running', value: 'running' },
    { label: 'Pending', value: 'pending' },
    { label: 'Failed', value: 'failed' },
    { label: 'Timeout', value: 'timeout' }
  ];

  const analysisTypeOptions = [
    { label: 'All Types', value: '' },
    { label: 'Quick', value: 'quick' },
    { label: 'Deep', value: 'deep' }
  ];

  const clearFilters = () => {
    setStatusFilter('');
    setAnalysisTypeFilter('');
    setSearchQuery('');
    setPage(1);
  };

  const hasActiveFilters = statusFilter || analysisTypeFilter || searchQuery;

  return (
    <div className="p-4 sm:p-6">
      <div className="mb-6">
        <h2 className="text-2xl font-bold text-slate-800 mb-2">Run History</h2>
        <p className="text-slate-500">View your past analysis runs</p>
      </div>

      {/* Filter Bar */}
      <div className="mb-4 p-4 bg-slate-50 rounded-lg border border-slate-200 w-full">
        <div className="flex flex-col sm:flex-row items-stretch sm:items-center gap-4 w-full">
          {/* Search */}
          <div className="p-inputgroup w-full sm:flex-1 sm:min-w-[200px]">
            <span className="p-inputgroup-addon">
              <i className="pi pi-search" />
            </span>
            <InputText
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              placeholder="Search by filename or target..."
              className="w-full"
            />
          </div>

          {/* Analysis Type Filter */}
          <Dropdown
            value={analysisTypeFilter}
            options={analysisTypeOptions}
            optionLabel="label"
            optionValue="value"
            onChange={(e) => { setAnalysisTypeFilter(e.value); setPage(1); }}
            placeholder="Type"
            className="w-full sm:w-[160px]"
          />

          {/* Status Filter */}
          <Dropdown
            value={statusFilter}
            options={statusOptions}
            optionLabel="label"
            optionValue="value"
            onChange={(e) => { setStatusFilter(e.value); setPage(1); }}
            placeholder="Status"
            className="w-full sm:w-[170px]"
          />

          {/* Clear Filters */}
          {/* Actions */}
          <div className="flex gap-2 sm:ml-auto">
            {hasActiveFilters && (
              <Button
                label="Clear"
                icon="pi pi-times"
                severity="secondary"
                outlined
                size="small"
                onClick={clearFilters}
              />
            )}

            <Button
              icon="pi pi-refresh"
              severity="secondary"
              outlined
              size="small"
              onClick={loadRuns}
              tooltip="Refresh"
              tooltipOptions={{ position: 'top' }}
            />
          </div>
        </div>
      </div>

      <div
        className={`overflow-x-auto transition-opacity duration-200 ${loading ? 'opacity-60' : 'opacity-100'}`}
      >
        <DataTable
          value={runs}
          lazy
          paginator
          first={(page - 1) * pageSize}
          rows={pageSize}
          totalRecords={totalRecords}
          onPage={onPageChange}
          sortField={sortField}
          sortOrder={sortOrder}
          onSort={onSort}
          emptyMessage="No runs found"
          className="w-full min-w-[600px]"
          paginatorTemplate="FirstPageLink PrevPageLink PageLinks NextPageLink LastPageLink CurrentPageReport"
          currentPageReportTemplate="Showing {first} to {last} of {totalRecords} runs"
        >
          <Column field="created_at" header="Date" body={dateTemplate} sortable />
          <Column field="csv_filename" header="Dataset" sortable />
          <Column field="target_variable" header="Target Variable" sortable />
          <Column field="analysis_type" header="Type" body={analysisTypeTemplate} sortable />
          <Column field="status" header="Status" body={statusTemplate} sortable />
          <Column header="Actions" body={actionTemplate} />
        </DataTable>
      </div>
    </div>
  );
};

export default HistoryView;
