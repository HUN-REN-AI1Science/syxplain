/**
 * HistoryFilterBar Component
 * Search, filter, and refresh controls for history table
 */

import React from 'react';
import { Button } from 'primereact/button';
import { Dropdown } from 'primereact/dropdown';
import { InputText } from 'primereact/inputtext';

const STATUS_OPTIONS = [
  { label: 'All Statuses', value: '' },
  { label: 'Completed', value: 'completed' },
  { label: 'Running', value: 'running' },
  { label: 'Pending', value: 'pending' },
  { label: 'Failed', value: 'failed' },
  { label: 'Timeout', value: 'timeout' },
];

const ANALYSIS_TYPE_OPTIONS = [
  { label: 'All Types', value: '' },
  { label: 'Quick', value: 'quick' },
  { label: 'Deep', value: 'deep' },
];

interface HistoryFilterBarProps {
  searchQuery: string;
  onSearchChange: (value: string) => void;
  statusFilter: string;
  onStatusChange: (value: string) => void;
  analysisTypeFilter: string;
  onAnalysisTypeChange: (value: string) => void;
  onClearFilters: () => void;
  onRefresh: () => void;
  hasActiveFilters: boolean;
}

export const HistoryFilterBar: React.FC<HistoryFilterBarProps> = ({
  searchQuery,
  onSearchChange,
  statusFilter,
  onStatusChange,
  analysisTypeFilter,
  onAnalysisTypeChange,
  onClearFilters,
  onRefresh,
  hasActiveFilters,
}) => (
  <div className="mb-4 p-4 bg-surface-alt rounded-lg border border-[var(--color-border)] w-full">
    <div className="flex flex-col sm:flex-row items-stretch sm:items-center gap-4 w-full">
      {/* Search */}
      <div className="p-inputgroup w-full sm:flex-1 sm:min-w-[200px]">
        <span className="p-inputgroup-addon">
          <i className="pi pi-search" />
        </span>
        <InputText
          value={searchQuery}
          onChange={(e) => onSearchChange(e.target.value)}
          placeholder="Search by filename or target..."
          className="w-full"
        />
      </div>

      {/* Analysis Type Filter */}
      <Dropdown
        value={analysisTypeFilter}
        options={ANALYSIS_TYPE_OPTIONS}
        optionLabel="label"
        optionValue="value"
        onChange={(e) => onAnalysisTypeChange(e.value)}
        placeholder="Type"
        className="w-full sm:w-[160px]"
      />

      {/* Status Filter */}
      <Dropdown
        value={statusFilter}
        options={STATUS_OPTIONS}
        optionLabel="label"
        optionValue="value"
        onChange={(e) => onStatusChange(e.value)}
        placeholder="Status"
        className="w-full sm:w-[170px]"
      />

      {/* Actions */}
      <div className="flex gap-2 sm:ml-auto">
        {hasActiveFilters && (
          <Button
            label="Clear"
            icon="pi pi-times"
            severity="secondary"
            outlined
            size="small"
            onClick={onClearFilters}
          />
        )}
        <Button
          icon="pi pi-refresh"
          severity="secondary"
          outlined
          size="small"
          onClick={onRefresh}
          tooltip="Refresh"
          tooltipOptions={{ position: 'top' }}
        />
      </div>
    </div>
  </div>
);

export default HistoryFilterBar;
