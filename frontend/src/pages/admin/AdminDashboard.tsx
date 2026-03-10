/**
 * AdminDashboard Component
 * Dashboard overview with key metrics and visualizations
 */

import React, { useState, useEffect, useCallback, RefObject } from 'react';
import { Card } from 'primereact/card';
import { Toast } from 'primereact/toast';
import { Chart } from 'primereact/chart';
import { Tag } from 'primereact/tag';
import { ProgressBar } from 'primereact/progressbar';
import { adminService } from '@services/api';
import type { DashboardStats, RunTrendItem, StatusDistributionItem, ActivityItem } from '@/types';

interface AdminDashboardProps {
  toast: RefObject<Toast | null>;
}

const AdminDashboard: React.FC<AdminDashboardProps> = ({ toast }) => {
  const [stats, setStats] = useState<DashboardStats | null>(null);
  const [trends, setTrends] = useState<RunTrendItem[]>([]);
  const [distribution, setDistribution] = useState<StatusDistributionItem[]>([]);
  const [activity, setActivity] = useState<ActivityItem[]>([]);
  const [loading, setLoading] = useState(true);

  const fetchDashboardData = useCallback(async () => {
    try {
      setLoading(true);
      const [statsRes, trendsRes, distRes, activityRes] = await Promise.all([
        adminService.getDashboardStats(),
        adminService.getRunTrends(30),
        adminService.getStatusDistribution(),
        adminService.getRecentActivity(5),
      ]);
      setStats(statsRes.data);
      setTrends(trendsRes.data.items);
      setDistribution(distRes.data.items);
      setActivity(activityRes.data.items);
    } catch (error: unknown) {
      toast.current?.show({
        severity: 'error',
        summary: 'Error',
        detail: 'Failed to load dashboard data',
      });
    } finally {
      setLoading(false);
    }
  }, [toast]);

  useEffect(() => {
    fetchDashboardData();
  }, [fetchDashboardData]);

  const formatDuration = (seconds: number): string => {
    if (seconds < 60) return `${Math.round(seconds)}s`;
    if (seconds < 3600) return `${Math.round(seconds / 60)}m`;
    return `${Math.round(seconds / 3600)}h`;
  };

  const trendChartData = {
    labels: trends.map((t) => t.date),
    datasets: [
      {
        label: 'Total',
        data: trends.map((t) => t.total),
        borderColor: '#3B82F6',
        backgroundColor: 'rgba(59, 130, 246, 0.1)',
        fill: true,
        tension: 0.4,
      },
      {
        label: 'Completed',
        data: trends.map((t) => t.completed),
        borderColor: '#10B981',
        backgroundColor: 'transparent',
        tension: 0.4,
      },
      {
        label: 'Failed',
        data: trends.map((t) => t.failed + t.timeout),
        borderColor: '#EF4444',
        backgroundColor: 'transparent',
        tension: 0.4,
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
        beginAtZero: true,
      },
    },
  };

  const statusColors: Record<string, string> = {
    completed: '#10B981',
    failed: '#EF4444',
    running: '#3B82F6',
    pending: '#F59E0B',
    timeout: '#8B5CF6',
    cancelled: '#6B7280',
  };

  const distributionChartData = {
    labels: distribution.map((d) => d.status),
    datasets: [
      {
        data: distribution.map((d) => d.count),
        backgroundColor: distribution.map((d) => statusColors[d.status] || '#6B7280'),
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

  const getActionIcon = (action: string): string => {
    if (action.includes('grant')) return 'pi pi-check-circle';
    if (action.includes('revoke')) return 'pi pi-times-circle';
    if (action.includes('delete')) return 'pi pi-trash';
    if (action.includes('cancel')) return 'pi pi-ban';
    return 'pi pi-cog';
  };

  const getActionSeverity = (action: string): 'success' | 'danger' | 'warning' | 'info' => {
    if (action.includes('grant')) return 'success';
    if (action.includes('revoke') || action.includes('delete')) return 'danger';
    if (action.includes('cancel')) return 'warning';
    return 'info';
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center p-8">
        <i className="pi pi-spin pi-spinner text-4xl text-brand-500" />
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Stats Cards */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        <Card className="shadow-md">
          <div className="flex items-center gap-3">
            <div className="p-3 bg-blue-100 rounded-lg">
              <i className="pi pi-users text-2xl text-brand-500" />
            </div>
            <div>
              <p className="text-sm text-secondary">Total Users</p>
              <p className="text-2xl font-bold font-heading text-primary">
                {stats?.total_users || 0}
              </p>
              <p className="text-xs text-green-600">{stats?.active_users_24h || 0} active today</p>
            </div>
          </div>
        </Card>

        <Card className="shadow-md">
          <div className="flex items-center gap-3">
            <div className="p-3 bg-green-100 rounded-lg">
              <i className="pi pi-play text-2xl text-green-600" />
            </div>
            <div>
              <p className="text-sm text-secondary">Total Runs</p>
              <p className="text-2xl font-bold font-heading text-primary">
                {stats?.total_runs || 0}
              </p>
              <p className="text-xs text-green-600">{stats?.runs_today || 0} today</p>
            </div>
          </div>
        </Card>

        <Card className="shadow-md">
          <div className="flex items-center gap-3">
            <div className="p-3 bg-purple-100 rounded-lg">
              <i className="pi pi-percentage text-2xl text-purple-600" />
            </div>
            <div>
              <p className="text-sm text-secondary">Success Rate</p>
              <p className="text-2xl font-bold font-heading text-primary">
                {stats?.success_rate || 0}%
              </p>
              <ProgressBar
                value={stats?.success_rate || 0}
                showValue={false}
                className="h-1 mt-1"
                color={
                  stats && stats.success_rate >= 80
                    ? '#10B981'
                    : stats && stats.success_rate >= 60
                      ? '#F59E0B'
                      : '#EF4444'
                }
              />
            </div>
          </div>
        </Card>

        <Card className="shadow-md">
          <div className="flex items-center gap-3">
            <div className="p-3 bg-orange-100 rounded-lg">
              <i className="pi pi-clock text-2xl text-orange-600" />
            </div>
            <div>
              <p className="text-sm text-secondary">Avg Duration</p>
              <p className="text-2xl font-bold font-heading text-primary">
                {formatDuration(stats?.avg_duration_seconds || 0)}
              </p>
              <p className="text-xs text-secondary">
                {stats?.pending_runs || 0} pending, {stats?.running_runs || 0} running
              </p>
            </div>
          </div>
        </Card>
      </div>

      {/* Charts Row */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Run Trends Chart */}
        <Card className="shadow-md lg:col-span-2">
          <h3 className="text-lg font-semibold font-heading text-primary mb-4">
            Run Trends (30 Days)
          </h3>
          <div className="h-48 sm:h-64">
            <Chart type="line" data={trendChartData} options={trendChartOptions} />
          </div>
        </Card>

        {/* Status Distribution Chart */}
        <Card className="shadow-md">
          <h3 className="text-lg font-semibold font-heading text-primary mb-4">
            Status Distribution
          </h3>
          <div className="h-48 sm:h-64">
            <Chart
              type="doughnut"
              data={distributionChartData}
              options={distributionChartOptions}
            />
          </div>
        </Card>
      </div>

      {/* Recent Activity */}
      <Card className="shadow-md">
        <h3 className="text-lg font-semibold font-heading text-primary mb-4">
          Recent Admin Activity
        </h3>
        {activity.length === 0 ? (
          <p className="text-secondary text-center py-4">No recent activity</p>
        ) : (
          <div className="space-y-3">
            {activity.map((item) => (
              <div key={item.id} className="flex items-center gap-3 p-3 bg-surface-alt rounded-lg">
                <i className={`${getActionIcon(item.action)} text-lg`} />
                <div className="flex-grow">
                  <p className="text-sm font-medium text-primary">
                    <span className="text-secondary">{item.admin_email}</span> performed{' '}
                    <Tag
                      value={item.action}
                      severity={getActionSeverity(item.action)}
                      className="text-xs"
                    />{' '}
                    on {item.target_type}/{item.target_id.substring(0, 8)}...
                  </p>
                  <p className="text-xs text-secondary">
                    {new Date(item.created_at).toLocaleString()}
                  </p>
                </div>
              </div>
            ))}
          </div>
        )}
      </Card>
    </div>
  );
};

export default AdminDashboard;
