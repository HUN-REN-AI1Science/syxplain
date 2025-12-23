/**
 * UsageStatsSection Component
 * Displays usage statistics (total runs count)
 */

import React from 'react';
import type { ProfileData } from '@/types';

interface UsageStatsSectionProps {
  profile: ProfileData | null;
}

export const UsageStatsSection: React.FC<UsageStatsSectionProps> = ({ profile }) => (
  <div className="mb-6">
    <div className="flex items-center gap-2 mb-4">
      <i className="pi pi-chart-bar text-blue-600 text-xl"></i>
      <h3 className="text-lg font-semibold text-slate-700">Usage Statistics</h3>
    </div>
    <div className="bg-blue-50 rounded-xl p-4 md:p-6 text-center border border-blue-100 w-full">
      <p className="text-2xl md:text-3xl font-bold text-blue-600">{profile?.total_runs || 0}</p>
      <p className="text-slate-600 text-xs md:text-sm mt-1">Analysis Runs</p>
    </div>
  </div>
);

export default UsageStatsSection;
