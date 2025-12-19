import { useState, useEffect } from 'react';
import api from './api';
import { DataTable } from 'primereact/datatable';
import { Column } from 'primereact/column';
import { Button } from 'primereact/button';
import { Tag } from 'primereact/tag';
import { Tooltip } from 'primereact/tooltip';

interface RunSummary {
  id: string;
  status: string;
  created_at: string;
  csv_filename: string;
  target_variable: string | null;
  progress: number;
}

interface HistoryViewProps {
  onSelectRun: (runId: string) => void;
}

const HistoryView: React.FC<HistoryViewProps> = ({ onSelectRun }) => {
  const [runs, setRuns] = useState<RunSummary[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    loadRuns();
    // Poll for updates every 5 seconds to refresh progress
    const intervalId = setInterval(loadRuns, 5000);
    return () => clearInterval(intervalId);
  }, []);

  const loadRuns = async () => {
    try {
      const response = await api.get('/runs');
      setRuns(response.data);
    } catch (error) {
      console.error('Failed to load runs:', error);
    } finally {
      setLoading(false);
    }
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

  return (
    <div className="p-6">
      <div className="mb-6">
        <h2 className="text-2xl font-bold text-slate-800 mb-2">Run History</h2>
        <p className="text-slate-500">View your past analysis runs</p>
      </div>

      <div className="overflow-x-auto">
        <DataTable
          value={runs}
          loading={loading}
          paginator
          rows={10}
          emptyMessage="No runs found"
          className="w-full min-w-[600px]"
        >
          <Column field="created_at" header="Date" body={dateTemplate} sortable />
          <Column field="csv_filename" header="Dataset" sortable />
          <Column field="target_variable" header="Target Variable" sortable />
          <Column field="status" header="Status" body={statusTemplate} sortable />
          <Column header="Actions" body={actionTemplate} />
        </DataTable>
      </div>
    </div>
  );
};

export default HistoryView;
