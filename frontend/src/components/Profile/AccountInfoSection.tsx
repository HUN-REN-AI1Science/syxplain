/**
 * AccountInfoSection Component
 * Displays user email and member since date
 */

import React from 'react';
import type { ProfileData } from '@/types';

interface AccountInfoSectionProps {
  profile: ProfileData | null;
}

export const AccountInfoSection: React.FC<AccountInfoSectionProps> = ({ profile }) => (
  <div className="mb-6">
    <div className="flex items-center gap-2 mb-4">
      <i className="pi pi-user text-blue-600 text-xl"></i>
      <h3 className="text-lg font-semibold text-slate-700">Account Information</h3>
    </div>
    <div className="bg-slate-50 rounded-xl p-4 md:p-6 space-y-4">
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
              day: 'numeric'
            })}
          </span>
        </div>
      )}
    </div>
  </div>
);

export default AccountInfoSection;
