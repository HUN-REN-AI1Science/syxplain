/**
 * PerformanceAnalytics Component
 * Analysis duration and success rate metrics
 */

import React, { useState, useEffect, RefObject } from 'react';
import { Card } from 'primereact/card';
import { Toast } from 'primereact/toast';
import { Chart } from 'primereact/chart';
import { DataTable } from 'primereact/datatable';
import { Column } from 'primereact/column';
import { Button } from 'primereact/button';
import { Tag } from 'primereact/tag';
import { ProgressBar } from 'primereact/progressbar';
import { adminService } from '@services/api';
import type { PerformanceStats, PerformanceByTypeItem, RunTrendItem } from '@/types';

interface PerformanceAnalyticsProps {
  toast: RefObject<Toast | null>;
}

const PerformanceAnalytics: React.FC<PerformanceAnalyticsProps> = ({ toast }) => {
  const [stats, setStats] = useState<PerformanceStats | null>(null);
  const [byType, setByType] = useState<PerformanceByTypeItem[]>([]);
  const [trends, setTrends] = useState<RunTrendItem[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetchPerformanceData();
  }, []);

  const fetchPerformanceData = async () => {
    try {
      setLoading(true);
      const [statsRes, byTypeRes, trendsRes] = await Promise.all([
        adminService.getPerformanceStats(),
        adminService.getPerformanceByType(),
        adminService.getRunTrends(30),
      ]);
      setStats(statsRes.data);
      setByType(byTypeRes.data.items);
      setTrends(trendsRes.data.items);
    } catch (error: unknown) {
      toast.current?.show({
        severity: 'error',
        summary: 'Error',
        detail: 'Failed to load performance data',
      });
    } finally {
      setLoading(false);
    }
  };

  const formatDuration = (seconds: number): string => {
    if (seconds < 60) return `${Math.round(seconds)}s`;
    if (seconds < 3600) {
      const mins = Math.floor(seconds / 60);
      const secs = Math.round(seconds % 60);
      return `${mins}m ${secs}s`;
    }
    const hours = Math.floor(seconds / 3600);
    const mins = Math.round((seconds % 3600) / 60);
    return `${hours}h ${mins}m`;
  };

  // Performance trend chart (success rate over time)
  const successRateByDay = trends.map((t) => {
    const terminal = t.completed + t.failed + t.timeout;
    return terminal > 0 ? (t.completed / terminal) * 100 : 0;
  });

  const trendChartData = {
    labels: trends.map((t) => t.date),
    datasets: [
      {
        label: 'Total Runs',
        data: trends.map((t) => t.total),
        borderColor: '#3B82F6',
        backgroundColor: 'rgba(59, 130, 246, 0.1)',
        fill: true,
        tension: 0.4,
        yAxisID: 'y',
      },
      {
        label: 'Success Rate (%)',
        data: successRateByDay,
        borderColor: '#10B981',
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
          text: 'Runs',
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
          text: 'Success Rate (%)',
        },
        grid: {
          drawOnChartArea: false,
        },
      },
    },
  };

  // Comparison chart data
  const comparisonChartData = {
    labels: byType.map((t) => t.type.charAt(0).toUpperCase() + t.type.slice(1)),
    datasets: [
      {
        label: 'Total Runs',
        data: byType.map((t) => t.total_runs),
        backgroundColor: '#3B82F6',
      },
      {
        label: 'Completed',
        data: byType.map((t) => t.completed),
        backgroundColor: '#10B981',
      },
      {
        label: 'Failed',
        data: byType.map((t) => t.failed),
        backgroundColor: '#EF4444',
      },
    ],
  };

  const comparisonChartOptions = {
    responsive: true,
    maintainAspectRatio: false,
    plugins: {
      legend: {
        position: 'top' as const,
      },
    },
    scales: {
      y: {
        beginAtZero: true,
      },
    },
  };

  const typeTemplate = (rowData: PerformanceByTypeItem) => (
    <Tag
      value={rowData.type.charAt(0).toUpperCase() + rowData.type.slice(1)}
      severity={rowData.type === 'quick' ? 'info' : 'warning'}
    />
  );

  const durationTemplate = (rowData: PerformanceByTypeItem) => (
    <span className="font-mono">{formatDuration(rowData.avg_duration)}</span>
  );

  const successRateTemplate = (rowData: PerformanceByTypeItem) => (
    <div className="flex items-center gap-2">
      <ProgressBar
        value={rowData.success_rate}
        showValue={false}
        className="h-2 w-24"
        color={
          rowData.success_rate >= 80
            ? '#10B981'
            : rowData.success_rate >= 60
              ? '#F59E0B'
              : '#EF4444'
        }
      />
      <span className="text-sm font-medium">{rowData.success_rate.toFixed(1)}%</span>
    </div>
  );

  if (loading && !stats) {
    return (
      <div className="flex items-center justify-center p-8">
        <i className="pi pi-spin pi-spinner text-4xl text-blue-600" />
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Performance Stats Cards */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-5 gap-4">
        <Card className="shadow-md">
          <div className="text-center">
            <i className="pi pi-clock text-3xl text-blue-500 mb-2" />
            <p className="text-sm text-slate-500">Avg Duration</p>
            <p className="text-xl font-bold text-slate-800">
              {formatDuration(stats?.avg_duration || 0)}
            </p>
          </div>
        </Card>

        <Card className="shadow-md">
          <div className="text-center">
            <i className="pi pi-stopwatch text-3xl text-purple-500 mb-2" />
            <p className="text-sm text-slate-500">Median Duration</p>
            <p className="text-xl font-bold text-slate-800">
              {formatDuration(stats?.median_duration || 0)}
            </p>
          </div>
        </Card>

        <Card className="shadow-md">
          <div className="text-center">
            <i className="pi pi-chart-bar text-3xl text-orange-500 mb-2" />
            <p className="text-sm text-slate-500">P95 Duration</p>
            <p className="text-xl font-bold text-slate-800">
              {formatDuration(stats?.p95_duration || 0)}
            </p>
          </div>
        </Card>

        <Card className="shadow-md">
          <div className="text-center">
            <i className="pi pi-check-circle text-3xl text-green-500 mb-2" />
            <p className="text-sm text-slate-500">Success Rate</p>
            <p className="text-xl font-bold text-slate-800">{stats?.success_rate.toFixed(1)}%</p>
          </div>
        </Card>

        <Card className="shadow-md">
          <div className="text-center">
            <i className="pi pi-check text-3xl text-teal-500 mb-2" />
            <p className="text-sm text-slate-500">Completed</p>
            <p className="text-xl font-bold text-slate-800">{stats?.total_completed || 0}</p>
          </div>
        </Card>
      </div>

      {/* Charts Row */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Performance Trend */}
        <Card className="shadow-md">
          <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-2 mb-4">
            <h3 className="text-base sm:text-lg font-semibold text-slate-800">
              Performance Trend (30d)
            </h3>
            <Button
              icon="pi pi-refresh"
              className="p-button-outlined p-button-sm"
              onClick={fetchPerformanceData}
              loading={loading}
            />
          </div>
          <div className="h-56 sm:h-64">
            <Chart type="line" data={trendChartData} options={trendChartOptions} />
          </div>
        </Card>

        {/* Quick vs Deep Comparison */}
        <Card className="shadow-md">
          <h3 className="text-base sm:text-lg font-semibold text-slate-800 mb-4">Quick vs Deep</h3>
          <div className="h-56 sm:h-64">
            <Chart type="bar" data={comparisonChartData} options={comparisonChartOptions} />
          </div>
        </Card>
      </div>

      {/* Performance by Type Table */}
      <Card className="shadow-md">
        <h3 className="text-lg font-semibold text-slate-800 mb-4">Performance by Analysis Type</h3>
        <div className="overflow-x-auto">
          <DataTable value={byType} loading={loading} className="text-sm">
            <Column header="Type" body={typeTemplate} style={{ width: '100px' }} />
            <Column field="total_runs" header="Runs" style={{ width: '80px' }} />
            <Column field="completed" header="Done" style={{ width: '80px' }} />
            <Column field="failed" header="Fail" style={{ width: '70px' }} />
            <Column header="Avg Time" body={durationTemplate} style={{ width: '100px' }} />
            <Column header="Success" body={successRateTemplate} />
          </DataTable>
        </div>
      </Card>

      {/* Insights */}
      <Card className="shadow-md bg-gradient-to-r from-blue-50 to-purple-50">
        <h3 className="text-lg font-semibold text-slate-800 mb-4">
          <i className="pi pi-lightbulb mr-2 text-yellow-500" />
          Performance Insights
        </h3>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {byType.map((type) => (
            <div key={type.type} className="bg-white rounded-lg p-4 shadow-sm">
              <h4 className="font-medium text-slate-700 mb-2">
                {type.type.charAt(0).toUpperCase() + type.type.slice(1)} Analysis
              </h4>
              <ul className="text-sm text-slate-600 space-y-1">
                <li>
                  <span className="text-slate-400">Avg completion time:</span>{' '}
                  <strong>{formatDuration(type.avg_duration)}</strong>
                </li>
                <li>
                  <span className="text-slate-400">Success rate:</span>{' '}
                  <strong
                    className={
                      type.success_rate >= 80
                        ? 'text-green-600'
                        : type.success_rate >= 60
                          ? 'text-yellow-600'
                          : 'text-red-600'
                    }
                  >
                    {type.success_rate.toFixed(1)}%
                  </strong>
                </li>
                <li>
                  <span className="text-slate-400">Failure rate:</span>{' '}
                  <strong>{((type.failed / type.total_runs) * 100).toFixed(1)}%</strong>
                </li>
              </ul>
            </div>
          ))}
        </div>
      </Card>
    </div>
  );
};

export default PerformanceAnalytics;
