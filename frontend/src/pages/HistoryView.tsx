/**
 * HistoryView Component
 * Displays paginated, sortable, and filterable run history
 */

import { useState, useEffect, useCallback } from 'react';
import { DataTable, DataTablePageEvent, DataTableSortEvent } from 'primereact/datatable';
import { Column } from 'primereact/column';
import { Button } from 'primereact/button';
import { Tag } from 'primereact/tag';
import { Tooltip } from 'primereact/tooltip';
import { History } from 'lucide-react';
import { runsService } from '@services/api';
import { HistoryFilterBar } from '@components/History';
import EmptyState from '@components/EmptyState';
import HelpButton from '@components/HelpButton';
import { useIsMobile } from '@hooks/useIsMobile';
import type { RunSummary } from '@/types';

// ============================================================================
// Types & Constants
// ============================================================================

interface HistoryViewProps {
  onSelectRun: (runId: string) => void;
}

const STATUS_CONFIG: Record<
  string,
  { severity: 'success' | 'info' | 'warning' | 'danger'; label: string }
> = {
  completed: { severity: 'success', label: 'Completed' },
  running: { severity: 'info', label: 'Running' },
  pending: { severity: 'warning', label: 'Pending' },
  failed: { severity: 'danger', label: 'Failed' },
  timeout: { severity: 'danger', label: 'Timeout' },
  cancelled: { severity: 'warning', label: 'Cancelled' },
};

const formatDuration = (startTime?: string | null, finishTime?: string | null): string => {
  if (!startTime || !finishTime) return '-';
  const seconds = Math.floor(
    (new Date(finishTime).getTime() - new Date(startTime).getTime()) / 1000
  );
  const hours = Math.floor(seconds / 3600);
  const minutes = Math.floor((seconds % 3600) / 60);
  const secs = seconds % 60;
  if (hours > 0) return `${hours}h ${minutes}m`;
  if (minutes > 0) return `${minutes}m ${secs}s`;
  return `${secs}s`;
};

// ============================================================================
// Component
// ============================================================================

const HistoryView: React.FC<HistoryViewProps> = ({ onSelectRun }) => {
  const isMobile = useIsMobile();

  // Data state
  const [runs, setRuns] = useState<RunSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [totalRecords, setTotalRecords] = useState(0);

  // Pagination state
  const [page, setPage] = useState(1);
  const [pageSize] = useState(10);

  // Sorting state
  const [sortField, setSortField] = useState('created_at');
  const [sortOrder, setSortOrder] = useState<1 | -1 | 0>(-1);

  // Filter state
  const [statusFilter, setStatusFilter] = useState('');
  const [analysisTypeFilter, setAnalysisTypeFilter] = useState('');
  const [searchQuery, setSearchQuery] = useState('');
  const [debouncedSearch, setDebouncedSearch] = useState('');

  // Debounce search input
  useEffect(() => {
    const timer = setTimeout(() => {
      setDebouncedSearch(searchQuery);
      setPage(1);
    }, 300);
    return () => clearTimeout(timer);
  }, [searchQuery]);

  // Load runs data
  const loadRuns = useCallback(async () => {
    setLoading(true);
    try {
      const response = await runsService.getAll({
        page,
        page_size: pageSize,
        sort_field: sortField,
        sort_order: sortOrder === 1 ? 'asc' : 'desc',
        status: statusFilter || undefined,
        analysis_type: analysisTypeFilter || undefined,
        search: debouncedSearch || undefined,
      });
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

  // Event handlers
  const onPageChange = (event: DataTablePageEvent) => {
    setPage((event.page ?? 0) + 1);
  };

  const onSort = (event: DataTableSortEvent) => {
    setSortField(event.sortField as string);
    setSortOrder(event.sortOrder as 1 | -1 | 0);
  };

  const clearFilters = () => {
    setStatusFilter('');
    setAnalysisTypeFilter('');
    setSearchQuery('');
    setPage(1);
  };

  // Computed values
  const hasActiveFilters = !!(statusFilter || analysisTypeFilter || searchQuery);

  // Column templates
  const statusTemplate = (rowData: RunSummary) => {
    const config = STATUS_CONFIG[rowData.status] || { severity: 'info', label: rowData.status };

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
          <Tooltip
            target={`.${tagId}`}
            content={`${rowData.progress || 0}% complete`}
            position="top"
          />
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

  const durationTemplate = (rowData: RunSummary) => {
    return formatDuration(rowData.start_time, rowData.finish_time);
  };

  const actionTemplate = (rowData: RunSummary) => (
    <Button
      label="View"
      icon="pi pi-eye"
      size="small"
      onClick={() => onSelectRun(rowData.id)}
      disabled={rowData.status !== 'completed'}
    />
  );

  return (
    <div className="p-4 sm:p-6">
      {/* Header */}
      <div className="mb-6">
        <div className="flex items-center gap-2 mb-2">
          <h2 className="font-heading text-2xl font-bold text-primary">Run History</h2>
          <HelpButton title="Run History">
            <h4>Run Statuses</h4>
            <ul>
              <li>
                <strong>Completed</strong> - Analysis finished successfully, results available
              </li>
              <li>
                <strong>Running</strong> - Analysis in progress (hover for % complete)
              </li>
              <li>
                <strong>Pending</strong> - Waiting to start processing
              </li>
              <li>
                <strong>Failed</strong> - Analysis encountered an error
              </li>
              <li>
                <strong>Timeout</strong> - Analysis took too long and was stopped
              </li>
            </ul>

            <h4>Navigating Your History</h4>
            <p>
              Click <strong>View</strong> on any completed run to see results. Use filters to find
              specific runs by status or analysis type.
            </p>
          </HelpButton>
        </div>
        <p className="text-secondary">View your past analysis runs</p>
      </div>

      {/* Filter Bar */}
      <HistoryFilterBar
        searchQuery={searchQuery}
        onSearchChange={setSearchQuery}
        statusFilter={statusFilter}
        onStatusChange={(value) => {
          setStatusFilter(value);
          setPage(1);
        }}
        analysisTypeFilter={analysisTypeFilter}
        onAnalysisTypeChange={(value) => {
          setAnalysisTypeFilter(value);
          setPage(1);
        }}
        onClearFilters={clearFilters}
        onRefresh={loadRuns}
        hasActiveFilters={hasActiveFilters}
      />

      {/* Data Table */}
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
          emptyMessage={
            <EmptyState
              icon={History}
              title="No analysis runs yet"
              subtitle="Start a new analysis from the Upload step to see your results here."
            />
          }
          className="w-full"
          paginatorTemplate="FirstPageLink PrevPageLink PageLinks NextPageLink LastPageLink CurrentPageReport"
          currentPageReportTemplate="Showing {first} to {last} of {totalRecords} runs"
        >
          <Column field="created_at" header="Date" body={dateTemplate} sortable />
          <Column field="csv_filename" header="Dataset" sortable />
          {!isMobile && <Column field="target_variable" header="Target Variable" sortable />}
          <Column field="analysis_type" header="Type" body={analysisTypeTemplate} sortable />
          <Column field="status" header="Status" body={statusTemplate} sortable />
          {!isMobile && <Column header="Duration" body={durationTemplate} />}
          <Column header="Actions" body={actionTemplate} />
        </DataTable>
      </div>
    </div>
  );
};

export default HistoryView;
