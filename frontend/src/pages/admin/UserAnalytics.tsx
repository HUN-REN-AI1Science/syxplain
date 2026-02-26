/**
 * UserAnalytics Component
 * User growth, activity, and top users analytics
 */

import React, { useState, useEffect, useCallback, RefObject } from 'react';
import { Card } from 'primereact/card';
import { Toast } from 'primereact/toast';
import { Chart } from 'primereact/chart';
import { DataTable } from 'primereact/datatable';
import { Column } from 'primereact/column';
import { Dropdown } from 'primereact/dropdown';
import { Button } from 'primereact/button';
import { Tag } from 'primereact/tag';
import { ProgressBar } from 'primereact/progressbar';
import { adminService } from '@services/api';
import type { UserGrowthItem, TopUserItem, DashboardStats } from '@/types';

interface UserAnalyticsProps {
  toast: RefObject<Toast | null>;
}

const UserAnalytics: React.FC<UserAnalyticsProps> = ({ toast }) => {
  const [stats, setStats] = useState<DashboardStats | null>(null);
  const [growth, setGrowth] = useState<UserGrowthItem[]>([]);
  const [topUsers, setTopUsers] = useState<TopUserItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [growthDays, setGrowthDays] = useState(90);
  const [topUsersDays, setTopUsersDays] = useState(30);

  const daysOptions = [
    { label: 'Last 30 days', value: 30 },
    { label: 'Last 90 days', value: 90 },
    { label: 'Last 180 days', value: 180 },
    { label: 'Last year', value: 365 },
  ];

  const topUsersPeriodOptions = [
    { label: 'Last 7 days', value: 7 },
    { label: 'Last 30 days', value: 30 },
    { label: 'Last 90 days', value: 90 },
  ];

  const fetchAnalytics = useCallback(async () => {
    try {
      setLoading(true);
      const [statsRes, growthRes, topRes] = await Promise.all([
        adminService.getDashboardStats(),
        adminService.getUserGrowth(growthDays),
        adminService.getTopUsers(10, topUsersDays),
      ]);
      setStats(statsRes.data);
      setGrowth(growthRes.data.items);
      setTopUsers(topRes.data.items);
    } catch (error: unknown) {
      toast.current?.show({
        severity: 'error',
        summary: 'Error',
        detail: 'Failed to load user analytics',
      });
    } finally {
      setLoading(false);
    }
  }, [growthDays, topUsersDays, toast]);

  useEffect(() => {
    fetchAnalytics();
  }, [fetchAnalytics]);

  // Calculate cumulative growth
  const cumulativeGrowth = growth.reduce<{ date: string; cumulative: number; daily: number }[]>(
    (acc, item) => {
      const prevTotal = acc.length > 0 ? acc[acc.length - 1].cumulative : 0;
      acc.push({
        date: item.date,
        daily: item.count,
        cumulative: prevTotal + item.count,
      });
      return acc;
    },
    []
  );

  const growthChartData = {
    labels: cumulativeGrowth.map((g) => g.date),
    datasets: [
      {
        label: 'Total Users',
        data: cumulativeGrowth.map((g) => g.cumulative),
        borderColor: '#3B82F6',
        backgroundColor: 'rgba(59, 130, 246, 0.1)',
        fill: true,
        tension: 0.4,
        yAxisID: 'y',
      },
      {
        label: 'New Users',
        data: cumulativeGrowth.map((g) => g.daily),
        borderColor: '#10B981',
        backgroundColor: 'transparent',
        tension: 0.4,
        yAxisID: 'y1',
        type: 'bar' as const,
      },
    ],
  };

  const growthChartOptions = {
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
          text: 'Total Users',
        },
      },
      y1: {
        type: 'linear' as const,
        display: true,
        position: 'right' as const,
        beginAtZero: true,
        title: {
          display: true,
          text: 'New Users',
        },
        grid: {
          drawOnChartArea: false,
        },
      },
    },
  };

  const maxRunCount = topUsers.length > 0 ? Math.max(...topUsers.map((u) => u.run_count)) : 1;

  const rankTemplate = (_rowData: TopUserItem, options: { rowIndex: number }) => {
    const rank = options.rowIndex + 1;
    let className = 'w-8 h-8 rounded-full flex items-center justify-center font-bold text-white ';
    if (rank === 1) className += 'bg-yellow-500';
    else if (rank === 2) className += 'bg-slate-400';
    else if (rank === 3) className += 'bg-amber-600';
    else className += 'bg-slate-300 text-primary';

    return <div className={className}>{rank}</div>;
  };

  const userTemplate = (rowData: TopUserItem) => (
    <div className="flex flex-col">
      <span className="font-medium">{rowData.email || 'Unknown User'}</span>
      <span className="text-xs text-muted font-mono">{rowData.user_id.substring(0, 8)}...</span>
    </div>
  );

  const runsTemplate = (rowData: TopUserItem) => (
    <div className="flex flex-col gap-1">
      <div className="flex items-center gap-2">
        <span className="font-bold text-lg">{rowData.run_count}</span>
        <span className="text-sm text-secondary">runs</span>
      </div>
      <ProgressBar
        value={(rowData.run_count / maxRunCount) * 100}
        showValue={false}
        className="h-2"
      />
    </div>
  );

  const successTemplate = (rowData: TopUserItem) => {
    const rate = rowData.run_count > 0 ? (rowData.completed / rowData.run_count) * 100 : 0;
    return (
      <div className="flex items-center gap-2">
        <Tag
          value={`${rate.toFixed(0)}%`}
          severity={rate >= 80 ? 'success' : rate >= 60 ? 'warning' : 'danger'}
        />
        <span className="text-xs text-secondary">({rowData.completed} completed)</span>
      </div>
    );
  };

  if (loading && !stats) {
    return (
      <div className="flex items-center justify-center p-8">
        <i className="pi pi-spin pi-spinner text-4xl text-brand-500" />
      </div>
    );
  }

  // Calculate new users in period
  const totalNewUsers = growth.reduce((sum, g) => sum + g.count, 0);

  return (
    <div className="space-y-6">
      {/* User Stats Cards */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        <Card className="shadow-md">
          <div className="flex items-center gap-3">
            <div className="p-3 bg-blue-100 rounded-lg">
              <i className="pi pi-users text-2xl text-brand-500" />
            </div>
            <div>
              <p className="text-sm text-secondary">Total Users</p>
              <p className="text-2xl font-bold font-heading text-primary">{stats?.total_users || 0}</p>
            </div>
          </div>
        </Card>

        <Card className="shadow-md">
          <div className="flex items-center gap-3">
            <div className="p-3 bg-green-100 rounded-lg">
              <i className="pi pi-user-plus text-2xl text-green-600" />
            </div>
            <div>
              <p className="text-sm text-secondary">New ({growthDays}d)</p>
              <p className="text-2xl font-bold font-heading text-primary">{totalNewUsers}</p>
            </div>
          </div>
        </Card>

        <Card className="shadow-md">
          <div className="flex items-center gap-3">
            <div className="p-3 bg-purple-100 rounded-lg">
              <i className="pi pi-bolt text-2xl text-purple-600" />
            </div>
            <div>
              <p className="text-sm text-secondary">Active (24h)</p>
              <p className="text-2xl font-bold font-heading text-primary">{stats?.active_users_24h || 0}</p>
            </div>
          </div>
        </Card>

        <Card className="shadow-md">
          <div className="flex items-center gap-3">
            <div className="p-3 bg-orange-100 rounded-lg">
              <i className="pi pi-chart-line text-2xl text-orange-600" />
            </div>
            <div>
              <p className="text-sm text-secondary">Avg Runs/Day</p>
              <p className="text-2xl font-bold font-heading text-primary">
                {growthDays > 0 ? ((stats?.total_runs || 0) / growthDays).toFixed(1) : 0}
              </p>
            </div>
          </div>
        </Card>
      </div>

      {/* Growth Chart */}
      <Card className="shadow-md">
        <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3 mb-4">
          <h3 className="text-lg font-semibold font-heading text-primary">User Growth</h3>
          <div className="flex items-center gap-2">
            <Dropdown
              value={growthDays}
              options={daysOptions}
              onChange={(e) => setGrowthDays(e.value)}
              className="w-48"
            />
            <Button
              icon="pi pi-refresh"
              className="p-button-outlined p-button-sm"
              onClick={fetchAnalytics}
              loading={loading}
            />
          </div>
        </div>
        <div className="h-64 sm:h-80">
          {growth.length > 0 ? (
            <Chart type="bar" data={growthChartData} options={growthChartOptions} />
          ) : (
            <div className="flex items-center justify-center h-full text-muted">
              No user growth data available
            </div>
          )}
        </div>
      </Card>

      {/* Top Users */}
      <Card className="shadow-md">
        <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3 mb-4">
          <h3 className="text-lg font-semibold font-heading text-primary">Top Users</h3>
          <Dropdown
            value={topUsersDays}
            options={topUsersPeriodOptions}
            onChange={(e) => setTopUsersDays(e.value)}
            className="w-48"
          />
        </div>
        <div className="overflow-x-auto">
          <DataTable
            value={topUsers}
            loading={loading}
            emptyMessage="No users found"
            className="text-sm"
          >
            <Column header="Rank" body={rankTemplate} style={{ width: '60px' }} />
            <Column header="User" body={userTemplate} />
            <Column header="Activity" body={runsTemplate} />
            <Column header="Success Rate" body={successTemplate} />
          </DataTable>
        </div>
      </Card>
    </div>
  );
};

export default UserAnalytics;
