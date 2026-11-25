/**
 * AccountInfoSection Component
 * Displays user info, role/permissions, and Keycloak account management actions
 */

import React from 'react';
import { Tag } from 'primereact/tag';
import type { ProfileData } from '@/types';

interface AccountInfoSectionProps {
  profile: ProfileData | null;
  hasServerKeysAccess?: boolean;
  isAdmin?: boolean;
  userName?: string;
}

export const AccountInfoSection: React.FC<AccountInfoSectionProps> = ({
  profile,
  hasServerKeysAccess = false,
  isAdmin = false,
  userName,
}) => (
  <div className="mb-6">
    <div className="flex items-center gap-2 mb-4">
      <i className="pi pi-user text-brand-500 text-xl"></i>
      <h3 className="text-lg font-heading font-semibold text-primary">Account Information</h3>
    </div>
    <div className="bg-surface-alt rounded-xl p-4 md:p-6 space-y-4">
      {userName && (
        <div className="flex flex-col sm:flex-row sm:items-center gap-1 sm:gap-4">
          <span className="text-secondary text-sm sm:w-32 font-medium">Name</span>
          <span className="font-medium text-primary">{userName}</span>
        </div>
      )}
      <div className="flex flex-col sm:flex-row sm:items-center gap-1 sm:gap-4">
        <span className="text-secondary text-sm sm:w-32 font-medium">Email</span>
        <span className="font-medium text-primary break-all">{profile?.email}</span>
      </div>
      {profile?.created_at && (
        <div className="flex flex-col sm:flex-row sm:items-center gap-1 sm:gap-4">
          <span className="text-secondary text-sm sm:w-32 font-medium">Member since</span>
          <span className="font-medium text-primary">
            {new Date(profile.created_at).toLocaleDateString('en-US', {
              year: 'numeric',
              month: 'long',
              day: 'numeric',
            })}
          </span>
        </div>
      )}
      <div className="flex flex-col sm:flex-row sm:items-center gap-1 sm:gap-4">
        <span className="text-secondary text-sm sm:w-32 font-medium">Role</span>
        <div className="flex flex-wrap gap-2">
          {isAdmin ? (
            <Tag severity="warning" value="Administrator" icon="pi pi-shield" />
          ) : hasServerKeysAccess ? (
            <Tag severity="success" value="Server Keys Access" icon="pi pi-check-circle" />
          ) : (
            <Tag severity="info" value="Standard User" icon="pi pi-user" />
          )}
        </div>
      </div>
      <div className="flex flex-col sm:flex-row sm:items-center gap-1 sm:gap-4">
        <span className="text-secondary text-sm sm:w-32 font-medium">API Access</span>
        <div className="flex flex-wrap gap-2">
          {hasServerKeysAccess ? (
            <span className="text-sm text-green-700 flex items-center gap-1">
              <i className="pi pi-check text-green-600"></i>
              Using the server's built-in API keys
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
