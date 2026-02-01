/**
 * AdminView Page
 * Admin user management interface for granting/revoking HUN-REN API key access
 * Used as a tab within AdminLayout
 */

import React, { useState, useEffect, useRef } from 'react';
import { DataTable } from 'primereact/datatable';
import { Column } from 'primereact/column';
import { Button } from 'primereact/button';
import { InputText } from 'primereact/inputtext';
import { Toast } from 'primereact/toast';
import { ConfirmDialog, confirmDialog } from 'primereact/confirmdialog';
import { Tag } from 'primereact/tag';
import { InputSwitch } from 'primereact/inputswitch';
import { adminService } from '@services/api';
import { useAuth } from '@contexts/AuthContext';
import HelpButton from '@components/HelpButton';
import type { UserPermissionInfo } from '@/types';

const AdminView: React.FC = () => {
  const { isAdmin } = useAuth();
  const [users, setUsers] = useState<UserPermissionInfo[]>([]);
  const [loading, setLoading] = useState(true);
  const [globalFilter, setGlobalFilter] = useState('');
  const toast = useRef<Toast>(null);

  // Fetch users on mount
  useEffect(() => {
    if (isAdmin) {
      fetchUsers();
    }
  }, [isAdmin]);

  const fetchUsers = async () => {
    try {
      setLoading(true);
      const response = await adminService.getUsers();
      setUsers(response.data.users);
    } catch (error: unknown) {
      toast.current?.show({
        severity: 'error',
        summary: 'Error',
        detail: 'Failed to load users'
      });
    } finally {
      setLoading(false);
    }
  };

  const handleTogglePermission = async (user: UserPermissionInfo) => {
    const newValue = !user.use_hunren_keys;
    const action = newValue ? 'grant' : 'revoke';

    confirmDialog({
      message: `Are you sure you want to ${action} HUN-REN API key access for ${user.email}?`,
      header: `${newValue ? 'Grant' : 'Revoke'} Access`,
      icon: newValue ? 'pi pi-check-circle' : 'pi pi-exclamation-triangle',
      acceptClassName: newValue ? 'p-button-success' : 'p-button-danger',
      accept: async () => {
        try {
          await adminService.updateUserPermission(user.user_id, newValue);
          toast.current?.show({
            severity: 'success',
            summary: 'Success',
            detail: `HUN-REN access ${action}ed for ${user.email}`
          });
          fetchUsers();
        } catch (error: unknown) {
          const err = error as { response?: { data?: { detail?: string } } };
          toast.current?.show({
            severity: 'error',
            summary: 'Error',
            detail: err.response?.data?.detail || `Failed to ${action} access`
          });
        }
      }
    });
  };

  const emailBodyTemplate = (rowData: UserPermissionInfo) => (
    <div className="flex items-center gap-2">
      <i className="pi pi-user text-slate-400" />
      <span className="font-medium">{rowData.email}</span>
    </div>
  );

  const statusBodyTemplate = (rowData: UserPermissionInfo) => {
    return rowData.use_hunren_keys ? (
      <Tag severity="success" value="HUN-REN Access" icon="pi pi-check" />
    ) : (
      <Tag severity="secondary" value="Standard" icon="pi pi-user" />
    );
  };

  const accessToggleTemplate = (rowData: UserPermissionInfo) => (
    <div className="flex items-center gap-3">
      <InputSwitch
        checked={rowData.use_hunren_keys}
        onChange={() => handleTogglePermission(rowData)}
      />
      <span className="text-sm text-slate-600">
        {rowData.use_hunren_keys ? 'Enabled' : 'Disabled'}
      </span>
    </div>
  );

  const dateBodyTemplate = (rowData: UserPermissionInfo) => {
    const date = rowData.user_created_at;
    if (!date) return '-';
    return new Date(date).toLocaleDateString('en-US', {
      year: 'numeric',
      month: 'short',
      day: 'numeric'
    });
  };

  const grantedByTemplate = (rowData: UserPermissionInfo) => {
    if (!rowData.granted_by) return <span className="text-slate-400">-</span>;
    return (
      <span className="text-sm text-slate-600">{rowData.granted_by}</span>
    );
  };

  const header = (
    <div className="flex flex-col sm:flex-row justify-between items-start sm:items-center gap-4">
      <InputText
        value={globalFilter}
        onChange={(e) => setGlobalFilter(e.target.value)}
        placeholder="Search by email..."
        className="w-full sm:w-80"
      />
      <Button
        icon="pi pi-refresh"
        label="Refresh"
        className="p-button-outlined p-button-sm"
        onClick={fetchUsers}
        loading={loading}
      />
    </div>
  );

  return (
    <div>
      <Toast ref={toast} />
      <ConfirmDialog />

      {/* Header */}
      <div className="mb-6">
        <div className="flex items-center gap-2 mb-2">
          <h3 className="text-lg font-semibold text-slate-800">User Management</h3>
          <HelpButton title="User Management">
            <h4>Managing API Access</h4>
            <p>
              Control which users can use the built-in HUN-REN API keys for analysis.
              Users without access must provide their own OpenAI API key.
            </p>

            <h4>Permission Levels</h4>
            <ul>
              <li><strong>HUN-REN Access</strong> - User can use built-in API keys</li>
              <li><strong>Standard</strong> - User must provide their own OpenAI key</li>
            </ul>

            <h4>How to Grant Access</h4>
            <p>
              Use the toggle switch in the "HUN-REN Access" column to enable or disable
              access for any user. Changes take effect immediately.
            </p>
          </HelpButton>
        </div>
        <p className="text-sm text-slate-500">Manage HUN-REN API key access for users</p>
      </div>

      {/* Users Table */}
      <div className={`transition-opacity duration-200 overflow-x-auto ${loading ? 'opacity-60' : 'opacity-100'}`}>
        <DataTable
          value={users}
          loading={loading}
          paginator
          rows={10}
          rowsPerPageOptions={[10, 25, 50]}
          globalFilter={globalFilter}
          header={header}
          emptyMessage="No users found"
          className="w-full"
          paginatorTemplate="FirstPageLink PrevPageLink PageLinks NextPageLink LastPageLink CurrentPageReport"
          currentPageReportTemplate="Showing {first} to {last} of {totalRecords} users"
        >
          <Column
            field="email"
            header="User"
            body={emailBodyTemplate}
            sortable
            filter
            filterPlaceholder="Search email"
          />
          <Column
            field="use_hunren_keys"
            header="Status"
            body={statusBodyTemplate}
            sortable
            style={{ width: '150px' }}
          />
          <Column
            header="HUN-REN Access"
            body={accessToggleTemplate}
            style={{ width: '180px' }}
          />
          <Column
            field="user_created_at"
            header="Joined"
            body={dateBodyTemplate}
            sortable
            style={{ width: '140px' }}
          />
          <Column
            field="granted_by"
            header="Granted By"
            body={grantedByTemplate}
            style={{ width: '200px' }}
          />
        </DataTable>
      </div>

      {/* Info Box */}
      <div className="mt-6 bg-blue-50 border border-blue-200 rounded-lg p-4">
        <div className="flex items-start gap-3">
          <i className="pi pi-info-circle text-blue-600 mt-0.5" />
          <div>
            <h4 className="font-semibold text-blue-800 mb-2">About Permissions</h4>
            <ul className="text-sm text-blue-700 list-disc pl-5 space-y-1">
              <li><strong>HUN-REN Access:</strong> User can use built-in API keys for analysis</li>
              <li><strong>Standard:</strong> User must provide their own OpenAI API key</li>
              <li>Admin users are defined by the <code className="bg-blue-100 px-1 rounded">ADMIN_EMAILS</code> environment variable</li>
              <li>User-provided API keys are never stored - they exist only in memory during analysis</li>
            </ul>
          </div>
        </div>
      </div>
    </div>
  );
};

export default AdminView;
