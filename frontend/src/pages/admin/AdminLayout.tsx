/**
 * AdminLayout Component
 * Main admin panel layout with tab navigation
 */

import React, { useState, useRef } from 'react';
import { Toast } from 'primereact/toast';
import { Button } from 'primereact/button';
import { useAuth } from '@contexts/AuthContext';
import { Navigate } from 'react-router-dom';
import AdminDashboard from './AdminDashboard';
import RunManagement from './RunManagement';
import ErrorMonitoring from './ErrorMonitoring';
import SystemMonitor from './SystemMonitor';
import AuditLogs from './AuditLogs';
import UserAnalytics from './UserAnalytics';
import PerformanceAnalytics from './PerformanceAnalytics';
import ConfigView from './ConfigView';

interface AdminLayoutProps {
  onBack?: () => void;
}

interface TabItem {
  label: string;
  icon: string;
}

const AdminLayout: React.FC<AdminLayoutProps> = ({ onBack }) => {
  const { isAdmin, loading: authLoading } = useAuth();
  const [activeIndex, setActiveIndex] = useState(0);
  const toast = useRef<Toast>(null);

  const tabs: TabItem[] = [
    { label: 'Dashboard', icon: 'pi pi-home' },
    { label: 'Runs', icon: 'pi pi-play' },
    { label: 'Errors', icon: 'pi pi-exclamation-triangle' },
    { label: 'System', icon: 'pi pi-server' },
    { label: 'Audit', icon: 'pi pi-history' },
    { label: 'Analytics', icon: 'pi pi-chart-bar' },
    { label: 'Config', icon: 'pi pi-cog' },
  ];

  // Redirect non-admin users
  if (!authLoading && !isAdmin) {
    return <Navigate to="/" replace />;
  }

  if (authLoading) {
    return (
      <div className="flex items-center justify-center p-8">
        <i className="pi pi-spin pi-spinner text-4xl text-blue-600" />
      </div>
    );
  }

  const renderContent = () => {
    switch (activeIndex) {
      case 0:
        return <AdminDashboard toast={toast} />;
      case 1:
        return <RunManagement toast={toast} />;
      case 2:
        return <ErrorMonitoring toast={toast} />;
      case 3:
        return <SystemMonitor toast={toast} />;
      case 4:
        return <AuditLogs toast={toast} />;
      case 5:
        // Analytics tab shows both user and performance analytics
        return (
          <div className="space-y-6">
            <UserAnalytics toast={toast} />
            <PerformanceAnalytics toast={toast} />
          </div>
        );
      case 6:
        return <ConfigView toast={toast} />;
      default:
        return <AdminDashboard toast={toast} />;
    }
  };

  return (
    <div className="p-4 sm:p-6">
      <Toast ref={toast} />

      {/* Header */}
      <div className="mb-6">
        <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
          <div>
            <h2 className="text-2xl font-bold text-slate-800">Admin Control Panel</h2>
            <p className="text-slate-500">Monitor and manage your Syxplain instance</p>
          </div>
          {onBack && (
            <Button
              label="Back"
              icon="pi pi-arrow-left"
              className="p-button-outlined p-button-sm w-full sm:w-auto"
              onClick={onBack}
            />
          )}
        </div>
      </div>

      {/* Tab Navigation */}
      <div className="mb-6">
        <div className="flex flex-wrap gap-2 p-1 bg-slate-100 rounded-lg">
          {tabs.map((tab, index) => (
            <button
              key={index}
              onClick={() => setActiveIndex(index)}
              aria-label={tab.label}
              aria-current={activeIndex === index ? 'true' : undefined}
              className={`
                flex items-center gap-2 px-4 py-2.5 rounded-md font-medium text-sm
                transition-all duration-200 ease-in-out
                ${
                  activeIndex === index
                    ? 'bg-white text-blue-600 shadow-md ring-1 ring-blue-100'
                    : 'text-slate-600 hover:bg-white/60 hover:text-slate-800 cursor-pointer'
                }
              `}
            >
              <i
                className={`${tab.icon} ${activeIndex === index ? 'text-blue-500' : 'text-slate-400'}`}
              />
              <span className="hidden sm:inline">{tab.label}</span>
            </button>
          ))}
        </div>
      </div>

      {/* Content */}
      <div className="min-h-[500px]">{renderContent()}</div>
    </div>
  );
};

export default AdminLayout;
