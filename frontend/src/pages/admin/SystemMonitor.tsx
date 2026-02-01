/**
 * SystemMonitor Component
 * Real-time system health and Slurm cluster monitoring
 */

import React, { useState, useEffect, useRef, RefObject } from 'react';
import { Card } from 'primereact/card';
import { Toast } from 'primereact/toast';
import { Tag } from 'primereact/tag';
import { Button } from 'primereact/button';
import { DataTable } from 'primereact/datatable';
import { Column } from 'primereact/column';
import { InputSwitch } from 'primereact/inputswitch';
import { adminService } from '@services/api';
import type { SystemHealth, SlurmStatus, PartitionInfo } from '@/types';

interface SystemMonitorProps {
  toast: RefObject<Toast | null>;
}

const SystemMonitor: React.FC<SystemMonitorProps> = ({ toast }) => {
  const [health, setHealth] = useState<SystemHealth | null>(null);
  const [slurmStatus, setSlurmStatus] = useState<SlurmStatus | null>(null);
  const [loading, setLoading] = useState(true);
  const [autoRefresh, setAutoRefresh] = useState(false);
  const refreshInterval = useRef<NodeJS.Timeout | null>(null);

  useEffect(() => {
    fetchSystemStatus();
    return () => {
      if (refreshInterval.current) {
        clearInterval(refreshInterval.current);
      }
    };
  }, []);

  useEffect(() => {
    if (autoRefresh) {
      refreshInterval.current = setInterval(fetchSystemStatus, 30000);
    } else if (refreshInterval.current) {
      clearInterval(refreshInterval.current);
      refreshInterval.current = null;
    }
    return () => {
      if (refreshInterval.current) {
        clearInterval(refreshInterval.current);
      }
    };
  }, [autoRefresh]);

  const fetchSystemStatus = async () => {
    try {
      setLoading(true);
      const healthRes = await adminService.getSystemHealth();
      setHealth(healthRes.data);

      if (healthRes.data.slurm_configured) {
        try {
          const slurmRes = await adminService.getSlurmStatus();
          setSlurmStatus(slurmRes.data);
        } catch {
          setSlurmStatus(null);
        }
      }
    } catch (error: unknown) {
      toast.current?.show({
        severity: 'error',
        summary: 'Error',
        detail: 'Failed to load system status',
      });
    } finally {
      setLoading(false);
    }
  };

  const formatUptime = (seconds: number): string => {
    const days = Math.floor(seconds / 86400);
    const hours = Math.floor((seconds % 86400) / 3600);
    const minutes = Math.floor((seconds % 3600) / 60);
    if (days > 0) return `${days}d ${hours}h ${minutes}m`;
    if (hours > 0) return `${hours}h ${minutes}m`;
    return `${minutes}m`;
  };

  const HealthCard: React.FC<{
    title: string;
    healthy: boolean;
    icon: string;
    description?: string;
  }> = ({ title, healthy, icon, description }) => (
    <Card className="shadow-md">
      <div className="flex items-center gap-4">
        <div
          className={`p-4 rounded-lg ${
            healthy ? 'bg-green-100' : 'bg-red-100'
          }`}
        >
          <i
            className={`${icon} text-2xl ${
              healthy ? 'text-green-600' : 'text-red-600'
            }`}
          />
        </div>
        <div className="flex-grow">
          <p className="text-sm text-slate-500">{title}</p>
          <div className="flex items-center gap-2">
            <Tag
              value={healthy ? 'Healthy' : 'Unhealthy'}
              severity={healthy ? 'success' : 'danger'}
            />
          </div>
          {description && (
            <p className="text-xs text-slate-400 mt-1">{description}</p>
          )}
        </div>
      </div>
    </Card>
  );

  if (loading && !health) {
    return (
      <div className="flex items-center justify-center p-8">
        <i className="pi pi-spin pi-spinner text-4xl text-blue-600" />
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Controls */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div className="flex flex-wrap items-center gap-3">
          <Button
            icon="pi pi-refresh"
            label="Refresh"
            className="p-button-outlined p-button-sm"
            onClick={fetchSystemStatus}
            loading={loading}
          />
          <div className="flex items-center gap-2">
            <InputSwitch
              checked={autoRefresh}
              onChange={(e) => setAutoRefresh(e.value)}
            />
            <span className="text-sm text-slate-600">Auto (30s)</span>
          </div>
        </div>
        {health && (
          <span className="text-xs sm:text-sm text-slate-500">
            Last: {new Date(health.checked_at).toLocaleTimeString()}
          </span>
        )}
      </div>

      {/* Health Status Cards */}
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
        <HealthCard
          title="API Status"
          healthy={health?.api_healthy ?? false}
          icon="pi pi-server"
          description={`Uptime: ${health ? formatUptime(health.uptime_seconds) : '-'}`}
        />
        <HealthCard
          title="Database"
          healthy={health?.database_connected ?? false}
          icon="pi pi-database"
        />
        <HealthCard
          title="Slurm Cluster"
          healthy={health?.slurm_connected ?? false}
          icon="pi pi-sitemap"
          description={health?.slurm_connected ? 'slurm.science-cloud.hu' : 'Disconnected'}
        />
      </div>

      {/* Slurm Status */}
      {health?.slurm_connected && slurmStatus && (
        <Card className="shadow-md">
          <h3 className="text-lg font-semibold text-slate-800 mb-4">
            Slurm Cluster Status
          </h3>

          {slurmStatus.error ? (
            <div className="bg-red-50 border border-red-200 rounded-lg p-4">
              <p className="text-red-600">{slurmStatus.error}</p>
            </div>
          ) : (
            <>
              {/* Cluster Overview */}
              <div className="grid grid-cols-2 sm:grid-cols-4 gap-4 mb-6">
                <div className="bg-slate-50 rounded-lg p-4">
                  <p className="text-sm text-slate-500">Cluster Status</p>
                  <Tag
                    value={slurmStatus.cluster_status}
                    severity={
                      slurmStatus.cluster_status === 'healthy'
                        ? 'success'
                        : 'warning'
                    }
                  />
                </div>
                <div className="bg-slate-50 rounded-lg p-4">
                  <p className="text-sm text-slate-500">Active Jobs</p>
                  <p className="text-2xl font-bold text-blue-600">
                    {slurmStatus.active_jobs}
                  </p>
                </div>
                <div className="bg-slate-50 rounded-lg p-4">
                  <p className="text-sm text-slate-500">Queue Length</p>
                  <p className="text-2xl font-bold text-orange-600">
                    {slurmStatus.queue_length}
                  </p>
                </div>
                <div className="bg-slate-50 rounded-lg p-4">
                  <p className="text-sm text-slate-500">Total Nodes</p>
                  <p className="text-2xl font-bold text-slate-800">
                    {slurmStatus.total_nodes}
                  </p>
                </div>
              </div>

              {/* Node Status */}
              {Object.keys(slurmStatus.node_status).length > 0 && (
                <div className="mb-6">
                  <h4 className="text-sm font-medium text-slate-600 mb-2">
                    Node Status
                  </h4>
                  <div className="flex flex-wrap gap-2">
                    {Object.entries(slurmStatus.node_status).map(
                      ([state, count]) => (
                        <Tag
                          key={state}
                          value={`${state}: ${count}`}
                          severity={
                            state === 'IDLE'
                              ? 'success'
                              : state === 'ALLOCATED'
                              ? 'info'
                              : state === 'DOWN'
                              ? 'danger'
                              : 'warning'
                          }
                        />
                      )
                    )}
                  </div>
                </div>
              )}

              {/* Partitions Table */}
              {slurmStatus.partitions.length > 0 && (
                <div>
                  <h4 className="text-sm font-medium text-slate-600 mb-2">
                    Partitions
                  </h4>
                  <DataTable
                    value={slurmStatus.partitions}
                    size="small"
                    className="text-sm"
                  >
                    <Column field="name" header="Name" />
                    <Column
                      field="state"
                      header="State"
                      body={(row: PartitionInfo) => (
                        <Tag
                          value={row.state}
                          severity={row.state === 'UP' ? 'success' : 'danger'}
                        />
                      )}
                    />
                    <Column field="total_nodes" header="Nodes" />
                    <Column field="total_cpus" header="CPUs" />
                  </DataTable>
                </div>
              )}
            </>
          )}
        </Card>
      )}

      {/* Info Box */}
      <div className="bg-blue-50 border border-blue-200 rounded-lg p-4">
        <div className="flex items-start gap-3">
          <i className="pi pi-info-circle text-blue-600 mt-0.5" />
          <div>
            <h3 className="font-semibold text-blue-800 mb-2">
              System Monitoring
            </h3>
            <ul className="text-sm text-blue-700 list-disc pl-5 space-y-1">
              <li>Health checks verify database and Slurm connectivity</li>
              <li>Auto-refresh polls the system every 30 seconds when enabled</li>
              <li>
                Slurm status shows real-time cluster information when available
              </li>
              <li>
                Use this page to monitor system health before and during
                operations
              </li>
            </ul>
          </div>
        </div>
      </div>
    </div>
  );
};

export default SystemMonitor;
