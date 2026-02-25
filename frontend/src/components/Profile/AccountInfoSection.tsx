/**
 * AccountInfoSection Component
 * Displays user info, role/permissions, and Keycloak account management actions
 */

import React from 'react';
import { Tag } from 'primereact/tag';
import type { ProfileData } from '@/types';

interface AccountInfoSectionProps {
  profile: ProfileData | null;
  hasHunrenAccess?: boolean;
  isAdmin?: boolean;
  userName?: string;
}

export const AccountInfoSection: React.FC<AccountInfoSectionProps> = ({
  profile,
  hasHunrenAccess = false,
  isAdmin = false,
  userName,
}) => (
  <div className="mb-6">
    <div className="flex items-center gap-2 mb-4">
      <i className="pi pi-user text-blue-600 text-xl"></i>
      <h3 className="text-lg font-semibold text-slate-700">Account Information</h3>
    </div>
    <div className="bg-slate-50 rounded-xl p-4 md:p-6 space-y-4">
      {userName && (
        <div className="flex flex-col sm:flex-row sm:items-center gap-1 sm:gap-4">
          <span className="text-slate-500 text-sm sm:w-32 font-medium">Name</span>
          <span className="font-medium text-slate-800">{userName}</span>
        </div>
      )}
      <div className="flex flex-col sm:flex-row sm:items-center gap-1 sm:gap-4">
        <span className="text-slate-500 text-sm sm:w-32 font-medium">Email</span>
        <span className="font-medium text-slate-800 break-all">{profile?.email}</span>
      </div>
      {profile?.created_at && (
        <div className="flex flex-col sm:flex-row sm:items-center gap-1 sm:gap-4">
          <span className="text-slate-500 text-sm sm:w-32 font-medium">Member since</span>
          <span className="font-medium text-slate-800">
            {new Date(profile.created_at).toLocaleDateString('en-US', {
              year: 'numeric',
              month: 'long',
              day: 'numeric',
            })}
          </span>
        </div>
      )}
      <div className="flex flex-col sm:flex-row sm:items-center gap-1 sm:gap-4">
        <span className="text-slate-500 text-sm sm:w-32 font-medium">Role</span>
        <div className="flex flex-wrap gap-2">
          {isAdmin ? (
            <Tag severity="warning" value="Administrator" icon="pi pi-shield" />
          ) : hasHunrenAccess ? (
            <Tag severity="success" value="HUN-REN Member" icon="pi pi-check-circle" />
          ) : (
            <Tag severity="info" value="Standard User" icon="pi pi-user" />
          )}
        </div>
      </div>
      <div className="flex flex-col sm:flex-row sm:items-center gap-1 sm:gap-4">
        <span className="text-slate-500 text-sm sm:w-32 font-medium">API Access</span>
        <div className="flex flex-wrap gap-2">
          {hasHunrenAccess ? (
            <span className="text-sm text-green-700 flex items-center gap-1">
              <i className="pi pi-check text-green-600"></i>
              Using built-in HUN-REN API keys
            </span>
          ) : (
            <span className="text-sm text-amber-700 flex items-center gap-1">
              <i className="pi pi-key text-amber-600"></i>
              Requires personal OpenAI API key
            </span>
          )}
        </div>
      </div>
    </div>
  </div>
);

export default AccountInfoSection;
